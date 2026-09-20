"""The DevOps team bundle (nineteenth pass) — a standing lead with an on-demand roster.

Shape under test: the lead is a watchman, not a coordinator-of-standing-staff — it
carries a shell for observation (the read-only observer credential is the physics
layer), staffs at most a bounded incident team, and never mutates production. Workers
are diagnosis lanes (symptom / platform / change), staffable-only, and never speak to
the end user.
"""

from __future__ import annotations

from stealth_study.personas.registry import PersonaRegistry

ROSTER = ("logs-worker", "infra-worker", "change-worker")


def _reg(tmp_path) -> PersonaRegistry:
    return PersonaRegistry(state_path=tmp_path / "personas.json")


def test_bundle_registers_with_team_traits(tmp_path):
    reg = _reg(tmp_path)
    assert reg.get("devops-lead").manifest.team == "lead"
    for pid in ROSTER:
        assert reg.get(pid).manifest.team == "worker"


def test_lead_surfaces_workers_do_not(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENWORKER_UNSHIPPED", "1")  # teams are ships:false — internal builds
    reg = _reg(tmp_path)
    ids = [e["name"] for e in reg.sidebar()]
    assert "devops-lead" in ids
    assert not any(pid in ids for pid in ROSTER)


def test_lead_observes_but_cannot_deploy(tmp_path):
    # Unlike coordination-only leads, the watchman carries shell — observation IS its
    # standing work. The prompt must pin the credential story and the no-mutation line.
    lead = _reg(tmp_path).get("devops-lead")
    assert "shell" in lead.tools
    prompt = lead.manifest.system_prompt
    assert "observer" in prompt.lower()
    assert "只读" in prompt.lower()
    assert "由人类执行" in prompt.lower()


def test_standing_watch_contract_lines(tmp_path):
    prompt = _reg(tmp_path).get("devops-lead").manifest.system_prompt
    # Case-ledger dedup: sweeps update cases, only new judgment files items.
    assert "它不会获得新的看板条目" in prompt
    # Deploy correlation is the product.
    assert "什么发布了" in prompt.lower()
    # Interim caps (budgets deferred): bounded cadence, bounded staffing.
    assert "绝不短于 10" in prompt
    assert "最多 三个 工人" in prompt
    # Ops notes are the deployment seam; without them the lead must not guess.
    assert "OPSWATCH" in prompt
    # The one-time board chip (seventeenth pass).
    assert "(board:)" in prompt


def test_workers_carry_the_load_bearing_rules(tmp_path):
    reg = _reg(tmp_path)
    for pid in ROSTER:
        prompt = reg.get(pid).manifest.system_prompt
        flat = " ".join(prompt.split())  # prompts hard-wrap; match across newlines
        assert "ask_user" in flat  # the "never use" line
        assert "不可信任的输入" in flat
        assert "绝不记录值" in flat  # secrets stay radioactive
    # Lane separation is written down, not vibes.
    assert "症状侧" in reg.get("logs-worker").manifest.system_prompt
    assert "平台侧" in reg.get("infra-worker").manifest.system_prompt
    assert "变更侧" in reg.get("change-worker").manifest.system_prompt
    # The infra worker never applies.
    assert "terraform apply" in reg.get("infra-worker").manifest.system_prompt
