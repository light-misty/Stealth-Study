"""应用内提醒（CERT-13 新口径）——`deadline_snapshot` 倒计时横幅事件（01 §3、ADR-12）。

读 `cert_deadline` 实时计算剩余天数并分档：D-30/D-7/D-1 三档给出
`deadline_snapshot` 的横幅数据源，当日到期与已错过节点进 `expired`。
按 ADR-12 不走 OS 通知：这里只产出数据，呈现交给前端 DeadlineBanner。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Mapping, Optional

from . import models

TIER_NORMAL = "normal"
TIER_D30 = "d30"
TIER_D7 = "d7"
TIER_D1 = "d1"
TIER_TODAY = "today"
TIER_OVERDUE = "overdue"

REMINDER_OFFSETS: tuple[int, ...] = (30, 7, 1)
REMINDER_FIRE_TIME = time(9, 0)

NODE_LABELS: Mapping[str, str] = {
    models.DeadlineNodeType.REGISTRATION_OPEN.value: "报名开始",
    models.DeadlineNodeType.REGISTRATION_CLOSE.value: "报名截止",
    models.DeadlineNodeType.PAYMENT_CLOSE.value: "缴费截止",
    models.DeadlineNodeType.ADMISSION_TICKET.value: "准考证打印",
    models.DeadlineNodeType.EXAM.value: "考试日",
    models.DeadlineNodeType.SCORE_QUERY.value: "成绩查询",
}


def today() -> date:
    """The machine's local day — deadlines are user-entered calendar dates."""
    return date.today()


def node_label(node_type: str) -> str:
    """The Chinese label of a deadline node, used in reminder task titles."""
    return NODE_LABELS.get(str(node_type), str(node_type))


def days_left(deadline_date: str, *, today: Optional[date] = None) -> Optional[int]:
    """Whole days from today until the deadline (negative once it has passed)."""
    try:
        day = date.fromisoformat(str(deadline_date))
    except (TypeError, ValueError):
        return None
    return (day - (today if today is not None else date.today())).days


def tier(days: int) -> str:
    """The D-30/D-7/D-1 band of a countdown, plus the due-today and overdue states."""
    if days < 0:
        return TIER_OVERDUE
    if days == 0:
        return TIER_TODAY
    if days == 1:
        return TIER_D1
    if days <= 7:
        return TIER_D7
    if days <= 30:
        return TIER_D30
    return TIER_NORMAL


def deadline_view(row: Any, *, today: Optional[date] = None) -> dict[str, Any]:
    """One `DeadlineView`: the documented fields plus the computed band."""
    return {
        "id": row["id"],
        "node_type": row["node_type"],
        "date": row["date"],
        "days_left": days_left(row["date"], today=today),
        "is_reference": bool(row["is_reference"]),
        "tier": tier(days_left(row["date"], today=today) or 0),
    }


def deadline_snapshot(
    store: Any, profile_id: str, *, today: Optional[date] = None
) -> dict[str, Any]:
    """H10's payload: upcoming nodes as the banner source, due/past nodes as alerts."""
    rows = store.list_rows("cert_deadline", profile_id=profile_id, order_by="date, id")
    banner: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    for row in rows:
        view = deadline_view(row, today=today)
        if view["days_left"] is not None and view["days_left"] <= 0:
            expired.append(view)
        else:
            banner.append(view)
    return {"banner": banner, "expired": expired}


def reminder_fire_dates(
    deadline_date: str, *, now: Optional[datetime] = None
) -> list[tuple[int, str]]:
    """The still-future `(offset, fire_at)` pairs of the D-30/D-7/D-1 once tasks.

    A fire moment that already passed would never trigger (`compute_next_run` refuses
    past once tasks), so it is not created: an exam three days away only gets its D-1.
    """
    try:
        day = date.fromisoformat(str(deadline_date))
    except (TypeError, ValueError):
        return []
    moment = now if now is not None else datetime.now()
    fires: list[tuple[int, str]] = []
    for offset in REMINDER_OFFSETS:
        fire_at = datetime.combine(day - timedelta(days=offset), REMINDER_FIRE_TIME)
        if fire_at <= moment:
            continue
        fires.append((offset, fire_at.isoformat()))
    return fires
