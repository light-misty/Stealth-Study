"""G4 进度总览端点（03 §4.7 G4、07 §4 T11 的 KY-11）。

`GET /v1/campus/progress` 是考研台进度页的唯一数据源：四轨完成度、连续打卡天数、
热力图。口径钉死三件事——

* `by_track` 按 `plan_task.subject` 聚合，`rate = done/total`（空轨不出现）；
* 打卡与热力图只认 `completed_at`（G2 真实写回的时间戳），不凭 `status=done` 倒推日期，
  数据与实际完成记录一致（KY-11 验收 3）；
* `streak_days` 从今天（或昨天，今天尚未打卡时）向回数连续打卡天。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"

TODAY = date(2026, 9, 15)
YESTERDAY = "2026-09-14"
TWO_DAYS_AGO = "2026-09-13"
TWO_WEEKS_AGO = "2026-09-01"


def _iso(day: date) -> str:
    return day.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, title in (
        (ACTIVE_ID, "2027 考研"),
        (OTHER_ID, "另一个档案"),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.KAOYAN.value,
                "title": title,
            },
        )
    instance.insert(
        "study_plan", {"id": "plan-1", "profile_id": ACTIVE_ID, "track": "overall"}
    )
    rows = [
        ("t-p-done-1", "politics", "done", _iso(TODAY)),
        ("t-p-done-2", "politics", "done", f"{YESTERDAY}T00:00:00Z"),
        ("t-p-todo", "politics", "todo", None),
        ("t-e-done-1", "english", "done", f"{TWO_DAYS_AGO}T00:00:00Z"),
        ("t-e-done-2", "english", "done", f"{TWO_WEEKS_AGO}T00:00:00Z"),
        ("t-e-doing", "english", "doing", None),
        ("t-m-todo", "math", "todo", None),
        ("t-j-done", "major", "done", f"{YESTERDAY}T12:00:00Z"),
    ]
    for task_id, subject, status, completed_at in rows:
        instance.insert(
            "plan_task",
            {
                "id": task_id,
                "plan_id": "plan-1",
                "profile_id": ACTIVE_ID,
                "title": f"任务 {task_id}",
                "subject": subject,
                "scheduled_date": "2026-09-15",
                "status": status,
                "completed_at": completed_at,
            },
        )
    instance.insert(
        "plan_task",
        {
            "id": "t-other",
            "plan_id": "plan-1",
            "profile_id": OTHER_ID,
            "title": "别的档案的任务",
            "subject": "politics",
            "scheduled_date": "2026-09-15",
            "status": "done",
            "completed_at": _iso(TODAY),
        },
    )
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


def _progress(client: TestClient, profile_id: str = ACTIVE_ID) -> dict:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/progress", params={"profile_id": profile_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_g4_aggregates_completion_by_track(client: TestClient) -> None:
    by_track = _progress(client)["by_track"]
    assert by_track["politics"] == {"done": 2, "total": 3, "rate": round(2 / 3, 4)}
    assert by_track["english"] == {"done": 2, "total": 3, "rate": round(2 / 3, 4)}
    assert by_track["math"] == {"done": 0, "total": 1, "rate": 0.0}
    assert by_track["major"] == {"done": 1, "total": 1, "rate": 1.0}


def test_g4_counts_a_streak_across_consecutive_days(client: TestClient) -> None:
    assert _progress(client)["streak_days"] == 3


def test_g4_builds_the_heatmap_from_completed_at_only(client: TestClient) -> None:
    heatmap = _progress(client)["heatmap"]
    assert heatmap == [
        {"date": TWO_WEEKS_AGO, "count": 1},
        {"date": TWO_DAYS_AGO, "count": 1},
        {"date": YESTERDAY, "count": 2},
        {"date": TODAY.isoformat(), "count": 1},
    ]


def test_g4_counts_zero_for_a_profile_without_completions(client: TestClient) -> None:
    body = _progress(client, OTHER_ID)
    assert body["by_track"] == {"politics": {"done": 1, "total": 1, "rate": 1.0}}
    assert body["streak_days"] == 1
    assert body["heatmap"] == [{"date": TODAY.isoformat(), "count": 1}]


def test_g4_reports_an_empty_body_for_a_profile_without_tasks(
    seeded_store: store.CampusStore, client: TestClient
) -> None:
    seeded_store.insert(
        "exam_profile",
        {"id": "profile-empty", "track_type": "kaoyan", "title": "空档案"},
    )
    body = _progress(client, "profile-empty")
    assert body == {"by_track": {}, "streak_days": 0, "heatmap": []}


def test_g4_never_leaks_another_profile(client: TestClient) -> None:
    body = _progress(client)
    assert "t-other" not in str(body)
    assert sum(entry["total"] for entry in body["by_track"].values()) == 8


def test_g4_reads_a_finished_profile(
    seeded_store: store.CampusStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded_store.insert(
        "exam_profile",
        {
            "id": "profile-finished",
            "track_type": "kaoyan",
            "title": "已结课",
            "status": "finished",
        },
    )
    monkeypatch.setattr("ss.campus.service._utc_today", lambda: TODAY)
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    client = TestClient(app)
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/progress", params={"profile_id": "profile-finished"}
    )
    assert response.status_code == 200
    assert response.json() == {"by_track": {}, "streak_days": 0, "heatmap": []}


def test_g4_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/progress")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_g4_refuses_a_forged_profile(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/progress", params={"profile_id": "nonexistent-uuid"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROFILE_NOT_FOUND"
