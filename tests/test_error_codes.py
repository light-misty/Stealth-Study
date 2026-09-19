"""错误代号分类器（中文化方案 C）：常见异常给稳定代号，长尾退回 UNCLASSIFIED。

服务端仍照原样发英文 `error` 文本（日志与旧客户端不变），额外附带 `error_code`；
前端按代号查语言包，查不到时才显示原文。这里锁定分类结果，避免异常文本
被直接印到中文界面上。
"""

from __future__ import annotations

import errno
import re
import socket
import subprocess
from pathlib import Path

import httpx
import pytest

from ss.errors import (
    CODES,
    UNCLASSIFIED,
    CodedValueError,
    _ERRNO_CODES,
    _TEXT_CODES,
    _WINDOWS_CODES,
    error_code,
    error_payload,
)


def _oserror(code: int, winerror: int | None = None) -> OSError:
    err = OSError(code, f"oserror {code}")
    if winerror is not None:
        err.winerror = winerror  # type: ignore[attr-defined]
    return err


# 下面三张表既是分类器的用例，也是「这个代号真的会被产出」的证据：
# test_registry_codes_are_all_reachable 直接从它们推导可达集合，删掉一行分支就会露出死代号。
_FILESYSTEM_CASES: list[tuple[BaseException, str]] = [
    (PermissionError(errno.EACCES, "Permission denied"), "PERMISSION_DENIED"),
    (_oserror(errno.EACCES, 5), "PERMISSION_DENIED"),
    (_oserror(errno.EACCES, 13), "PERMISSION_DENIED"),
    (FileNotFoundError(errno.ENOENT, "No such file or directory"), "PATH_NOT_FOUND"),
    (_oserror(errno.ENOENT, 2), "PATH_NOT_FOUND"),
    (_oserror(errno.ENOENT, 3), "PATH_NOT_FOUND"),
    (_oserror(errno.EEXIST, 183), "PATH_ALREADY_EXISTS"),
    (OSError(errno.EEXIST, "already exists"), "PATH_ALREADY_EXISTS"),
    (_oserror(errno.EBUSY, 32), "FILE_LOCKED"),
    (_oserror(0, 32), "FILE_LOCKED"),
    (_oserror(0, 33), "FILE_LOCKED"),
    (_oserror(errno.ENOSPC, 112), "DISK_FULL"),
    (OSError(errno.ENOSPC, "No space left on device"), "DISK_FULL"),
    (OSError(errno.EROFS, "read-only file system"), "DISK_READONLY"),
    (_oserror(errno.ENAMETOOLONG, 206), "PATH_TOO_LONG"),
    (IsADirectoryError(errno.EISDIR, "Is a directory"), "PATH_INVALID"),
    (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"), "ENCODING"),
]

_NETWORK_CASES: list[tuple[BaseException, str]] = [
    (httpx.ConnectTimeout("timed out"), "NETWORK_TIMEOUT"),
    (httpx.ReadTimeout("read timed out"), "NETWORK_TIMEOUT"),
    (httpx.PoolTimeout("pool timeout"), "NETWORK_TIMEOUT"),
    (TimeoutError("operation timed out"), "NETWORK_TIMEOUT"),
    (socket.timeout("timed out"), "NETWORK_TIMEOUT"),
    (httpx.ConnectError("[WinError 10061] No connection could be made"), "NETWORK_UNREACHABLE"),
    (socket.gaierror("getaddrinfo failed"), "NETWORK_UNREACHABLE"),
    (ConnectionRefusedError("Connection refused"), "NETWORK_UNREACHABLE"),
    (ConnectionResetError("Connection reset by peer"), "NETWORK_RESET"),
    (httpx.RemoteProtocolError("bad frame"), "NETWORK_PROTOCOL"),
]

_HTTP_STATUS_CASES: list[tuple[int, str]] = [
    (401, "AUTH_FAILED"),
    (403, "AUTH_FAILED"),
    (429, "RATE_LIMITED"),
    (404, "HTTP_NOT_FOUND"),
    (409, "CONFLICT"),
    (418, "HTTP_CLIENT_ERROR"),
    (500, "HTTP_SERVER_ERROR"),
]

# 只有带 context 才会走到的分支，由下面两个专用用例证明。
_CONTEXT_CODES = {"EXECUTABLE_NOT_FOUND", "FILE_MANAGER_UNAVAILABLE"}


@pytest.mark.parametrize("exc,expected", _FILESYSTEM_CASES)
def test_filesystem_exceptions_map_to_codes(exc: BaseException, expected: str) -> None:
    assert error_code(exc) == expected


@pytest.mark.parametrize("exc,expected", _NETWORK_CASES)
def test_network_exceptions_map_to_codes(exc: BaseException, expected: str) -> None:
    assert error_code(exc) == expected


def _status_exc(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/v1/x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"Client error '{status}'", request=request, response=response)


@pytest.mark.parametrize("status,expected", _HTTP_STATUS_CASES)
def test_http_status_exceptions_map_to_codes(status: int, expected: str) -> None:
    assert error_code(_status_exc(status)) == expected


def test_spawn_context_distinguishes_a_missing_executable() -> None:
    exc = FileNotFoundError(errno.ENOENT, "No such file or directory: 'openworker-server'")
    assert error_code(exc) == "PATH_NOT_FOUND"
    assert error_code(exc, context="spawn") == "EXECUTABLE_NOT_FOUND"


def test_reveal_context_blames_the_file_manager_not_the_path() -> None:
    exc = FileNotFoundError(errno.ENOENT, "No such file or directory: 'explorer'")
    assert error_code(exc, context="reveal") == "FILE_MANAGER_UNAVAILABLE"
    assert error_code(PermissionError(errno.EACCES, "denied"), context="reveal") == "FILE_MANAGER_UNAVAILABLE"


def test_a_real_mkdir_failure_is_classified_not_unclassified(tmp_path: Path) -> None:
    """构造出的 OSError 只能证明映射表，这里验真实系统调用抛出的异常确实能被分类。"""
    blocker = tmp_path / "regular.txt"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(OSError) as info:
        (blocker / "child").mkdir(parents=True)
    assert error_code(info.value) != UNCLASSIFIED


def test_a_real_missing_executable_launch_is_classified(tmp_path: Path) -> None:
    with pytest.raises(OSError) as info:
        subprocess.Popen(["definitely-not-a-real-binary-8f3a1c"])
    assert error_code(info.value) == "PATH_NOT_FOUND"
    assert error_code(info.value, context="spawn") == "EXECUTABLE_NOT_FOUND"


def test_coded_value_error_is_still_a_value_error() -> None:
    """子系统既有 `except ValueError` 与 pytest.raises(ValueError) 必须原样成立。"""
    exc = CodedValueError("SKILL_NOT_FOUND", "Unknown skill: weekly-report", name="weekly-report")
    assert isinstance(exc, ValueError)
    assert str(exc) == "Unknown skill: weekly-report"


def test_coded_error_carries_code_and_interpolation_params() -> None:
    exc = CodedValueError("SKILL_NOT_FOUND", "Unknown skill: weekly-report", name="weekly-report")
    assert error_code(exc) == "SKILL_NOT_FOUND"
    assert error_payload(exc, ok=False) == {
        "error": "Unknown skill: weekly-report",
        "error_code": "SKILL_NOT_FOUND",
        "error_params": {"name": "weekly-report"},
        "ok": False,
    }


def test_coded_error_omits_params_when_there_are_none() -> None:
    exc = CodedValueError("SKILL_NAME_REQUIRED", "Skill name is required.")
    assert error_payload(exc) == {
        "error": "Skill name is required.",
        "error_code": "SKILL_NAME_REQUIRED",
    }


def test_any_exception_carrying_error_code_is_honoured() -> None:
    class LegacyOSError(OSError):
        error_code = "DISK_FULL"  # type: ignore[misc]

    exc = LegacyOSError(28, "No space left on device")
    assert error_code(exc) == "DISK_FULL"


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("board item id must be an integer"),
        RuntimeError("MCP server exited with code 1"),
        Exception("something the classifier has never seen"),
    ],
)
def test_long_tail_stays_unclassified(exc: BaseException) -> None:
    assert error_code(exc) == UNCLASSIFIED


def test_payload_keeps_the_original_english_and_adds_the_code() -> None:
    exc = PermissionError(errno.EACCES, "[WinError 5] Access is denied: 'D:\\repo'")
    payload = error_payload(exc)
    assert payload["error"] == str(exc)
    assert payload["error_code"] == "PERMISSION_DENIED"


def test_payload_supports_extra_fields_and_a_message_override() -> None:
    exc = RuntimeError("boom")
    payload = error_payload(exc, "could not promote", tools=[], retryable=False)
    assert payload == {
        "error": "could not promote",
        "error_code": UNCLASSIFIED,
        "tools": [],
        "retryable": False,
    }


def test_payload_survives_an_empty_exception() -> None:
    payload = error_payload(ValueError())
    assert payload["error_code"] == UNCLASSIFIED
    assert payload["error"] == ""


def _locale(path: str) -> dict:
    import json
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("code", sorted(CODES))
def test_every_code_has_a_locale_string_in_both_languages(code: str) -> None:
    key = code.lower()
    for name in ("en.json", "zh.json"):
        tree = _locale(f"surfaces/gui/src/locales/{name}")
        entry = tree.get("error", {}).get(key)
        assert isinstance(entry, str) and entry, f"{name} 缺少 error.{key}"


# 中文值里允许出现的技术标识：文件名、格式名与协议名，翻成中文反而更差。
# 不能用 \b —— `.zip` 以句点开头，前一个字符是空格时根本没有词边界。
_LATIN_OK = re.compile(r"SKILL\.md|\.zip|\.md|YAML|MCP|Slack", re.IGNORECASE)


@pytest.mark.parametrize("code", sorted(CODES))
def test_chinese_error_strings_hold_no_english_prose(code: str) -> None:
    if code == UNCLASSIFIED:
        pytest.skip("兜底条目允许把原文一并显示")
    tree = _locale("surfaces/gui/src/locales/zh.json")
    text = tree["error"][code.lower()]
    stripped = _LATIN_OK.sub("", re.sub(r"\{\{[^}]*\}\}", "", text))
    assert re.search(r"[A-Za-z]{2,}", stripped) is None, (
        f"error.{code.lower()} 中文值残留英文单词：{text!r}"
    )


_CODE_LITERALS = re.compile(
    r'CodedValueError\(\s*"([A-Z][A-Z0-9_]{3,})"'
    r'|coded_error\((?:[^()]|\([^()]*\))*?"([A-Z][A-Z0-9_]{3,})"',
    re.DOTALL,
)

_ROOT = Path(__file__).resolve().parents[1]


def _subsystem_codes() -> set[str]:
    """代码里真写出来的代号。扫整棵 `ss/` 树，新增站点自动进登记表，不必再维护文件清单。"""
    found: set[str] = set()
    for path in sorted((_ROOT / "ss").rglob("*.py")):
        for groups in _CODE_LITERALS.findall(path.read_text(encoding="utf-8")):
            found |= {value for value in groups if value}
    return found


def _proven_codes() -> set[str]:
    """分类器确实能产出、或子系统确实会抛出的全部代号 —— 每条都有用例或真实抛点为证。"""
    proven = {expected for _, expected in _FILESYSTEM_CASES}
    proven |= {expected for _, expected in _NETWORK_CASES}
    proven |= {expected for _, expected in _HTTP_STATUS_CASES}
    proven |= _CONTEXT_CODES
    proven |= set(_ERRNO_CODES.values()) | set(_WINDOWS_CODES.values())
    proven |= {code for _, code in _TEXT_CODES}
    proven |= _subsystem_codes()
    proven.add(UNCLASSIFIED)
    return proven


def test_classifiers_never_invent_a_code_outside_the_registry() -> None:
    assert _proven_codes() <= CODES


def test_registry_codes_are_all_reachable() -> None:
    # 表里列了却永远不会产出的代号就是死文案，逼着要么接上要么删掉。
    assert _proven_codes() == CODES
