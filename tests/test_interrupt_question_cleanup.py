"""Stop-interrupt must close the session's still-pending ask_user prompts: the turn is dead, so
its questions can never be answered and must not linger as answerable cards (nor durable-resume)."""

import asyncio

from stealth_study.providers import (
    AssistantTurn,
    ModelCapabilities,
    ProviderClient,
    ToolCall,
)
from stealth_study.server.manager import SessionManager


class ScriptedProvider(ProviderClient):
    def __init__(self, turns):
        self._turns = list(turns)

    def complete(self, *, model, messages, tools=None, **settings):
        return self._turns.pop(0)

    def capabilities(self, model):
        return ModelCapabilities()


def _tool(name, args, call_id):
    return AssistantTurn(tool_calls=[ToolCall(id=call_id, name=name, arguments=args)])


async def _wait_for_pending(mgr, sid):
    for _ in range(100):
        await asyncio.sleep(0.02)
        pend = mgr.inbox.pending(sid)
        if pend:
            return pend[0]
    raise AssertionError("prompt never became a pending Inbox item")


def test_interrupt_closes_pending_questions_but_leaves_other_kinds(tmp_path):
    mgr = SessionManager(
        workspace=tmp_path,
        provider=ScriptedProvider(
            [_tool("ask_user", {"question": "Which region?"}, "call_q")]
        ),
    )
    sid = "int-q"

    async def scenario():
        engine = mgr.get_engine(sid, agent="cowork", workspace=str(tmp_path))

        async def run():
            async for _ in engine.run("go"):
                pass

        task = asyncio.create_task(run())
        item = await _wait_for_pending(mgr, sid)
        assert item.kind == "question"
        note = mgr.inbox.add_notification(sid, "unrelated note")

        closed = mgr.close_pending_questions(sid)

        assert closed == 1
        question = mgr.inbox.get(item.id)
        assert question.state == "resolved"
        assert question.resolution == "interrupted by user"
        assert [i.id for i in mgr.inbox.pending(sid)] == [note.id]

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


def test_interrupt_cleanup_is_idempotent_and_count_accurate(tmp_path):
    mgr = SessionManager(workspace=tmp_path, provider=ScriptedProvider([]))
    sid = "int-q2"
    mgr.inbox.add_question(sid, "One?")
    mgr.inbox.add_question(sid, "Two?")
    assert mgr.close_pending_questions(sid) == 2
    assert mgr.inbox.pending(sid) == []
    assert mgr.close_pending_questions(sid) == 0
