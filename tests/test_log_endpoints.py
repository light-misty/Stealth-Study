"""日志接收端点与请求上下文中间件测试。"""

from __future__ import annotations

import re

from starlette.requests import Request

from stealth_study.logging_setup import setup_logging


def _make_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from stealth_study.server import SessionManager, create_app

    monkeypatch.setenv("COWORKER_API_TOKEN", "secret-token")
    monkeypatch.setenv("SS_LOG_DIR", str(tmp_path / "log"))
    setup_logging(tmp_path)
    manager = SessionManager(workspace=tmp_path)
    return TestClient(create_app(manager))


def _frontend_log(tmp_path) -> str:
    files = sorted((tmp_path / "log").glob("frontend_*.log"))
    assert files, "frontend 日志文件不存在"
    return files[-1].read_text(encoding="utf-8")


def test_ingest_requires_token(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post("/v1/logs/frontend", json={"logs": []})
    assert resp.status_code == 401


def test_ingest_writes_frontend_file(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/v1/logs/frontend",
        headers={"X-StealthStudy-Token": "secret-token"},
        json={
            "logs": [
                {"ts": "2026-09-16 22:31:00,000", "level": "INFO", "message": "页面加载完成"}
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] == 1
    assert body["skipped"] == 0
    text = _frontend_log(tmp_path)
    assert "2026-09-16 22:31:00,000 [INFO] 页面加载完成" in text


def test_ingest_counts_invalid_entries(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/v1/logs/frontend",
        headers={"X-StealthStudy-Token": "secret-token"},
        json={
            "logs": [
                {"ts": "bad", "level": "INFO", "message": "跳过"},
                {"level": "NOPE", "message": "跳过"},
                {"ts": "2026-09-16 22:31:01,000", "level": "WARN", "message": "ok"},
            ]
        },
    )
    assert resp.json() == {"accepted": 1, "skipped": 2, "rotated": False}
    assert "跳过" not in _frontend_log(tmp_path)


def test_ingest_malformed_payload_returns_422(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/v1/logs/frontend",
        headers={"X-StealthStudy-Token": "secret-token"},
        content=b"[1,2,3]",
    )
    assert resp.status_code == 422


def test_ingest_rotates_when_max_bytes_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_LOG_MAX_BYTES", "300")
    client = _make_client(tmp_path, monkeypatch)
    merged = {"accepted": 0, "skipped": 0, "rotated": False}
    for i in range(30):
        resp = client.post(
            "/v1/logs/frontend",
            headers={"X-StealthStudy-Token": "secret-token"},
            json={"logs": [{"ts": f"2026-09-16 22:31:{i:02d},000", "level": "INFO", "message": f"row-{i}"}]},
        )
        body = resp.json()
        merged["accepted"] += body["accepted"]
        merged["rotated"] = merged["rotated"] or body["rotated"]
    assert merged["accepted"] == 30
    assert merged["rotated"] is True
    backups = list((tmp_path / "log").glob("frontend_*.log.*"))
    assert backups, "小阈值下应产生轮转备份文件"


def test_response_carries_x_request_id(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/v1/health")
    value = resp.headers.get("X-Request-ID")
    assert value and re.fullmatch(r"[0-9a-f]{8}", value)


def test_request_user_id_prefers_actor_header(tmp_path, monkeypatch):
    from stealth_study.server.app import _request_user_id

    req = Request(
        {
            "type": "http",
            "headers": [(b"x-stealthstudy-actor", b"actor-42"), (b"host", b"localhost")],
            "query_string": b"profile_id=prof-1",
            "method": "GET",
            "path": "/v1/test",
        }
    )
    assert _request_user_id(req) == "actor-42"


def test_request_user_id_falls_back_to_profile_id(tmp_path, monkeypatch):
    from stealth_study.server.app import _request_user_id

    req = Request(
        {
            "type": "http",
            "headers": [(b"host", b"localhost")],
            "query_string": b"profile_id=prof-9",
            "method": "GET",
            "path": "/v1/test",
        }
    )
    assert _request_user_id(req) == "prof-9"


def test_request_user_id_empty_without_identity(tmp_path, monkeypatch):
    from stealth_study.server.app import _request_user_id

    req = Request(
        {
            "type": "http",
            "headers": [(b"host", b"localhost")],
            "query_string": b"",
            "method": "GET",
            "path": "/v1/test",
        }
    )
    assert _request_user_id(req) == ""