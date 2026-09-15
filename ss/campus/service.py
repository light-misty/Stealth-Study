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
from pathlib import Path
from typing import Any, Mapping, Optional

from ..secrets import state_dir
from . import models
from .config import DEFAULT_DAILY_MINUTES
from .grading import GradeRequest, GradeResult, GradingEngine, extract_json
from .library import FAIL_NO_TEXT_LAYER
from .rubrics import CERT_SCORING_POINTS_SPEC, CET_ESSAY_RUBRIC, CET_TRANSLATION_RUBRIC
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

POINT_FIELDS: tuple[str, ...] = ("title", "desc", "order_index", "parent_id")

TREE_MAX_CHARS = 20000
TREE_MAX_DEPTH = 3

TREE_SYSTEM_PROMPT = (
    "你是证书教研员。把用户给出的考纲文本抽成「章-节-点」三层知识点树。"
    "节点名使用考纲原文措辞，不改写、不缩写；层级以考纲编号体系（一/（一）/1.）为准；"
    "拿不准归属的点挂到最近的章节并标记 ambiguous 为 true，宁缺毋滥。"
    "只输出一个 JSON 对象，不要任何其他文字，schema："
    '{"sections": [{"title": "章", "children": [{"title": "节", "children": [{"title": "点"}]}]}]}'
)

_MASTERY_LEVELS: frozenset[str] = frozenset(item.value for item in models.MasteryLevel)
_MASTERY_WEAK_ORDER: Mapping[str, int] = {
    models.MasteryLevel.UNKNOWN.value: 0,
    models.MasteryLevel.FUZZY.value: 1,
}

MASTERY_DOWNGRADE: Mapping[str, str] = {
    models.MasteryLevel.MASTERED.value: models.MasteryLevel.FUZZY.value,
    models.MasteryLevel.FUZZY.value: models.MasteryLevel.UNKNOWN.value,
    models.MasteryLevel.UNKNOWN.value: models.MasteryLevel.UNKNOWN.value,
}

GENERAL_SUBJECT = "general"

DIMENSION_LABELS: Mapping[str, str] = {"content": "内容", "structure": "结构", "language": "语言"}
DIMENSION_MAX_SCORE = 5


@dataclass(frozen=True)
class RubricSpec:
    """One named rubric of 05 §5: the label the API reports and the prompt text."""

    name: str
    text: str


RUBRICS: Mapping[str, RubricSpec] = {
    "cet_essay": RubricSpec("四六级短文写作评分标准", CET_ESSAY_RUBRIC),
    "cet_translation": RubricSpec("四六级段落翻译评分标准", CET_TRANSLATION_RUBRIC),
    "cert_scoring_points": RubricSpec("主观题评分点三态输出契约", CERT_SCORING_POINTS_SPEC),
}

DEFAULT_RUBRIC_BY_KIND: Mapping[str, str] = {
    "essay": "cet_essay",
    "translation": "cet_translation",
    "short_answer": "cert_scoring_points",
    "essay_material": "cert_scoring_points",
    "lesson_plan": "cert_scoring_points",
    "practical": "cert_scoring_points",
}

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
        with self._store.transaction():
            self._store.update("attempt", attempt_id, self._grading_columns(result))
            self._apply_mastery_downgrade(profile.id, question, result)
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

    # -- C1: the shared grading endpoint (03 §4.3) --------------------------

    async def grade(
        self,
        profile: models.ExamProfile,
        question: Optional[models.QuestionBankItem],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Grade one subjective answer through the shared chain (C1, CERT-07/14).

        The attempt row is written first and survives a model failure — exactly the E5
        semantics — and the CERT-15 mastery downgrade runs in the same transaction as the
        grading write, so the response and the side effect land together.
        """
        kind = str(payload["kind"])
        if self.model_for_task(models.task_for_kind(kind)) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        rubric_id = payload.get("rubric_id")
        if rubric_id is not None and rubric_id not in RUBRICS:
            raise CampusError("RUBRIC_NOT_FOUND", f"评分标准不存在：{rubric_id}")
        chosen = RUBRICS[rubric_id if rubric_id is not None else DEFAULT_RUBRIC_BY_KIND[kind]]
        custom = str(payload.get("custom_rubric") or "").strip() or None
        rubric_text = custom if custom is not None else chosen.text
        rubric_name = (
            chosen.name
            if custom is None or rubric_id is not None
            else "自定义评分标准"
        )
        answer = str(payload["answer"])
        attempt_id = self._insert_attempt(
            profile,
            question,
            answer,
            models.SessionType.GRADING.value,
            None,
        )
        result = await self._require_grader().grade(
            GradeRequest(
                profile_id=profile.id,
                track_type=profile.track_type,
                kind=kind,
                question=question.stem if question is not None else "",
                answer=answer,
                rubric_id=rubric_id,
                custom_rubric=rubric_text,
            )
        )
        with self._store.transaction():
            self._store.update("attempt", attempt_id, self._grading_columns(result))
            self._apply_mastery_downgrade(profile.id, question, result)
        if not result.ok:
            code = "MODEL_TIMEOUT" if result.fail_reason == "MODEL_TIMEOUT" else "MODEL_OUTPUT_INVALID"
            raise CampusError(code, f"批改失败（{result.fail_reason}）")
        return self._grading_response(attempt_id, result, rubric_name)

    def _grading_response(
        self, attempt_id: str, result: GradeResult, rubric_name: str
    ) -> dict[str, Any]:
        """The 03 §4.3 GradeResult view plus the attempt id and the raw grading columns."""
        attempt = self.attempt(attempt_id)
        return {
            "attempt_id": attempt_id,
            "degrade_level": result.degrade_level,
            "rubric": rubric_name,
            "dimensions": [
                {"name": DIMENSION_LABELS[name], "score": score, "max": DIMENSION_MAX_SCORE, "comment": ""}
                for name, score in result.dimension_scores.items()
            ],
            "errors": [
                {
                    "original": error.get("fragment", ""),
                    "suggestion": error.get("suggestion", ""),
                    "type": error.get("type", ""),
                    "offset": error.get("offset"),
                }
                for error in result.errors
            ],
            "model_answer_outline": result.model_answer_outline,
            "model_used": result.model_used,
            "notice": result.notice,
            "band": result.band,
            "score": attempt["score"],
            "max_score": attempt["max_score"],
            "scoring_points": result.scoring_points,
            "grading_json": attempt["grading_json"],
        }

    def _apply_mastery_downgrade(
        self,
        profile_id: str,
        question: Optional[models.QuestionBankItem],
        result: GradeResult,
    ) -> None:
        """CERT-15: one fully missed scoring point drags the point's mastery down a state.

        Runs inside the caller's transaction together with the attempt write, so a grading
        that fails to land never leaves the tree marked "待加强" behind.
        """
        if question is None or not question.point_id or not result.scoring_points:
            return
        misses = [
            str(point["point"])
            for point in result.scoring_points
            if point.get("status") == "miss"
        ]
        if not misses:
            return
        point_id = str(question.point_id)
        row = self._mastery_row(profile_id, point_id, None)
        level = row["level"] if row is not None else models.MasteryLevel.UNKNOWN.value
        next_level = MASTERY_DOWNGRADE.get(level, models.MasteryLevel.UNKNOWN.value)
        evidence = "未命中得分点：" + "；".join(misses)
        if row is None:
            self._store.insert(
                "mastery",
                {
                    "profile_id": profile_id,
                    "point_id": point_id,
                    "level": next_level,
                    "evidence": evidence,
                },
            )
        else:
            self._store.update("mastery", row["id"], {"level": next_level, "evidence": evidence})

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

    # -- H1-H6: the knowledge tree and mastery (03 §4.8) --------------------

    def knowledge_tree(self, profile_id: str) -> dict[str, Any]:
        """The profile's tree as nested `KnowledgePointNode`s (H1).

        `question_count`/`mistake_count` are counted from their owning tables at request
        time — the tree endpoint is exactly where CERT-01 wants the truth, and maintained
        counters would go stale the moment any future writer forgets to bump them.
        """
        rows = self._store.list_rows(
            "knowledge_point", profile_id=profile_id, order_by="order_index, created_at, id"
        )
        question_counts = self._count_by_point("question_bank_item", profile_id)
        mistake_counts = self._count_by_point("mistake_book", profile_id)
        nodes: dict[str, dict[str, Any]] = {}
        links: list[tuple[str, Optional[str]]] = []
        roots: list[dict[str, Any]] = []
        for row in rows:
            point = models.KnowledgePoint.from_row(row)
            nodes[point.id] = {
                **asdict(point),
                "question_count": question_counts.get(point.id, 0),
                "mistake_count": mistake_counts.get(point.id, 0),
                "children": [],
            }
            links.append((point.id, point.parent_id))
        for point_id, parent_id in links:
            parent = nodes.get(parent_id) if parent_id else None
            if parent is None:
                roots.append(nodes[point_id])
            else:
                parent["children"].append(nodes[point_id])
        return {"roots": roots}

    def create_knowledge_point(
        self, profile_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create one manual point under an optional parent (H2)."""
        parent_id = self._require_point(profile_id, payload.get("parent_id"))
        point_id = self._store.insert(
            "knowledge_point",
            {
                "profile_id": profile_id,
                "title": str(payload["title"]).strip(),
                "parent_id": parent_id,
                "desc": payload.get("desc"),
                "order_index": int(payload.get("order_index") or 0),
                "source": models.KnowledgeSource.MANUAL.value,
            },
        )
        row = self._store.get("knowledge_point", point_id)
        return self._point_payload(row, *self._point_counts(profile_id, point_id))

    def update_knowledge_point(
        self,
        profile_id: str,
        point: models.KnowledgePoint,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Rename, reorder or re-parent one point (H3).

        A re-parent may never make the tree cyclic: a point cannot take itself or one of
        its descendants as the parent, which is refused before the write happens.
        """
        values = {key: patch[key] for key in POINT_FIELDS if key in patch}
        if "title" in values:
            values["title"] = str(values["title"]).strip()
        if "parent_id" in values and values["parent_id"] is not None:
            parent_id = self._require_point(profile_id, values["parent_id"])
            if parent_id == point.id or self._is_descendant(profile_id, point.id, parent_id):
                raise CampusError("ILLEGAL_TRANSITION", "父节点不能是自身或其后代")
            values["parent_id"] = parent_id
        if values:
            self._store.update("knowledge_point", point.id, values)
        row = self._store.get("knowledge_point", point.id)
        return self._point_payload(row, *self._point_counts(profile_id, point.id))

    def delete_knowledge_point(
        self, profile_id: str, point: models.KnowledgePoint
    ) -> dict[str, Any]:
        """Delete a point; its children are promoted to top level, its mastery rows go too (H3)."""
        children = self._store.list_rows(
            "knowledge_point", profile_id=profile_id, where='"parent_id" = ?', params=[point.id]
        )
        with self._store.transaction():
            for child in children:
                self._store.update("knowledge_point", child["id"], {"parent_id": None})
            self._store.delete_where("mastery", '"point_id" = ?', (point.id,))
            self._store.delete("knowledge_point", point.id)
        return {"deleted": True, "orphaned_children": len(children)}

    async def generate_knowledge_tree(
        self, profile: models.ExamProfile, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Extract the chapter-section-point tree from a syllabus (H4, CERT-02).

        The extraction discipline of 05 §4.8 travels as the system prompt; the model's
        JSON is validated and inserted as one transaction, so a malformed tree leaves
        nothing behind.
        """
        model = self.model_for_task(models.CampusTask.EXPLAIN.value)
        if model is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        text = self._tree_source_text(profile.id, payload)
        messages = [
            {"role": "system", "content": TREE_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        try:
            turn = await asyncio.to_thread(
                self._require_provider().complete,
                model=model,
                messages=messages,
                temperature=0,
                timeout=90,
            )
        except CampusError:
            raise
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower():
                raise CampusError("MODEL_TIMEOUT", "模型调用超时") from exc
            raise CampusError("MODEL_OUTPUT_INVALID", "模型调用失败") from exc
        data, _reason = extract_json(getattr(turn, "text", None))
        sections = self._tree_sections(data)
        with self._store.transaction():
            created, roots = self._insert_tree_sections(profile.id, sections)
        return {"created": created, "roots": roots}

    def set_mastery(self, profile_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """UPSERT one mastery row keyed by (profile, point, dimension) (H5)."""
        level = str(payload.get("level") or "")
        if level not in _MASTERY_LEVELS:
            raise CampusError("INVALID_LEVEL", f"掌握度取值非法：{level}")
        point_id = self._require_point(profile_id, payload.get("point_id"))
        dimension = payload.get("dimension")
        row = self._mastery_row(profile_id, point_id, dimension)
        if row is None:
            mastery_id = self._store.insert(
                "mastery",
                {
                    "profile_id": profile_id,
                    "level": level,
                    "point_id": point_id,
                    "dimension": dimension,
                },
            )
            row = self._store.get("mastery", mastery_id)
        else:
            self._store.update("mastery", row["id"], {"level": level})
            row = self._store.get("mastery", row["id"])
        return asdict(models.Mastery.from_row(row))

    def mastery_coverage(self, profile_id: str) -> dict[str, Any]:
        """The rated share of the tree plus the weakest rated points (H6, CERT-03)."""
        points = self._store.list_rows("knowledge_point", profile_id=profile_id)
        titles = {row["id"]: row["title"] for row in points}
        rated = [
            row
            for row in self._store.list_rows("mastery", profile_id=profile_id)
            if row["point_id"] in titles and row["dimension"] is None
        ]
        coverage = round(len(rated) / len(points), 2) if points else 0.0
        weak = sorted(
            (
                {
                    "point_id": row["point_id"],
                    "title": titles[row["point_id"]],
                    "level": row["level"],
                }
                for row in rated
                if row["level"] != models.MasteryLevel.MASTERED.value
            ),
            key=lambda item: (_MASTERY_WEAK_ORDER.get(item["level"], 0), item["title"]),
        )
        return {"coverage": coverage, "weak_top5": weak[:5]}

    # -- internals ---------------------------------------------------------

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
        question: Optional[models.QuestionBankItem],
        answer: str,
        session_type: str,
        mock_exam_id: Optional[str],
        *,
        values: Optional[Mapping[str, Any]] = None,
    ) -> str:
        row: dict[str, Any] = {
            "profile_id": profile.id,
            "track_type": profile.track_type,
            "subject": question.subject if question is not None else GENERAL_SUBJECT,
            "user_answer": answer,
            "question_id": question.id if question is not None else None,
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

    def _require_provider(self) -> Any:
        """The sidecar's `ProviderClient`, or `MODEL_NOT_CONFIGURED` (G-04's safe default)."""
        provider = (
            getattr(self._provider_host, "provider", None)
            if self._provider_host is not None
            else None
        )
        if provider is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        return provider

    def _count_by_point(self, table: str, profile_id: str) -> dict[str, int]:
        rows = self._store.query_all(
            f'SELECT "point_id", COUNT(*) AS n FROM "{table}" '
            'WHERE "profile_id" = ? AND "point_id" IS NOT NULL GROUP BY "point_id"',
            (profile_id,),
        )
        return {row["point_id"]: int(row["n"]) for row in rows}

    def _point_counts(self, profile_id: str, point_id: str) -> tuple[int, int]:
        questions = self._store.count(
            "question_bank_item", '"profile_id" = ? AND "point_id" = ?', (profile_id, point_id)
        )
        mistakes = self._store.count(
            "mistake_book", '"profile_id" = ? AND "point_id" = ?', (profile_id, point_id)
        )
        return questions, mistakes

    def _point_payload(
        self, row: Any, question_count: int, mistake_count: int
    ) -> dict[str, Any]:
        payload = asdict(models.KnowledgePoint.from_row(row))
        payload["question_count"] = question_count
        payload["mistake_count"] = mistake_count
        return payload

    def _is_descendant(
        self, profile_id: str, ancestor_id: str, candidate_id: str
    ) -> bool:
        parent_by_id = {
            row["id"]: row["parent_id"]
            for row in self._store.list_rows("knowledge_point", profile_id=profile_id)
        }
        current = parent_by_id.get(candidate_id)
        seen: set[str] = set()
        while current is not None and current not in seen:
            if current == ancestor_id:
                return True
            seen.add(current)
            current = parent_by_id.get(current)
        return False

    def _tree_source_text(self, profile_id: str, payload: Mapping[str, Any]) -> str:
        """The pasted text wins; otherwise the doc's chunks are joined in page order."""
        text = str(payload.get("text") or "").strip()
        if text:
            return text
        doc_id = str(payload.get("doc_id") or "")
        row = self._store.get_scoped("source_doc", doc_id, profile_id)
        if row is None:
            raise CampusError("DOC_NOT_FOUND", f"资料不存在：{doc_id}")
        chunks = self._store.list_rows(
            "doc_chunk",
            profile_id=profile_id,
            where='"doc_id" = ?',
            params=[doc_id],
            order_by="page_no, char_start, id",
        )
        if not chunks:
            doc = models.SourceDoc.from_row(row)
            if (
                doc.parse_status == models.ParseStatus.FAILED.value
                and doc.fail_reason == FAIL_NO_TEXT_LAYER
            ):
                raise CampusError("DOC_SCAN_EMPTY", "扫描件无可提取文字层，无法抽取知识树")
            raise CampusError("DOC_NOT_READY", "资料尚未解析完成，无法抽取知识树")
        return "\n".join(str(chunk["content"]) for chunk in chunks)[:TREE_MAX_CHARS]

    def _tree_sections(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
            raise CampusError("MODEL_OUTPUT_INVALID", "知识树输出无法解析")
        sections = [
            section
            for section in (self._tree_node(item) for item in data["sections"])
            if section is not None
        ]
        if not sections:
            raise CampusError("MODEL_OUTPUT_INVALID", "知识树输出为空")
        return sections

    def _tree_node(self, item: Any) -> Optional[dict[str, Any]]:
        """One validated node: a non-empty title plus its validated children, depth-capped."""
        if not isinstance(item, dict):
            return None
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        children = [
            child
            for child in (self._tree_node(raw) for raw in item.get("children") or [])
            if child is not None
        ]
        return {"title": title, "children": children}

    def _insert_tree_sections(
        self, profile_id: str, sections: list[dict[str, Any]]
    ) -> tuple[int, list[dict[str, Any]]]:
        created = 0
        roots: list[dict[str, Any]] = []
        for index, section in enumerate(sections):
            level_created, payload = self._insert_tree_level(
                profile_id, section, None, index, 1
            )
            created += level_created
            roots.append(payload)
        return created, roots

    def _insert_tree_level(
        self,
        profile_id: str,
        node: Mapping[str, Any],
        parent_id: Optional[str],
        order_index: int,
        depth: int,
    ) -> tuple[int, dict[str, Any]]:
        point_id = self._store.insert(
            "knowledge_point",
            {
                "profile_id": profile_id,
                "title": str(node["title"]),
                "parent_id": parent_id,
                "order_index": order_index,
                "source": models.KnowledgeSource.AI_GENERATED.value,
            },
        )
        created = 1
        children: list[dict[str, Any]] = []
        if depth < TREE_MAX_DEPTH:
            for index, child in enumerate(node.get("children") or []):
                level_created, payload = self._insert_tree_level(
                    profile_id, child, point_id, index, depth + 1
                )
                created += level_created
                children.append(payload)
        row = self._store.get("knowledge_point", point_id)
        payload = self._point_payload(row, 0, 0)
        payload["children"] = children
        return created, payload

    def _mastery_row(
        self, profile_id: str, point_id: Optional[str], dimension: Optional[str]
    ) -> Any:
        conditions = ['"profile_id" = ?']
        params: list[Any] = [profile_id]
        for column, value in (("point_id", point_id), ("dimension", dimension)):
            if value is None:
                conditions.append(f'"{column}" IS NULL')
            else:
                conditions.append(f'"{column}" = ?')
                params.append(value)
        return self._store.query_one(
            f'SELECT * FROM "mastery" WHERE {" AND ".join(conditions)}', params
        )
