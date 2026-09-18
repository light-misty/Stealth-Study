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
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..automation.models import Schedule, ScheduledTask
from ..memory import Scope
from ..secrets import state_dir
from . import automation_templates, models, reminders, review_scheduler, rubrics, store, tracks
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
from .library import FAIL_NO_TEXT_LAYER, CampusLibrary, LibraryError
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

REVIEW_SOURCE_TABLES: Mapping[str, str] = {
    models.ReviewItemType.MISTAKE.value: "mistake_book",
    models.ReviewItemType.VOCAB.value: "vocab_item",
    models.ReviewItemType.KNOWLEDGE_POINT.value: "knowledge_point",
}

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

EXPORT_FORMATS: tuple[str, ...] = ("md", "json", "csv")

EXPORT_TABLE_ORDER: tuple[str, ...] = (
    "exam_profile",
    "school_profile",
    "source_doc",
    "doc_chunk",
    "knowledge_point",
    "mastery",
    "study_plan",
    "plan_task",
    "vocab_item",
    "question_bank_item",
    "attempt",
    "mistake_book",
    "review_queue",
    "mock_exam",
    "assessment",
    "weekly_report",
    "cert_deadline",
    "app_state",
)

EXPORT_MEDIA_TYPES: Mapping[str, str] = {
    "md": "text/markdown",
    "json": "application/json",
    "csv": "text/csv",
}

BACKUP_KIND = "stealth-study-campus-backup"

EXPORT_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(?:md|json|csv)$")

EXPORT_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

CSV_ATTEMPT_COLUMNS: tuple[str, ...] = (
    "id",
    "created_at",
    "track_type",
    "subject",
    "question_id",
    "session_type",
    "mock_exam_id",
    "is_correct",
    "score",
    "max_score",
    "degrade_level",
    "model_used",
)

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


# -- B 组资料库：导入校验（03 §4.2 B1 与 attachments 同 10MB 上限）--------
LIBRARY_UPLOAD_SUFFIXES: frozenset[str] = frozenset({".pdf", ".md", ".txt"})
MAX_LIBRARY_UPLOAD_BYTES = 10 * 1024 * 1024
# 导入前必须留出的空闲余量：解析过程会再写一份切片与库文件，写满磁盘会让整台机器遭殃
MIN_LIBRARY_FREE_BYTES = 16 * 1024 * 1024

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
MISTAKE_FIELDS: tuple[str, ...] = ("attribution", "note", "resolved", "point_id")
_ATTRIBUTIONS: frozenset[str] = frozenset(item.value for item in models.Attribution)

# I1:03 §4.9 只列三台备考人设，顺序按轨道声明去重（cet → kaoyan → cert）。
CAMPUS_PERSONA_IDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        persona for spec in tracks.TRACKS.values() for persona in spec.default_personas
    )
)
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


NEW_WORD_LIMIT = 30
VOCAB_MASTERY_ALIASES: Mapping[str, str] = {
    "known": models.MasteryLevel.MASTERED.value,
    "mastered": models.MasteryLevel.MASTERED.value,
    "fuzzy": models.MasteryLevel.FUZZY.value,
    "unknown": models.MasteryLevel.UNKNOWN.value,
}

VOCAB_FIELDS: tuple[str, ...] = ("word", "phonetic", "meaning", "example")

MOCK_PAUSE_BUDGET_SECONDS = 180
MOCK_SECTIONS: tuple[str, ...] = ("listening", "reading", "writing_translation")
MOCK_STAGE_ORDER: tuple[str, ...] = (
    models.MockStage.WRITING.value,
    models.MockStage.LISTENING.value,
    models.MockStage.READING_TRANSLATION.value,
)
MOCK_STAGE_MINUTES: Mapping[str, int] = {
    models.MockStage.WRITING.value: 30,
    models.MockStage.LISTENING.value: 25,
    models.MockStage.READING_TRANSLATION.value: 70,
}
SUBJECT_STAGE: Mapping[str, str] = {
    models.Subject.WRITING.value: models.MockStage.WRITING.value,
    models.Subject.LISTENING.value: models.MockStage.LISTENING.value,
    models.Subject.READING.value: models.MockStage.READING_TRANSLATION.value,
    models.Subject.TRANSLATION.value: models.MockStage.READING_TRANSLATION.value,
}
SUBJECT_SECTION: Mapping[str, str] = {
    models.Subject.LISTENING.value: "listening",
    models.Subject.READING.value: "reading",
    models.Subject.WRITING.value: "writing_translation",
    models.Subject.TRANSLATION.value: "writing_translation",
}

_VOCAB_LABELS: Mapping[str, str] = {
    "word": "word",
    "单词": "word",
    "词": "word",
    "phonetic": "phonetic",
    "音标": "phonetic",
    "meaning": "meaning",
    "释义": "meaning",
    "example": "example",
    "例句": "example",
}
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


def vocab_payload(vocab: models.VocabItem) -> dict[str, Any]:
    """One word card; every column is scalar, so the body is the row itself (02 §4.11)."""
    return asdict(vocab)


def review_payload(item: models.ReviewItem) -> dict[str, Any]:
    """One queue row; every column is scalar, so the body is the row itself (02 §4.15)."""
    return asdict(item)


def mock_payload(mock: models.MockExam) -> dict[str, Any]:
    """One mock exam; every column is scalar, `locked_stages` stays its JSON string (02 §4.16)."""
    return asdict(mock)


def _parse_utc(value: str) -> datetime:
    """Parse a campus timestamp (`...Z`) into an aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _utcformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def parse_vocabulary(fmt: str, content: str) -> list[dict[str, str]]:
    """Parse an F8 word-list payload into `{word, phonetic, meaning, example}` rows.

    Two shapes, one vocabulary (03 §4.6 F8):
    * `md` — one word per line (PRD CET2 验收②), optionally `word|音标|释义|例句` with `|`;
    * `csv` — a header row using the same labels, then one word per row.

    Blank lines and `#` comments are skipped; anything else unusable raises `PARSE_ERROR` with the
    physical line number, and the whole payload is validated before the first insert.
    """
    if not isinstance(content, str) or not content.strip():
        raise CampusError("PARSE_ERROR", "导入内容为空", line=1)
    if fmt == "md":
        rows = _parse_markdown_vocabulary(content)
    elif fmt == "csv":
        rows = _parse_csv_vocabulary(content)
    else:
        raise CampusError("PARSE_ERROR", f"不支持的内容格式：{fmt}", line=1)
    if not rows:
        raise CampusError("PARSE_ERROR", "未解析到任何单词", line=1)
    return rows


def _parse_markdown_vocabulary(content: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for number, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = [cell.strip() for cell in _OPTION_SEPARATOR.split(line)]
        if len(cells) > len(VOCAB_FIELDS):
            raise CampusError("PARSE_ERROR", f"第 {number} 行字段过多：{line}", line=number)
        if not cells[0]:
            raise CampusError("PARSE_ERROR", f"第 {number} 行缺少单词", line=number)
        rows.append(dict(zip(VOCAB_FIELDS, cells)))
    return rows


def _parse_csv_vocabulary(content: str) -> list[dict[str, str]]:
    reader = csv.reader(io.StringIO(content))
    header = next(reader, None)
    if not header:
        raise CampusError("PARSE_ERROR", "导入内容为空", line=1)
    columns = [_VOCAB_LABELS.get(cell.strip()) for cell in header]
    if any(column is None for column in columns):
        raise CampusError("PARSE_ERROR", "第 1 行表头含未知字段", line=1)
    if len(set(columns)) != len(columns):
        raise CampusError("PARSE_ERROR", "第 1 行表头字段重复", line=1)
    if "word" not in columns:
        raise CampusError("PARSE_ERROR", "第 1 行表头缺少必填字段：word", line=1)
    rows: list[dict[str, str]] = []
    for row in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(header):
            raise CampusError("PARSE_ERROR", f"第 {line} 行列数与表头不一致", line=line)
        fields = {str(column): cell.strip() for column, cell in zip(columns, row)}
        if not fields.get("word"):
            raise CampusError("PARSE_ERROR", f"第 {line} 行缺少单词", line=line)
        rows.append(fields)
    return rows


def build_mnemonic_messages(vocab: models.VocabItem) -> list[dict[str, str]]:
    """The F9 助记 prompt — one line, no chatter (05 §3.1 技能包语气)."""
    system = (
        "你在为备考四六级的学生生成单词助记。只输出一句中文助记（拆词 / 谐音 / 词根任选其一），"
        "不超过 60 字，不要任何其他文字。"
    )
    detail = "、".join(
        part for part in (vocab.phonetic or "", vocab.meaning or "") if part
    )
    user = f"单词：{vocab.word}" + (f"（{detail}）" if detail else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


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


LIBRARY_QUESTION_SYSTEM_PROMPT = (
    "你是备考教研员。根据用户给出的资料片段或主题出题，题目必须能由给定材料作答，"
    "不要引入材料之外的事实；材料不足时降低题目难度而不是编造。"
    "只输出一个 JSON 对象，不要任何其他文字，schema："
    '{"items": [{"subject": "reading", "qtype": "single", "stem": "题干", '
    '"options": [{"key": "A", "text": "选项"}, {"key": "B", "text": "选项"}], "answer": "A"}]}'
)

DEFAULT_QUESTION_COUNT = 5
MAX_QUESTION_COUNT = 20
QUESTION_GEN_TOP_K = 6
QUESTION_GEN_CONTEXT_CHARS = 6000


def build_library_question_messages(
    topic: str, chunks: list[dict[str, Any]], count: int
) -> list[dict[str, str]]:
    """B7 出题 prompt（03 §4.2 / KY-10 / CERT-06）：资料片段是唯一事实来源。

    片段可以为空——只有主题时仍让模型出一组通用题，而不是直接拒绝：`doc_id` 与
    `point_id` 都是可选的，调用方可能只想按知识点名出一组自测题。
    """
    context = "\n\n".join(
        f"[片段 {index + 1}｜p.{chunk.get('page_no')}]\n{chunk.get('content', '')}"
        for index, chunk in enumerate(chunks)
    )[:QUESTION_GEN_CONTEXT_CHARS]
    user = (
        f"主题：{topic}\n题量：{count} 道\n\n"
        f"资料片段：\n{context or '（没有可用片段，请按主题出一组通用自测题）'}\n\n"
        "字段约束：subject 只能取 listening / reading / writing / translation / vocab / "
        "politics / english / math / major；qtype 只能取 single / multiple / judge / blank / "
        "short_answer / essay / material / lesson_plan / practical；单选题与多选题必须给出"
        "至少两个选项，answer 写正确选项的 key（多选题用逗号分隔），其余题型 answer 写参考答案。"
    )
    return [
        {"role": "system", "content": LIBRARY_QUESTION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def validate_generated_questions(text: Optional[str], count: int) -> list[dict[str, Any]]:
    """Parse and validate B7's output, or `MODEL_OUTPUT_INVALID` (ADR-03 不静默)。

    少于请求量是允许的（模型给出 3 道可用题仍值得入库），空结果与超量则拒绝：前者说明模型
    没有按 schema 作答，后者说明它忽略了题量预算。落库字段与手动录入、导入两条路径完全一致，
    题库的行形状不因来源而异。
    """
    payload, reason = extract_json(text)
    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, list) or not items:
        raise CampusError("MODEL_OUTPUT_INVALID", f"出题输出无法解析（{reason or 'items 缺失'}）")
    if len(items) > count:
        raise CampusError("MODEL_OUTPUT_INVALID", f"出题数量超出请求：{len(items)} > {count}")
    subjects = {subject.value for subject in models.Subject}
    qtypes = {qtype.value for qtype in models.QuestionType}
    choice_types = {models.QuestionType.SINGLE.value, models.QuestionType.MULTIPLE.value}
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题不是对象")
        subject = str(item.get("subject") or "").strip()
        stem = str(item.get("stem") or "").strip()
        answer = str(item.get("answer") or "").strip()
        qtype = str(item.get("qtype") or models.QuestionType.SINGLE.value).strip()
        if subject not in subjects:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题 subject 非法：{subject}")
        if qtype not in qtypes:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题题型非法：{qtype}")
        if not stem or not answer:
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题字段缺失")
        options = item.get("options")
        if qtype in choice_types:
            if not isinstance(options, list):
                raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 题缺少选项")
            options = [
                {
                    "key": str(option.get("key") or "").strip(),
                    "text": str(option.get("text") or "").strip(),
                }
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
                "max_score": 1,
                "source": models.QuestionSource.AI.value,
            }
        )
    return normalized


ATTRIBUTION_SYSTEM_PROMPT = (
    "你是备考复盘教练。根据每题的错误片段判断最可能的一个错因，"
    "只能从 concept_unclear / misread / calculation_or_operation / out_of_scope / "
    "time_short / pending 中选一个；证据不足时选 pending 并在 note 里说明原因。"
    "只输出一个 JSON 对象，不要任何其他文字，schema："
    '{"items": [{"attempt_id": "id", "suggestion": "misread", "confidence_note": "简短依据"}]}'
)

MAX_ATTRIBUTION_ATTEMPTS = 20


def build_attribution_messages(attempts: list[Any]) -> list[dict[str, str]]:
    """D7 归因建议 prompt（05 §4.3 study-companion 的 mistake-attribution 技能）。

    每条作答给出 id / 科目 / 作答原文 / 批改错误片段，让模型只在已有证据上判断——
    归因是"建议"，落库由用户在 D2 确认（CERT-08 v1.1 B④）。
    """
    lines: list[str] = []
    for row in attempts:
        grading = _grading_of(row)
        fragments = [
            str(error.get("fragment") or "").strip()
            for error in (grading.get("errors") or [])
            if isinstance(error, Mapping) and str(error.get("fragment") or "").strip()
        ]
        lines.append(
            "\n".join(
                [
                    f"- attempt_id: {row['id']}",
                    f"  科目: {row['subject']}",
                    f"  作答: {str(row['user_answer'] or '')[:400]}",
                    f"  错误片段: {'；'.join(fragments) or '（无）'}",
                ]
            )
        )
    user = "请为下面每条作答给出一个错因建议：\n\n" + "\n\n".join(lines)
    return [
        {"role": "system", "content": ATTRIBUTION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def validate_attribution_suggestions(text: Optional[str], attempt_ids: list[str]) -> list[dict]:
    """Parse and validate D7's output, or `MODEL_OUTPUT_INVALID` (ADR-03 不静默)。

    建议里出现请求之外的 attempt_id、或落在枚举外的错因，一律拒绝——这两个字段是前端
    回填选择器的输入，收下一条脏数据就把别人的归因写到当前档案上。数量允许少于请求
    （建议本就可能只覆盖一部分作答）。
    """
    payload, reason = extract_json(text)
    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, list) or not items:
        raise CampusError("MODEL_OUTPUT_INVALID", f"归因输出无法解析（{reason or 'items 缺失'}）")
    allowed = {attribution.value for attribution in models.Attribution}
    requested = set(attempt_ids)
    normalized: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise CampusError("MODEL_OUTPUT_INVALID", f"第 {index + 1} 条不是对象")
        attempt_id = str(item.get("attempt_id") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        if attempt_id not in requested:
            raise CampusError(
                "MODEL_OUTPUT_INVALID", f"第 {index + 1} 条的 attempt_id 不在请求中：{attempt_id}"
            )
        if suggestion not in allowed:
            raise CampusError(
                "MODEL_OUTPUT_INVALID", f"第 {index + 1} 条的 suggestion 非法：{suggestion}"
            )
        normalized.append(
            {
                "attempt_id": attempt_id,
                "suggestion": suggestion,
                "confidence_note": str(item.get("confidence_note") or "").strip(),
            }
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
        automation_store: Any = None,
    ) -> None:
        self._store = campus_store
        self._config = config
        self._inventory = inventory if inventory is not None else ModelInventory()
        self._provider_host = provider_host
        self._automation_store = automation_store
        self._grader = (
            ManagerGrader(provider_host, self.model_for_task, config.grading_start_level)
            if provider_host is not None
            else None
        )
        self._caller = (
            ManagerCaller(provider_host, self.model_for_task) if provider_host is not None else None
        )
        self._memory_store = getattr(provider_host, "memory_store", None)
        self._memory_settings = getattr(provider_host, "memory_settings", None)

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
        status = values.get("status")
        if status is not None and str(status) != profile.status:
            values["archived_at"] = (
                _utcnow() if str(status) == models.ProfileStatus.ARCHIVED.value else None
            )
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

    # -- I4-I6: exports (03 §4.9, INF-02/03) ---------------------------------

    def exports_dir(self) -> Path:
        """The export drop zone of PRD §6.1: `state_dir()/campus/exports/`."""
        return Path(state_dir()) / "campus" / "exports"

    def create_export(self, profile: models.ExamProfile, fmt: str) -> dict[str, Any]:
        """Write one export file into `campus/exports/` and name it back (I4).

        The json package is a whole-database backup (02 §7.4: the 18 data tables behind
        `schema_meta`, one array each, with the schema version carried as a field) so a
        restore can rebuild everything losslessly; md and csv are human-readable views of
        this profile only. Download names are safe by construction: every component of the
        filename is generated here, never user-supplied.
        """
        if fmt not in EXPORT_FORMATS:
            raise CampusError("UNSUPPORTED_TYPE", f"不支持的导出格式：{fmt}")
        directory = self.exports_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"campus-{profile.track_type}-{profile.id[:8]}-{self._export_stamp()}"
        name = f"{stem}.{fmt}"
        counter = 2
        while (directory / name).exists():
            name = f"{stem}-{counter}.{fmt}"
            counter += 1
        target = directory / name
        body = self._export_body(profile, fmt)
        target.write_bytes(body.encode("utf-8-sig" if fmt == "csv" else "utf-8"))
        return {"filename": name, "path": str(target)}

    def resolve_export(self, filename: str) -> tuple[Path, str]:
        """The whitelisted on-disk export for `filename`, or `EXPORT_NOT_FOUND` (I5).

        The pattern refuses separators, leading dots, reserved device stems and anything
        without an export extension outright; the resolved-path containment check then keeps
        a name that slipped past the pattern from pointing outside `campus/exports/`. Every
        failure answers with the same code, so odd names leak no extra information.
        """
        name = str(filename or "")
        stem = name.rsplit(".", 1)[0].upper()
        if not EXPORT_FILENAME_RE.match(name) or stem in EXPORT_RESERVED_STEMS:
            raise CampusError("EXPORT_NOT_FOUND", f"导出文件不存在：{name}")
        directory = self.exports_dir().resolve()
        target = (directory / name).resolve()
        if target.parent != directory or not target.is_file():
            raise CampusError("EXPORT_NOT_FOUND", f"导出文件不存在：{name}")
        return target, EXPORT_MEDIA_TYPES[target.suffix.lstrip(".")]

    def wipe_campus_data(self, *, restore_filename: Optional[str] = None) -> dict[str, Any]:
        """I6 — the 02 §7.1 one-click clear, or the INF-03 restore that rides on it.

        Bare (the A10 implementation, `{wiped: true}` per 03 §4.9): the database and the whole
        `campus/` tree go. With `restore_filename` (07 §2 registers I6 as I4's inverse, 02
        §7.4), the package is read and fully validated BEFORE anything is destroyed, the wipe
        rebuilds the schema at the package's own version, the rows replay in one transaction,
        and `migrate()` walks the result up to the current version — which is how a
        lower-version package earns its migration notice. `campus/exports/` survives a
        restore, so the backup being restored from is never destroyed by the restore itself.
        """
        if restore_filename is None:
            root = Path(state_dir())
            self._store.wipe()
            _remove_tree(root, root / "campus")
            return {"wiped": True}
        package = self._load_restore_package(restore_filename)
        self._store.wipe(target=package["schema_version"])
        rows_inserted = 0
        try:
            with self._store.transaction():
                for table in EXPORT_TABLE_ORDER:
                    for row in package["tables"].get(table, ()):
                        self._store.insert(table, dict(row))
                        rows_inserted += 1
        except CampusError:
            raise
        except Exception as exc:
            raise CampusError("PARSE_ERROR", f"恢复写入失败：{exc}") from exc
        migration: Optional[dict[str, int]] = None
        if package["schema_version"] < store.CURRENT_SCHEMA_VERSION:
            migration = {"from": package["schema_version"], "to": self._store.migrate()}
        counts = {table: self._store.count(table) for table in EXPORT_TABLE_ORDER}
        recorded = package.get("row_counts")
        counts_match = recorded == counts if isinstance(recorded, dict) else None
        _remove_tree(Path(state_dir()), Path(state_dir()) / "campus" / "library")
        return {
            "wiped": True,
            "restored": {"rows": rows_inserted, "tables": counts, "counts_match": counts_match},
            "schema_migration": migration,
        }

    def _load_restore_package(self, filename: str) -> dict[str, Any]:
        """Read and fully validate a restore package before the wipe destroys anything.

        Every refusal here happens while the live database is still untouched, so a bad
        package can never leave the user with nothing. A package newer than this app answers
        `SCHEMA_VERSION_ERROR` (03 §6's defensive case); everything malformed — JSON
        decoding, an unknown table or column, a row without its primary key — answers
        `PARSE_ERROR`. `schema_meta` itself is refused as a replay table: the version it
        records travels as the package's `schema_version` field instead. Duplicate primary
        keys are refused here too — the only replay failure the validation cannot otherwise
        see coming, and the one that would strike after the wipe has already destroyed the
        live rows.
        """
        target, media = self.resolve_export(filename)
        if media != "application/json":
            raise CampusError("PARSE_ERROR", "恢复包必须是 json 导出文件")
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampusError("PARSE_ERROR", f"恢复包不是有效 JSON：{exc}") from exc
        if not isinstance(payload, dict):
            raise CampusError("PARSE_ERROR", "恢复包必须是 JSON 对象")
        version = payload.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise CampusError("PARSE_ERROR", f"恢复包缺少有效的 schema_version：{version!r}")
        if version > store.CURRENT_SCHEMA_VERSION:
            raise CampusError(
                "SCHEMA_VERSION_ERROR",
                f"恢复包 schema v{version} 新于当前应用 v{store.CURRENT_SCHEMA_VERSION}，"
                "请先升级应用再恢复",
            )
        tables = payload.get("tables")
        if not isinstance(tables, dict):
            raise CampusError("PARSE_ERROR", "恢复包缺少 tables 行集")
        for name, rows in tables.items():
            if name not in models.ROW_MODELS or name == "schema_meta":
                raise CampusError("PARSE_ERROR", f"恢复包含未知表：{name}")
            columns = models.TABLE_COLUMNS[name]
            if not isinstance(rows, list):
                raise CampusError("PARSE_ERROR", f"{name} 的行集必须是数组")
            seen_ids: Optional[set[str]] = set() if "id" in columns else None
            for row in rows:
                if not isinstance(row, dict):
                    raise CampusError("PARSE_ERROR", f"{name} 存在非对象行")
                unknown = sorted(set(row) - set(columns))
                if unknown:
                    raise CampusError("PARSE_ERROR", f"{name} 存在未知列：{unknown}")
                if seen_ids is not None:
                    row_id = row.get("id")
                    if not row_id:
                        raise CampusError("PARSE_ERROR", f"{name} 存在缺少 id 的行")
                    if row_id in seen_ids:
                        raise CampusError("PARSE_ERROR", f"{name} 存在重复 id：{row_id}")
                    seen_ids.add(row_id)
        return {
            "schema_version": version,
            "tables": tables,
            "row_counts": payload.get("row_counts"),
        }

    def _export_stamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _export_body(self, profile: models.ExamProfile, fmt: str) -> str:
        if fmt == "json":
            return json.dumps(self._backup_package(), ensure_ascii=False, indent=2)
        if fmt == "md":
            return self._profile_markdown(profile)
        return self._attempts_csv(profile)

    def _backup_package(self) -> dict[str, Any]:
        """The 02 §7.4 restore package: one array per data table plus the schema version."""
        tables: dict[str, list[dict[str, Any]]] = {}
        counts: dict[str, int] = {}
        for table in EXPORT_TABLE_ORDER:
            rows = [
                {key: row[key] for key in row.keys()}
                for row in self._store.query_all(f'SELECT * FROM "{table}"')
            ]
            tables[table] = rows
            counts[table] = len(rows)
        return {
            "kind": BACKUP_KIND,
            "schema_version": store.CURRENT_SCHEMA_VERSION,
            "exported_at": _utcnow(),
            "row_counts": counts,
            "tables": tables,
        }

    def _profile_markdown(self, profile: models.ExamProfile) -> str:
        """The human-readable study report of this profile (INF-02's Markdown face)."""
        progress = self.progress(profile)
        coverage = self.mastery_coverage(profile.id)
        deadlines = self.list_deadlines(profile.id)["items"]
        questions = self._store.count("question_bank_item", '"profile_id" = ?', [profile.id])
        attempts = self._store.count("attempt", '"profile_id" = ?', [profile.id])
        correct = self._store.count(
            "attempt", '"profile_id" = ? AND "is_correct" = 1', [profile.id]
        )
        mistakes = self._store.count("mistake_book", '"profile_id" = ?', [profile.id])
        unresolved = self._store.count(
            "mistake_book", '"profile_id" = ? AND "resolved" = 0', [profile.id]
        )
        vocab_levels: dict[str, int] = {}
        for row in self._store.list_rows("vocab_item", profile_id=profile.id):
            vocab_levels[row["mastery"]] = vocab_levels.get(row["mastery"], 0) + 1
        vocab_total = sum(vocab_levels.values())
        plans = self._store.count("study_plan", '"profile_id" = ?', [profile.id])
        tasks = self._store.count("plan_task", '"profile_id" = ?', [profile.id])
        tasks_done = self._store.count(
            "plan_task",
            '"profile_id" = ? AND "status" = ?',
            [profile.id, models.PlanTaskStatus.DONE.value],
        )
        due = len(review_scheduler.due_items(self._store, profile.id))
        lines = [
            f"# 学习数据导出 — {profile.title}",
            "",
            f"- 导出时间：{_utcnow()}",
            f"- 轨道：{profile.track_type} / 状态：{profile.status}",
            f"- 考试日期：{profile.exam_date or '未设置'} / 目标分：{profile.target_score or '未设置'}",
            "",
            "## 学习进度",
            f"- 连续打卡：{progress['streak_days']} 天",
        ]
        for subject, entry in progress["by_track"].items():
            lines.append(f"- {subject}：{entry['done']}/{entry['total']}（{entry['rate']:.0%}）")
        lines += ["", "## 知识点掌握", f"- 覆盖率：{coverage['coverage']:.0%}"]
        weak = coverage.get("weak_top5") or []
        if weak:
            for item in weak:
                lines.append(f"- 薄弱：{item['title']}（{item['level']}）")
        else:
            lines.append("- 薄弱：暂无已评级知识点")
        lines += [
            "",
            "## 题库与作答",
            f"- 题目：{questions} 题 / 作答：{attempts} 次 / 判对：{correct} 次",
            "",
            "## 错题本",
            f"- 累计：{mistakes} 条 / 未解决：{unresolved} 条",
            "",
            "## 词汇",
            f"- 共 {vocab_total} 词（mastered {vocab_levels.get(models.MasteryLevel.MASTERED.value, 0)}"
            f" / fuzzy {vocab_levels.get(models.MasteryLevel.FUZZY.value, 0)}"
            f" / unknown {vocab_levels.get(models.MasteryLevel.UNKNOWN.value, 0)}）",
            "",
            "## 复习队列",
            f"- 今日到期：{due} 项",
            "",
            "## 学习计划",
            f"- 计划：{plans} 份 / 任务：{tasks} 项（已完成 {tasks_done} 项）",
            "",
            "## 考试节点",
        ]
        if deadlines:
            for item in deadlines:
                lines.append(f"- {item['node_type']} {item['date']}：剩 {item['days_left']} 天")
        else:
            lines.append("- 暂无考试节点")
        return "\n".join(lines) + "\n"

    def _attempts_csv(self, profile: models.ExamProfile) -> str:
        """The profile's attempt log as one flat CSV (INF-02's spreadsheet face)."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_ATTEMPT_COLUMNS)
        rows = self._store.list_rows(
            "attempt", profile_id=profile.id, order_by="created_at ASC, rowid ASC"
        )
        for row in rows:
            writer.writerow([row[column] for column in CSV_ATTEMPT_COLUMNS])
        return buffer.getvalue()

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
        mock = self._require_mock(profile.id, payload.get("mock_exam_id"))
        self._assert_mock_open(mock, question)
        mock_exam_id = None if mock is None else mock.id
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
            self._store.update("attempt", attempt_id, self._grading_columns(result, kind))
            self._apply_mastery_downgrade(profile.id, question, result)
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
        degradation trace (T07 §6-3/§6-6). The CERT-15 mastery downgrade runs in the same
        transaction as the grading write, so the response and the side effect land together.
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
        with self._store.transaction():
            self._store.update("attempt", attempt_id, self._grading_columns(result, kind))
            self._apply_mastery_downgrade(profile.id, question, result)
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

    # -- B 组：资料库与按页问答（03 §4.2 G-07/G-10/G-11、KY-09/KY-10）----------

    @property
    def library(self) -> CampusLibrary:
        """A `CampusLibrary` handle bound to this service's store.

        Built per call instead of cached in `__init__`: the sidecar installs its
        `ProviderClient` lazily, and `CampusLibrary` decides between the L1 目录路由 and the
        L2 keyword path from `provider is None` — a key added in Settings must change that
        decision on the next request rather than after a restart. Construction is cheap
        (`enable_fts` stays off, so nothing touches the database).
        """
        provider = (
            getattr(self._provider_host, "provider", None)
            if self._provider_host is not None
            else None
        )
        return CampusLibrary(self._store, provider=provider, model_picker=self._library_picker)

    def _library_picker(self, kind: str, track_type: str = "") -> tuple[str, str]:
        """The model the library would run a task on, plus the static list's floor (06 §2.2)."""
        del track_type
        task = models.task_for_kind(kind)
        model = self.model_for_task(task)
        if model is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        return model, models.pick_for_task(task)[1]

    def _library_call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run one library-layer call, translating `LibraryError` into the documented code."""
        try:
            return fn(*args, **kwargs)
        except LibraryError as exc:
            raise CampusError(exc.code, exc.message, **exc.extra) from exc

    def list_library_docs(
        self, profile: models.ExamProfile, *, parse_status: Optional[str] = None
    ) -> dict[str, Any]:
        """B2 — the profile's imported documents, newest first (03 §4.2)."""
        rows = self._store.list_rows(
            "source_doc",
            profile_id=profile.id,
            where='"parse_status" = ?' if parse_status else None,
            params=[parse_status] if parse_status else None,
            order_by="imported_at DESC, rowid DESC",
        )
        return {"items": [asdict(models.SourceDoc.from_row(row)) for row in rows]}

    def import_library_doc(
        self, profile: models.ExamProfile, file_path: str, filename: Optional[str] = None
    ) -> dict[str, Any]:
        """B1 — validate the upload, then copy + parse it into the library (G-10).

        The refusals the endpoint owes the caller (015/413/507) are decided here so they travel
        out as one documented error family; the copy and the parse belong to `CampusLibrary`.
        `filename` is the client's own name for the upload — the route stages the body in a temp
        file, so without it every imported document would be titled `tmpab12cd`.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix not in LIBRARY_UPLOAD_SUFFIXES:
            raise CampusError("UNSUPPORTED_TYPE", f"不支持的文件类型：{suffix or '（无扩展名）'}")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise CampusError("PARSE_ERROR", f"上传文件不可读：{exc}") from exc
        if size > MAX_LIBRARY_UPLOAD_BYTES:
            limit = MAX_LIBRARY_UPLOAD_BYTES // (1024 * 1024)
            raise CampusError("FILE_TOO_LARGE", f"文件超过 {limit}MB 上限")
        free = shutil.disk_usage(state_dir()).free
        if free < size + MIN_LIBRARY_FREE_BYTES:
            raise CampusError("DISK_FULL", "磁盘剩余空间不足，已拒绝导入")
        return self._library_call(self.library.import_pdf, profile.id, str(path), filename)

    def retry_library_doc(self, profile: models.ExamProfile, doc_id: str) -> dict[str, Any]:
        """B5 — re-run the parse; a scanned document is refused instead of burning another pass."""
        return self._library_call(self.library.retry_parse, profile.id, doc_id)

    def delete_library_doc(self, profile: models.ExamProfile, doc_id: str) -> dict[str, Any]:
        """B4 — drop the row, its chunks and the stored file (02 §5.3 order)."""
        self._library_call(self.library.delete_doc, profile.id, doc_id)
        return {"deleted": True}

    async def ask_library(self, profile: models.ExamProfile, payload: Mapping[str, Any]) -> dict:
        """B6 — answer one question against the library, citations included (KY-09).

        `doc_id` is optional: absent means the whole profile library is in scope. The
        readiness gate (missing / unpacked / scanned) lives in the library layer so B6 and B7
        refuse the same documents for the same reasons.
        """
        doc_id = str(payload.get("doc_id") or "").strip() or None
        question = str(payload.get("question") or "").strip()
        try:
            return await self.library.answer_qa(profile.id, question, doc_id)
        except LibraryError as exc:
            raise CampusError(exc.code, exc.message, **exc.extra) from exc

    async def generate_library_questions(
        self, profile: models.ExamProfile, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """B7 — generate question-bank items from a document (or a knowledge point).

        Retrieval picks the grounding <em>context</em> from the profile's library, so the
        generated questions stay inside material the student actually owns; `point_id` and
        `doc_id` are both optional, and with neither the whole library (or, failing that, just
        the topic string) is the source. Every accepted item is inserted through the same
        `_insert_question` path as manual entry, inside one transaction, so a rejected batch
        leaves the bank untouched.
        """
        doc_id = str(payload.get("doc_id") or "").strip() or None
        point_id = self._require_point(profile.id, payload.get("point_id"))
        count = int(payload.get("count") or DEFAULT_QUESTION_COUNT)
        library = self.library
        if doc_id is not None:
            self._library_call(library.require_ready_doc, profile.id, doc_id)
        topic = self._question_topic(profile, doc_id, point_id)
        chunks = library.retrieve(profile.id, topic, top_k=QUESTION_GEN_TOP_K, doc_id=doc_id)
        model = self.model_for_task(models.CampusTask.QUESTION.value)
        if model is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        messages = build_library_question_messages(topic, chunks, count)
        try:
            turn = await asyncio.to_thread(
                self._require_provider().complete,
                model=model,
                messages=messages,
                temperature=0,
                timeout=PROVIDER_TIMEOUT_S,
            )
        except CampusError:
            raise
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower():
                raise CampusError("MODEL_TIMEOUT", "模型调用超时") from exc
            raise CampusError("MODEL_OUTPUT_INVALID", "模型调用失败") from exc
        items = validate_generated_questions(getattr(turn, "text", None), count)
        created: list[dict[str, Any]] = []
        with self._store.transaction():
            for item in items:
                created.append(
                    self._insert_question(
                        profile.id, {**item, "point_id": point_id, "doc_id": doc_id}
                    )
                )
        return {"items": created}

    def _question_topic(
        self, profile: models.ExamProfile, doc_id: Optional[str], point_id: Optional[str]
    ) -> str:
        """The retrieval query / prompt topic: the point, else the document, else the profile."""
        if point_id:
            row = self._store.get_scoped("knowledge_point", point_id, profile.id)
            if row is not None:
                return str(row["title"])
        if doc_id:
            row = self._store.get_scoped("source_doc", doc_id, profile.id)
            if row is not None:
                return str(row["title"])
        return profile.title

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

    # -- H7-H10: exam nodes and in-app reminders (03 §4.8) ------------------

    def create_deadline(self, profile_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Record one node of the exam timeline; one node of each type per profile (H7)."""
        node_type = str(payload["node_type"])
        if (
            self._store.query_one(
                'SELECT "id" FROM "cert_deadline" WHERE "profile_id" = ? AND "node_type" = ?',
                (profile_id, node_type),
            )
            is not None
        ):
            raise CampusError("DUPLICATE_NODE", f"同类型考试节点已存在：{node_type}")
        deadline_id = self._store.insert(
            "cert_deadline",
            {
                "profile_id": profile_id,
                "node_type": node_type,
                "date": str(payload["date"]),
                "is_reference": 1 if payload.get("is_reference") else 0,
            },
        )
        return self._deadline_payload(self._store.get("cert_deadline", deadline_id))

    def list_deadlines(self, profile_id: str) -> dict[str, Any]:
        """The node timeline, oldest first, each with its live countdown (H8)."""
        rows = self._store.list_rows(
            "cert_deadline", profile_id=profile_id, order_by="date, id"
        )
        today = reminders.today()
        return {
            "items": [
                {
                    **self._deadline_payload(row),
                    "days_left": reminders.days_left(row["date"], today=today),
                }
                for row in rows
            ]
        }

    def create_deadline_reminders(self, deadline: models.CertDeadline) -> dict[str, Any]:
        """Create the D-30/D-7/D-1 `once` tasks through the existing TaskStore (H9, CERT-13).

        Pressing the button again returns the stored ids instead of duplicating tasks, and
        a fire moment that already passed is not created at all: `compute_next_run` refuses
        past once tasks, so such a row would only clutter the automation list.
        """
        if self._automation_store is None:
            raise CampusError("AUTOMATION_UNAVAILABLE")
        existing = _decode(deadline.automation_ids, [])
        if existing:
            return {"automation_ids": [str(task_id) for task_id in existing]}
        label = reminders.node_label(deadline.node_type)
        ids: list[str] = []
        try:
            for offset, fire_at in reminders.reminder_fire_dates(deadline.date):
                task = ScheduledTask(
                    title=f"{label}提醒（D-{offset}）",
                    instructions=(
                        f"用户备考的证书节点「{label}」定于 {deadline.date}。"
                        f"今天是该节点的 D-{offset} 应用内提醒：请生成一条 50 字以内的中文提醒，"
                        "包含节点名、日期与剩余天数，提醒用户及时处理，不要执行其他操作。"
                    ),
                    schedule=Schedule(kind="once", fire_at=fire_at, timezone="local"),
                    workspace=os.getcwd(),
                    origin_surface="campus",
                )
                self._automation_store.save(task)
                ids.append(task.id)
        except CampusError:
            raise
        except Exception as exc:
            raise CampusError("AUTOMATION_UNAVAILABLE", f"自动化任务存储不可用：{exc}") from exc
        if ids:
            self._store.update("cert_deadline", deadline.id, {"automation_ids": _encode(ids)})
        return {"automation_ids": ids}

    def reminders(self, profile_id: str) -> dict[str, Any]:
        """The banner data source: upcoming nodes plus the due-today and overdue ones (H10)."""
        return reminders.deadline_snapshot(self._store, profile_id)

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

    # -- F6-F9: high-frequency vocabulary (CET-02/04/06) --------------------

    def vocab_today(self, profile: models.ExamProfile) -> dict[str, Any]:
        """The day's word list: new words plus the reviews that are due (F6).

        New words are capped at 30 (PRD CET2's "每天只背 30 个词"), ordered by the real-exam
        frequency (`freq_rank`, unknown ranks last) and excluding anything already queued for
        review — a word the student is reviewing must not reappear as new. Due reviews inline the
        word itself so the card can render without a second request.
        """
        queued = {
            row["item_id"]
            for row in self._store.list_rows(
                "review_queue",
                profile_id=profile.id,
                where='"item_type" = ? AND "status" = ?',
                params=[models.ReviewItemType.VOCAB.value, models.ReviewStatus.PENDING.value],
            )
        }
        unknown_rows = self._store.list_rows(
            "vocab_item",
            profile_id=profile.id,
            where='"mastery" = ?',
            params=[models.MasteryLevel.UNKNOWN.value],
            order_by="created_at, rowid",
        )
        candidates = [row for row in unknown_rows if row["id"] not in queued]
        candidates.sort(key=lambda row: (row["freq_rank"] is None, row["freq_rank"] or 0))
        review_items: list[dict[str, Any]] = []
        for row in self._store.list_rows(
            "review_queue",
            profile_id=profile.id,
            where='"item_type" = ? AND "status" = ? AND "due_at" <= ?',
            params=[
                models.ReviewItemType.VOCAB.value,
                models.ReviewStatus.PENDING.value,
                _utcnow(),
            ],
            order_by="due_at, rowid",
        ):
            word = self._store.get_scoped("vocab_item", row["item_id"], profile.id)
            if word is None:
                continue
            review_items.append(
                {
                    **asdict(models.ReviewItem.from_row(row)),
                    "payload": vocab_payload(models.VocabItem.from_row(word)),
                }
            )
        return {
            "new_items": [
                vocab_payload(models.VocabItem.from_row(row))
                for row in candidates[:NEW_WORD_LIMIT]
            ],
            "review_items": review_items,
        }

    def set_vocab_mastery(
        self, profile: models.ExamProfile, vocab: models.VocabItem, mastery: str
    ) -> dict[str, Any]:
        """Record a self-reported mastery mark, queueing "不认识" for tomorrow (F7).

        The API vocabulary of 03 §4.6 (`known`) and the column vocabulary of 02 §4.11
        (`mastered`) are two names for the same state; both are accepted and the column form is
        stored. Queueing is idempotent — marking a word unknown twice leaves one pending item —
        and the interval progression itself belongs to T13's `review_scheduler` (D6).
        """
        stored = VOCAB_MASTERY_ALIASES[mastery]
        self._store.update("vocab_item", vocab.id, {"mastery": stored})
        if stored == models.MasteryLevel.UNKNOWN.value:
            self._enqueue_vocab_review(profile.id, vocab.id)
        return self.vocab(vocab.id)

    def import_vocabulary(
        self, profile: models.ExamProfile, fmt: str, content: str
    ) -> dict[str, int]:
        """Import a custom word list, counting words already stored as skipped (F8)."""
        imported = 0
        skipped = 0
        for row in parse_vocabulary(fmt, content):
            word = row["word"]
            if self._vocab_exists(profile.id, word):
                skipped += 1
                continue
            self._store.insert(
                "vocab_item",
                {
                    "profile_id": profile.id,
                    "word": word,
                    "phonetic": row.get("phonetic") or "",
                    "meaning": row.get("meaning") or "",
                    "example": row.get("example") or "",
                    "example_source": models.ExampleSource.AI.value,
                },
            )
            imported += 1
        return {"imported": imported, "skipped": skipped}

    async def vocab_mnemonic(
        self, profile: models.ExamProfile, vocab: models.VocabItem
    ) -> dict[str, Any]:
        """Generate a mnemonic and remember it through the existing memory chain (F9).

        The write goes through the manager's memory store and respects the user's Memory switch
        (01 §4.2: campus never opens `coworker.db` itself) — with Memory off the mnemonic is still
        returned, just not remembered, and the response says so instead of pretending.
        """
        if self.model_for_task(models.CampusTask.EXPLAIN.value) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        mnemonic = (
            await asyncio.to_thread(
                self._require_caller().complete,
                models.CampusTask.EXPLAIN.value,
                build_mnemonic_messages(vocab),
            )
        ).strip()
        if not mnemonic:
            raise CampusError("MODEL_OUTPUT_INVALID", "助记输出为空")
        saved, memory_id = self._remember_mnemonic(vocab, mnemonic)
        return {"mnemonic": mnemonic, "saved": saved, "memory_id": memory_id}

    def vocab(self, vocab_id: str) -> dict[str, Any]:
        """One word body, or `ITEM_NOT_FOUND` (03 §6's code for a missing review source)."""
        row = self._store.get("vocab_item", vocab_id)
        if row is None:
            raise CampusError("ITEM_NOT_FOUND", f"单词不存在：{vocab_id}")
        return vocab_payload(models.VocabItem.from_row(row))

    # -- D4-D6: the review queue (G-17/CET-05, scheduler of T13) ------------

    def enqueue_review(
        self, profile: models.ExamProfile, item_type: str, item_id: str
    ) -> dict[str, Any]:
        """Put one source item into tomorrow's queue, never twice (D4).

        The source must exist and belong to the profile (`ITEM_NOT_FOUND` / `FORBIDDEN_PROFILE`).
        A still-pending row is returned unchanged so re-joining never resets progress —
        02 §4.15 keeps one pending row per item and rides repeats through the UPSERT —
        while a `done` history row starts a fresh cycle at the ladder's first step.
        """
        table = REVIEW_SOURCE_TABLES[item_type]
        if self._store.get_scoped(table, item_id, profile.id) is None:
            if self._store.get(table, item_id) is not None:
                raise CampusError("FORBIDDEN_PROFILE", f"{table} 不属于当前档案：{item_id}")
            raise CampusError("ITEM_NOT_FOUND", f"复习素材不存在：{item_id}")
        existing = self._store.query_one(
            'SELECT * FROM "review_queue" WHERE "profile_id" = ? AND "item_type" = ? '
            'AND "item_id" = ? AND "status" = ?',
            (profile.id, item_type, item_id, models.ReviewStatus.PENDING.value),
        )
        if existing is not None:
            return review_payload(models.ReviewItem.from_row(existing))
        row_id = self._store.insert(
            "review_queue",
            {
                "profile_id": profile.id,
                "item_type": item_type,
                "item_id": item_id,
                "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                    "%Y-%m-%dT00:00:00Z"
                ),
                "interval_days": 1,
                "streak_right": 0,
                "ease": 2.5,
                "status": models.ReviewStatus.PENDING.value,
            },
        )
        return review_payload(models.ReviewItem.from_row(self._store.get("review_queue", row_id)))

    def review_due(
        self, profile: models.ExamProfile, *, as_of: Optional[str] = None
    ) -> dict[str, Any]:
        """The due queue with the source content inlined (D5).

        The scheduler owns the pull (pending, `due_at <= as_of`, oldest first, profile
        isolated); this layer only adds each source's body so a review card renders
        without a second request. A row whose source has disappeared — an individually
        deleted question, say — is skipped instead of failing the whole pull.
        """
        items: list[dict[str, Any]] = []
        for item in review_scheduler.due_items(self._store, profile.id, as_of=as_of):
            source = self._store.get_scoped(
                REVIEW_SOURCE_TABLES[item.item_type], item.item_id, profile.id
            )
            if source is None:
                continue
            items.append({**review_payload(item), "payload": self._source_payload(item.item_type, source)})
        return {"items": items}

    def review_result(
        self, profile: models.ExamProfile, item: models.ReviewItem, correct: bool
    ) -> dict[str, Any]:
        """Record one review's outcome and reschedule it (D6, the SM-2 progression)."""
        del profile
        updated = review_scheduler.apply_result(item, correct)
        self._store.update(
            "review_queue",
            item.id,
            {
                "due_at": updated.due_at,
                "interval_days": updated.interval_days,
                "streak_right": updated.streak_right,
                "ease": updated.ease,
                "status": updated.status,
                "last_reviewed_at": updated.last_reviewed_at,
            },
        )
        return review_payload(updated)

    def _source_payload(self, item_type: str, source: Any) -> dict[str, Any]:
        """The inlined body of a queue row's source, per its item type (D5)."""
        if item_type == models.ReviewItemType.VOCAB.value:
            return vocab_payload(models.VocabItem.from_row(source))
        if item_type == models.ReviewItemType.KNOWLEDGE_POINT.value:
            return asdict(models.KnowledgePoint.from_row(source))
        return asdict(models.MistakeBookEntry.from_row(source))

    # -- I2-I3: automation templates (G-18, installed through T13) ----------

    def automation_template_catalogue(self) -> dict[str, Any]:
        """The installable templates (I2, G-18): identity and schedule shape only."""
        return {"items": automation_templates.catalogue()}

    def install_automation_template(
        self, profile: models.ExamProfile, tpl_id: str
    ) -> dict[str, Any]:
        """One-click install of an automation template (I3, G-18/CET-05/KY-12/CERT-13).

        The tasks are created through the sidecar's existing automation CRUD — campus
        adds no scheduler of its own (01 §2). The weekly report fires a model call when
        it runs, so installing it without a usable model is refused up front; the node
        template computes `once` fire moments from the exam date and cannot be installed
        without one. Repeat installs return the already-installed task ids unchanged.
        """
        task_store = (
            getattr(self._provider_host, "task_store", None)
            if self._provider_host is not None
            else None
        )
        if task_store is None:
            raise CampusError("AUTOMATION_UNAVAILABLE")
        template = automation_templates.get_template(tpl_id)
        if template is None:
            raise CampusError("TEMPLATE_NOT_FOUND", f"自动化模板不存在：{tpl_id}")
        if template.requires_model and self.model_for_task(models.CampusTask.EXPLAIN.value) is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        if template.requires_exam_date and not str(profile.exam_date or "").strip():
            raise CampusError("EXAM_DATE_REQUIRED", "考试节点提醒需要先设置考试日期")
        push_time = self.app_state()["settings"]["push_time"]
        task_ids = automation_templates.install_template(
            self._provider_host, profile, tpl_id, push_time=str(push_time)
        )
        return {"task_ids": task_ids}

    # -- D1-D3 / D7：错题本与归因建议（03 §4.4 G-16、CERT-08/09）-------------

    def list_mistakes(
        self,
        profile: models.ExamProfile,
        *,
        attribution: Optional[str] = None,
        resolved: Optional[int] = None,
        point_id: Optional[str] = None,
        track_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """D1 — one page of the mistake book, newest wrong first (G-16/CERT-08)."""
        filters = [
            pair
            for pair in (
                ("attribution", attribution),
                ("resolved", resolved),
                ("point_id", point_id),
                ("track_type", track_type),
            )
            if pair[1] is not None and pair[1] != ""
        ]
        where = " AND ".join(f'"{name}" = ?' for name, _ in filters) or None
        params = [value for _, value in filters]
        total = self._store.count(
            "mistake_book",
            " AND ".join(['"profile_id" = ?', *(f'"{name}" = ?' for name, _ in filters)]),
            [profile.id, *params],
        )
        rows = self._store.list_rows(
            "mistake_book",
            profile_id=profile.id,
            where=where,
            params=params,
            order_by="last_wrong_at DESC, rowid DESC",
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return {
            "items": [
                asdict(models.MistakeBookEntry.from_row(row)) for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_mistake(
        self,
        profile: models.ExamProfile,
        mistake: models.MistakeBookEntry,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]:
        """D2 — the user's own re-attribution / note / resolve on one entry (CERT-08).

        Only `MISTAKE_FIELDS` is honoured, mirroring `update_profile`: the row's attempt and
        track decide what the entry means, so a patch that tried to rewrite them is dropped
        rather than silently accepted.
        """
        values: dict[str, Any] = {}
        for name in MISTAKE_FIELDS:
            if name not in patch:
                continue
            value = patch[name]
            if name == "attribution":
                value = str(value or "")
                if value not in _ATTRIBUTIONS:
                    raise CampusError("INVALID_ATTRIBUTION", f"错因取值非法：{value}")
            elif name == "point_id":
                value = self._require_point(profile.id, value)
            elif name == "resolved":
                value = 1 if int(value) else 0
            else:
                value = str(value or "")
            values[name] = value
        if not values:
            return asdict(mistake)
        with self._store.transaction():
            self._store.update("mistake_book", mistake.id, values)
            if values.get("attribution") and values["attribution"] != models.Attribution.PENDING.value:
                self._store.update(
                    "mistake_book", mistake.id, {"attribution_confidence": None}
                )
        row = self._store.get("mistake_book", mistake.id)
        return asdict(models.MistakeBookEntry.from_row(row))

    def mistake_stats(self, profile: models.ExamProfile) -> dict[str, Any]:
        """D3 — the attribution histogram over the profile's unresolved mistakes (CERT-09).

        `resolved` rows are excluded on purpose: the card answers "what am I still getting
        wrong", and a closed entry no longer needs an attribution to act on. The winner is the
        highest count with a stable alphabetical tie-break, so the same data always reports the
        same top错因.
        """
        rows = self._store.query_all(
            'SELECT "attribution", COUNT(*) AS "n" FROM "mistake_book" '
            'WHERE "profile_id" = ? AND "resolved" = 0 GROUP BY "attribution"',
            (profile.id,),
        )
        distribution = {
            str(row["attribution"] or models.Attribution.PENDING.value): int(row["n"])
            for row in rows
        }
        ranked = sorted(distribution.items(), key=lambda item: (-item[1], item[0]))
        return {
            "distribution": distribution,
            "top_attribution": ranked[0][0] if ranked else None,
        }

    async def suggest_attributions(
        self, profile: models.ExamProfile, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """D7 — AI-suggested attributions for graded attempts, advisory only (CERT-08 v1.1 B④).

        Nothing is written: the suggestions come back for the client to pre-fill the picker,
        and the user's confirmation is what reaches D2. Every requested attempt is resolved
        through the profile scope first, so one foreign id fails the whole call instead of
        having its errors read on someone else's behalf.
        """
        attempt_ids = [str(value) for value in payload.get("attempt_ids") or []]
        attempts = [self._require_attempt(profile.id, attempt_id) for attempt_id in attempt_ids]
        model = self.model_for_task(models.CampusTask.EXPLAIN.value)
        if model is None:
            raise CampusError("MODEL_NOT_CONFIGURED")
        try:
            turn = await asyncio.to_thread(
                self._require_provider().complete,
                model=model,
                messages=build_attribution_messages(attempts),
                temperature=0,
                timeout=PROVIDER_TIMEOUT_S,
            )
        except CampusError:
            raise
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower():
                raise CampusError("MODEL_TIMEOUT", "模型调用超时") from exc
            raise CampusError("MODEL_OUTPUT_INVALID", "模型调用失败") from exc
        return {"items": validate_attribution_suggestions(getattr(turn, "text", None), attempt_ids)}

    def _require_attempt(self, profile_id: str, attempt_id: str) -> Any:
        """Resolve one attempt inside the profile scope (`FORBIDDEN_PROFILE` for anyone else's)."""
        row = self._store.get_scoped("attempt", attempt_id, profile_id)
        if row is None:
            if self._store.get("attempt", attempt_id) is not None:
                raise CampusError("FORBIDDEN_PROFILE", f"作答记录不属于当前档案：{attempt_id}")
            raise CampusError("ATTEMPT_NOT_FOUND", f"作答记录不存在：{attempt_id}")
        return row

    # -- I1：备考人设只读清单（03 §4.9 G-12）--------------------------------

    def campus_personas(self) -> dict[str, Any]:
        """I1 — the persona bundles the three stations declare, with live availability (G-12).

        The kernel registry stays the single source of truth for names, icons and taglines
        (05 §3); this endpoint is a read-only filter over it. The list is always the six
        declared ids — an id the user disabled in Settings reports `available: false` instead
        of disappearing, so the station can say why the picker is short.
        """
        from ..personas.registry import get_registry

        registry = get_registry()
        items: list[dict[str, Any]] = []
        for persona_id in CAMPUS_PERSONA_IDS:
            entry = registry.get(persona_id)
            items.append(
                {
                    "id": persona_id,
                    "name": entry.name if entry is not None else persona_id,
                    "icon": entry.icon if entry is not None else "",
                    "tagline": entry.tagline if entry is not None else "",
                    "available": entry is not None and registry.is_enabled(persona_id),
                }
            )
        return {"items": items}

    # -- F10-F14: the proctored mock exam (CET-13/14) -----------------------

    def start_mock(self, profile: models.ExamProfile, paper_title: str) -> dict[str, Any]:
        """F10 — open an ongoing mock on the writing stage with a precomputed deadline."""
        started = _utcnow()
        mock_id = self._store.insert(
            "mock_exam",
            {
                "profile_id": profile.id,
                "paper_title": paper_title,
                "started_at": started,
                "stage_deadline": _utcformat(
                    _parse_utc(started)
                    + timedelta(minutes=MOCK_STAGE_MINUTES[models.MockStage.WRITING.value])
                ),
            },
        )
        mock = models.MockExam.from_row(self._store.get("mock_exam", mock_id))
        return self.mock_view(mock)

    def mock_view(self, mock: models.MockExam) -> dict[str, Any]:
        """F11 — the stored row plus a live derived timer, so a refresh never trusts the client.

        The read is pure: the clock is recomputed from `stage_deadline` (which pauses already
        shifted), and the stage transition itself stays an explicit F12 call.
        """
        payload = mock_payload(mock)
        now = datetime.now(timezone.utc)
        if mock.stage_deadline:
            deadline = _parse_utc(mock.stage_deadline)
            payload["remaining_seconds"] = max(0, int((deadline - now).total_seconds()))
            payload["stage_expired"] = now >= deadline
        else:
            payload["remaining_seconds"] = 0
            payload["stage_expired"] = False
        payload["server_now"] = _utcformat(now)
        return payload

    def advance_mock_stage(
        self, profile: models.ExamProfile, mock: models.MockExam, to: str
    ) -> dict[str, Any]:
        """F12 — move to the next stage and collect the previous answer sheet (CET-13 验收 1)."""
        del profile
        self._assert_mock_ongoing(mock)
        locked = json.loads(mock.locked_stages or "[]")
        if to in locked:
            raise CampusError("STAGE_LOCKED", f"该阶段已收卡，不可返回：{to}")
        successor = self._mock_successor(mock.current_stage)
        if to != successor:
            raise CampusError(
                "ILLEGAL_STAGE", f"阶段流转非法：{mock.current_stage} → {to}"
            )
        locked.append(mock.current_stage)
        deadline = _parse_utc(mock.stage_deadline) + timedelta(minutes=MOCK_STAGE_MINUTES[to])
        self._store.update(
            "mock_exam",
            mock.id,
            {
                "current_stage": to,
                "locked_stages": json.dumps(locked, ensure_ascii=False),
                "stage_deadline": _utcformat(deadline),
            },
        )
        return self.mock_view(models.MockExam.from_row(self._store.get("mock_exam", mock.id)))

    def pause_mock(
        self, profile: models.ExamProfile, mock: models.MockExam, seconds: int
    ) -> dict[str, Any]:
        """F13 — extend the stage clock, within the cumulative pause budget (03 §4.6)."""
        del profile
        self._assert_mock_ongoing(mock)
        total = mock.paused_seconds + seconds
        if total > MOCK_PAUSE_BUDGET_SECONDS:
            raise CampusError(
                "PAUSE_EXCEEDED",
                f"累计暂停 {total}s 超过上限 {MOCK_PAUSE_BUDGET_SECONDS}s",
            )
        self._store.update(
            "mock_exam",
            mock.id,
            {
                "paused_seconds": total,
                "stage_deadline": _utcformat(_parse_utc(mock.stage_deadline) + timedelta(seconds=seconds)),
            },
        )
        return self.mock_view(models.MockExam.from_row(self._store.get("mock_exam", mock.id)))

    def submit_mock(self, profile: models.ExamProfile, mock: models.MockExam) -> dict[str, Any]:
        """F14 — score the linked attempts, store the estimate and file the wrong answers.

        The estimate is the paper's own scores summed (objective earned, band-graded subjective
        scores as recorded by E5): imported real papers carry their official per-item scores, so
        a second rescaling would only invent precision (CET-14, 06 §2).
        """
        self._assert_mock_ongoing(mock)
        attempts = self._store.list_rows(
            "attempt",
            profile_id=profile.id,
            where="mock_exam_id = ?",
            params=(mock.id,),
            order_by="created_at, rowid",
        )
        by_section = {
            section: {"earned": 0.0, "max": 0.0} for section in MOCK_SECTIONS
        }
        for row in attempts:
            section = SUBJECT_SECTION.get(row["subject"])
            if section is None:
                continue
            by_section[section]["earned"] += float(row["score"] or 0.0)
            by_section[section]["max"] += float(row["max_score"] or 0.0)
        for entry in by_section.values():
            entry["ratio"] = (
                round(entry["earned"] / entry["max"], 4) if entry["max"] > 0 else None
            )
        estimate = round(sum(entry["earned"] for entry in by_section.values()), 1)
        self._store.update(
            "mock_exam",
            mock.id,
            {
                "status": models.MockStatus.SUBMITTED.value,
                "current_stage": models.MockStage.GRADED.value,
                "estimate_score": estimate,
            },
        )
        for row in attempts:
            if row["is_correct"] == 0 and row["question_id"]:
                self._file_mistake(profile, row)
        return {
            "estimate_score": estimate,
            "by_section": by_section,
            "attempt_ids": [row["id"] for row in attempts],
        }

    # -- internals ---------------------------------------------------------

    def _assert_mock_ongoing(self, mock: models.MockExam) -> None:
        if mock.status != models.MockStatus.ONGOING.value:
            raise CampusError("MOCK_SUBMITTED", f"模考已交卷：{mock.id}")

    def _mock_successor(self, stage: Optional[str]) -> Optional[str]:
        try:
            return MOCK_STAGE_ORDER[MOCK_STAGE_ORDER.index(stage) + 1]
        except (ValueError, IndexError):
            return None

    def _file_mistake(self, profile: models.ExamProfile, attempt_row: Any) -> None:
        """Enter one wrong attempt into the mistake book, idempotent per attempt (CET-14 验收 3)."""
        if self._store.count("mistake_book", "attempt_id = ?", (attempt_row["id"],)):
            return
        self._store.insert(
            "mistake_book",
            {
                "profile_id": profile.id,
                "attempt_id": attempt_row["id"],
                "track_type": profile.track_type,
                "subject": attempt_row["subject"],
                "question_id": attempt_row["question_id"],
                "last_wrong_at": _utcnow(),
            },
        )

    def _enqueue_vocab_review(self, profile_id: str, vocab_id: str) -> None:
        """Put a word into tomorrow's review queue once, never twice."""
        existing = self._store.query_one(
            'SELECT "id" FROM "review_queue" WHERE "profile_id" = ? AND "item_type" = ? '
            'AND "item_id" = ? AND "status" = ?',
            (
                profile_id,
                models.ReviewItemType.VOCAB.value,
                vocab_id,
                models.ReviewStatus.PENDING.value,
            ),
        )
        if existing is not None:
            return
        due = datetime.now(timezone.utc) + timedelta(days=1)
        self._store.insert(
            "review_queue",
            {
                "profile_id": profile_id,
                "item_type": models.ReviewItemType.VOCAB.value,
                "item_id": vocab_id,
                "due_at": due.strftime("%Y-%m-%dT00:00:00Z"),
                "interval_days": 1,
                "streak_right": 0,
                "ease": 2.5,
                "status": models.ReviewStatus.PENDING.value,
            },
        )

    def _vocab_exists(self, profile_id: str, word: str) -> bool:
        row = self._store.query_one(
            'SELECT "id" FROM "vocab_item" WHERE "profile_id" = ? AND "word" = ?',
            (profile_id, word),
        )
        return row is not None

    def _remember_mnemonic(self, vocab: models.VocabItem, mnemonic: str) -> tuple[bool, Optional[int]]:
        """Write the mnemonic through the manager's memory store, honouring the Memory switch."""
        settings = self._memory_settings
        if settings is not None and not getattr(settings, "enabled", False):
            return False, None
        store = self._memory_store
        if store is None:
            return False, None
        try:
            item = store.add(
                f"背单词助记（{vocab.word}）：{mnemonic}",
                scope=Scope.GLOBAL,
                summary=f"{vocab.word} 的助记",
            )
        except Exception:
            return False, None
        return True, getattr(item, "id", None)

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

    def _require_mock(
        self, profile_id: str, mock_exam_id: Optional[str]
    ) -> Optional[models.MockExam]:
        """Load the referenced mock inside the profile's scope, or `MOCK_NOT_FOUND`."""
        if mock_exam_id is None:
            return None
        row = self._store.get_scoped("mock_exam", str(mock_exam_id), profile_id)
        if row is None:
            raise CampusError("MOCK_NOT_FOUND", f"模考不存在：{mock_exam_id}")
        return models.MockExam.from_row(row)

    def _assert_mock_open(
        self, mock: Optional[models.MockExam], question: models.QuestionBankItem
    ) -> None:
        """Refuse attempts a real exam would not accept (PRD CET-13 验收 1, CET-14)."""
        if mock is None:
            return
        self._assert_mock_ongoing(mock)
        stage = SUBJECT_STAGE.get(question.subject)
        if stage and stage in json.loads(mock.locked_stages or "[]"):
            raise CampusError("STAGE_LOCKED", f"该阶段已收卡，不可再作答：{stage}")

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
        """Refuse a title an on-desk profile already holds (A2/A4).

        An archived profile is in the box, not on the desk: it gave its name back, so it does
        not block a new one. Restoring it later is deliberately not a create — see 02 §7.2 — so
        the box and the desk can end up holding the same name, which the station's switcher
        already distinguishes by row.
        """
        row = self._store.query_one(
            'SELECT "id" FROM "exam_profile" WHERE "title" = ? AND "status" != ?',
            (title, models.ProfileStatus.ARCHIVED.value),
        )
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

    def _deadline_payload(self, row: Any) -> dict[str, Any]:
        payload = asdict(models.CertDeadline.from_row(row))
        payload["automation_ids"] = _decode(payload.get("automation_ids"), [])
        return payload
