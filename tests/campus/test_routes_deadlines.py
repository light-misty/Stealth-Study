"""H7-H10 考试节点与 CERT-13 应用内提醒端点（03 §4.8、07 §4 T12 验收③、ADR-12）。

H9 经既有 `stealth_study/automation` 的 TaskStore 创建 D-30/D-7/D-1 三条 `once` 任务（已创建的
不重复建、已错过的触发点不再建，过去的一次性任务永远不会触发）；H10 是横幅数据源，
`deadline_snapshot` 的 D-30/D-7/D-1 三档状态在这里端到端钉住。全程无 OS 通知。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.automation.store import TaskStore
from stealth_study.campus import models, reminders, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

TODAY = date.today()


def days_from_today(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


class FakeManager:
    """The slice of `SessionManager` campus reads, plus the automation TaskStore."""

    def __init__(self, task_store: TaskStore | None) -> None:
        if task_store is not None:
            self.task_store = task_store


@pytest.fixture()
def task_store(tmp_path) -> TaskStore:
    instance = TaskStore(tmp_path / "automation.db")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def manager(task_store: TaskStore) -> FakeManager:
    return FakeManager(task_store)


@pytest.fixture()
def seeded_store():
    instance = store.CampusStore(secrets.state_dir() / "campus.db")
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "教资高中语文"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.CERT.value,
                "title": title,
                "status": status,
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


def _prefix() -> str:
    return routes.CAMPUS_PREFIX


def _detail(response) -> dict:
    return response.json()["detail"]


def _create_deadline(client: TestClient, **overrides):
    payload = {
        "profile_id": ACTIVE_ID,
        "node_type": models.DeadlineNodeType.EXAM.value,
        "date": days_from_today(40),
    }
    payload.update(overrides)
    return client.post(f"{_prefix()}/deadlines", json=payload)


# ---------------------------------------------------------------------------
# H7 — 节点 CRUD（创建）
# ---------------------------------------------------------------------------


def test_h7_creates_an_exam_node(client: TestClient) -> None:
    response = _create_deadline(client)
    assert response.status_code == 200
    body = response.json()
    assert body["node_type"] == models.DeadlineNodeType.EXAM.value
    assert body["date"] == days_from_today(40)
    assert body["is_reference"] == 0
    assert body["automation_ids"] == []
    assert body["note"] == ""


def test_h7_marks_a_reference_node(client: TestClient) -> None:
    body = _create_deadline(
        client,
        node_type=models.DeadlineNodeType.REGISTRATION_OPEN.value,
        is_reference=True,
    ).json()
    assert body["is_reference"] == 1


def test_h7_rejects_a_duplicate_node_type(client: TestClient) -> None:
    assert _create_deadline(client).status_code == 200
    duplicate = _create_deadline(client)
    assert duplicate.status_code == 409
    assert _detail(duplicate)["code"] == "DUPLICATE_NODE"
    other = _create_deadline(
        client, node_type=models.DeadlineNodeType.REGISTRATION_CLOSE.value
    )
    assert other.status_code == 200


def test_h7_rejects_a_malformed_date(client: TestClient) -> None:
    response = _create_deadline(client, date="2026/09/20")
    assert response.status_code == 422


def test_h7_rejects_an_unknown_node_type(client: TestClient) -> None:
    response = _create_deadline(client, node_type="open_house")
    assert response.status_code == 422


def test_h7_rejects_unknown_body_fields(client: TestClient) -> None:
    response = _create_deadline(client, color="red")
    assert response.status_code == 422


def test_h7_refuses_a_finished_profile(client: TestClient) -> None:
    response = _create_deadline(client, profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


# ---------------------------------------------------------------------------
# H8 — 时间轴列表
# ---------------------------------------------------------------------------


def test_h8_lists_nodes_oldest_first_with_days_left(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(10),
        },
    )
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.REGISTRATION_CLOSE.value,
            "date": days_from_today(-3),
        },
    )
    body = client.get(f"{_prefix()}/deadlines", params={"profile_id": ACTIVE_ID}).json()

    assert [(item["node_type"], item["days_left"]) for item in body["items"]] == [
        (models.DeadlineNodeType.REGISTRATION_CLOSE.value, -3),
        (models.DeadlineNodeType.EXAM.value, 10),
    ]


def test_h8_decodes_the_stored_automation_ids(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(10),
            "automation_ids": '["task-a", "task-b"]',
        },
    )
    (item,) = client.get(f"{_prefix()}/deadlines", params={"profile_id": ACTIVE_ID}).json()["items"]
    assert item["automation_ids"] == ["task-a", "task-b"]


def test_h8_scopes_to_the_profile(client: TestClient) -> None:
    _create_deadline(client)
    body = client.get(f"{_prefix()}/deadlines", params={"profile_id": OTHER_ID}).json()
    assert body == {"items": []}


def test_h8_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{_prefix()}/deadlines")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# H9 — 一键创建 D-30/D-7/D-1 once 任务
# ---------------------------------------------------------------------------


def test_h9_creates_three_once_tasks_and_stores_the_ids(
    client: TestClient, task_store: TaskStore
) -> None:
    deadline = _create_deadline(client).json()
    response = client.post(
        f"{_prefix()}/deadlines/{deadline['id']}/reminders",
        params={"profile_id": ACTIVE_ID},
    )
    assert response.status_code == 200
    ids = response.json()["automation_ids"]
    assert len(ids) == 3
    tasks = [task_store.get(task_id) for task_id in ids]
    assert all(task.schedule.kind == "once" for task in tasks)
    fire_days = sorted(task.schedule.fire_at[:10] for task in tasks)
    assert fire_days == [days_from_today(10), days_from_today(33), days_from_today(39)]
    assert all(task.schedule.fire_at[11:] == "09:00:00" for task in tasks)
    stored = client.get(f"{_prefix()}/deadlines", params={"profile_id": ACTIVE_ID}).json()
    assert stored["items"][0]["automation_ids"] == ids


def test_h9_titles_name_the_node_and_the_offset(
    client: TestClient, task_store: TaskStore
) -> None:
    deadline = _create_deadline(
        client, node_type=models.DeadlineNodeType.REGISTRATION_CLOSE.value
    ).json()
    ids = client.post(
        f"{_prefix()}/deadlines/{deadline['id']}/reminders",
        params={"profile_id": ACTIVE_ID},
    ).json()["automation_ids"]
    titles = sorted(task_store.get(task_id).title for task_id in ids)
    assert titles == ["报名截止提醒（D-1）", "报名截止提醒（D-30）", "报名截止提醒（D-7）"]


def test_h9_is_idempotent_when_reminders_already_exist(
    client: TestClient, task_store: TaskStore
) -> None:
    deadline = _create_deadline(client).json()
    first = client.post(
        f"{_prefix()}/deadlines/{deadline['id']}/reminders",
        params={"profile_id": ACTIVE_ID},
    ).json()["automation_ids"]
    second = client.post(
        f"{_prefix()}/deadlines/{deadline['id']}/reminders",
        params={"profile_id": ACTIVE_ID},
    ).json()["automation_ids"]
    assert second == first
    assert len(task_store.list()) == 3


def test_h9_skips_fire_moments_already_past(
    client: TestClient, task_store: TaskStore
) -> None:
    deadline = _create_deadline(client, date=days_from_today(2)).json()
    ids = client.post(
        f"{_prefix()}/deadlines/{deadline['id']}/reminders",
        params={"profile_id": ACTIVE_ID},
    ).json()["automation_ids"]
    assert len(ids) == 1
    task = task_store.get(ids[0])
    assert task.schedule.fire_at[:10] == days_from_today(1)


def test_h9_reports_when_automation_is_unavailable(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(task_store=None)))
    client = TestClient(app)
    created = client.post(
        f"{_prefix()}/deadlines",
        json={
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(40),
        },
    ).json()
    response = client.post(
        f"{_prefix()}/deadlines/{created['id']}/reminders",
        params={"profile_id": ACTIVE_ID},
    )
    assert response.status_code == 503
    assert _detail(response)["code"] == "AUTOMATION_UNAVAILABLE"


def test_h9_refuses_a_missing_deadline(client: TestClient) -> None:
    response = client.post(
        f"{_prefix()}/deadlines/no-such-node/reminders", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "ITEM_NOT_FOUND"


def test_h9_refuses_a_foreign_deadline(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    foreign_id = seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": OTHER_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(40),
        },
    )
    response = client.post(
        f"{_prefix()}/deadlines/{foreign_id}/reminders", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_h9_refuses_a_finished_profile(client: TestClient, seeded_store: store.CampusStore) -> None:
    node_id = seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": FINISHED_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(40),
        },
    )
    response = client.post(
        f"{_prefix()}/deadlines/{node_id}/reminders", params={"profile_id": FINISHED_ID}
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


# ---------------------------------------------------------------------------
# H10 — 横幅数据源（deadline_snapshot 三档）
# ---------------------------------------------------------------------------


def test_h10_returns_banner_and_expired_with_the_documented_tiers(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(30),
        },
    )
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.REGISTRATION_CLOSE.value,
            "date": days_from_today(7),
        },
    )
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.PAYMENT_CLOSE.value,
            "date": days_from_today(0),
        },
    )
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": ACTIVE_ID,
            "node_type": models.DeadlineNodeType.SCORE_QUERY.value,
            "date": days_from_today(-4),
        },
    )
    body = client.get(f"{_prefix()}/reminders", params={"profile_id": ACTIVE_ID}).json()

    assert [(view["node_type"], view["tier"], view["days_left"]) for view in body["banner"]] == [
        (models.DeadlineNodeType.REGISTRATION_CLOSE.value, "d7", 7),
        (models.DeadlineNodeType.EXAM.value, "d30", 30),
    ]
    assert [(view["node_type"], view["tier"]) for view in body["expired"]] == [
        (models.DeadlineNodeType.SCORE_QUERY.value, "overdue"),
        (models.DeadlineNodeType.PAYMENT_CLOSE.value, "today"),
    ]
    assert body["banner"][0]["is_reference"] is False


def test_h10_scopes_to_the_profile(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "cert_deadline",
        {
            "profile_id": OTHER_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": days_from_today(3),
        },
    )
    body = client.get(f"{_prefix()}/reminders", params={"profile_id": ACTIVE_ID}).json()
    assert body == {"banner": [], "expired": []}


def test_h10_exposes_every_documented_band_over_the_calendar(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    nodes = (
        (models.DeadlineNodeType.ADMISSION_TICKET.value, 45, "normal"),
        (models.DeadlineNodeType.REGISTRATION_CLOSE.value, 30, "d30"),
        (models.DeadlineNodeType.PAYMENT_CLOSE.value, 2, "d7"),
        (models.DeadlineNodeType.REGISTRATION_OPEN.value, 1, "d1"),
    )
    for node_type, offset, expected in nodes:
        seeded_store.insert(
            "cert_deadline",
            {
                "profile_id": ACTIVE_ID,
                "node_type": node_type,
                "date": days_from_today(offset),
            },
        )
        body = client.get(f"{_prefix()}/reminders", params={"profile_id": ACTIVE_ID}).json()
        view = next(v for v in body["banner"] if v["node_type"] == node_type)
        assert view["tier"] == expected, offset
        assert view["days_left"] == offset
