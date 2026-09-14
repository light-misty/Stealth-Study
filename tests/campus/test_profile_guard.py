"""The profile_id guard (07 §4 T06 验收②, 08 §4 P-1/P-2/P-4).

`profile_id` is the one cross-cutting parameter of the whole campus API: 03 §4 states it is a
common parameter of nearly every endpoint, and 07 §4 T06 requires that no endpoint ever takes
a raw `profile_id` string and queries with it. These tests pin that contract against the
production `ProfileGuard` and the requests it answers:

* P-1 — a request without `profile_id` is refused, never answered with an empty result.
* P-2 — a forged `profile_id` is refused after exactly one existence probe.
* P-4 — a `finished` profile still reads, and refuses every write.

08 §4 asks for the cases to be parametrised over the endpoint groups A/B/C/D/E/F/I of 03 §4.
At T06 those endpoints do not exist yet (they arrive with T09-T14), so the parametrisation
runs over probe endpoints declared per group in this file; each probe declares exactly the
dependency the group's real endpoints will declare, on the same router prefix. When the real
endpoints land, T23 re-points the parametrisation at them without touching the guard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

ACTIVE_ID = "profile-active"
FINISHED_ID = "profile-finished"
ARCHIVED_ID = "profile-archived"
FORGED_ID = "nonexistent-uuid"

PROFILE_GROUPS = ("A", "B", "C", "D", "E", "F", "G", "H", "I")


class CountingStore(store.CampusStore):
    """A store that records the primary-key reads the guard performs."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.reads: list[tuple[str, str]] = []

    def get(self, table: str, row_id: str):
        self.reads.append((table, row_id))
        return super().get(table, row_id)

    def get_scoped(self, table: str, row_id: str, profile_id: str):
        self.reads.append((table, row_id))
        return super().get_scoped(table, row_id, profile_id)


@pytest.fixture()
def campus_store() -> CountingStore:
    instance = CountingStore(secrets.state_dir() / "campus.db")
    instance.insert(
        "exam_profile",
        {
            "id": ACTIVE_ID,
            "track_type": models.TrackType.CET.value,
            "title": "六级 12 月",
            "status": models.ProfileStatus.ACTIVE.value,
        },
    )
    instance.insert(
        "exam_profile",
        {
            "id": FINISHED_ID,
            "track_type": models.TrackType.CET.value,
            "title": "已结课的档案",
            "status": models.ProfileStatus.FINISHED.value,
        },
    )
    instance.insert(
        "exam_profile",
        {
            "id": ARCHIVED_ID,
            "track_type": models.TrackType.CET.value,
            "title": "已归档的档案",
            "status": models.ProfileStatus.ARCHIVED.value,
        },
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def guard(campus_store: CountingStore) -> routes.ProfileGuard:
    return routes.ProfileGuard(campus_store)


def _read_handler(guard: routes.ProfileGuard, group: str) -> Callable:
    def handler(profile: models.ExamProfile = Depends(guard.get_profile)) -> dict[str, str]:
        return {"group": group, "profile_id": profile.id, "status": profile.status}

    handler.__name__ = f"probe_read_{group.lower()}"
    return handler


def _write_handler(guard: routes.ProfileGuard, group: str) -> Callable:
    def handler(
        profile: models.ExamProfile = Depends(guard.get_writable_profile),
    ) -> dict[str, str]:
        return {"group": group, "profile_id": profile.id}

    handler.__name__ = f"probe_write_{group.lower()}"
    return handler


def _probe_router(guard: routes.ProfileGuard) -> APIRouter:
    router = APIRouter()
    for group in PROFILE_GROUPS:
        slug = group.lower()
        router.add_api_route(
            f"/probe/{slug}/read", _read_handler(guard, group), methods=["GET", "POST"]
        )
        router.add_api_route(
            f"/probe/{slug}/write", _write_handler(guard, group), methods=["POST"]
        )
    return router


def _app(guard: routes.ProfileGuard) -> FastAPI:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    app.include_router(_probe_router(guard), prefix=routes.CAMPUS_PREFIX)
    return app


@pytest.fixture()
def client(guard: routes.ProfileGuard) -> TestClient:
    return TestClient(_app(guard))


def _detail(response) -> dict:
    return response.json()["detail"]


@pytest.mark.parametrize("group", PROFILE_GROUPS)
def test_p1_a_read_without_a_profile_id_is_refused(client: TestClient, group: str) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/probe/{group.lower()}/read")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"
    assert _detail(response)["retryable"] is False


@pytest.mark.parametrize("group", PROFILE_GROUPS)
def test_p1_a_write_without_a_profile_id_is_refused(client: TestClient, group: str) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/probe/{group.lower()}/write", json={})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


@pytest.mark.parametrize("group", PROFILE_GROUPS)
def test_p2_a_forged_profile_id_is_refused_with_one_existence_probe(
    client: TestClient, campus_store: CountingStore, group: str
) -> None:
    campus_store.reads.clear()
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/probe/{group.lower()}/read",
        params={"profile_id": FORGED_ID},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "PROFILE_NOT_FOUND"
    assert campus_store.reads == [("exam_profile", FORGED_ID)]


def test_p4_writes_are_refused_on_a_finished_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/write", json={"profile_id": FINISHED_ID}
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_p4_reads_stay_available_on_a_finished_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/read", json={"profile_id": FINISHED_ID}
    )
    assert response.status_code == 200
    assert response.json()["status"] == models.ProfileStatus.FINISHED.value


def test_an_archived_profile_is_still_writable_because_restoring_it_is_a_write(
    client: TestClient,
) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/write", json={"profile_id": ARCHIVED_ID}
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ARCHIVED_ID


def test_an_active_profile_is_injected_into_the_endpoint(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/read", json={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200
    assert response.json() == {
        "group": "A",
        "profile_id": ACTIVE_ID,
        "status": models.ProfileStatus.ACTIVE.value,
    }


def test_profile_id_can_come_from_the_query_string(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/probe/a/read", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ACTIVE_ID


def test_profile_id_can_come_from_a_json_body(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/b/read", json={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ACTIVE_ID


def test_profile_id_can_come_from_a_urlencoded_form(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/b/read", data={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ACTIVE_ID


def test_profile_id_can_come_from_a_multipart_form(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/b/read",
        files={"file": ("notes.md", b"hello", "text/markdown")},
        data={"profile_id": ACTIVE_ID},
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ACTIVE_ID


def _path_probe_app(guard: routes.ProfileGuard) -> FastAPI:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))

    def _handler(profile: models.ExamProfile = Depends(guard.get_profile)) -> dict[str, str]:
        return {"profile_id": profile.id}

    probe = APIRouter()
    probe.add_api_route("/probe/path/{pid}", _handler, methods=["GET"])
    app.include_router(probe, prefix=routes.CAMPUS_PREFIX)
    return app


def test_profile_id_can_come_from_the_path(guard: routes.ProfileGuard) -> None:
    response = TestClient(_path_probe_app(guard)).get(
        f"{routes.CAMPUS_PREFIX}/probe/path/{FINISHED_ID}"
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == FINISHED_ID


def test_the_path_parameter_wins_over_the_query_string(guard: routes.ProfileGuard) -> None:
    response = TestClient(_path_probe_app(guard)).get(
        f"{routes.CAMPUS_PREFIX}/probe/path/{ACTIVE_ID}", params={"profile_id": FORGED_ID}
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ACTIVE_ID


def test_a_blank_profile_id_counts_as_missing(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/probe/a/read?profile_id=")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_a_whitespace_only_profile_id_counts_as_missing(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/probe/a/read?profile_id=%20%20")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_whitespace_around_a_profile_id_is_ignored(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/probe/a/read", params={"profile_id": f"  {ACTIVE_ID}  "}
    )
    assert response.status_code == 200
    assert response.json()["profile_id"] == ACTIVE_ID


def test_a_malformed_json_body_is_reported_as_a_missing_profile_not_a_server_error(
    client: TestClient,
) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/read",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_a_json_body_that_is_not_an_object_is_reported_as_a_missing_profile(
    client: TestClient,
) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/read",
        content=b'["profile_id"]',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_a_non_string_profile_id_is_reported_as_a_missing_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/probe/a/read", json={"profile_id": 17})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_an_unparsable_form_is_reported_as_a_missing_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/probe/a/read",
        content=b"--broken",
        headers={"content-type": "multipart/form-data; boundary=--broken"},
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"
