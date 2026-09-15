"""G2 任务写回与 G3 一键重排（03 §4.7、07 §4 T11 的 KY-03/KY-04/KY-13）。

G2 是自建看板（ADR-11）的拖卡写回端点：状态流转严格按 PRD §6.4 状态机校验，
非法流转返回 `ILLEGAL_TRANSITION`；改期与改优先级不是状态流转，任何状态都允许。
`board_card_id` 保持不写（ADR-11：字段为 V0.2 只读同步预留）。

G3 是"修改考试日期后一键重排"：已完成/进行中任务原样保留（T11 验收②），
todo 任务按原相对顺序摊铺到"今天 → 新考试日"；完成率落后计划 ≥15% 的轨
（KY-13 落后预警口径）其 todo 任务优先级提为 1（落后轨加权）。

路径资源归属协议：03 §6 未定义 PLAN/TASK 专属 404 码，缺失与跨档案的
plan/task 一律按 `FORBIDDEN_PROFILE` 拒绝，不向调用方确认资源存在性。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

TODAY = date(2026, 9, 15)
NEW_EXAM = "2027-01-31"


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


def _task_row(
    task_id: str,
    subject: str,
    scheduled: str,
    status: str,
    *,
    plan_id: str = "plan-1",
    profile_id: str = ACTIVE_ID,
    priority: int = 2,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "plan_id": plan_id,
        "profile_id": profile_id,
        "title": f"任务 {task_id}",
        "subject": subject,
        "scheduled_date": scheduled,
        "priority": priority,
        "status": status,
        "completed_at": "2026-09-01T00:00:00Z" if status == "done" else None,
    }


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, title, exam, status in (
        (ACTIVE_ID, "2027 考研", "2026-12-31", models.ProfileStatus.ACTIVE.value),
        (OTHER_ID, "另一个档案", None, models.ProfileStatus.ACTIVE.value),
        (FINISHED_ID, "已结课", None, models.ProfileStatus.FINISHED.value),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.KAOYAN.value,
                "title": title,
                "exam_date": exam,
                "status": status,
            },
        )
    instance.insert(
        "study_plan",
        {
            "id": "plan-1",
            "profile_id": ACTIVE_ID,
            "track": models.PlanTrack.OVERALL.value,
            "start_date": "2026-07-01",
            "end_date": "2026-12-31",
        },
    )
    instance.insert(
        "study_plan",
        {"id": "plan-other", "profile_id": OTHER_ID, "track": models.PlanTrack.OVERALL.value},
    )
    for row in (
        _task_row("t-p-todo-1", "politics", "2026-09-01", "todo", priority=3),
        _task_row("t-p-todo-2", "politics", "2026-09-02", "todo", priority=2),
        _task_row("t-p-todo-3", "politics", "2026-09-03", "todo", priority=2),
        _task_row("t-p-todo-4", "politics", "2026-09-04", "todo", priority=2),
        _task_row("t-e-done-1", "english", "2026-08-01", "done"),
        _task_row("t-e-done-2", "english", "2026-08-02", "done"),
        _task_row("t-e-todo-1", "english", "2026-09-05", "todo", priority=2),
        _task_row("t-e-todo-2", "english", "2026-09-06", "todo", priority=2),
        _task_row("t-m-doing", "math", "2026-09-07", "doing"),
        _task_row("t-m-todo", "math", "2026-09-08", "todo"),
        _task_row("t-j-review", "major", "2026-09-09", "review"),
        _task_row("t-j-skip", "major", "2026-09-10", "skipped"),
        _task_row("t-other", "english", "2026-09-11", "todo", profile_id=OTHER_ID, plan_id="plan-other"),
    ):
        instance.insert("plan_task", row)
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(seeded_store: store.CampusStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("ss.campus.service._utc_today", lambda: TODAY)
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


def _patch_task(client: TestClient, task_id: str, payload: dict, profile_id: str = ACTIVE_ID) -> Any:
    return client.patch(
        f"{routes.CAMPUS_PREFIX}/tasks/{task_id}",
        json=payload,
        params={"profile_id": profile_id},
    )


def _reschedule(
    client: TestClient, plan_id: str, payload: dict, profile_id: str = ACTIVE_ID
) -> Any:
    return client.post(
        f"{routes.CAMPUS_PREFIX}/plans/{plan_id}/reschedule",
        json=payload,
        params={"profile_id": profile_id},
    )


# ---------- G2：拖卡写回（PRD §6.4 状态机） ----------


@pytest.mark.parametrize(
    ("task_id", "status"),
    [
        ("t-p-todo-1", "doing"),
        ("t-m-doing", "review"),
        ("t-j-review", "done"),
        ("t-j-review", "review"),
        ("t-p-todo-1", "skipped"),
        ("t-m-doing", "skipped"),
    ],
)
def test_g2_allows_every_documented_transition(
    client: TestClient, seeded_store: store.CampusStore, task_id: str, status: str
) -> None:
    response = _patch_task(client, task_id, {"status": status})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == status
    row = seeded_store.get("plan_task", task_id)
    assert row["status"] == status
    assert row["board_card_id"] is None


def test_g2_marks_completed_at_when_a_task_is_done(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    response = _patch_task(client, "t-j-review", {"status": "done"})
    assert response.status_code == 200
    row = seeded_store.get("plan_task", "t-j-review")
    assert row["completed_at"] is not None


def test_g2_keeps_completed_at_on_a_review_self_loop(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    response = _patch_task(client, "t-j-review", {"status": "review"})
    assert response.status_code == 200
    assert seeded_store.get("plan_task", "t-j-review")["completed_at"] is None


def test_g2_never_refreshes_completed_at_when_already_done(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    response = _patch_task(client, "t-e-done-1", {"status": "done"})
    assert response.status_code == 200
    assert seeded_store.get("plan_task", "t-e-done-1")["completed_at"] == "2026-09-01T00:00:00Z"


@pytest.mark.parametrize(
    ("task_id", "status"),
    [
        ("t-e-done-1", "todo"),
        ("t-e-done-1", "review"),
        ("t-j-skip", "todo"),
        ("t-p-todo-1", "done"),
        ("t-p-todo-1", "review"),
        ("t-m-doing", "todo"),
    ],
)
def test_g2_refuses_illegal_transitions(
    client: TestClient, task_id: str, status: str
) -> None:
    response = _patch_task(client, task_id, {"status": status})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ILLEGAL_TRANSITION"


def test_g2_reschedules_a_task_to_another_date(client: TestClient) -> None:
    response = _patch_task(client, "t-p-todo-1", {"scheduled_date": "2026-09-20"})
    assert response.status_code == 200
    assert response.json()["scheduled_date"] == "2026-09-20"


def test_g2_reprioritises_a_task(client: TestClient) -> None:
    response = _patch_task(client, "t-p-todo-1", {"priority": 1})
    assert response.status_code == 200
    assert response.json()["priority"] == 1


def test_g2_applies_a_combined_patch(client: TestClient) -> None:
    response = _patch_task(
        client, "t-p-todo-1", {"scheduled_date": "2026-09-21", "priority": 1}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scheduled_date"] == "2026-09-21"
    assert body["priority"] == 1
    assert body["status"] == "todo"


def test_g2_returns_the_task_unchanged_on_an_empty_patch(client: TestClient) -> None:
    response = _patch_task(client, "t-p-todo-1", {})
    assert response.status_code == 200
    assert response.json()["scheduled_date"] == "2026-09-01"
    assert response.json()["priority"] == 3


@pytest.mark.parametrize("priority", [0, 4])
def test_g2_rejects_an_out_of_range_priority(client: TestClient, priority: int) -> None:
    assert _patch_task(client, "t-p-todo-1", {"priority": priority}).status_code == 422


def test_g2_rejects_malformed_input(client: TestClient) -> None:
    assert _patch_task(client, "t-p-todo-1", {"scheduled_date": "09/20/2026"}).status_code == 422
    assert _patch_task(client, "t-p-todo-1", {"status": "finished"}).status_code == 422
    assert _patch_task(client, "t-p-todo-1", {"board_card_id": "x"}).status_code == 422


def test_g2_refuses_another_profiles_task(client: TestClient) -> None:
    response = _patch_task(client, "t-other", {"priority": 1})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_g2_refuses_a_missing_task_as_forbidden(client: TestClient) -> None:
    response = _patch_task(client, "nonexistent-task", {"priority": 1})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_g2_refuses_a_finished_profile(client: TestClient) -> None:
    response = _patch_task(
        client, "t-p-todo-1", {"priority": 1}, profile_id=FINISHED_ID
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


def test_g2_requires_a_profile(client: TestClient) -> None:
    response = client.patch(f"{routes.CAMPUS_PREFIX}/tasks/t-p-todo-1", json={"priority": 1})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


# ---------- G3：一键重排（KY-04/KY-13） ----------


def test_g3_preserves_done_and_doing_and_redates_todo(client: TestClient) -> None:
    response = _reschedule(client, "plan-1", {"new_exam_date": NEW_EXAM})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rescheduled"] == 7
    assert body["preserved_done"] == 2

    todo = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks",
        params={"profile_id": ACTIVE_ID, "status": "todo"},
    ).json()["items"]
    assert todo
    for task in todo:
        assert date.fromisoformat(task["scheduled_date"]) >= TODAY
        assert task["scheduled_date"] <= NEW_EXAM


def test_g3_keeps_done_tasks_exactly_where_they_were(client: TestClient) -> None:
    before = {
        task["id"]: task["scheduled_date"]
        for task in client.get(
            f"{routes.CAMPUS_PREFIX}/tasks",
            params={"profile_id": ACTIVE_ID, "status": "done"},
        ).json()["items"]
    }
    assert _reschedule(client, "plan-1", {"new_exam_date": NEW_EXAM}).status_code == 200
    after = {
        task["id"]: task["scheduled_date"]
        for task in client.get(
            f"{routes.CAMPUS_PREFIX}/tasks",
            params={"profile_id": ACTIVE_ID, "status": "done"},
        ).json()["items"]
    }
    assert before == after


def test_g3_keeps_the_doing_task_where_it_was(client: TestClient) -> None:
    assert _reschedule(client, "plan-1", {"new_exam_date": NEW_EXAM}).status_code == 200
    doing = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks",
        params={"profile_id": ACTIVE_ID, "status": "doing"},
    ).json()["items"]
    assert [task["scheduled_date"] for task in doing] == ["2026-09-07"]


def test_g3_boosts_lagging_tracks_priority(client: TestClient) -> None:
    assert _reschedule(client, "plan-1", {"new_exam_date": NEW_EXAM}).status_code == 200
    tasks = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": ACTIVE_ID, "status": "todo"}
    ).json()["items"]
    politics = [task for task in tasks if task["subject"] == "politics"]
    english = [task for task in tasks if task["subject"] == "english"]
    assert politics and all(task["priority"] == 1 for task in politics)
    assert english and all(task["priority"] == 2 for task in english)


def test_g3_updates_the_profile_and_the_plan_horizon(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    assert _reschedule(client, "plan-1", {"new_exam_date": NEW_EXAM}).status_code == 200
    assert seeded_store.get("exam_profile", ACTIVE_ID)["exam_date"] == NEW_EXAM
    assert seeded_store.get("study_plan", "plan-1")["end_date"] == NEW_EXAM


def test_g3_falls_back_to_the_profile_exam_date(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    response = _reschedule(client, "plan-1", {})
    assert response.status_code == 200
    assert response.json()["rescheduled"] == 7
    assert seeded_store.get("study_plan", "plan-1")["end_date"] == "2026-12-31"


def test_g3_requires_an_exam_date_somewhere(client: TestClient) -> None:
    response = _reschedule(client, "plan-other", {}, profile_id=OTHER_ID)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXAM_DATE_REQUIRED"


def test_g3_refuses_a_past_exam_date(client: TestClient) -> None:
    response = _reschedule(client, "plan-1", {"new_exam_date": "2026-09-01"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXAM_DATE_REQUIRED"


def test_g3_reschedules_a_one_task_plan(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.update("study_plan", "plan-other", {"end_date": "2027-06-30"})
    response = _reschedule(
        client, "plan-other", {"new_exam_date": NEW_EXAM}, profile_id=OTHER_ID
    )
    assert response.status_code == 200
    assert response.json() == {"rescheduled": 1, "preserved_done": 0}


def test_g3_refuses_another_profiles_plan(client: TestClient) -> None:
    response = _reschedule(client, "plan-other", {"new_exam_date": NEW_EXAM})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_g3_refuses_a_missing_plan_as_forbidden(client: TestClient) -> None:
    response = _reschedule(client, "nonexistent-plan", {"new_exam_date": NEW_EXAM})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_g3_refuses_a_finished_profile(client: TestClient) -> None:
    response = _reschedule(
        client, "plan-1", {"new_exam_date": NEW_EXAM}, profile_id=FINISHED_ID
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


def test_g3_rejects_a_malformed_date(client: TestClient) -> None:
    assert _reschedule(client, "plan-1", {"new_exam_date": "2027/01/31"}).status_code == 422


def test_g3_rejects_unknown_body_fields(client: TestClient) -> None:
    assert _reschedule(client, "plan-1", {"profile_id": ACTIVE_ID}).status_code == 422
