"""F-5, 08 §2.2 — the campus frontend intrusion budget as a machine check.

01 §6 registers the campus intrusion points in existing files; the frontend ones
touch App.tsx / Sidebar.tsx / SettingsView.tsx / Composer.tsx / Onboarding.tsx / flags.ts
(plus the locales and the backend mount in app.py). Anything else modified in the
production tree — outside the campus-owned trees (`ss/campus/**`,
`surfaces/gui/src/campus/**`, `surfaces/gui/src/components/campus/**`) plus the registered
e2e harness files, the locales, the design mockups and the tests — means the "addition only"
rule (PRD v1.1 B⑤: no spreading into the 24 voice-adjacent files) has been violated and the
diff must go back through review.

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
    # skip-question-card 分支登记：OPE-153 跳过提问——ask 工具的哨兵值与跳过结算、
    # 引擎对全跳过卡片的 denied 判定、Slack 镜像的 Skip 按钮、收件箱卡片的跳过
    # 入口，以及覆盖四个跳过场景的 e2e 规格
    "ss/tools/ask.py",
    "ss/engine.py",
    "ss/interactions.py",
    "surfaces/gui/src/components/InboxItemCard.tsx",
    "surfaces/gui/e2e/ask-skip.spec.ts",
    "docs/skip-question-test-report.md",
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
    # 错误显示点接线第一片：SkillsTab 的 fail() 改走 apiErrorText，原文降级为悬浮提示。
    "surfaces/gui/src/components/SkillsTab.tsx",
    # 工作区/文件夹域接线（同一片的第二组）：错误文案改由 error_code 查语言包，
    # useRoots 额外把后端原文作为 errorDetail 透出给消费方挂悬浮。
    "surfaces/gui/src/components/AccessSection.tsx",
    "surfaces/gui/src/components/FolderGate.tsx",
    "surfaces/gui/src/components/SendFolderDialog.tsx",
    "surfaces/gui/src/components/SessionIntro.tsx",
    "surfaces/gui/src/components/SessionSetupRow.tsx",
    "surfaces/gui/src/components/WorkspaceTrustPrompt.tsx",
    # 第二档 A（personas 域）：清单/导出异常带代号，安装/导出/删除/画廊四处界面取键。
    "ss/personas/registry.py",
    # fix/study-agent-persona 分支登记：默认人设（cowork）系统提示词与元数据学习向改造。
    "ss/agents/cowork.py",
    "ss/cloud.py",
    "surfaces/gui/src/components/GalleryModal.tsx",
    "surfaces/gui/src/components/PersonaView.tsx",
    "surfaces/gui/src/components/PersonasTab.tsx",
    # 第二档 B（定时任务与项目绑定域）：命名/校验异常带代号，两处界面取键。
    "ss/projects.py",
    "surfaces/gui/src/components/ProjectBindMenu.tsx",
    # 第二档 C（Slack/Inbox/订阅域）：连接态与入参守卫消息带代号，6 处界面取键。
    "ss/connectors/slack_directory.py",
    # 第二档 D（连接器一键/手动连接与 PDF 检查）：自写守卫消息带代号，10 处界面取键。
    "ss/connectors/setup.py",
    "ss/pdf_support.py",
    "surfaces/gui/src/components/ManageTabs.tsx",
    "surfaces/gui/src/components/connectors/AddConnectionModal.tsx",
    # 第三档（模型提供方校验）：自写校验消息带代号，ProviderSetup 取键。
    "ss/providers/registry.py",
    # 备考台原型落地：三个台子的样式层与图标集落在 campus 目录之外，因为它们要能被
    # `main.tsx` 直接 import（`src/campus/` 下的文件按约定只放数据层与面板）。
    # `campus-station.css` / `campus-icons.tsx` 是新增文件，另外三处是既有文件的追加式改动。
    "surfaces/gui/src/campus-station.css",
    "surfaces/gui/src/components/campus-icons.tsx",
    "surfaces/gui/src/components/Icon.tsx",
    "surfaces/gui/src/styles.css",
    "surfaces/gui/tailwind.config.js",
}

# Design mockups: neither shipped nor compiled, and the whole redesign workflow lives in there.
# They are not "the production tree", so the budget's "no spreading" rule does not apply to them.
NON_PRODUCTION_PREFIXES = ("ui-mocks/",)

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
    if path.startswith(CAMPUS_OWNED_PREFIXES) or path.startswith(NON_PRODUCTION_PREFIXES):
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
