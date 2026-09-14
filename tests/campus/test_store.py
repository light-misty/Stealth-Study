"""Unit tests for `ss.campus.store` — connection mode, 19 tables, WAL, locking and self-heal."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from ss.campus import models, store

EXPECTED_INDEXES = {
    "idx_profile_track",
    "idx_profile_status",
    "idx_school_profile",
    "idx_doc_profile",
    "idx_chunk_doc",
    "idx_chunk_profile",
    "idx_kp_profile_parent",
    "idx_mastery",
    "idx_mastery_level",
    "idx_plan_profile",
    "idx_task_profile_date",
    "idx_task_plan",
    "idx_task_status",
    "idx_vocab_word",
    "idx_vocab_mastery",
    "idx_qb_profile_point",
    "idx_qb_profile_type",
    "idx_attempt_profile_time",
    "idx_attempt_question",
    "idx_attempt_mock",
    "idx_mb_profile_resolved",
    "idx_mb_point",
    "idx_mb_track",
    "idx_rq_active",
    "idx_rq_due",
    "idx_mock_profile",
    "idx_asmt_profile",
    "idx_wr_week",
    "idx_cd_unique",
    "idx_cd_date",
}


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "campus.db"


@pytest.fixture()
def store_under_test(db_path: Path):
    instance = store.CampusStore(db_path)
    try:
        yield instance
    finally:
        instance.close()


def test_first_boot_creates_the_nineteen_tables(store_under_test) -> None:
    assert set(store_under_test.table_names()) == set(models.ROW_MODELS)
    assert len(store_under_test.table_names()) == 19


def test_first_boot_records_schema_version_one(store_under_test) -> None:
    assert store_under_test.current_version() == 1
    row = store_under_test.query_one("SELECT key, version, applied_at FROM schema_meta")
    assert row["key"] == "schema_version"
    assert row["version"] == 1
    assert row["applied_at"].endswith("Z")


def test_every_declared_index_is_created(store_under_test) -> None:
    created = set(store_under_test.index_names())
    assert EXPECTED_INDEXES <= created, sorted(EXPECTED_INDEXES - created)


def test_table_columns_match_the_declared_model_columns(store_under_test) -> None:
    for table, declared in models.TABLE_COLUMNS.items():
        actual = tuple(row["name"] for row in store_under_test.query_all(f"PRAGMA table_info({table})"))
        assert actual == declared, table


def test_foreign_key_enforcement_stays_off(store_under_test) -> None:
    assert store_under_test.scalar("PRAGMA foreign_keys") == 0


def test_journal_mode_is_wal(db_path: Path) -> None:
    instance = store.CampusStore(db_path)
    try:
        assert instance.scalar("PRAGMA journal_mode").lower() == "wal"
    finally:
        instance.close()


def test_review_queue_allows_only_one_pending_entry_per_item(store_under_test) -> None:
    pending = {
        "profile_id": "p1",
        "item_type": "mistake",
        "item_id": "m1",
        "due_at": "2026-09-15T00:00:00Z",
    }
    first = store_under_test.insert("review_queue", pending)
    assert first
    with pytest.raises(sqlite3.IntegrityError):
        store_under_test.insert("review_queue", pending)
    store_under_test.update("review_queue", first, {"status": "done"})
    assert store_under_test.insert("review_queue", pending)


def test_default_path_is_the_state_directory(db_path: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    instance = store.CampusStore()
    try:
        assert Path(instance.path) == tmp_path / "state" / "campus.db"
        assert Path(instance.path).is_file()
    finally:
        instance.close()


def test_parent_directory_is_created(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "deeper" / "campus.db"
    instance = store.CampusStore(nested)
    try:
        assert nested.is_file()
    finally:
        instance.close()


def test_new_id_is_a_thirty_two_character_hex_string(store_under_test) -> None:
    identifiers = {store.CampusStore.new_id() for _ in range(50)}
    assert len(identifiers) == 50
    for identifier in identifiers:
        assert len(identifier) == 32
        assert all(char in "0123456789abcdef" for char in identifier)


def test_deleting_the_database_and_reopening_self_heals(db_path: Path) -> None:
    first = store.CampusStore(db_path)
    try:
        first.insert(
            "exam_profile", {"id": "p1", "track_type": "cet", "title": "2026年12月 四级"}
        )
    finally:
        first.close()
    for suffix in ("", "-wal", "-shm"):
        artifact = Path(str(db_path) + suffix)
        if artifact.exists():
            artifact.unlink()

    second = store.CampusStore(db_path)
    try:
        assert set(second.table_names()) == set(models.ROW_MODELS)
        assert second.current_version() == 1
        assert second.get("exam_profile", "p1") is None
    finally:
        second.close()


def test_deleting_campus_db_leaves_the_kernel_database_untouched(db_path: Path) -> None:
    kernel_db = db_path.parent / "coworker.db"
    connection = sqlite3.connect(kernel_db)
    connection.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT)")
    connection.execute("INSERT INTO memories (content) VALUES ('用户听力篇章弱')")
    connection.commit()
    connection.close()
    before = kernel_db.read_bytes()
    before_mtime = kernel_db.stat().st_mtime

    instance = store.CampusStore(db_path)
    instance.insert("exam_profile", {"id": "p1", "track_type": "cet", "title": "四级"})
    instance.close()
    db_path.unlink()

    rebuilt = store.CampusStore(db_path)
    try:
        assert rebuilt.get("exam_profile", "p1") is None
    finally:
        rebuilt.close()
    assert kernel_db.read_bytes() == before
    assert kernel_db.stat().st_mtime == before_mtime


def test_concurrent_writes_are_serialised_by_the_lock(store_under_test) -> None:
    errors: list[BaseException] = []

    def writer(worker: int) -> None:
        try:
            for index in range(25):
                store_under_test.set_state(f"worker-{worker}-{index}", {"index": index})
        except BaseException as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(worker,)) for worker in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store_under_test.scalar("SELECT COUNT(*) FROM app_state") == 200


def test_concurrent_readers_and_writers_do_not_interleave_corruptly(store_under_test) -> None:
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader() -> None:
        try:
            while not stop.is_set():
                store_under_test.list_rows("exam_profile")
        except BaseException as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    def writer() -> None:
        try:
            for index in range(60):
                store_under_test.insert(
                    "exam_profile",
                    {"id": f"p{index}", "track_type": "cet", "title": f"档案{index}"},
                )
        except BaseException as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for thread in readers:
        thread.start()
    writer_thread = threading.Thread(target=writer)
    writer_thread.start()
    writer_thread.join()
    stop.set()
    for thread in readers:
        thread.join()

    assert errors == []
    assert store_under_test.scalar("SELECT COUNT(*) FROM exam_profile") == 60


def test_insert_stamps_id_and_timestamps(store_under_test) -> None:
    identifier = store_under_test.insert(
        "exam_profile", {"track_type": "cet", "title": "四级"}
    )
    row = store_under_test.get("exam_profile", identifier)
    assert row["id"] == identifier
    assert len(identifier) == 32
    assert row["created_at"].endswith("Z")
    assert row["updated_at"] == row["created_at"]
    assert row["status"] == "active"


def test_insert_rejects_unknown_tables_and_columns(store_under_test) -> None:
    with pytest.raises(ValueError):
        store_under_test.insert("nope", {"id": "x"})
    with pytest.raises(ValueError):
        store_under_test.insert("exam_profile", {"nope": 1})
    with pytest.raises(ValueError):
        store_under_test.columns("nope")


def test_update_refreshes_updated_at_and_reports_missing_rows(store_under_test) -> None:
    identifier = store_under_test.insert(
        "exam_profile", {"track_type": "cet", "title": "四级", "created_at": "2020-01-01T00:00:00Z"}
    )
    assert store_under_test.update("exam_profile", identifier, {"title": "六级"}) is True
    row = store_under_test.get("exam_profile", identifier)
    assert row["title"] == "六级"
    assert row["updated_at"] != "2020-01-01T00:00:00Z"
    assert store_under_test.update("exam_profile", "absent", {"title": "x"}) is False
    with pytest.raises(ValueError):
        store_under_test.update("exam_profile", identifier, {"nope": 1})


def test_delete_reports_whether_a_row_was_removed(store_under_test) -> None:
    identifier = store_under_test.insert(
        "exam_profile", {"track_type": "cet", "title": "四级"}
    )
    assert store_under_test.delete("exam_profile", identifier) is True
    assert store_under_test.delete("exam_profile", identifier) is False


def test_get_scoped_hides_rows_of_other_profiles(store_under_test) -> None:
    identifier = store_under_test.insert(
        "attempt",
        {
            "profile_id": "profile-a",
            "track_type": "cet",
            "subject": "writing",
            "user_answer": "作文",
        },
    )
    assert store_under_test.get_scoped("attempt", identifier, "profile-a") is not None
    assert store_under_test.get_scoped("attempt", identifier, "profile-b") is None


def test_profile_scoped_listing_filters_by_profile(store_under_test) -> None:
    for identifier, profile in (("a1", "profile-a"), ("a2", "profile-b")):
        store_under_test.insert(
            "attempt",
            {
                "id": identifier,
                "profile_id": profile,
                "track_type": "cet",
                "subject": "writing",
                "user_answer": "作文",
            },
        )
    rows = store_under_test.list_rows("attempt", profile_id="profile-a")
    assert [row["id"] for row in rows] == ["a1"]
    assert store_under_test.list_rows("attempt", profile_id="absent") == []


def test_profile_scoped_listing_requires_a_profile_id_column(store_under_test) -> None:
    with pytest.raises(ValueError):
        store_under_test.list_rows("exam_profile", profile_id="p1")


def test_list_rows_supports_ordering_and_paging(store_under_test) -> None:
    for index in range(5):
        store_under_test.insert(
            "exam_profile",
            {"id": f"p{index}", "track_type": "cet", "title": f"T{index}"},
        )
    rows = store_under_test.list_rows(
        "exam_profile", order_by="id DESC", limit=2, offset=1
    )
    assert [row["id"] for row in rows] == ["p3", "p2"]


def test_order_by_is_validated_against_the_table_columns(store_under_test) -> None:
    for bad in ("nope", "id; DROP TABLE exam_profile", "id DESC, nope", "id DESCENDING"):
        with pytest.raises(ValueError):
            store_under_test.list_rows("exam_profile", order_by=bad)


def test_queries_reject_unknown_tables(store_under_test) -> None:
    with pytest.raises(ValueError):
        store_under_test.list_rows("nope")
    with pytest.raises(ValueError):
        store_under_test.get("nope", "x")
    with pytest.raises(ValueError):
        store_under_test.delete("nope", "x")


def test_app_state_round_trips_json_values(store_under_test) -> None:
    store_under_test.set_state("campus_settings", {"daily_minutes": 90, "tasks": ["a", "b"]})
    store_under_test.set_state("active_profile_id", "p1")
    assert store_under_test.get_state("campus_settings") == {
        "daily_minutes": 90,
        "tasks": ["a", "b"],
    }
    assert store_under_test.get_state("active_profile_id") == "p1"
    assert store_under_test.get_state("missing") is None
    assert store_under_test.get_state("missing", default="fallback") == "fallback"


def test_set_state_upserts_and_refreshes_updated_at(store_under_test) -> None:
    store_under_test.set_state("k", 1, now="2020-01-01T00:00:00Z")
    store_under_test.set_state("k", 2, now="2021-01-01T00:00:00Z")
    assert store_under_test.get_state("k") == 2
    assert store_under_test.scalar("SELECT COUNT(*) FROM app_state WHERE key='k'") == 1
    assert store_under_test.query_one("SELECT updated_at FROM app_state WHERE key='k'")[
        "updated_at"
    ] == "2021-01-01T00:00:00Z"


def test_delete_state_reports_whether_a_key_was_removed(store_under_test) -> None:
    store_under_test.set_state("k", 1)
    assert store_under_test.delete_state("k") is True
    assert store_under_test.delete_state("k") is False


def test_transaction_rolls_back_every_statement_on_failure(store_under_test) -> None:
    with pytest.raises(RuntimeError):
        with store_under_test.transaction():
            store_under_test.insert(
                "exam_profile", {"id": "kept", "track_type": "cet", "title": "回滚"}
            )
            raise RuntimeError("boom")
    assert store_under_test.get("exam_profile", "kept") is None


def test_transaction_commits_on_success(store_under_test) -> None:
    with store_under_test.transaction():
        store_under_test.insert(
            "exam_profile", {"id": "committed", "track_type": "cet", "title": "提交"}
        )
    assert store_under_test.get("exam_profile", "committed") is not None


def test_nested_transactions_reuse_the_outer_one(store_under_test) -> None:
    with store_under_test.transaction():
        with store_under_test.transaction():
            store_under_test.insert(
                "exam_profile", {"id": "nested", "track_type": "cet", "title": "嵌套"}
            )
    assert store_under_test.get("exam_profile", "nested") is not None


def test_store_works_as_a_context_manager(db_path: Path) -> None:
    with store.CampusStore(db_path) as instance:
        assert instance.current_version() == 1
    with pytest.raises(sqlite3.ProgrammingError):
        instance.query_all("SELECT 1")


def test_close_is_idempotent(db_path: Path) -> None:
    instance = store.CampusStore(db_path)
    instance.close()
    instance.close()


def test_document_text_is_not_capped_like_conversation_attachments(store_under_test) -> None:
    from ss import attachments

    oversized = "知" * (attachments.MAX_TEXT_CHARS + 50_000)
    store_under_test.insert(
        "source_doc",
        {
            "id": "d1",
            "profile_id": "p1",
            "title": "775 页教材",
            "file_path": "library/p1/d1/book.pdf",
            "char_count": len(oversized),
            "parse_status": "ready",
            "imported_at": "2026-09-14T00:00:00Z",
        },
    )
    store_under_test.insert(
        "doc_chunk",
        {"id": "c1", "doc_id": "d1", "profile_id": "p1", "page_no": 1, "content": oversized},
    )

    assert store_under_test.get("doc_chunk", "c1")["content"] == oversized
    assert store_under_test.get("source_doc", "d1")["char_count"] == len(oversized)
    assert len(oversized) > attachments.MAX_TEXT_CHARS


def test_store_does_not_inherit_the_attachment_text_cap() -> None:
    source = Path(store.__file__).read_text(encoding="utf-8")
    assert "attachments" not in source
    assert "MAX_TEXT_CHARS" not in source
