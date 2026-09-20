"""日志系统后端功能测试：目录/命名、格式字段、轮转与清理、并发写入与幂等配置。"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import pytest

from stealth_study.logging_setup import (
    DailyRotatingSizeHandler,
    get_logger,
    request_id_var,
    setup_logging,
    user_id_var,
    write_frontend_logs,
)


def _read(log_dir) -> str:
    files = sorted((log_dir).glob("backend_*.log"))
    assert files, "no backend log file written"
    return files[-1].read_text(encoding="utf-8")


def _line_matches(line: str, pattern: str) -> bool:
    return re.match(pattern, line) is not None


def test_creates_log_dir_and_backend_file_named_by_startup_ts(tmp_path):
    setup_logging(tmp_path)
    files = list((tmp_path / "log").glob("backend_*.log"))
    assert files, "log/ 目录未自动创建或 backend 文件缺失"
    assert re.fullmatch(r"backend_\d{8}_\d{6}\.log", files[0].name)


def test_sets_uniform_format_with_ms_level_module_and_context(tmp_path):
    setup_logging(tmp_path)
    lg = get_logger("fmt.test")
    request_id_var.set("REQ-1")
    user_id_var.set("USR-7")
    lg.info("hello")
    text = _read(tmp_path / "log")
    line = text.strip().splitlines()[0]
    assert _line_matches(
        line,
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} "
        r"\[INFO\] \[fmt\.test\] \[req=REQ-1\] \[user=USR-7\] hello$",
    )


def test_contextfalls_back_to_dash_when_unset(tmp_path):
    setup_logging(tmp_path)
    request_id_var.set("")
    user_id_var.set("")
    get_logger("ctx").warning("no context")
    line = _read(tmp_path / "log").strip().splitlines()[0]
    assert "[req=-] [user=-]" in line


def test_level_names_map_to_standard_logging(tmp_path):
    setup_logging(tmp_path, level="DEBUG")
    lg = get_logger("lvl")
    lg.debug("d")
    lg.info("i")
    lg.warning("w")
    lg.error("e")
    lg.critical("f")  # FATAL 映射
    text = _read(tmp_path / "log")
    lines = text.strip().splitlines()
    assert "[DEBUG]" in "\n".join(lines)
    assert "[INFO]" in "\n".join(lines)
    assert "[WARNING]" in "\n".join(lines)
    assert "[ERROR]" in "\n".join(lines)
    assert "[CRITICAL]" in "\n".join(lines)


def test_ss_log_dir_env_overrides_default(tmp_path, monkeypatch):
    custom = tmp_path / "custom-logs"
    monkeypatch.setenv("SS_LOG_DIR", str(custom))
    setup_logging(tmp_path)
    assert (custom / "backend_*.log").parent.exists()


def test_setup_logging_is_idempotent(tmp_path):
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    root = logging.getLogger()
    handlers = [
        h
        for h in root.handlers
        if getattr(h, "baseFilename", "").startswith(str(tmp_path))
    ]
    assert len(handlers) == 1


def test_size_rotation_creates_backup_files(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_LOG_MAX_BYTES", "500")
    setup_logging(tmp_path)
    lg = get_logger("rotate")
    for i in range(100):
        lg.info(f"padding line {i:04d}")
    backups = [f for f in (tmp_path / "log").glob("backend_*.log.*")]
    assert backups, "超过 maxBytes 后应产生 .1/.2 轮转备份"


def test_daily_rollover_opens_new_file_with_new_ts(tmp_path):
    now = [datetime(2026, 9, 16, 23, 59, 59)]
    handler = DailyRotatingSizeHandler("backend", tmp_path, now=lambda: now[0])
    try:
        handler.write_line("first")
        first_name = (tmp_path / "backend_20260916_235959.log").name
        now[0] = datetime(2026, 9, 17, 0, 0, 1)
        handler.write_line("second")
        files = sorted(f.name for f in tmp_path.glob("backend_*.log"))
        assert first_name in files
        assert "backend_20260917_000001.log" in files
        content = (tmp_path / "backend_20260917_000001.log").read_text(encoding="utf-8")
        assert content == "second\n"
    finally:
        handler.close()


def test_keep_files_trims_oldest(tmp_path):
    now = [datetime(2026, 9, 15, 10, 0, 0)]
    handler = DailyRotatingSizeHandler("backend", tmp_path, keep_files=2, now=lambda: now[0])
    try:
        for day in range(1, 5):
            now[0] = datetime(2026, 9, 15 + day, 10, 0, 0)
            handler.write_line(f"day-{day}")
        files = sorted(f.name for f in tmp_path.glob("backend_*.log"))
        assert len(files) == 2, "仅应保留最近 2 个文件"
    finally:
        handler.close()


def test_concurrent_writes_do_not_lose_lines(tmp_path):
    setup_logging(tmp_path)
    lg = get_logger("conc")

    async def hammer(i: int) -> None:
        for n in range(200):
            lg.info(f"task-{i} line-{n}")

    async def main() -> None:
        await asyncio.gather(*(hammer(i) for i in range(8)))

    asyncio.run(main())
    text = _read(tmp_path / "log")
    for i in range(8):
        for n in range(200):
            assert f"task-{i} line-{n}" in text, f"并发写丢行 task-{i} line-{n}"


def test_write_frontend_logs_accepts_and_skips(tmp_path):
    setup_logging(tmp_path)
    entries = [
        {"ts": "2026-09-16 22:30:05,123", "level": "INFO", "message": "ok"},
        {"ts": "2026-09-16T22:30:06.789Z", "level": "ERROR", "message": "iso", "stack": "at fn (x:1)"},
        {"ts": "bad", "level": "INFO", "message": "跳过"},
        {"level": "NOPE", "message": "跳过"},
        {"ts": "2026-09-16 22:30:07,000", "level": "WARN", "message": "   "},
        "not-a-dict",
    ]
    accepted, skipped, rotated = write_frontend_logs(entries)
    assert (accepted, skipped) == (2, 4)
    assert rotated is False
    files = sorted((tmp_path / "log").glob("frontend_*.log"))
    assert files and re.fullmatch(r"frontend_\d{8}_\d{6}\.log", files[-1].name)
    text = files[-1].read_text(encoding="utf-8")
    assert "2026-09-16 22:30:05,123 [INFO] ok" in text
    assert "2026-09-16 22:30:06,789 [ERROR] iso" in text
    assert "at fn (x:1)" in text
    assert "跳过" not in text


def test_write_frontend_logs_truncates_oversized_batch(tmp_path):
    setup_logging(tmp_path)
    entries = [
        {"ts": "2026-09-16 22:30:05,000", "level": "INFO", "message": f"m-{i}"}
        for i in range(10001)
    ]
    accepted, skipped, _ = write_frontend_logs(entries)
    assert accepted == 10000
    assert skipped == 1