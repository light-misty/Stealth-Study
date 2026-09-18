"""`campus.db` — the connection, the 19 tables and the `schema_meta` migration runner.

The connection mode is copied from `ss/memory/sqlite_store.py:13-43` (`check_same_thread=False`
plus a single long-lived connection guarded by a `threading.RLock`), with one addition:
`PRAGMA journal_mode=WAL`, so a FastAPI handler writing while the GUI polls does not block
readers (02 §2.1).

Everything campus owns lives in one file: deleting `campus.db` (plus its `-wal`/`-shm`
siblings) and restarting rebuilds the schema, and no other component reads that path, so the
kernel's own database is never touched (02 §2.2, PRD §13-B6).

Schema changes are expressed as `_MIGRATIONS[target_version]` functions. A published entry is
never edited — a new version is appended instead — and a database written by a newer
application version refuses to start rather than degrading silently (02 §3.2).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..secrets import state_dir
from . import models

CURRENT_SCHEMA_VERSION = 2
SCHEMA_VERSION_KEY = "schema_version"

SCHEMA_META_DDL = """
CREATE TABLE IF NOT EXISTS "schema_meta" (
    "key" TEXT PRIMARY KEY,
    "version" INTEGER NOT NULL,
    "applied_at" TEXT NOT NULL
)
"""

_TABLE_DDL: dict[str, str] = {
    "app_state": """
        CREATE TABLE IF NOT EXISTS "app_state" (
            "key" TEXT PRIMARY KEY,
            "value" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "exam_profile": """
        CREATE TABLE IF NOT EXISTS "exam_profile" (
            "id" TEXT PRIMARY KEY,
            "track_type" TEXT NOT NULL,
            "title" TEXT NOT NULL,
            "cert_type" TEXT,
            "level" TEXT,
            "exam_date" TEXT,
            "target_score" INTEGER,
            "current_estimate" INTEGER,
            "subjects" TEXT DEFAULT '[]',
            "daily_minutes" INTEGER DEFAULT 60,
            "status" TEXT NOT NULL DEFAULT 'active',
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "school_profile": """
        CREATE TABLE IF NOT EXISTS "school_profile" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "school" TEXT DEFAULT '',
            "major" TEXT DEFAULT '',
            "degree_type" TEXT,
            "subjects" TEXT DEFAULT '[]',
            "enroll_count" INTEGER,
            "recommend_ratio" REAL,
            "past_scores" TEXT DEFAULT '[]',
            "books" TEXT DEFAULT '[]',
            "note" TEXT DEFAULT '',
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "source_doc": """
        CREATE TABLE IF NOT EXISTS "source_doc" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "title" TEXT NOT NULL,
            "file_path" TEXT NOT NULL,
            "file_type" TEXT NOT NULL DEFAULT 'pdf',
            "page_count" INTEGER DEFAULT 0,
            "parse_status" TEXT NOT NULL DEFAULT 'pending',
            "fail_reason" TEXT,
            "chunk_count" INTEGER DEFAULT 0,
            "char_count" INTEGER DEFAULT 0,
            "imported_at" TEXT NOT NULL
        )
    """,
    "doc_chunk": """
        CREATE TABLE IF NOT EXISTS "doc_chunk" (
            "id" TEXT PRIMARY KEY,
            "doc_id" TEXT NOT NULL,
            "profile_id" TEXT NOT NULL,
            "page_no" INTEGER NOT NULL,
            "content" TEXT NOT NULL,
            "chunk_type" TEXT NOT NULL DEFAULT 'page',
            "section_title" TEXT,
            "char_start" INTEGER DEFAULT 0,
            "char_end" INTEGER DEFAULT 0,
            "token_est" INTEGER DEFAULT 0,
            "created_at" TEXT NOT NULL
        )
    """,
    "knowledge_point": """
        CREATE TABLE IF NOT EXISTS "knowledge_point" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "title" TEXT NOT NULL,
            "parent_id" TEXT,
            "desc" TEXT,
            "order_index" INTEGER NOT NULL DEFAULT 0,
            "source" TEXT NOT NULL DEFAULT 'manual',
            "question_count" INTEGER NOT NULL DEFAULT 0,
            "mistake_count" INTEGER NOT NULL DEFAULT 0,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "mastery": """
        CREATE TABLE IF NOT EXISTS "mastery" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "level" TEXT NOT NULL DEFAULT 'unknown',
            "point_id" TEXT,
            "dimension" TEXT,
            "score_0_100" INTEGER,
            "evidence" TEXT DEFAULT '',
            "updated_at" TEXT NOT NULL
        )
    """,
    "study_plan": """
        CREATE TABLE IF NOT EXISTS "study_plan" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "track" TEXT,
            "stage" TEXT,
            "start_date" TEXT,
            "end_date" TEXT,
            "goal_desc" TEXT DEFAULT '',
            "source" TEXT NOT NULL DEFAULT 'ai_generated',
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "plan_task": """
        CREATE TABLE IF NOT EXISTS "plan_task" (
            "id" TEXT PRIMARY KEY,
            "plan_id" TEXT NOT NULL,
            "profile_id" TEXT NOT NULL,
            "title" TEXT NOT NULL,
            "subject" TEXT NOT NULL,
            "scheduled_date" TEXT NOT NULL,
            "detail" TEXT DEFAULT '',
            "est_minutes" INTEGER DEFAULT 30,
            "priority" INTEGER NOT NULL DEFAULT 2,
            "status" TEXT NOT NULL DEFAULT 'todo',
            "board_card_id" TEXT,
            "completed_at" TEXT,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "vocab_item": """
        CREATE TABLE IF NOT EXISTS "vocab_item" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "word" TEXT NOT NULL,
            "phonetic" TEXT DEFAULT '',
            "meaning" TEXT DEFAULT '',
            "example" TEXT DEFAULT '',
            "example_source" TEXT DEFAULT 'ai',
            "freq_rank" INTEGER,
            "mastery" TEXT NOT NULL DEFAULT 'unknown',
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "question_bank_item": """
        CREATE TABLE IF NOT EXISTS "question_bank_item" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "subject" TEXT NOT NULL,
            "stem" TEXT NOT NULL,
            "qtype" TEXT NOT NULL DEFAULT 'single',
            "point_id" TEXT,
            "options" TEXT,
            "answer" TEXT,
            "answer_meta" TEXT,
            "max_score" REAL NOT NULL DEFAULT 1,
            "difficulty" INTEGER,
            "source" TEXT NOT NULL DEFAULT 'manual',
            "doc_id" TEXT,
            "created_at" TEXT NOT NULL
        )
    """,
    "attempt": """
        CREATE TABLE IF NOT EXISTS "attempt" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "track_type" TEXT NOT NULL,
            "subject" TEXT NOT NULL,
            "user_answer" TEXT NOT NULL,
            "question_id" TEXT,
            "session_type" TEXT NOT NULL DEFAULT 'practice',
            "mock_exam_id" TEXT,
            "is_correct" INTEGER,
            "score" REAL,
            "max_score" REAL,
            "grading_json" TEXT,
            "degrade_level" INTEGER,
            "model_used" TEXT,
            "created_at" TEXT NOT NULL
        )
    """,
    "mistake_book": """
        CREATE TABLE IF NOT EXISTS "mistake_book" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "attempt_id" TEXT NOT NULL,
            "track_type" TEXT NOT NULL,
            "subject" TEXT NOT NULL,
            "question_id" TEXT,
            "point_id" TEXT,
            "attribution" TEXT NOT NULL DEFAULT 'pending',
            "attribution_confidence" REAL,
            "wrong_count" INTEGER NOT NULL DEFAULT 1,
            "last_wrong_at" TEXT NOT NULL,
            "resolved" INTEGER NOT NULL DEFAULT 0,
            "note" TEXT DEFAULT '',
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "review_queue": """
        CREATE TABLE IF NOT EXISTS "review_queue" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "item_type" TEXT NOT NULL,
            "item_id" TEXT NOT NULL,
            "due_at" TEXT NOT NULL,
            "interval_days" INTEGER NOT NULL DEFAULT 1,
            "streak_right" INTEGER NOT NULL DEFAULT 0,
            "ease" REAL NOT NULL DEFAULT 2.5,
            "status" TEXT NOT NULL DEFAULT 'pending',
            "last_reviewed_at" TEXT,
            "created_at" TEXT NOT NULL
        )
    """,
    "mock_exam": """
        CREATE TABLE IF NOT EXISTS "mock_exam" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "paper_title" TEXT NOT NULL,
            "started_at" TEXT NOT NULL,
            "current_stage" TEXT DEFAULT 'writing',
            "stage_deadline" TEXT,
            "paused_seconds" INTEGER NOT NULL DEFAULT 0,
            "locked_stages" TEXT NOT NULL DEFAULT '[]',
            "status" TEXT NOT NULL DEFAULT 'ongoing',
            "estimate_score" REAL,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
    "assessment": """
        CREATE TABLE IF NOT EXISTS "assessment" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "started_at" TEXT NOT NULL,
            "status" TEXT NOT NULL DEFAULT 'draft',
            "question_ids" TEXT NOT NULL DEFAULT '[]',
            "answers" TEXT NOT NULL DEFAULT '{}',
            "scores" TEXT,
            "finished_at" TEXT
        )
    """,
    "weekly_report": """
        CREATE TABLE IF NOT EXISTS "weekly_report" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "week_start" TEXT NOT NULL,
            "week_end" TEXT NOT NULL,
            "completion_rate" TEXT NOT NULL DEFAULT '{}',
            "top_mistake_points" TEXT NOT NULL DEFAULT '[]',
            "content_md" TEXT NOT NULL DEFAULT '',
            "suggestion" TEXT DEFAULT '',
            "created_at" TEXT NOT NULL
        )
    """,
    "cert_deadline": """
        CREATE TABLE IF NOT EXISTS "cert_deadline" (
            "id" TEXT PRIMARY KEY,
            "profile_id" TEXT NOT NULL,
            "node_type" TEXT NOT NULL,
            "date" TEXT NOT NULL,
            "is_reference" INTEGER NOT NULL DEFAULT 0,
            "automation_ids" TEXT NOT NULL DEFAULT '[]',
            "note" TEXT DEFAULT '',
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
    """,
}

_INDEX_DDL: tuple[str, ...] = (
    'CREATE INDEX IF NOT EXISTS "idx_profile_track" ON "exam_profile" ("track_type", "status")',
    'CREATE INDEX IF NOT EXISTS "idx_profile_status" ON "exam_profile" ("status")',
    'CREATE UNIQUE INDEX IF NOT EXISTS "idx_school_profile" ON "school_profile" ("profile_id")',
    'CREATE INDEX IF NOT EXISTS "idx_doc_profile" ON "source_doc" ("profile_id", "imported_at" DESC)',
    'CREATE INDEX IF NOT EXISTS "idx_chunk_doc" ON "doc_chunk" ("doc_id", "page_no")',
    'CREATE INDEX IF NOT EXISTS "idx_chunk_profile" ON "doc_chunk" ("profile_id", "doc_id")',
    'CREATE INDEX IF NOT EXISTS "idx_kp_profile_parent" ON "knowledge_point" ("profile_id", "parent_id", "order_index")',
    'CREATE UNIQUE INDEX IF NOT EXISTS "idx_mastery" ON "mastery" ("profile_id", "point_id", "dimension")',
    'CREATE INDEX IF NOT EXISTS "idx_mastery_level" ON "mastery" ("profile_id", "level")',
    'CREATE INDEX IF NOT EXISTS "idx_plan_profile" ON "study_plan" ("profile_id", "track", "stage")',
    'CREATE INDEX IF NOT EXISTS "idx_task_profile_date" ON "plan_task" ("profile_id", "scheduled_date", "priority")',
    'CREATE INDEX IF NOT EXISTS "idx_task_plan" ON "plan_task" ("plan_id")',
    'CREATE INDEX IF NOT EXISTS "idx_task_status" ON "plan_task" ("profile_id", "status")',
    'CREATE UNIQUE INDEX IF NOT EXISTS "idx_vocab_word" ON "vocab_item" ("profile_id", "word")',
    'CREATE INDEX IF NOT EXISTS "idx_vocab_mastery" ON "vocab_item" ("profile_id", "mastery")',
    'CREATE INDEX IF NOT EXISTS "idx_qb_profile_point" ON "question_bank_item" ("profile_id", "point_id")',
    'CREATE INDEX IF NOT EXISTS "idx_qb_profile_type" ON "question_bank_item" ("profile_id", "qtype")',
    'CREATE INDEX IF NOT EXISTS "idx_attempt_profile_time" ON "attempt" ("profile_id", "created_at" DESC)',
    'CREATE INDEX IF NOT EXISTS "idx_attempt_question" ON "attempt" ("question_id")',
    'CREATE INDEX IF NOT EXISTS "idx_attempt_mock" ON "attempt" ("mock_exam_id")',
    'CREATE INDEX IF NOT EXISTS "idx_mb_profile_resolved" ON "mistake_book" ("profile_id", "resolved", "last_wrong_at" DESC)',
    'CREATE INDEX IF NOT EXISTS "idx_mb_point" ON "mistake_book" ("point_id")',
    'CREATE INDEX IF NOT EXISTS "idx_mb_track" ON "mistake_book" ("track_type", "subject")',
    'CREATE UNIQUE INDEX IF NOT EXISTS "idx_rq_active" ON "review_queue" ("profile_id", "item_type", "item_id") WHERE "status" = \'pending\'',
    'CREATE INDEX IF NOT EXISTS "idx_rq_due" ON "review_queue" ("profile_id", "status", "due_at")',
    'CREATE INDEX IF NOT EXISTS "idx_mock_profile" ON "mock_exam" ("profile_id", "status")',
    'CREATE INDEX IF NOT EXISTS "idx_asmt_profile" ON "assessment" ("profile_id", "status")',
    'CREATE UNIQUE INDEX IF NOT EXISTS "idx_wr_week" ON "weekly_report" ("profile_id", "week_start")',
    'CREATE UNIQUE INDEX IF NOT EXISTS "idx_cd_unique" ON "cert_deadline" ("profile_id", "node_type")',
    'CREATE INDEX IF NOT EXISTS "idx_cd_date" ON "cert_deadline" ("profile_id", "date")',
)

_ORDER_DIRECTIONS = {"ASC", "DESC"}


class SchemaVersionError(RuntimeError):
    """`campus.db` was written by a newer application version and must not be downgraded."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _v1_initial_schema(conn: sqlite3.Connection) -> None:
    for statement in _TABLE_DDL.values():
        conn.execute(statement)
    for statement in _INDEX_DDL:
        conn.execute(statement)


def _v2_add_profile_archived_at(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(exam_profile)")}
    if "archived_at" not in columns:
        conn.execute('ALTER TABLE "exam_profile" ADD COLUMN "archived_at" TEXT')


_MIGRATIONS: dict[int, Any] = {1: _v1_initial_schema, 2: _v2_add_profile_archived_at}


class CampusStore:
    """Single-process, lock-guarded handle on `campus.db`.

    All reads and writes take the reentrant lock, so the FastAPI handlers and the pollers
    that share one instance cannot interleave half-applied statements (02 §2.1).
    """

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = str(path if path is not None else (state_dir() / "campus.db"))
        Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._depth = 0
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
        try:
            self.migrate()
        except Exception:
            self._conn.close()
            raise

    def __enter__(self) -> "CampusStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    @staticmethod
    def new_id() -> str:
        """A fresh primary key: `uuid4().hex`, 32 lowercase hex characters (02 §1.3)."""
        return uuid.uuid4().hex

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def wipe(self, *, target: Optional[int] = None) -> int:
        """Delete `campus.db` and rebuild an empty schema, returning the bytes freed (02 §7.1).

        The connection is closed before the files go and reopened after, so this object stays
        the single handle the rest of the application shares (02 §2.1) and nothing has to be
        re-wired after a wipe. `-wal`/`-shm` siblings and the pre-migration backups
        (`campus.db.bak-v*`, 02 §3.3) go with the database; no file outside campus's own set is
        touched, and a wipe requested from inside an open transaction is refused rather than
        leaving a half-applied one behind. The optional `target` (T14's restore path, 02 §7.4)
        rebuilds at exactly that schema version instead of the current one, so a restore can
        replay an older export into its own era and then migrate forward through the real
        migration chain.
        """
        with self._lock:
            if self._depth:
                raise RuntimeError("cannot wipe campus.db inside an open transaction")
            self._conn.close()
            freed = 0
            for path in self._database_paths():
                if os.path.isfile(path):
                    freed += os.path.getsize(path)
                    os.remove(path)
            self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
            if target is None:
                self.migrate()
            else:
                self._rebuild_schema(target)
            return freed

    def _rebuild_schema(self, target: int) -> None:
        """Build the empty schema of exactly `target`, stamping it into `schema_meta`.

        The restore path needs the database of the export's own version — replaying a v1
        package straight into a v2 schema would silently skip the data work the v2 migration
        exists to do — so the rebuild runs the migration chain from nothing instead of
        `migrate()`'s stored-version jump, and no backup is taken because the database was
        just destroyed on purpose.
        """
        if target not in _MIGRATIONS or not 1 <= target <= CURRENT_SCHEMA_VERSION:
            raise ValueError(f"cannot rebuild campus.db at schema v{target}")
        self._conn.execute(SCHEMA_META_DDL)
        self._conn.execute("BEGIN")
        try:
            for version in range(1, target + 1):
                _MIGRATIONS[version](self._conn)
            self._conn.execute(
                "INSERT INTO schema_meta (key, version, applied_at) VALUES (?, ?, ?)",
                (SCHEMA_VERSION_KEY, target, _utcnow()),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _database_paths(self) -> list[str]:
        """The database plus every file sqlite keeps beside it."""
        parent = Path(self.path).parent
        backups = sorted(str(path) for path in parent.glob(f"{Path(self.path).name}.bak-v*"))
        return [self.path, f"{self.path}-wal", f"{self.path}-shm", *backups]

    def database_bytes(self) -> int:
        """The on-disk footprint of the database, siblings included (A9)."""
        return sum(os.path.getsize(path) for path in self._database_paths() if os.path.isfile(path))

    def migrate(self) -> int:
        """Bring the database up to `CURRENT_SCHEMA_VERSION`, returning that version."""
        with self._lock:
            self._conn.execute(SCHEMA_META_DDL)
            stored = self.current_version()
            if stored > CURRENT_SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"campus.db schema v{stored} is newer than this app's "
                    f"v{CURRENT_SCHEMA_VERSION}; refusing to start"
                )
            for target in range(stored + 1, CURRENT_SCHEMA_VERSION + 1):
                self._backup_before(target, stored=stored)
                try:
                    self._conn.execute("BEGIN")
                    _MIGRATIONS[target](self._conn)
                    self._conn.execute(
                        "INSERT INTO schema_meta (key, version, applied_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET version=excluded.version, "
                        "applied_at=excluded.applied_at",
                        (SCHEMA_VERSION_KEY, target, _utcnow()),
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
            return CURRENT_SCHEMA_VERSION

    def current_version(self) -> int:
        """The version recorded in `schema_meta`, or 0 before the first migration."""
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT version FROM schema_meta WHERE key = ?", (SCHEMA_VERSION_KEY,)
                ).fetchone()
            except sqlite3.OperationalError:
                return 0
            return int(row["version"]) if row else 0

    def table_names(self) -> list[str]:
        return [
            row["name"]
            for row in self._query_all(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

    def index_names(self) -> list[str]:
        return [
            row["name"]
            for row in self._query_all(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

    def columns(self, table: str) -> tuple[str, ...]:
        """The declared columns of `table`, rejecting anything not in `models.ROW_MODELS`."""
        try:
            return models.TABLE_COLUMNS[table]
        except KeyError as exc:
            raise ValueError(f"unknown campus table: {table}") from exc

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run one statement; commits immediately unless a transaction is open."""
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            if self._depth == 0:
                self._conn.commit()
            return cursor

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.executemany(sql, rows)
            if self._depth == 0:
                self._conn.commit()
            return cursor

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self._query_all(sql, params)

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return row[0] if row is not None else None

    def _query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    @contextmanager
    def transaction(self) -> Iterator["CampusStore"]:
        """Group statements atomically; nested blocks join the outermost transaction."""
        with self._lock:
            self._depth += 1
            try:
                if self._depth == 1:
                    self._conn.execute("BEGIN")
                yield self
                if self._depth == 1:
                    self._conn.execute("COMMIT")
            except Exception:
                if self._depth == 1:
                    self._conn.execute("ROLLBACK")
                raise
            finally:
                self._depth -= 1

    def insert(self, table: str, values: Mapping[str, Any]) -> str:
        """Insert one row, stamping `id` and the audit columns when they are not supplied."""
        columns = self.columns(table)
        row = dict(values)
        if "id" in columns and not row.get("id"):
            row["id"] = self.new_id()
        now = _utcnow()
        for stamp in ("created_at", "updated_at"):
            if stamp in columns and not row.get(stamp):
                row[stamp] = now
        self._check_columns(table, row, columns)
        if not row:
            raise ValueError(f"{table}: nothing to insert")
        names = ", ".join(f'"{name}"' for name in row)
        placeholders = ", ".join("?" for _ in row)
        self.execute(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', tuple(row.values()))
        return str(row.get("id", ""))

    def update(self, table: str, row_id: str, values: Mapping[str, Any]) -> bool:
        """Update one row by primary key, refreshing `updated_at`."""
        columns = self.columns(table)
        row = {key: value for key, value in values.items() if key != "id"}
        if "updated_at" in columns and "updated_at" not in row:
            row["updated_at"] = _utcnow()
        self._check_columns(table, row, columns)
        if not row:
            raise ValueError(f"{table}: nothing to update")
        assignments = ", ".join(f'"{name}" = ?' for name in row)
        cursor = self.execute(
            f'UPDATE "{table}" SET {assignments} WHERE "id" = ?', (*row.values(), row_id)
        )
        return cursor.rowcount > 0

    def delete(self, table: str, row_id: str) -> bool:
        self.columns(table)
        return self.execute(f'DELETE FROM "{table}" WHERE "id" = ?', (row_id,)).rowcount > 0

    def delete_where(self, table: str, where: str, params: Sequence[Any] = ()) -> int:
        self.columns(table)
        return self.execute(f'DELETE FROM "{table}" WHERE {where}', params).rowcount

    def count(self, table: str, where: str = "", params: Sequence[Any] = ()) -> int:
        self.columns(table)
        clause = f" WHERE {where}" if where else ""
        return int(self.scalar(f'SELECT COUNT(*) FROM "{table}"{clause}', params) or 0)

    def get(self, table: str, row_id: str) -> Optional[sqlite3.Row]:
        self.columns(table)
        return self.query_one(f'SELECT * FROM "{table}" WHERE "id" = ?', (row_id,))

    def get_scoped(self, table: str, row_id: str, profile_id: str) -> Optional[sqlite3.Row]:
        """Fetch a row only when it belongs to `profile_id`.

        Returns `None` for another profile's row, which is what turns a cross-profile read
        into `FORBIDDEN_PROFILE` instead of a silent leak (08 §4 P-3).
        """
        self.columns(table)
        return self.query_one(
            f'SELECT * FROM "{table}" WHERE "id" = ? AND "profile_id" = ?',
            (row_id, profile_id),
        )

    def list_rows(
        self,
        table: str,
        *,
        profile_id: Optional[str] = None,
        where: Optional[str] = None,
        params: Sequence[Any] = (),
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[sqlite3.Row]:
        """List rows, optionally scoped to one profile.

        Passing `profile_id` is the enforced form of the cross-cutting rule in 01 §3: it is
        rejected for tables that have no `profile_id` column, so a caller cannot believe it
        filtered when it did not.
        """
        columns = self.columns(table)
        conditions: list[str] = []
        values: list[Any] = []
        if profile_id is not None:
            if "profile_id" not in columns:
                raise ValueError(f"{table} has no profile_id column")
            conditions.append('"profile_id" = ?')
            values.append(profile_id)
        if where:
            conditions.append(f"({where})")
            values.extend(params)
        sql = f'SELECT * FROM "{table}"'
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        if order_by:
            sql += " ORDER BY " + self._compile_order_by(order_by, columns)
        if limit is not None:
            sql += " LIMIT ?"
            values.append(int(limit))
            if offset is not None:
                sql += " OFFSET ?"
                values.append(int(offset))
        return self.query_all(sql, values)

    def get_state(self, key: str, default: Any = None) -> Any:
        """Read a JSON-encoded `app_state` value."""
        row = self.query_one("SELECT value FROM app_state WHERE key = ?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set_state(self, key: str, value: Any, now: Optional[str] = None) -> None:
        """Write a JSON-encoded `app_state` value, creating the key when it is new."""
        self.execute(
            "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), now or _utcnow()),
        )

    def delete_state(self, key: str) -> bool:
        return self.execute("DELETE FROM app_state WHERE key = ?", (key,)).rowcount > 0

    def _check_columns(
        self, table: str, row: Mapping[str, Any], columns: Sequence[str]
    ) -> None:
        unknown = sorted(set(row) - set(columns))
        if unknown:
            raise ValueError(f"{table}: unknown columns {unknown}")

    def _compile_order_by(self, order_by: str, columns: Sequence[str]) -> str:
        """Compile an `order_by` clause, accepting declared columns plus `rowid`.

        `rowid` is SQLite's insertion counter and is the only stable tie-breaker for rows written
        in the same second (`created_at` has second precision, 02 §1.3): without it, two attempts
        stored back to back can swap places between pages. It is a real column of every campus
        table (none is declared `WITHOUT ROWID`), it never appears in a row dataclass, and every
        other name still has to be a declared column.
        """
        compiled: list[str] = []
        for clause in order_by.split(","):
            tokens = clause.split()
            if not tokens or (tokens[0] not in columns and tokens[0] != "rowid"):
                raise ValueError(f"unknown order column: {clause.strip()!r}")
            if len(tokens) > 2:
                raise ValueError(f"bad order clause: {clause.strip()!r}")
            if len(tokens) == 2:
                direction = tokens[1].upper()
                if direction not in _ORDER_DIRECTIONS:
                    raise ValueError(f"bad order direction: {clause.strip()!r}")
                compiled.append(f'"{tokens[0]}" {direction}')
            else:
                compiled.append(f'"{tokens[0]}"')
        return ", ".join(compiled)

    def _backup_before(self, target: int, *, stored: int) -> None:
        """Copy the current database aside before a migration runs (02 §3.3).

        Named after the version being left behind (`campus.db.bak-v1` when moving 1 -> 2).
        `stored == 0` is a first install building the chain from nothing, which has nothing to
        preserve, and `:memory:` has no file to copy.
        """
        if target <= 1 or stored < 1 or not os.path.isfile(self.path):
            return
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(self.path, f"{self.path}.bak-v{target - 1}")
