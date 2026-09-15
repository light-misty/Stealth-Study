"""F5 计划生成端点（03 §4.6 F5、07 §4 T10、PRD CET1 验收③）。

F5 是**共享端点**（03 标注 "CET-03/KY-01/02，按 TrackSpec 分台"）：本阶段交付 CET 台所需的能力，
T11 的考研台沿用同一端点。因此实现里**不得出现任何 `if track == "cet"` 分支**（01 §3.2 的分层铁律）——
科目骨架、投入优先级全部从 `tracks.py` 的 `TrackSpec.subject_skeleton` 取值，加第四台只需往字典加一项。

结构约束由服务端保证（覆盖到考试日期、每天 ≥1 条、按骨架顺序定优先级），AI 只负责内容，
所以 PRD CET1 验收③ 是代码性质而非模型性质。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store, tracks

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
NO_DATE_ID = "profile-no-date"

EXAM_DATE = (date.today() + timedelta(days=4)).isoformat()
START_DATE = date.today().isoformat()
FIRST_SUBJECT, SECOND_SUBJECT = tracks.CET_SPEC.subject_skeleton[0], tracks.CET_SPEC.subject_skeleton[1]


def plan_payload(days: int = 5, *, subject: str | None = None, start: str = START_DATE) -> str:
    """A plan whose days are all covered, so no server-side gap filling is needed."""
    first = date.fromisoformat(start)
    tasks = [
        {
            "date": (first + timedelta(days=offset)).isoformat(),
            "subject": subject or tracks.CET_SPEC.subject_skeleton[offset % len(tracks.CET_SPEC.subject_skeleton)],
            "title": f"第 {offset + 1} 天任务",
            "detail": "按分值性价比排序的当日动作",
            "est_minutes": 30,
        }
        for offset in range(days)
    ]
    return json.dumps({"goal_desc": "四周冲刺到 425", "tasks": tasks})


class FakeProvider:
    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses if responses is not None else {"default": plan_payload()}
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
    for profile_id, title, exam_date, track in (
        (ACTIVE_ID, "六级 12 月", EXAM_DATE, models.TrackType.CET.value),
        (OTHER_ID, "另一个档案", EXAM_DATE, models.TrackType.CET.value),
        (NO_DATE_ID, "没填日期的档案", None, models.TrackType.CET.value),
        (FINISHED_ID, "已结课", EXAM_DATE, models.TrackType.CET.value),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": track,
                "title": title,
                "exam_date": exam_date,
                "status": (
                    models.ProfileStatus.FINISHED.value
                    if profile_id == FINISHED_ID
                    else models.ProfileStatus.ACTIVE.value
                ),
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


def _generate(client: TestClient, profile_id: str = ACTIVE_ID):
    return client.post(f"{routes.CAMPUS_PREFIX}/plans/generate", json={"profile_id": profile_id})


def test_f5_builds_a_plan_that_covers_every_day_until_the_exam(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    body = _generate(client).json()
    assert body["first_date"] == START_DATE
    assert body["plan_id"]
    plan = seeded_store.get("study_plan", body["plan_id"])
    assert plan["profile_id"] == ACTIVE_ID
    assert plan["start_date"] == START_DATE
    assert plan["end_date"] == EXAM_DATE
    assert plan["goal_desc"] == "四周冲刺到 425"
    tasks = seeded_store.list_rows("plan_task", profile_id=ACTIVE_ID)
    assert len(tasks) == body["task_count"]
    days = {task["scheduled_date"] for task in tasks}
    assert days == {(date.fromisoformat(START_DATE) + timedelta(days=offset)).isoformat() for offset in range(5)}
    assert all(task["status"] == models.PlanTaskStatus.TODO.value for task in tasks)


def test_f5_requires_an_exam_date(client: TestClient) -> None:
    response = _generate(client, NO_DATE_ID)
    assert response.status_code == 400
    assert _detail(response)["code"] == "EXAM_DATE_REQUIRED"


def test_f5_orders_the_priority_by_the_declared_skeleton(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    body = _generate(client).json()
    tasks = seeded_store.list_rows("plan_task", profile_id=ACTIVE_ID, order_by="scheduled_date, rowid")
    skeleton = tracks.CET_SPEC.subject_skeleton
    for task in tasks:
        assert task["priority"] == skeleton.index(task["subject"]) + 1
    assert tasks[0]["subject"] == FIRST_SUBJECT


def test_f5_asks_the_model_for_the_declared_skeleton(client: TestClient, manager: FakeManager) -> None:
    _generate(client)
    prompt = "\n".join(str(message.get("content", "")) for message in manager.provider.seen[0]["messages"])
    for subject in tracks.CET_SPEC.subject_skeleton:
        assert subject in prompt
    assert EXAM_DATE in prompt


def test_f5_keeps_the_generated_task_content(client: TestClient, seeded_store: store.CampusStore) -> None:
    _generate(client)
    task = seeded_store.list_rows("plan_task", profile_id=ACTIVE_ID, order_by="scheduled_date, rowid")[0]
    assert task["title"] == "第 1 天任务"
    assert task["detail"] == "按分值性价比排序的当日动作"
    assert task["est_minutes"] == 30


def test_f5_fills_days_the_model_left_empty(client: TestClient, manager: FakeManager, seeded_store: store.CampusStore) -> None:
    """A short model answer still yields a plan covering every day (PRD CET1 ③ 是结构硬约束)."""
    manager.provider = FakeProvider(
        {
            "default": json.dumps(
                {
                    "goal_desc": "冲刺",
                    "tasks": [
                        {
                            "date": START_DATE,
                            "subject": FIRST_SUBJECT,
                            "title": "模型给的唯一一天",
                            "detail": "",
                            "est_minutes": 20,
                        }
                    ],
                }
            )
        }
    )
    body = _generate(client).json()
    tasks = seeded_store.list_rows("plan_task", profile_id=ACTIVE_ID)
    assert len(tasks) == body["task_count"] == 5
    assert any(task["title"] == "模型给的唯一一天" for task in tasks)
    assert {task["scheduled_date"] for task in tasks} == {
        (date.fromisoformat(START_DATE) + timedelta(days=offset)).isoformat() for offset in range(5)
    }


def test_f5_refuses_a_subject_outside_the_skeleton(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": plan_payload(subject="化学")})
    response = _generate(client)
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


@pytest.mark.parametrize("broken", ["not json", json.dumps({"tasks": []}), json.dumps({"goal_desc": "只有目标"})])
def test_f5_reports_unusable_plan_output(client: TestClient, manager: FakeManager, broken: str) -> None:
    manager.provider = FakeProvider({"default": broken})
    response = _generate(client)
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


def test_f5_reports_a_timeout(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": TimeoutError("upstream timeout")})
    response = _generate(client)
    assert response.status_code == 504
    assert _detail(response)["code"] == "MODEL_TIMEOUT"


def test_f5_refuses_without_a_configured_model(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(model="", ready=False)))
    client = TestClient(app)
    response = _generate(client)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"
    assert seeded_store.count("study_plan", "profile_id = ?", (ACTIVE_ID,)) == 0


def test_f5_refuses_a_finished_profile(client: TestClient) -> None:
    response = _generate(client, FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_f5_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/plans/generate", json={})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_f5_writes_nothing_when_the_exam_date_is_missing(
    client: TestClient, seeded_store: store.CampusStore, manager: FakeManager
) -> None:
    assert _generate(client, NO_DATE_ID).status_code == 400
    assert seeded_store.count("study_plan", "profile_id = ?", (NO_DATE_ID,)) == 0
    assert manager.provider.seen == []


def test_f5_tasks_land_in_the_today_view(client: TestClient, manager: FakeManager) -> None:
    """The generated tasks are immediately visible through G1 — the plan starts today."""
    body = _generate(client, OTHER_ID).json()
    assert body["first_date"] == START_DATE
    tasks = client.get(
        f"{routes.CAMPUS_PREFIX}/tasks", params={"profile_id": OTHER_ID, "date": START_DATE}
    ).json()["items"]
    assert tasks
    assert all(task["scheduled_date"] >= START_DATE for task in tasks)
