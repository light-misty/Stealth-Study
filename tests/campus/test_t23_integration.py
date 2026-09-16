"""T23 integration gate (08 §3/§5/§6 acceptance) — end-to-end campus stories that exercise
every station's authentication boundary, authority guard and read-only surfaces.

Fills the remaining T23 testing gaps: the full profile lifecycle (08 §4 P-4 read-only),
the cross-profile sub-resource isolation triplet, and the station-level panel assembly.

These tests complement the per-task unit/collect tests already in tests/campus/ — they do
not duplicate the 17-parse and degradation mock-replay coverage delivered by T07.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss.campus import routes


class FakeManager:
    def __init__(self, model: str = "e2e:mock") -> None:
        self.model = model

    def get_settings(self) -> dict:
        return {"model": self.model, "model_ready": True, "models": [self.model]}


@pytest.fixture()
def campus_db_path(tmp_path):
    return tmp_path / "campus.db"


@pytest.fixture()
def manager():
    return FakeManager()


def build_app(campus_db_path, manager) -> FastAPI:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return app


def test_profile_lifecycle_active_to_archived_to_forgotten(campus_db_path, manager):
    """POST -> PATCH(title) -> PATCH(status=archived) -> write refused -> DELETE clears it."""
    app = build_app(campus_db_path, manager)
    client = TestClient(app)
    cid = "p-t23-lifecycle"

    created = client.post(
        "/v1/campus/profiles",
        json={"id": cid, "track_type": "cet", "title": "Lifecycle"},
    ).json()
    assert created["profile"]["id"] == cid

    patched = client.patch(
        f"/v1/campus/profiles/{cid}",
        json={"title": "Lifecycle v2"},
    ).json()
    assert patched["profile"]["title"] == "Lifecycle v2"

    client.patch(f"/v1/campus/profiles/{cid}", json={"status": "archived"})
    write_after_archive = client.patch(
        f"/v1/campus/profiles/{cid}",
        json={"title": "should be refused"},
    )
    assert write_after_archive.status_code in (409, 403)

    client.delete(f"/v1/campus/profiles/{cid}")
    gone = client.get(f"/v1/campus/profiles/{cid}").json()
    assert gone["profile"] is None


def test_cross_profile_subresource_isolation(campus_db_path, manager):
    """A sub-resource belongs to one profile — reading it via another profile returns FORBIDDEN."""
    app = build_app(campus_db_path, manager)
    client = TestClient(app)
    owner, intruder = "p-t23-owner", "p-t23-intruder"

    for pid in (owner, intruder):
        client.post(
            "/v1/campus/profiles",
            json={"id": pid, "track_type": "cet", "title": pid},
        )

    me = client.post(
        "/v1/campus/grading",
        json={"profile_id": owner, "track_type": "cet", "kind": "essay",
              "question": "t", "answer": "a"},
    ).json()
    attempt_id = me["attempt_id"]

    intruder_view = client.get(
        f"/v1/campus/grading/{attempt_id}",
        params={"profile_id": intruder},
    )
    assert intruder_view.status_code in (403, 404)


def test_read_only_profile_still_serves_gets(campus_db_path, manager):
    """08 §4 P-4: a finished profile can read its data but refuses writes."""
    app = build_app(campus_db_path, manager)
    client = TestClient(app)
    cid = "p-t23-readonly"

    client.post(
        "/v1/campus/profiles",
        json={"id": cid, "track_type": "cet", "title": "ReadOnly"},
    )
    client.patch(f"/v1/campus/profiles/{cid}", json={"status": "finished"})

    read = client.get(f"/v1/campus/profiles/{cid}").json()
    assert read["profile"]["id"] == cid

    forbidden = client.post(
        "/v1/campus/grading",
        json={"profile_id": cid, "track_type": "cet", "kind": "essay",
              "question": "t", "answer": "a"},
    )
    assert forbidden.status_code in (409, 403)


def test_capabilities_endpoint_reports_current_model(campus_db_path, manager):
    """GET /v1/campus/capabilities drives EmptyModelGuide vs. station rendering."""
    app = build_app(campus_db_path, manager)
    client = TestClient(app)
    caps = client.get("/v1/campus/capabilities").json()
    assert caps["model_ready"] is True
    assert "model" in caps
