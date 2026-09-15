"""A 组端点：全局与设置（03 §4.1 A1-A10、07 §4 T09 验收①③）。

A 组是 campus 的第一个真实端点组，因此这里同时钉住三件事：端点的契约形状、档案 CRUD 的
业务规则（`DUPLICATE_TITLE` / `PROFILE_READ_ONLY` / 级联删除），以及 service 层"查询强制带
`profile_id`"的隔离承诺（01 §3）。用例走真实 HTTP 路径（TestClient → router → service → store），
不 mock provider 之外的任何东西。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

ACTIVE_ID = "profile-active"
FINISHED_ID = "profile-finished"
ARCHIVED_ID = "profile-archived"
FORGED_ID = "nonexistent-uuid"


class FakeProvider:
    """Stands in for the sidecar's `ProviderClient` (`complete(*, model, messages, **settings)`)."""

    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses or {}
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        from types import SimpleNamespace

        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    """The slice of `SessionManager` campus reads: `.model`, `.get_settings()`, `.provider`."""

    def __init__(
        self,
        model: str = "fake:model",
        *,
        ready: bool = True,
        provider: Any = None,
    ) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "model_ready": self._ready,
            "models": [self.model] if self.model else [],
        }


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture()
def seeded_store(campus_db_path: Path) -> store.CampusStore:
    """A second handle on the same `campus.db`, used to seed and to inspect rows directly."""
    instance = store.CampusStore(campus_db_path)
    for profile_id, status, title, track in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月", models.TrackType.CET.value),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课", models.TrackType.CET.value),
        (ARCHIVED_ID, models.ProfileStatus.ARCHIVED.value, "已归档", models.TrackType.CERT.value),
    ):
        instance.insert(
            "exam_profile",
            {"id": profile_id, "track_type": track, "title": title, "status": status},
        )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(manager: FakeManager, seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return TestClient(app)


def _detail(response) -> dict:
    return response.json()["detail"]


def _profile_ids(response) -> set[str]:
    return {item["id"] for item in response.json()["items"]}


# ---------------------------------------------------------------------------
# A1 GET /profiles
# ---------------------------------------------------------------------------

def test_a1_lists_every_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/profiles")
    assert response.status_code == 200
    assert _profile_ids(response) == {ACTIVE_ID, FINISHED_ID, ARCHIVED_ID}


def test_a1_decodes_the_subjects_json_column(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.update("exam_profile", ACTIVE_ID, {"subjects": '["listening", "reading"]'})
    body = client.get(f"{routes.CAMPUS_PREFIX}/profiles").json()
    profile = next(item for item in body["items"] if item["id"] == ACTIVE_ID)
    assert profile["subjects"] == ["listening", "reading"]


def test_a1_filters_by_track_and_status(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/profiles",
        params={"track": models.TrackType.CERT.value, "status": models.ProfileStatus.ARCHIVED.value},
    )
    assert _profile_ids(response) == {ARCHIVED_ID}


def test_a1_keeps_archived_profiles_listed_because_they_can_be_restored(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/profiles", params={"track": models.TrackType.CERT.value}
    )
    assert _profile_ids(response) == {ARCHIVED_ID}


def test_a1_rejects_an_unknown_track_value(client: TestClient) -> None:
    assert client.get(f"{routes.CAMPUS_PREFIX}/profiles", params={"track": "nope"}).status_code == 422


# ---------------------------------------------------------------------------
# A2 POST /profiles
# ---------------------------------------------------------------------------

def test_a2_creates_a_profile_with_documented_defaults(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/profiles",
        json={"track_type": models.TrackType.KAOYAN.value, "title": "2027 考研"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "2027 考研"
    assert body["track_type"] == models.TrackType.KAOYAN.value
    assert body["status"] == models.ProfileStatus.ACTIVE.value
    assert body["subjects"] == []
    assert body["daily_minutes"] == 60
    assert body["exam_date"] is None
    assert body["id"]


def test_a2_persists_the_optional_fields(client: TestClient) -> None:
    body = client.post(
        f"{routes.CAMPUS_PREFIX}/profiles",
        json={
            "track_type": models.TrackType.CET.value,
            "title": "六级 6 月",
            "level": models.CetLevel.CET6.value,
            "exam_date": "2027-06-13",
            "target_score": 500,
            "subjects": ["listening", "reading"],
            "daily_minutes": 90,
        },
    ).json()
    assert body["level"] == models.CetLevel.CET6.value
    assert body["exam_date"] == "2027-06-13"
    assert body["target_score"] == 500
    assert body["subjects"] == ["listening", "reading"]
    assert body["daily_minutes"] == 90


def test_a2_refuses_a_duplicate_title(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/profiles",
        json={"track_type": models.TrackType.CET.value, "title": "六级 12 月"},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "DUPLICATE_TITLE"
    assert _detail(response)["retryable"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"track_type": models.TrackType.CET.value},
        {"track_type": models.TrackType.CET.value, "title": "   "},
        {"track_type": "nope", "title": "标题"},
        {"track_type": models.TrackType.CET.value, "title": "标题", "exam_date": "2027/06/13"},
        {"track_type": models.TrackType.CET.value, "title": "标题", "daily_minutes": 0},
    ],
)
def test_a2_rejects_malformed_bodies(client: TestClient, payload: dict) -> None:
    assert client.post(f"{routes.CAMPUS_PREFIX}/profiles", json=payload).status_code == 422


def test_a2_leaves_the_database_untouched_on_a_rejected_body(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    rejected = client.post(
        f"{routes.CAMPUS_PREFIX}/profiles", json={"track_type": "nope", "title": "标题"}
    )
    assert rejected.status_code == 422
    assert seeded_store.count("exam_profile") == 3


# ---------------------------------------------------------------------------
# A3 GET /profiles/{pid}
# ---------------------------------------------------------------------------

def test_a3_returns_the_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}")
    assert response.status_code == 200
    assert response.json()["id"] == ACTIVE_ID


def test_a3_returns_a_structured_not_found(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/profiles/{FORGED_ID}")
    assert response.status_code == 404
    assert _detail(response)["code"] == "PROFILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# A4 PATCH /profiles/{pid}
# ---------------------------------------------------------------------------

def test_a4_updates_only_the_supplied_fields(client: TestClient) -> None:
    body = client.patch(
        f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}",
        json={"target_score": 500, "daily_minutes": 45},
    ).json()
    assert body["target_score"] == 500
    assert body["daily_minutes"] == 45
    assert body["title"] == "六级 12 月"


def test_a4_archives_and_restores_a_profile(client: TestClient) -> None:
    archived = client.patch(
        f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}",
        json={"status": models.ProfileStatus.ARCHIVED.value},
    )
    assert archived.status_code == 200
    restored = client.patch(
        f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}",
        json={"status": models.ProfileStatus.ACTIVE.value},
    )
    assert restored.json()["status"] == models.ProfileStatus.ACTIVE.value


def test_a4_accepts_finishing_a_profile(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}",
        json={"status": models.ProfileStatus.FINISHED.value},
    )
    assert response.status_code == 200
    assert response.json()["status"] == models.ProfileStatus.FINISHED.value


def test_a4_refuses_every_write_once_the_profile_is_finished(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/profiles/{FINISHED_ID}", json={"target_score": 425}
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_a4_refuses_a_forged_profile_id(client: TestClient) -> None:
    response = client.patch(f"{routes.CAMPUS_PREFIX}/profiles/{FORGED_ID}", json={"title": "x"})
    assert response.status_code == 404
    assert _detail(response)["code"] == "PROFILE_NOT_FOUND"


def test_a4_refuses_an_unknown_status_value(client: TestClient) -> None:
    response = client.patch(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}", json={"status": "gone"})
    assert response.status_code == 422


def test_a4_refuses_a_duplicate_title_on_rename(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}", json={"title": "已归档"}
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "DUPLICATE_TITLE"


def test_a4_keeps_reading_a_finished_profile_available(client: TestClient) -> None:
    assert client.get(f"{routes.CAMPUS_PREFIX}/profiles/{FINISHED_ID}").status_code == 200


# ---------------------------------------------------------------------------
# A5 DELETE /profiles/{pid}
# ---------------------------------------------------------------------------

CASCADE_SEED: tuple[tuple[str, dict], ...] = (
    ("review_queue", {"item_type": "vocab", "item_id": "v1", "due_at": "2026-09-20T00:00:00Z"}),
    (
        "mistake_book",
        {
            "attempt_id": "a1",
            "track_type": "cet",
            "subject": "writing",
            "last_wrong_at": "2026-09-14T00:00:00Z",
        },
    ),
    ("attempt", {"track_type": "cet", "subject": "writing", "user_answer": "x"}),
    ("question_bank_item", {"subject": "reading", "stem": "题干"}),
    ("vocab_item", {"word": "abandon"}),
    ("mock_exam", {"paper_title": "真题", "started_at": "2026-09-14T00:00:00Z"}),
    ("assessment", {"started_at": "2026-09-14T00:00:00Z"}),
    ("weekly_report", {"week_start": "2026-09-07", "week_end": "2026-09-13"}),
    ("cert_deadline", {"node_type": "exam", "date": "2026-12-19"}),
    ("mastery", {"level": "fuzzy"}),
    ("study_plan", {}),
    ("plan_task", {"plan_id": "plan-1", "title": "背单词", "subject": "english", "scheduled_date": "2026-09-15"}),
    (
        "source_doc",
        {"title": "讲义", "file_path": "library/notes.pdf", "imported_at": "2026-09-14T00:00:00Z"},
    ),
    ("school_profile", {}),
    ("knowledge_point", {"title": "定语从句"}),
)


def _seed_cascade(campus_store: store.CampusStore, profile_id: str) -> None:
    for table, columns in CASCADE_SEED:
        values = {"profile_id": profile_id, **columns}
        if table == "doc_chunk":
            values["doc_id"] = "doc-1"
        campus_store.insert(table, values)
    campus_store.insert(
        "doc_chunk", {"profile_id": profile_id, "doc_id": "doc-1", "page_no": 1, "content": "正文"}
    )


def test_a5_deletes_the_profile_and_reports_the_cascade(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    _seed_cascade(seeded_store, ACTIVE_ID)
    response = client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    cascade = body["cascade"]
    assert cascade["exam_profile"] == 1
    for table, _columns in CASCADE_SEED:
        assert cascade[table] == 1, table
    assert cascade["doc_chunk"] == 1


def test_a5_removes_every_row_it_reported(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    _seed_cascade(seeded_store, ACTIVE_ID)
    client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}")
    for table, _columns in CASCADE_SEED:
        assert seeded_store.count(table, "profile_id = ?", (ACTIVE_ID,)) == 0, table


def test_a5_leaves_another_profile_untouched(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    _seed_cascade(seeded_store, ACTIVE_ID)
    _seed_cascade(seeded_store, ARCHIVED_ID)
    client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}")
    assert seeded_store.count("attempt", "profile_id = ?", (ARCHIVED_ID,)) == 1
    assert seeded_store.count("exam_profile") == 2


def test_a5_deletes_the_profile_library_directory(
    client: TestClient, campus_db_path: Path
) -> None:
    library_dir = campus_db_path.parent / "campus" / "library" / ACTIVE_ID
    library_dir.mkdir(parents=True, exist_ok=True)
    (library_dir / "notes.pdf").write_bytes(b"pdf")
    client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}")
    assert not library_dir.exists()


def test_a5_clears_a_dangling_active_profile_pointer(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.set_state("active_profile_id", ACTIVE_ID)
    client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{ACTIVE_ID}")
    assert seeded_store.get_state("active_profile_id") is None


def test_a5_returns_not_found_for_a_forged_profile_id(client: TestClient) -> None:
    response = client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{FORGED_ID}")
    assert response.status_code == 404
    assert _detail(response)["code"] == "PROFILE_NOT_FOUND"


def test_a5_refuses_to_delete_a_finished_profile(client: TestClient) -> None:
    response = client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{FINISHED_ID}")
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_a5_keeps_the_deleted_profile_out_of_later_reads(client: TestClient) -> None:
    client.delete(f"{routes.CAMPUS_PREFIX}/profiles/{ARCHIVED_ID}")
    assert client.get(f"{routes.CAMPUS_PREFIX}/profiles/{ARCHIVED_ID}").status_code == 404
    assert _profile_ids(client.get(f"{routes.CAMPUS_PREFIX}/profiles")) == {ACTIVE_ID, FINISHED_ID}
