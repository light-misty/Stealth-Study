"""T13 复习间隔调度器（简化 SM-2，PRD §6.3 间隔表、01 §2 `review_scheduler.py` 契约）。

三条纯函数契约：

* `next_interval(streak)` —— 连对 `streak` 次后的下一次间隔：0-5 连对的间隔序列为
  1/1/2/4/7/15（07 §4 T13 验收①），连对超过阶梯封顶 15 天，答错重置回 1 天；
* `apply_result(item, correct)` —— 按本次结果推进 `streak_right`/`interval_days`/`due_at`
  并盖章 `last_reviewed_at`，返回新实例不改入参；
* `due_items(store, profile_id)` —— 到期复习拉取：只取本档案 `pending` 且 `due_at <= as_of`
  的行，按到期时间升序（同刻按 rowid 稳定断尾）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ss.campus import models
from ss.campus.review_scheduler import apply_result, due_items, next_interval
from ss.campus.store import CampusStore

PROFILE_ID = "profile-rq"
OTHER_ID = "profile-other"
NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
NOW_TEXT = "2026-09-15T12:00:00Z"


def _item(**overrides):
    values = {
        "id": "rq-1",
        "profile_id": PROFILE_ID,
        "item_type": models.ReviewItemType.VOCAB.value,
        "item_id": "vocab-1",
        "due_at": "2026-09-15T00:00:00Z",
        "interval_days": 1,
        "streak_right": 0,
        "ease": 2.5,
        "status": models.ReviewStatus.PENDING.value,
        "last_reviewed_at": None,
        "created_at": "2026-09-14T00:00:00Z",
    }
    values.update(overrides)
    return models.ReviewItem(**values)


# ---------- next_interval：0-5 连对的间隔序列（验收①） ----------


@pytest.mark.parametrize(
    ("streak", "expected"),
    [(0, 1), (1, 1), (2, 2), (3, 4), (4, 7), (5, 15)],
)
def test_interval_ladder_matches_the_prd_table(streak: int, expected: int) -> None:
    assert next_interval(streak) == expected


@pytest.mark.parametrize("streak", [6, 7, 20, 100])
def test_interval_caps_at_the_ladder_top(streak: int) -> None:
    assert next_interval(streak) == 15


def test_interval_treats_a_wrong_answer_reset_as_one_day() -> None:
    assert next_interval(0) == 1


# ---------- apply_result：结果推进 ----------


def test_first_correct_review_grants_one_day() -> None:
    updated = apply_result(_item(), True, now=NOW)
    assert updated.streak_right == 1
    assert updated.interval_days == 1
    assert updated.due_at == "2026-09-16T12:00:00Z"
    assert updated.last_reviewed_at == NOW_TEXT
    assert updated.status == models.ReviewStatus.PENDING.value
    assert updated.ease == 2.5


def test_correct_chain_walks_the_ladder() -> None:
    item = _item(streak_right=3, interval_days=4)
    updated = apply_result(item, True, now=NOW)
    assert updated.streak_right == 4
    assert updated.interval_days == 7


def test_correct_at_the_ladder_top_stays_fifteen_days() -> None:
    updated = apply_result(_item(streak_right=9, interval_days=15), True, now=NOW)
    assert updated.streak_right == 10
    assert updated.interval_days == 15


def test_wrong_answer_resets_the_streak_to_one_day() -> None:
    updated = apply_result(_item(streak_right=4, interval_days=7), False, now=NOW)
    assert updated.streak_right == 0
    assert updated.interval_days == 1
    assert updated.due_at == "2026-09-16T12:00:00Z"
    assert updated.last_reviewed_at == NOW_TEXT


def test_apply_result_returns_a_new_item_and_keeps_the_input() -> None:
    item = _item(streak_right=2, interval_days=2)
    updated = apply_result(item, True, now=NOW)
    assert updated is not item
    assert item.streak_right == 2 and item.interval_days == 2
    assert item.last_reviewed_at is None


def test_apply_result_defaults_to_the_current_clock() -> None:
    updated = apply_result(_item(), True)
    assert updated.last_reviewed_at is not None
    due = datetime.fromisoformat(updated.due_at.replace("Z", "+00:00"))
    reviewed = datetime.fromisoformat(str(updated.last_reviewed_at).replace("Z", "+00:00"))
    assert timedelta(0) < due - reviewed <= timedelta(days=1, seconds=5)


# ---------- due_items：到期拉取 ----------


@pytest.fixture()
def rq_store(tmp_path):
    instance = CampusStore(tmp_path / "campus.db")
    instance.insert(
        "exam_profile",
        {"id": PROFILE_ID, "track_type": models.TrackType.CET.value, "title": "六级"},
    )
    instance.insert(
        "exam_profile",
        {"id": OTHER_ID, "track_type": models.TrackType.CET.value, "title": "别人"},
    )
    yield instance
    instance.close()


def _seed(store: CampusStore, row_id: str, **overrides) -> None:
    values = {
        "id": row_id,
        "profile_id": PROFILE_ID,
        "item_type": models.ReviewItemType.VOCAB.value,
        "item_id": f"vocab-{row_id}",
        "due_at": "2026-09-01T00:00:00Z",
        "status": models.ReviewStatus.PENDING.value,
    }
    values.update(overrides)
    store.insert("review_queue", values)


def test_due_items_returns_only_due_pending_rows(rq_store: CampusStore) -> None:
    _seed(rq_store, "rq-due", due_at="2026-09-01T00:00:00Z")
    _seed(rq_store, "rq-future", due_at="2026-09-30T00:00:00Z")
    _seed(rq_store, "rq-done", status=models.ReviewStatus.DONE.value)
    _seed(rq_store, "rq-dropped", status=models.ReviewStatus.DROPPED.value)
    items = due_items(rq_store, PROFILE_ID, as_of=NOW_TEXT)
    assert [item.id for item in items] == ["rq-due"]


def test_due_items_orders_by_due_at_then_insertion(rq_store: CampusStore) -> None:
    _seed(rq_store, "rq-late", due_at="2026-09-05T00:00:00Z")
    _seed(rq_store, "rq-early", due_at="2026-09-02T00:00:00Z")
    _seed(rq_store, "rq-twin-a", due_at="2026-09-01T00:00:00Z")
    _seed(rq_store, "rq-twin-b", due_at="2026-09-01T00:00:00Z")
    items = due_items(rq_store, PROFILE_ID, as_of=NOW_TEXT)
    assert [item.id for item in items] == ["rq-twin-a", "rq-twin-b", "rq-early", "rq-late"]


def test_due_items_isolates_profiles(rq_store: CampusStore) -> None:
    _seed(rq_store, "rq-mine")
    _seed(rq_store, "rq-theirs", profile_id=OTHER_ID)
    assert [item.id for item in due_items(rq_store, PROFILE_ID, as_of=NOW_TEXT)] == ["rq-mine"]
    assert [item.id for item in due_items(rq_store, OTHER_ID, as_of=NOW_TEXT)] == ["rq-theirs"]


def test_due_items_defaults_to_now(rq_store: CampusStore) -> None:
    _seed(rq_store, "rq-old", due_at="2026-01-01T00:00:00Z")
    _seed(rq_store, "rq-ahead", due_at="2999-01-01T00:00:00Z")
    assert [item.id for item in due_items(rq_store, PROFILE_ID)] == ["rq-old"]


def test_due_items_returns_review_items(rq_store: CampusStore) -> None:
    _seed(rq_store, "rq-typed", item_type=models.ReviewItemType.MISTAKE.value)
    item = due_items(rq_store, PROFILE_ID, as_of=NOW_TEXT)[0]
    assert isinstance(item, models.ReviewItem)
    assert item.item_type == models.ReviewItemType.MISTAKE.value
