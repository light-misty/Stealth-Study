"""`grading.py` — 结构化批改引擎（06 §2/§3 的四级降级）。

职责边界（06 §1）：只做 prompt 组装、模型调用、四级降级、输出校验；**不落库、不检索**。
落库与检索分别在 `service.py` 与 `library.py`。引擎通过 `ProviderClient.complete`（阻塞式，
`providers/base.py:109-117`）调用模型，取 `turn.text`，由调用方决定是否 `asyncio.to_thread`
包裹（06 §2.2；`grading()` 由 service 层决定线程模型，详见本文件末 GradingEngine）。

降级只能由**输出解析失败**驱动（06 §3.1 总表 + §2.3）：L0 强约束 JSON → L1 填空模板 →
L2 逐维度拆分 → L3 弃结构化（返回 raw_text）。`response_format` 只是 L0 的加分项，成败
只看输出能否通过 `_parse(0, ...)`（ADR-06）。

本文件上半部分是与 kind 无关的**纯解析器**（不依赖模型，直接可测，06 §7-1 的 17 用例）；
下半部分是按 kind 分发的 prompt 组装与 GradingEngine。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from .rubrics import (
    CERT_SCORING_POINTS_SPEC,
    CET_ESSAY_RUBRIC,
    CET_TRANSLATION_RUBRIC,
    ERROR_TYPES_CET,
    ESSAY_BAND_INTERVALS,
    ESSAY_BANDS,
    ESSAY_DIMENSIONS,
    SCORING_POINT_STATUSES,
    TRANSLATION_BAND_MAX,
    TRANSLATION_BAND_MIN,
    TRANSLATION_ERROR_TYPES,
)

# ---- 引擎参数（06 §3.5，T07 验收③） ----
MAX_ERROR_ROWS = 8
CALL_BUDGET = 5
PROVIDER_TIMEOUT_S = 90
TEMPERATURE = 0
DEFAULT_GRADING_START_LEVEL = 0

# ---- L0 JSON schema（作文，06 §3.2） ----
L0_SCHEMA = (
    '{"band": <0|2|5|8|11|14>, "dimension_scores": {"content": <0-5>, "structure": <0-5>, '
    '"language": <0-5>},\n "errors": [{"fragment": "...", "suggestion": "...", '
    '"type": "<错误类型枚举之一>"}],\n "upgraded_demo": "...", "model_answer_outline": "..."}'
)

# ---- L1 填空模板（作文，06 §3.3） ----
L1_TEMPLATE_ROWS = ["档位：<14|11|8|5|2|0>", "内容分：<0-5>", "结构分：<0-5>", "语言分：<0-5>"]
L1_TEMPLATE_ROWS += [
    f"错误{i}：<原文片段> || <修改建议> || <类型>" for i in range(1, MAX_ERROR_ROWS + 1)
]
L1_TEMPLATE_ROWS.append("升格示范：<一段改写>")
L1_TEMPLATE = "\n".join(L1_TEMPLATE_ROWS)

# ---- 作文行式正则 ----
BAND_LINE = re.compile(r"^档位\s*[:：]\s*(\d+)\s*$")
DIM_LINE = re.compile(r"^(内容|结构|语言)分\s*[:：]\s*(\d+)\s*$")
ERROR_LINE = re.compile(r"^错误\s*\d+\s*[:：]\s*(.*)$")
DEMO_LINE = re.compile(r"^升格示范\s*[:：]\s*(.*)$")
L2_BAND_LINE = re.compile(r"结论\s*[:：]\s*(\d+)")
L2_DIM_LINE = re.compile(r"结论\s*[:：]\s*(\d+)\s*[,，、]\s*(\d+)\s*[,，、]\s*(\d+)")
L2_ERROR_LINE = re.compile(r"^\s*(.+?)\s*\|\|\s*(.+?)\s*\|\|\s*(.+?)\s*$")

_DIM_LABEL_MAP = {"内容": "content", "结构": "structure", "语言": "language"}


# ---------------------------------------------------------------------------
# JSON 提取器
# ---------------------------------------------------------------------------


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


def _balanced_object(text: str, start: int) -> Optional[str]:
    depth = 0
    in_str = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_str:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json(text: Optional[str]) -> Tuple[Optional[dict], Optional[str]]:
    """提取首个平衡 JSON 对象并 `json.loads`（06 §3.2）。

    剥 ```json 围栏 → 栈式配对首个 `{...}`（容忍字符串内大括号）→ loads。**不做**激进修复
    （补引号/补逗号）——修出来的数据比降级更危险。失败返回 `reason`。
    """
    if not text or not text.strip():
        return None, "empty_response"
    body = _strip_fence(text)
    start = body.find("{")
    if start < 0:
        return None, "json_invalid"
    candidate = _balanced_object(body, start)
    if candidate is None:
        return None, "json_invalid"
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None, "json_invalid"
    if not isinstance(parsed, dict):
        return None, "json_invalid"
    return parsed, None


def band_for_sum(total: int) -> int:
    """按三维之和反推档位（06 §3.4：取包含该和的最高档）。"""
    for band in ESSAY_BANDS:
        low, high = ESSAY_BAND_INTERVALS[band]
        if low <= total <= high:
            return band
    return 0


# ---------------------------------------------------------------------------
# 作文校验与解析（L0/L1/L2）
# ---------------------------------------------------------------------------


def validate_essay_payload(data: dict) -> Tuple[bool, List[str]]:
    """字段级白名单校验（06 §2.2）：band 白名单、三维 0-5 且落在档位区间、错误类型枚举。"""
    flags: List[str] = []
    band = data.get("band")
    if not isinstance(band, int) or isinstance(band, bool) or band not in ESSAY_BANDS:
        return False, ["schema_violation:band_out_of_whitelist"]

    dims = data.get("dimension_scores")
    if not isinstance(dims, dict):
        return False, ["schema_violation:dimension_scores_missing"]
    values: dict[str, int] = {}
    for key in ESSAY_DIMENSIONS:
        value = dims.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5:
            return False, [f"schema_violation:dimension_{key}_invalid"]
        values[key] = value

    if not ESSAY_BAND_INTERVALS[band][0] <= sum(values.values()) <= ESSAY_BAND_INTERVALS[band][1]:
        flags.append("schema_violation:band_dimension_mismatch")

    errors = data.get("errors")
    if not isinstance(errors, list):
        return False, ["schema_violation:errors_missing"]
    for index, item in enumerate(errors):
        if not isinstance(item, dict):
            return False, [f"schema_violation:error_{index}_not_object"]
        if item.get("type") not in ERROR_TYPES_CET:
            return False, [f"schema_violation:error_{index}_type_unknown"]
        if not isinstance(item.get("fragment"), str) or not isinstance(item.get("suggestion"), str):
            return False, [f"schema_violation:error_{index}_fields_missing"]

    return (not flags), flags


def parse_l0(payload: dict) -> Tuple[bool, dict, List[str], Optional[str]]:
    """L0：对已提取的 JSON 对象做作文白名单校验（06 §2.2）。

    `payload` 是 `extract_json` 已解码的 dict；引擎对 L0 的调用链是
    `extract_json(text)` → `parse_l0(data)`。
    """
    ok, flags = validate_essay_payload(payload)
    if not ok:
        return False, {}, flags, "schema_violation"
    return True, payload, flags, None


def parse_l1(text: Optional[str]) -> Tuple[bool, dict, List[str], Optional[str]]:
    """L1：按行前缀正则提取填空模板槽位（06 §3.3）。"""
    if not text or not text.strip():
        return False, {}, [], "empty_response"
    flags: List[str] = []
    band: Optional[int] = None
    dims: dict[str, int] = {}
    errors: List[dict] = []
    demo: Optional[str] = None

    for raw in text.splitlines():
        line = raw.strip().strip("*").strip()
        if not line:
            continue
        match = BAND_LINE.match(line)
        if match:
            band = int(match.group(1))
            continue
        match = DIM_LINE.match(line)
        if match:
            dims[_DIM_LABEL_MAP[match.group(1)]] = int(match.group(2))
            continue
        match = ERROR_LINE.match(line)
        if match:
            payload = match.group(1).strip()
            if not payload:
                continue
            parts = [piece.strip() for piece in payload.split("||")]
            if len(parts) < 3:
                continue
            fragment, suggestion, kind = parts[0], parts[1], parts[2]
            if not fragment and not suggestion:
                continue
            errors.append({"fragment": fragment, "suggestion": suggestion, "type": kind})
            continue
        match = DEMO_LINE.match(line)
        if match:
            demo = match.group(1).strip()

    if len(errors) > MAX_ERROR_ROWS:
        errors = errors[:MAX_ERROR_ROWS]
        flags.append("schema_violation:errors_truncated")

    if band is None or band not in ESSAY_BANDS:
        return False, {}, flags, "schema_violation"
    if set(dims) != set(ESSAY_DIMENSIONS):
        return False, {}, flags, "schema_violation"
    if any(not 0 <= value <= 5 for value in dims.values()):
        return False, {}, flags, "schema_violation"
    if not ESSAY_BAND_INTERVALS[band][0] <= sum(dims.values()) <= ESSAY_BAND_INTERVALS[band][1]:
        flags.append("schema_violation:band_dimension_mismatch")
        return False, {}, flags, "schema_violation"
    for index, item in enumerate(errors):
        if item["type"] not in ERROR_TYPES_CET:
            flags.append(f"schema_violation:error_{index}_type_unknown")
            return False, {}, flags, "schema_violation"

    data = {
        "band": band,
        "dimension_scores": dims,
        "errors": errors,
        "upgraded_demo": demo,
        "model_answer_outline": None,
    }
    return True, data, flags, None


def parse_l2_rounds(rounds: Sequence[str]) -> Tuple[bool, dict, List[str], Optional[str]]:
    """L2：三轮输出聚合 + 档位重算（06 §3.4）。

    档位与三维和矛盾时，以三维为准反推档位并记 `schema_violation:band_reconciled`。
    """
    if len(rounds) < 3:
        return False, {}, [], "round_budget_exhausted"
    flags: List[str] = []

    band: Optional[int] = None
    match = L2_BAND_LINE.search(rounds[0] or "")
    if match:
        candidate = int(match.group(1))
        if candidate in ESSAY_BANDS:
            band = candidate

    dims: dict[str, int] = {}
    match = L2_DIM_LINE.search(rounds[1] or "")
    if match:
        values = [int(match.group(i)) for i in (1, 2, 3)]
        if all(0 <= value <= 5 for value in values):
            dims = dict(zip(ESSAY_DIMENSIONS, values))

    errors: List[dict] = []
    for raw in (rounds[2] or "").splitlines():
        match = L2_ERROR_LINE.match(raw.strip())
        if not match:
            continue
        fragment, suggestion, kind = (match.group(i).strip() for i in (1, 2, 3))
        errors.append({"fragment": fragment, "suggestion": suggestion, "type": kind})
    if len(errors) > MAX_ERROR_ROWS:
        errors = errors[:MAX_ERROR_ROWS]
        flags.append("schema_violation:errors_truncated")

    if set(dims) != set(ESSAY_DIMENSIONS):
        return False, {}, flags, "schema_violation"

    total = sum(dims.values())
    if band is None or not ESSAY_BAND_INTERVALS[band][0] <= total <= ESSAY_BAND_INTERVALS[band][1]:
        band = band_for_sum(total)
        flags.append("schema_violation:band_reconciled")

    for index, item in enumerate(errors):
        if item["type"] not in ERROR_TYPES_CET:
            flags.append(f"schema_violation:error_{index}_type_unknown")
            return False, {}, flags, "schema_violation"

    data = {
        "band": band,
        "dimension_scores": dims,
        "errors": errors,
        "upgraded_demo": None,
        "model_answer_outline": None,
    }
    return True, data, flags, None


# ---------------------------------------------------------------------------
# 翻译（L1 逐句批改）
# ---------------------------------------------------------------------------

_TRANS_BAND_LINE = re.compile(r"^档位\s*[:：]\s*(\d+)\s*$")
_TRANS_ERROR_LINE = re.compile(r"^错误\s*\d+\s*[:：]\s*(.+?)\s*\|\|\s*(.+?)\s*$")
_TRANS_DEMO_LINE = re.compile(r"^升格示范\s*[:：]\s*(.*)$")


def parse_translation_l1(text: Optional[str]) -> Tuple[bool, dict, List[str], Optional[str]]:
    """翻译 L1：整段定档 + 逐句给问题类型（类型取自 `TRANSLATION_ERROR_TYPES`）。"""
    if not text or not text.strip():
        return False, {}, [], "empty_response"
    flags: List[str] = []
    band: Optional[int] = None
    errors: List[dict] = []
    demo: Optional[str] = None

    for raw in text.splitlines():
        line = raw.strip().strip("*").strip()
        if not line:
            continue
        if _TRANS_BAND_LINE.match(line):
            band = int(_TRANS_BAND_LINE.match(line).group(1))
            continue
        match = _TRANS_ERROR_LINE.match(line)
        if match:
            errors.append({"fragment": match.group(1), "suggestion": "", "type": match.group(2)})
            continue
        if _TRANS_DEMO_LINE.match(line):
            demo = _TRANS_DEMO_LINE.match(line).group(1).strip()

    if len(errors) > MAX_ERROR_ROWS:
        errors = errors[:MAX_ERROR_ROWS]
        flags.append("schema_violation:errors_truncated")

    if band is None or not TRANSLATION_BAND_MIN <= band <= TRANSLATION_BAND_MAX:
        return False, {}, flags, "schema_violation"
    for index, item in enumerate(errors):
        if item["type"] not in TRANSLATION_ERROR_TYPES:
            flags.append(f"schema_violation:error_{index}_type_unknown")
            return False, {}, flags, "schema_violation"

    data = {
        "band": band,
        "dimension_scores": {},
        "errors": errors,
        "upgraded_demo": demo,
        "model_answer_outline": None,
    }
    return True, data, flags, None


# ---------------------------------------------------------------------------
# 主观题评分点（L0 JSON）
# ---------------------------------------------------------------------------


def parse_scoring_points_l0(payload: dict) -> Tuple[bool, dict, List[str], Optional[str]]:
    """主观题（short_answer/material/lesson_plan/practical）L0：校验三态得分点清单。"""
    flags: List[str] = []
    points = payload.get("scoring_points")
    if not isinstance(points, list):
        return False, {}, ["schema_violation:scoring_points_missing"], "schema_violation"
    normalized: List[dict] = []
    for index, item in enumerate(points):
        if not isinstance(item, dict):
            return False, {}, [f"schema_violation:scoring_point_{index}_not_object"], "schema_violation"
        point = item.get("point")
        if not isinstance(point, str) or not point.strip():
            return False, {}, [f"schema_violation:scoring_point_{index}_missing_point"], "schema_violation"
        status = item.get("status")
        if status not in SCORING_POINT_STATUSES:
            return False, {}, [f"schema_violation:scoring_point_{index}_status_unknown"], "schema_violation"
        normalized.append(
            {
                "point": point,
                "status": status,
                "note": item.get("note", ""),
                "point_ref": item.get("point_ref", ""),
            }
        )
    overall = payload.get("overall_score")
    data: dict = {"scoring_points": normalized, "overall_score": overall}
    if payload.get("upgraded_demo") is not None:
        data["upgraded_demo"] = payload["upgraded_demo"]
    if payload.get("model_answer_outline") is not None:
        data["model_answer_outline"] = payload["model_answer_outline"]
    return (not flags), data, flags, None