"""`reminders.py` — CERT-13 应用内提醒的倒计时口径（01 §3、ADR-12、07 §4 T12 验收③）。

reminders.py 是纯计算模块：读 `cert_deadline`，算 `days_left`，把节点分进
D-30/D-7/D-1 三档（外加 today/overdue），产出 H10 横幅数据源 `{banner, expired}`。
不走 OS 通知——这里没有也不允许出现任何通知通道调用。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from ss.campus import models, reminders, store

TODAY = date(2026, 9, 15)


@pytest.fixture()
def campus(tmp_path) -> store.CampusStore:
    instance = store.CampusStore(tmp_path / "campus.db")
    try:
        yield instance
    finally:
        instance.close()


def seed_deadline(campus: store.CampusStore, node_type: str, day: str, **overrides) -> str:
    values = {
        "profile_id": "profile-1",
        "node_type": node_type,
        "date": day,
    }
    values.update(overrides)
    return campus.insert("cert_deadline", values)


# ---------------------------------------------------------------------------
# days_left 与三档判定
# ---------------------------------------------------------------------------


def test_days_left_counts_days_to_the_deadline() -> None:
    assert reminders.days_left("2026-09-15", today=TODAY) == 0
    assert reminders.days_left("2026-10-15", today=TODAY) == 30
    assert reminders.days_left("2026-09-12", today=TODAY) == -3


@pytest.mark.parametrize(
    "days, tier",
    [
        (45, "normal"),
        (31, "normal"),
        (30, "d30"),
        (8, "d30"),
        (7, "d7"),
        (2, "d7"),
        (1, "d1"),
        (0, "today"),
        (-1, "overdue"),
        (-20, "overdue"),
    ],
)
def test_tier_maps_the_documented_d30_d7_d1_bands(days: int, tier: str) -> None:
    assert reminders.tier(days) == tier


# ---------------------------------------------------------------------------
# deadline_snapshot：H10 横幅数据源
# ---------------------------------------------------------------------------


def test_snapshot_splits_upcoming_banner_from_expired(campus: store.CampusStore) -> None:
    seed_deadline(campus, "exam", "2026-10-15")
    seed_deadline(campus, "registration_close", "2026-09-12")
    seed_deadline(campus, "score_query", "2026-09-15")

    snapshot = reminders.deadline_snapshot(campus, "profile-1", today=TODAY)

    assert [view["node_type"] for view in snapshot["banner"]] == ["exam"]
    assert [view["node_type"] for view in snapshot["expired"]] == [
        "registration_close",
        "score_query",
    ]
    assert snapshot["expired"][0]["days_left"] == -3
    assert snapshot["expired"][1]["days_left"] == 0


def test_snapshot_banner_carries_every_documented_tier(campus: store.CampusStore) -> None:
    seed_deadline(campus, "exam", "2026-10-16")
    seed_deadline(campus, "registration_open", "2026-10-15")
    seed_deadline(campus, "registration_close", "2026-09-22")
    seed_deadline(campus, "payment_close", "2026-09-16")

    snapshot = reminders.deadline_snapshot(campus, "profile-1", today=TODAY)

    tiers = [(view["node_type"], view["tier"]) for view in snapshot["banner"]]
    assert tiers == [
        ("payment_close", "d1"),
        ("registration_close", "d7"),
        ("registration_open", "d30"),
        ("exam", "normal"),
    ]


def test_snapshot_view_matches_the_documented_deadlineview_shape(
    campus: store.CampusStore,
) -> None:
    deadline_id = seed_deadline(
        campus, "exam", "2026-10-15", is_reference=1, automation_ids='["task-x"]'
    )

    (view,) = reminders.deadline_snapshot(campus, "profile-1", today=TODAY)["banner"]

    assert set(view) == {"id", "node_type", "date", "days_left", "is_reference", "tier"}
    assert view["id"] == deadline_id
    assert view["date"] == "2026-10-15"
    assert view["days_left"] == 30
    assert view["tier"] == "d30"
    assert view["is_reference"] is True


def test_snapshot_never_leaks_another_profiles_nodes(campus: store.CampusStore) -> None:
    seed_deadline(campus, "exam", "2026-10-15")
    seed_deadline(campus, "exam", "2026-10-15", profile_id="profile-2")

    snapshot = reminders.deadline_snapshot(campus, "profile-1", today=TODAY)

    assert [view["id"] for view in snapshot["banner"]] == [campus.query_one(
        'SELECT "id" FROM "cert_deadline" WHERE "profile_id" = ?', ("profile-1",)
    )["id"]]


def test_snapshot_of_an_empty_profile_is_two_empty_lists(campus: store.CampusStore) -> None:
    assert reminders.deadline_snapshot(campus, "profile-none", today=TODAY) == {
        "banner": [],
        "expired": [],
    }


# ---------------------------------------------------------------------------
# reminder_fire_dates：H9 的 D-30/D-7/D-1 once 触发点
# ---------------------------------------------------------------------------


def test_reminder_fire_dates_cover_the_three_documented_offsets() -> None:
    fires = reminders.reminder_fire_dates("2026-12-15", now=datetime(2026, 9, 15, 12, 0))

    assert [offset for offset, _fire_at in fires] == [30, 7, 1]
    assert fires[0][1].startswith("2026-11-15T09:00:00")
    assert fires[1][1].startswith("2026-12-08T09:00:00")
    assert fires[2][1].startswith("2026-12-14T09:00:00")


def test_reminder_fire_dates_skip_moments_already_past() -> None:
    fires = reminders.reminder_fire_dates("2026-09-17", now=datetime(2026, 9, 15, 12, 0))

    assert [offset for offset, _fire_at in fires] == [1]
    assert fires[0][1].startswith("2026-09-16T09:00:00")


def test_reminder_fire_dates_are_empty_when_the_node_has_passed() -> None:
    assert reminders.reminder_fire_dates("2026-09-15", now=datetime(2026, 9, 15, 12, 0)) == []


# ---------------------------------------------------------------------------
# 节点中文名（自动化任务标题用）
# ---------------------------------------------------------------------------


def test_every_deadline_node_type_has_a_label() -> None:
    for node_type in models.DeadlineNodeType:
        assert reminders.node_label(node_type.value)
