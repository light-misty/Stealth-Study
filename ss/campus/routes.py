"""campus HTTP surface — the single mounted router and the profile_id cross-cutting guard.

This is the only campus module that talks HTTP. It is mounted exactly once, from
`ss/server/app.py`'s `create_app()`, through the two lines registered as intrusion point #9
of `docs/dev/01-系统架构设计.md` §6 (form and rationale in `docs/dev/03-API接口设计.md` §2):
the campus router carries the `/v1/campus` prefix and inherits the existing sidecar token
middleware without being added to `tokenless_paths` (03 §1).

The error contract lives here. `ERROR_SPECS` is the machine-readable image of the 03 §6 code
table, and `campus_error()` / `raise_campus_error()` turn a code into the documented body
`{"detail": {"code", "message", "retryable"}}` (03 §1). Endpoints never invent a status or a
bare string; a code that is not in the table is a programming error and raises `KeyError`
instead of silently returning something plausible.

`build_campus_router()` is the factory the mount calls, so it is also where campus is
initialised: constructing it opens `campus.db` (running the migration at mount time, 02 §3.4)
and an unmigratable database aborts application startup rather than serving a half-built API.

`ProfileGuard` is the cross-cutting `profile_id` rule of 07 §4 T06: it resolves the profile a
request acts on from the path, query string, JSON body or form, and refuses unknown and
read-only profiles (`PROFILE_REQUIRED` / `PROFILE_NOT_FOUND` / `PROFILE_READ_ONLY`). Endpoints
declare `Depends(guard.get_profile)` and receive an `ExamProfile`; they never accept a raw
`profile_id` string and query with it. `scoped_row()` is the sub-resource half of the same
rule: a row owned by another profile is refused as `FORBIDDEN_PROFILE`.

Group registrations sit next to the factory that mounts them. Body shapes are Pydantic models
whose enums, patterns and ranges are taken from the campus enums and config constants
themselves, so a malformed request is refused by the framework (422) while every documented
business failure travels out of `service.py` as a `CampusError` and comes back through
`_call()` as the structured body of 03 §1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping, NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import models, tracks
from .config import MAX_DAILY_MINUTES, MIN_DAILY_MINUTES, load_campus_config
from .service import (
    MAX_DIFFICULTY,
    MIN_DIFFICULTY,
    CampusError,
    CampusService,
    ModelInventory,
)
from .store import CampusStore

CAMPUS_PREFIX = "/v1/campus"
PROFILE_ID_PARAM = "profile_id"
PROFILE_PATH_PARAM = "pid"
EXAM_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
PUSH_TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class ErrorSpec:
    """One row of the 03 §6 error table: its HTTP status, retryability and fallback text."""

    status: int
    retryable: bool = False
    message: str = ""


ERROR_SPECS: Mapping[str, ErrorSpec] = {
    "PROFILE_REQUIRED": ErrorSpec(400, False, "缺少档案参数 profile_id"),
    "PROFILE_NOT_FOUND": ErrorSpec(404, False, "档案不存在"),
    "PROFILE_READ_ONLY": ErrorSpec(409, False, "档案已结课，拒绝写入"),
    "FORBIDDEN_PROFILE": ErrorSpec(403, False, "该资源不属于当前档案"),
    "DUPLICATE_TITLE": ErrorSpec(409, False, "同名档案已存在"),
    "DUPLICATE_NODE": ErrorSpec(409, False, "同类型考试节点已存在"),
    "EXAM_DATE_REQUIRED": ErrorSpec(400, False, "请先设置考试日期"),
    "FILE_TOO_LARGE": ErrorSpec(413, False, "文件超过大小上限"),
    "UNSUPPORTED_TYPE": ErrorSpec(415, False, "不支持的文件类型"),
    "DISK_FULL": ErrorSpec(507, False, "磁盘空间不足"),
    "DOC_NOT_FOUND": ErrorSpec(404, False, "资料不存在"),
    "DOC_NOT_READY": ErrorSpec(409, True, "资料尚未解析完成"),
    "DOC_SCAN_EMPTY": ErrorSpec(422, False, "疑似扫描件，无可提取文字层"),
    "PARSE_ERROR": ErrorSpec(422, False, "导入内容格式错误"),
    "QUESTION_NOT_FOUND": ErrorSpec(404, False, "题目不存在"),
    "POINT_NOT_FOUND": ErrorSpec(404, False, "知识点不存在"),
    "ATTEMPT_NOT_FOUND": ErrorSpec(404, False, "作答记录不存在"),
    "RQ_NOT_FOUND": ErrorSpec(404, False, "复习队列项不存在"),
    "MOCK_NOT_FOUND": ErrorSpec(404, False, "模考不存在"),
    "ASSESSMENT_NOT_FOUND": ErrorSpec(404, False, "定级测评不存在"),
    "ITEM_NOT_FOUND": ErrorSpec(404, False, "复习素材不存在"),
    "INVALID_ATTRIBUTION": ErrorSpec(400, False, "错因取值非法"),
    "INVALID_LEVEL": ErrorSpec(400, False, "掌握度取值非法"),
    "ILLEGAL_TRANSITION": ErrorSpec(409, False, "任务状态流转非法"),
    "ILLEGAL_STAGE": ErrorSpec(409, False, "模考阶段流转非法"),
    "STAGE_LOCKED": ErrorSpec(409, False, "该阶段已锁定"),
    "MOCK_SUBMITTED": ErrorSpec(409, False, "模考已交卷"),
    "PAUSE_EXCEEDED": ErrorSpec(409, False, "暂停时长已超上限"),
    "ASSESSMENT_FINISHED": ErrorSpec(409, False, "定级测评已结束"),
    "MODEL_NOT_CONFIGURED": ErrorSpec(409, False, "尚未配置可用模型"),
    "MODEL_TIMEOUT": ErrorSpec(504, True, "模型调用超时"),
    "MODEL_OUTPUT_INVALID": ErrorSpec(502, True, "模型输出无法解析"),
    "RUBRIC_NOT_FOUND": ErrorSpec(404, False, "评分标准不存在"),
    "AUTOMATION_UNAVAILABLE": ErrorSpec(503, True, "自动化任务存储不可用"),
    "EXPORT_NOT_FOUND": ErrorSpec(404, False, "导出文件不存在"),
    "NO_TASK_DATA": ErrorSpec(409, False, "暂无任务数据，无法生成周报"),
    "SCHEMA_VERSION_ERROR": ErrorSpec(500, False, "数据版本高于当前应用版本"),
}


def error_detail(code: str, message: Optional[str] = None, **extra: Any) -> dict[str, Any]:
    """The documented structured error body for `code` (03 §1).

    Extra keyword arguments are merged into the body, which is how a code such as
    `PARSE_ERROR` carries its offending line number without inventing a new shape.
    """
    spec = ERROR_SPECS[code]
    detail: dict[str, Any] = {
        "code": code,
        "message": message or spec.message,
        "retryable": spec.retryable,
    }
    detail.update(extra)
    return detail


def campus_error(
    code: str,
    message: Optional[str] = None,
    *,
    status: Optional[int] = None,
    **extra: Any,
) -> HTTPException:
    """Build the `HTTPException` that returns a campus error body.

    `status` exists only for the rare defensive override; the normal path takes the status
    from the table so a code can never drift away from its documented status.
    """
    spec = ERROR_SPECS[code]
    return HTTPException(
        status_code=spec.status if status is None else status,
        detail=error_detail(code, message, **extra),
    )


def raise_campus_error(
    code: str,
    message: Optional[str] = None,
    *,
    status: Optional[int] = None,
    **extra: Any,
) -> NoReturn:
    """Raise the structured error for `code`."""
    raise campus_error(code, message, status=status, **extra)


def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run one `CampusService` call, translating its `CampusError` into the documented response.

    `service.py` owns the business rules and never imports FastAPI, so this is the single place
    a campus failure crosses into HTTP: the code selects the status, retryability and fallback
    message from `ERROR_SPECS`, and a code outside the table still fails loudly (03 §6).
    """
    try:
        return fn(*args, **kwargs)
    except CampusError as exc:
        raise_campus_error(exc.code, exc.message, **exc.extra)


async def _async_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """`_call` for the awaited endpoints (E5 drives the grading chain)."""
    try:
        return await fn(*args, **kwargs)
    except CampusError as exc:
        raise_campus_error(exc.code, exc.message, **exc.extra)


class ProfileGuard:
    """Resolve and validate the `profile_id` a profile-scoped request acts on.

    One instance lives inside the mounted router, so every endpoint of every group shares the
    same resolution order and the same refusals. The four accepted carriers cover the request
    shapes 03 §4 uses: `{pid}` path parameters (A3-A5), the `profile_id` query parameter
    (list endpoints such as B2/D1/E2), JSON bodies (C1/E5/F10) and multipart forms (B1).
    """

    def __init__(self, campus_store: CampusStore) -> None:
        self._store = campus_store

    def _clean(self, value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    async def _payload_profile_id(self, request: Request) -> Optional[str]:
        """Read `profile_id` from the request body, treating anything odd as absent."""
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                payload = json.loads(await request.body() or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            if not isinstance(payload, dict):
                return None
            return payload.get(PROFILE_ID_PARAM)
        if "form" in content_type:
            try:
                form = await request.form()
            except Exception:
                return None
            return form.get(PROFILE_ID_PARAM)
        return None

    async def requested_profile_id(self, request: Request) -> Optional[str]:
        """The profile id the request carries, or `None` when it carries none.

        Order matters only for pathological requests that carry two values; the path
        parameter is the most specific carrier and therefore wins.
        """
        candidates = (
            request.path_params.get(PROFILE_PATH_PARAM),
            request.path_params.get(PROFILE_ID_PARAM),
            request.query_params.get(PROFILE_ID_PARAM),
            await self._payload_profile_id(request),
        )
        for candidate in candidates:
            cleaned = self._clean(candidate)
            if cleaned:
                return cleaned
        return None

    def load(self, profile_id: str) -> models.ExamProfile:
        """The stored profile, or `PROFILE_NOT_FOUND`.

        This single primary-key read is the only query a forged `profile_id` costs (08 §4 P-2).
        """
        row = self._store.get("exam_profile", profile_id)
        if row is None:
            raise_campus_error("PROFILE_NOT_FOUND", f"档案不存在：{profile_id}")
        return models.ExamProfile.from_row(row)

    async def get_profile(self, request: Request) -> models.ExamProfile:
        """Dependency for every endpoint that reads profile-owned data."""
        profile_id = await self.requested_profile_id(request)
        if not profile_id:
            raise_campus_error("PROFILE_REQUIRED")
        return self.load(profile_id)

    async def get_writable_profile(self, request: Request) -> models.ExamProfile:
        """Dependency for every endpoint that writes profile-owned data.

        Only a `finished` profile is refused: 02 §7.2 keeps `active` and `archived` reversible,
        so treating archive as read-only would make restoring a profile impossible.
        """
        profile = await self.get_profile(request)
        if profile.status == models.ProfileStatus.FINISHED.value:
            raise_campus_error("PROFILE_READ_ONLY", f"档案已结课，拒绝写入：{profile.id}")
        return profile

    def scoped_row(self, table: str, row_id: str, profile_id: str, *, missing_code: str) -> Any:
        """Load a sub-resource row, refusing one that belongs to another profile.

        The scoped read (`WHERE id = ? AND profile_id = ?` — the data-layer half of the double
        insurance described in 01 §3) is the only way the row is ever loaded, so another
        profile's row yields nothing and becomes `FORBIDDEN_PROFILE` (08 §4 P-3). The unscoped
        existence probe that follows only chooses between `FORBIDDEN_PROFILE` and the group's
        own `missing_code`: 03 §6 defines both families (`ATTEMPT_NOT_FOUND`, `DOC_NOT_FOUND`,
        ...), so collapsing "absent" into the cross-profile refusal would leave them
        unreachable.
        """
        row = self._store.get_scoped(table, row_id, profile_id)
        if row is None:
            if self._store.get(table, row_id) is not None:
                raise_campus_error("FORBIDDEN_PROFILE", f"{table} 不属于当前档案：{row_id}")
            raise_campus_error(missing_code, f"{table} 不存在：{row_id}")
        return models.ROW_MODELS[table].from_row(row)


class ProfileCreate(BaseModel):
    """A2 body (03 §4.1): the track and a title are required, everything else is optional.

    `extra="forbid"` is the "never silent" half of 03 §1 — a misspelled field is refused with
    422 instead of being dropped while the caller believes it was stored.
    """

    model_config = ConfigDict(extra="forbid")

    track_type: models.TrackType
    title: str
    cert_type: Optional[models.CertType] = None
    level: Optional[models.CetLevel] = None
    exam_date: Optional[str] = Field(default=None, pattern=EXAM_DATE_PATTERN)
    target_score: Optional[int] = None
    subjects: Optional[list[str]] = None
    daily_minutes: Optional[int] = Field(default=None, ge=MIN_DAILY_MINUTES, le=MAX_DAILY_MINUTES)

    @field_validator("title")
    @classmethod
    def _title_must_carry_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be blank")
        return cleaned


class ProfilePatch(BaseModel):
    """A4 body: any subset of the mutable fields of a profile (03 §4.1 "任意可变字段").

    `track_type` is not part of the body: a profile's track decides the meaning of every row
    it owns, so an accidental track change is refused rather than silently rewriting them.
    """

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    cert_type: Optional[models.CertType] = None
    level: Optional[models.CetLevel] = None
    exam_date: Optional[str] = Field(default=None, pattern=EXAM_DATE_PATTERN)
    target_score: Optional[int] = None
    current_estimate: Optional[int] = None
    subjects: Optional[list[str]] = None
    daily_minutes: Optional[int] = Field(default=None, ge=MIN_DAILY_MINUTES, le=MAX_DAILY_MINUTES)
    status: Optional[models.ProfileStatus] = None

    @field_validator("title")
    @classmethod
    def _title_must_carry_content(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be blank")
        return cleaned


class CampusSettingsPatch(BaseModel):
    """A7 preference body: the G-09 set (02 §4.2 `campus_settings`).

    Ranges and patterns are the same ones `config.py` applies to the TOML defaults, so the API
    and the config file cannot drift into accepting different values.
    """

    model_config = ConfigDict(extra="forbid")

    daily_minutes: Optional[int] = Field(default=None, ge=MIN_DAILY_MINUTES, le=MAX_DAILY_MINUTES)
    push_time: Optional[str] = Field(default=None, pattern=PUSH_TIME_PATTERN)
    review_intensity: Optional[models.ReviewIntensity] = None
    task_models: Optional[dict[models.CampusTask, Optional[str]]] = None


class AppStatePatch(BaseModel):
    """A7 body: the active profile pointer and/or a partial preference patch (03 §4.1)."""

    model_config = ConfigDict(extra="forbid")

    active_profile_id: Optional[str] = None
    settings: Optional[CampusSettingsPatch] = None


class QuestionOption(BaseModel):
    """One choice of a question, as stored in `question_bank_item.options` (02 §4.12)."""

    model_config = ConfigDict(extra="forbid")

    key: str
    text: str

    @field_validator("key", "text")
    @classmethod
    def _must_carry_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("option key and text must not be blank")
        return cleaned


class QuestionImport(BaseModel):
    """E1 body (03 §4.5): the payload format and its raw text."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    format: Literal["md", "csv"]
    content: str


class QuestionCreate(BaseModel):
    """E3 body: the question itself; `profile_id` is the cross-cutting guard parameter."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    subject: str
    stem: str
    qtype: models.QuestionType = models.QuestionType.SINGLE
    point_id: Optional[str] = None
    options: Optional[list[QuestionOption]] = None
    answer: Optional[str] = None
    answer_meta: Optional[dict[str, Any]] = None
    max_score: Optional[float] = Field(default=None, gt=0)
    difficulty: Optional[int] = Field(default=None, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)
    source: Optional[models.QuestionSource] = None
    doc_id: Optional[str] = None

    @field_validator("subject", "stem")
    @classmethod
    def _must_carry_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("subject and stem must not be blank")
        return cleaned


class QuestionPatch(BaseModel):
    """E4 body: any subset of a question's fields, plus the guard's `profile_id`.

    An explicit `null` clears a nullable field (`options`, `answer`, `point_id`), which is how a
    question is reduced back to its stem without a dedicated endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    subject: Optional[str] = None
    stem: Optional[str] = None
    qtype: Optional[models.QuestionType] = None
    point_id: Optional[str] = None
    options: Optional[list[QuestionOption]] = None
    answer: Optional[str] = None
    answer_meta: Optional[dict[str, Any]] = None
    max_score: Optional[float] = Field(default=None, gt=0)
    difficulty: Optional[int] = Field(default=None, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)
    source: Optional[models.QuestionSource] = None
    doc_id: Optional[str] = None

    @field_validator("subject", "stem")
    @classmethod
    def _must_carry_content(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("subject and stem must not be blank")
        return cleaned


class AttemptCreate(BaseModel):
    """E5 body (03 §4.5): which question was answered, in what context, and with what."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    question_id: str
    session_type: models.SessionType = models.SessionType.PRACTICE
    mock_exam_id: Optional[str] = None
    answer: str

    @field_validator("answer")
    @classmethod
    def _must_carry_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value


class PlanGenerate(BaseModel):
    """F5 body (03 §4.4): the profile is the only input — exam date, subjects and budget
    already live on the profile, so the request cannot contradict them."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str


def build_campus_router(manager: Any) -> APIRouter:
    """Build the router that `create_app()` mounts under `/v1/campus` (03 §2).

    `manager` is the sidecar `SessionManager` the documented mount passes in; campus only
    needs it for the automation templates of T13, and holding campus state must never touch
    the kernel's own stores (01 §4.3).

    Opening the router opens `campus.db`, so the migration of 02 §3.4 runs here: a schema
    written by a newer application raises `SchemaVersionError` and stops startup.

    The service, the guard and the store are built here and shared by every endpoint of every
    group, which is what keeps `campus.db` a single handle for the whole application (02 §2.1).
    """
    campus_store = CampusStore()
    campus_config = load_campus_config()
    campus_service = CampusService(
        campus_store,
        campus_config,
        inventory=ModelInventory.from_manager(manager),
        provider_host=manager,
    )
    guard = ProfileGuard(campus_store)
    router = APIRouter(prefix=CAMPUS_PREFIX, tags=["campus"])

    @router.get("/health")
    def campus_health() -> dict[str, Any]:
        """Liveness plus the schema version the running database is actually on."""
        return {
            "status": "ok",
            "schema_version": campus_store.current_version(),
            "tracks": list(tracks.TRACK_IDS),
        }

    # -- A 组：全局与设置（03 §4.1）------------------------------------------

    @router.get("/profiles")
    def campus_list_profiles(
        track: Optional[models.TrackType] = None,
        status: Optional[models.ProfileStatus] = None,
    ) -> dict[str, Any]:
        """A1 — every profile, optionally narrowed by track and status."""
        return {
            "items": _call(
                campus_service.list_profiles,
                track=track.value if track is not None else None,
                status=status.value if status is not None else None,
            )
        }

    @router.post("/profiles")
    def campus_create_profile(body: ProfileCreate) -> dict[str, Any]:
        """A2 — create a profile; a title already in use is `DUPLICATE_TITLE`."""
        return _call(campus_service.create_profile, body.model_dump())

    @router.get("/profiles/{pid}")
    def campus_get_profile(
        profile: models.ExamProfile = Depends(guard.get_profile),
    ) -> dict[str, Any]:
        """A3 — one profile, resolved and ownership-checked by the guard."""
        return _call(campus_service.get_profile, profile.id)

    @router.patch("/profiles/{pid}")
    def campus_patch_profile(
        body: ProfilePatch,
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
    ) -> dict[str, Any]:
        """A4 — partial update; a `finished` profile refuses every write (02 §7.2)."""
        return _call(
            campus_service.update_profile, profile, body.model_dump(exclude_unset=True)
        )

    @router.delete("/profiles/{pid}")
    def campus_delete_profile(
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
    ) -> dict[str, Any]:
        """A5 — delete the profile with its whole subtree (02 §7.3)."""
        return _call(campus_service.delete_profile, profile)

    @router.get("/app-state")
    def campus_get_app_state() -> dict[str, Any]:
        """A6 — the active profile pointer plus the resolved campus preferences.

        Deliberately profile-free: `app_state` is global, so this endpoint carries neither a
        `profile_id` nor one of the guard dependencies.
        """
        return _call(campus_service.app_state)

    @router.patch("/app-state")
    def campus_patch_app_state(body: AppStatePatch) -> dict[str, Any]:
        """A7 — switch the active profile and/or merge preference changes."""
        return _call(
            campus_service.update_app_state,
            body.model_dump(exclude_unset=True, mode="json"),
        )

    @router.get("/capabilities")
    def campus_capabilities() -> dict[str, Any]:
        """A8 — the static model recommendation list plus what this machine can run."""
        return _call(campus_service.capabilities)

    @router.get("/privacy")
    def campus_privacy() -> dict[str, Any]:
        """A9 — local data layout, its size, and the model endpoints in use."""
        return _call(campus_service.privacy)

    @router.delete("/privacy/data")
    def campus_wipe_data() -> dict[str, Any]:
        """A10 — clear local campus data: `campus.db` rebuilt empty plus the `campus/` tree."""
        return _call(campus_service.wipe_data)

    # -- E 组：题库与作答（03 §4.5）----------------------------------------

    def scoped_question(
        qid: str, profile: models.ExamProfile = Depends(guard.get_profile)
    ) -> models.QuestionBankItem:
        """Resolve a question of the request's profile (`FORBIDDEN_PROFILE` for anyone else's)."""
        return guard.scoped_row(
            "question_bank_item", qid, profile.id, missing_code="QUESTION_NOT_FOUND"
        )

    @router.post("/questions/import")
    def campus_import_questions(
        body: QuestionImport,
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
    ) -> dict[str, Any]:
        """E1 — import MD/CSV questions; a broken payload is `PARSE_ERROR` with its line."""
        return _call(campus_service.import_questions, profile, body.format, body.content)

    @router.get("/questions")
    def campus_list_questions(
        profile: models.ExamProfile = Depends(guard.get_profile),
        point_id: Optional[str] = None,
        qtype: Optional[models.QuestionType] = None,
        subject: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    ) -> dict[str, Any]:
        """E2 — one page of the profile's question bank."""
        return _call(
            campus_service.list_questions,
            profile,
            point_id=point_id,
            qtype=qtype.value if qtype is not None else None,
            subject=subject,
            page=page,
            page_size=page_size,
        )

    @router.post("/questions")
    def campus_create_question(
        body: QuestionCreate,
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
    ) -> dict[str, Any]:
        """E3 — add one question by hand."""
        return _call(
            campus_service.create_question,
            profile,
            body.model_dump(mode="json", exclude_unset=True),
        )

    @router.patch("/questions/{qid}")
    def campus_patch_question(
        body: QuestionPatch,
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
        question: models.QuestionBankItem = Depends(scoped_question),
    ) -> dict[str, Any]:
        """E4 — partial update; the writable check runs before the row is even looked up."""
        return _call(
            campus_service.update_question,
            profile,
            question,
            body.model_dump(mode="json", exclude_unset=True),
        )

    @router.delete("/questions/{qid}")
    def campus_delete_question(
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
        question: models.QuestionBankItem = Depends(scoped_question),
    ) -> dict[str, Any]:
        """E4 — delete one question of the profile."""
        return _call(campus_service.delete_question, profile, question)

    def scoped_attempt_question(
        body: AttemptCreate,
        profile: models.ExamProfile = Depends(guard.get_profile),
    ) -> models.QuestionBankItem:
        """Resolve the question E5 answers, which the body names instead of the path."""
        return guard.scoped_row(
            "question_bank_item", body.question_id, profile.id, missing_code="QUESTION_NOT_FOUND"
        )

    @router.post("/attempts")
    async def campus_submit_attempt(
        body: AttemptCreate,
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
        question: models.QuestionBankItem = Depends(scoped_attempt_question),
    ) -> dict[str, Any]:
        """E5 — record an answer; objective questions are judged, subjective ones graded."""
        return await _async_call(
            campus_service.submit_attempt,
            profile,
            question,
            body.model_dump(mode="json", exclude_unset=True),
        )

    # -- F5：计划生成（03 §4.4，KY-01/02 与 CET-03 按 TrackSpec 分台共用）---

    @router.post("/plans/generate")
    async def campus_generate_plan(
        body: PlanGenerate,
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
    ) -> dict[str, Any]:
        """F5 — lay out weekly and daily tasks from today to the exam date."""
        return await _async_call(campus_service.generate_plan, profile)

    # -- G1：今日建议 / 自建看板（03 §4.7）---------------------------------

    @router.get("/tasks")
    def campus_list_tasks(
        profile: models.ExamProfile = Depends(guard.get_profile),
        date: Optional[str] = Query(default=None, pattern=EXAM_DATE_PATTERN),
        status: Optional[models.PlanTaskStatus] = None,
        track: Optional[str] = None,
    ) -> dict[str, Any]:
        """G1 — the profile's plan tasks; `date=<today>` is the today suggestion."""
        return {
            "items": _call(
                campus_service.list_tasks,
                profile,
                date=date,
                status=status.value if status is not None else None,
                track=track,
            )
        }

    return router
