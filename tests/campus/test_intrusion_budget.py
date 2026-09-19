"""F-5, 08 §2.2 — the campus frontend intrusion budget as a machine check.

01 §6 registers exactly nine campus intrusion points in existing files; the frontend ones
touch App.tsx / Sidebar.tsx / SettingsView.tsx / Composer.tsx / Onboarding.tsx / flags.ts
(plus the locales and the backend mount in app.py). Anything else modified in the
production tree — outside the campus-owned trees (`ss/campus/**`,
`surfaces/gui/src/campus/**`, `surfaces/gui/src/components/campus/**`) plus the registered
e2e harness files, the locales and the tests — means the "addition only" rule (PRD v1.1 B⑤:
no spreading into the 24 voice-adjacent files) has been violated and the diff must go back
through review.

Pure `git diff --name-status` assertion, no GUI needed; skipped when there is no base
revision to compare against (a checkout already on the base, a shallow clone without the
base objects, or the merged state where the diff is empty by construction).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

BASE_CANDIDATES = (
    "main",
    "refs/heads/main",
    "refs/remotes/origin/main",
    "refs/remotes/Stealth-Study/main",
)

REGISTERED_PATCH: set[str] = {
    "surfaces/gui/src/App.tsx",
    "surfaces/gui/src/components/Sidebar.tsx",
    "surfaces/gui/src/components/SettingsView.tsx",
    "surfaces/gui/src/components/Composer.tsx",
    "surfaces/gui/src/components/Onboarding.tsx",
    "surfaces/gui/src/flags.ts",
    "surfaces/gui/src/locales/zh.json",
    "surfaces/gui/src/locales/en.json",
    # 桌面壳登记：STT 从编译链移除 + 后端日志根固定到仓库根 log/（桌面壳及其依赖清单）
    "surfaces/gui/src-tauri/src/lib.rs",
    "surfaces/gui/src-tauri/Cargo.toml",
    "surfaces/gui/src-tauri/Cargo.lock",
    "stt/Cargo.lock",
    "ss/server/app.py",
    # logging-system 分支登记：统一日志配置、启动初始化、上传端点与前端日志模块
    "ss/logging_setup.py",
    "ss/server/run.py",
    "surfaces/gui/src/api.ts",
    "surfaces/gui/src/main.tsx",
    "surfaces/gui/src/logging/capture.ts",
    "surfaces/gui/src/logging/index.ts",
    "surfaces/gui/src/logging/store.ts",
    "surfaces/gui/src/logging/upload.ts",
    "pyproject.toml",
    ".gitignore",
    "docs/logging-system-test-report.md",
    "docs/superpowers/specs/2026-09-16-logging-system-design.md",
    # The campus e2e harness: `fixtures.ts` is shared test infrastructure every spec routes
    # through (the same category as `app.py`), and `campus.spec.ts` is the campus smoke itself.
    # Listed by file — not by directory — so the other 60 specs stay outside the budget. The live
    # pair is the same deal for `e2e-live/`: the real-backend smoke plus the one config knob
    # (`actionTimeout`) that keeps a missing selector failing instead of hanging.
    "surfaces/gui/e2e/fixtures.ts",
    "surfaces/gui/e2e/campus.spec.ts",
    "surfaces/gui/e2e-live/campus.spec.ts",
    "surfaces/gui/playwright.live.config.ts",
    # i18n-chinese-coverage 分支登记：全 GUI 的中文化清扫，不是 campus 侵入。
    # 这批文件被改的原因一律是「原先硬编码英文/未接 i18n」或「零引用废弃代码清理」，
    # 逐提交对应 fix(gui)/chore(gui) 记录；不改任何 campus 业务逻辑，也不新增共享文件。
    # 三个 i18n 测试文件按 .test.ts(x) 规则自动豁免，故不在此列出。
    "surfaces/gui/index.html",
    "surfaces/gui/src/humanize.ts",
    "surfaces/gui/src/i18n.ts",
    "surfaces/gui/src/itemsFromMessages.ts",
    "surfaces/gui/src/tauri.ts",
    "surfaces/gui/src/useRoots.ts",
    "surfaces/gui/src/connectors/ConnectorIcon.tsx",
    "surfaces/gui/src/providers/ProviderSetup.tsx",
    "surfaces/gui/src/components/BoardPanel.tsx",
    "surfaces/gui/src/components/ConnectorMessageCard.tsx",
    "surfaces/gui/src/components/InboxConfigure.tsx",
    "surfaces/gui/src/components/Markdown.tsx",
    "surfaces/gui/src/components/ModelChecklist.tsx",
    "surfaces/gui/src/components/RightRail.tsx",
    "surfaces/gui/src/components/ScheduledView.tsx",
    "surfaces/gui/src/components/SubscriptionsChip.tsx",
    "surfaces/gui/src/components/TeamChatView.tsx",
    "surfaces/gui/src/components/Transcript.tsx",
    "surfaces/gui/src/components/brandIcons.tsx",
    "surfaces/gui/src/components/personaIcon.tsx",
    "surfaces/gui/src/components/connectors/CalendarDetail.tsx",
    "surfaces/gui/src/components/connectors/CloudSignIn.tsx",
    "surfaces/gui/src/components/connectors/ConnectorsSection.tsx",
    "surfaces/gui/src/components/connectors/CustomMcp.tsx",
    "surfaces/gui/src/components/connectors/GithubDetail.tsx",
    "surfaces/gui/src/components/connectors/HubSpotDetail.tsx",
    "surfaces/gui/src/components/connectors/SlackDetail.tsx",
    "surfaces/gui/src/components/connectors/SlackHowItWorks.tsx",
    # 已删除的废弃组件：待办面板早被 RightRail 取代，全仓库零引用（删除同样要过本登记）。
    "surfaces/gui/src/components/TodoPanel.tsx",
    # 后端错误代号分类器与前端取键入口（中文化方案 C 的地基，两侧各一个新文件）。
    "ss/errors.py",
    "ss/server/manager.py",
    "surfaces/gui/src/errors.ts",
    # 技能子系统的校验异常改抛带代号的 CodedValueError（仍是 ValueError，消息逐字未变）。
    "ss/skills/store.py",
}

CAMPUS_OWNED_PREFIXES = (
    "ss/campus/",
    "surfaces/gui/src/campus/",
    "surfaces/gui/src/components/campus/",
    "tests/",
    "docs/dev/",
)


def _allowed(path: str) -> bool:
    if path in REGISTERED_PATCH:
        return True
    if path.startswith(CAMPUS_OWNED_PREFIXES):
        return True
    return path.endswith(".test.tsx") or path.endswith(".test.ts")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def _base_revision() -> str | None:
    for candidate in BASE_CANDIDATES:
        resolved = _git("rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}").strip()
        if resolved:
            return resolved
    return None


def test_no_production_file_outside_the_registered_frontend_patch_changed() -> None:
    base = _base_revision()
    if base is None or _git("rev-parse", "HEAD").strip() == base:
        pytest.skip("no base revision to compare against from this checkout")
    status = _git("diff", "--name-status", base)
    offenders: list[str] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        path = line.split("\t", 1)[-1]
        if not _allowed(path):
            offenders.append(line)
    assert offenders == [], (
        "campus frontend intrusion spread outside the 01 §6 registered set: "
        + ", ".join(offenders)
    )
