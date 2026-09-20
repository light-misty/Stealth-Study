"""T21 验收 — 备考台人设包与技能包的落盘终态（07 §6 T21、08 §8 T21 行）。

四条验收标准的落点：

1. 6 人设在新会话选择器可见（发布构建、无 `OPENWORKER_UNSHIPPED`）——同时钉住 05 §1
   硬约束 1 的反面：既有 14 个 `ships: false` 人设行为不变，不因新目录而泄漏。
2. 7 个技能包在**对应**人设会话内可渐进加载（目录只有 name+description，正文按需 load），
   且不会串到别人设会话。
3. `rubrics.py` ↔ SKILL.md 的逐字一致性由 `test_rubrics_consistency.py` 独立承担。
4. `group: campus` 等非法注入必须被 `ManifestError` 拦在注册表构造之外（不是静默丢弃），
   因为 `_load_dir()` 无 try/except，漏进去等于应用启动失败。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from stealth_study.personas.manifest import ManifestError, parse_manifest
from stealth_study.personas.registry import PersonaRegistry
from stealth_study.providers import ModelCapabilities, ProviderClient
from stealth_study.sessions import SessionRecord
from stealth_study.skills.base import SkillLoader

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ROOT / "ss" / "personas" / "builtin"
DOC = ROOT / "docs" / "dev" / "05-人设与技能包设计.md"

# 人设 id → 该 bundle 的技能 allowlist（05 §2 字段分配总表）。
BUNDLES = {
    "cet-examiner": ("cet-listening-drill", "mock-exam-proctor"),
    "cet-grader": ("cet-essay-grading", "cet-translation-grading"),
    "kaoyan-planner": ("kaoyan-weekly-review",),
    "kaoyan-subject-tutor": (),
    "cert-instructor": ("cert-knowledge-tree",),
    "study-companion": ("mistake-attribution",),
}
ALL_SKILLS = tuple(s for skills in BUNDLES.values() for s in skills)

# 05 §2 表：人设 id → (icon, tools)。icon 必须落在 personaIcon 的 NAMED 集合内。
ICONS_AND_TOOLS = {
    "cet-examiner": ("clock", ["files", "search", "todo"]),
    "cet-grader": ("pencil", ["files", "todo"]),
    "kaoyan-planner": ("branch", ["files", "search", "todo"]),
    "kaoyan-subject-tutor": ("sliders", ["files", "search"]),
    "cert-instructor": ("table", ["files", "search", "todo"]),
    "study-companion": ("sparkle", ["files", "search", "todo"]),
}

# 既有 14 个 ships:false 人设（13 个目录 + ops.md）——它们的可见性不因 T21 改变。
UNSHIPPED = (
    "ops",
    "appsec-worker",
    "change-worker",
    "design-worker",
    "devops-lead",
    "devsecops-lead",
    "infra-worker",
    "logs-worker",
    "posture-worker",
    "secrets-worker",
    "swe-lead",
    "swe-worker",
    "test-worker",
    "triage-lead",
)

# 05 文档 §3.1-§3.6 的人设模板（顺序即 id 顺序）。
DOC_TEMPLATES = {
    "3.1": "cet-examiner",
    "3.2": "cet-grader",
    "3.3": "kaoyan-planner",
    "3.4": "kaoyan-subject-tutor",
    "3.5": "cert-instructor",
    "3.6": "study-companion",
}


def _reg(tmp_path) -> PersonaRegistry:
    return PersonaRegistry(state_path=tmp_path / "personas.json")


def _doc_block(header: str) -> str:
    doc = DOC.read_text(encoding="utf-8")
    match = re.search(rf"### {re.escape(header)}.*?```markdown\n(.*?)\n```", doc, re.S)
    assert match, f"未在 05 文档中找到 {header} 章节"
    return match.group(1).strip()


# -- 验收 ① 可见性与可用性 -----------------------------------------------------


def test_six_campus_personas_are_visible_in_a_release_build(tmp_path, monkeypatch):
    """发布构建（无 OPENWORKER_UNSHIPPED）即应在选择器里看到六人设。

    这条同时是 05 §1 硬约束 1 的回归网：只要有人照抄现有人设模板带出 `ships: false`，
    人设会在正式构建里集体隐身，此处立刻变红。
    """
    monkeypatch.delenv("OPENWORKER_UNSHIPPED", raising=False)
    reg = _reg(tmp_path)
    sidebar = {e["name"] for e in reg.sidebar()}
    listed = {p["id"]: p for p in reg.list_all()}

    for persona_id in BUNDLES:
        assert persona_id in sidebar, f"{persona_id} 未出现在新会话选择器"
        assert persona_id in listed, f"{persona_id} 未出现在人设设置面板"
        assert listed[persona_id]["ships"] is True
        assert listed[persona_id]["group"] == "general"
        assert listed[persona_id]["enabled"] and listed[persona_id]["surfaced"]
        assert listed[persona_id]["requires_folder"] is False


def test_existing_unshipped_personas_keep_their_behaviour(tmp_path, monkeypatch):
    """既有 14 个 `ships: false` 人设：发布构建不可见、仍可解析；内部构建全量可见。"""
    monkeypatch.delenv("OPENWORKER_UNSHIPPED", raising=False)
    release = _reg(tmp_path)
    release_ids = {p["id"] for p in release.list_all()}
    for persona_id in UNSHIPPED:
        assert persona_id not in release_ids, f"{persona_id} 泄漏进发布构建"
        # 解析路径不受影响：已运行的人设会话不会因为不可见而失效。
        assert release.agent(persona_id).name == persona_id

    monkeypatch.setenv("OPENWORKER_UNSHIPPED", "1")
    internal_ids = {p["id"] for p in _reg(tmp_path).list_all()}
    assert set(UNSHIPPED) <= internal_ids


def test_campus_personas_carry_the_documented_identity_fields(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENWORKER_UNSHIPPED", raising=False)
    reg = _reg(tmp_path)
    for persona_id, (icon, tools) in ICONS_AND_TOOLS.items():
        entry = reg.get(persona_id)
        assert entry is not None, persona_id
        assert entry.icon == icon
        assert entry.tools == tools
        # `team` 缺省才 default_surfaced；填 worker 会让人设在选择器里消失。
        assert entry.manifest.team is None
        assert entry.manifest.skills == list(BUNDLES[persona_id])


def test_campus_personas_resolve_without_shell_or_git(tmp_path, monkeypatch):
    """核心流程：六人设均可解析成人设会话 Agent，且不因为新增而放大权限面。

    备考台是终端用户面（学生），05 §2 只给 files/search/todo；一旦有人在 manifest 里
    补上 `shell` 或 `git`，这里立刻变红——执行权不该随人设落盘悄悄扩出去。
    """
    from stealth_study.agents.base import AgentContext
    from stealth_study.tools.todo import TodoList

    monkeypatch.delenv("OPENWORKER_UNSHIPPED", raising=False)
    reg = _reg(tmp_path)
    ctx = AgentContext(workspace=tmp_path, executor=object(), todo=TodoList())
    for persona_id in BUNDLES:
        agent = reg.agent(persona_id)
        assert agent.name == persona_id
        assert agent.requires_folder is False
        assert agent.scheduling is True
        names = {getattr(t, "__name__", "") for t in agent.build_tools(ctx)}
        assert "read_file" in names
        assert "run_shell" not in names
        assert not any(n.startswith("git_") for n in names)


# -- 落盘保真：manifest 与 05 文档模板逐字一致 --------------------------------


@pytest.mark.parametrize("header", sorted(DOC_TEMPLATES))
def test_manifest_is_verbatim_the_05_document_template(header: str) -> None:
    """07 §6 T21 要求 manifest "全文照抄 05 文档 §3"。逐字锁定，含三条硬约束注释。"""
    persona_id = DOC_TEMPLATES[header]
    text = (PERSONAS / persona_id / "manifest.md").read_text(encoding="utf-8")
    assert text.strip() == _doc_block(header)


# -- 验收 ② 技能包落盘与渐进加载 ----------------------------------------------


def test_seven_skill_bundles_live_inside_their_persona_directories() -> None:
    """7 个技能包必须落在人设 bundle 内（ADR-02），不建 `stealth_study/skills/campus/`。"""
    assert len(ALL_SKILLS) == 7
    assert len(set(ALL_SKILLS)) == 7
    assert not (ROOT / "ss" / "skills" / "campus").exists()

    for persona_id, skills in BUNDLES.items():
        bundle = PERSONAS / persona_id / "skills"
        if not skills:
            assert not bundle.exists(), f"{persona_id} 不应带技能目录"
            continue
        on_disk = {p.parent.name for p in bundle.glob("*/SKILL.md")}
        assert on_disk == set(skills), persona_id
        for name in skills:
            text = (bundle / name / "SKILL.md").read_text(encoding="utf-8")
            # name 必须等于目录名（skills/store.py 的 validate_name 口径）。
            assert re.search(r"^name: (.+)$", text, re.M).group(1).strip() == name
            assert re.search(r"^description: .+$", text, re.M), f"{name} 缺 description"
            # campus 技能是纯方法指导，一律不声明 allowed-tools（05 §4.1）。
            assert "allowed-tools" not in text and "allowed_tools" not in text


def _persona_skill_dir(persona_id: str) -> Path:
    return PERSONAS / persona_id / "skills"


def test_bundle_skills_are_progressive_disclosure():
    """会话启动只注入 name+description，正文经 load_skill 按需取（skills/base.py:1-6）。"""
    for persona_id, skills in BUNDLES.items():
        if not skills:
            continue
        loader = SkillLoader([_persona_skill_dir(persona_id)])
        catalog = {row["name"]: row["description"] for row in loader.catalog()}
        assert set(catalog) == set(skills)
        for name in skills:
            assert catalog[name].strip()
            skill = loader.get(name)
            # 目录里只有摘要；load_skill 才拿到全文，且正文非空。
            assert skill.instructions.strip()
            assert skill.allowed_tools == []


def test_load_skill_gate_admits_only_the_personas_own_skills():
    """渐进加载的落地口径：会话目录只有 name+description，正文经 load_skill 取；
    跨人设的技能在门禁处被拒，不靠提示词自觉（`skill_tools` 的 allowed 闸门）。
    """
    from stealth_study.skills.base import skill_catalog_text, skill_tools

    for persona_id, skills in BUNDLES.items():
        if not skills:
            continue
        loader = SkillLoader([_persona_skill_dir(persona_id)])
        allowed = set(skills)
        catalog = skill_catalog_text(loader, allowed)
        for name in skills:
            skill = loader.get(name)
            assert f"- {name}: {skill.description}" in catalog
            # 摘要进目录、正文不进：会话启动时看不到评分档全文。
            title = skill.instructions.splitlines()[0]
            assert title not in catalog

        load_skill = {
            getattr(tool, "__name__", ""): tool for tool in skill_tools(loader, allowed)
        }["load_skill"]
        first_title = loader.get(skills[0]).instructions.splitlines()[0]
        assert first_title in str(load_skill(name=skills[0]))

        foreign = set(ALL_SKILLS) - allowed
        if foreign:
            refused = load_skill(name=sorted(foreign)[0])
            assert "unknown skill" in str(refused)


class _ScriptedProvider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        raise AssertionError("no turns expected")

    def capabilities(self, model):
        return ModelCapabilities()


def _manager(tmp_path, monkeypatch):
    from stealth_study.server.manager import SessionManager

    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    return SessionManager(workspace=tmp_path, provider=_ScriptedProvider())


def _save_sessions(manager, persona_ids) -> None:
    for persona_id in persona_ids:
        manager.session_store.save(
            SessionRecord(
                session_id=f"session-{persona_id}",
                workspace="",
                model="m",
                mode="interactive",
                agent=persona_id,
            )
        )


def test_bundle_skills_join_only_their_own_persona_session(tmp_path, monkeypatch):
    """每个 bundle 的 7 个技能只对该人设会话可见，且被 manifest allowlist 收口。"""
    manager = _manager(tmp_path, monkeypatch)
    _save_sessions(manager, BUNDLES)

    for persona_id, skills in BUNDLES.items():
        visible = manager.effective_skill_names(f"session-{persona_id}") & set(ALL_SKILLS)
        assert visible == set(skills), persona_id
        rows = {
            row["name"]: row
            for row in manager.session_skills_view(f"session-{persona_id}")["skills"]
            if row["name"] in ALL_SKILLS
        }
        assert set(rows) == set(skills)
        for row in rows.values():
            assert row["scope"] == "coworker"

    # 不承载 bundle 的会话（内建 cowork）看不到任何一个 campus 技能。
    _save_sessions(manager, ("cowork",))
    assert manager.effective_skill_names("session-cowork").isdisjoint(ALL_SKILLS)


def test_skill_allowlist_narrows_within_the_bundle(tmp_path, monkeypatch):
    """allowlist 是收口而非装饰：考官 bundle 里不应出现阅卷技能，反之亦然。"""
    manager = _manager(tmp_path, monkeypatch)
    _save_sessions(manager, BUNDLES)
    examiner = manager.effective_skill_names("session-cet-examiner")
    grader = manager.effective_skill_names("session-cet-grader")
    assert "cet-essay-grading" not in examiner
    assert "cet-listening-drill" not in grader
    assert "mistake-attribution" not in examiner | grader


# -- 验收 ④ 非法注入负例 ------------------------------------------------------


def test_group_campus_is_rejected_by_the_manifest_error():
    """`VALID_GROUPS` 只有 general/security（manifest.py:29）；campus 必须硬失败。"""
    text = "---\nid: bogus\ngroup: campus\ntools: [files]\n---\n你是一个非法人设。\n"
    with pytest.raises(ManifestError, match="group must be one of"):
        parse_manifest(text)


def test_illegal_campus_injection_does_not_silently_land_in_the_registry(tmp_path, monkeypatch):
    """把非法人设推进 bundle 扫描路径，`_load_dir()` 必须抛错而不是静默跳过。

    静默丢掉是更危险的失败模式：注册表看似正常，用户装的人设却不存在。这里用临时
    `builtin_dir` 复现同一段扫描代码，不触碰仓库内的真实 `stealth_study/personas/builtin/`。
    """
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    probe = tmp_path / "builtin" / "campus-bogus-probe"
    probe.mkdir(parents=True)
    (probe / "manifest.md").write_text(
        "---\nid: campus-bogus-probe\ngroup: campus\ntools: [files]\n---\n非法。\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="group must be one of"):
        PersonaRegistry(builtin_dir=tmp_path / "builtin", state_path=tmp_path / "personas.json")


def test_unknown_tool_is_rejected_by_the_manifest_error():
    """tools 只认 `stealth_study/catalog.py` 的 6 个 id；PRD 提到的 ask/plan 不在白名单。"""
    with pytest.raises(ManifestError, match="unknown tool capabilities"):
        parse_manifest("---\nid: bogus\ntools: [ask]\n---\n非法工具。\n")


def test_worker_team_persona_never_reaches_the_picker(tmp_path):
    """`team: worker` 的人设仍装载但 default_surfaced=False → 只进 Settings，不进选择器。"""
    probe = tmp_path / "builtin" / "bogus-worker"
    probe.mkdir(parents=True)
    (probe / "manifest.md").write_text(
        "---\nid: bogus-worker\nteam: worker\n---\n工人。\n", encoding="utf-8"
    )
    reg = PersonaRegistry(
        builtin_dir=tmp_path / "builtin", state_path=tmp_path / "personas.json"
    )
    assert "bogus-worker" in {p["id"] for p in reg.list_all()}
    assert "bogus-worker" not in {e["name"] for e in reg.sidebar()}
    assert reg.is_enabled("bogus-worker")  # 仍可被 lead 编入团队
