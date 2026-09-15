"""间隔复习调度器 —— 简化 SM-2（G-17/CET-05，01 §2 `review_scheduler.py` 契约）。

间隔规则固定为 PRD §6.3 的阶梯表（V0.1 不做算法调优，`ease` 恒为 2.5）：答对间隔按
1/2/4/7/15 天递增、连对超过阶梯封顶 15 天、答错重置回 1 天（`streak_right` 归零）。
本模块只做纯计算与到期拉取；队列入队、payload 内联与错误语义由 `service.py` 的
D4-D6 编排（02 §4.15：同一条目只允许一条 pending，重复加入走 UPSERT）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from . import models
from .store import CampusStore

INTERVAL_LADDER: tuple[int, ...] = (1, 2, 4, 7, 15)

_CAMPUSTAMP = "%Y-%m-%dT%H:%M:%SZ"


def _campus_now() -> datetime:
    return datetime.now(timezone.utc)


def _campusformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_CAMPUSTAMP)


def next_interval(streak: int) -> int:
    """The interval (days) granted for `streak` consecutive correct reviews.

    `streak` is the count AFTER the review being recorded: a wrong answer (0) and a
    first-correct (1) both grant 1 day, then the PRD §6.3 ladder walks 2/4/7 and caps
    at 15 days from the fifth consecutive correct on.
    """
    if streak < 1:
        return 1
    return INTERVAL_LADDER[min(streak, len(INTERVAL_LADDER)) - 1]


def apply_result(
    item: models.ReviewItem, correct: bool, *, now: Optional[datetime] = None
) -> models.ReviewItem:
    """Advance one review item by its result, returning a new `ReviewItem`.

    A correct answer grows the streak and walks the ladder; a wrong one resets the
    streak to 0 and reschedules for tomorrow (1 day). Either way `last_reviewed_at`
    is stamped and `due_at` moves to the review moment plus the new interval. The
    input item is never mutated — the caller decides what to persist.
    """
    moment = now if now is not None else _campus_now()
    streak = item.streak_right + 1 if correct else 0
    interval = next_interval(streak)
    return models.ReviewItem(
        id=item.id,
        profile_id=item.profile_id,
        item_type=item.item_type,
        item_id=item.item_id,
        due_at=_campusformat(moment + timedelta(days=interval)),
        interval_days=interval,
        streak_right=streak,
        ease=item.ease,
        status=models.ReviewStatus.PENDING.value,
        last_reviewed_at=_campusformat(moment),
        created_at=item.created_at,
    )


def due_items(
    store: CampusStore, profile_id: str, *, as_of: Optional[str] = None
) -> list[models.ReviewItem]:
    """The profile's pending items whose `due_at` has passed, oldest due first.

    `as_of` (campus timestamp, 02 §1.3) defaults to the current clock; rows of another
    profile, a `done`/`dropped` status or a future `due_at` never surface. Same-instant
    ties keep insertion order via `rowid`, matching the store's stable-pagination rule.
    """
    moment = as_of if as_of is not None else _campusformat(_campus_now())
    rows = store.list_rows(
        "review_queue",
        profile_id=profile_id,
        where='"status" = ? AND "due_at" <= ?',
        params=[models.ReviewStatus.PENDING.value, moment],
        order_by="due_at, rowid",
    )
    return [models.ReviewItem.from_row(row) for row in rows]
