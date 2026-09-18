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
    # 桌面壳登记：STT 从编译链移除 + 后端日志根固定到仓库根 log/（桌面壳均改动此文件）
    "surfaces/gui/src-tauri/src/lib.rs",
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
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
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
