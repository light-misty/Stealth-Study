"""T11 考研台端到端主链与边界场景（07 §4 T11 验收①②③、08 §8 "端点契约抽查"）。

两条证据，与 T09 的 test_campus_flow.py 同构：

* `test_the_kaoyan_story_runs_end_to_end` —— 用一条真实主线把 T11 的 9 个端点串起来跑
  （建档设考试日期 → F5 生成计划 → G2 拖卡写回 → G3 一键重排 → G4 进度 → G5/G6 周报 →
  G7/G8 院校档案 → 删档级联），证明它们在同一份 store/guard/service 上协同；
* 边界场景组 —— F5 按 TrackSpec 分台（CET 四题型轨，01 §3.2 无 track 分支）、短周期
  （不足四周）、两年长周期、非法 subjects 回落骨架、G4 打卡从昨天起数、G5 整周无
  排期任务与缺考试日期、G9 部分抽取的 confidence。
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import routes, store

TODAY = date(2026, 9, 15)
EXAM = date(2026, 12, 26)

PLAN_JSON = json.dumps(
    {
        "tracks": {
            "politics": {"weekly_goals": ["马原"]},
            "english": {"weekly_goals": ["阅读"]},
            "math": {"weekly_goals": ["高数"]},
            "major": {"weekly_goals": ["专业课"]},
        }
    }
)


class FakeManager:
    def __init__(self, text: str = "", error: Optional[Exception] = None) -> None:
        self.model = "stub:flow"
        self.provider = self
        self._text = text
        self._error = error

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": True, "models": [self.model]}

    def complete(self, *, model: str, messages: list[dict], **settings: Any) -> Any:
        from types import SimpleNamespace

        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._text)


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> Any:
    instance = store.CampusStore(campus_db_path)
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def model_client(
    seeded_store: Any, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr("ss.campus.service._utc_today", lambda: TODAY)
    monkeypatch.setattr(
        "ss.campus.service._utcnow_iso", lambda: f"{TODAY.isoformat()}T08:00:00Z"
    )
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(text=PLAN_JSON)))
    return TestClient(app)


def _create_kaoyan(client: TestClient, **extra: Any) -> str:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/profiles",
        json={"track_type": "kaoyan", "title": "2027 考研", **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _generate_plan(client: TestClient, profile_id: str) -> str:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/plans/generate", json={"profile_id": profile_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["plan_id"]


def test_the_kaoyan_story_runs_end_to_end(
    model_client: TestClient, seeded_store: Any
) -> None:
    client = model_client
    prefix = routes.CAMPUS_PREFIX

    profile_id = _create_kaoyan(
        client, exam_date=EXAM.isoformat(), target_score=380, daily_minutes=90
    )
    assert (
        client.patch(f"{prefix}/app-state", json={"active_profile_id": profile_id}).status_code
        == 200
    )

    plan_id = _generate_plan(client, profile_id)
    tasks = client.get(f"{prefix}/tasks", params={"profile_id": profile_id}).json()["items"]
    assert tasks

    first_todo = next(task for task in tasks if task["status"] == "todo")
    for status in ("doing", "review", "done"):
        dragged = client.patch(
            f"{prefix}/tasks/{first_todo['id']}",
            json={"status": status},
            params={"profile_id": profile_id},
        )
        assert dragged.status_code == 200, dragged.text
    assert dragged.json()["completed_at"]

    illegal = client.patch(
        f"{prefix}/tasks/{first_todo['id']}",
        json={"status": "todo"},
        params={"profile_id": profile_id},
    )
    assert illegal.status_code == 409
    assert illegal.json()["detail"]["code"] == "ILLEGAL_TRANSITION"

    rescheduled = client.post(
        f"{prefix}/plans/{plan_id}/reschedule",
        json={"new_exam_date": "2027-01-31"},
        params={"profile_id": profile_id},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["preserved_done"] == 1
    assert (
        client.get(f"{prefix}/profiles/{profile_id}").json()["exam_date"] == "2027-01-31"
    )

    progress = client.get(f"{prefix}/progress", params={"profile_id": profile_id})
    assert progress.status_code == 200
    assert progress.json()["streak_days"] == 1

    report = client.post(
        f"{prefix}/weekly-reports/generate", json={"profile_id": profile_id}
    )
    assert report.status_code == 200, report.text
    content = report.json()["content_md"]
    assert "一、总览" in content and "五、下周建议" in content
    listed = client.get(f"{prefix}/weekly-reports", params={"profile_id": profile_id})
    assert [item["id"] for item in listed.json()["items"]] == [report.json()["id"]]

    school = client.patch(
        f"{prefix}/school-profile",
        json={"school": "华东师范大学", "major": "教育学"},
        params={"profile_id": profile_id},
    )
    assert school.status_code == 200
    assert (
        client.get(f"{prefix}/school-profile", params={"profile_id": profile_id})
        .json()["school"]
        == "华东师范大学"
    )

    deleted = client.delete(f"{prefix}/profiles/{profile_id}")
    assert deleted.status_code == 200
    assert client.get(
        f"{prefix}/school-profile", params={"profile_id": profile_id}
    ).status_code == 404
    assert seeded_store.list_rows("school_profile", profile_id=profile_id) == []


# ---------- 边界场景 ----------


def test_f5_serves_the_cet_station_from_the_same_code_path(
    model_client: TestClient,
) -> None:
    client = model_client
    created = client.post(
        f"{routes.CAMPUS_PREFIX}/profiles",
        json={
            "track_type": "cet",
            "title": "六级备考",
            "level": "cet6",
            "exam_date": EXAM.isoformat(),
        },
    )
    profile_id = created.json()["id"]
    _generate_plan(client, profile_id)
    tasks = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": profile_id}
    ).json()["items"]
    assert {task["subject"] for task in tasks} == {
        "listening",
        "reading",
        "writing",
        "translation",
    }
    weeks = math.ceil((EXAM - TODAY).days / 7)
    for track in ("listening", "reading", "writing", "translation"):
        weekly = [
            task
            for task in tasks
            if task["subject"] == track and "每日" not in task["title"]
        ]
        assert len(weekly) == weeks


def test_f5_handles_a_span_shorter_than_four_stages(
    model_client: TestClient,
) -> None:
    client = model_client
    profile_id = _create_kaoyan(client, exam_date=(TODAY + timedelta(days=6)).isoformat())
    _generate_plan(client, profile_id)
    tasks = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": profile_id}
    ).json()["items"]
    for track in ("politics", "english", "math", "major"):
        weekly = [
            task
            for task in tasks
            if task["subject"] == track and "每日" not in task["title"]
        ]
        assert len(weekly) == 1
    stages = {
        task["detail"].split("阶段", 1)[0]
        for task in tasks
        if "每日" not in task["title"]
    }
    assert len(stages) == 1


def test_f5_ignores_unknown_subjects_and_falls_back_to_chosen(
    model_client: TestClient,
) -> None:
    client = model_client
    profile_id = _create_kaoyan(
        client, exam_date=EXAM.isoformat(), subjects=["politics", "cooking", "english"]
    )
    _generate_plan(client, profile_id)
    tasks = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": profile_id}
    ).json()["items"]
    assert {task["subject"] for task in tasks} == {"politics", "english"}


def test_f5_covers_a_two_year_horizon(model_client: TestClient) -> None:
    client = model_client
    far = TODAY + timedelta(days=700)
    profile_id = _create_kaoyan(client, exam_date=far.isoformat())
    body = client.post(
        f"{routes.CAMPUS_PREFIX}/plans/generate", json={"profile_id": profile_id}
    ).json()
    assert body["task_count"] == 100 * 4 + 700
    tasks = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": profile_id}
    ).json()["items"]
    weekly = [task for task in tasks if "每日" not in task["title"]]
    assert len(weekly) == 100 * 4


def test_g4_counts_a_streak_starting_yesterday(
    model_client: TestClient, seeded_store: Any
) -> None:
    client = model_client
    profile_id = _create_kaoyan(client, exam_date=EXAM.isoformat())
    for index, day in enumerate((2, 1)):
        seeded_store.insert(
            "plan_task",
            {
                "id": f"t-streak-{index}",
                "plan_id": "plan-x",
                "profile_id": profile_id,
                "title": f"打卡任务 {index}",
                "subject": "politics",
                "scheduled_date": (TODAY - timedelta(days=day)).isoformat(),
                "status": "done",
                "completed_at": (
                    f"{(TODAY - timedelta(days=day)).isoformat()}T08:00:00Z"
                ),
            },
        )
    progress = client.get(
        f"{routes.CAMPUS_PREFIX}/progress", params={"profile_id": profile_id}
    )
    assert progress.json()["streak_days"] == 2


def test_g5_covers_a_week_without_scheduled_tasks(
    model_client: TestClient, seeded_store: Any
) -> None:
    client = model_client
    profile_id = _create_kaoyan(client, exam_date=EXAM.isoformat())
    seeded_store.insert(
        "plan_task",
        {
            "id": "t-far-away",
            "plan_id": "plan-x",
            "profile_id": profile_id,
            "title": "远期任务",
            "subject": "politics",
            "scheduled_date": (TODAY + timedelta(days=30)).isoformat(),
        },
    )
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/weekly-reports/generate",
        json={"profile_id": profile_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completion_rate"]["overall"] == 0.0
    assert "本周无排期任务" in body["content_md"]


def test_g5_reports_a_missing_exam_date(
    model_client: TestClient, seeded_store: Any
) -> None:
    client = model_client
    profile_id = _create_kaoyan(client)
    seeded_store.insert(
        "plan_task",
        {
            "id": "t-no-exam",
            "plan_id": "plan-x",
            "profile_id": profile_id,
            "title": "无考试日期任务",
            "subject": "politics",
            "scheduled_date": TODAY.isoformat(),
        },
    )
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/weekly-reports/generate",
        json={"profile_id": profile_id},
    )
    assert response.status_code == 200
    assert "未设置考试日期" in response.json()["content_md"]


def test_g9_scores_a_partial_extraction(model_client: TestClient) -> None:
    profile_id = _create_kaoyan(model_client, exam_date=EXAM.isoformat())
    partial = json.dumps({"school": "复旦大学", "enroll_count": "55"})
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(text=partial)))
    bare = TestClient(app)
    response = bare.post(
        f"{routes.CAMPUS_PREFIX}/school-profile/extract",
        json={"profile_id": profile_id, "text": "简章"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["prefill"] == {"school": "复旦大学", "enroll_count": 55}
    assert body["confidence"] == round(2 / 8, 4)
