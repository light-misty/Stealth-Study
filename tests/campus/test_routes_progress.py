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

from stealth_study import secrets
from stealth_study.campus import models, routes, store

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
    monkeypatch.setattr("stealth_study.campus.service._utc_today", lambda: TODAY)
    monkeypatch.setattr("stealth_study.campus.reminders.today", lambda: TODAY)
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
    assert body["by_track"] == {}
    assert body["streak_days"] == 0
    assert body["heatmap"] == []
    assert body["today"]["tasks"] == {"done": 0, "total": 0}


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
    monkeypatch.setattr("stealth_study.campus.service._utc_today", lambda: TODAY)
    monkeypatch.setattr("stealth_study.campus.reminders.today", lambda: TODAY)
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    client = TestClient(app)
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/progress", params={"profile_id": "profile-finished"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["by_track"] == {}
    assert body["streak_days"] == 0
    assert body["heatmap"] == []
    assert body["today"]["minutes"] == {"done": 0, "plan": 60}


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


# ---------------------------------------------------------------------------
# G4 的 today 块：右栏「今日进度」四行的数据源
# ---------------------------------------------------------------------------

# 正午 UTC 在 ±12 时区里都落进同一个本地日，因此这些行在任何 CI 机器上都不受时区影响。
NOON = "T12:00:00Z"
TODAY_ISO = TODAY.isoformat()


@pytest.fixture()
def today_store(seeded_store: store.CampusStore) -> store.CampusStore:
    seeded_store.update("exam_profile", ACTIVE_ID, {"daily_minutes": 90})
    for row_id, status, due in (
        ("rq-1", models.ReviewStatus.DONE.value, TODAY_ISO),
        ("rq-2", models.ReviewStatus.PENDING.value, TODAY_ISO),
        ("rq-3", models.ReviewStatus.DONE.value, YESTERDAY),
    ):
        seeded_store.insert(
            "review_queue",
            {
                "id": row_id,
                "profile_id": ACTIVE_ID,
                "item_type": models.ReviewItemType.VOCAB.value,
                "item_id": f"v-{row_id}",
                "due_at": f"{due}{NOON}",
                "status": status,
            },
        )
    for row_id, graded, created in (
        ("at-1", True, TODAY_ISO),
        ("at-2", False, TODAY_ISO),
        ("at-3", True, YESTERDAY),
    ):
        seeded_store.insert(
            "attempt",
            {
                "id": row_id,
                "profile_id": ACTIVE_ID,
                "track_type": models.TrackType.KAOYAN.value,
                "subject": "math",
                "user_answer": "x",
                "created_at": f"{created}{NOON}",
                **({"grading_json": "{}"} if graded else {}),
            },
        )
    for row_id, mastery, updated in (
        ("v-1", models.MasteryLevel.MASTERED.value, TODAY_ISO),
        ("v-2", models.MasteryLevel.FUZZY.value, TODAY_ISO),
        ("v-3", models.MasteryLevel.UNKNOWN.value, TODAY_ISO),
        ("v-4", models.MasteryLevel.MASTERED.value, YESTERDAY),
    ):
        seeded_store.insert(
            "vocab_item",
            {
                "id": row_id,
                "profile_id": ACTIVE_ID,
                "word": f"word-{row_id}",
                "mastery": mastery,
                "updated_at": f"{updated}{NOON}",
            },
        )
    for row_id, parse_status in (
        ("doc-1", models.ParseStatus.READY.value),
        ("doc-2", models.ParseStatus.PENDING.value),
        ("doc-3", models.ParseStatus.FAILED.value),
    ):
        seeded_store.insert(
            "source_doc",
            {
                "id": row_id,
                "profile_id": ACTIVE_ID,
                "title": row_id,
                "file_path": f"library/{row_id}.pdf",
                "imported_at": f"{TODAY_ISO}{NOON}",
                "parse_status": parse_status,
            },
        )
    for point_id in ("kp-1", "kp-2"):
        seeded_store.insert(
            "knowledge_point", {"id": point_id, "profile_id": ACTIVE_ID, "title": point_id}
        )
    seeded_store.insert(
        "mastery",
        {
            "id": "ms-1",
            "profile_id": ACTIVE_ID,
            "point_id": "kp-1",
            "level": models.MasteryLevel.MASTERED.value,
        },
    )
    seeded_store.insert(
        "review_queue",
        {
            "id": "rq-other",
            "profile_id": OTHER_ID,
            "item_type": models.ReviewItemType.VOCAB.value,
            "item_id": "v-x",
            "due_at": f"{TODAY_ISO}{NOON}",
            "status": models.ReviewStatus.PENDING.value,
        },
    )
    return seeded_store


def _today(client: TestClient, profile_id: str = ACTIVE_ID) -> dict:
    return _progress(client, profile_id)["today"]


def test_g4_today_counts_finished_minutes_against_the_daily_plan(
    seeded_store: store.CampusStore, client: TestClient
) -> None:
    seeded_store.update("exam_profile", ACTIVE_ID, {"daily_minutes": 90})
    today = _today(client)
    # 今日排期的 8 条任务里 5 条已完成，各按 est_minutes 默认 30 分钟计；时长偏好是档案的 90 分钟。
    assert today["minutes"] == {"done": 150, "plan": 90}
    assert today["tasks"] == {"done": 5, "total": 8}


def test_g4_today_counts_the_review_queue_due_today(client: TestClient, today_store: store.CampusStore) -> None:
    assert _today(client)["review"] == {"done": 1, "total": 2}


def test_g4_today_counts_graded_attempts_today(client: TestClient, today_store: store.CampusStore) -> None:
    assert _today(client)["grading"] == {"done": 1, "total": 2}


def test_g4_today_counts_new_words_against_the_daily_cap(
    client: TestClient, today_store: store.CampusStore
) -> None:
    assert _today(client)["vocab"] == {"done": 2, "quota": 30}


def test_g4_today_counts_parsed_documents(client: TestClient, today_store: store.CampusStore) -> None:
    assert _today(client)["docs"] == {"ready": 1, "total": 3}


def test_g4_today_counts_mastered_knowledge_points(
    client: TestClient, today_store: store.CampusStore
) -> None:
    assert _today(client)["knowledge"] == {"mastered": 1, "total": 2}


def test_g4_today_never_counts_another_profile_s_rows(
    client: TestClient, today_store: store.CampusStore
) -> None:
    body = _progress(client, OTHER_ID)["today"]
    assert body["review"] == {"done": 0, "total": 1}
    assert body["minutes"] == {"done": 30, "plan": 60}


def test_g4_today_is_a_zero_shape_for_a_profile_without_anything(
    seeded_store: store.CampusStore, client: TestClient
) -> None:
    seeded_store.insert(
        "exam_profile", {"id": "profile-clean", "track_type": "cet", "title": "全新档案"}
    )
    assert _today(client, "profile-clean") == {
        "date": TODAY_ISO,
        "minutes": {"done": 0, "plan": 60},
        "tasks": {"done": 0, "total": 0},
        "review": {"done": 0, "total": 0},
        "grading": {"done": 0, "total": 0},
        "vocab": {"done": 0, "quota": 30},
        "docs": {"ready": 0, "total": 0},
        "knowledge": {"mastered": 0, "total": 0},
    }
