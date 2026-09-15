"""campus orchestration layer — the business rules behind the campus endpoints.

`routes.py` owns HTTP (status codes, request shapes, the structured error body); this module
owns the decisions. It therefore never imports FastAPI: a failure leaves here as `CampusError`
carrying one of the codes of 03 §6, and the router is the only place that turns a code into a
response (T06 §7-2).

Three rules from 01 §2.1/§3 are structural here:

* Every profile-scoped read and write passes `profile_id` to the store, which is the
  data-layer half of the multi-profile isolation promise ("service 层所有查询强制
  `WHERE profile_id=?`"; the router half is `ProfileGuard`, T06).
* No method branches on a track id. Station differences are read from `tracks.py`
  (`TrackSpec`), never from a literal comparison (01 §3.2 forbids `if track == "cet"`).
* A `finished` profile refuses every write (02 §7.2). The router decorates every mutating
  endpoint with the guard's `get_writable_profile` (T06 §7-1), so this layer is only ever
  reached for a writable profile and never re-implements that rule.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..secrets import state_dir
from . import models, rubrics, tracks
from .config import DEFAULT_DAILY_MINUTES
from .grading import (
    PROVIDER_TIMEOUT_S,
    SCORING_KINDS,
    TEMPERATURE,
    TRANSLATION_KINDS,
    GradeRequest,
    GradeResult,
    GradingEngine,
    extract_json,
)
from .store import CampusStore

ACTIVE_PROFILE_KEY = "active_profile_id"
SETTINGS_KEY = "campus_settings"

CASCADE_TABLES: tuple[str, ...] = (
    "review_queue",
    "mistake_book",
    "attempt",
    "question_bank_item",
    "vocab_item",
    "mock_exam",
    "assessment",
    "weekly_report",
    "cert_deadline",
    "mastery",
    "plan_task",
    "study_plan",
    "doc_chunk",
    "source_doc",
    "school_profile",
    "knowledge_point",
)

PROFILE_MUTABLE_FIELDS: tuple[str, ...] = (
    "title",
    "cert_type",
    "level",
    "exam_date",
    "target_score",
    "current_estimate",
    "subjects",
    "daily_minutes",
    "status",
)

JSON_PROFILE_FIELDS: frozenset[str] = frozenset({"subjects"})

QUESTION_FIELDS: tuple[str, ...] = (
    "subject",
    "stem",
    "qtype",
    "point_id",
    "options",
    "answer",
    "answer_meta",
    "max_score",
    "difficulty",
    "source",
    "doc_id",
)

JSON_QUESTION_FIELDS: frozenset[str] = frozenset({"options", "answer_meta"})

QUESTION_REQUIRED_FIELDS: tuple[str, ...] = ("stem", "subject")

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5

_QUESTION_LABELS: Mapping[str, str] = {
    "题干": "stem",
    "stem": "stem",
    "科目": "subject",
    "subject": "subject",
    "题型": "qtype",
    "类型": "qtype",
    "qtype": "qtype",
    "选项": "options",
    "options": "options",
    "答案": "answer",
    "answer": "answer",
    "分值": "max_score",
    "满分": "max_score",
    "max_score": "max_score",
    "难度": "difficulty",
    "difficulty": "difficulty",
}

_LABEL_LINE = re.compile(r"^\s*([^\s：:]{1,12})\s*[：:]\s*(.*)$")
_OPTION_PART = re.compile(r"^\s*([A-Za-z]{1,3})\s*[.、)．]\s*(\S.*)$")
_OPTION_SEPARATOR = re.compile(r"[|｜]")

OBJECTIVE_QUESTION_TYPES: frozenset[str] = frozenset(
    {
        models.QuestionType.SINGLE.value,
        models.QuestionType.MULTIPLE.value,
        models.QuestionType.JUDGE.value,
        models.QuestionType.BLANK.value,
    }
)

GRADING_KIND_BY_QTYPE: Mapping[str, str] = {
    models.QuestionType.ESSAY.value: "essay",
    models.QuestionType.MATERIAL.value: "essay_material",
    models.QuestionType.SHORT_ANSWER.value: "short_answer",
    models.QuestionType.LESSON_PLAN.value: "lesson_plan",
    models.QuestionType.PRACTICAL.value: "practical",
}

BAND_MAX_SCORE = 15

_JUDGE_TRUE: frozenset[str] = frozenset({"t", "true", "y", "yes", "对", "正确", "√"})
_JUDGE_FALSE: frozenset[str] = frozenset({"f", "false", "n", "no", "错", "错误", "×", "x"})

_BLANK_SEPARATOR = re.compile(r"[|｜]")

RUBRIC_TEXTS: Mapping[str, str] = {
    "cet-essay": rubrics.CET_ESSAY_RUBRIC,
    "cet-translation": rubrics.CET_TRANSLATION_RUBRIC,
    "cert-scoring-points": rubrics.CERT_SCORING_POINTS_SPEC,
}

RUBRIC_BY_KIND: Mapping[str, str] = {
    models.QuestionType.ESSAY.value: "cet-essay",
    "translation": "cet-translation",
    models.QuestionType.SHORT_ANSWER.value: "cert-scoring-points",
    models.QuestionType.MATERIAL.value: "cert-scoring-points",
    models.QuestionType.LESSON_PLAN.value: "cert-scoring-points",
    models.QuestionType.PRACTICAL.value: "cert-scoring-points",
}

CUSTOM_RUBRIC_ID = "custom"

SUBJECT_BY_KIND: Mapping[str, str] = {
    models.QuestionType.ESSAY.value: models.Subject.WRITING.value,
    models.QuestionType.MATERIAL.value: models.Subject.WRITING.value,
    models.QuestionType.LESSON_PLAN.value: models.Subject.WRITING.value,
    "translation": models.Subject.TRANSLATION.value,
    models.QuestionType.SHORT_ANSWER.value: models.Subject.MAJOR.value,
    models.QuestionType.PRACTICAL.value: models.Subject.MAJOR.value,
}

DIMENSION_LABELS: Mapping[str, str] = {
    "content": "内容",
    "structure": "结构",
    "language": "语言",
}

ESSAY_DIMENSION_MAX = 5
TRANSLATION_DIMENSION_NAME = "档位"
SCORING_POINT_SCORES: Mapping[str, float] = {"hit": 1.0, "partial": 0.5, "miss": 0.0}
SCORING_POINT_MAX = 1

TOP_ERROR_TYPES = 3
MAX_ERROR_SAMPLES = 3

ASSESSMENT_SECTIONS: tuple[tuple[str, int], ...] = (
    ("vocab", 6),
    ("listening", 4),
    ("reading", 5),
    ("writing_translation", 5),
)

ASSESSMENT_PROMPT_SECTIONS: tuple[tuple[str, int, str], ...] = (
    ("vocab", 6, "词汇辨析"),
    ("listening", 4, "听力理解"),
    ("reading", 5, "阅读理解"),
    ("writing", 3, "写作知识"),
    ("translation", 2, "翻译知识"),
)

SECTION_OF_SUBJECT: Mapping[str, str] = {
    models.Subject.VOCAB.value: "vocab",
    models.Subject.LISTENING.value: "listening",
    models.Subject.READING.value: "reading",
    models.Subject.WRITING.value: "writing_translation",
    models.Subject.TRANSLATION.value: "writing_translation",
}

SECTION_WEIGHTS: Mapping[str, float] = {
    "listening": 248.5,
    "reading": 248.5,
    "writing_translation": 213.0,
}

FULL_SCORE = 710.0
DEFAULT_TARGET_SCORE = 425
ASSESSMENT_ITEM_SCORE = 1
MASTERY_MASTERED_RATIO = 0.75
MASTERY_FUZZY_RATIO = 0.4

PLAN_DATE_FORMAT = "%Y-%m-%d"
PLAN_FALLBACK_MINUTES = 30
PLAN_FALLBACK_TITLE = "{subject} 巩固练习"
PLAN_FALLBACK_DETAIL = "按科目骨架轮转补齐的当日最低任务（模型未给出这一天）"


class CampusError(Exception):
    """A business failure carrying one documented code, its message and any extra detail.

    The code is validated by the router when it is translated (`ERROR_SPECS[code]` raises
    `KeyError` for a code that is not in 03 §6), so this layer cannot invent a status.
    """

    def __init__(self, code: str, message: Optional[str] = None, **extra: Any) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.extra = extra


def _decode(value: Any, default: Any) -> Any:
    """Read a JSON column, returning `default` for NULL, empty and unparsable values."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _encode(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def profile_payload(profile: models.ExamProfile) -> dict[str, Any]:
    """The documented resource body: every stored column, JSON columns decoded (03 §1)."""
    payload = asdict(profile)
    for name in JSON_PROFILE_FIELDS:
        payload[name] = _decode(payload.get(name), [])
    return payload


def question_payload(question: models.QuestionBankItem) -> dict[str, Any]:
    """One question with its JSON columns decoded (`options`, `answer_meta`)."""
    payload = asdict(question)
    for name in JSON_QUESTION_FIELDS:
        payload[name] = _decode(payload.get(name), None)
    return payload


def attempt_payload(attempt: models.Attempt) -> dict[str, Any]:
    """One attempt with its `grading_json` decoded (03 §4.3 shape lives in that column)."""
    payload = asdict(attempt)
    payload["grading_json"] = _decode(payload.get("grading_json"), None)
    return payload


def task_payload(task: models.PlanTask) -> dict[str, Any]:
    """One plan task; every column is scalar, so the body is the row itself (02 §4.10)."""
    return asdict(task)


def parse_questions(fmt: str, content: str) -> list[dict[str, Any]]:
    """Parse an E1 payload into validated question dictionaries (03 §4.5 E1).

    Two shapes are accepted, both addressed by the same label vocabulary so the UI can offer one
    template per format:

    * `md` — one block of `标签：值` lines per question (full-width or ASCII colon), blocks
      separated by a blank line or a `#` heading, values single-line. The required labels are
      `题干` and `科目`; `类型` defaults to `single` and `分值` to 1. `选项` is `A.内容` items
      joined by `|`.
    * `csv` — a header row using those same labels, then one question per row.

    English aliases (`stem`, `subject`, `qtype`, `options`, `answer`, `max_score`, `difficulty`)
    are accepted alongside the Chinese ones. Nothing is dropped silently: an unparsable line, an
    unknown label, a missing required value or an out-of-range value raises `PARSE_ERROR` with
    the physical line number, and the whole payload is validated before anything is stored.
    """
    if not isinstance(content, str) or not content.strip():
        raise CampusError("PARSE_ERROR", "导入内容为空", line=1)
    if fmt == "md":
        questions = _parse_markdown_questions(content)
    elif fmt == "csv":
        questions = _parse_csv_questions(content)
    else:
        raise CampusError("PARSE_ERROR", f"不支持的内容格式：{fmt}", line=1)
    if not questions:
        raise CampusError("PARSE_ERROR", "未解析到任何题目", line=1)
    return questions


def _parse_markdown_questions(content: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    fields: dict[str, Any] = {}
    block_line = 1
    for number, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            if fields:
                questions.append(_normalize_question(fields, block_line))
                fields = {}
            continue
        match = _LABEL_LINE.match(line)
        label = _QUESTION_LABELS.get(match.group(1)) if match else None
        if label is None:
            raise CampusError("PARSE_ERROR", f"第 {number} 行不是「标签：值」形式", line=number)
        if label in fields:
            raise CampusError("PARSE_ERROR", f"第 {number} 行字段重复：{match.group(1)}", line=number)
        if not fields:
            block_line = number
        fields[label] = match.group(2).strip()
    if fields:
        questions.append(_normalize_question(fields, block_line))
    return questions


def _parse_csv_questions(content: str) -> list[dict[str, Any]]:
    reader = csv.reader(io.StringIO(content))
    header = next(reader, None)
    if not header:
        raise CampusError("PARSE_ERROR", "导入内容为空", line=1)
    columns = [_QUESTION_LABELS.get(cell.strip()) for cell in header]
    if any(column is None for column in columns):
        raise CampusError("PARSE_ERROR", "第 1 行表头含未知字段", line=1)
    if len(set(columns)) != len(columns):
        raise CampusError("PARSE_ERROR", "第 1 行表头字段重复", line=1)
    for required in QUESTION_REQUIRED_FIELDS:
        if required not in columns:
            raise CampusError("PARSE_ERROR", f"第 1 行表头缺少必填字段：{required}", line=1)
    questions: list[dict[str, Any]] = []
    for row in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(header):
            raise CampusError("PARSE_ERROR", f"第 {line} 行列数与表头不一致", line=line)
        fields = {str(column): cell.strip() for column, cell in zip(columns, row)}
        questions.append(_normalize_question(fields, line))
    return questions


def _normalize_question(fields: Mapping[str, Any], line: int) -> dict[str, Any]:
    question: dict[str, Any] = {}
    for name in QUESTION_REQUIRED_FIELDS:
        value = str(fields.get(name) or "").strip()
        if not value:
            raise CampusError("PARSE_ERROR", f"第 {line} 行缺少必填字段：{name}", line=line)
        question[name] = value
    question["qtype"] = _question_type(fields.get("qtype"), line)
    question["options"] = _parse_options(fields.get("options"), line)
    question["answer"] = str(fields.get("answer") or "").strip() or None
    if fields.get("max_score") not in (None, ""):
        question["max_score"] = _question_score(fields["max_score"], line)
    if fields.get("difficulty") not in (None, ""):
        question["difficulty"] = _question_difficulty(fields["difficulty"], line)
    return question


def _question_type(value: Any, line: int) -> str:
    raw = str(value or models.QuestionType.SINGLE.value).strip()
    try:
        return models.QuestionType.from_value(raw).value
    except ValueError:
        raise CampusError("PARSE_ERROR", f"第 {line} 行题型非法：{raw}", line=line) from None


def _question_score(value: Any, line: int) -> float:
    try:
        score = float(str(value).strip())
    except ValueError:
        raise CampusError("PARSE_ERROR", f"第 {line} 行分值不是数字：{value}", line=line) from None
    if score <= 0:
        raise CampusError("PARSE_ERROR", f"第 {line} 行分值必须为正数：{value}", line=line)
    return score


def _question_difficulty(value: Any, line: int) -> int:
    raw = str(value).strip()
    if not raw.isdigit() or not MIN_DIFFICULTY <= int(raw) <= MAX_DIFFICULTY:
        raise CampusError(
            "PARSE_ERROR",
            f"第 {line} 行难度需为 {MIN_DIFFICULTY}-{MAX_DIFFICULTY} 的整数：{value}",
            line=line,
        )
    return int(raw)


def _parse_options(value: Any, line: int) -> Optional[list[dict[str, str]]]:
    text = str(value or "").strip()
    if not text:
        return None
    options: list[dict[str, str]] = []
    for part in _OPTION_SEPARATOR.split(text):
        match = _OPTION_PART.match(part)
        if match is None:
            raise CampusError(
                "PARSE_ERROR",
                f"第 {line} 行选项应为「A.内容」并以 | 分隔：{part.strip()}",
                line=line,
            )
        options.append({"key": match.group(1).upper(), "text": match.group(2).strip()})
    return options


@dataclass(frozen=True)
class ModelInventory:
    """Which models this machine can actually call — the input to every AI decision.

    ADR-06 rules out a runtime capability probe (`providers/base.py` carries no structured
    output flag), so "supported" means "a usable model is reachable for this task", not "this
    model handles JSON well". The static recommendation list in `models.TASK_MODEL_CHOICES`
    stays the single source of per-task advice.
    """

    current: str = ""
    ready: bool = False
    selectable: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ()

    def usable(self, model: Optional[str]) -> bool:
        """Whether `model` can be called: declared selectable, or the active ready default."""
        if not model:
            return False
        if model in self.selectable:
            return True
        return bool(self.ready and model == self.current)

    @classmethod
    def from_manager(cls, manager: Any) -> "ModelInventory":
        """Read the sidecar's model state, degrading to "nothing configured".

        Only public surface is touched (`SessionManager.model` and `get_settings()`), and a
        manager that cannot answer — a stub in a unit test, or a sidecar still starting up —
        yields an empty inventory instead of raising. Denying AI calls is the safe default:
        G-04 requires an unconfigured model to be refused with a clear notice rather than
        attempted.
        """
        current = str(getattr(manager, "model", "") or "")
        settings: Mapping[str, Any] = {}
        getter = getattr(manager, "get_settings", None)
        if callable(getter):
            try:
                settings = getter() or {}
            except Exception:
                settings = {}
        if not isinstance(settings, Mapping):
            settings = {}
        selectable = tuple(str(m) for m in (settings.get("models") or ()) if m)
        endpoints = tuple(sorted({_provider_of(model) for model in selectable}))
        return cls(
            current=str(settings.get("model") or current),
            ready=bool(settings.get("model_ready")),
            selectable=selectable,
            endpoints=endpoints,
        )


def _provider_of(model: str) -> str:
    """The provider a model id routes to, following `SessionManager._model_provider`."""
    prefix, _, _rest = model.partition(":")
    return prefix if _rest else "openai"


def _remove_tree(root: Path, target: Path) -> int:
    """Remove the `target` tree when it really sits below `root`, returning the bytes freed.

    The containment check is what keeps a wipe inside campus's own state directory: a target
    equal to the root, or one outside it, is left alone instead of being deleted.
    """
    if target == root or root not in target.parents or not target.is_dir():
        return 0
    freed = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
    shutil.rmtree(target, ignore_errors=True)
    return freed


def _letters(value: Any) -> str:
    """The sorted uppercase letters of a multi-choice answer, so "CA" equals "AC"."""
    return "".join(sorted(char for char in str(value).upper() if char.isalpha()))


def _judge_value(value: Any) -> str:
    """Normalise a true/false answer onto `T`/`F`, leaving anything else as written."""
    text = str(value).strip().casefold()
    if text in _JUDGE_TRUE:
        return "T"
    if text in _JUDGE_FALSE:
        return "F"
    return text


def _blanks(value: Any) -> tuple[str, ...]:
    """Split a fill-in-the-blank key on `|`, trimming and case-folding each slot."""
    return tuple(part.strip().casefold() for part in _BLANK_SEPARATOR.split(str(value).strip()))


def build_plan_messages(
    profile: models.ExamProfile,
    *,
    start: date,
    exam_date: date,
    skeleton: tuple[str, ...],
) -> list[dict[str, str]]:
    """The 备考计划 生成 prompt (03 §4.6 F5, PRD CET1 ③).

    The prompt hands the model the exact window, the subject vocabulary and the spending order,
    because the server validates all three afterwards: a task dated outside the window or named
    with an undeclared subject is refused, and any day the model skips is filled locally.
    """
    order = "、".join(skeleton) if skeleton else "（无固定科目）"
    system = (
        "你在为学生生成一份按天执行的备考计划。只输出一个 JSON 对象，不要任何其他文字。\n"
        f"计划窗口：{start.isoformat()} 到 {exam_date.isoformat()}，每天至少 1 条任务。\n"
        f"科目只能取：{order}；优先把分值性价比高的科目排在前面。\n"
        f"每日任务总时长不超过 {profile.daily_minutes} 分钟。\n"
        '输出 schema：{"goal_desc": "一句话目标", "tasks": [{"date": "YYYY-MM-DD", '
        '"subject": "listening", "title": "任务标题", "detail": "具体做法", "est_minutes": 30}]}'
    )
    user = (
        f"档案：{profile.title}；考试日期 {exam_date.isoformat()}；"
        f"目标分 {profile.target_score or DEFAULT_TARGET_SCORE}；每日可用 {profile.daily_minutes} 分钟。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_plan_payload(
    text: Optional[str],
    *,
    start: date,
    exam_date: date,
    skeleton: tuple[str, ...],
) -> tuple[str, list[dict[str, Any]]]:
    """Parse and validate the generated plan, or `MODEL_OUTPUT_INVALID` (05 §4.7 无空话原则).

    Every task must sit inside the plan window and name a declared subject; the goal line is
    optional. Days the model leaves out are the caller's business (they get filled), but a task it
    *did* return has to be usable — a silently dropped task would make `task_count` a lie.
    """
    payload, reason = extract_json(text)
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise CampusError("MODEL_OUTPUT_INVALID", f"计划输出无法解析（{reason or 'tasks 缺失'}）")
    validated: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 条任务不是对象")
        raw_date = str(task.get("date") or "").strip()
        try:
            scheduled = datetime.strptime(raw_date, PLAN_DATE_FORMAT).date()
        except ValueError:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 条任务日期非法：{raw_date}") from None
        if not start <= scheduled <= exam_date:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 条任务日期越出计划窗口：{raw_date}")
        subject = str(task.get("subject") or "").strip()
        if skeleton and subject not in skeleton:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 条任务科目不在骨架内：{subject}")
        title = str(task.get("title") or "").strip()
        if not title:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 条任务缺少标题")
        minutes = task.get("est_minutes")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
            minutes = PLAN_FALLBACK_MINUTES
        validated.append(
            {
                "date": scheduled.isoformat(),
                "subject": subject,
                "title": title,
                "detail": str(task.get("detail") or ""),
                "est_minutes": minutes,
            }
        )
    goal = payload.get("goal_desc")
    return (str(goal).strip() if goal else ""), validated


def _plan_priority(subject: str, skeleton: tuple[str, ...]) -> int:
    """The task's priority, taken from the station's declared spending order (01 §3.2).

    1 is the most important entry of `subject_skeleton` — for CET that is listening, so the
    "听力和仔细阅读优先" rule of PRD CET1 ③ is expressed by the station declaration, not by a
    special case in the generator.
    """
    if subject in skeleton:
        return skeleton.index(subject) + 1
    return len(skeleton) + 1 if skeleton else 1


def _fill_plan_days(
    tasks: list[dict[str, Any]],
    *,
    start: date,
    exam_date: date,
    skeleton: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Give every day of the window at least one task (PRD CET1 ③ "每天任务数 ≥1").

    Days the model skipped get one fallback task, rotated through the station's skeleton so the
    order still reflects the spending priority. A model that returned nothing usable for a day is
    the normal case for long windows, so this runs on every generation rather than as an error
    path.
    """
    covered = {task["date"] for task in tasks}
    filled = list(tasks)
    for offset in range((exam_date - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        if day in covered:
            continue
        subject = skeleton[offset % len(skeleton)] if skeleton else ""
        filled.append(
            {
                "date": day,
                "subject": subject,
                "title": PLAN_FALLBACK_TITLE.format(subject=subject or "当日"),
                "detail": PLAN_FALLBACK_DETAIL,
                "est_minutes": PLAN_FALLBACK_MINUTES,
            }
        )
    filled.sort(key=lambda task: (task["date"], _plan_priority(task["subject"], skeleton)))
    return filled


def _utcnow() -> str:
    """The campus timestamp format of 02 §1.3 (ISO 8601 UTC to the second)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _grading_of(row: Any) -> dict[str, Any]:
    """The decoded `grading_json` of an attempt row, or an empty dict when it is unusable."""
    payload = _decode(row["grading_json"], None)
    return payload if isinstance(payload, dict) else {}


def _error_list(errors: Any, answer: str) -> list[dict[str, Any]]:
    """Adapt the engine's error entries onto the documented `{original, suggestion, type, offset}`.

    The offset is the position of the offending fragment inside the submitted text, which is what
    makes each entry clickable back to the original (PRD CET4 ②); a fragment the model paraphrased
    rather than quoted yields `null` instead of a misleading position.
    """
    adapted: list[dict[str, Any]] = []
    for error in errors or []:
        if not isinstance(error, Mapping):
            continue
        original = str(error.get("fragment") or "")
        offset = answer.find(original) if original else -1
        adapted.append(
            {
                "original": original,
                "suggestion": str(error.get("suggestion") or ""),
                "type": str(error.get("type") or ""),
                "offset": None if offset < 0 else offset,
            }
        )
    return adapted


def build_assessment_messages(profile: models.ExamProfile) -> list[dict[str, str]]:
    """The 定级测评 出题 prompt (05 §3.1 cet-examiner: 20 题固定结构).

    The section mix is spelled out in the prompt because the server validates it afterwards: a
    model that returns 19 items or the wrong mix is refused rather than partially stored.
    """
    layout = "\n".join(
        f"- {subject} {count} 题（{focus}）" for subject, count, focus in ASSESSMENT_PROMPT_SECTIONS
    )
    total = sum(count for _subject, count, _focus in ASSESSMENT_PROMPT_SECTIONS)
    system = (
        "你在为一位备考四六级的学生出定级测评卷。只输出一个 JSON 对象，不要任何其他文字。\n"
        f"共 {total} 道单项选择题，每题 1 分、四个选项、唯一正确答案：\n{layout}\n"
        '输出 schema：{"items": [{"subject": "vocab", "qtype": "single", "stem": "题干", '
        '"options": [{"key": "A", "text": "选项"}], "answer": "A"}]}\n'
        "要求：题干与选项用中文（听力题给出可阅读的文本材料），answer 只写正确选项的 key；"
        "subject 只能取 vocab / listening / reading / writing / translation。"
    )
    user = f"考生档案：{profile.title}（目标分 {profile.target_score or DEFAULT_TARGET_SCORE}）。请出题。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_assessment_items(text: Optional[str]) -> list[dict[str, Any]]:
    """Parse and validate the generated 20 items, or `MODEL_OUTPUT_INVALID` (ADR-03 不静默).

    Validation covers the whole paper at once: every item has a usable subject, a non-empty stem
    and answer, and single/multiple items carry options; then the per-section counts must match
    05 §3.1 exactly (词汇 6 / 听力 4 / 阅读 5 / 写译 5). A payload that fails any of these is
    refused before a single question is stored, so a bad generation never leaves a half paper.
    """
    payload, reason = extract_json(text)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise CampusError("MODEL_OUTPUT_INVALID", f"出题输出无法解析（{reason or 'items 缺失'}）")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题不是对象")
        subject = str(item.get("subject") or "").strip()
        stem = str(item.get("stem") or "").strip()
        answer = str(item.get("answer") or "").strip()
        qtype = str(item.get("qtype") or models.QuestionType.SINGLE.value).strip()
        if subject not in SECTION_OF_SUBJECT or not stem or not answer:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题字段缺失或 subject 非法")
        if qtype not in {q.value for q in models.QuestionType}:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题题型非法：{qtype}")
        options = item.get("options")
        if qtype in {models.QuestionType.SINGLE.value, models.QuestionType.MULTIPLE.value}:
            if not isinstance(options, list) or not options:
                raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题缺少选项")
            options = [
                {"key": str(option.get("key") or "").strip(), "text": str(option.get("text") or "").strip()}
                for option in options
                if isinstance(option, Mapping)
            ]
            if len(options) < 2 or any(not option["key"] or not option["text"] for option in options):
                raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题选项不完整")
        else:
            options = None
        normalized.append(
            {
                "subject": subject,
                "qtype": qtype,
                "stem": stem,
                "options": options,
                "answer": answer,
                "max_score": ASSESSMENT_ITEM_SCORE,
                "source": models.QuestionSource.AI.value,
            }
        )
    counts: dict[str, int] = {}
    for item in normalized:
        section = SECTION_OF_SUBJECT[str(item["subject"])]
        counts[section] = counts.get(section, 0) + 1
    if counts != dict(ASSESSMENT_SECTIONS):
        raise CampusError(
            "MODEL_OUTPUT_INVALID",
            f"出题结构与要求不符：{counts}，应为 {dict(ASSESSMENT_SECTIONS)}",
        )
    return normalized


class ManagerCaller:
    """One plain provider call through the sidecar's client — the non-grading AI path.

    `GradingEngine` owns its own provider calls; question/plan/mnemonic generation is a single
    prompt with a validated answer, so it goes through this thin caller instead. The model comes
    from the same resolution chain (`CampusService.model_for_task`) and the call keeps the grading
    chain's temperature and timeout, so one configured model drives every AI feature.
    """

    def __init__(self, provider_host: Any, resolve_model: Any) -> None:
        self._host = provider_host
        self._resolve_model = resolve_model

    def complete(self, task: str, messages: list[dict]) -> str:
        """Run one blocking completion; failures leave as documented campus codes."""
        provider = getattr(self._host, "provider", None)
        model = self._resolve_model(task)
        if provider is None or model is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        try:
            turn = provider.complete(
                model=model, messages=messages, temperature=TEMPERATURE, timeout=PROVIDER_TIMEOUT_S
            )
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower():
                raise CampusError("MODEL_TIMEOUT", f"模型调用超时：{type(exc).__name__}") from exc
            raise CampusError("MODEL_OUTPUT_INVALID", f"模型调用失败：{type(exc).__name__}") from exc
        return turn.text or ""


class ManagerGrader:
    """Runs T07's grading engine through the sidecar's provider (T07 §6-1 移交要点).

    The engine asks for a model per grading kind through its `model_picker`; campus answers with
    the model it would actually run that task on (`CampusService.model_for_task`), and the
    recommended-but-unconfigured entry of the static list never reaches the provider. The
    engine's own parameters (temperature 0, 90s, 5-call budget) stay untouched.
    """

    def __init__(
        self,
        provider_host: Any,
        resolve_model: Any,
        start_level: int,
    ) -> None:
        self._host = provider_host
        self._resolve_model = resolve_model
        self._start_level = start_level

    async def grade(self, request: GradeRequest) -> GradeResult:
        """Grade one answer through the host's `ProviderClient`."""
        provider = getattr(self._host, "provider", None)
        if provider is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        engine = GradingEngine(
            provider,
            self._pick,
            start_level=self._start_level,
        )
        return await engine.grade(request)

    def _pick(self, kind: str, track_type: str) -> tuple[str, str]:
        del track_type
        task = models.task_for_kind(kind)
        model = self._resolve_model(task)
        if model is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        return model, models.pick_for_task(task)[1]


class CampusService:
    """Global-domain orchestration (07 §4 T09).

    `store` is the single `campus.db` handle and `config` the resolved `[campus]` preferences;
    both are shared with the router that builds this service. `provider_host` is the sidecar
    object that owns the `ProviderClient` (campus only reads `.provider` off it), used by the
    AI endpoints of the E group.
    """

    def __init__(
        self,
        campus_store: CampusStore,
        config: Any,
        *,
        inventory: Optional[ModelInventory] = None,
        provider_host: Any = None,
    ) -> None:
        self._store = campus_store
        self._config = config
        self._inventory = inventory if inventory is not None else ModelInventory()
        self._grader = (
            ManagerGrader(provider_host, self.model_for_task, config.grading_start_level)
            if provider_host is not None
            else None
        )
        self._caller = (
            ManagerCaller(provider_host, self.model_for_task) if provider_host is not None else None
        )

    @property
    def inventory(self) -> ModelInventory:
        return self._inventory

    # -- A1-A5: profiles ---------------------------------------------------

    def list_profiles(
        self, *, track: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Every profile, newest first, optionally narrowed by track and status (A1).

        Archived profiles stay listed: they are reversible (02 §7.2) and the switcher needs to
        show them to offer the restore action.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if track:
            conditions.append('"track_type" = ?')
            params.append(track)
        if status:
            conditions.append('"status" = ?')
            params.append(status)
        rows = self._store.list_rows(
            "exam_profile",
            where=" AND ".join(conditions) or None,
            params=params,
            order_by="created_at DESC, rowid DESC",
        )
        return [profile_payload(models.ExamProfile.from_row(row)) for row in rows]

    def create_profile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Create a profile, refusing a title already in use (A2)."""
        title = str(payload["title"]).strip()
        self._assert_title_free(title)
        daily_minutes = payload.get("daily_minutes")
        values: dict[str, Any] = {
            "track_type": payload["track_type"],
            "title": title,
            "cert_type": payload.get("cert_type"),
            "level": payload.get("level"),
            "exam_date": payload.get("exam_date"),
            "target_score": payload.get("target_score"),
            "subjects": _encode(payload.get("subjects") or []),
            "daily_minutes": DEFAULT_DAILY_MINUTES if daily_minutes is None else daily_minutes,
            "status": models.ProfileStatus.ACTIVE.value,
        }
        profile_id = self._store.insert("exam_profile", values)
        return self.get_profile(profile_id)

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        """The profile body, or `PROFILE_NOT_FOUND` (A3)."""
        row = self._store.get("exam_profile", profile_id)
        if row is None:
            raise CampusError("PROFILE_NOT_FOUND", f"档案不存在：{profile_id}")
        return profile_payload(models.ExamProfile.from_row(row))

    def update_profile(
        self, profile: models.ExamProfile, patch: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Apply a partial update, refusing a rename onto another profile's title (A4).

        Only the fields of `PROFILE_MUTABLE_FIELDS` are honoured; `track_type` is deliberately
        not among them, because a profile's track decides the meaning of everything it owns.
        """
        values: dict[str, Any] = {}
        for name in PROFILE_MUTABLE_FIELDS:
            if name not in patch:
                continue
            value = patch[name]
            if name == "title":
                value = str(value).strip()
                if value != profile.title:
                    self._assert_title_free(value, exclude=profile.id)
            if name in JSON_PROFILE_FIELDS:
                value = _encode(value or [])
            values[name] = value
        if not values:
            return self.get_profile(profile.id)
        self._store.update("exam_profile", profile.id, values)
        return self.get_profile(profile.id)

    def delete_profile(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Delete a profile with its whole subtree, reporting the rows removed (A5, 02 §7.3).

        The cascade runs in one transaction in leaf-first order, so an interrupted delete never
        leaves orphan rows; the library directory goes afterwards, because the database is the
        authority and a re-import can rebuild the files (02 §7.3).
        """
        cascade: dict[str, int] = {}
        with self._store.transaction():
            for table in CASCADE_TABLES:
                cascade[table] = self._store.delete_where(table, "profile_id = ?", (profile.id,))
            cascade["exam_profile"] = int(self._store.delete("exam_profile", profile.id))
        if self._store.get_state(ACTIVE_PROFILE_KEY) == profile.id:
            self._store.delete_state(ACTIVE_PROFILE_KEY)
        self._remove_library_dir(profile.id)
        return {"deleted": True, "cascade": {table: rows for table, rows in cascade.items() if rows}}

    # -- A6-A7: app state and campus preferences ---------------------------

    def app_state(self) -> dict[str, Any]:
        """The global app state: the active profile pointer and the resolved preferences (A6).

        The stored `campus_settings` holds only what the user explicitly chose, and wins over
        `config.toml` (02 §4.2 "运行时以 app_state 为准"); every absent key falls back to the
        config value. `task_models` always reports all three tasks, resolved through
        `CampusConfig.resolve_task_model`, so the settings panel never needs the static list.
        """
        stored = self._stored_settings()
        overrides = stored.get("task_models")
        overrides = overrides if isinstance(overrides, dict) else {}
        return {
            "active_profile_id": self._store.get_state(ACTIVE_PROFILE_KEY, None),
            "settings": {
                "daily_minutes": self._setting(
                    stored, "daily_minutes", self._config.daily_minutes
                ),
                "push_time": self._setting(stored, "push_time", self._config.push_time),
                "review_intensity": self._setting(
                    stored, "review_intensity", self._config.review_intensity
                ),
                "task_models": {
                    task.value: overrides.get(task.value)
                    or self._config.resolve_task_model(task.value)
                    for task in models.CampusTask
                },
            },
        }

    def update_app_state(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        """Point `active_profile_id` at a real profile and/or merge preference changes (A7).

        An explicit `null` clears the key and falls back to the config file, which is how the
        settings panel offers "reset to default" without a second endpoint.
        """
        if "active_profile_id" in patch:
            value = patch["active_profile_id"]
            if value is None:
                self._store.delete_state(ACTIVE_PROFILE_KEY)
            else:
                if self._store.get("exam_profile", str(value)) is None:
                    raise CampusError("PROFILE_NOT_FOUND", f"档案不存在：{value}")
                self._store.set_state(ACTIVE_PROFILE_KEY, str(value))
        settings_patch = patch.get("settings")
        if isinstance(settings_patch, Mapping) and settings_patch:
            self._merge_settings(settings_patch)
        return self.app_state()

    # -- A8-A10: model self-check and the local-data panel -----------------

    def model_for_task(self, task: str) -> Optional[str]:
        """The model a task will actually run on, or `None` when none is callable (ADR-06).

        The first candidate the inventory considers usable wins: the user's choice in the
        settings panel, then their `config.toml` entry, then the app's active default, then the
        static recommendation. The static list is last on purpose — it names the model a task
        *should* use (A8 reports it for the UI), not necessarily one this machine holds a key
        for, so a missing recommendation degrades to the configured default instead of failing.
        """
        candidates = (
            self._task_model_override(task),
            self._config.task_models.get(task),
            self._inventory.current,
            models.pick_for_task(task)[0],
        )
        for candidate in candidates:
            if self._inventory.usable(candidate):
                return candidate
        return None

    def capabilities(self) -> dict[str, Any]:
        """The self-check card: the static recommendation list and what this machine can run (A8).

        ADR-06 replaced the runtime capability probe (`providers/base.py` carries no structured
        output flag) with a static list, so `supported` answers "can this task be called at
        all right now" — the UI shows the recommendation itself and lets the user upgrade.
        """
        return {
            "current_model": self._inventory.current,
            "tasks": [self._capability_entry(task.value) for task in models.CampusTask],
        }

    def privacy(self) -> dict[str, Any]:
        """Where campus data lives, how big it is, and which endpoints it would call (A9)."""
        root = Path(state_dir())
        return {
            "data_dir": str(root),
            "library_dir": str(root / "campus" / "library"),
            "db_size_bytes": self._store.database_bytes(),
            "model_endpoints": list(self._inventory.endpoints),
        }

    def wipe_data(self) -> dict[str, Any]:
        """Clear every local campus artefact: the database and the `campus/` tree (A10).

        This is G-03's "一键清除本地数据" of 02 §7.1 — the database is dropped and rebuilt empty
        and the library/export tree goes with it. The kernel's own database is untouched: no
        other component reads this path (02 §2.2).
        """
        root = Path(state_dir())
        freed = self._store.wipe()
        freed += _remove_tree(root, root / "campus")
        return {"cleared": True, "freed_bytes": freed}

    # -- E1-E4: question bank ----------------------------------------------

    def import_questions(
        self, profile: models.ExamProfile, fmt: str, content: str
    ) -> dict[str, Any]:
        """Import questions from an MD or CSV payload, skipping ones already in the bank (E1).

        The payload is fully parsed and validated before the first write, so a malformed block
        cannot leave a half-imported batch behind. A question already present for this profile
        with the same subject and stem is counted in `skipped` instead of being duplicated,
        which is what makes re-importing the same file idempotent.
        """
        imported: list[dict[str, Any]] = []
        skipped = 0
        for question in parse_questions(fmt, content):
            if self._question_exists(profile.id, question["subject"], question["stem"]):
                skipped += 1
                continue
            imported.append(self._insert_question(profile.id, question))
        return {"imported": len(imported), "skipped": skipped, "items": imported}

    def list_questions(
        self,
        profile: models.ExamProfile,
        *,
        point_id: Optional[str] = None,
        qtype: Optional[str] = None,
        subject: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """One page of the profile's question bank, newest first (E2, 03 §1 pagination)."""
        filters = [
            pair
            for pair in (("point_id", point_id), ("qtype", qtype), ("subject", subject))
            if pair[1]
        ]
        conditions = ['"profile_id" = ?', *(f'"{name}" = ?' for name, _ in filters)]
        total = self._store.count(
            "question_bank_item", " AND ".join(conditions), [profile.id, *(v for _, v in filters)]
        )
        rows = self._store.list_rows(
            "question_bank_item",
            profile_id=profile.id,
            where=" AND ".join(f'"{name}" = ?' for name, _ in filters) or None,
            params=[value for _, value in filters],
            order_by="created_at DESC, rowid DESC",
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return {
            "items": [question_payload(models.QuestionBankItem.from_row(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def create_question(
        self, profile: models.ExamProfile, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Add one question by hand (E3)."""
        return self._insert_question(profile.id, dict(payload))

    def update_question(
        self,
        profile: models.ExamProfile,
        question: models.QuestionBankItem,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply a partial update to a question of this profile (E4)."""
        values: dict[str, Any] = {}
        for name in QUESTION_FIELDS:
            if name not in patch:
                continue
            value = patch[name]
            if name == "point_id":
                value = self._require_point(profile.id, value)
            elif name in JSON_QUESTION_FIELDS:
                value = _encode(value)
            values[name] = value
        if values:
            self._store.update("question_bank_item", question.id, values)
        return self.question(question.id)

    def delete_question(
        self, profile: models.ExamProfile, question: models.QuestionBankItem
    ) -> dict[str, Any]:
        """Remove one question of this profile (E4)."""
        del profile
        self._store.delete("question_bank_item", question.id)
        return {"deleted": True}

    def question(self, question_id: str) -> dict[str, Any]:
        """One question body, or `QUESTION_NOT_FOUND`."""
        row = self._store.get("question_bank_item", question_id)
        if row is None:
            raise CampusError("QUESTION_NOT_FOUND", f"题目不存在：{question_id}")
        return question_payload(models.QuestionBankItem.from_row(row))

    # -- E5: answering ------------------------------------------------------

    async def submit_attempt(
        self,
        profile: models.ExamProfile,
        question: models.QuestionBankItem,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Record one answer and grade it the way its question type demands (E5).

        Objective questions are judged here against the stored key and answered immediately with
        `is_correct` plus the key itself. Subjective ones are stored first and then graded
        synchronously through the C1 chain, so the attempt survives even when the model call
        fails — the response reports the failure with its documented code while the row keeps the
        answer and the degradation trace.
        """
        answer = str(payload["answer"])
        session_type = str(payload.get("session_type") or models.SessionType.PRACTICE.value)
        mock_exam_id = self._require_mock(profile.id, payload.get("mock_exam_id"))
        if question.qtype in OBJECTIVE_QUESTION_TYPES:
            return self._record_objective(profile, question, answer, session_type, mock_exam_id)
        kind = GRADING_KIND_BY_QTYPE[question.qtype]
        if self.model_for_task(models.task_for_kind(kind)) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        attempt_id = self._insert_attempt(
            profile, question, answer, session_type, mock_exam_id
        )
        result = await self._require_grader().grade(
            GradeRequest(
                profile_id=profile.id,
                track_type=profile.track_type,
                kind=kind,
                question=question.stem,
                answer=answer,
                subject=question.subject,
            )
        )
        self._store.update("attempt", attempt_id, self._grading_columns(result, kind))
        if not result.ok:
            code = "MODEL_TIMEOUT" if result.fail_reason == "MODEL_TIMEOUT" else "MODEL_OUTPUT_INVALID"
            raise CampusError(code, f"批改失败（{result.fail_reason}）")
        body = self.attempt(attempt_id)
        body["pending_grading"] = True
        return body

    # -- C1-C4: grading (shared by every station) --------------------------

    def attempt(self, attempt_id: str) -> dict[str, Any]:
        """One attempt body, or `ATTEMPT_NOT_FOUND` — the C2 read and E5's own reply."""
        row = self._store.get("attempt", attempt_id)
        if row is None:
            raise CampusError("ATTEMPT_NOT_FOUND", f"作答记录不存在：{attempt_id}")
        return attempt_payload(models.Attempt.from_row(row))

    async def grade(
        self,
        profile: models.ExamProfile,
        question: Optional[models.QuestionBankItem],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Grade one free-form or question-bound answer through the C1 chain (03 §4.3 C1).

        The rubric is resolved first so an unknown `rubric_id` costs nothing, then a usable model
        is checked before the attempt is written: a missing model is `MODEL_NOT_CONFIGURED` with
        no side effect, while a model call that fails leaves the attempt behind with its
        degradation trace (T07 §6-3/§6-6).
        """
        kind = str(payload["kind"])
        answer = str(payload["answer"])
        rubric_id, rubric_text = self._rubric_for(kind, payload)
        if self.model_for_task(models.task_for_kind(kind)) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        subject = question.subject if question is not None else SUBJECT_BY_KIND[kind]
        attempt_id = self._store.insert(
            "attempt",
            {
                "profile_id": profile.id,
                "track_type": profile.track_type,
                "subject": subject,
                "user_answer": answer,
                "question_id": question.id if question is not None else None,
                "session_type": models.SessionType.GRADING.value,
            },
        )
        result = await self._require_grader().grade(
            GradeRequest(
                profile_id=profile.id,
                track_type=profile.track_type,
                kind=kind,
                question=question.stem if question is not None else "",
                answer=answer,
                subject=subject,
                custom_rubric=rubric_text,
            )
        )
        self._store.update("attempt", attempt_id, self._grading_columns(result, kind))
        if not result.ok:
            raise CampusError(
                "MODEL_TIMEOUT" if result.fail_reason == "MODEL_TIMEOUT" else "MODEL_OUTPUT_INVALID",
                f"批改失败（{result.fail_reason}）",
            )
        return self.grade_payload(result, attempt_id, kind, rubric_id, answer)

    def grade_payload(
        self,
        result: GradeResult,
        attempt_id: str,
        kind: str,
        rubric_id: str,
        answer: str,
    ) -> dict[str, Any]:
        """Adapt a `GradeResult` onto the documented 03 §4.3 response shape.

        Three shape differences are bridged here: the engine's per-dimension dict becomes the
        documented `[{name, score, max, comment}]` list (five-point essay dimensions, the
        translation band, or one entry per scoring point), its `fragment`/`suggestion` errors
        gain the `offset` the UI needs to highlight the original text, and the band plus the
        upgraded demo ride along as additive fields the result card renders.
        """
        return {
            "attempt_id": attempt_id,
            "degrade_level": result.degrade_level,
            "rubric": rubric_id,
            "dimensions": self._dimensions(kind, result),
            "errors": _error_list(result.errors, answer),
            "model_answer_outline": result.model_answer_outline,
            "model_used": result.model_used,
            "notice": result.notice,
            "band": result.band,
            "upgraded_demo": result.upgraded_demo,
        }

    def attempt_history(
        self,
        profile: models.ExamProfile,
        *,
        subject: Optional[str] = None,
        kind: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """One page of the profile's graded attempts, newest first (C3).

        `kind` is matched against the `kind` recorded inside `grading_json`; like the CET-12
        aggregation of 02 §4.13 this is a Python-side scan rather than a JSON index, so the
        page is sliced after filtering.
        """
        rows = self._store.list_rows(
            "attempt",
            profile_id=profile.id,
            where='"subject" = ?' if subject else None,
            params=[subject] if subject else [],
            order_by="created_at DESC, rowid DESC",
        )
        if kind:
            rows = [row for row in rows if _grading_of(row).get("kind") == kind]
        page_rows = rows[(page - 1) * page_size : (page - 1) * page_size + page_size]
        return {
            "items": [attempt_payload(models.Attempt.from_row(row)) for row in page_rows],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    def common_errors(
        self, profile: models.ExamProfile, *, kind: Optional[str] = None
    ) -> dict[str, Any]:
        """The profile's most frequent grading error types, ranked (C4 / CET-12).

        Counts come from `grading_json.errors[].type` across the profile's attempts (02 §4.13),
        with a per-type sample of the offending fragments so the card can show what the mistake
        looked like. A stored payload that cannot be decoded is skipped instead of failing the
        whole ranking.
        """
        counts: dict[str, int] = {}
        samples: dict[str, list[str]] = {}
        for row in self._store.list_rows(
            "attempt",
            profile_id=profile.id,
            where='"grading_json" IS NOT NULL',
            order_by="created_at DESC, rowid DESC",
        ):
            grading = _grading_of(row)
            if not grading or (kind and grading.get("kind") != kind):
                continue
            for error in grading.get("errors") or []:
                if not isinstance(error, Mapping):
                    continue
                type_name = str(error.get("type") or "").strip()
                if not type_name:
                    continue
                counts[type_name] = counts.get(type_name, 0) + 1
                bucket = samples.setdefault(type_name, [])
                fragment = str(error.get("fragment") or "").strip()
                if fragment and fragment not in bucket and len(bucket) < MAX_ERROR_SAMPLES:
                    bucket.append(fragment)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:TOP_ERROR_TYPES]
        return {
            "top3": [
                {"type": type_name, "count": count, "samples": samples.get(type_name, [])}
                for type_name, count in ranked
            ]
        }

    # -- G1: today's suggestion and the self-built board -------------------

    def list_tasks(
        self,
        profile: models.ExamProfile,
        *,
        date: Optional[str] = None,
        status: Optional[str] = None,
        track: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """The profile's plan tasks, oldest day and most important first (G1).

        Called with `date=<today>` this is the "今日建议" of 07 §4 T09; called without a date it is
        the board's data source (ADR-11: the board is `plan_task` itself, no Teams involvement).
        `track` is matched against `plan_task.subject`, which is where 02 §4.10 keeps the subject
        or four-track label.
        """
        filters = [
            pair
            for pair in (("scheduled_date", date), ("status", status), ("subject", track))
            if pair[1]
        ]
        rows = self._store.list_rows(
            "plan_task",
            profile_id=profile.id,
            where=" AND ".join(f'"{name}" = ?' for name, _ in filters) or None,
            params=[value for _, value in filters],
            order_by="scheduled_date, priority, created_at, rowid",
        )
        return [task_payload(models.PlanTask.from_row(row)) for row in rows]

    # -- F1-F4: the level assessment (CET-01) ------------------------------

    async def create_assessment(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Generate the 20-question level assessment and open a draft (F1).

        The paper is generated, validated as a whole and stored in one transaction, so a bad
        generation leaves neither a partial question bank nor an empty assessment behind.
        """
        if self.model_for_task(models.CampusTask.QUESTION.value) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        answer = await asyncio.to_thread(
            self._require_caller().complete,
            models.CampusTask.QUESTION.value,
            build_assessment_messages(profile),
        )
        items = validate_assessment_items(answer)
        with self._store.transaction():
            question_ids = [self._insert_question(profile.id, item)["id"] for item in items]
            assessment_id = self._store.insert(
                "assessment",
                {
                    "profile_id": profile.id,
                    "question_ids": json.dumps(question_ids),
                    "started_at": _utcnow(),
                },
            )
        return self.assessment(self._load_assessment(profile.id, assessment_id))

    def assessment(self, assessment: models.Assessment) -> dict[str, Any]:
        """The documented assessment body: stored fields decoded plus the resume question list.

        The questions are returned **without their answer keys**: the paper is graded at F4, and a
        resume view that leaked the keys would make 自评 meaningless (03 §4.6 keeps the key server
        side until the paper is finished).
        """
        payload = asdict(assessment)
        payload["question_ids"] = _decode(assessment.question_ids, [])
        payload["answers"] = _decode(assessment.answers, {})
        payload["scores"] = _decode(assessment.scores, None)
        payload["questions"] = [
            self._resume_question(question_id) for question_id in payload["question_ids"]
        ]
        return payload

    def record_answers(
        self,
        profile: models.ExamProfile,
        assessment: models.Assessment,
        answers: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Merge a batch of answers into the draft, refusing unknown question ids (F3).

        Only ids that belong to this paper are accepted: storing an unrelated id would silently
        create an answer nobody can grade, and a finished paper is immutable
        (`ASSESSMENT_FINISHED`).
        """
        if assessment.status == models.AssessmentStatus.FINISHED.value:
            raise CampusError("ASSESSMENT_FINISHED", f"测评已结束：{assessment.id}")
        known = set(_decode(assessment.question_ids, []))
        merged = _decode(assessment.answers, {})
        merged = dict(merged) if isinstance(merged, Mapping) else {}
        for question_id, answer in answers.items():
            if str(question_id) not in known:
                raise CampusError("QUESTION_NOT_FOUND", f"题目不属于本次测评：{question_id}")
            merged[str(question_id)] = "" if answer is None else str(answer)
        self._store.update("assessment", assessment.id, {"answers": json.dumps(merged, ensure_ascii=False)})
        return self.assessment(self._load_assessment(profile.id, assessment.id))

    def finish_assessment(
        self, profile: models.ExamProfile, assessment: models.Assessment
    ) -> dict[str, Any]:
        """Grade the paper offline, fold the three sections onto 710 and write the side effects (F4).

        Folding is deterministic — every item is objectively judged against its stored key — which
        is what makes the "数字自洽" acceptance (PRD CET1 ②) a property of the code rather than of
        the model. The side effects are 02 §4.8's per-section `mastery` rows, the profile's
        `current_estimate` (02 §4.3) and, when the user never set one, the default 425 target the
        gap table needs.
        """
        if assessment.status == models.AssessmentStatus.FINISHED.value:
            raise CampusError("ASSESSMENT_FINISHED", f"测评已结束：{assessment.id}")
        answers = _decode(assessment.answers, {})
        answers = answers if isinstance(answers, Mapping) else {}
        correct: dict[str, int] = {section: 0 for section in SECTION_WEIGHTS}
        totals: dict[str, int] = {section: 0 for section in SECTION_WEIGHTS}
        vocab = {"correct": 0, "total": 0}
        for question_id in _decode(assessment.question_ids, []):
            row = self._store.get("question_bank_item", str(question_id))
            if row is None:
                continue
            question = models.QuestionBankItem.from_row(row)
            section = SECTION_OF_SUBJECT.get(question.subject)
            answered = answers.get(str(question_id))
            hit = answered is not None and self._judge(question, str(answered))
            if section is None:
                continue
            if section not in SECTION_WEIGHTS:
                vocab["total"] += 1
                vocab["correct"] += int(hit)
                continue
            totals[section] += 1
            correct[section] += int(hit)
        scores = {
            section: round(weight * correct[section] / totals[section], 1) if totals[section] else 0.0
            for section, weight in SECTION_WEIGHTS.items()
        }
        estimate_total = round(sum(scores.values()), 1)
        target = profile.target_score or DEFAULT_TARGET_SCORE
        gap_table = [
            {
                "section": section,
                "current": scores[section],
                "target": round(target * weight / FULL_SCORE, 2),
                "gap": round(round(target * weight / FULL_SCORE, 2) - scores[section], 1),
            }
            for section, weight in SECTION_WEIGHTS.items()
        ]
        stored_scores = {**scores, "estimate_total": estimate_total}
        with self._store.transaction():
            self._store.update(
                "assessment",
                assessment.id,
                {
                    "status": models.AssessmentStatus.FINISHED.value,
                    "scores": json.dumps(stored_scores, ensure_ascii=False),
                    "finished_at": _utcnow(),
                },
            )
            self._write_assessment_mastery(profile, correct, totals)
            profile_update: dict[str, Any] = {"current_estimate": round(estimate_total)}
            if not profile.target_score:
                profile_update["target_score"] = DEFAULT_TARGET_SCORE
            self._store.update("exam_profile", profile.id, profile_update)
        return {
            "scores": stored_scores,
            "estimate_total": estimate_total,
            "gap_table": gap_table,
            "vocab": vocab,
        }

    # -- F5: plan generation (shared by every station) ----------------------

    async def generate_plan(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Generate a day-by-day plan up to the exam date and store it (F5).

        The station difference never appears as a branch here: the subject vocabulary and the
        spending order come from the profile's `TrackSpec.subject_skeleton` (01 §3.2), so a fourth
        station is one entry in `tracks.py`. Structural promises (cover every day, ≥1 task a day,
        priority by the declared order) are enforced server-side, which is what makes PRD CET1 ③ a
        property of the code rather than of the model.
        """
        if not profile.exam_date:
            raise CampusError("EXAM_DATE_REQUIRED", "请先在档案里设置考试日期")
        if self.model_for_task(models.CampusTask.QUESTION.value) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        start = date.today()
        exam_date = datetime.strptime(profile.exam_date, PLAN_DATE_FORMAT).date()
        if exam_date < start:
            raise CampusError("EXAM_DATE_REQUIRED", f"考试日期已过（{profile.exam_date}），请更新档案")
        skeleton = self._plan_skeleton(profile)
        answer = await asyncio.to_thread(
            self._require_caller().complete,
            models.CampusTask.QUESTION.value,
            build_plan_messages(profile, start=start, exam_date=exam_date, skeleton=skeleton),
        )
        goal_desc, tasks = validate_plan_payload(
            answer, start=start, exam_date=exam_date, skeleton=skeleton
        )
        tasks = _fill_plan_days(tasks, start=start, exam_date=exam_date, skeleton=skeleton)
        with self._store.transaction():
            plan_id = self._store.insert(
                "study_plan",
                {
                    "profile_id": profile.id,
                    "track": None,
                    "start_date": start.isoformat(),
                    "end_date": exam_date.isoformat(),
                    "goal_desc": goal_desc,
                    "source": models.PlanSource.AI_GENERATED.value,
                },
            )
            for task in tasks:
                self._store.insert(
                    "plan_task",
                    {
                        "plan_id": plan_id,
                        "profile_id": profile.id,
                        "title": task["title"],
                        "subject": task["subject"],
                        "scheduled_date": task["date"],
                        "detail": task["detail"],
                        "est_minutes": task["est_minutes"],
                        "priority": _plan_priority(task["subject"], skeleton),
                    },
                )
        return {"plan_id": plan_id, "task_count": len(tasks), "first_date": start.isoformat()}

    # -- internals ---------------------------------------------------------

    def _plan_skeleton(self, profile: models.ExamProfile) -> tuple[str, ...]:
        """The station's declared subjects, falling back to the profile's own list.

        `tracks.py` declares the skeleton per station (01 §3.2); a profile created for a station
        without one (the reserved `other`) or a CERT profile (whose subjects live in its knowledge
        tree) can still carry its own `subjects` list, and an empty result simply means "no
        vocabulary to validate against" rather than a failure.
        """
        spec = tracks.spec_for(profile.track_type) if profile.track_type in tracks.TRACKS else None
        if spec is not None and spec.subject_skeleton:
            return spec.subject_skeleton
        own = _decode(profile.subjects, [])
        return tuple(str(subject) for subject in own) if isinstance(own, list) else ()

    def _load_assessment(self, profile_id: str, assessment_id: str) -> models.Assessment:
        row = self._store.get_scoped("assessment", assessment_id, profile_id)
        if row is None:
            raise CampusError("ASSESSMENT_NOT_FOUND", f"测评不存在：{assessment_id}")
        return models.Assessment.from_row(row)

    def _resume_question(self, question_id: str) -> dict[str, Any]:
        row = self._store.get("question_bank_item", str(question_id))
        if row is None:
            return {"id": str(question_id)}
        payload = question_payload(models.QuestionBankItem.from_row(row))
        for hidden in ("answer", "answer_meta"):
            payload.pop(hidden, None)
        return payload

    def _write_assessment_mastery(
        self, profile: models.ExamProfile, correct: Mapping[str, int], totals: Mapping[str, int]
    ) -> None:
        """UPSERT the three per-section mastery rows (02 §4.8: `point_id IS NULL` = 分项掌握度).

        The unique index on `(profile_id, point_id, dimension)` cannot dedupe these rows because
        SQLite treats NULL point ids as distinct, so the existing row is looked up explicitly and
        updated — otherwise every re-assessment would pile up a new generation of rows.
        """
        now = _utcnow()
        for section, total in totals.items():
            ratio = (correct[section] / total) if total else 0.0
            level = models.MasteryLevel.UNKNOWN.value
            if ratio >= MASTERY_MASTERED_RATIO:
                level = models.MasteryLevel.MASTERED.value
            elif ratio >= MASTERY_FUZZY_RATIO:
                level = models.MasteryLevel.FUZZY.value
            values = {
                "level": level,
                "score_0_100": round(ratio * 100),
                "evidence": f"定级测评：{section} {correct[section]}/{total} 正确",
                "updated_at": now,
            }
            existing = self._store.query_one(
                'SELECT "id" FROM "mastery" WHERE "profile_id" = ? AND "point_id" IS NULL '
                'AND "dimension" = ?',
                (profile.id, section),
            )
            if existing is None:
                self._store.insert(
                    "mastery", {"profile_id": profile.id, "dimension": section, **values}
                )
            else:
                self._store.update("mastery", existing["id"], values)

    def _require_caller(self) -> ManagerCaller:
        if self._caller is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        return self._caller

    def _record_objective(
        self,
        profile: models.ExamProfile,
        question: models.QuestionBankItem,
        answer: str,
        session_type: str,
        mock_exam_id: Optional[str],
    ) -> dict[str, Any]:
        max_score = float(question.max_score if question.max_score is not None else 0)
        correct = self._judge(question, answer)
        attempt_id = self._insert_attempt(
            profile,
            question,
            answer,
            session_type,
            mock_exam_id,
            values={
                "is_correct": 1 if correct else 0,
                "score": max_score if correct else 0.0,
                "max_score": max_score,
            },
        )
        body = self.attempt(attempt_id)
        body["pending_grading"] = False
        body["standard_answer"] = question.answer
        return body

    def _judge(self, question: models.QuestionBankItem, answer: str) -> bool:
        """Compare an objective answer with the stored key, normalising the documented spellings.

        A question with no key can never be marked correct: guessing "correct by default" would
        feed the mistake book with false negatives, which is worse than an explicit zero.
        """
        expected = question.answer
        if expected is None or not str(expected).strip():
            return False
        if question.qtype == models.QuestionType.MULTIPLE.value:
            return _letters(expected) == _letters(answer)
        if question.qtype == models.QuestionType.JUDGE.value:
            return _judge_value(expected) == _judge_value(answer)
        if question.qtype == models.QuestionType.BLANK.value:
            return _blanks(expected) == _blanks(answer)
        return str(expected).strip().upper() == answer.strip().upper()

    def _insert_attempt(
        self,
        profile: models.ExamProfile,
        question: models.QuestionBankItem,
        answer: str,
        session_type: str,
        mock_exam_id: Optional[str],
        *,
        values: Optional[Mapping[str, Any]] = None,
    ) -> str:
        row: dict[str, Any] = {
            "profile_id": profile.id,
            "track_type": profile.track_type,
            "subject": question.subject,
            "user_answer": answer,
            "question_id": question.id,
            "session_type": session_type,
            "mock_exam_id": mock_exam_id,
        }
        row.update(values or {})
        return self._store.insert("attempt", row)

    def _rubric_for(self, kind: str, payload: Mapping[str, Any]) -> tuple[str, Optional[str]]:
        """Resolve the rubric to grade with, returning its reported id and its full text.

        A caller-supplied `custom_rubric` wins outright and reports itself as `custom`; otherwise
        an explicit `rubric_id` selects a `rubrics.py` constant and an unknown one is
        `RUBRIC_NOT_FOUND`. With neither, the kind's own default applies — so the reported id is
        always the rubric that actually shaped the prompt (T07's engine treats `custom_rubric` as
        a full override of the built-in text).
        """
        custom = str(payload.get("custom_rubric") or "").strip()
        if custom:
            return CUSTOM_RUBRIC_ID, custom
        rubric_id = payload.get("rubric_id")
        if rubric_id:
            text = RUBRIC_TEXTS.get(str(rubric_id))
            if text is None:
                raise CampusError("RUBRIC_NOT_FOUND", f"评分标准不存在：{rubric_id}")
            return str(rubric_id), text
        default_id = RUBRIC_BY_KIND[kind]
        return default_id, RUBRIC_TEXTS[default_id]

    def _dimensions(self, kind: str, result: GradeResult) -> list[dict[str, Any]]:
        """The documented `dimensions` list for the graded kind (03 §4.3).

        Essay keeps the three five-point dimensions of 06 §2.2 in their canonical order; a
        translation has one 15-point band dimension (its L0/L1 payload carries no breakdown);
        a scoring-point kind reports one entry per point with the three states mapped to
        1 / 0.5 / 0.
        """
        if kind in SCORING_KINDS:
            return [
                {
                    "name": str(point.get("point", "")),
                    "score": SCORING_POINT_SCORES.get(str(point.get("status")), 0.0),
                    "max": SCORING_POINT_MAX,
                    "comment": str(point.get("note") or ""),
                }
                for point in result.scoring_points
            ]
        if kind in TRANSLATION_KINDS:
            if result.band is None:
                return []
            return [
                {
                    "name": TRANSLATION_DIMENSION_NAME,
                    "score": result.band,
                    "max": rubrics.TRANSLATION_BAND_MAX,
                    "comment": "",
                }
            ]
        scores = result.dimension_scores or {}
        return [
            {
                "name": DIMENSION_LABELS.get(name, name),
                "score": scores.get(name),
                "max": ESSAY_DIMENSION_MAX,
                "comment": "",
            }
            for name in rubrics.ESSAY_DIMENSIONS
            if name in scores
        ]

    def _grading_columns(self, result: GradeResult, kind: str) -> dict[str, Any]:
        """Map a `GradeResult` onto the attempt columns and its `grading_json` whitelist.

        The whitelist is T07 §6-4: the server-side fields (`ok`, `model_used`, `usage`,
        `fail_reason`) stay out, `degrade_level` gets its own column, and the degradation trace
        is kept under `_degrade_trace`. `kind` is kept alongside them because C3/C4 filter on it
        and 02 §4.13 has no column for it. `score` carries the rubric band on the 15-point scale
        of 06 §2.1; a scoring-point kind has no band, so both score columns stay empty and the
        detail lives in `grading_json.scoring_points`.
        """
        score = None if result.band is None else float(result.band)
        return {
            "grading_json": json.dumps(
                {
                    "kind": kind,
                    "band": result.band,
                    "dimension_scores": result.dimension_scores,
                    "errors": result.errors,
                    "scoring_points": result.scoring_points,
                    "upgraded_demo": result.upgraded_demo,
                    "model_answer_outline": result.model_answer_outline,
                    "notice": result.notice,
                    "raw_text": result.raw_text,
                    "_degrade_trace": result.degrade_trace,
                    "schema_flags": result.schema_flags,
                    "calls": result.calls,
                    "retries": result.retries,
                },
                ensure_ascii=False,
            ),
            "degrade_level": result.degrade_level,
            "model_used": result.model_used,
            "score": score,
            "max_score": None if score is None else float(BAND_MAX_SCORE),
        }

    def _require_grader(self) -> ManagerGrader:
        if self._grader is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        return self._grader

    def _require_mock(self, profile_id: str, mock_exam_id: Optional[str]) -> Optional[str]:
        """Validate `mock_exam_id` inside the profile's scope, or `MOCK_NOT_FOUND`."""
        if mock_exam_id is None:
            return None
        if self._store.get_scoped("mock_exam", str(mock_exam_id), profile_id) is None:
            raise CampusError("MOCK_NOT_FOUND", f"模考不存在：{mock_exam_id}")
        return str(mock_exam_id)

    def _insert_question(self, profile_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        values = {
            "profile_id": profile_id,
            "subject": str(data["subject"]),
            "stem": str(data["stem"]),
            "qtype": str(data.get("qtype") or models.QuestionType.SINGLE.value),
            "point_id": self._require_point(profile_id, data.get("point_id")),
            "options": _encode(data.get("options")),
            "answer": data.get("answer") or None,
            "answer_meta": _encode(data.get("answer_meta")),
            "max_score": 1 if data.get("max_score") is None else data["max_score"],
            "difficulty": data.get("difficulty"),
            "source": str(data.get("source") or models.QuestionSource.MANUAL.value),
            "doc_id": data.get("doc_id") or None,
        }
        return self.question(self._store.insert("question_bank_item", values))

    def _question_exists(self, profile_id: str, subject: str, stem: str) -> bool:
        row = self._store.query_one(
            'SELECT "id" FROM "question_bank_item" WHERE "profile_id" = ? AND "subject" = ? '
            'AND "stem" = ?',
            (profile_id, subject, stem),
        )
        return row is not None

    def _require_point(self, profile_id: str, point_id: Optional[str]) -> Optional[str]:
        """Validate a knowledge point inside the profile's scope, or `POINT_NOT_FOUND`.

        The read is scoped (`WHERE id = ? AND profile_id = ?`), so another profile's point is
        simply not found — the same answer as a point that never existed, which keeps a
        cross-profile reference from confirming that someone else's row exists.
        """
        if point_id is None:
            return None
        if self._store.get_scoped("knowledge_point", str(point_id), profile_id) is None:
            raise CampusError("POINT_NOT_FOUND", f"知识点不存在：{point_id}")
        return str(point_id)

    def _task_model_override(self, task: str) -> Optional[str]:
        overrides = self._stored_settings().get("task_models")
        return overrides.get(task) if isinstance(overrides, Mapping) else None

    def _capability_entry(self, task: str) -> dict[str, Any]:
        recommended, minimum = models.pick_for_task(task)
        supported = self.model_for_task(task) is not None
        return {
            "task": task,
            "recommended": recommended,
            "minimum": minimum,
            "supported": supported,
            "reason": f"建议使用 {recommended} 及以上模型" if supported else "尚未配置可用模型",
        }

    def _stored_settings(self) -> dict[str, Any]:
        stored = self._store.get_state(SETTINGS_KEY, {})
        return dict(stored) if isinstance(stored, dict) else {}

    def _setting(self, stored: Mapping[str, Any], name: str, default: Any) -> Any:
        value = stored.get(name)
        return default if value is None else value

    def _merge_settings(self, patch: Mapping[str, Any]) -> None:
        stored = self._stored_settings()
        for name in ("daily_minutes", "push_time", "review_intensity"):
            if name not in patch:
                continue
            if patch[name] is None:
                stored.pop(name, None)
            else:
                stored[name] = patch[name]
        if "task_models" in patch:
            overrides = dict(stored.get("task_models") or {})
            for task, model in (patch["task_models"] or {}).items():
                if model:
                    overrides[str(task)] = str(model)
                else:
                    overrides.pop(str(task), None)
            if overrides:
                stored["task_models"] = overrides
            else:
                stored.pop("task_models", None)
        if stored:
            self._store.set_state(SETTINGS_KEY, stored)
        else:
            self._store.delete_state(SETTINGS_KEY)

    def _assert_title_free(self, title: str, *, exclude: Optional[str] = None) -> None:
        row = self._store.query_one('SELECT "id" FROM "exam_profile" WHERE "title" = ?', (title,))
        if row is not None and row["id"] != exclude:
            raise CampusError("DUPLICATE_TITLE", f"同名档案已存在：{title}")

    def _remove_library_dir(self, profile_id: str) -> None:
        """Drop `campus/library/<profile_id>/`, staying inside the state directory."""
        root = Path(state_dir())
        target = root / "campus" / "library" / profile_id
        if target.parent.name != "library" or root not in target.parents:
            return
        shutil.rmtree(target, ignore_errors=True)
