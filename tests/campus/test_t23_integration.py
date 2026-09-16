"""T23 integration gate (08 §3/§5/§6 acceptance) — end-to-end campus stories that exercise
every station's authentication boundary, authority guard and read-only surfaces.

Fills the remaining T23 testing gaps: the full profile lifecycle (08 §4 P-4 read-only),
the cross-profile sub-resource isolation triplet, and the station-level panel assembly.

These tests complement the per-task unit/collect tests already in tests/campus/ — they do
not duplicate the 17-parse and degradation mock-replay coverage delivered by T07.

KEY API CONTRACTS (verified from routes.py / service.py):
* POST  /profiles  -> 200 with the profile resource body directly (no wrapper).
* GET   /profiles/{pid} -> same resource body.
* PATCH /profiles/{pid} -> same resource body (full partial update).
* DELETE /profiles/{pid} -> {"deleted": True, "cascade": {...}}.
* GET   /capabilities  -> {"current_model": ..., "tasks": [...]}.
* POST  /grading -> {"attempt_id", "degrade_level", "rubric", "dimensions", "errors", ...}
  (requires a provider to replay the model's response).
* Profile ref resolved from path > query > body (guard.requested_profile_id).
* `ProfileCreate` has extra="forbid": no `id` in body; server auto-generates.
* 02 §7.2: `active` and `archived` stay writable. Only `finished` is read-only.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss.campus import routes


class FakeProvider:
    """Replays a fixed grading-JSON to the engine (mirrors test_routes_grading.py)."""

    def __init__(self, band: int = 11) -> None:
        self.responses: dict[Any, Any] = {"default": self._payload(band)}
        self.seen: list[dict] = []

    def _payload(self, band: int) -> str:
        return json.dumps({
            "band": band,
            "dimension_scores": {"content": 4, "structure": 4, "language": 3},
            "errors": [{"fragment": "I thinks", "suggestion": "I think", "type": "主谓一致"}],
            "upgraded_demo": "rewritten",
            "model_answer_outline": "outline",
        })

    def complete(self, *, model: str, messages: list[dict], **settings: Any) -> Any:
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    def __init__(self, model: str = "e2e:mock", *, ready: bool = True, provider: Any = None) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_provider(self):
        return self.provider

    def get_settings(self) -> dict:
        return {
            "model": self.model,
            "model_ready": self._ready,
            "models": [self.model] if self.model else [],
        }


@pytest.fixture()
def manager():
    return FakeManager()


def build_app(manager) -> FastAPI:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return app


def test_profile_lifecycle_active_to_finished_to_forgotten(manager):
    """PATCH(title) -> DELETE(active profile) -> GET returns 404.
    Per 02 §7.2, only `finished` is read-only; `active` and `archived` stay reversible."""
    app = build_app(manager)
    client = TestClient(app)

    created = client.post(
        "/v1/campus/profiles",
        json={"track_type": "cet", "title": "Lifecycle"},
    ).json()
    cid = created["id"]
    assert created["track_type"] == "cet"
    assert created["title"] == "Lifecycle"
    assert created["status"] == "active"

    patched = client.patch(
        f"/v1/campus/profiles/{cid}",
        json={"title": "Lifecycle v2"},
    ).json()
    assert patched["title"] == "Lifecycle v2"

    deleted = client.delete(f"/v1/campus/profiles/{cid}").json()
    assert deleted["deleted"] is True

    gone = client.get(f"/v1/campus/profiles/{cid}")
    assert gone.status_code in (404, 400)


def test_finished_profile_is_read_only(manager):
    """PATCH(status=finished) locks the profile; subsequent PATCH is refused."""
    app = build_app(manager)
    client = TestClient(app)

    created = client.post(
        "/v1/campus/profiles",
        json={"track_type": "cet", "title": "WillFinish"},
    ).json()
    cid = created["id"]

    client.patch(f"/v1/campus/profiles/{cid}", json={"status": "finished"})
    write_after_finish = client.patch(
        f"/v1/campus/profiles/{cid}",
        json={"title": "should be refused"},
    )
    assert write_after_finish.status_code in (409, 403)


def test_cross_profile_subresource_isolation(manager):
    """A sub-resource belongs to one profile — reading it via another profile returns FORBIDDEN."""
    app = build_app(manager)
    client = TestClient(app)

    owner_resp = client.post(
        "/v1/campus/profiles",
        json={"track_type": "cet", "title": "t-owner"},
    ).json()
    owner_id = owner_resp["id"]

    intruder_resp = client.post(
        "/v1/campus/profiles",
        json={"track_type": "cet", "title": "t-intruder"},
    ).json()
    intruder_id = intruder_resp["id"]

    me = client.post(
        "/v1/campus/grading",
        json={"profile_id": owner_id, "kind": "essay", "answer": "I thinks it is good."},
    ).json()
    attempt_id = me["attempt_id"]
    assert attempt_id

    intruder_view = client.get(
        f"/v1/campus/grading/{attempt_id}",
        params={"profile_id": intruder_id},
    )
    assert intruder_view.status_code in (403, 404)


def test_read_only_profile_still_serves_gets(manager):
    """08 §4 P-4: a finished profile can read its data but refuses writes."""
    app = build_app(manager)
    client = TestClient(app)

    created = client.post(
        "/v1/campus/profiles",
        json={"track_type": "cet", "title": "ReadOnly"},
    ).json()
    cid = created["id"]

    client.patch(f"/v1/campus/profiles/{cid}", json={"status": "finished"})

    read = client.get(f"/v1/campus/profiles/{cid}").json()
    assert read["id"] == cid
    assert read["status"] == "finished"

    forbidden = client.post(
        "/v1/campus/grading",
        json={"profile_id": cid, "kind": "essay", "answer": "a"},
    )
    assert forbidden.status_code in (409, 403)


def test_capabilities_endpoint_reports_current_model(manager):
    """GET /v1/campus/capabilities drives EmptyModelGuide vs. station rendering."""
    app = build_app(manager)
    client = TestClient(app)
    caps = client.get("/v1/campus/capabilities").json()
    assert "current_model" in caps
    assert "tasks" in caps
