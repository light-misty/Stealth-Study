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
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, NoReturn, Optional

from fastapi import APIRouter, HTTPException, Request

from . import models, tracks
from .store import CampusStore

CAMPUS_PREFIX = "/v1/campus"
PROFILE_ID_PARAM = "profile_id"
PROFILE_PATH_PARAM = "pid"


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


def build_campus_router(manager: Any) -> APIRouter:
    """Build the router that `create_app()` mounts under `/v1/campus` (03 §2).

    `manager` is the sidecar `SessionManager` the documented mount passes in; campus only
    needs it for the automation templates of T13, and holding campus state must never touch
    the kernel's own stores (01 §4.3).

    Opening the router opens `campus.db`, so the migration of 02 §3.4 runs here: a schema
    written by a newer application raises `SchemaVersionError` and stops startup.
    """
    campus_store = CampusStore()
    router = APIRouter(prefix=CAMPUS_PREFIX, tags=["campus"])

    @router.get("/health")
    def campus_health() -> dict[str, Any]:
        """Liveness plus the schema version the running database is actually on."""
        return {
            "status": "ok",
            "schema_version": campus_store.current_version(),
            "tracks": list(tracks.TRACK_IDS),
        }

    return router
