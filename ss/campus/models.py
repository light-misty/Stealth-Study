"""Data models for the campus (exam-prep) application layer.

Two things live here, both declared in `docs/dev/01-系统架构设计.md` §2.1 and
`docs/dev/02-数据库设计.md`:

1. The column enums every `campus.db` TEXT column is validated against before a write
   (02 §1.3: "全部用 TEXT 存小写字符串，取值见各表'取值'列").
2. One row dataclass per table — a faithful image of a result row, so JSON columns stay
   TEXT here and are decoded by the caller (02 §1.3: "读取时 json.loads").

`TABLE_COLUMNS` is the declared column list of each table; `tests/campus/test_store.py`
cross-checks it against the DDL `store.py` actually creates, so the two cannot drift.

`TASK_MODEL_CHOICES` is the static per-task model list (ADR-06, INF-08) that replaces the
runtime capability probe `providers/base.py` cannot provide.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, Optional


class CampusEnum(str, Enum):
    """Base class for campus enums.

    Subclassing `str` keeps values round-trippable through sqlite TEXT columns and
    `json.dumps` without a custom encoder. `__str__` is pinned to the plain value so an
    f-string can never leak `"TrackType.CET"` into a column: `enum.StrEnum` would do this
    too, but it only exists from Python 3.11 and this project supports 3.10.
    """

    __str__ = str.__str__

    @classmethod
    def from_value(cls, value: str) -> "CampusEnum":
        """Validate a raw column value, raising `ValueError` when it is out of range."""
        return cls(value)


class TrackType(CampusEnum):
    CET = "cet"
    KAOYAN = "kaoyan"
    CERT = "cert"
    OTHER = "other"


class CertType(CampusEnum):
    TEACHING = "teaching"
    NCRE = "ncre"
    LAW = "law"
    CPA = "cpa"
    OTHER = "other"


class CetLevel(CampusEnum):
    CET4 = "cet4"
    CET6 = "cet6"


class ProfileStatus(CampusEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FINISHED = "finished"


class DegreeType(CampusEnum):
    ACADEMIC = "academic"
    PROFESSIONAL = "professional"


class DocFileType(CampusEnum):
    PDF = "pdf"
    MD = "md"
    TXT = "txt"


class ParseStatus(CampusEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class ChunkType(CampusEnum):
    PAGE = "page"
    SECTION = "section"
    SPLIT = "split"


class KnowledgeSource(CampusEnum):
    MANUAL = "manual"
    AI_GENERATED = "ai_generated"
    IMPORTED = "imported"


class MasteryLevel(CampusEnum):
    UNKNOWN = "unknown"
    FUZZY = "fuzzy"
    MASTERED = "mastered"


class MasteryDimension(CampusEnum):
    CONCEPT = "concept"
    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    TRANSLATION = "translation"


class Subject(CampusEnum):
    """Subject / question-type code for the fixed CET and KY tracks.

    CERT subjects are user-authored (02 §4.3: the knowledge-point tree carries them), so
    they are stored as free-form strings instead of being constrained by this enum.
    """

    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    TRANSLATION = "translation"
    VOCAB = "vocab"
    POLITICS = "politics"
    ENGLISH = "english"
    MATH = "math"
    MAJOR = "major"


class PlanTrack(CampusEnum):
    OVERALL = "overall"
    POLITICS = "politics"
    ENGLISH = "english"
    MATH = "math"
    MAJOR = "major"


class PlanStage(CampusEnum):
    FOUNDATION = "foundation"
    INTENSIVE = "intensive"
    PASTPAPER = "pastpaper"
    SPRINT = "sprint"


class PlanSource(CampusEnum):
    AI_GENERATED = "ai_generated"
    MANUAL = "manual"


class PlanTaskStatus(CampusEnum):
    TODO = "todo"
    DOING = "doing"
    REVIEW = "review"
    DONE = "done"
    SKIPPED = "skipped"


class ExampleSource(CampusEnum):
    PAST_PAPER = "past_paper"
    AI = "ai"


class QuestionType(CampusEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    JUDGE = "judge"
    BLANK = "blank"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    MATERIAL = "material"
    LESSON_PLAN = "lesson_plan"
    PRACTICAL = "practical"


class QuestionSource(CampusEnum):
    MANUAL = "manual"
    AI = "ai"
    IMPORTED = "imported"
    PAST_PAPER = "past_paper"


class SessionType(CampusEnum):
    PRACTICE = "practice"
    MOCK = "mock"
    ASSESSMENT = "assessment"
    GRADING = "grading"


class Attribution(CampusEnum):
    CONCEPT_UNCLEAR = "concept_unclear"
    MISREAD = "misread"
    CALCULATION_OR_OPERATION = "calculation_or_operation"
    OUT_OF_SCOPE = "out_of_scope"
    TIME_SHORT = "time_short"
    PENDING = "pending"


class ReviewItemType(CampusEnum):
    MISTAKE = "mistake"
    VOCAB = "vocab"
    KNOWLEDGE_POINT = "knowledge_point"


class ReviewStatus(CampusEnum):
    PENDING = "pending"
    DONE = "done"
    DROPPED = "dropped"


class MockStage(CampusEnum):
    WRITING = "writing"
    LISTENING = "listening"
    READING_TRANSLATION = "reading_translation"
    GRADED = "graded"


class MockStatus(CampusEnum):
    ONGOING = "ongoing"
    SUBMITTED = "submitted"
    GRADED = "graded"
    ABANDONED = "abandoned"


class AssessmentStatus(CampusEnum):
    DRAFT = "draft"
    FINISHED = "finished"


class DeadlineNodeType(CampusEnum):
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSE = "registration_close"
    PAYMENT_CLOSE = "payment_close"
    ADMISSION_TICKET = "admission_ticket"
    EXAM = "exam"
    SCORE_QUERY = "score_query"


class ReviewIntensity(CampusEnum):
    LIGHT = "light"
    STANDARD = "standard"
    INTENSE = "intense"


class CampusTask(CampusEnum):
    GRADING = "grading"
    QUESTION = "question"
    EXPLAIN = "explain"


ALL_ENUMS: tuple[type[CampusEnum], ...] = (
    TrackType,
    CertType,
    CetLevel,
    ProfileStatus,
    DegreeType,
    DocFileType,
    ParseStatus,
    ChunkType,
    KnowledgeSource,
    MasteryLevel,
    MasteryDimension,
    Subject,
    PlanTrack,
    PlanStage,
    PlanSource,
    PlanTaskStatus,
    ExampleSource,
    QuestionType,
    QuestionSource,
    SessionType,
    Attribution,
    ReviewItemType,
    ReviewStatus,
    MockStage,
    MockStatus,
    AssessmentStatus,
    DeadlineNodeType,
    ReviewIntensity,
    CampusTask,
)


def _columns_of(row: Any) -> set[str]:
    if row is None:
        raise ValueError("row is None")
    if isinstance(row, dict):
        return set(row)
    try:
        return set(row.keys())
    except AttributeError as exc:
        raise ValueError(f"unsupported row type: {type(row)!r}") from exc


@dataclass(slots=True)
class _Row:
    """Mapping back-end shared by every row dataclass."""

    @classmethod
    def from_row(cls, row: Any) -> Any:
        """Build an instance from a `sqlite3.Row` or a plain mapping.

        Columns the source does not carry are left at their declared default, so a
        partial `SELECT` (for example a list query that skips heavy TEXT columns) still
        materialises.
        """
        if row is None:
            raise ValueError("row is None")
        get = row.get if isinstance(row, dict) else row.__getitem__
        available = _columns_of(row)
        values: dict[str, Any] = {}
        for field in fields(cls):
            if field.name in available:
                values[field.name] = get(field.name)
        return cls(**values)


@dataclass(slots=True)
class SchemaMeta(_Row):
    key: str
    version: int
    applied_at: str


@dataclass(slots=True)
class AppState(_Row):
    key: str
    value: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class ExamProfile(_Row):
    id: str
    track_type: str
    title: str
    cert_type: Optional[str] = None
    level: Optional[str] = None
    exam_date: Optional[str] = None
    target_score: Optional[int] = None
    current_estimate: Optional[int] = None
    subjects: Optional[str] = "[]"
    daily_minutes: Optional[int] = 60
    status: str = ProfileStatus.ACTIVE.value
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class SchoolProfile(_Row):
    id: str
    profile_id: str
    school: Optional[str] = ""
    major: Optional[str] = ""
    degree_type: Optional[str] = None
    subjects: Optional[str] = "[]"
    enroll_count: Optional[int] = None
    recommend_ratio: Optional[float] = None
    past_scores: Optional[str] = "[]"
    books: Optional[str] = "[]"
    note: Optional[str] = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class SourceDoc(_Row):
    id: str
    profile_id: str
    title: str
    file_path: str
    file_type: str = DocFileType.PDF.value
    page_count: Optional[int] = 0
    parse_status: str = ParseStatus.PENDING.value
    fail_reason: Optional[str] = None
    chunk_count: Optional[int] = 0
    char_count: Optional[int] = 0
    imported_at: Optional[str] = None


@dataclass(slots=True)
class DocChunk(_Row):
    id: str
    doc_id: str
    profile_id: str
    page_no: int
    content: str
    chunk_type: str = ChunkType.PAGE.value
    section_title: Optional[str] = None
    char_start: Optional[int] = 0
    char_end: Optional[int] = 0
    token_est: Optional[int] = 0
    created_at: Optional[str] = None


@dataclass(slots=True)
class KnowledgePoint(_Row):
    id: str
    profile_id: str
    title: str
    parent_id: Optional[str] = None
    desc: Optional[str] = None
    order_index: int = 0
    source: str = KnowledgeSource.MANUAL.value
    question_count: int = 0
    mistake_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class Mastery(_Row):
    id: str
    profile_id: str
    level: str = MasteryLevel.UNKNOWN.value
    point_id: Optional[str] = None
    dimension: Optional[str] = None
    score_0_100: Optional[int] = None
    evidence: Optional[str] = ""
    updated_at: Optional[str] = None


@dataclass(slots=True)
class StudyPlan(_Row):
    id: str
    profile_id: str
    track: Optional[str] = None
    stage: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    goal_desc: Optional[str] = ""
    source: str = PlanSource.AI_GENERATED.value
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class PlanTask(_Row):
    id: str
    plan_id: str
    profile_id: str
    title: str
    subject: str
    scheduled_date: str
    detail: Optional[str] = ""
    est_minutes: Optional[int] = 30
    priority: int = 2
    status: str = PlanTaskStatus.TODO.value
    board_card_id: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class VocabItem(_Row):
    id: str
    profile_id: str
    word: str
    phonetic: Optional[str] = ""
    meaning: Optional[str] = ""
    example: Optional[str] = ""
    example_source: Optional[str] = ExampleSource.AI.value
    freq_rank: Optional[int] = None
    mastery: str = MasteryLevel.UNKNOWN.value
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class QuestionBankItem(_Row):
    id: str
    profile_id: str
    subject: str
    stem: str
    qtype: str = QuestionType.SINGLE.value
    point_id: Optional[str] = None
    options: Optional[str] = None
    answer: Optional[str] = None
    answer_meta: Optional[str] = None
    max_score: float = 1
    difficulty: Optional[int] = None
    source: str = QuestionSource.MANUAL.value
    doc_id: Optional[str] = None
    created_at: Optional[str] = None


@dataclass(slots=True)
class Attempt(_Row):
    id: str
    profile_id: str
    track_type: str
    subject: str
    user_answer: str
    question_id: Optional[str] = None
    session_type: str = SessionType.PRACTICE.value
    mock_exam_id: Optional[str] = None
    is_correct: Optional[int] = None
    score: Optional[float] = None
    max_score: Optional[float] = None
    grading_json: Optional[str] = None
    degrade_level: Optional[int] = None
    model_used: Optional[str] = None
    created_at: Optional[str] = None


@dataclass(slots=True)
class MistakeBookEntry(_Row):
    id: str
    profile_id: str
    attempt_id: str
    track_type: str
    subject: str
    question_id: Optional[str] = None
    point_id: Optional[str] = None
    attribution: str = Attribution.PENDING.value
    attribution_confidence: Optional[float] = None
    wrong_count: int = 1
    last_wrong_at: Optional[str] = None
    resolved: int = 0
    note: Optional[str] = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class ReviewItem(_Row):
    id: str
    profile_id: str
    item_type: str
    item_id: str
    due_at: str
    interval_days: int = 1
    streak_right: int = 0
    ease: float = 2.5
    status: str = ReviewStatus.PENDING.value
    last_reviewed_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass(slots=True)
class MockExam(_Row):
    id: str
    profile_id: str
    paper_title: str
    started_at: str
    current_stage: Optional[str] = MockStage.WRITING.value
    stage_deadline: Optional[str] = None
    paused_seconds: int = 0
    locked_stages: str = "[]"
    status: str = MockStatus.ONGOING.value
    estimate_score: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class Assessment(_Row):
    id: str
    profile_id: str
    started_at: str
    status: str = AssessmentStatus.DRAFT.value
    question_ids: str = "[]"
    answers: str = "{}"
    scores: Optional[str] = None
    finished_at: Optional[str] = None


@dataclass(slots=True)
class WeeklyReport(_Row):
    id: str
    profile_id: str
    week_start: str
    week_end: str
    completion_rate: str = "{}"
    top_mistake_points: str = "[]"
    content_md: str = ""
    suggestion: Optional[str] = ""
    created_at: Optional[str] = None


@dataclass(slots=True)
class CertDeadline(_Row):
    id: str
    profile_id: str
    node_type: str
    date: str
    is_reference: int = 0
    automation_ids: str = "[]"
    note: Optional[str] = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


ROW_MODELS: dict[str, type] = {
    "schema_meta": SchemaMeta,
    "app_state": AppState,
    "exam_profile": ExamProfile,
    "school_profile": SchoolProfile,
    "source_doc": SourceDoc,
    "doc_chunk": DocChunk,
    "knowledge_point": KnowledgePoint,
    "mastery": Mastery,
    "study_plan": StudyPlan,
    "plan_task": PlanTask,
    "vocab_item": VocabItem,
    "question_bank_item": QuestionBankItem,
    "attempt": Attempt,
    "mistake_book": MistakeBookEntry,
    "review_queue": ReviewItem,
    "mock_exam": MockExam,
    "assessment": Assessment,
    "weekly_report": WeeklyReport,
    "cert_deadline": CertDeadline,
}

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    name: tuple(field.name for field in fields(model))
    for name, model in ROW_MODELS.items()
    if is_dataclass(model)
}


@dataclass(frozen=True)
class ModelChoice:
    """A task's recommended model and the weakest model that still passes (ADR-06)."""

    task: str
    recommended: str
    minimum: str


TASK_MODEL_CHOICES: dict[str, ModelChoice] = {
    CampusTask.GRADING.value: ModelChoice(
        CampusTask.GRADING.value, "anthropic:claude-opus-4-8", "deepseek:deepseek-v4-pro"
    ),
    CampusTask.QUESTION.value: ModelChoice(
        CampusTask.QUESTION.value, "gpt-5.6-sol", "zai:glm-5.2"
    ),
    CampusTask.EXPLAIN.value: ModelChoice(
        CampusTask.EXPLAIN.value,
        "anthropic:claude-sonnet-4-6",
        "deepseek:deepseek-v4-flash",
    ),
}

GRADING_KINDS: frozenset[str] = frozenset(
    {
        "essay",
        "translation",
        "short_answer",
        "essay_material",
        "lesson_plan",
        "practical",
    }
)

_KIND_TASKS: dict[str, str] = {
    **{kind: CampusTask.GRADING.value for kind in sorted(GRADING_KINDS)},
    "question": CampusTask.QUESTION.value,
    "explain": CampusTask.EXPLAIN.value,
}

DEFAULT_TASK: str = CampusTask.EXPLAIN.value


def task_for_kind(kind: str) -> str:
    """Map a request kind (grading kind or task name) onto a `CampusTask` value."""
    return _KIND_TASKS.get(str(kind), DEFAULT_TASK)


def pick_for_task(task: str) -> tuple[str, str]:
    """Return `(recommended, minimum)` model ids for a `CampusTask` value."""
    choice = TASK_MODEL_CHOICES[task]
    return choice.recommended, choice.minimum


def pick(kind: str, track_type: Optional[str] = None) -> tuple[str, str]:
    """Model picker handed to the grading engine (06 §2.2).

    `track_type` is part of the agreed signature but does not change the static list —
    the list is keyed by task, not by track.
    """
    del track_type
    return pick_for_task(task_for_kind(kind))
