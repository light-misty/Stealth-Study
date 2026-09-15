"""F5 计划生成端点（03 §4.4 F5、07 §4 T11 的 KY-01/02）。

`POST /v1/campus/plans/generate` 按档案的 TrackSpec 分台（01 §3.2：service 不分支 track id），
把"今天 → 考试日"拆成周级 + 日级任务，验收口径为 07 §4 T11 ①：四轨周级+日级、
每轨周级任务数 = 周数、无空轨；结构（轨数/周数/日期网格）由代码保证，模型只贡献每周主题文案，
因此异构组合（考不考数学）与模型输出的好坏都不会破坏结构不变量。

模型契约对齐 03 §4.4 F5 的错误清单：未配模型 `MODEL_NOT_CONFIGURED`、调用失败/超时
`MODEL_TIMEOUT`、缺考试日期 `EXAM_DATE_REQUIRED`。
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

ACTIVE_ID = "profile-kaoyan"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

TODAY = date(2026, 9, 15)
EXAM = date(2026, 12, 26)

PLAN_JSON = json.dumps(
    {
        "tracks": {
            "politics": {"weekly_goals": ["马原强化", "毛中特梳理"]},
            "english": {"weekly_goals": ["真题阅读精读"]},
            "math": {"weekly_goals": ["高数专题刷题"]},
            "major": {"weekly_goals": ["专业课一轮"]},
        }
    }
)


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


def _insert_profile(
    instance: store.CampusStore,
    profile_id: str,
    *,
    title: str,
    status: str = models.ProfileStatus.ACTIVE.value,
    exam_date: Optional[str] = None,
    subjects: Optional[list[str]] = None,
) -> None:
    instance.insert(
        "exam_profile",
        {
            "id": profile_id,
            "track_type": models.TrackType.KAOYAN.value,
            "title": title,
            "status": status,
            "exam_date": exam_date,
            "subjects": json.dumps(subjects or []),
        },
    )


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    _insert_profile(
        instance, ACTIVE_ID, title="2027 考研", exam_date=EXAM.isoformat()
    )
    _insert_profile(instance, OTHER_ID, title="另一个档案")
    _insert_profile(
        instance, FINISHED_ID, title="已结课", status=models.ProfileStatus.FINISHED.value
    )
    try:
        yield instance
    finally:
        instance.close()


class FakeManager:
    """router 的假 sidecar：模型就绪、provider 按脚本回放。"""

    def __init__(self, text: str = "", error: Optional[Exception] = None) -> None:
        self.model = "stub:planner"
        self.provider = self
        self._text = text
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": True, "models": [self.model]}

    def complete(self, *, model: str, messages: list[dict], **settings: Any) -> Any:
        self.calls.append({"model": model, "messages": messages, "settings": settings})
        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._text)


@pytest.fixture()
def client(seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


@pytest.fixture()
def model_client(seeded_store: store.CampusStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    manager = FakeManager(text=PLAN_JSON)
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    monkeypatch.setattr("ss.campus.service._utc_today", lambda: TODAY)
    return TestClient(app)


def _generate(client: TestClient, profile_id: str = ACTIVE_ID) -> Any:
    return client.post(f"{routes.CAMPUS_PREFIX}/plans/generate", json={"profile_id": profile_id})


def _tasks(client: TestClient, profile_id: str = ACTIVE_ID) -> list[dict]:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": profile_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_f5_requires_a_configured_model(client: TestClient) -> None:
    response = _generate(client)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"


def test_f5_requires_an_exam_date(client: TestClient) -> None:
    response = _generate(client, OTHER_ID)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXAM_DATE_REQUIRED"


def test_f5_refuses_a_past_exam_date(
    seeded_store: store.CampusStore, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ss.campus.service._utc_today", lambda: TODAY)
    seeded_store.update("exam_profile", OTHER_ID, {"exam_date": "2026-09-01"})
    response = _generate(client, OTHER_ID)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXAM_DATE_REQUIRED"


def test_f5_generates_a_four_track_plan(model_client: TestClient) -> None:
    response = _generate(model_client)
    assert response.status_code == 200, response.text
    body = response.json()
    days = (EXAM - TODAY).days
    weeks = math.ceil(days / 7)
    assert body["first_date"] == TODAY.isoformat()
    assert body["task_count"] == weeks * 4 + days

    tasks = _tasks(model_client)
    assert {task["subject"] for task in tasks} == {"politics", "english", "math", "major"}
    for track in ("politics", "english", "math", "major"):
        owned = [task for task in tasks if task["subject"] == track]
        weekly = [task for task in owned if "每日" not in task["title"]]
        assert len(weekly) == weeks
        assert owned
    daily = [task for task in tasks if "每日" in task["title"]]
    assert len(daily) == days
    assert all(task["status"] == "todo" for task in tasks)
    assert all(task["board_card_id"] is None for task in tasks)


def test_f5_weekly_tasks_land_on_the_week_grid(model_client: TestClient) -> None:
    assert _generate(model_client).status_code == 200
    tasks = _tasks(model_client)
    weekly = [task for task in tasks if "每日" not in task["title"]]
    assert all(
        (date.fromisoformat(task["scheduled_date"]) - TODAY).days % 7 == 0
        for task in weekly
    )
    weeks = math.ceil((EXAM - TODAY).days / 7)
    for track in ("politics", "english", "math", "major"):
        assert sum(1 for task in weekly if task["subject"] == track) == weeks
    assert max(date.fromisoformat(task["scheduled_date"]) for task in tasks) <= EXAM


def test_f5_model_themes_enrich_weekly_titles(model_client: TestClient) -> None:
    assert _generate(model_client).status_code == 200
    titles = " | ".join(task["title"] for task in _tasks(model_client))
    assert "马原强化" in titles
    assert "专业课一轮" in titles


def test_f5_survives_unusable_model_output(seeded_store: store.CampusStore) -> None:
    manager = FakeManager(text="这不是一段结构化输出")
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    client = TestClient(app)
    response = _generate(client)
    assert response.status_code == 200
    tasks = _tasks(client)
    assert tasks
    assert "马原强化" not in " | ".join(task["title"] for task in tasks)


def test_f5_model_failure_maps_to_model_timeout(seeded_store: store.CampusStore) -> None:
    manager = FakeManager(error=RuntimeError("ReadTimeout"))
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    client = TestClient(app)
    response = _generate(client)
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "MODEL_TIMEOUT"


def test_f5_respects_heterogeneous_subjects(
    seeded_store: store.CampusStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ss.campus.service._utc_today", lambda: TODAY)
    seeded_store.update(
        "exam_profile",
        OTHER_ID,
        {
            "exam_date": EXAM.isoformat(),
            "subjects": json.dumps(["politics", "english", "major"]),
        },
    )
    manager = FakeManager(text=PLAN_JSON)
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    client = TestClient(app)
    response = _generate(client, OTHER_ID)
    assert response.status_code == 200
    days = (EXAM - TODAY).days
    weeks = math.ceil(days / 7)
    assert response.json()["task_count"] == weeks * 3 + days
    subjects = {task["subject"] for task in _tasks(client, OTHER_ID)}
    assert subjects == {"politics", "english", "major"}


def test_f5_records_an_ai_generated_plan_row(
    model_client: TestClient, seeded_store: store.CampusStore
) -> None:
    assert _generate(model_client).status_code == 200
    plans = seeded_store.list_rows("study_plan", profile_id=ACTIVE_ID)
    assert len(plans) == 1
    plan = plans[0]
    assert plan["track"] == "overall"
    assert plan["source"] == models.PlanSource.AI_GENERATED.value
    assert plan["start_date"] == TODAY.isoformat()
    assert plan["end_date"] == EXAM.isoformat()


def test_f5_refuses_a_finished_profile(client: TestClient) -> None:
    response = _generate(client, FINISHED_ID)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


def test_f5_refuses_a_forged_profile(client: TestClient) -> None:
    response = _generate(client, "nonexistent-uuid")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROFILE_NOT_FOUND"


def test_f5_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/plans/generate", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_f5_rejects_unknown_body_fields(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/plans/generate",
        json={"profile_id": ACTIVE_ID, "exam_date": "2027-06-01"},
    )
    assert response.status_code == 422
