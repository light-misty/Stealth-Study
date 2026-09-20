"""T01 SPIKE-1：批改 JSON 输出成功率与四级降级验证。

验证对象是 06 文档 §2/§3 的设计假设：L0（强约束 JSON）在真实云端模型上的解析成功率，
以及 L0+L1 合计成功率是否足以支撑 V0.1 从 L0 起步（08 文档 §3.1 的量化门槛）。

本脚本不落库、不接入 campus 包，按 06 §2 的字段白名单校验器判档；
语料由 fetch_corpus.py 产出，模型经由既有 ProviderClient 链路真实调用。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = Path(__file__).resolve().parent
CORPUS_PATH = SPIKE_DIR / "corpus" / "cet_essays.json"
DEFAULT_OUT_DIR = SPIKE_DIR / "results"

SECRET_PROFILE = "provider:xiaomimimo"
STRONG_MODEL = "mimo-v2.5-pro"
CHEAP_MODEL = "mimo-v2.5"
DEFAULT_MODELS = (STRONG_MODEL, CHEAP_MODEL)
CONDITIONS = ("l0_plain", "l0_response_format")

CALL_BUDGET = 5
PROVIDER_TIMEOUT_S = 90
TEMPERATURE = 0
MAX_ERROR_ROWS = 8

CET_ESSAY_RUBRIC = """# 四六级短文写作评分标准（15 分制，官方五档）

评分流程：通读定档（下表）→ 按内容/结构/语言三维各 5 分拆分展示 → 三维之和必须落在该档
分值区间内 → 逐条列错误 → 升格示范一段。

| 档位 | 分值 | 判据（官方表述） |
|---|---|---|
| 一档 | 14 分 | 切题。表达思想清楚，文字通顺、连贯，基本上无语言错误，仅有个别小错。 |
| 二档 | 11 分 | 切题。表达思想清楚，文字连贯，但有少量语言错误。 |
| 三档 | 8 分 | 基本切题。有些地方表达思想不够清楚，文字勉强连贯；语言错误相当多，其中有一些是严重错误。 |
| 四档 | 5 分 | 基本切题。表达思想不清楚，连贯性差。有较多的严重语言错误。 |
| 五档 | 2 分 | 条理不清，思路紊乱，语言支离破碎或大部分句子均有错误，且多数为严重错误。 |
| 零分 | 0 分 | 未作答，或只有几个孤立的词，或文不对题。 |

分项维度（各 0-5 分，用于批改卡展示）：内容（切题度与要点覆盖）、结构（段落组织与衔接手段）、
语言（用词与语法的准确性、句式多样性）。换算：15 分制原始分 × 7.1 = 106.5 分制得分。

错误类型枚举（供错误清单使用，与 rubrics.py 的 ERROR_TYPES 一致）：主谓一致 / 时态语态 / 动词
搭配 / 冠词与单复数 / 中式英语 / 逻辑连接缺失 / 用词不当 / 拼写。

批改纪律：先定档后拆分，禁止"分项之和与档位矛盾"；每条错误给原文片段+修改建议+类型；
升格示范必须基于学生原句改写，不得换题重写。输出标注"AI 生成，仅供参考"。"""

ERROR_TYPES_CET = (
    "主谓一致",
    "时态语态",
    "动词搭配",
    "冠词与单复数",
    "中式英语",
    "逻辑连接缺失",
    "用词不当",
    "拼写",
)

BAND_VALUES = (14, 11, 8, 5, 2, 0)
BAND_INTERVALS = {14: (13, 15), 11: (10, 12), 8: (7, 9), 5: (4, 6), 2: (1, 3), 0: (0, 0)}
DIMENSION_KEYS = ("content", "structure", "language")

RUBRIC_BAND_TABLE = re.compile(r"^\| 档位 \|.*?(?=\n\n)", re.S | re.M)
RUBRIC_DIMENSIONS = re.compile(r"^分项维度.*?(?=\n\n)", re.S | re.M)
RUBRIC_ERROR_TYPES = re.compile(r"^错误类型枚举.*?(?=\n\n)", re.S | re.M)

L0_SCHEMA = (
    '{"band": <0|2|5|8|11|14>, "dimension_scores": {"content": <0-5>, "structure": <0-5>, '
    '"language": <0-5>},\n "errors": [{"fragment": "...", "suggestion": "...", '
    '"type": "<错误类型枚举之一>"}],\n "upgraded_demo": "...", "model_answer_outline": "..."}'
)

L1_TEMPLATE_ROWS = ["档位：<14|11|8|5|2|0>", "内容分：<0-5>", "结构分：<0-5>", "语言分：<0-5>"]
L1_TEMPLATE_ROWS += [
    f"错误{i}：<原文片段> || <修改建议> || <类型>" for i in range(1, MAX_ERROR_ROWS + 1)
]
L1_TEMPLATE_ROWS.append("升格示范：<一段改写>")
L1_TEMPLATE = "\n".join(L1_TEMPLATE_ROWS)

BAND_LINE = re.compile(r"^档位\s*[:：]\s*(\d+)\s*$")
DIM_LINE = re.compile(r"^(内容|结构|语言)分\s*[:：]\s*(\d+)\s*$")
ERROR_LINE = re.compile(r"^错误\s*\d+\s*[:：]\s*(.*)$")
DEMO_LINE = re.compile(r"^升格示范\s*[:：]\s*(.*)$")
L2_BAND_LINE = re.compile(r"结论\s*[:：]\s*(\d+)")
L2_DIM_LINE = re.compile(r"结论\s*[:：]\s*(\d+)\s*[,，、]\s*(\d+)\s*[,，、]\s*(\d+)")
L2_ERROR_LINE = re.compile(r"^\s*(.+?)\s*\|\|\s*(.+?)\s*\|\|\s*(.+?)\s*$")


def rubric_section(pattern: re.Pattern[str]) -> str:
    match = pattern.search(CET_ESSAY_RUBRIC)
    return match.group(0).strip() if match else ""


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


def _balanced_object(text: str, start: int) -> str | None:
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


def extract_json(text: str | None) -> tuple[dict | None, str | None]:
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
    for band in BAND_VALUES:
        low, high = BAND_INTERVALS[band]
        if low <= total <= high:
            return band
    return 0


def validate_essay_payload(data: dict) -> tuple[bool, list[str]]:
    flags: list[str] = []
    band = data.get("band")
    if not isinstance(band, int) or isinstance(band, bool) or band not in BAND_VALUES:
        return False, ["schema_violation:band_out_of_whitelist"]

    dims = data.get("dimension_scores")
    if not isinstance(dims, dict):
        return False, ["schema_violation:dimension_scores_missing"]
    values: dict[str, int] = {}
    for key in DIMENSION_KEYS:
        value = dims.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5:
            return False, [f"schema_violation:dimension_{key}_invalid"]
        values[key] = value

    if not BAND_INTERVALS[band][0] <= sum(values.values()) <= BAND_INTERVALS[band][1]:
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


def parse_l0(text: str | None) -> tuple[bool, dict, list[str], str | None]:
    data, reason = extract_json(text)
    if data is None:
        return False, {}, [], reason or "json_invalid"
    ok, flags = validate_essay_payload(data)
    if not ok:
        return False, {}, flags, "schema_violation"
    return True, data, flags, None


def parse_l1(text: str | None) -> tuple[bool, dict, list[str], str | None]:
    if not text or not text.strip():
        return False, {}, [], "empty_response"
    flags: list[str] = []
    band: int | None = None
    dims: dict[str, int] = {}
    errors: list[dict] = []
    demo: str | None = None
    label_map = {"内容": "content", "结构": "structure", "语言": "language"}

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
            dims[label_map[match.group(1)]] = int(match.group(2))
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

    if band is None or band not in BAND_VALUES:
        return False, {}, flags, "schema_violation"
    if set(dims) != set(DIMENSION_KEYS):
        return False, {}, flags, "schema_violation"
    if any(not 0 <= value <= 5 for value in dims.values()):
        return False, {}, flags, "schema_violation"

    if not BAND_INTERVALS[band][0] <= sum(dims.values()) <= BAND_INTERVALS[band][1]:
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


def parse_l2_rounds(rounds: list[str]) -> tuple[bool, dict, list[str], str | None]:
    if len(rounds) < 3:
        return False, {}, [], "round_budget_exhausted"
    flags: list[str] = []

    band: int | None = None
    match = L2_BAND_LINE.search(rounds[0] or "")
    if match:
        candidate = int(match.group(1))
        if candidate in BAND_VALUES:
            band = candidate

    dims: dict[str, int] = {}
    match = L2_DIM_LINE.search(rounds[1] or "")
    if match:
        values = [int(match.group(i)) for i in (1, 2, 3)]
        if all(0 <= value <= 5 for value in values):
            dims = dict(zip(DIMENSION_KEYS, values))

    errors: list[dict] = []
    for raw in (rounds[2] or "").splitlines():
        match = L2_ERROR_LINE.match(raw.strip())
        if not match:
            continue
        fragment, suggestion, kind = (match.group(i).strip() for i in (1, 2, 3))
        errors.append({"fragment": fragment, "suggestion": suggestion, "type": kind})
    if len(errors) > MAX_ERROR_ROWS:
        errors = errors[:MAX_ERROR_ROWS]
        flags.append("schema_violation:errors_truncated")

    if set(dims) != set(DIMENSION_KEYS):
        return False, {}, flags, "schema_violation"

    total = sum(dims.values())
    if band is None or not BAND_INTERVALS[band][0] <= total <= BAND_INTERVALS[band][1]:
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


@dataclass
class GradeRequest:
    essay_id: str
    question: str
    answer: str


@dataclass
class GradeAttempt:
    level: int
    reason: str | None
    calls: int
    schema_flags: list[str] = field(default_factory=list)


@dataclass
class GradeOutcome:
    ok: bool
    degrade_level: int
    band: int | None
    errors_count: int
    schema_flags: list[str]
    trace: list[dict]
    calls: int
    transport_retries: int
    raw_by_level: dict
    fail_reason: str | None


def build_l0_messages(req: GradeRequest) -> list[dict]:
    system = (
        f"{CET_ESSAY_RUBRIC}\n\n"
        f"你只能输出一个 JSON 对象，schema：\n{L0_SCHEMA}\n\n"
        "只输出一个 JSON 对象，不要任何其他文字。"
    )
    user = f"题目：{req.question}\n学生作文：{req.answer}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_l1_messages(req: GradeRequest) -> list[dict]:
    system = (
        f"{CET_ESSAY_RUBRIC}\n\n"
        "按下面的行式模板逐行填空，不要增删行，不要输出任何其他文字：\n"
        f"{L1_TEMPLATE}"
    )
    user = f"题目：{req.question}\n学生作文：{req.answer}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_l2_messages(round_no: int, req: GradeRequest) -> list[dict]:
    table = rubric_section(RUBRIC_BAND_TABLE)
    dims = rubric_section(RUBRIC_DIMENSIONS)
    errors = rubric_section(RUBRIC_ERROR_TYPES)
    if round_no == 0:
        section = table
        instruction = (
            "只做一件事：给这篇作文定档。\n"
            "输出两行：第一行 `结论：<档位分值>`（取 0/2/5/8/11/14），第二行 `依据：<一句话>`。"
        )
    elif round_no == 1:
        section = dims
        instruction = (
            "只做一件事：按内容/结构/语言三维给分，各 0-5 分。\n"
            "输出两行：第一行 `结论：<内容分>,<结构分>,<语言分>`，第二行 `依据：<一句话>`。"
        )
    else:
        section = errors
        instruction = (
            "只做一件事：列出这篇作文的语言错误，每行一条，格式为 `原片段 || 修改建议 || 类型`，"
            f"最多 {MAX_ERROR_ROWS} 行，类型只能取上述枚举值。输出两行：第一行 `结论：见下列清单`，"
            "后续每行一条错误。"
        )
    system = f"{section}\n\n{instruction}\n只输出要求的内容，不要任何其他文字。"
    user = f"题目：{req.question}\n学生作文：{req.answer}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class ModelCaller:
    def __init__(self, provider: Any, model: str):
        self.provider = provider
        self.model = model

    def __call__(self, messages: list[dict], response_format: bool = False) -> tuple[str, int]:
        settings: dict[str, Any] = {"temperature": TEMPERATURE, "timeout": PROVIDER_TIMEOUT_S}
        if response_format:
            settings["response_format"] = {"type": "json_object"}
        try:
            turn = self.provider.complete(model=self.model, messages=messages, **settings)
            return (turn.text or ""), 0
        except Exception as exc:
            if not response_format:
                raise
            try:
                turn = self.provider.complete(
                    model=self.model,
                    messages=messages,
                    temperature=TEMPERATURE,
                    timeout=PROVIDER_TIMEOUT_S,
                )
                return (turn.text or ""), 1
            except Exception:
                raise exc


def grade_one(caller: ModelCaller, req: GradeRequest, condition: str) -> GradeOutcome:
    trace: list[dict] = []
    raw: dict[str, str] = {}
    flags: list[str] = []
    state = {"calls": 0, "retries": 0, "timeout_seen": False}

    def attempt(level_label: str, messages: list[dict], with_rf: bool) -> str | None:
        state["calls"] += 1
        try:
            text, used = caller(messages, response_format=with_rf)
            state["retries"] += used
            return text
        except Exception as exc:
            name = type(exc).__name__
            if "timeout" in name.lower() or "timeout" in str(exc).lower():
                state["timeout_seen"] = True
            trace.append(
                {
                    "level": level_label,
                    "ok": False,
                    "reason": f"provider_error:{name}",
                    "schema_flags": [],
                }
            )
            return None

    text = attempt(0, build_l0_messages(req), condition == "l0_response_format")
    if text is not None:
        raw["l0"] = text
        ok, data, schema_flags, reason = parse_l0(text)
        trace.append(
            {"level": 0, "condition": condition, "ok": ok, "reason": reason, "schema_flags": schema_flags}
        )
        flags.extend(schema_flags)
        if ok:
            return GradeOutcome(
                True, 0, data["band"], len(data["errors"]), flags, trace,
                state["calls"], state["retries"], raw, None,
            )

    text = attempt(1, build_l1_messages(req), False)
    if text is not None:
        raw["l1"] = text
        ok, data, schema_flags, reason = parse_l1(text)
        trace.append({"level": 1, "ok": ok, "reason": reason, "schema_flags": schema_flags})
        flags.extend(schema_flags)
        if ok:
            return GradeOutcome(
                True, 1, data["band"], len(data["errors"]), flags, trace,
                state["calls"], state["retries"], raw, None,
            )

    rounds: list[str] = []
    for round_no in range(3):
        round_text = attempt(2, build_l2_messages(round_no, req), False)
        if round_text is None:
            break
        rounds.append(round_text)
        raw[f"l2_r{round_no}"] = round_text
    ok, data, schema_flags, reason = parse_l2_rounds(rounds)
    trace.append(
        {
            "level": 2,
            "rounds_completed": len(rounds),
            "ok": ok,
            "reason": reason,
            "schema_flags": schema_flags,
        }
    )
    flags.extend(schema_flags)
    if ok:
        return GradeOutcome(
            True, 2, data["band"], len(data["errors"]), flags, trace,
            state["calls"], state["retries"], raw, None,
        )

    fallback = raw.get("l2_r2") or raw.get("l1") or raw.get("l0") or None
    if fallback and fallback.strip():
        return GradeOutcome(
            True, 3, None, 0, flags, trace, state["calls"], state["retries"], raw, None
        )
    fail_reason = "MODEL_TIMEOUT" if state["timeout_seen"] else "MODEL_EMPTY"
    return GradeOutcome(
        False, 3, None, 0, flags, trace, state["calls"], state["retries"], raw, fail_reason
    )


def load_corpus(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["essays"]


def resolve_provider() -> tuple[Any, str]:
    sys.path.insert(0, str(ROOT))
    from stealth_study.providers.openai_provider import OpenAIProvider
    from stealth_study.secrets import SecretStore

    profile = SecretStore().get(SECRET_PROFILE)
    if not profile or not profile.get("api_key"):
        raise SystemExit(f"缺少密钥配置：SecretStore 未找到 {SECRET_PROFILE}")
    provider = OpenAIProvider(api_key=profile["api_key"], base_url=profile.get("base_url"))
    return provider, profile.get("base_url", "")


def matrix_cells(models: Iterable[str], conditions: Iterable[str], essays: list[dict]) -> list[tuple]:
    cells = []
    for essay in essays:
        for model in models:
            for condition in conditions:
                cells.append((essay, model, condition))
    return cells


def run_matrix(args: argparse.Namespace) -> int:
    provider, base_url = resolve_provider()
    essays = load_corpus(Path(args.corpus))
    if args.limit:
        essays = essays[: args.limit]
    models = args.models.split(",") if args.models else list(DEFAULT_MODELS)
    conditions = args.conditions.split(",") if args.conditions else list(CONDITIONS)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "matrix.jsonl"
    done: set[tuple] = set()
    if args.resume and raw_path.is_file():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                done.add((record["essay_id"], record["model"], record["condition"]))
        print(f"resume: {len(done)} 格已完成")

    cells = [
        cell
        for cell in matrix_cells(models, conditions, essays)
        if (cell[0]["essay_id"], cell[1], cell[2]) not in done
    ]
    print(f"models={models} conditions={conditions} essays={len(essays)} cells={len(cells)}")
    if not cells:
        return 0

    lock = threading.Lock()
    counters = {"ok": 0, "fail": 0, "l0": 0}

    def work(cell: tuple) -> dict:
        essay, model, condition = cell
        caller = ModelCaller(provider, model)
        req = GradeRequest(essay_id=essay["essay_id"], question=essay["prompt"], answer=essay["essay"])
        started = time.time()
        outcome = grade_one(caller, req, condition)
        record = {
            "essay_id": essay["essay_id"],
            "track": essay["track"],
            "role_group": essay["role_group"],
            "model": model,
            "condition": condition,
            "ok": outcome.ok,
            "degrade_level": outcome.degrade_level,
            "band": outcome.band,
            "errors_count": outcome.errors_count,
            "schema_flags": outcome.schema_flags,
            "degrade_trace": outcome.trace,
            "calls": outcome.calls,
            "transport_retries": outcome.transport_retries,
            "fail_reason": outcome.fail_reason,
            "elapsed_s": round(time.time() - started, 2),
            "raw": {key: value[:4000] for key, value in outcome.raw_by_level.items()},
        }
        with lock:
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            counters["ok" if outcome.ok else "fail"] += 1
            counters["l0"] += int(outcome.degrade_level == 0)
            total = counters["ok"] + counters["fail"]
            print(
                f"[{total}/{len(cells)}] {record['essay_id']} {model} {condition} "
                f"-> level={record['degrade_level']} band={record['band']} calls={record['calls']} "
                f"flags={record['schema_flags']}"
            )
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(work, cells))

    print(f"done ok={counters['ok']} fail={counters['fail']} l0={counters['l0']} base_url={base_url}")
    return 0


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def summarize(records: list[dict], models: list[str], conditions: list[str]) -> dict:
    grid: dict[str, dict] = {}
    for model in models:
        for condition in conditions:
            subset = [r for r in records if r["model"] == model and r["condition"] == condition]
            dist = {str(level): 0 for level in (0, 1, 2, 3)}
            for record in subset:
                dist[str(record["degrade_level"])] += 1
            total = len(subset)
            l0 = dist["0"]
            l01 = l0 + dist["1"]
            accepted = sum(
                1
                for record in subset
                if record["condition"] == "l0_response_format" and record["transport_retries"] == 0
            )
            rejected = sum(record["transport_retries"] for record in subset)
            flag_counter: dict[str, int] = {}
            for record in subset:
                for flag in record["schema_flags"]:
                    flag_counter[flag] = flag_counter.get(flag, 0) + 1
            calls = [record["calls"] for record in subset]
            bands = [record["band"] for record in subset if record["band"] is not None]
            grid[f"{model}|{condition}"] = {
                "model": model,
                "condition": condition,
                "samples": total,
                "degrade_distribution": dist,
                "l0_success_rate": round(l0 / total, 4) if total else None,
                "l0_l1_success_rate": round(l01 / total, 4) if total else None,
                "l3_count": dist["3"],
                "fail_count": sum(1 for record in subset if not record["ok"]),
                "schema_flags": flag_counter,
                "calls_total": sum(calls),
                "calls_max": max(calls) if calls else 0,
                "calls_budget_ok": all(call <= CALL_BUDGET for call in calls),
                "band_histogram": {str(band): bands.count(band) for band in sorted(set(bands), reverse=True)},
                "response_format_rejected": rejected,
                "response_format_accepted": accepted if condition == "l0_response_format" else None,
            }

    pooled: dict[str, dict] = {}
    for model in models:
        subset = [r for r in records if r["model"] == model]
        total = len(subset)
        dist = {str(level): sum(1 for r in subset if r["degrade_level"] == level) for level in (0, 1, 2, 3)}
        pooled[model] = {
            "samples": total,
            "degrade_distribution": dist,
            "l0_success_rate": round(dist["0"] / total, 4) if total else None,
            "l0_l1_success_rate": round((dist["0"] + dist["1"]) / total, 4) if total else None,
        }

    return {"grid": grid, "pooled_by_model": pooled, "total_cells": len(records)}


def report(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    records = load_records(out_dir / "matrix.jsonl")
    models = args.models.split(",") if args.models else list(DEFAULT_MODELS)
    summary = summarize(records, models, list(CONDITIONS))
    (out_dir / "matrix_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for key, cell in summary["grid"].items():
        print(
            f"{key}: n={cell['samples']} dist={cell['degrade_distribution']} "
            f"L0={cell['l0_success_rate']} L0+L1={cell['l0_l1_success_rate']} "
            f"calls_max={cell['calls_max']} budget_ok={cell['calls_budget_ok']}"
        )
    for model, cell in summary["pooled_by_model"].items():
        print(f"pooled {model}: n={cell['samples']} L0={cell['l0_success_rate']} L0+L1={cell['l0_l1_success_rate']}")
    return 0


def consistency(args: argparse.Namespace) -> int:
    provider, _ = resolve_provider()
    essays = load_corpus(Path(args.corpus))
    model = args.model or STRONG_MODEL
    paired = [essay for essay in essays if essay["role_group"] == "paired"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "consistency.jsonl"

    def work(essay: dict) -> dict:
        caller = ModelCaller(provider, model)
        req = GradeRequest(essay_id=essay["essay_id"], question=essay["prompt"], answer=essay["essay"])
        first = grade_one(caller, req, "l0_plain")
        second = grade_one(caller, req, "l0_plain")
        record = {
            "essay_id": essay["essay_id"],
            "model": model,
            "bands": [first.band, second.band],
            "degrade_levels": [first.degrade_level, second.degrade_level],
            "ok": [first.ok, second.ok],
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"consistency {record['essay_id']}: bands={record['bands']} levels={record['degrade_levels']}")
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(work, paired))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="T01 SPIKE-1 批改 JSON 成功率验证")
    parser.add_argument("command", choices=["run", "report", "consistency"])
    parser.add_argument("--corpus", default=str(CORPUS_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--models", default="")
    parser.add_argument("--conditions", default="")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--model", default="", help="consistency 子命令使用的模型")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return run_matrix(args)
    if args.command == "report":
        return report(args)
    return consistency(args)


if __name__ == "__main__":
    sys.exit(main())
