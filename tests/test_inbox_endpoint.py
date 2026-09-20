"""`GET /v1/inbox` — the cross-session list must honor what the attention count promises.

The sidebar's per-session badge and the footer Inbox chip count EVERY pending item of a
session, an attended session's inline ask_user prompt included. The Inbox page those chips
open therefore has to list the very same pending items: filtering any of them out strands
the user on an empty Inbox after following a "待你处理" notification (owner-hit 2026-09-19).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from stealth_study.inbox import VIS_INLINE, VIS_INBOX
from stealth_study.providers import ModelCapabilities, ProviderClient
from stealth_study.server import create_app
from stealth_study.server.manager import SessionManager
from stealth_study.sessions import SessionRecord


class NoTurnsProvider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        raise AssertionError("no model turns expected")

    def capabilities(self, model):
        return ModelCapabilities()


def _client(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data", provider=NoTurnsProvider())
    for sid, title in (("s-attended", "Attended chat"), ("s-unattended", "Unattended run")):
        manager.session_store.save(
            SessionRecord(
                session_id=sid,
                workspace="",
                model="test-model",
                mode="interactive",
                title=title,
                agent="cowork",
            )
        )
    return TestClient(create_app(manager)), manager


def test_cross_session_inbox_lists_attended_pending_question(tmp_path):
    client, manager = _client(tmp_path)
    manager.inbox.add_question(
        "s-attended", "Which environment should I restart?", visibility=VIS_INLINE
    )
    items = client.get("/v1/inbox", params={"state": "pending"}).json()["items"]
    assert [i["title"] for i in items] == ["Which environment should I restart?"]
    assert items[0]["visibility"] == VIS_INLINE
    assert items[0]["session_title"] == "Attended chat"


def test_unattended_question_stays_listed(tmp_path):
    client, manager = _client(tmp_path)
    manager.inbox.add_question(
        "s-unattended", "Deploy now or after the freeze?", visibility=VIS_INBOX
    )
    items = client.get("/v1/inbox", params={"state": "pending"}).json()["items"]
    assert [i["title"] for i in items] == ["Deploy now or after the freeze?"]


def test_attention_count_matches_cross_session_pending_list(tmp_path):
    client, manager = _client(tmp_path)
    manager.inbox.add_question(
        "s-attended", "Which environment should I restart?", visibility=VIS_INLINE
    )
    manager.inbox.add_approval("s-unattended", "Run `write_file`?", visibility=VIS_INBOX)
    listed = client.get("/v1/inbox", params={"state": "pending"}).json()["items"]
    attention = {s["session_id"]: s["attention"] for s in manager.list_sessions()}
    assert len(listed) == sum(attention.values())
    assert attention["s-attended"] == 1 and attention["s-unattended"] == 1


def test_resolving_from_inbox_drops_item_and_attention(tmp_path):
    client, manager = _client(tmp_path)
    item = manager.inbox.add_question(
        "s-attended", "Which environment should I restart?", visibility=VIS_INLINE
    )
    assert client.post(f"/v1/inbox/{item.id}/resolve", json={"resolution": "staging"}).json()[
        "ok"
    ]
    assert client.get("/v1/inbox", params={"state": "pending"}).json()["items"] == []
    assert all(s["attention"] == 0 for s in manager.list_sessions())


def test_concurrent_attended_questions_stay_per_session(tmp_path):
    client, manager = _client(tmp_path)
    manager.inbox.add_question("s-attended", "Which environment?", visibility=VIS_INLINE)
    manager.inbox.add_question("s-unattended", "Which database?", visibility=VIS_INLINE)
    listed = client.get("/v1/inbox", params={"state": "pending"}).json()["items"]
    assert [i["title"] for i in listed] == ["Which environment?", "Which database?"]
    mine = client.get(
        "/v1/inbox", params={"session_id": "s-unattended", "state": "pending"}
    ).json()["items"]
    assert [i["title"] for i in mine] == ["Which database?"]


def test_orphaned_inline_prompt_is_closed_by_the_cross_session_list(tmp_path):
    client, manager = _client(tmp_path)
    orphan = manager.inbox.add_question("s-gone", "Anyone there?", visibility=VIS_INLINE)
    items = client.get("/v1/inbox", params={"state": "pending"}).json()["items"]
    assert items == []
    assert manager.inbox.get(orphan.id).state == "resolved"
