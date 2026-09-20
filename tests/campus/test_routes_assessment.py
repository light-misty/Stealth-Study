"""F1-F4 定级测评端点（03 §4.6、07 §4 T10 验收①、PRD CET1）。

钉住四件事：

* **20 题结构**（词汇 6 / 听力理解 4 / 阅读 5 / 写译 5）与 AI 出题的校验口径（05 §3.1 cet-examiner）；
* **可中断续做**：F2 可恢复题目与已答内容，且**不回传答案键**（否则续做即泄题）；
* **425 折算与差距表**：三项得分之和 = 预估总分（PRD CET1 验收 2 的"数字自洽"），分项目标按官方
  权重（听力 35% / 阅读 35% / 写译 30%）从目标总分拆出且精确求和；
* **落库副作用**：`mastery` 三条分项掌握度 + `exam_profile.current_estimate` + 目标分缺省补 425。
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

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

SECTION_SUBJECTS = (
    (models.Subject.VOCAB.value, 6),
    (models.Subject.LISTENING.value, 4),
    (models.Subject.READING.value, 5),
    (models.Subject.WRITING.value, 3),
    (models.Subject.TRANSLATION.value, 2),
)


def made_items() -> list[dict[str, Any]]:
    """A well-formed 20-item payload: 6 vocab / 4 listening / 5 reading / 5 writing+translation."""
    items: list[dict[str, Any]] = []
    index = 0
    for subject, count in SECTION_SUBJECTS:
        for _ in range(count):
            index += 1
            items.append(
                {
                    "subject": subject,
                    "qtype": models.QuestionType.SINGLE.value,
                    "stem": f"第 {index} 题",
                    "options": [{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
                    "answer": "A",
                }
            )
    return items


def generation_payload(items: list[dict[str, Any]] | None = None) -> str:
    return json.dumps({"items": made_items() if items is None else items})


class FakeProvider:
    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses if responses is not None else {"default": generation_payload()}
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    def __init__(self, model: str = "fake:model", *, ready: bool = True, provider: Any = None) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model] if self.model else []}


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture()
def seeded_store(campus_db_path: Path) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, status, title, target in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月", None),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案", 500),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课", None),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.CET.value,
                "title": title,
                "status": status,
                "target_score": target,
            },
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


def _start(client: TestClient, profile_id: str = ACTIVE_ID):
    return client.post(f"{routes.CAMPUS_PREFIX}/assessments", json={"profile_id": profile_id})


def _finish(client: TestClient, assessment_id: str, profile_id: str = ACTIVE_ID):
    """F4 has no request body, so the guard reads `profile_id` from the query string."""
    return client.post(
        f"{routes.CAMPUS_PREFIX}/assessments/{assessment_id}/finish",
        params={"profile_id": profile_id},
    )


def _assessment(client: TestClient, assessment_id: str, profile_id: str = ACTIVE_ID) -> dict:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/assessments/{assessment_id}", params={"profile_id": profile_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _answer_all(client: TestClient, body: dict, *, correct: bool = True, profile_id: str = ACTIVE_ID) -> None:
    answers = {qid: ("A" if correct else "B") for qid in body["question_ids"]}
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": profile_id, "answers": answers},
    )
    assert response.status_code == 200, response.text


def _section_question_ids(client: TestClient, body: dict, subject: str) -> list[str]:
    """The generated question ids of one subject, read back through F2's resume view."""
    resumed = _assessment(client, body["id"])
    return [question["id"] for question in resumed["questions"] if question["subject"] == subject]


# ---------------------------------------------------------------------------
# F1 POST /assessments
# ---------------------------------------------------------------------------

def test_f1_creates_a_twenty_question_draft(client: TestClient) -> None:
    response = _start(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == models.AssessmentStatus.DRAFT.value
    assert len(body["question_ids"]) == 20
    assert body["answers"] == {}
    assert body["scores"] is None
    assert body["started_at"]


def test_f1_stores_the_generated_questions_in_the_bank(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _start(client).json()
    rows = [seeded_store.get("question_bank_item", qid) for qid in body["question_ids"]]
    assert all(row is not None for row in rows)
    assert {row["source"] for row in rows} == {models.QuestionSource.AI.value}
    assert {row["subject"] for row in rows} == {
        models.Subject.VOCAB.value,
        models.Subject.LISTENING.value,
        models.Subject.READING.value,
        models.Subject.WRITING.value,
        models.Subject.TRANSLATION.value,
    }
    assert seeded_store.count("assessment", "profile_id = ?", (ACTIVE_ID,)) == 1


def test_f1_asks_the_model_for_the_documented_section_mix(client: TestClient, manager: FakeManager) -> None:
    _start(client)
    prompt = "\n".join(str(message.get("content", "")) for message in manager.provider.seen[0]["messages"])
    for subject, count in SECTION_SUBJECTS:
        assert subject in prompt
    assert "20" in prompt


def test_f1_rejects_a_generation_payload_with_the_wrong_section_mix(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": generation_payload(made_items()[:-1])})
    response = _start(client)
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "broken",
    [
        "not json at all",
        json.dumps({"items": []}),
        json.dumps({"items": [{"subject": "vocab", "stem": "x"}] * 20}),
    ],
)
def test_f1_reports_unusable_generation_output(client: TestClient, manager: FakeManager, broken: str) -> None:
    manager.provider = FakeProvider({"default": broken})
    response = _start(client)
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


def test_f1_refuses_without_a_configured_model(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(model="", ready=False)))
    client = TestClient(app)
    response = _start(client)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"
    assert seeded_store.count("assessment", "profile_id = ?", (ACTIVE_ID,)) == 0


def test_f1_refuses_a_finished_profile(client: TestClient, seeded_store: store.CampusStore) -> None:
    response = _start(client, FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"
    assert seeded_store.count("question_bank_item", "profile_id = ?", (FINISHED_ID,)) == 0


def test_f1_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/assessments", json={})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# F2 GET /assessments/{id}（中断续做）
# ---------------------------------------------------------------------------

def test_f2_returns_the_questions_and_the_answers_so_far(client: TestClient) -> None:
    body = _start(client).json()
    client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": ACTIVE_ID, "answers": {body["question_ids"][0]: "A"}},
    )
    resumed = _assessment(client, body["id"])
    assert resumed["id"] == body["id"]
    assert len(resumed["questions"]) == 20
    assert resumed["answers"] == {body["question_ids"][0]: "A"}


def test_f2_never_leaks_the_answer_key(client: TestClient) -> None:
    body = _start(client).json()
    resumed = _assessment(client, body["id"])
    for question in resumed["questions"]:
        assert "answer" not in question
        assert "answer_meta" not in question
        assert question["stem"]


def test_f2_returns_assessment_not_found(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/assessments/no-such-assessment", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "ASSESSMENT_NOT_FOUND"


def test_f2_refuses_another_profile_assessment(client: TestClient) -> None:
    body = _start(client).json()
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}", params={"profile_id": OTHER_ID}
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


# ---------------------------------------------------------------------------
# F3 PATCH /assessments/{id}
# ---------------------------------------------------------------------------

def test_f3_merges_answers_incrementally(client: TestClient) -> None:
    body = _start(client).json()
    first, second = body["question_ids"][0], body["question_ids"][1]
    client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": ACTIVE_ID, "answers": {first: "A"}},
    )
    body2 = client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": ACTIVE_ID, "answers": {second: "B"}},
    ).json()
    assert body2["answers"] == {first: "A", second: "B"}


def test_f3_rejects_a_question_outside_the_assessment(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _start(client).json()
    seeded_store.insert(
        "question_bank_item",
        {"id": "q-outside", "profile_id": ACTIVE_ID, "subject": "reading", "stem": "无关题", "answer": "A"},
    )
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": ACTIVE_ID, "answers": {"q-outside": "A"}},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "QUESTION_NOT_FOUND"


def test_f3_refuses_a_finished_assessment(client: TestClient) -> None:
    body = _start(client).json()
    _answer_all(client, body)
    assert _finish(client, body["id"]).status_code == 200
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": ACTIVE_ID, "answers": {body["question_ids"][0]: "B"}},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "ASSESSMENT_FINISHED"


# ---------------------------------------------------------------------------
# F4 POST /assessments/{id}/finish（425 折算）
# ---------------------------------------------------------------------------

def test_f4_folds_the_three_sections_and_keeps_the_total_self_consistent(client: TestClient) -> None:
    body = _start(client).json()
    _answer_all(client, body, correct=True)
    result = _finish(client, body["id"]).json()
    scores = result["scores"]
    assert scores["listening"] == 248.5
    assert scores["reading"] == 248.5
    assert scores["writing_translation"] == 213.0
    assert result["estimate_total"] == round(
        scores["listening"] + scores["reading"] + scores["writing_translation"], 1
    )
    assert scores["estimate_total"] == result["estimate_total"]


def test_f4_scales_a_partial_result_by_the_official_weights(client: TestClient) -> None:
    body = _start(client).json()
    answers = {qid: "A" for qid in body["question_ids"]}
    listening_ids = _section_question_ids(client, body, models.Subject.LISTENING.value)
    assert len(listening_ids) == 4
    answers[listening_ids[0]] = "B"
    client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}", json={"profile_id": ACTIVE_ID, "answers": answers}
    )
    scores = _finish(client, body["id"]).json()["scores"]
    assert scores["listening"] == round(248.5 * 3 / 4, 1)
    assert scores["reading"] == 248.5
    assert scores["writing_translation"] == 213.0


def test_f4_builds_the_gap_table_against_the_profile_target(client: TestClient) -> None:
    body = _start(client).json()
    _answer_all(client, body, correct=True)
    gap_table = _finish(client, body["id"]).json()["gap_table"]
    by_section = {row["section"]: row for row in gap_table}
    assert set(by_section) == {"listening", "reading", "writing_translation"}
    assert by_section["listening"]["target"] == 148.75
    assert by_section["reading"]["target"] == 148.75
    assert by_section["writing_translation"]["target"] == 127.5
    assert sum(row["target"] for row in gap_table) == 425
    assert by_section["listening"]["gap"] == round(148.75 - 248.5, 1)


def test_f4_uses_the_profile_target_when_it_is_set(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _start(client, OTHER_ID).json()
    _answer_all(client, body, correct=True, profile_id=OTHER_ID)
    gap_table = _finish(client, body["id"], OTHER_ID).json()["gap_table"]
    assert sum(row["target"] for row in gap_table) == 500
    assert seeded_store.get("exam_profile", OTHER_ID)["target_score"] == 500


def test_f4_records_mastery_current_estimate_and_a_default_target(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    body = _start(client).json()
    _answer_all(client, body, correct=True)
    result = _finish(client, body["id"]).json()
    rows = seeded_store.list_rows("mastery", profile_id=ACTIVE_ID)
    assert {row["dimension"] for row in rows} == {"listening", "reading", "writing_translation"}
    assert {row["level"] for row in rows} == {models.MasteryLevel.MASTERED.value}
    assert all(row["point_id"] is None for row in rows)
    profile = seeded_store.get("exam_profile", ACTIVE_ID)
    assert profile["current_estimate"] == round(result["estimate_total"])
    assert profile["target_score"] == 425


def test_f4_grades_a_weak_result_as_unknown_mastery(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _start(client).json()
    _answer_all(client, body, correct=False)
    result = _finish(client, body["id"]).json()
    assert result["scores"]["listening"] == 0.0
    assert {row["level"] for row in seeded_store.list_rows("mastery", profile_id=ACTIVE_ID)} == {
        models.MasteryLevel.UNKNOWN.value
    }


def test_f4_marks_the_assessment_finished_and_keeps_it_readable(client: TestClient) -> None:
    body = _start(client).json()
    _answer_all(client, body)
    _finish(client, body["id"])
    stored = _assessment(client, body["id"])
    assert stored["status"] == models.AssessmentStatus.FINISHED.value
    assert stored["finished_at"]


def test_f4_is_idempotent_only_once(client: TestClient) -> None:
    body = _start(client).json()
    _answer_all(client, body)
    assert _finish(client, body["id"]).status_code == 200
    second = _finish(client, body["id"])
    assert second.status_code == 409
    assert _detail(second)["code"] == "ASSESSMENT_FINISHED"


def test_f4_treats_missing_answers_as_unanswered(client: TestClient) -> None:
    body = _start(client).json()
    first = body["question_ids"][0]
    client.patch(
        f"{routes.CAMPUS_PREFIX}/assessments/{body['id']}",
        json={"profile_id": ACTIVE_ID, "answers": {first: "A"}},
    )
    scores = _finish(client, body["id"]).json()["scores"]
    assert scores["listening"] == 0.0
    assert scores["reading"] == 0.0


def test_f4_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/assessments/anything/finish")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_f4_refuses_a_finished_profile(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "assessment",
        {"id": "assessment-finished", "profile_id": FINISHED_ID, "started_at": "2026-09-15T00:00:00Z"},
    )
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/assessments/assessment-finished/finish",
        params={"profile_id": FINISHED_ID},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"
    assert seeded_store.get("assessment", "assessment-finished")["scores"] is None
