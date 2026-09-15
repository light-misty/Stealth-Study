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
from . import models, tracks
from .config import DEFAULT_DAILY_MINUTES
from .grading import (
    PROVIDER_TIMEOUT_S,
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

PLAN_STAGES: tuple[tuple[str, float], ...] = (
    (models.PlanStage.FOUNDATION.value, 0.4),
    (models.PlanStage.INTENSIVE.value, 0.3),
    (models.PlanStage.PASTPAPER.value, 0.2),
    (models.PlanStage.SPRINT.value, 0.1),
)

PLAN_STAGE_LABELS: Mapping[str, str] = {
    "foundation": "基础",
    "intensive": "强化",
    "pastpaper": "真题",
    "sprint": "冲刺",
}

PLAN_PRIORITY_BY_STAGE: Mapping[str, int] = {
    "foundation": 3,
    "intensive": 2,
    "pastpaper": 1,
    "sprint": 1,
}

TRACK_LABELS: Mapping[str, str] = {
    "overall": "综合",
    "politics": "政治",
    "english": "英语",
    "math": "数学",
    "major": "专业课",
    "listening": "听力",
    "reading": "阅读",
    "writing": "写作",
    "translation": "翻译",
}


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


TASK_TRANSITIONS: Mapping[str, frozenset[str]] = {
    models.PlanTaskStatus.TODO.value: frozenset(
        {models.PlanTaskStatus.DOING.value, models.PlanTaskStatus.SKIPPED.value}
    ),
    models.PlanTaskStatus.DOING.value: frozenset(
        {models.PlanTaskStatus.REVIEW.value, models.PlanTaskStatus.SKIPPED.value}
    ),
    models.PlanTaskStatus.REVIEW.value: frozenset(
        {models.PlanTaskStatus.DONE.value, models.PlanTaskStatus.REVIEW.value}
    ),
    models.PlanTaskStatus.DONE.value: frozenset(),
    models.PlanTaskStatus.SKIPPED.value: frozenset(),
}

PLAN_LAG_THRESHOLD = 0.15


def _track_label(subject: str) -> str:
    return TRACK_LABELS.get(subject, subject)


def _parse_exam_date(raw: str) -> date:
    """Parse a `YYYY-MM-DD` exam date, refusing absence and garbage with the same code.

    `EXAM_DATE_REQUIRED` is the documented precondition of both F5 and G3 (03 §4.4), so an
    unparsable stored date fails the request the same way a missing one does instead of
    inventing a new error code.
    """
    text = str(raw or "").strip()
    if not text:
        raise CampusError("EXAM_DATE_REQUIRED", "请先设置考试日期")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise CampusError("EXAM_DATE_REQUIRED", f"考试日期无效：{text}") from None


def _stage_counts(weeks: int) -> list[int]:
    counts = [max(1, round(weeks * frac)) for _stage, frac in PLAN_STAGES]
    counts[0] += weeks - sum(counts)
    return counts


def _stage_for_week(index: int, weeks: int) -> str:
    if weeks < len(PLAN_STAGES):
        position = min(index * len(PLAN_STAGES) // weeks, len(PLAN_STAGES) - 1)
        return PLAN_STAGES[position][0]
    elapsed = 0
    for (stage, _frac), count in zip(PLAN_STAGES, _stage_counts(weeks)):
        elapsed += count
        if index < elapsed:
            return stage
    return PLAN_STAGES[-1][0]


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


def weekly_report_payload(report: models.WeeklyReport) -> dict[str, Any]:
    """One weekly report with its JSON columns decoded (03 §4.7 G5/G6 shape)."""
    payload = asdict(report)
    payload["completion_rate"] = _decode(payload.get("completion_rate"), {})
    payload["top_mistake_points"] = _decode(payload.get("top_mistake_points"), [])
    return payload


def school_profile_payload(school: models.SchoolProfile) -> dict[str, Any]:
    """One school card with its JSON columns decoded (02 §4.4)."""
    payload = asdict(school)
    for name in ("subjects", "past_scores", "books"):
        payload[name] = _decode(payload.get(name), [])
    return payload


SCHOOL_PROFILE_MUTABLE_FIELDS: tuple[str, ...] = (
    "school",
    "major",
    "degree_type",
    "subjects",
    "enroll_count",
    "recommend_ratio",
    "past_scores",
    "books",
    "note",
)

JSON_SCHOOL_FIELDS: frozenset[str] = frozenset({"subjects", "past_scores", "books"})

SCHOOL_PREFILL_FIELDS = 8

_DEGREE_SYNONYMS: Mapping[str, str] = {
    "academic": "academic",
    "professional": "professional",
    "学硕": "academic",
    "学术型": "academic",
    "学术学位": "academic",
    "专硕": "professional",
    "专业型": "professional",
    "专业学位": "professional",
}


def _clean_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text


def _clean_degree(value: Any) -> Optional[str]:
    return _DEGREE_SYNONYMS.get(_clean_text(value).lower())


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for entry in value:
        if isinstance(entry, Mapping):
            entry = entry.get("name") or entry.get("title") or ""
        text = _clean_text(entry)
        if text:
            items.append(text[:60])
    return items


def _clean_enroll_count(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _clean_ratio(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 1:
        return round(number, 4)
    if 1 < number <= 100:
        return round(number / 100, 4)
    return None


def _clean_past_scores(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            continue
        try:
            year = int(str(entry.get("year")).strip()[:4])
            line = float(entry.get("line"))
        except (TypeError, ValueError):
            continue
        items.append({"year": year, "line": line})
    return items


def school_prefill(data: Optional[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    """Keep only the well-formed fields of a school extraction, scored by coverage.

    `confidence` is the share of the eight documented fields the model actually produced in a
    valid shape (KY-14 验收 1 的"抽取 ≥3 字段"由调用方按此判断); unusable output degrades to
    an empty prefill with confidence 0 instead of failing the endpoint.
    """
    prefill: dict[str, Any] = {}
    if not data:
        return prefill, 0.0
    school = _clean_text(data.get("school"))
    if school:
        prefill["school"] = school[:80]
    major = _clean_text(data.get("major"))
    if major:
        prefill["major"] = major[:80]
    degree = _clean_degree(data.get("degree_type"))
    if degree:
        prefill["degree_type"] = degree
    subjects = _clean_string_list(data.get("subjects"))
    if subjects:
        prefill["subjects"] = subjects
    enroll = _clean_enroll_count(data.get("enroll_count"))
    if enroll is not None:
        prefill["enroll_count"] = enroll
    ratio = _clean_ratio(data.get("recommend_ratio"))
    if ratio is not None:
        prefill["recommend_ratio"] = ratio
    scores = _clean_past_scores(data.get("past_scores"))
    if scores:
        prefill["past_scores"] = scores
    books = _clean_string_list(data.get("books"))
    if books:
        prefill["books"] = books
    return prefill, round(len(prefill) / SCHOOL_PREFILL_FIELDS, 4)


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
        self._provider_host = provider_host
        self._grader = (
            ManagerGrader(provider_host, self.model_for_task, config.grading_start_level)
            if provider_host is not None
            else None
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
            order_by="created_at DESC, id",
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
            order_by="created_at DESC, id",
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
        self._store.update("attempt", attempt_id, self._grading_columns(result))
        if not result.ok:
            code = "MODEL_TIMEOUT" if result.fail_reason == "MODEL_TIMEOUT" else "MODEL_OUTPUT_INVALID"
            raise CampusError(code, f"批改失败（{result.fail_reason}）")
        body = self.attempt(attempt_id)
        body["pending_grading"] = True
        return body

    def attempt(self, attempt_id: str) -> dict[str, Any]:
        """One attempt body, or `ATTEMPT_NOT_FOUND`."""
        row = self._store.get("attempt", attempt_id)
        if row is None:
            raise CampusError("ATTEMPT_NOT_FOUND", f"作答记录不存在：{attempt_id}")
        return attempt_payload(models.Attempt.from_row(row))

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
            order_by="scheduled_date, priority, created_at, id",
        )
        return [task_payload(models.PlanTask.from_row(row)) for row in rows]

    # -- G2/G3: board write-back and rescheduling ---------------------------

    def update_task(
        self,
        profile: models.ExamProfile,
        task: models.PlanTask,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Write a board drag back onto `plan_task` (G2, KY-03/ADR-11).

        Status changes must follow the PRD §6.4 machine (`TASK_TRANSITIONS`), anything else is
        `ILLEGAL_TRANSITION`; re-dating and re-prioritising are not status transitions and stay
        legal in every state. `board_card_id` is never written here — ADR-11 reserves it for a
        possible V0.2 read-only sync.
        """
        del profile
        values: dict[str, Any] = {}
        if "scheduled_date" in patch:
            values["scheduled_date"] = patch["scheduled_date"]
        if "priority" in patch:
            values["priority"] = patch["priority"]
        if "status" in patch:
            status = str(patch["status"])
            if status != task.status and status not in TASK_TRANSITIONS[task.status]:
                raise CampusError(
                    "ILLEGAL_TRANSITION",
                    f"任务状态不可从 {task.status} 流转到 {status}",
                )
            values["status"] = status
            if status == models.PlanTaskStatus.DONE.value and task.status != status:
                values["completed_at"] = _utcnow_iso()
        if not values:
            return task_payload(task)
        self._store.update("plan_task", task.id, values)
        row = self._store.get("plan_task", task.id)
        return task_payload(models.PlanTask.from_row(row))

    def reschedule_plan(
        self,
        profile: models.ExamProfile,
        plan_id: str,
        new_exam_date: Optional[str],
    ) -> dict[str, Any]:
        """Spread the plan's open tasks over the new horizon (G3, KY-04/KY-13).

        Done and doing tasks keep their dates — "已完成任务不丢失" is the whole point of the
        feature — while todo tasks, in their original relative order, land evenly between today
        and the new exam date. A track whose completion runs ≥15 points behind the plan's
        expected pace gets its open tasks boosted to priority 1 (落后轨加权), and the horizon
        change is persisted on both the plan and the profile so the two never disagree.
        """
        row = self._store.get_scoped("study_plan", plan_id, profile.id)
        if row is None:
            raise CampusError("FORBIDDEN_PROFILE", f"学习计划不属于当前档案：{plan_id}")
        plan = models.StudyPlan.from_row(row)
        provided = str(new_exam_date or "").strip()
        end = _parse_exam_date(provided or str(profile.exam_date or "").strip())
        start = _utc_today()
        if (end - start).days < 1:
            raise CampusError("EXAM_DATE_REQUIRED", "考试日期需晚于今天")
        tasks = [
            models.PlanTask.from_row(item)
            for item in self._store.list_rows(
                "plan_task", profile_id=profile.id, where='"plan_id" = ?', params=[plan.id]
            )
        ]
        done = sum(1 for task in tasks if task.status == models.PlanTaskStatus.DONE.value)
        todo = sorted(
            (task for task in tasks if task.status == models.PlanTaskStatus.TODO.value),
            key=lambda task: (task.scheduled_date, task.priority, task.created_at or "", task.id),
        )
        lagging = self._lagging_tracks(plan, tasks)
        span = (end - start).days
        with self._store.transaction():
            if provided:
                self._store.update("exam_profile", profile.id, {"exam_date": end.isoformat()})
            self._store.update("study_plan", plan.id, {"end_date": end.isoformat()})
            for index, task in enumerate(todo):
                offset = round(index * span / (len(todo) - 1)) if len(todo) > 1 else 0
                values: dict[str, Any] = {
                    "scheduled_date": (start + timedelta(days=offset)).isoformat()
                }
                if task.subject in lagging and task.priority != 1:
                    values["priority"] = 1
                self._store.update("plan_task", task.id, values)
        return {"rescheduled": len(todo), "preserved_done": done}

    # -- F5: plan generation ------------------------------------------------

    async def generate_plan(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Lay out the road to the exam date as weekly plus daily tasks (F5).

        The structure is code-owned so the acceptance invariants of 07 §4 T11 cannot be broken
        by a bad model day: every declared track gets exactly one weekly task per week from
        today to the exam date (周级任务数 = 周数，无空轨), and every day gets one daily task
        rotating through the tracks. The model only contributes the weekly themes — unusable
        output degrades to the deterministic titles instead of failing, while a missing model
        or a failed call is refused with the documented codes of 03 §4.4.
        """
        start = _utc_today()
        exam = self._plan_exam_date(profile)
        days = (exam - start).days
        if days < 1:
            raise CampusError("EXAM_DATE_REQUIRED", "考试日期需晚于今天")
        plan_tracks = self._plan_tracks(profile)
        weeks = -(-days // 7)
        themes = await self._weekly_themes(profile, plan_tracks, weeks)
        daily_minutes = int(profile.daily_minutes or DEFAULT_DAILY_MINUTES)
        plan_id = self._store.insert(
            "study_plan",
            {
                "profile_id": profile.id,
                "track": models.PlanTrack.OVERALL.value,
                "start_date": start.isoformat(),
                "end_date": exam.isoformat(),
                "goal_desc": f"目标 {profile.target_score} 分" if profile.target_score else "",
                "source": models.PlanSource.AI_GENERATED.value,
            },
        )
        with self._store.transaction():
            for track in plan_tracks:
                for week in range(weeks):
                    stage = _stage_for_week(week, weeks)
                    goals = themes.get(track) or ()
                    title = (
                        goals[week % len(goals)]
                        if goals
                        else f"{_track_label(track)}·第{week + 1}周（{PLAN_STAGE_LABELS[stage]}）"
                    )
                    self._store.insert(
                        "plan_task",
                        {
                            "plan_id": plan_id,
                            "profile_id": profile.id,
                            "title": title,
                            "subject": track,
                            "scheduled_date": (
                                start + timedelta(days=7 * week)
                            ).isoformat(),
                            "detail": f"{PLAN_STAGE_LABELS[stage]}阶段 · 第 {week + 1}/{weeks} 周",
                            "est_minutes": daily_minutes,
                            "priority": PLAN_PRIORITY_BY_STAGE[stage],
                            "status": models.PlanTaskStatus.TODO.value,
                        },
                    )
            for day in range(days):
                track = plan_tracks[day % len(plan_tracks)]
                stage = _stage_for_week(day // 7, weeks)
                self._store.insert(
                    "plan_task",
                    {
                        "plan_id": plan_id,
                        "profile_id": profile.id,
                        "title": f"{_track_label(track)}·每日练习",
                        "subject": track,
                        "scheduled_date": (start + timedelta(days=day)).isoformat(),
                        "detail": f"{PLAN_STAGE_LABELS[stage]}阶段每日任务",
                        "est_minutes": daily_minutes,
                        "priority": 2,
                        "status": models.PlanTaskStatus.TODO.value,
                    },
                )
        return {
            "plan_id": plan_id,
            "task_count": weeks * len(plan_tracks) + days,
            "first_date": start.isoformat(),
        }

    # -- G4: progress overview ----------------------------------------------

    def progress(self, profile: models.ExamProfile) -> dict[str, Any]:
        """The four-track progress overview (G4, KY-11).

        Completion aggregates over `plan_task.subject`; the streak and the heatmap read only
        `completed_at` — the timestamp G2 actually writes when a task reaches done — so the
        overview can never claim a completion the board did not record.
        """
        tasks = [
            models.PlanTask.from_row(row)
            for row in self._store.list_rows("plan_task", profile_id=profile.id)
        ]
        totals: dict[str, list[int]] = {}
        completed: dict[str, int] = {}
        for task in tasks:
            entry = totals.setdefault(task.subject, [0, 0])
            entry[1] += 1
            if task.status == models.PlanTaskStatus.DONE.value:
                entry[0] += 1
                if task.completed_at:
                    day = str(task.completed_at)[:10]
                    completed[day] = completed.get(day, 0) + 1
        by_track = {
            subject: {
                "done": entry[0],
                "total": entry[1],
                "rate": round(entry[0] / entry[1], 4) if entry[1] else 0.0,
            }
            for subject, entry in sorted(totals.items())
        }
        heatmap = [{"date": day, "count": completed[day]} for day in sorted(completed)]
        return {
            "by_track": by_track,
            "streak_days": self._streak_days(completed),
            "heatmap": heatmap,
        }

    # -- G5/G6: weekly reports ----------------------------------------------

    def generate_weekly_report(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Aggregate the running ISO week into the fixed five-section report (G5, KY-12).

        Deliberately model-free: 03 §4.7 registers only `NO_TASK_DATA` for this endpoint, and
        the 05 §4.7 section structure is fully derivable from stored data — the AI-authored
        variant arrives through T13's automation template, not here. Regenerating the same week
        upserts (02 §4.18 一周一报) instead of stacking a second row.
        """
        today = _utc_today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        tasks = [
            models.PlanTask.from_row(row)
            for row in self._store.list_rows("plan_task", profile_id=profile.id)
        ]
        if not tasks:
            raise CampusError("NO_TASK_DATA", "暂无任务数据，无法生成周报")
        daily_minutes = int(profile.daily_minutes or DEFAULT_DAILY_MINUTES)
        week_tasks = [
            task
            for task in tasks
            if week_start.isoformat() <= task.scheduled_date <= week_end.isoformat()
        ]
        totals: dict[str, list[int]] = {}
        buckets: dict[str, list[models.PlanTask]] = {}
        for task in week_tasks:
            entry = totals.setdefault(task.subject, [0, 0])
            entry[1] += 1
            if task.status == models.PlanTaskStatus.DONE.value:
                entry[0] += 1
                continue
            reason = (
                "卡住了"
                if task.status == models.PlanTaskStatus.DOING.value
                else "拖了"
                if task.scheduled_date < today.isoformat()
                else "超量"
                if (task.est_minutes or 0) > daily_minutes
                else "计划内"
            )
            buckets.setdefault(reason, []).append(task)
        done = sum(entry[0] for entry in totals.values())
        total = sum(entry[1] for entry in totals.values())
        overall = round(done / total, 4) if total else 0.0
        completion_rate: dict[str, Any] = {"overall": overall}
        for subject, entry in sorted(totals.items()):
            completion_rate[subject] = round(entry[0] / entry[1], 4) if entry[1] else 0.0
        plan = self._latest_plan(profile.id)
        expected = self._expected_progress(plan) if plan is not None else None
        if expected is None:
            expected = overall
        lagging = {
            subject
            for subject, entry in totals.items()
            if entry[1] and entry[0] / entry[1] <= expected - PLAN_LAG_THRESHOLD
        }
        top_points = self._week_top_mistake_points(profile.id, week_start, week_end)
        streak = self._streak_days(self._completion_days(tasks))
        exam_days = self._days_until_exam(profile, today)
        suggestion = self._next_week_suggestion(
            today, tasks, buckets, lagging, top_points
        )
        content_md = self._weekly_markdown(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            completion_rate=completion_rate,
            totals=totals,
            buckets=buckets,
            overdue=[
                task
                for task in tasks
                if task.status == models.PlanTaskStatus.TODO.value
                and task.scheduled_date < week_start.isoformat()
            ],
            streak=streak,
            exam_days=exam_days,
            top_points=top_points,
            lagging=lagging,
            expected=expected,
            suggestion=suggestion,
        )
        values = {
            "completion_rate": _encode(completion_rate),
            "top_mistake_points": _encode(top_points),
            "content_md": content_md,
            "suggestion": suggestion,
        }
        existing = self._store.query_one(
            'SELECT "id" FROM "weekly_report" WHERE "profile_id" = ? AND "week_start" = ?',
            (profile.id, week_start.isoformat()),
        )
        if existing is not None:
            report_id = str(existing["id"])
            self._store.update("weekly_report", report_id, values)
        else:
            report_id = self._store.insert(
                "weekly_report",
                {
                    "profile_id": profile.id,
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    **values,
                },
            )
        row = self._store.get("weekly_report", report_id)
        return weekly_report_payload(models.WeeklyReport.from_row(row))

    def list_weekly_reports(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Every stored weekly report, newest week first (G6)."""
        rows = self._store.list_rows(
            "weekly_report", profile_id=profile.id, order_by="week_start DESC"
        )
        return {
            "items": [
                weekly_report_payload(models.WeeklyReport.from_row(row)) for row in rows
            ]
        }

    # -- G7-G9: the target school profile ------------------------------------

    def get_school_profile(self, profile: models.ExamProfile) -> dict[str, Any]:
        """The school card, or an empty `id=None` shell before the first save (G7, KY-14).

        03 §4.7 registers no error for G7, so an absent card is an empty card: the settings
        panel renders the blank form and the first PATCH (G8) creates the row.
        """
        row = self._store.query_one(
            'SELECT * FROM "school_profile" WHERE "profile_id" = ?', (profile.id,)
        )
        if row is None:
            shell = school_profile_payload(models.SchoolProfile(id="", profile_id=profile.id))
            shell["id"] = None
            return shell
        return school_profile_payload(models.SchoolProfile.from_row(row))

    def update_school_profile(
        self, profile: models.ExamProfile, patch: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Upsert the school card from a partial body (G8, KY-14)."""
        values: dict[str, Any] = {}
        for name in SCHOOL_PROFILE_MUTABLE_FIELDS:
            if name not in patch:
                continue
            value = patch[name]
            if name in JSON_SCHOOL_FIELDS:
                value = _encode(value or [])
            values[name] = value
        row = self._store.query_one(
            'SELECT "id" FROM "school_profile" WHERE "profile_id" = ?', (profile.id,)
        )
        if row is None:
            self._store.insert("school_profile", {"profile_id": profile.id, **values})
        elif values:
            self._store.update("school_profile", str(row["id"]), values)
        return self.get_school_profile(profile)

    async def extract_school_profile(
        self, profile: models.ExamProfile, text: str
    ) -> dict[str, Any]:
        """Pull a school-card prefill out of pasted admission text (G9, KY-14).

        Same model chain as F5 (`_complete_json`): a configured model is required, a failed
        call is the documented `MODEL_TIMEOUT`, and a model answer that parses to nothing
        useful simply yields an empty prefill — the user's confirmation click, not the model,
        is what writes the card.
        """
        cleaned = _clean_text(text)
        if not cleaned:
            raise CampusError("PARSE_ERROR", "粘贴内容为空")
        data = await self._complete_json(
            models.task_for_kind("explain"),
            system=(
                "你是招生简章信息抽取助手。从简章原文中抽取目标院校信息。"
                "只输出一个 JSON 对象，schema："
                '{"school": "...", "major": "...", "degree_type": "academic|professional", '
                '"subjects": ["科目"], "enroll_count": 0, "recommend_ratio": 0.0, '
                '"past_scores": [{"year": 2025, "line": 350}], "books": ["参考书"]}，'
                "取不到的键直接省略，不要编造，不要输出任何其他文字。"
            ),
            user=f"简章原文：\n{cleaned[:6000]}",
        )
        prefill, confidence = school_prefill(data)
        return {"prefill": prefill, "confidence": confidence}

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _completion_days(tasks: list[models.PlanTask]) -> dict[str, int]:
        """Completions per day, counted only where `completed_at` actually says so."""
        days: dict[str, int] = {}
        for task in tasks:
            if task.status == models.PlanTaskStatus.DONE.value and task.completed_at:
                day = str(task.completed_at)[:10]
                days[day] = days.get(day, 0) + 1
        return days

    @staticmethod
    def _streak_days(completed: Mapping[str, int]) -> int:
        """Consecutive days with a completion, counted back from today or yesterday."""
        day = _utc_today()
        if day.isoformat() not in completed:
            day -= timedelta(days=1)
        streak = 0
        while day.isoformat() in completed:
            streak += 1
            day -= timedelta(days=1)
        return streak

    @staticmethod
    def _days_until_exam(profile: models.ExamProfile, today: date) -> Optional[int]:
        raw = str(profile.exam_date or "").strip()
        if not raw:
            return None
        try:
            return (date.fromisoformat(raw) - today).days
        except ValueError:
            return None

    def _latest_plan(self, profile_id: str) -> Optional[models.StudyPlan]:
        rows = self._store.list_rows(
            "study_plan", profile_id=profile_id, order_by="created_at DESC, id", limit=1
        )
        return models.StudyPlan.from_row(rows[0]) if rows else None

    def _week_top_mistake_points(
        self, profile_id: str, week_start: date, week_end: date
    ) -> list[dict[str, Any]]:
        """Mistake points entered this week that showed up at least twice (05 §4.7 §3)."""
        counts: dict[str, int] = {}
        for row in self._store.list_rows("mistake_book", profile_id=profile_id):
            entry = models.MistakeBookEntry.from_row(row)
            created = str(entry.created_at or "")[:10]
            if not week_start.isoformat() <= created <= week_end.isoformat():
                continue
            key = (
                f"point:{entry.point_id}"
                if entry.point_id
                else f"subject:{entry.subject}"
            )
            counts[key] = counts.get(key, 0) + 1
        items: list[dict[str, Any]] = []
        for key, count in counts.items():
            if count < 2:
                continue
            kind, _, value = key.partition(":")
            point_id: Optional[str] = None
            title = value
            if kind == "point":
                point_id = value
                row = self._store.get_scoped("knowledge_point", value, profile_id)
                if row is not None:
                    title = str(row["title"])
            items.append({"point_id": point_id, "title": title, "count": count})
        items.sort(key=lambda item: (-int(item["count"]), str(item["title"])))
        return items[:5]

    @staticmethod
    def _minutes_of(tasks: list[models.PlanTask]) -> int:
        return sum(int(task.est_minutes or 30) for task in tasks)

    @staticmethod
    def _next_week_suggestion(
        today: date,
        tasks: list[models.PlanTask],
        buckets: Mapping[str, list[models.PlanTask]],
        lagging: set[str],
        top_points: list[dict[str, Any]],
    ) -> str:
        """Up to five concrete, time-estimated actions for next week (05 §4.7 §5)."""
        messages: list[str] = []
        overdue = [
            task
            for task in tasks
            if task.status == models.PlanTaskStatus.TODO.value
            and task.scheduled_date < today.isoformat()
        ]
        if overdue:
            messages.append(
                f"先补做 {len(overdue)} 个拖期任务（约 {CampusService._minutes_of(overdue)} 分钟），"
                "别让旧任务滚雪球。"
            )
        stuck = buckets.get("卡住了", [])
        if stuck:
            messages.append(
                f"推进 {len(stuck)} 个卡住的任务（约 {CampusService._minutes_of(stuck)} 分钟），"
                "从最小的一步重启。"
            )
        if lagging:
            labels = "、".join(_track_label(subject) for subject in sorted(lagging))
            messages.append(
                f"{labels} 完成率落后计划 15% 以上，下周给这些轨加权，优先安排其任务。"
            )
        if top_points:
            names = "、".join(str(item["title"]) for item in top_points[:3])
            messages.append(f"重做高频错题知识点：{names}（约 30 分钟）。")
        pending = buckets.get("计划内", [])
        if pending:
            messages.append(
                f"按期推进 {len(pending)} 个计划内任务"
                f"（约 {CampusService._minutes_of(pending)} 分钟）。"
            )
        if not messages:
            messages.append("本周任务已全部完成，下周从新一周的周计划开始。")
        return "\n".join(
            f"{index}. {message}" for index, message in enumerate(messages[:5], start=1)
        )

    def _weekly_markdown(
        self,
        *,
        week_start: str,
        week_end: str,
        completion_rate: Mapping[str, Any],
        totals: Mapping[str, list[int]],
        buckets: Mapping[str, list[models.PlanTask]],
        overdue: list[models.PlanTask],
        streak: int,
        exam_days: Optional[int],
        top_points: list[dict[str, Any]],
        lagging: set[str],
        expected: float,
        suggestion: str,
    ) -> str:
        """Render the fixed five-section report of 05 §4.7 as exportable markdown."""
        lines = [f"# 周报（{week_start} ~ {week_end}）", "", "## 一、总览"]
        overall = float(completion_rate.get("overall", 0.0))
        track_summary = "、".join(
            f"{_track_label(subject)} {float(completion_rate.get(subject, 0.0)):.0%}"
            for subject in sorted(totals)
        )
        lines.append(f"- 本周任务完成率：整体 {overall:.0%}（{track_summary}）")
        lines.append(f"- 连续打卡天数：{streak} 天")
        lines.append(
            f"- 距考试天数：{exam_days} 天"
            if exam_days is not None
            else "- 距考试天数：未设置考试日期"
        )
        lines += ["", "## 二、各轨明细"]
        if totals:
            for subject, entry in sorted(totals.items()):
                parts = [
                    f"{len(items)} 个{reason}"
                    for reason in ("拖了", "卡住了", "超量", "计划内")
                    if (items := [t for t in buckets.get(reason, []) if t.subject == subject])
                ]
                leftover = sum(1 for task in overdue if task.subject == subject)
                if leftover:
                    parts.append(f"本周之前遗留 {leftover} 个拖了的任务")
                lines.append(
                    f"- {_track_label(subject)}：完成 {entry[0]} / 共 {entry[1]}"
                    + (f"；未完成 " + "、".join(parts) if parts else "")
                )
        else:
            lines.append("- 本周无排期任务。")
        lines += ["", "## 三、新增错题 TOP 知识点"]
        if top_points:
            lines += [f"- {item['title']} ×{item['count']}" for item in top_points]
        else:
            lines.append("- 本周暂无出现 ≥2 次的错题知识点。")
        lines += ["", "## 四、落后预警"]
        if lagging:
            for subject in sorted(lagging):
                lines.append(
                    f"- 【落后】{_track_label(subject)}：本周完成率落后计划 {expected:.0%} 达 "
                    "15 个百分点以上，建议使用「一键重排」调整计划（已完成任务保留）。"
                )
        else:
            lines.append("- 各轨进度均未落后计划 15% 以上。")
        lines += ["", "## 五、下周建议", suggestion]
        return "\n".join(lines)

    # -- internals (plan domain) -------------------------------------------

    def _plan_exam_date(self, profile: models.ExamProfile) -> date:
        raw = str(profile.exam_date or "").strip()
        if not raw:
            raise CampusError("EXAM_DATE_REQUIRED", "请先设置考试日期")
        return _parse_exam_date(raw)

    def _lagging_tracks(
        self, plan: models.StudyPlan, tasks: list[models.PlanTask]
    ) -> set[str]:
        """Tracks whose completion runs ≥15 points behind the plan's expected pace (KY-13).

        The expected pace is how far through the plan's own start→end span today sits; when the
        plan carries no usable span the overall completion rate stands in, so a fresh plan never
        flags anything and a half-finished one flags the genuinely neglected tracks.
        """
        total_by_track: dict[str, int] = {}
        done_by_track: dict[str, int] = {}
        for task in tasks:
            total_by_track[task.subject] = total_by_track.get(task.subject, 0) + 1
            if task.status == models.PlanTaskStatus.DONE.value:
                done_by_track[task.subject] = done_by_track.get(task.subject, 0) + 1
        expected = self._expected_progress(plan)
        if expected is None:
            done = sum(done_by_track.values())
            total = sum(total_by_track.values())
            expected = done / total if total else 0.0
        threshold = expected - PLAN_LAG_THRESHOLD
        return {
            subject
            for subject, total in total_by_track.items()
            if total and done_by_track.get(subject, 0) / total <= threshold
        }

    @staticmethod
    def _expected_progress(plan: models.StudyPlan) -> Optional[float]:
        try:
            start = date.fromisoformat(str(plan.start_date))
            end = date.fromisoformat(str(plan.end_date))
        except (TypeError, ValueError):
            return None
        span = (end - start).days
        if span <= 0:
            return None
        elapsed = (_utc_today() - start).days
        return min(1.0, max(0.0, elapsed / span))

    def _plan_tracks(self, profile: models.ExamProfile) -> tuple[str, ...]:
        """The tracks this profile's plan covers, read from the TrackSpec (01 §3.2).

        The profile's own `subjects` narrow and reorder the station skeleton — a "不考数学 +
        两门专业课" plan covers three tracks while the default covers four, which is exactly
        the heterogeneity KY-02's acceptance asks for. Values outside the skeleton are ignored
        (never silently widened), and an empty skeleton degrades to the single `overall` track
        so every station can still produce a plan.
        """
        allowed = tracks.spec_for(profile.track_type).subject_skeleton
        chosen: list[str] = []
        for subject in _decode(profile.subjects, []):
            value = str(subject)
            if value in allowed and value not in chosen:
                chosen.append(value)
        return tuple(chosen) or (tuple(allowed) or (models.PlanTrack.OVERALL.value,))

    async def _weekly_themes(
        self, profile: models.ExamProfile, plan_tracks: tuple[str, ...], weeks: int
    ) -> dict[str, list[str]]:
        """Ask the model for per-track weekly goals, keeping only the well-formed part.

        Every failure mode of the model (absent, unreachable, unparseable, wrong shape) ends in
        an empty or partial dict: the caller falls back to its deterministic titles per track,
        so the plan's structure never depends on this call succeeding.
        """
        data = await self._complete_json(
            models.task_for_kind("question"),
            system=(
                "你是备考规划助手。依据学生档案为每条科目轨输出每周学习主题。"
                "只输出一个 JSON 对象，schema："
                '{"tracks": {"<科目>": {"weekly_goals": ["第1周主题", "..."]}}}，'
                "每条轨的 weekly_goals 数量必须等于给定周数，不要输出任何其他文字。"
            ),
            user=(
                f"考试日期：{profile.exam_date}；距今天共 {weeks} 周；"
                f"每日可用时长 {profile.daily_minutes} 分钟；"
                f"科目轨：{'、'.join(_track_label(track) for track in plan_tracks)}。"
                f"请为每条轨给出 {weeks} 个每周主题。"
            ),
        )
        if not data:
            return {}
        raw_tracks = data.get("tracks")
        if not isinstance(raw_tracks, Mapping):
            return {}
        themes: dict[str, list[str]] = {}
        for track in plan_tracks:
            entry = raw_tracks.get(track)
            if not isinstance(entry, Mapping):
                continue
            goals = entry.get("weekly_goals")
            if not isinstance(goals, list):
                continue
            cleaned = [str(goal).strip()[:80] for goal in goals if str(goal).strip()]
            if cleaned:
                themes[track] = cleaned
        return themes

    async def _complete_json(
        self, task: str, *, system: str, user: str
    ) -> Optional[dict[str, Any]]:
        """One structured-output model call, refused or timed out with documented codes.

        The blocking `provider.complete` runs in a thread (the GradingEngine pattern of 06
        §2.2) under a hard `asyncio.wait_for`; any provider failure surfaces as the retryable
        `MODEL_TIMEOUT` of 03 §6 rather than an undocumented error. Output that fails
        `extract_json` comes back as `None` — a parsing failure is the caller's degrade path,
        not an exception (F5/G9 list no `MODEL_OUTPUT_INVALID`).
        """
        model = self.model_for_task(task)
        provider = getattr(self._provider_host, "provider", None)
        if model is None or provider is None:
            raise CampusError("MODEL_NOT_CONFIGURED")

        def call() -> str:
            turn = provider.complete(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                timeout=PROVIDER_TIMEOUT_S,
            )
            return str(getattr(turn, "text", "") or "")

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(call), timeout=PROVIDER_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            raise CampusError("MODEL_TIMEOUT", "模型调用超时") from None
        except Exception as exc:
            raise CampusError("MODEL_TIMEOUT", f"模型调用失败（{type(exc).__name__}）") from exc
        data, _reason = extract_json(text)
        return data

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

    def _grading_columns(self, result: GradeResult) -> dict[str, Any]:
        """Map a `GradeResult` onto the attempt columns and its `grading_json` whitelist.

        The whitelist is T07 §6-4: the server-side fields (`ok`, `model_used`, `usage`,
        `fail_reason`) stay out, `degrade_level` gets its own column, and the degradation trace
        is kept under `_degrade_trace`. `score` carries the rubric band on the 15-point scale of
        06 §2.1; a scoring-point kind has no band, so both score columns stay empty and the
        detail lives in `grading_json.scoring_points`.
        """
        score = None if result.band is None else float(result.band)
        return {
            "grading_json": json.dumps(
                {
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
