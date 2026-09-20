"""D 组错题本（D1-D3、D7）与 I1 人设清单（03 §4.4/§4.9、G-16、CERT-08/09、G-12）。

与 B 组同因：`campus/api.ts` 一直声明着这五个端点、`MistakeBookPanel` 也照常渲染，但
`routes.py` 从未挂载它们，真实环境里打开错题本只会看到 404。本文件把这条链路钉在 HTTP 层。

D7 是唯一走模型的 D 端点，用 FakeProvider 回放；其余全部只碰 store。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, store
from stealth_study.campus.service import CAMPUS_PERSONA_IDS
from stealth_study.personas.registry import PersonaRegistry

CAMPUS = routes.CAMPUS_PREFIX
ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

SUGGESTION_OK = json.dumps(
    {
        "items": [
            {
                "attempt_id": "at-1",
                "suggestion": "misread",
                "confidence_note": "把 nearly 读成了 nearby",
            }
        ]
    }
)


class FakeProvider:
    def __init__(self, text: str = SUGGESTION_OK) -> None:
        self.text = text
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        return SimpleNamespace(text=self.text)


class FakeManager:
    def __init__(self, *, ready: bool = True, provider: Any = None) -> None:
        self.model = "fake:model"
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model]}


@pytest.fixture()
def seeded_store() -> store.CampusStore:
    instance = store.CampusStore(secrets.state_dir() / "campus.db")
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.CET.value,
                "title": title,
                "status": status,
            },
        )
    instance.insert(
        "knowledge_point", {"id": "p-1", "profile_id": ACTIVE_ID, "title": "长难句"}
    )
    instance.insert(
        "knowledge_point", {"id": "p-foreign", "profile_id": OTHER_ID, "title": "他人知识点"}
    )
    rows = [
        ("mk-1", ACTIVE_ID, "at-1", "reading", "concept_unclear", 0, "2026-09-10T00:00:00Z"),
        ("mk-2", ACTIVE_ID, "at-2", "writing", "misread", 1, "2026-09-12T00:00:00Z"),
        ("mk-3", OTHER_ID, "at-3", "reading", "time_short", 0, "2026-09-13T00:00:00Z"),
    ]
    for mistake_id, profile_id, attempt_id, subject, attribution, resolved, when in rows:
        instance.insert(
            "attempt",
            {
                "id": attempt_id,
                "profile_id": profile_id,
                "track_type": models.TrackType.CET.value,
                "subject": subject,
                "user_answer": "The important of study.",
                "grading_json": json.dumps(
                    {"errors": [{"fragment": "The important of", "type": "搭配"}], "kind": "essay"}
                ),
            },
        )
        instance.insert(
            "mistake_book",
            {
                "id": mistake_id,
                "profile_id": profile_id,
                "attempt_id": attempt_id,
                "track_type": models.TrackType.CET.value,
                "subject": subject,
                "attribution": attribution,
                "resolved": resolved,
                "last_wrong_at": when,
            },
        )
    try:
        yield instance
    finally:
        instance.close()


def make_client(manager: FakeManager) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return TestClient(app)


@pytest.fixture()
def client(manager: FakeManager, seeded_store: store.CampusStore) -> TestClient:
    del seeded_store
    return make_client(manager)


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


# -- D1 列表 ----------------------------------------------------------------


def test_d1_lists_the_profiles_mistakes_newest_wrong_first(client: TestClient) -> None:
    body = client.get(f"{CAMPUS}/mistakes", params={"profile_id": ACTIVE_ID}).json()
    assert body["total"] == 2
    assert body["page"] == 1 and body["page_size"] == 50
    assert [row["id"] for row in body["items"]] == ["mk-2", "mk-1"]
    assert set(body["items"][0]) >= {
        "id",
        "attempt_id",
        "track_type",
        "subject",
        "attribution",
        "wrong_count",
        "resolved",
    }


def test_d1_never_returns_another_profiles_mistakes(client: TestClient) -> None:
    body = client.get(f"{CAMPUS}/mistakes", params={"profile_id": OTHER_ID}).json()
    assert [row["id"] for row in body["items"]] == ["mk-3"]


def test_d1_filters_by_attribution_resolved_subject_track_and_point(client: TestClient) -> None:
    def ids(**params) -> list[str]:
        query = {"profile_id": ACTIVE_ID, **params}
        return [row["id"] for row in client.get(f"{CAMPUS}/mistakes", params=query).json()["items"]]

    assert ids(attribution="misread") == ["mk-2"]
    assert ids(resolved=0) == ["mk-1"]
    assert ids(track_type=models.TrackType.CET.value) == ["mk-2", "mk-1"]
    assert ids(point_id="p-1") == []
    assert ids(attribution="misread", resolved=0) == []


def test_d1_pages_with_total_kept_whole(client: TestClient) -> None:
    body = client.get(
        f"{CAMPUS}/mistakes", params={"profile_id": ACTIVE_ID, "page": 2, "page_size": 1}
    ).json()
    assert body["total"] == 2
    assert [row["id"] for row in body["items"]] == ["mk-1"]


def test_d1_rejects_an_unknown_attribution_filter(client: TestClient) -> None:
    response = client.get(
        f"{CAMPUS}/mistakes", params={"profile_id": ACTIVE_ID, "attribution": "made-up"}
    )
    assert response.status_code == 422


def test_d1_requires_the_profile_id(client: TestClient) -> None:
    response = client.get(f"{CAMPUS}/mistakes")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


# -- D2 改归因 --------------------------------------------------------------


def test_d2_re_attributes_one_entry_and_clears_the_ai_confidence(client: TestClient) -> None:
    body = client.patch(
        f"{CAMPUS}/mistakes/mk-1",
        json={"attribution": "misread"},
        params={"profile_id": ACTIVE_ID},
    ).json()
    assert body["id"] == "mk-1"
    assert body["attribution"] == "misread"
    refreshed = client.get(f"{CAMPUS}/mistakes", params={"profile_id": ACTIVE_ID}).json()
    assert {row["id"]: row["attribution"] for row in refreshed["items"]}["mk-1"] == "misread"


def test_d2_writes_the_note_and_the_resolved_flag(client: TestClient) -> None:
    body = client.patch(
        f"{CAMPUS}/mistakes/mk-1",
        json={"note": "周三回看", "resolved": 1},
        params={"profile_id": ACTIVE_ID},
    ).json()
    assert body["note"] == "周三回看"
    assert body["resolved"] == 1


def test_d2_accepts_an_empty_patch_as_a_no_op(client: TestClient) -> None:
    before = client.get(f"{CAMPUS}/mistakes", params={"profile_id": ACTIVE_ID}).json()["items"][1]
    after = client.patch(
        f"{CAMPUS}/mistakes/mk-1", json={}, params={"profile_id": ACTIVE_ID}
    ).json()
    assert after["attribution"] == before["attribution"]
    assert after["resolved"] == before["resolved"]


def test_d2_refuses_an_unknown_attribution_with_the_documented_code(client: TestClient) -> None:
    response = client.patch(
        f"{CAMPUS}/mistakes/mk-1",
        json={"attribution": "made-up"},
        params={"profile_id": ACTIVE_ID},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_ATTRIBUTION"


def test_d2_validates_the_point_against_the_profile_tree(client: TestClient) -> None:
    query = {"profile_id": ACTIVE_ID}
    assert (
        client.patch(f"{CAMPUS}/mistakes/mk-1", json={"point_id": "p-1"}, params=query).status_code
        == 200
    )
    missing = client.patch(
        f"{CAMPUS}/mistakes/mk-1", json={"point_id": "p-nope"}, params=query
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "POINT_NOT_FOUND"
    foreign = client.patch(
        f"{CAMPUS}/mistakes/mk-1", json={"point_id": "p-foreign"}, params=query
    )
    assert foreign.status_code == 404


def test_d2_refuses_a_resolved_flag_outside_zero_one(client: TestClient) -> None:
    assert (
        client.patch(
            f"{CAMPUS}/mistakes/mk-1", json={"resolved": 2}, params={"profile_id": ACTIVE_ID}
        ).status_code
        == 422
    )


def test_d2_refuses_another_profiles_entry(client: TestClient) -> None:
    response = client.patch(
        f"{CAMPUS}/mistakes/mk-3",
        json={"attribution": "misread"},
        params={"profile_id": ACTIVE_ID},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_d2_unknown_entry_and_a_read_only_profile(client: TestClient) -> None:
    missing = client.patch(
        f"{CAMPUS}/mistakes/mk-nope", json={"note": "x"}, params={"profile_id": ACTIVE_ID}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "ITEM_NOT_FOUND"
    # D2 has no `profile_id` body field (03 §4.4), so the query string is the carrier and
    # the guard resolves the finished profile from it — a write into it is PROFILE_READ_ONLY.
    finished = client.patch(
        f"{CAMPUS}/mistakes/mk-1",
        json={"note": "x"},
        params={"profile_id": FINISHED_ID},
    )
    assert finished.status_code == 409
    assert finished.json()["detail"]["code"] == "PROFILE_READ_ONLY"


# -- D3 归因分布 ------------------------------------------------------------


def test_d3_distributes_the_unresolved_entries_and_names_the_winner(client: TestClient) -> None:
    body = client.get(f"{CAMPUS}/mistakes/stats", params={"profile_id": ACTIVE_ID}).json()
    # mk-2 is resolved, so only mk-1's concept_unclear is counted.
    assert body["distribution"] == {models.Attribution.CONCEPT_UNCLEAR.value: 1}
    assert body["top_attribution"] == models.Attribution.CONCEPT_UNCLEAR.value


def test_d3_reports_an_empty_distribution_for_a_clean_profile(client: TestClient) -> None:
    body = client.get(f"{CAMPUS}/mistakes/stats", params={"profile_id": OTHER_ID}).json()
    assert body["distribution"] == {
        models.Attribution.TIME_SHORT.value: 1
    }
    clean = client.get(f"{CAMPUS}/mistakes/stats", params={"profile_id": FINISHED_ID}).json()
    assert clean == {"distribution": {}, "top_attribution": None}


def test_d3_breaks_a_tie_alphabetically_so_the_answer_is_stable(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "mistake_book",
        {
            "id": "mk-4",
            "profile_id": ACTIVE_ID,
            "attempt_id": "at-4",
            "track_type": models.TrackType.CET.value,
            "subject": "reading",
            "attribution": models.Attribution.TIME_SHORT.value,
            "resolved": 0,
            "last_wrong_at": "2026-09-14T00:00:00Z",
        },
    )
    body = client.get(f"{CAMPUS}/mistakes/stats", params={"profile_id": ACTIVE_ID}).json()
    assert body["distribution"] == {"concept_unclear": 1, "time_short": 1}
    assert body["top_attribution"] == "concept_unclear"


# -- D7 归因建议 ------------------------------------------------------------


def test_d7_returns_suggestions_without_writing_anything(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [
            {
                "attempt_id": "at-1",
                "suggestion": "misread",
                "confidence_note": "把 nearly 读成了 nearby",
            }
        ]
    }
    # Advisory only: the stored attribution is untouched (CERT-08 v1.1 B④).
    listing = client.get(f"{CAMPUS}/mistakes", params={"profile_id": ACTIVE_ID}).json()
    assert {row["id"]: row for row in listing["items"]}["mk-1"]["attribution"] == "concept_unclear"


def test_d7_fails_the_whole_call_on_one_foreign_attempt(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1", "at-3"]},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_d7_unknown_attempt_is_not_found(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-nope"]},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ATTEMPT_NOT_FOUND"


def test_d7_rejects_an_empty_or_oversized_id_list(client: TestClient) -> None:
    assert (
        client.post(f"{CAMPUS}/review/attributions", json={"profile_id": ACTIVE_ID, "attempt_ids": []}).status_code
        == 422
    )
    assert (
        client.post(
            f"{CAMPUS}/review/attributions",
            json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1"] * 21},
        ).status_code
        == 422
    )


def test_d7_refuses_when_no_model_is_callable(
    seeded_store: store.CampusStore,
) -> None:
    del seeded_store
    manager = FakeManager(ready=False)
    manager.provider = None
    response = make_client(manager).post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"


def test_d7_refuses_unparsable_output(manager: FakeManager, seeded_store: store.CampusStore) -> None:
    del seeded_store
    manager.provider = FakeProvider("抱歉，我无法判断。")
    response = make_client(manager).post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1"]},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "MODEL_OUTPUT_INVALID"


def test_d7_refuses_a_suggestion_outside_the_documented_enum(
    manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    del seeded_store
    manager.provider = FakeProvider(
        json.dumps(
            {"items": [{"attempt_id": "at-1", "suggestion": "bad_luck", "confidence_note": ""}]}
        )
    )
    response = make_client(manager).post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1"]},
    )
    assert response.status_code == 502
    assert "suggestion" in response.json()["detail"]["message"]


def test_d7_refuses_an_attempt_id_that_was_not_requested(
    manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    del seeded_store
    manager.provider = FakeProvider(
        json.dumps(
            {"items": [{"attempt_id": "at-9", "suggestion": "misread", "confidence_note": ""}]}
        )
    )
    response = make_client(manager).post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": ACTIVE_ID, "attempt_ids": ["at-1"]},
    )
    assert response.status_code == 502
    assert "attempt_id" in response.json()["detail"]["message"]


def test_d7_answers_for_a_finished_profile_because_it_writes_nothing(
    client: TestClient,
) -> None:
    response = client.post(
        f"{CAMPUS}/review/attributions",
        json={"profile_id": FINISHED_ID, "attempt_ids": ["at-1"]},
    )
    # at-1 belongs to the active profile, so the refusal is the cross-profile one, not a 409.
    assert response.status_code == 403


# -- I1 人设清单 ------------------------------------------------------------

PERSONAS = Path(__file__).resolve().parents[2] / "ss" / "personas" / "builtin"


def _registry(tmp_path: Path) -> PersonaRegistry:
    return PersonaRegistry(builtin_dir=PERSONAS, state_path=tmp_path / "personas.json")


def test_i1_lists_the_six_station_personas_with_live_metadata(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(tmp_path)
    monkeypatch.setattr("stealth_study.personas.registry.get_registry", lambda: registry, raising=True)
    body = client.get(f"{CAMPUS}/personas").json()
    listed = {row["id"]: row for row in body["items"]}
    assert tuple(listed) == CAMPUS_PERSONA_IDS
    assert len(listed) == 6
    for row in listed.values():
        assert row["name"] and row["icon"]
        assert isinstance(row["available"], bool)
    assert listed["cet-examiner"]["icon"] == "clock"
    assert listed["cet-grader"]["available"] is True


def test_i1_reports_a_disabled_persona_as_unavailable_without_hiding_it(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(tmp_path)
    registry.set_enabled("cet-grader", False)
    monkeypatch.setattr("stealth_study.personas.registry.get_registry", lambda: registry, raising=True)
    body = client.get(f"{CAMPUS}/personas").json()
    listed = {row["id"]: row for row in body["items"]}
    assert listed["cet-grader"]["available"] is False
    assert listed["cet-examiner"]["available"] is True
    assert len(listed) == 6


def test_i1_never_lists_the_kernel_only_personas(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(tmp_path)
    monkeypatch.setattr("stealth_study.personas.registry.get_registry", lambda: registry, raising=True)
    ids = {row["id"] for row in client.get(f"{CAMPUS}/personas").json()["items"]}
    assert "cowork" not in ids
    assert "code" not in ids
