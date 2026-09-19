"""异常 → 稳定错误代号（03 §1 错误契约在非 campus 侧的延伸）。

界面上显示什么文字由前端的 `error.*` 语言包决定，因此这里只负责把异常归到
一个稳定代号：常见故障（权限、路径、磁盘、网络、HTTP 状态）各给一个，剩下的
一律 `UNCLASSIFIED`，由前端退回显示原始文本。异常原文始终原样保留在 `error`
字段里，日志与旧客户端的行为不变。
"""

from __future__ import annotations

import errno as _errno
import socket
from typing import Any, Mapping, Optional

import httpx

UNCLASSIFIED = "UNCLASSIFIED"

# 前端 `error.<小写代号>` 必须逐条备齐，由 tests/test_error_codes.py 守住。
CODES: frozenset[str] = frozenset(
    {
        "ARTIFACT_BINARY",
        "ARTIFACT_MISSING",
        "ARTIFACT_TOO_LARGE",
        "AUTH_FAILED",
        "CLOUD_SIGNIN_REQUIRED",
        "CONFLICT",
        "DESTINATION_NOT_EMPTY",
        "DESTINATION_REQUIRED",
        "DISK_FULL",
        "DISK_READONLY",
        "ENCODING",
        "EXECUTABLE_NOT_FOUND",
        "FILE_LOCKED",
        "FILE_MANAGER_UNAVAILABLE",
        "FOLDER_MISSING",
        "HTTP_CLIENT_ERROR",
        "HTTP_NOT_FOUND",
        "HTTP_SERVER_ERROR",
        "INVALID_SESSION_ID",
        "MCP_SERVER_UNKNOWN",
        "NETWORK_PROTOCOL",
        "NETWORK_RESET",
        "NETWORK_TIMEOUT",
        "NETWORK_UNREACHABLE",
        "NOT_A_DIRECTORY",
        "NOT_A_TEMP_SESSION",
        "PATH_ALREADY_EXISTS",
        "PATH_ESCAPES_ROOT",
        "PATH_INVALID",
        "PATH_NOT_FOUND",
        "PATH_REQUIRED",
        "PATH_TOO_LONG",
        "PERMISSION_DENIED",
        "PERSONA_ARCHIVE_ENCODING",
        "PERSONA_ARCHIVE_INVALID",
        "PERSONA_ARCHIVE_UNSAFE",
        "PERSONA_BUILTIN_PROTECTED",
        "PERSONA_BUNDLE_MISSING",
        "PERSONA_GALLERY_UNAVAILABLE",
        "PERSONA_HASH_MISMATCH",
        "PERSONA_MANIFEST_INVALID",
        "PERSONA_MANIFEST_MISSING",
        "PERSONA_MANIFESTS_MISSING",
        "PERSONA_NO_BUNDLE",
        "PERSONA_SOURCE_REQUIRED",
        "PERSONA_UNKNOWN",
        "PRIMARY_FOLDER_PROTECTED",
        "RATE_LIMITED",
        "SESSION_BUSY",
        "SKILL_ALREADY_EXISTS",
        "SKILL_ALREADY_EXISTS_TARGET",
        "SKILL_ARCHIVE_INVALID",
        "SKILL_ARCHIVE_NOT_ONE",
        "SKILL_ARCHIVE_UNSAFE",
        "SKILL_FILE_TYPE_INVALID",
        "SKILL_FOLDER_ESCAPES_SCOPE",
        "SKILL_FOLDER_UNREADABLE",
        "SKILL_FRONTMATTER_MISSING",
        "SKILL_INSTRUCTIONS_REQUIRED",
        "SKILL_NAME_INVALID",
        "SKILL_NAME_REQUIRED",
        "SKILL_NAME_TOO_LONG",
        "SKILL_NOT_FOUND",
        "SKILL_SCOPE_UNKNOWN",
        "SKILL_UPLOAD_UNKNOWN",
        "SKILL_WORKSPACE_REQUIRED",
        "SKILL_WORKSPACE_SCRATCH",
        "SKILL_WORKSPACE_UNKNOWN",
        "TLS_VERIFICATION",
        UNCLASSIFIED,
        "WORKSPACE_MISSING",
    }
)

_WINDOWS_CODES: Mapping[int, str] = {
    2: "PATH_NOT_FOUND",
    3: "PATH_NOT_FOUND",
    5: "PERMISSION_DENIED",
    32: "FILE_LOCKED",
    33: "FILE_LOCKED",
    112: "DISK_FULL",
    183: "PATH_ALREADY_EXISTS",
    206: "PATH_TOO_LONG",
}

_ERRNO_CODES: Mapping[int, str] = {
    _errno.EACCES: "PERMISSION_DENIED",
    _errno.EPERM: "PERMISSION_DENIED",
    _errno.EEXIST: "PATH_ALREADY_EXISTS",
    _errno.ENAMETOOLONG: "PATH_TOO_LONG",
    _errno.ENOENT: "PATH_NOT_FOUND",
    _errno.ENOSPC: "DISK_FULL",
    _errno.EROFS: "DISK_READONLY",
}

_TEXT_CODES: tuple[tuple[str, str], ...] = (
    ("access is denied", "PERMISSION_DENIED"),
    ("permission denied", "PERMISSION_DENIED"),
    ("operation not permitted", "PERMISSION_DENIED"),
    ("no such file or directory", "PATH_NOT_FOUND"),
    ("cannot find the path specified", "PATH_NOT_FOUND"),
    ("already exists", "PATH_ALREADY_EXISTS"),
    ("the process cannot access the file", "FILE_LOCKED"),
    ("being used by another process", "FILE_LOCKED"),
    ("resource temporarily unavailable", "FILE_LOCKED"),
    ("no space left on device", "DISK_FULL"),
    ("disk full", "DISK_FULL"),
    ("read-only file system", "DISK_READONLY"),
    ("filename or extension is too long", "PATH_TOO_LONG"),
    ("timed out", "NETWORK_TIMEOUT"),
    ("timeout", "NETWORK_TIMEOUT"),
    ("connection refused", "NETWORK_UNREACHABLE"),
    ("could not connect to proxy", "NETWORK_UNREACHABLE"),
    ("getaddrinfo failed", "NETWORK_UNREACHABLE"),
    ("name or service not known", "NETWORK_UNREACHABLE"),
    ("nodename nor servname provided", "NETWORK_UNREACHABLE"),
    ("unreachable", "NETWORK_UNREACHABLE"),
    ("certificate verify failed", "TLS_VERIFICATION"),
    ("ssl", "TLS_VERIFICATION"),
    ("not authorized", "AUTH_FAILED"),
    ("authentication failed", "AUTH_FAILED"),
    ("unauthorized", "AUTH_FAILED"),
    ("forbidden", "AUTH_FAILED"),
    ("too many requests", "RATE_LIMITED"),
)


class CodedValueError(ValueError):
    """A validation failure that already knows its code, so the GUI can localize it.

    Subclasses ValueError on purpose: every existing `except ValueError` and
    `pytest.raises(ValueError, match=...)` in the subsystems keeps working unchanged,
    and the message text stays byte-identical for logs and for those assertions.
    """

    def __init__(self, code: str, message: str, **params: Any) -> None:
        super().__init__(message)
        self.error_code = code
        self.error_params = params


def _carried_code(exc: BaseException) -> Optional[str]:
    value = getattr(exc, "error_code", None)
    return value if isinstance(value, str) and value else None


def _carried_params(exc: BaseException) -> Optional[dict[str, Any]]:
    value = getattr(exc, "error_params", None)
    return value if isinstance(value, dict) and value else None


def _winerror(exc: BaseException) -> Optional[int]:
    value = getattr(exc, "winerror", None)
    return value if isinstance(value, int) else None


def _errno_value(exc: BaseException) -> Optional[int]:
    value = getattr(exc, "errno", None)
    return value if isinstance(value, int) else None


def _http_status(exc: BaseException) -> Optional[int]:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _status_code(status: int) -> Optional[str]:
    if status in (401, 403):
        return "AUTH_FAILED"
    if status == 404:
        return "HTTP_NOT_FOUND"
    if status == 409:
        return "CONFLICT"
    if status == 429:
        return "RATE_LIMITED"
    if 400 <= status < 500:
        return "HTTP_CLIENT_ERROR"
    if status >= 500:
        return "HTTP_SERVER_ERROR"
    return None


def error_code(exc: BaseException, context: Optional[str] = None) -> str:
    """The stable code for an exception; `context` distinguishes same-type call sites.

    `spawn` = we tried to launch an executable; `reveal` = we tried to hand a path to the
    desktop's file manager, where a missing entry means the file manager is missing.
    """
    carried = _carried_code(exc)
    if carried:
        return carried
    if context == "reveal":
        return "FILE_MANAGER_UNAVAILABLE"
    if context == "spawn" and isinstance(exc, FileNotFoundError):
        return "EXECUTABLE_NOT_FOUND"

    if isinstance(exc, httpx.HTTPStatusError):
        status = _http_status(exc)
        if status is not None:
            mapped = _status_code(status)
            if mapped:
                return mapped
    elif isinstance(exc, httpx.TimeoutException):
        return "NETWORK_TIMEOUT"
    elif isinstance(exc, httpx.NetworkError):
        return "NETWORK_UNREACHABLE"
    elif isinstance(exc, httpx.ProtocolError):
        return "NETWORK_PROTOCOL"
    elif isinstance(exc, httpx.HTTPError):
        return "NETWORK_UNREACHABLE"

    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "NETWORK_TIMEOUT"
    if isinstance(exc, ConnectionError):
        if isinstance(exc, ConnectionResetError):
            return "NETWORK_RESET"
        return "NETWORK_UNREACHABLE"

    win = _winerror(exc)
    num = _errno_value(exc)
    if num is not None and num in _ERRNO_CODES:
        return _ERRNO_CODES[num]
    if isinstance(exc, FileNotFoundError):
        return "PATH_NOT_FOUND"
    if isinstance(exc, FileExistsError):
        return "PATH_ALREADY_EXISTS"
    if isinstance(exc, NotADirectoryError):
        return "PATH_NOT_FOUND"
    if isinstance(exc, IsADirectoryError):
        return "PATH_INVALID"
    if isinstance(exc, PermissionError):
        return "PERMISSION_DENIED"
    if win is not None and win in _WINDOWS_CODES:
        return _WINDOWS_CODES[win]
    if isinstance(exc, socket.gaierror):
        return "NETWORK_UNREACHABLE"
    if isinstance(exc, UnicodeDecodeError):
        return "ENCODING"

    text = str(exc).lower()
    if text:
        for marker, code in _TEXT_CODES:
            if marker in text:
                return code
    return UNCLASSIFIED


def error_payload(
    exc: BaseException,
    message: Optional[str] = None,
    *,
    context: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    """`{"error": <原文或改写>, "error_code": <代号>}` plus any caller fields."""
    payload: dict[str, Any] = {"error": str(exc) if message is None else message}
    payload["error_code"] = error_code(exc, context)
    params = _carried_params(exc)
    if params:
        payload["error_params"] = params
    payload.update(extra)
    return payload


def forwarded_error(
    exc: BaseException, message: Optional[str] = None, **extra: Any
) -> dict[str, Any]:
    """Forward an exception raised somewhere else, and only claim a code when one applies.

    A catch-all that always classifies would print "Something went wrong" over a
    third-party sentence the user actually needs (`fatal: repository not found`), so an
    unclassified exception keeps its own text and simply carries no code — the GUI then
    shows the raw, which is the honest answer.
    """
    if error_code(exc) == UNCLASSIFIED:
        payload: dict[str, Any] = {"error": str(exc) if message is None else message}
        payload.update(extra)
        return payload
    return error_payload(exc, message, **extra)


def coded_error(message: str, code: str, **extra: Any) -> dict[str, Any]:
    """A hand-written message that already has a code (validation guards, no exception)."""
    payload: dict[str, Any] = {"error": message, "error_code": code}
    payload.update(extra)
    return payload
