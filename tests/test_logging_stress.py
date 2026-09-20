"""日志系统压力测试：大流量写入的吞吐、轮转与批量接收正确性。

默认跳过；显式设置 SS_RUN_STRESS=1 时运行（避免拖慢常规 CI）：
    SS_RUN_STRESS=1 python -m pytest tests/test_logging_stress.py -q -s
"""

from __future__ import annotations

import os
import time

import pytest

from stealth_study.logging_setup import get_logger, setup_logging

pytestmark = pytest.mark.skipif(
    os.environ.get("SS_RUN_STRESS") != "1",
    reason="压力测试需显式设置 SS_RUN_STRESS=1 运行",
)

# 单测写入规模（10 万行）
TOTAL = 100_000


def test_backend_throughput_large_volume(tmp_path, monkeypatch, capsys):
    # 关闭大小轮转以排除归档开销，测纯写入吞吐
    monkeypatch.setenv("SS_LOG_MAX_BYTES", "0")
    monkeypatch.setenv("SS_LOG_DIR", str(tmp_path / "log"))
    setup_logging(tmp_path, level="INFO")
    lg = get_logger("stress")

    start = time.perf_counter()
    for i in range(TOTAL):
        lg.info(f"stress line {i} payload 0123456789")
    elapsed = time.perf_counter() - start

    lines = 0
    for f in (tmp_path / "log").glob("backend_*.log"):
        lines += sum(1 for _ in f.open(encoding="utf-8"))
    assert lines == TOTAL, "大流量写入出现丢行"

    ms_per_line = elapsed * 1000 / TOTAL
    with capsys.disabled():
        print(f"backend: {TOTAL} lines in {elapsed:.2f}s -> {ms_per_line * 1000:.1f} us/line")
    assert ms_per_line < 5, "单行写入耗时需低于 5ms"


def test_backend_rotation_under_load(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_LOG_MAX_BYTES", str(256 * 1024))
    monkeypatch.setenv("SS_LOG_KEEP_FILES", "3")
    monkeypatch.setenv("SS_LOG_DIR", str(tmp_path / "log"))
    setup_logging(tmp_path, level="DEBUG")
    lg = get_logger("stress-rot")

    for i in range(TOTAL // 4):
        lg.debug(f"rot line {i} data")

    all_files = list((tmp_path / "log").glob("backend_*.log*"))
    assert any(".log." in f.name for f in all_files), "未触发大小轮转"
    # 主文件不应超过阈值 + 单行余量
    mains = [f for f in all_files if f.suffix == ".log"]
    for f in mains:
        assert f.stat().st_size <= 256 * 1024 + 1024


def test_frontend_endpoint_bulk_ingest(tmp_path, monkeypatch, capsys):
    from fastapi.testclient import TestClient

    from stealth_study.server import SessionManager, create_app

    monkeypatch.setenv("SS_LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setenv("COWORKER_API_TOKEN", "t")
    setup_logging(tmp_path)
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))

    entries = [
        {
            "ts": f"2026-09-16 10:00:00,{i % 1000:03d}",
            "level": "INFO",
            "message": f"m-{i}",
        }
        for i in range(5000)
    ]
    start = time.perf_counter()
    resp = client.post("/v1/logs/frontend", headers={"X-SS-Token": "t"}, json={"logs": entries})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"accepted": 5000, "skipped": 0, "rotated": False}

    written = sum(
        1
        for _ in sorted((tmp_path / "log").glob("frontend_*.log"))[-1].open(encoding="utf-8")
    )
    assert written == 5000
    with capsys.disabled():
        print(f"frontend bulk: 5000 entries ingested in {elapsed * 1000:.0f} ms")