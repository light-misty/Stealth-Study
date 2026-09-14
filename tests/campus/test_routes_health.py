"""Tests for `build_campus_router()` and `GET /v1/campus/health` (03 §2, 07 §4 T06 验收①).

The factory is what `create_app()` calls once, so these tests pin three things: the router
shape the documented two-line mount depends on, the health contract, and the "mounting is
initialising" rule of 02 §3.4 — opening the router opens `campus.db`, and a database that
cannot be migrated aborts startup instead of serving a half-built API.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import routes, store, tracks

EXPECTED_TABLE_COUNT = 19
APPLIED_AT = "2026-09-14T00:00:00Z"


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


def _write_future_database(path: Path, version: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(store.SCHEMA_META_DDL)
        connection.execute(
            "INSERT INTO schema_meta (key, version, applied_at) VALUES (?, ?, ?)",
            (store.SCHEMA_VERSION_KEY, version, APPLIED_AT),
        )
        connection.commit()
    finally:
        connection.close()


def test_the_factory_returns_an_api_router_under_the_campus_prefix() -> None:
    router = routes.build_campus_router(object())
    assert isinstance(router, APIRouter)
    assert router.prefix == routes.CAMPUS_PREFIX


def test_every_declared_route_stays_inside_the_campus_prefix() -> None:
    router = routes.build_campus_router(object())
    assert router.routes
    for route in router.routes:
        assert route.path.startswith(f"{routes.CAMPUS_PREFIX}/")


def test_health_answers_200_with_the_documented_body(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == store.CURRENT_SCHEMA_VERSION


def test_health_reports_the_three_declared_tracks(client: TestClient) -> None:
    body = client.get(f"{routes.CAMPUS_PREFIX}/health").json()
    assert body["tracks"] == list(tracks.TRACK_IDS)


def test_health_is_read_only(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/health")
    assert response.status_code == 405


def test_mounting_the_router_creates_the_campus_database(campus_db_path: Path) -> None:
    assert not campus_db_path.exists()
    routes.build_campus_router(object())
    assert campus_db_path.is_file()
    with store.CampusStore(campus_db_path) as opened:
        assert opened.current_version() == store.CURRENT_SCHEMA_VERSION
        assert len(opened.table_names()) == EXPECTED_TABLE_COUNT


def test_mounting_refuses_a_database_from_a_newer_application(campus_db_path: Path) -> None:
    _write_future_database(campus_db_path, store.CURRENT_SCHEMA_VERSION + 1)
    with pytest.raises(store.SchemaVersionError):
        routes.build_campus_router(object())


def test_a_refused_mount_releases_the_file_and_recovers_after_repair(campus_db_path: Path) -> None:
    _write_future_database(campus_db_path, store.CURRENT_SCHEMA_VERSION + 1)
    with pytest.raises(store.SchemaVersionError):
        routes.build_campus_router(object())
    campus_db_path.unlink()
    with store.CampusStore(campus_db_path) as reopened:
        assert reopened.current_version() == store.CURRENT_SCHEMA_VERSION
