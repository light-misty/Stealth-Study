"""G1 任务列表端点（03 §4.7 G1、07 §4 T09 的「今日建议」）。

G1 同时承担两个用途，因此本文件把两者都钉住：

* **今日建议**：前端以 `date=<今天>` 调用，取当天任务与优先级；
* **自建看板的数据源**（ADR-11：看板数据即 `plan_task`，不触 Teams）：不带 `date` 即取全部任务。

`track` 过滤映射到 `plan_task.subject`（02 §4.10 用 subject 承载题型/轨），响应只有 `{items}`，
与 A1 一样不带分页信封（03 §4.7）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
FORGED_ID = "nonexistent-uuid"

TODAY = "2026-09-15"
TOMORROW = "2026-09-16"


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def seeded_store(campus_db_path: Path) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "2027 考研"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.KAOYAN.value,
                "title": title,
                "status": status,
            },
        )
    instance.insert(
        "study_plan",
        {"id": "plan-1", "profile_id": ACTIVE_ID, "track": models.PlanTrack.ENGLISH.value},
    )
    for task_id, profile_id, subject, scheduled, priority, status in (
        ("t-english", ACTIVE_ID, models.PlanTrack.ENGLISH.value, TODAY, 1, "todo"),
        ("t-math", ACTIVE_ID, models.PlanTrack.MATH.value, TODAY, 2, "doing"),
        ("t-done", ACTIVE_ID, models.PlanTrack.POLITICS.value, TODAY, 3, "done"),
        ("t-tomorrow", ACTIVE_ID, models.PlanTrack.MAJOR.value, TOMORROW, 1, "todo"),
        ("t-other", OTHER_ID, models.PlanTrack.ENGLISH.value, TODAY, 1, "todo"),
    ):
        instance.insert(
            "plan_task",
            {
                "id": task_id,
                "plan_id": "plan-1",
                "profile_id": profile_id,
                "title": f"任务 {task_id}",
                "subject": subject,
                "scheduled_date": scheduled,
                "priority": priority,
                "status": status,
            },
        )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


def _tasks(client: TestClient, **params) -> list[dict]:
    query = {"profile_id": ACTIVE_ID, **params}
    response = client.get(f"{routes.CAMPUS_PREFIX}/tasks", params=query)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_g1_lists_every_task_of_the_profile(client: TestClient) -> None:
    assert {task["id"] for task in _tasks(client)} == {
        "t-english",
        "t-math",
        "t-done",
        "t-tomorrow",
    }


def test_g1_orders_by_date_then_priority(client: TestClient) -> None:
    assert [task["id"] for task in _tasks(client)] == [
        "t-english",
        "t-math",
        "t-done",
        "t-tomorrow",
    ]


def test_g1_feeds_the_today_suggestion(client: TestClient) -> None:
    assert [task["id"] for task in _tasks(client, date=TODAY)] == [
        "t-english",
        "t-math",
        "t-done",
    ]


def test_g1_feeds_the_board_with_one_track_at_a_time(client: TestClient) -> None:
    english = _tasks(client, track=models.PlanTrack.ENGLISH.value)
    assert [task["id"] for task in english] == ["t-english"]
    assert english[0]["subject"] == models.PlanTrack.ENGLISH.value


def test_g1_filters_by_status(client: TestClient) -> None:
    assert [task["id"] for task in _tasks(client, status=models.PlanTaskStatus.DONE.value)] == [
        "t-done"
    ]
    assert {
        task["id"] for task in _tasks(client, status=models.PlanTaskStatus.TODO.value)
    } == {"t-english", "t-tomorrow"}


def test_g1_combines_filters(client: TestClient) -> None:
    assert [
        task["id"]
        for task in _tasks(client, date=TODAY, track=models.PlanTrack.MATH.value)
    ] == ["t-math"]
    assert _tasks(client, date=TOMORROW, track=models.PlanTrack.ENGLISH.value) == []


def test_g1_returns_the_documented_task_fields(client: TestClient) -> None:
    task = _tasks(client, date=TODAY)[0]
    assert task["plan_id"] == "plan-1"
    assert task["profile_id"] == ACTIVE_ID
    assert task["title"] == "任务 t-english"
    assert task["est_minutes"] == 30
    assert task["board_card_id"] is None
    assert task["completed_at"] is None


def test_g1_never_leaks_another_profile_tasks(client: TestClient) -> None:
    assert "t-other" not in {task["id"] for task in _tasks(client)}
    assert [task["id"] for task in _tasks(client, profile_id=OTHER_ID)] == ["t-other"]


def test_g1_reads_a_finished_profile(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": FINISHED_ID}
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_g1_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/tasks")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_g1_refuses_a_forged_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": FORGED_ID})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROFILE_NOT_FOUND"


@pytest.mark.parametrize(
    "params",
    [
        {"date": "2026/09/15"},
        {"status": "nope"},
        {"date": "15-09-2026"},
    ],
)
def test_g1_rejects_malformed_filters(client: TestClient, params: dict) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": ACTIVE_ID, **params}
    )
    assert response.status_code == 422


def test_g1_is_read_only(client: TestClient) -> None:
    assert client.post(f"{routes.CAMPUS_PREFIX}/tasks").status_code == 405
