"""G-06: the server-side sign-in kill switch (`campus.login_enabled`, default off).

Three contracts are covered: `/v1/cloud/status` never reports a session, `/v1/cloud/login`
and `/v1/cloud/logout` refuse with 403 instead of opening a browser, and `/auth/callback`
refuses before it can exchange a code. Flipping `[campus] login_enabled = true` restores
the upstream behaviour, which is what makes the change reversible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stealth_study.server import SessionManager, create_app


def _write_global_config(state_dir: Path, body: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "config.toml").write_text(body, encoding="utf-8")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(workspace=tmp_path)
    app = create_app(manager)
    with TestClient(app) as c:
        c.manager = manager
        yield c


def test_status_reports_signed_out_even_with_a_stored_session(client) -> None:
    client.manager.secrets.put(
        "cloud:session", {"access_token": "ya29.tok", "account": "a@b.c", "user_id": "u_1"}
    )
    assert client.get("/v1/cloud/status").json() == {
        "signed_in": False,
        "account": "",
        "user_id": "",
        "telemetry_enabled": False,
    }


def test_login_is_refused_without_opening_a_browser(client, monkeypatch) -> None:
    import webbrowser

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    resp = client.post("/v1/cloud/login")
    assert resp.status_code == 403
    assert resp.json()["error"] == "signin_disabled"
    assert opened == []


def test_logout_is_refused(client) -> None:
    resp = client.post("/v1/cloud/logout")
    assert resp.status_code == 403
    assert resp.json()["error"] == "signin_disabled"


def test_auth_callback_is_refused_before_exchanging_the_code(client) -> None:
    resp = client.get("/auth/callback", params={"code": "c", "state": "forged"})
    assert resp.status_code == 403
    assert "Sign-in disabled" in resp.text


def test_local_connector_management_still_works(client) -> None:
    client.manager.secrets.put("gmail:default", {"type": "oauth", "access_token": "t"})
    body = client.post("/v1/connectors/gmail/disconnect").json()
    assert body["ok"]
    assert client.manager.secrets.get("gmail:default") is None


def test_telemetry_toggle_still_answers_but_stays_off(client) -> None:
    body = client.post("/v1/cloud/telemetry", json={"enabled": True}).json()
    assert body["ok"]
    assert client.get("/v1/cloud/status").json()["telemetry_enabled"] is False


def test_login_enabled_true_restores_the_upstream_routes(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _write_global_config(state_dir, "[campus]\nlogin_enabled = true\n")
    monkeypatch.setenv("COWORKER_STATE_DIR", str(state_dir))
    manager = SessionManager(workspace=tmp_path)
    app = create_app(manager)
    with TestClient(app) as probe:
        probe.manager = manager
        status = probe.get("/v1/cloud/status").json()
        assert status["signed_in"] is False
        assert status["telemetry_enabled"] is True
        callback = probe.get("/auth/callback", params={"code": "c", "state": "forged"})
        assert callback.status_code == 400
        assert "Sign-in failed" in callback.text
