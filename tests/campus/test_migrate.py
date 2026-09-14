"""Migration-drill tests for `ss.campus.store` — the `schema_meta` version runner (02 §3).

The drill reproduces 02 §3.5's V0.2 example verbatim (`degrade_level` on `attempt`) and adds a
synthetic column that v1 genuinely does not ship, because v1 already declares `degrade_level`
(02 §4.13) while §3.5's example assumes it is added later. Both are kept: the first proves the
published example replays idempotently, the second proves the ALTER path itself.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ss.campus import store


def _v2_add_column(conn: sqlite3.Connection) -> None:
    """02 §3.5's example migration, verbatim in shape."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(attempt)")}
    if "degrade_level" not in columns:
        conn.execute("ALTER TABLE attempt ADD COLUMN degrade_level INTEGER")


def _v2_add_new_column(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(attempt)")}
    if "review_note" not in columns:
        conn.execute("ALTER TABLE attempt ADD COLUMN review_note TEXT")


def _v2_explode(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE attempt ADD COLUMN doomed TEXT")
    raise RuntimeError("migration exploded")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "campus.db"


def build_v1(db_path: Path) -> None:
    with store.CampusStore(db_path) as instance:
        assert instance.current_version() == 1
        instance.insert(
            "attempt",
            {
                "id": "a1",
                "profile_id": "p1",
                "track_type": "cet",
                "subject": "writing",
                "user_answer": "作文",
            },
        )


def columns_of(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def stored_version(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT version FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def test_registry_is_contiguous_and_starts_at_one() -> None:
    assert store.CURRENT_SCHEMA_VERSION == 1
    assert sorted(store._MIGRATIONS) == list(range(1, store.CURRENT_SCHEMA_VERSION + 1))
    assert store._MIGRATIONS[1] is store._v1_initial_schema


def test_first_install_writes_no_backup(db_path: Path) -> None:
    build_v1(db_path)
    assert not Path(f"{db_path}.bak-v0").exists()


def test_reopening_an_up_to_date_database_is_a_no_op(db_path: Path) -> None:
    build_v1(db_path)
    with store.CampusStore(db_path) as instance:
        assert instance.migrate() == 1
        assert instance.scalar("SELECT COUNT(*) FROM schema_meta") == 1
        assert instance.get("attempt", "a1") is not None


def test_published_example_replays_idempotently_on_a_v1_database(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_v1(db_path)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setitem(store._MIGRATIONS, 2, _v2_add_column)

    with store.CampusStore(db_path) as upgraded:
        assert upgraded.current_version() == 2
        assert "degrade_level" in columns_of(db_path, "attempt")
        assert upgraded.get("attempt", "a1") is not None


def test_version_upgrade_adds_a_missing_column(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_v1(db_path)
    assert "review_note" not in columns_of(db_path, "attempt")
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setitem(store._MIGRATIONS, 2, _v2_add_new_column)

    with store.CampusStore(db_path) as upgraded:
        assert upgraded.current_version() == 2
    assert "review_note" in columns_of(db_path, "attempt")


def test_backup_captures_the_pre_migration_state(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_v1(db_path)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setitem(store._MIGRATIONS, 2, _v2_add_new_column)

    with store.CampusStore(db_path):
        pass

    backup = Path(f"{db_path}.bak-v1")
    assert backup.is_file()
    assert stored_version(backup) == 1
    assert "review_note" not in columns_of(backup, "attempt")
    assert stored_version(db_path) == 2


def test_backup_is_refreshed_for_each_version_that_is_left_behind(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_v1(db_path)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 3)
    monkeypatch.setitem(store._MIGRATIONS, 2, _v2_add_new_column)
    monkeypatch.setitem(store._MIGRATIONS, 3, _v2_add_column)

    with store.CampusStore(db_path):
        pass

    assert stored_version(Path(f"{db_path}.bak-v1")) == 1
    assert stored_version(Path(f"{db_path}.bak-v2")) == 2
    assert stored_version(db_path) == 3


def test_a_database_from_a_newer_version_refuses_to_start(db_path: Path) -> None:
    build_v1(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("UPDATE schema_meta SET version = 99 WHERE key='schema_version'")
    connection.commit()
    connection.close()

    with pytest.raises(store.SchemaVersionError) as error:
        store.CampusStore(db_path)
    assert "99" in str(error.value)
    assert "1" in str(error.value)
    assert stored_version(db_path) == 99


def test_refusing_a_newer_database_releases_the_file_handle(db_path: Path) -> None:
    build_v1(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("UPDATE schema_meta SET version = 99 WHERE key='schema_version'")
    connection.commit()
    connection.close()

    with pytest.raises(store.SchemaVersionError):
        store.CampusStore(db_path)

    db_path.unlink()
    assert not db_path.exists()


def test_a_failing_migration_rolls_back_schema_version_and_ddl(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_v1(db_path)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setitem(store._MIGRATIONS, 2, _v2_explode)

    with pytest.raises(RuntimeError):
        store.CampusStore(db_path)

    assert stored_version(db_path) == 1
    assert "doomed" not in columns_of(db_path, "attempt")


def test_a_failing_migration_does_not_lose_existing_rows(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_v1(db_path)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setitem(store._MIGRATIONS, 2, _v2_explode)

    with pytest.raises(RuntimeError):
        store.CampusStore(db_path)

    monkeypatch.delitem(store._MIGRATIONS, 2)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 1)
    with store.CampusStore(db_path) as recovered:
        assert recovered.get("attempt", "a1") is not None


def test_degrade_level_column_is_nullable_integer(db_path: Path) -> None:
    build_v1(db_path)
    connection = sqlite3.connect(db_path)
    try:
        declared = {
            row[1]: (row[2], row[3])
            for row in connection.execute("PRAGMA table_info(attempt)")
        }
    finally:
        connection.close()
    assert declared["degrade_level"] == ("INTEGER", 0)
