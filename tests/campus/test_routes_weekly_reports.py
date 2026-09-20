"""G5/G6 周报生成与列表端点（03 §4.7、07 §4 T11 的 KY-12、05 §4.7 周报五段）。

G5 把"本周"（含今天的 ISO 周，周一到周日）的任务数据聚合为固定五段周报落
`weekly_report` 表：总览、各轨明细（未完成原因归类：拖了/卡住了/超量）、新增错题
TOP 知识点（本周新增、出现 ≥2 次）、落后预警（落后计划 ≥15%）、下周建议（≤5 条、
每条带预计用时）。生成是**确定性的数据聚合**——03 §4.7 给 G5 只登记了 `NO_TASK_DATA`
一个错误，模型内容经 T13 的自动化模板进入，不经本端点。

一周一报（`UQ idx_wr_week`）：同一周重复生成走 UPSERT，不堆叠重复行。
打卡/热力口径与 G4 一致：只认 `completed_at`。
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
FINISHED_ID = "profile-finished"

TODAY = date(2026, 9, 15)
WEEK_START = "2026-09-14"
WEEK_END = "2026-09-20"
EXAM = "2026-12-31"


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


def _insert_task(
    instance: store.CampusStore,
    task_id: str,
    subject: str,
    scheduled: str,
    status: str,
    *,
    profile_id: str = ACTIVE_ID,
    est_minutes: int = 30,
    completed_at: Any = None,
) -> None:
    instance.insert(
        "plan_task",
        {
            "id": task_id,
            "plan_id": "plan-1",
            "profile_id": profile_id,
            "title": f"任务 {task_id}",
            "subject": subject,
            "scheduled_date": scheduled,
            "est_minutes": est_minutes,
            "status": status,
            "completed_at": completed_at,
        },
    )


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, title, status in (
        (ACTIVE_ID, "2027 考研", models.ProfileStatus.ACTIVE.value),
        (OTHER_ID, "另一个档案", models.ProfileStatus.ACTIVE.value),
        (FINISHED_ID, "已结课", models.ProfileStatus.FINISHED.value),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.KAOYAN.value,
                "title": title,
                "exam_date": EXAM,
                "daily_minutes": 60,
                "status": status,
            },
        )
    instance.insert(
        "study_plan",
        {
            "id": "plan-1",
            "profile_id": ACTIVE_ID,
            "track": "overall",
            "start_date": "2026-08-01",
            "end_date": EXAM,
        },
    )
    _insert_task(
        instance, "t-p-done", "politics", WEEK_START, "done",
        completed_at=f"{WEEK_START}T08:00:00Z",
    )
    _insert_task(instance, "t-p-todo", "politics", "2026-09-15", "todo")
    _insert_task(instance, "t-p-overdue", "politics", "2026-09-10", "todo")
    _insert_task(instance, "t-e-doing", "english", "2026-09-16", "doing")
    _insert_task(instance, "t-e-heavy", "english", "2026-09-18", "todo", est_minutes=120)
    _insert_task(
        instance, "t-m-done", "math", "2026-09-15", "done",
        completed_at="2026-09-15T10:00:00Z",
    )
    _insert_task(instance, "t-j-todo", "major", "2026-09-19", "todo")
    for index, (point_id, subject, created_at) in enumerate(
        (
            ("kp-1", "politics", f"{WEEK_START}T08:00:00Z"),
            ("kp-1", "politics", "2026-09-15T09:00:00Z"),
            (None, "politics", "2026-09-15T09:30:00Z"),
            ("kp-1", "politics", "2026-09-01T09:00:00Z"),
        ),
        start=1,
    ):
        instance.insert(
            "mistake_book",
            {
                "id": f"mb-{index}",
                "profile_id": ACTIVE_ID,
                "attempt_id": "attempt-x",
                "track_type": models.TrackType.KAOYAN.value,
                "subject": subject,
                "point_id": point_id,
                "created_at": created_at,
                "last_wrong_at": created_at,
            },
        )
    instance.insert(
        "knowledge_point",
        {"id": "kp-1", "profile_id": ACTIVE_ID, "title": "德育原则"},
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(seeded_store: store.CampusStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("stealth_study.campus.service._utc_today", lambda: TODAY)
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


def _generate(client: TestClient, profile_id: str = ACTIVE_ID) -> Any:
    return client.post(
        f"{routes.CAMPUS_PREFIX}/weekly-reports/generate",
        json={"profile_id": profile_id},
    )


def _reports(client: TestClient, profile_id: str = ACTIVE_ID) -> Any:
    return client.get(
        f"{routes.CAMPUS_PREFIX}/weekly-reports", params={"profile_id": profile_id}
    )


def test_g5_generates_the_current_week_report(client: TestClient) -> None:
    response = _generate(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile_id"] == ACTIVE_ID
    assert body["week_start"] == WEEK_START
    assert body["week_end"] == WEEK_END


def test_g5_completion_rate_covers_overall_and_each_track(client: TestClient) -> None:
    body = _generate(client).json()
    rate = body["completion_rate"]
    assert rate["overall"] == round(2 / 6, 4)
    assert rate["politics"] == 0.5
    assert rate["english"] == 0.0
    assert rate["math"] == 1.0
    assert rate["major"] == 0.0


def test_g5_ranks_this_weeks_repeated_mistake_points(client: TestClient) -> None:
    body = _generate(client).json()
    assert body["top_mistake_points"] == [
        {"point_id": "kp-1", "title": "德育原则", "count": 2}
    ]


def test_g5_content_carries_the_five_fixed_sections(client: TestClient) -> None:
    body = _generate(client).json()
    content = body["content_md"]
    for marker in ("一、总览", "二、各轨明细", "三、新增错题", "四、落后预警", "五、下周建议"):
        assert marker in content, marker
    assert "107 天" in content
    for track in ("政治", "英语", "数学", "专业课"):
        assert track in content
    assert "卡住了" in content and "超量" in content and "拖了" in content
    assert "英语" in content.split("四、落后预警", 1)[1].split("五、", 1)[0]


def test_g5_suggestion_carries_actions_with_minutes(client: TestClient) -> None:
    body = _generate(client).json()
    suggestion = body["suggestion"]
    assert "补做" in suggestion and "1 个拖期任务" in suggestion
    assert "卡住" in suggestion
    assert "英语" in suggestion and "专业课" in suggestion
    assert "分钟" in suggestion
    assert suggestion.count("\n") <= 4


def test_g5_upserts_within_the_same_week(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    first = _generate(client).json()
    second = _generate(client).json()
    assert first["id"] == second["id"]
    rows = seeded_store.list_rows("weekly_report", profile_id=ACTIVE_ID)
    assert len(rows) == 1


def test_g5_refuses_a_profile_without_any_task(client: TestClient) -> None:
    response = _generate(client, OTHER_ID)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_TASK_DATA"


def test_g5_refuses_a_finished_profile(client: TestClient) -> None:
    response = _generate(client, FINISHED_ID)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


def test_g5_refuses_a_forged_profile(client: TestClient) -> None:
    response = _generate(client, "nonexistent-uuid")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROFILE_NOT_FOUND"


def test_g5_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/weekly-reports/generate", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_g5_rejects_unknown_body_fields(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/weekly-reports/generate",
        json={"profile_id": ACTIVE_ID, "week": "current"},
    )
    assert response.status_code == 422


def test_g6_lists_reports_newest_week_first(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "weekly_report",
        {
            "id": "wr-earlier",
            "profile_id": ACTIVE_ID,
            "week_start": "2026-09-07",
            "week_end": "2026-09-13",
        },
    )
    _generate(client)
    response = _reports(client)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["week_start"] for item in items] == [WEEK_START, "2026-09-07"]


def test_g6_decodes_the_json_columns(client: TestClient) -> None:
    _generate(client)
    item = _reports(client).json()["items"][0]
    assert isinstance(item["completion_rate"], dict)
    assert isinstance(item["top_mistake_points"], list)


def test_g6_returns_an_empty_list_without_reports(client: TestClient) -> None:
    assert _reports(client).json() == {"items": []}


def test_g6_never_leaks_another_profile(client: TestClient) -> None:
    _generate(client)
    assert _reports(client, OTHER_ID).json() == {"items": []}


def test_g6_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/weekly-reports")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"
