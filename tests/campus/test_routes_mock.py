"""F10-F14 模考端点（03 §4.6 CET-13/14、PRD CET5）。

钉住五件事：

* **阶段化计时**：writing 30 分钟起步，`stage_deadline` 为绝对时刻，暂停把当前与后续阶段
  一起顺延（真实考试的"流程时刻表"语义）；
* **收卡锁**：F12 推进阶段时把前序阶段写进 `locked_stages`，此后 E5 携带 `mock_exam_id`
  作答已锁科目的题目即 `STAGE_LOCKED`（PRD CET-13 验收 1）；
* **暂停预算**：累计 `paused_seconds` ≤ 180，超限 409 且不落任何变更（03 §4.6 口径）；
* **交卷估分**：客观题按题库分值累加，分项 max 只累计已作答题目（mock 与题库无关联存储，
  未答题无法归卷，得分率分母口径已在交付文档登记），估分落 `mock_exam.estimate_score`，
  错题写入错题本（PRD CET-14 验收 3）；
* **边界**：空卷名 422、非法流转 ILLEGAL_STAGE、重复交卷 MOCK_SUBMITTED、跨档案 403、
  finished 档案只读。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, service, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

WRITING_MINUTES = 30
LISTENING_MINUTES = 25
READING_TRANSLATION_MINUTES = 70

MOCK_CONTENT = """题干：听力第一题
科目：listening
类型：single
选项：A.甲|B.乙
答案：A
分值：10

题干：听力第二题
科目：listening
类型：single
选项：A.甲|B.乙
答案：B
分值：10

题干：阅读第一题
科目：reading
类型：single
选项：A.甲|B.乙
答案：A
分值：20

题干：作文题
科目：writing
类型：essay
答案：
分值：106.5
"""


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class FakeProvider:
    def __init__(self) -> None:
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        return SimpleNamespace(text="not-a-json-payload")


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
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {"id": profile_id, "track_type": models.TrackType.CET.value, "title": title, "status": status},
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


@pytest.fixture()
def question_ids(client: TestClient) -> dict[str, str]:
    """A small imported paper: 2 listening / 1 reading / 1 writing, with documented scores."""
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/questions/import",
        json={"profile_id": ACTIVE_ID, "format": "md", "content": MOCK_CONTENT},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    return {item["subject"]: item["id"] for item in items}


def _detail(response) -> dict:
    return response.json()["detail"]


def _start(client: TestClient, profile_id: str = ACTIVE_ID, title: str = "2026 年 6 月四级真题"):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/mock-exams", json={"profile_id": profile_id, "paper_title": title}
    )


def _mock(client: TestClient, mock_id: str, profile_id: str = ACTIVE_ID) -> dict:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/mock-exams/{mock_id}", params={"profile_id": profile_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _stage(client: TestClient, mock_id: str, to: str, profile_id: str = ACTIVE_ID):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/mock-exams/{mock_id}/stage",
        json={"to": to},
        params={"profile_id": profile_id},
    )


def _pause(client: TestClient, mock_id: str, seconds: int, profile_id: str = ACTIVE_ID):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/mock-exams/{mock_id}/pause",
        json={"seconds": seconds},
        params={"profile_id": profile_id},
    )


def _submit(client: TestClient, mock_id: str, profile_id: str = ACTIVE_ID):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/mock-exams/{mock_id}/submit", params={"profile_id": profile_id}
    )


def _attempt(client: TestClient, question_id: str, *, mock_id: str | None = None, answer: str = "A"):
    body: dict[str, Any] = {"profile_id": ACTIVE_ID, "question_id": question_id, "answer": answer}
    if mock_id is not None:
        body["mock_exam_id"] = mock_id
    return client.post(f"{routes.CAMPUS_PREFIX}/attempts", json=body)


# ---------------------------------------------------------------------------
# F10 POST /mock-exams
# ---------------------------------------------------------------------------

def test_f10_starts_on_the_writing_stage_with_a_precomputed_deadline(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    # _utcnow keeps whole seconds, so give the window one second of slack on each side.
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    response = _start(client)
    after = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_stage"] == models.MockStage.WRITING.value
    assert body["status"] == models.MockStatus.ONGOING.value
    assert body["paused_seconds"] == 0
    assert json.loads(body["locked_stages"]) == []
    started = _iso(body["started_at"])
    assert before <= started <= after
    deadline = _iso(body["stage_deadline"])
    assert deadline - started == timedelta(minutes=WRITING_MINUTES)


def test_f10_rejects_an_empty_paper_title(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/mock-exams", json={"profile_id": ACTIVE_ID, "paper_title": "  "}
    )
    assert response.status_code == 422


def test_f10_refuses_a_finished_profile(client: TestClient) -> None:
    response = _start(client, FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_f10_refuses_an_unknown_profile(client: TestClient) -> None:
    response = _start(client, "nope")
    assert response.status_code == 404
    assert _detail(response)["code"] == "PROFILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# F11 GET /mock-exams/{id}
# ---------------------------------------------------------------------------

def test_f11_reports_a_live_derived_timer(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    body = _mock(client, mock_id)
    assert body["id"] == mock_id
    assert body["current_stage"] == models.MockStage.WRITING.value
    assert 0 <= body["remaining_seconds"] <= WRITING_MINUTES * 60
    assert body["stage_expired"] is False
    assert body["server_now"]


def test_f11_marks_an_expired_stage(client: TestClient, seeded_store: store.CampusStore) -> None:
    mock_id = _start(client).json()["id"]
    expired = datetime.now(timezone.utc) - timedelta(seconds=5)
    seeded_store.update(
        "mock_exam", mock_id, {"stage_deadline": service._utcformat(expired)}
    )
    body = _mock(client, mock_id)
    assert body["stage_expired"] is True
    assert body["remaining_seconds"] == 0


def test_f11_refuses_a_foreign_profile(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/mock-exams/{mock_id}", params={"profile_id": OTHER_ID}
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_f11_reports_an_unknown_mock(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/mock-exams/nope", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "MOCK_NOT_FOUND"


# ---------------------------------------------------------------------------
# F12 POST /mock-exams/{id}/stage
# ---------------------------------------------------------------------------

def test_f12_advances_writing_to_listening_and_collects_the_answer_sheet(
    client: TestClient,
) -> None:
    mock_id = _start(client).json()["id"]
    old_deadline = _iso(_mock(client, mock_id)["stage_deadline"])
    body = _stage(client, mock_id, "listening").json()
    assert body["current_stage"] == models.MockStage.LISTENING.value
    assert json.loads(body["locked_stages"]) == [models.MockStage.WRITING.value]
    assert _iso(body["stage_deadline"]) - old_deadline == timedelta(minutes=LISTENING_MINUTES)


def test_f12_keeps_a_running_schedule_across_two_advances(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    first = _stage(client, mock_id, "listening").json()
    second = _stage(client, mock_id, "reading_translation").json()
    assert second["current_stage"] == models.MockStage.READING_TRANSLATION.value
    assert json.loads(second["locked_stages"]) == [
        models.MockStage.WRITING.value,
        models.MockStage.LISTENING.value,
    ]
    assert _iso(second["stage_deadline"]) - _iso(first["stage_deadline"]) == timedelta(
        minutes=READING_TRANSLATION_MINUTES
    )


def test_f12_refuses_a_pause_pushed_schedule_beyond_the_budget(client: TestClient) -> None:
    """The pause budget belongs to the stage clock: a pushed deadline keeps its own stage length."""
    mock_id = _start(client).json()["id"]
    _pause(client, mock_id, 90)
    old_deadline = _iso(_mock(client, mock_id)["stage_deadline"])
    body = _stage(client, mock_id, "listening").json()
    assert _iso(body["stage_deadline"]) - old_deadline == timedelta(minutes=LISTENING_MINUTES)


@pytest.mark.parametrize("to", ["writing", "reading_translation", "graded"])
def test_f12_rejects_illegal_transitions_from_writing(client: TestClient, to: str) -> None:
    mock_id = _start(client).json()["id"]
    response = _stage(client, mock_id, to)
    assert response.status_code == 409
    assert _detail(response)["code"] == "ILLEGAL_STAGE"


def test_f12_rejects_going_back_to_a_locked_stage(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    _stage(client, mock_id, "listening")
    _stage(client, mock_id, "reading_translation")
    response = _stage(client, mock_id, "writing")
    assert response.status_code == 409
    assert _detail(response)["code"] == "STAGE_LOCKED"


def test_f12_refuses_a_submitted_mock(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    _submit(client, mock_id)
    response = _stage(client, mock_id, "listening")
    assert response.status_code == 409
    assert _detail(response)["code"] == "MOCK_SUBMITTED"


def test_f12_refuses_a_foreign_profile(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    response = _stage(client, mock_id, "listening", OTHER_ID)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# E5 × F12：收卡后已锁阶段的作答被拒（PRD CET-13 验收 1）
# ---------------------------------------------------------------------------

def test_a_locked_stage_refuses_new_attempts(client: TestClient, question_ids: dict[str, str]) -> None:
    mock_id = _start(client).json()["id"]
    writing_id = question_ids[models.Subject.WRITING.value]
    listening_id = question_ids[models.Subject.LISTENING.value]

    before_lock = _attempt(client, writing_id, mock_id=mock_id)
    assert before_lock.status_code == 200, before_lock.text

    assert _stage(client, mock_id, "listening").status_code == 200
    locked = _attempt(client, writing_id, mock_id=mock_id)
    assert locked.status_code == 409
    assert _detail(locked)["code"] == "STAGE_LOCKED"

    current = _attempt(client, listening_id, mock_id=mock_id, answer="B")
    assert current.status_code == 200, current.text


def test_attempts_without_a_mock_are_never_locked(client: TestClient, question_ids: dict[str, str]) -> None:
    mock_id = _start(client).json()["id"]
    _stage(client, mock_id, "listening")
    free = _attempt(client, question_ids[models.Subject.WRITING.value])
    assert free.status_code == 200, free.text


def test_a_submitted_mock_refuses_new_attempts(client: TestClient, question_ids: dict[str, str]) -> None:
    mock_id = _start(client).json()["id"]
    _submit(client, mock_id)
    response = _attempt(client, question_ids[models.Subject.READING.value], mock_id=mock_id)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MOCK_SUBMITTED"


# ---------------------------------------------------------------------------
# F13 POST /mock-exams/{id}/pause
# ---------------------------------------------------------------------------

def test_f13_extends_the_deadline_by_the_paused_seconds(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    old_deadline = _iso(_mock(client, mock_id)["stage_deadline"])
    body = _pause(client, mock_id, 60).json()
    assert body["paused_seconds"] == 60
    assert _iso(body["stage_deadline"]) - old_deadline == timedelta(seconds=60)


def test_f13_accumulates_up_to_the_budget(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    assert _pause(client, mock_id, 90).json()["paused_seconds"] == 90
    body = _pause(client, mock_id, 90).json()
    assert body["paused_seconds"] == 180
    refused = _pause(client, mock_id, 1)
    assert refused.status_code == 409
    assert _detail(refused)["code"] == "PAUSE_EXCEEDED"
    assert _mock(client, mock_id)["paused_seconds"] == 180


@pytest.mark.parametrize("seconds", [0, -5])
def test_f13_rejects_non_positive_seconds(client: TestClient, seconds: int) -> None:
    mock_id = _start(client).json()["id"]
    response = _pause(client, mock_id, seconds)
    assert response.status_code == 422


def test_f13_refuses_a_submitted_mock(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    _submit(client, mock_id)
    response = _pause(client, mock_id, 30)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MOCK_SUBMITTED"


def test_f13_refuses_a_foreign_profile(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    response = _pause(client, mock_id, 30, OTHER_ID)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# F14 POST /mock-exams/{id}/submit
# ---------------------------------------------------------------------------

def test_f14_estimates_from_the_paper_scores_and_files_wrong_answers(
    client: TestClient, question_ids: dict[str, str], seeded_store: store.CampusStore
) -> None:
    mock_id = _start(client).json()["id"]
    listening = question_ids[models.Subject.LISTENING.value]
    reading = question_ids[models.Subject.READING.value]

    # question_ids keeps the LAST listening item (answer key "B"); answer it correctly.
    assert _attempt(client, listening, mock_id=mock_id, answer="B").status_code == 200
    assert _attempt(client, reading, mock_id=mock_id, answer="B").status_code == 200

    body = _submit(client, mock_id).json()
    assert body["estimate_score"] == 10.0
    by_section = body["by_section"]
    assert by_section["listening"] == {"earned": 10.0, "max": 10.0, "ratio": 1.0}
    assert by_section["reading"] == {"earned": 0.0, "max": 20.0, "ratio": 0.0}
    assert by_section["writing_translation"] == {"earned": 0.0, "max": 0.0, "ratio": None}
    assert len(body["attempt_ids"]) == 2

    stored = seeded_store.get("mock_exam", mock_id)
    assert stored["status"] == models.MockStatus.SUBMITTED.value
    assert stored["current_stage"] == models.MockStage.GRADED.value
    assert stored["estimate_score"] == 10.0

    wrong = seeded_store.list_rows("mistake_book", profile_id=ACTIVE_ID)
    assert len(wrong) == 1
    assert wrong[0]["attempt_id"] in body["attempt_ids"]
    assert wrong[0]["subject"] == models.Subject.READING.value


def test_f14_refuses_a_second_submission(client: TestClient, question_ids: dict[str, str]) -> None:
    mock_id = _start(client).json()["id"]
    _attempt(client, question_ids[models.Subject.LISTENING.value], mock_id=mock_id)
    assert _submit(client, mock_id).status_code == 200
    response = _submit(client, mock_id)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MOCK_SUBMITTED"


def test_f14_of_an_empty_mock_scores_zero_but_still_submits(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    mock_id = _start(client).json()["id"]
    body = _submit(client, mock_id).json()
    assert body["estimate_score"] == 0.0
    assert body["attempt_ids"] == []
    assert all(row["earned"] == 0.0 for row in body["by_section"].values())


def test_f14_refuses_a_foreign_profile(client: TestClient) -> None:
    mock_id = _start(client).json()["id"]
    response = _submit(client, mock_id, OTHER_ID)
    assert response.status_code == 403


def test_f14_reports_an_unknown_mock(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/mock-exams/nope/submit", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "MOCK_NOT_FOUND"
