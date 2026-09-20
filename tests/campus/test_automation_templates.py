"""T13 自动化模板（G-18，01 §2 `automation_templates.py` 契约、ADR-12）。

四条契约要点：

* **模板清单**（I2）：恰好 4 个模板（每日复习推送 / 周报复盘 / 冲刺倒计时 / 考试节点提醒），
  形状 `{id, title, cron_desc, kind}`，节点提醒为 `once`、其余为 `cron`；
* **一键安装**（I3）：经既有 automation CRUD（`create_automation` + `TaskStore`）创建，
  cron/`fire_at` 正确——每日复习跟随备考偏好的 `push_time`，节点提醒按考试日期落
  D-30/D-7/D-1 三个 `once` 任务（`Schedule.kind="once"` + `fire_at`，ADR-12：不走 OS 通知）；
* **幂等**（验收②）：重复安装不产生重复任务——以 `origin_session_id` 模板标记识别已装任务，
  返回既有 id；被手动删除的模板任务重新安装可再创建；
* **前置校验**：周报模板需要可用模型（`MODEL_NOT_CONFIGURED`），节点提醒需要考试日期
  （`EXAM_DATE_REQUIRED`），manager 无任务存储时 `AUTOMATION_UNAVAILABLE`。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.automation.store import TaskStore
from stealth_study.campus import models, routes, store

ACTIVE_ID = "profile-active"
FINISHED_ID = "profile-finished"
EXAM_DATE = date.today() + timedelta(days=90)


class FakeManager:
    def __init__(
        self,
        *,
        task_store: Any = None,
        model: str = "fake:model",
        ready: bool = True,
    ) -> None:
        self.model = model
        self._ready = ready
        self.task_store = task_store

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model] if self.model else []}

    def create_automation(self, payload: dict[str, Any]) -> dict[str, Any]:
        from stealth_study.automation.models import Schedule, ScheduledTask

        cron = (payload.get("cron") or "").strip() or None
        fire_at = (payload.get("fire_at") or "").strip() or None
        task = ScheduledTask(
            title=(payload.get("title") or "").strip(),
            instructions=(payload.get("instructions") or "").strip(),
            schedule=Schedule(kind="once" if (fire_at and not cron) else "cron", cron=cron, fire_at=fire_at),
            workspace="",
        )
        if self.task_store is not None and task.workspace == "":
            task.workspace = str((secrets.state_dir() / "scratch" / task.task_session_id).resolve())
            Path(task.workspace).mkdir(parents=True, exist_ok=True)
        if self.task_store is not None:
            self.task_store.save(task)
        return {"ok": True, "task": task.public()}


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def task_store(tmp_path: Path) -> TaskStore:
    instance = TaskStore(tmp_path / "tasks.db")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def seeded_store(campus_db_path: Path) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    instance.insert(
        "exam_profile",
        {"id": ACTIVE_ID, "track_type": models.TrackType.CET.value, "title": "六级 12 月"},
    )
    instance.insert(
        "exam_profile",
        {
            "id": FINISHED_ID,
            "track_type": models.TrackType.CET.value,
            "title": "已结课",
            "status": models.ProfileStatus.FINISHED.value,
        },
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(task_store: TaskStore, seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(task_store=task_store)))
    return TestClient(app)


def _detail(response) -> dict:
    return response.json()["detail"]


def _install(client: TestClient, tpl_id: str, profile_id: str = ACTIVE_ID):
    return client.post(
        f"/v1/campus/automation-templates/{tpl_id}/install",
        json={"profile_id": profile_id},
    )


# ---------- I2：模板清单 ----------


def test_i2_lists_exactly_the_four_templates(client: TestClient) -> None:
    body = client.get("/v1/campus/automation-templates").json()
    items = body["items"]
    assert len(items) == 4
    assert [item["id"] for item in items] == [
        "daily-review",
        "weekly-report",
        "sprint",
        "deadline-node",
    ]
    assert all(set(item) == {"id", "title", "cron_desc", "kind"} for item in items)
    kinds = {item["id"]: item["kind"] for item in items}
    assert kinds == {
        "daily-review": "cron",
        "weekly-report": "cron",
        "sprint": "cron",
        "deadline-node": "once",
    }


# ---------- I3：每日复习推送 ----------


def test_i3_daily_uses_the_default_push_time_cron(client: TestClient, task_store: TaskStore) -> None:
    body = _install(client, "daily-review").json()
    assert len(body["task_ids"]) == 1
    task = task_store.get(body["task_ids"][0])
    assert task.schedule.kind == "cron"
    assert task.schedule.cron == "0 20 * * *"
    assert task.enabled is True
    assert "六级 12 月" in task.title
    assert task.origin_surface == "campus"
    assert task.workspace, "模板任务应经既有创建链路拿到工作区"


def test_i3_daily_follows_the_configured_push_time(
    client: TestClient, task_store: TaskStore
) -> None:
    assert (
        client.patch(
            "/v1/campus/app-state",
            json={"settings": {"push_time": "07:30"}},
        ).status_code
        == 200
    )
    body = _install(client, "daily-review").json()
    assert task_store.get(body["task_ids"][0]).schedule.cron == "30 7 * * *"


# ---------- I3：幂等（验收②）----------


def test_i3_reinstall_does_not_duplicate_tasks(client: TestClient, task_store: TaskStore) -> None:
    first = _install(client, "daily-review").json()["task_ids"]
    second = _install(client, "daily-review").json()["task_ids"]
    assert second == first
    assert task_store.get(first[0]) is not None
    assert len(task_store.list()) == 1


def test_i3_reinstall_after_manual_deletion_recreates(
    client: TestClient, task_store: TaskStore
) -> None:
    first = _install(client, "daily-review").json()["task_ids"]
    task_store.delete(first[0])
    second = _install(client, "daily-review").json()["task_ids"]
    assert second != first
    assert task_store.get(second[0]) is not None


def test_i3_different_templates_install_independently(
    client: TestClient, task_store: TaskStore
) -> None:
    daily = _install(client, "daily-review").json()["task_ids"]
    sprint = _install(client, "sprint").json()["task_ids"]
    assert set(daily).isdisjoint(sprint)
    assert len(task_store.list()) == 2


# ---------- I3：周报复盘（需要模型）----------


def test_i3_weekly_installs_with_a_model(client: TestClient, task_store: TaskStore) -> None:
    body = _install(client, "weekly-report").json()
    task = task_store.get(body["task_ids"][0])
    assert task.schedule.kind == "cron"
    assert task.schedule.cron == "30 20 * * 0"
    assert task.instructions


def test_i3_weekly_without_a_model_is_refused(
    seeded_store: store.CampusStore, task_store: TaskStore
) -> None:
    app = FastAPI()
    app.include_router(
        routes.build_campus_router(FakeManager(task_store=task_store, model="", ready=False))
    )
    client = TestClient(app)
    response = _install(client, "weekly-report")
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"
    assert task_store.list() == []


# ---------- I3：冲刺倒计时 ----------


def test_i3_sprint_installs_a_daily_morning_cron(
    client: TestClient, task_store: TaskStore
) -> None:
    body = _install(client, "sprint").json()
    task = task_store.get(body["task_ids"][0])
    assert task.schedule.cron == "0 8 * * *"
    assert task.instructions


# ---------- I3：考试节点提醒（once + fire_at，ADR-12）----------


def _set_exam_date(client: TestClient, iso_date: str) -> None:
    response = client.patch(
        f"/v1/campus/profiles/{ACTIVE_ID}", json={"exam_date": iso_date}
    )
    assert response.status_code == 200


def test_i3_node_requires_an_exam_date(client: TestClient) -> None:
    response = _install(client, "deadline-node")
    assert response.status_code == 400
    assert _detail(response)["code"] == "EXAM_DATE_REQUIRED"


def test_i3_node_creates_three_once_tasks(
    client: TestClient, task_store: TaskStore
) -> None:
    _set_exam_date(client, "2027-01-15")
    body = _install(client, "deadline-node").json()
    assert len(body["task_ids"]) == 3
    tasks = [task_store.get(task_id) for task_id in body["task_ids"]]
    assert [task.schedule.fire_at for task in tasks] == [
        "2026-12-16T09:00:00",
        "2027-01-08T09:00:00",
        "2027-01-14T09:00:00",
    ]
    assert all(task.schedule.kind == "once" for task in tasks)
    assert all(task.next_run is not None for task in tasks)


def test_i3_node_skips_offsets_already_past(
    client: TestClient, task_store: TaskStore
) -> None:
    _set_exam_date(client, (date.today() + timedelta(days=10)).isoformat())
    body = _install(client, "deadline-node").json()
    assert len(body["task_ids"]) == 2, "D-30 已过期只应创建 D-7 与 D-1"
    tasks = [task_store.get(task_id) for task_id in body["task_ids"]]
    assert all(task.schedule.kind == "once" for task in tasks)


def test_i3_node_install_is_idempotent(client: TestClient, task_store: TaskStore) -> None:
    _set_exam_date(client, "2027-01-15")
    first = _install(client, "deadline-node").json()["task_ids"]
    second = _install(client, "deadline-node").json()["task_ids"]
    assert second == first
    assert len(task_store.list()) == 3


# ---------- 横切与异常 ----------


def test_i3_unknown_template_is_refused(client: TestClient) -> None:
    response = _install(client, "no-such-template")
    assert response.status_code == 404
    assert _detail(response)["code"] == "TEMPLATE_NOT_FOUND"


def test_i3_refuses_a_finished_profile(client: TestClient) -> None:
    response = _install(client, "daily-review", profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_i3_without_a_task_store_reports_automation_unavailable(
    seeded_store: store.CampusStore,
) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager()))
    client = TestClient(app)
    response = _install(client, "daily-review")
    assert response.status_code == 503
    assert _detail(response)["code"] == "AUTOMATION_UNAVAILABLE"


def test_i3_requires_the_profile_parameter(client: TestClient) -> None:
    response = client.post("/v1/campus/automation-templates/daily-review/install", json={})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"
