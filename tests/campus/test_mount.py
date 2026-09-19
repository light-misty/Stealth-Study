"""Intrusion point #9: the two-line campus mount inside `create_app()` (01 §6, 03 §2).

T06 is allowed exactly one change to an existing backend file. These tests hold that budget
literally: the patch is the documented pair of lines, it sits immediately after
`app = FastAPI(...)`, it adds nothing else, and it neither breaks the sidecar token middleware
nor turns a bad database into a silently degraded startup (03 §2-4).

G-06 widens that budget by exactly one more module. The cloud sign-in kill switch adds a
guarded early return to `/v1/cloud/login`, `/v1/cloud/logout`, `/auth/callback` and
`/v1/cloud/status` inside `create_app()`, and `ss/campus/config.py` — project-owned code, not
an upstream file — carries the `login_enabled` read that drives it. Both are pinned below, so
the wider patch still cannot reach any other backend module and the two-line mount itself
stays untouched.

The 2026-09-16 stage verification widens it by one module again: `ss/automation/store.py`
gained a `rowid DESC` tiebreaker so `unseen_failed` follows the newest run when two runs
share one timestamp. Pinned below for the same reason.

The logging-system branch widens it by one more module and one more `app.py` increment:
`ss/server/run.py` initializes the unified log config at sidecar startup, and `app.py`
gains the request-context middleware plus the `POST /v1/logs/frontend` ingest endpoint
(startup timestamp file naming + 50MB/daily rotation live in new file `ss/logging_setup.py`,
which the names-status check above deliberately ignores as a pure addition).

The inbox-fix branch widens it by one more `app.py` increment: the `/v1/inbox` endpoint
drops its cross-session visibility filter, so an attended session's parked ask_user
question lists in the Inbox exactly as the sidebar's attention count promises (6 added /
3 removed lines).
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import store

ROOT = Path(__file__).resolve().parents[2]
APP_PY = ROOT / "ss" / "server" / "app.py"
CAMPUS_PREFIX = "/v1/campus"
HEALTH_PATH = f"{CAMPUS_PREFIX}/health"

ANCHOR = "app = FastAPI("
MOUNT_IMPORT = "from ..campus.routes import build_campus_router"
MOUNT_CALL = "app.include_router(build_campus_router(manager))"

BASE_CANDIDATES = (
    "main",
    "refs/heads/main",
    "refs/remotes/origin/main",
    "refs/remotes/Stealth-Study/main",
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def _base_revision() -> str | None:
    for candidate in BASE_CANDIDATES:
        resolved = _git("rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}").strip()
        if resolved:
            return resolved
    return None


def _on_the_base_revision(base: str) -> bool:
    return _git("rev-parse", "HEAD").strip() == base


@pytest.fixture()
def app_source() -> list[str]:
    return APP_PY.read_text(encoding="utf-8").splitlines()


def test_the_mount_sits_immediately_after_the_app_is_created(app_source: list[str]) -> None:
    anchors = [index for index, line in enumerate(app_source) if line.strip().startswith(ANCHOR)]
    assert len(anchors) == 1
    at = anchors[0]
    assert app_source[at + 1].strip() == MOUNT_IMPORT
    assert app_source[at + 2].strip() == MOUNT_CALL


def test_the_mount_is_the_only_router_include_in_the_file(app_source: list[str]) -> None:
    includes = [line for line in app_source if "include_router(" in line]
    assert includes == [f"    {MOUNT_CALL}"]
    assert sum(line.count("build_campus_router") for line in app_source) == 2


# The whole registered existing-file patch (01 §6 #9, widened by G-06 and again by the
# 2026-09-16 stage verification): `config.py` is the project-owned `login_enabled` read,
# `app.py` the guarded early returns, `automation/store.py` the run-ordering fix that keeps
# `unseen_failed` keyed to the newest run when two runs share a timestamp. A diff outside
# this list — and outside `ss/campus/`, which the feature owns — means the intrusion has
# spread and must go back through review.
BACKEND_PATCH = {
    "M\tss/campus/config.py",
    "M\tss/server/app.py",
    "M\tss/automation/store.py",
    # logging-system 分支：sidecar 启动时初始化统一日志
    "M\tss/server/run.py",
    # i18n-chinese-coverage 分支：错误响应附带稳定 error_code（文案仍为原英文，见 ss/errors.py）
    "M\tss/server/manager.py",
    "M\tss/skills/store.py",
    # skip-question-card 分支（OPE-153）：ask 工具的哨兵值与跳过结算、引擎对
    # 全跳过卡片的 denied 判定、Slack 镜像为问题附带 Skip 按钮
    "M\tss/tools/ask.py",
    "M\tss/engine.py",
    "M\tss/interactions.py",
    # i18n-chinese-coverage 分支续：personas 域的清单/导出异常改抛带代号类型，云端画廊
    # 与 install/export 端点随之附带 error_code（裸文本照旧保留）
    "M\tss/personas/registry.py",
    "M\tss/cloud.py",
    # i18n-chinese-coverage 分支续：项目命名异常改抛带代号类型（定时任务与绑定域）
    "M\tss/projects.py",
    # i18n-chinese-coverage 分支续：Slack 成员目录的未分类异常改用 forwarded_error 透传原文
    "M\tss/connectors/slack_directory.py",
}
CAMPUS_OWNED_PREFIX = "ss/campus/"
# campus 挂载、日志系统、inbox 修复与错误代号四条分支各自的 app.py 增量预算
APP_PY_PATCHES = {
    "40\t2\tss/server/app.py",
    "34\t1\tss/server/app.py",
    "6\t3\tss/server/app.py",
    "27\t19\tss/server/app.py",
    "36\t25\tss/server/app.py",
}


def test_no_other_backend_module_changed_against_the_base_revision() -> None:
    base = _base_revision()
    if base is None or _on_the_base_revision(base):
        pytest.skip("no base revision to compare against from this checkout")
    status = _git("diff", "--name-status", base, "--", "ss/")
    touched = [line for line in status.splitlines() if line[:1] in {"M", "D", "R"}]
    # A subset check, not an equality: the registered patch is merged into `main`, so a branch
    # cut from it is expected to contain *none* of those edits — what this gate forbids is an
    # edit outside the registered set.
    for line in touched:
        path = line.split("\t", 1)[1]
        assert line in BACKEND_PATCH or path.startswith(CAMPUS_OWNED_PREFIX), line


def test_app_py_keeps_its_registered_budget_against_the_base_revision() -> None:
    base = _base_revision()
    if base is None or _on_the_base_revision(base):
        pytest.skip("no base revision to compare against from this checkout")
    numstat = _git("diff", "--numstat", base, "--", "ss/server/app.py").strip()
    # Either the mount and the G-06 guard are already in the base (the normal case for a new
    # feature branch), `app.py` carries exactly one of the registered patches, or nothing.
    assert numstat in {"", *APP_PY_PATCHES}


def test_create_app_serves_the_campus_health_endpoint_behind_the_sidecar_token(
    monkeypatch, tmp_path: Path
) -> None:
    from ss.server.app import create_app
    from ss.server.manager import SessionManager

    token = "t06-sidecar-token"
    monkeypatch.setenv("COWORKER_API_TOKEN", token)
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "data")))

    assert client.get(HEALTH_PATH).status_code == 401
    assert client.get(HEALTH_PATH, headers={"x-ss-token": "wrong"}).status_code == 401
    authorized = client.get(HEALTH_PATH, headers={"x-ss-token": token})
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "ok"


def test_create_app_leaves_the_existing_endpoints_alone(
    monkeypatch, tmp_path: Path
) -> None:
    from ss.server.app import create_app
    from ss.server.manager import SessionManager

    token = "t06-sidecar-token"
    monkeypatch.setenv("COWORKER_API_TOKEN", token)
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "data")))
    headers = {"x-ss-token": token}

    for path in ("/v1/health", "/v1/sessions", "/v1/settings", "/v1/automations"):
        assert client.get(path, headers=headers).status_code == 200


def test_create_app_fails_to_start_when_the_campus_database_is_newer(tmp_path: Path) -> None:
    from ss.server.app import create_app
    from ss.server.manager import SessionManager

    database = secrets.state_dir() / "campus.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute(store.SCHEMA_META_DDL)
        connection.execute(
            "INSERT INTO schema_meta (key, version, applied_at) VALUES (?, ?, ?)",
            (store.SCHEMA_VERSION_KEY, store.CURRENT_SCHEMA_VERSION + 1, "2026-09-14T00:00:00Z"),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(store.SchemaVersionError):
        create_app(SessionManager(data_dir=tmp_path / "data"))


def test_the_sidecar_entry_point_serves_the_campus_health_endpoint(tmp_path: Path) -> None:
    from ss.config import load_config
    from ss.server.run import build_app

    config = load_config()
    client = TestClient(build_app(str(tmp_path / "workspace"), config.model, config.mode))

    response = client.get(HEALTH_PATH)
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "schema_version": store.CURRENT_SCHEMA_VERSION,
        "tracks": ["cet", "kaoyan", "cert"],
    }


def test_the_campus_routes_are_published_in_the_openapi_schema(tmp_path: Path) -> None:
    from ss.server.app import create_app
    from ss.server.manager import SessionManager

    schema = create_app(SessionManager(data_dir=tmp_path / "data")).openapi()
    assert HEALTH_PATH in schema["paths"]
    assert schema["paths"][HEALTH_PATH]["get"]["tags"] == ["campus"]
