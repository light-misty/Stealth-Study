"""自动化模板 —— 4 个学习模板的一键安装（G-18，01 §2 契约、ADR-12）。

模板只做定义与创建：任务经既有 automation CRUD（`manager.create_automation` +
`TaskStore`）落库，不新增调度器；节点提醒以 `Schedule.kind="once"` + `fire_at` 落
D-30/D-7/D-1 三个一次性任务，其余走 cron。全部提醒都是应用内横幅/任务列表事件，
不依赖 OS 通知（ADR-12）。

幂等口径（07 §4 T13 验收②）：每个模板任务以 `origin_session_id` 携带
`campus-tpl:<tpl>:<profile>[:<offset>]` 标记，重复安装先扫描既有任务，命中即返回原
id 不重建——同一条目标记永远只对应一个任务，被手动删除的标记随之消失，可再创建。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

NODE_OFFSETS: tuple[int, ...] = (30, 7, 1)
NODE_FIRE_TIME = "09:00:00"
MARKER_PREFIX = "campus-tpl"


@dataclass(frozen=True)
class AutomationTemplate:
    """One installable template: its identity, schedule shape and prerequisites."""

    id: str
    title: str
    cron_desc: str
    kind: str
    cron: Optional[str] = None
    requires_model: bool = False
    requires_exam_date: bool = False


TEMPLATES: tuple[AutomationTemplate, ...] = (
    AutomationTemplate(
        id="daily-review",
        title="每日复习推送",
        cron_desc="每天按备考偏好的推送时间（默认 20:00）",
        kind="cron",
        cron="{push_cron}",
    ),
    AutomationTemplate(
        id="weekly-report",
        title="周报复盘",
        cron_desc="每周日 20:30",
        kind="cron",
        cron="30 20 * * 0",
        requires_model=True,
    ),
    AutomationTemplate(
        id="sprint",
        title="冲刺倒计时",
        cron_desc="每天 08:00",
        kind="cron",
        cron="0 8 * * *",
    ),
    AutomationTemplate(
        id="deadline-node",
        title="考试节点提醒",
        cron_desc="考试日前 30/7/1 天各提醒一次",
        kind="once",
        requires_exam_date=True,
    ),
)


def get_template(tpl_id: str) -> Optional[AutomationTemplate]:
    """The template with this id, or `None` (the router refuses unknown ids with 404)."""
    for template in TEMPLATES:
        if template.id == tpl_id:
            return template
    return None


def catalogue() -> list[dict[str, str]]:
    """The I2 shape: one `{id, title, cron_desc, kind}` per template, declared order."""
    return [
        {"id": t.id, "title": t.title, "cron_desc": t.cron_desc, "kind": t.kind}
        for t in TEMPLATES
    ]


@dataclass(frozen=True)
class _TaskDraft:
    """One concrete task a template expands to, before it reaches the automation CRUD."""

    marker: str
    title: str
    instructions: str
    cron: Optional[str] = None
    fire_at: Optional[str] = None


def install_template(
    mgr: Any,
    profile: Any,
    tpl_id: str,
    *,
    push_time: str,
    now: Optional[datetime] = None,
) -> list[str]:
    """Install a template for one profile through the existing automation CRUD.

    Returns the task ids (already-installed tasks keep their id and are never rebuilt).
    `push_time` is the profile's resolved campus preference (daily-review's cron follows
    it); `now` bounds which node reminders are still worth creating — an offset whose
    fire moment has passed is skipped instead of being stored to never fire.
    """
    template = get_template(tpl_id)
    if template is None:
        raise KeyError(f"unknown automation template: {tpl_id}")
    moment = now if now is not None else datetime.now()
    markers = _marker_index(mgr)
    task_ids: list[str] = []
    for draft in _template_tasks(template, profile, push_time=push_time, now=moment):
        known = markers.get(draft.marker)
        if known is not None:
            task_ids.append(known)
            continue
        task_ids.append(_create_task(mgr, draft))
    return task_ids


def _template_tasks(
    template: AutomationTemplate,
    profile: Any,
    *,
    push_time: str,
    now: datetime,
) -> list[_TaskDraft]:
    """Expand one template into its concrete task drafts (a cron template yields one,
    the node template up to `len(NODE_OFFSETS)`)."""
    if template.kind == "once":
        exam = date.fromisoformat(str(profile.exam_date).strip())
        drafts: list[_TaskDraft] = []
        for offset in NODE_OFFSETS:
            fire_at = (exam - timedelta(days=offset)).isoformat() + f"T{NODE_FIRE_TIME}"
            if datetime.fromisoformat(fire_at) <= now:
                continue
            drafts.append(
                _TaskDraft(
                    marker=f"{MARKER_PREFIX}:{template.id}:{profile.id}:{offset}",
                    title=f"{template.title}（D-{offset}）· {profile.title}",
                    instructions=(
                        f"你是备考档案「{profile.title}」的考试节点提醒助手。考试日期为 {exam.isoformat()}，"
                        f"今天是考前第 {offset} 天：请提醒用户该节点已临近，说明接下来应完成的报名/缴费/"
                        f"备考动作。本提醒为应用内任务列表事件，不发送系统通知。"
                    ),
                    fire_at=fire_at,
                )
            )
        return drafts
    cron = template.cron or ""
    if "{push_cron}" in cron:
        hour, minute = str(push_time).split(":")
        cron = f"{int(minute)} {int(hour)} * * *"
    return [
        _TaskDraft(
            marker=f"{MARKER_PREFIX}:{template.id}:{profile.id}",
            title=f"{template.title} · {profile.title}",
            instructions=_instructions(template, profile),
            cron=cron,
        )
    ]


def _instructions(template: AutomationTemplate, profile: Any) -> str:
    """The task's standing instruction: what this run does and where its data lives."""
    exam_date = str(getattr(profile, "exam_date", "") or "").strip()
    exam_line = f"考试日期为 {exam_date}。" if exam_date else "尚未设置考试日期。"
    if template.id == "daily-review":
        return (
            f"你是备考档案「{profile.title}」的学习助手，现在是每日复习推送时间。请汇总该档案今日"
            f"到期的间隔复习项（review_queue 中 status=pending 且 due_at 已到的 mistake/vocab/"
            f"knowledge_point，可经本机 campus 服务 GET /v1/campus/review/due 获取，或读取 state "
            f"目录下 campus.db），以清单形式输出每项内容与建议动作，提醒学生在应用内复习卡完成今日"
            f"复习。不要编造不存在的内容；没有到期项时输出「今日复习已完成」。"
        )
    if template.id == "weekly-report":
        return (
            f"你是备考档案「{profile.title}」的学习教练。请生成本周复盘周报：读取 state 目录下 "
            f"campus.db 的 plan_task（必要时含 attempt、mistake_book），按 05 §4.7 的固定五段"
            f"（总览 / 各轨明细 / 错题与薄弱点 / 落后预警 / 下周建议）输出 markdown。语气对事不对"
            f"人，不做心理评价；没有任务数据时如实说明「本周暂无任务记录」。"
        )
    return (
        f"你是备考档案「{profile.title}」的冲刺陪练。{exam_line}请输出今日冲刺要点：距考试剩余"
        f"天数（未设日期则提示先设置）、计划中最近到期且未完成的任务、以及一句简短鼓励。数据不"
        f"存在时如实说明，不要编造。"
    )


def _create_task(mgr: Any, draft: _TaskDraft) -> str:
    """Create one task via the existing CRUD, tag the template marker and return its id."""
    payload: dict[str, Any] = {
        "title": draft.title,
        "instructions": draft.instructions,
    }
    if draft.cron:
        payload["cron"] = draft.cron
    else:
        payload["fire_at"] = draft.fire_at
    result = mgr.create_automation(payload)
    task = mgr.task_store.get(result["task"]["id"])
    task.origin_surface = "campus"
    task.origin_session_id = draft.marker
    mgr.task_store.save(task)
    return task.id


def _marker_index(mgr: Any) -> dict[str, str]:
    """Existing template markers → task ids, scanned once per install."""
    index: dict[str, str] = {}
    for task in mgr.task_store.list():
        marker = task.origin_session_id
        if isinstance(marker, str) and marker.startswith(f"{MARKER_PREFIX}:"):
            index[marker] = task.id
    return index
