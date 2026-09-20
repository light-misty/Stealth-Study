"""T03 SPIKE-3：include_router 挂载冒烟的纯本地测试。

不启动真实服务器（真实子进程冒烟由 spike_mount.py 自身执行），
这里只验证三件事：临时路由形状正确、apiToken 中间件覆盖挂载路由、
app.py 补丁可精确插入与无损还原（08 文档 §3.3）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = ROOT / "scripts" / "v0-spikes"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def spike():
    return _load("ss_v0_spike_mount", SPIKE_DIR / "spike_mount.py")


def _make_temp_campus_pkg(spike, tmp_path: Path):
    spike.write_temp_campus_package(tmp_path)
    return spike.load_build_campus_router(tmp_path)


def test_temp_router_health_200(spike, tmp_path: Path):
    build_campus_router = _make_temp_campus_pkg(spike, tmp_path)
    app = FastAPI()
    app.include_router(build_campus_router(object()))
    client = TestClient(app)
    resp = client.get("/v1/campus/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["spike"] == "T03"


def test_token_middleware_covers_mounted_router(spike, tmp_path: Path, monkeypatch):
    from stealth_study.server.app import create_app
    from stealth_study.server.manager import SessionManager

    token = "spike-t03-token"
    monkeypatch.setenv("COWORKER_API_TOKEN", token)
    manager = SessionManager(data_dir=tmp_path / "data")
    app = create_app(manager)
    build_campus_router = _make_temp_campus_pkg(spike, tmp_path)
    app.include_router(build_campus_router(manager))
    client = TestClient(app)

    assert client.get("/v1/campus/health").status_code == 401
    assert (
        client.get("/v1/campus/health", headers={"x-stealthstudy-token": "wrong"}).status_code
        == 401
    )
    ok = client.get("/v1/campus/health", headers={"x-stealthstudy-token": token})
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"

    assert client.get("/v1/sessions", headers={"x-stealthstudy-token": token}).status_code == 200
    assert client.get("/v1/settings", headers={"x-stealthstudy-token": token}).status_code == 200
    assert (
        client.get("/v1/automations", headers={"x-stealthstudy-token": token}).status_code == 200
    )


def test_patch_inserts_two_lines_after_app_creation(spike):
    original = (ROOT / "stealth_study" / "server" / "app.py").read_text(encoding="utf-8")
    patched = spike.apply_mount_patch(original)
    lines = patched.splitlines()
    anchor = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith("app = FastAPI(")
    )
    assert "from stealth_study.campus.routes import build_campus_router" in lines[anchor + 1]
    assert "app.include_router(build_campus_router(manager))" in lines[anchor + 2]
    assert len(lines) == len(original.splitlines()) + 2
    with pytest.raises(spike.SpikeError):
        spike.apply_mount_patch(patched)


def test_restore_returns_original_exactly(spike):
    original = (ROOT / "stealth_study" / "server" / "app.py").read_text(encoding="utf-8")
    patched = spike.apply_mount_patch(original)
    assert spike.restore_mount_patch(patched) == original


def test_patch_fails_cleanly_on_unexpected_source(spike):
    with pytest.raises(spike.SpikeError):
        spike.apply_mount_patch("def unrelated():\n    pass\n")
    with pytest.raises(spike.SpikeError):
        spike.restore_mount_patch("def unrelated():\n    pass\n")


def test_temp_campus_package_is_self_contained(spike, tmp_path: Path):
    spike.write_temp_campus_package(tmp_path)
    pkg = tmp_path / "campus"
    assert (pkg / "__init__.py").is_file()
    source = (pkg / "routes.py").read_text(encoding="utf-8")
    assert "def build_campus_router" in source
    assert source.count("\n") <= 20
    assert "/v1/campus" in source
