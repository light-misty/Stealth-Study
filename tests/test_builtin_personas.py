"""Phase 1 gate — built-in personas resolve to the same toolsets as the legacy agents.

The equivalence net: routing Code/Cowork through the persona registry must yield the exact
same tools the agent builders produce, and Ops (a markdown persona) must compose the knowledge
toolset. Ties back to the Phase 0 catalog equivalence."""

from __future__ import annotations

from stealth_study.agents.base import AgentContext
from stealth_study.agents.code import code_agent
from stealth_study.agents.cowork import cowork_agent
from stealth_study.personas.registry import PersonaRegistry
from stealth_study.tools.todo import TodoList


def _ctx(tmp_path) -> AgentContext:
    return AgentContext(workspace=tmp_path, executor=object(), todo=TodoList())


def _names(agent, ctx) -> set:
    return {getattr(t, "__name__", "") for t in agent.build_tools(ctx)}


def test_code_persona_matches_builder(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    assert _names(reg.agent("code"), ctx) == _names(code_agent(), ctx)
    assert reg.agent("code").requires_folder and reg.agent("code").subagents


def test_cowork_persona_matches_builder(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    assert _names(reg.agent("cowork"), ctx) == _names(cowork_agent(), ctx)
    a = reg.agent("cowork")
    assert a.messaging and a.connectors


def test_ops_persona_composes_knowledge_toolset(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    # Ops uses the same capability list as Cowork (files/search/shell/todo).
    assert _names(reg.agent("ops"), ctx) == _names(cowork_agent(), ctx)
    a = reg.agent("ops")
    assert not a.requires_folder and a.scheduling and a.messaging and a.connectors
    assert "read_file" in _names(a, ctx)  # windowed reader, multi-root aware


def test_code_keeps_single_root_file_tools(tmp_path):
    reg = PersonaRegistry()
    names = _names(reg.agent("code"), _ctx(tmp_path))
    assert "read_file" in names and "read_file_lines" not in names
    assert "git_log" in names  # code has git; cowork/ops do not


def test_default_cowork_prompt_is_study_oriented():
    from stealth_study.agents.cowork import COWORK_INSTRUCTIONS

    prompt = COWORK_INSTRUCTIONS
    assert "学习" in prompt
    assert "deliverable" not in prompt.lower()
    assert "knowledge-work" not in prompt.lower()

def test_default_cowork_registry_meta_is_study_oriented():
    reg = PersonaRegistry()
    entry = reg.get("cowork")
    assert entry is not None
    assert entry.name == "学习伙伴"
    assert "学习" in entry.tagline
    assert "deliverable" not in entry.tagline.lower()
