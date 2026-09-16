"""I 组导出端点（03 §4.9 I4-I6、07 §4 T14、02 §7.1/§7.4）。

I4 把学习数据写成 `campus/exports/` 落盘文件：json 是全库备份包（02 §7.4"单 JSON 文档，
19 张表各一数组，schema_meta.version 一并写入"——schema_meta 表本身只以版本号字段承载），
md/csv 只覆盖请求档案的人读数据。I5 以附件下载回流文件，路径穿越由文件名白名单拦截。
I6 是 02 §7.1 的一键清除（删库删目录后重建空库），与 A10 共用同一清除实现。

验收标准（07 §4 T14）的测试化：
① 三格式导出可被重新导入且行数一致 —— json 包经 I6 恢复后逐表行数一致（本文件 + 恢复用例）；
② 低版本导出包导入时迁移提示 —— 恢复用例以注入的 v2 迁移演练 02 §3.5 场景；
③ 路径穿越防护 —— I5 与恢复入口的文件名白名单用例。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store
from ss.campus.config import load_campus_config
from ss.campus.service import CampusError, CampusService

ACTIVE_ID = "profile-export"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
BACKUP_KIND = "stealth-study-campus-backup"
DATA_TABLES = set(models.ROW_MODELS) - {"schema_meta"}


class FakeManager:
    def __init__(self, model: str = "fake:model") -> None:
        self.model = model

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": True, "models": [self.model]}


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    _seed_rich(instance)
    try:
        yield instance
    finally:
        instance.close()


def _seed_rich(instance: store.CampusStore) -> None:
    instance.insert(
        "exam_profile",
        {
            "id": ACTIVE_ID,
            "track_type": models.TrackType.CET.value,
            "title": "六级 12 月",
            "exam_date": "2026-12-19",
            "target_score": 500,
            "status": models.ProfileStatus.ACTIVE.value,
        },
    )
    instance.insert(
        "exam_profile",
        {
            "id": OTHER_ID,
            "track_type": models.TrackType.CERT.value,
            "title": "教资高中语文",
            "cert_type": models.CertType.TEACHING.value,
            "exam_date": "2027-03-14",
            "status": models.ProfileStatus.ACTIVE.value,
        },
    )
    instance.insert(
        "exam_profile",
        {
            "id": FINISHED_ID,
            "track_type": models.TrackType.CET.value,
            "title": "已结课",
            "status": models.ProfileStatus.FINISHED.value,
        },
    )
    instance.insert(
        "school_profile",
        {"id": "school-1", "profile_id": ACTIVE_ID, "school": "某某大学", "major": "英语"},
    )
    instance.insert(
        "source_doc",
        {
            "id": "doc-1",
            "profile_id": ACTIVE_ID,
            "title": "真题讲义.pdf",
            "file_path": "campus/library/x.pdf",
            "parse_status": models.ParseStatus.READY.value,
            "page_count": 2,
            "chunk_count": 2,
            "imported_at": "2026-09-01T08:00:00Z",
        },
    )
    for page_no in (1, 2):
        instance.insert(
            "doc_chunk",
            {
                "id": f"chunk-{page_no}",
                "doc_id": "doc-1",
                "profile_id": ACTIVE_ID,
                "page_no": page_no,
                "content": f"第 {page_no} 页内容",
            },
        )
    instance.insert(
        "knowledge_point", {"id": "kp-1", "profile_id": ACTIVE_ID, "title": "听力"}
    )
    instance.insert(
        "knowledge_point",
        {"id": "kp-2", "profile_id": ACTIVE_ID, "title": "长对话", "parent_id": "kp-1"},
    )
    instance.insert(
        "knowledge_point", {"id": "kp-9", "profile_id": OTHER_ID, "title": "教育学"}
    )
    instance.insert(
        "mastery",
        {
            "id": "mast-1",
            "profile_id": ACTIVE_ID,
            "point_id": "kp-1",
            "level": models.MasteryLevel.MASTERED.value,
        },
    )
    instance.insert(
        "mastery",
        {
            "id": "mast-2",
            "profile_id": ACTIVE_ID,
            "point_id": "kp-2",
            "level": models.MasteryLevel.UNKNOWN.value,
        },
    )
    instance.insert(
        "study_plan",
        {
            "id": "plan-1",
            "profile_id": ACTIVE_ID,
            "track": models.PlanTrack.ENGLISH.value,
            "stage": models.PlanStage.FOUNDATION.value,
            "start_date": "2026-09-01",
            "end_date": "2026-12-19",
        },
    )
    instance.insert(
        "plan_task",
        {
            "id": "task-1",
            "plan_id": "plan-1",
            "profile_id": ACTIVE_ID,
            "title": "精听一篇",
            "subject": models.Subject.LISTENING.value,
            "scheduled_date": "2026-09-02",
            "status": models.PlanTaskStatus.DONE.value,
            "completed_at": "2026-09-02T12:00:00Z",
        },
    )
    instance.insert(
        "plan_task",
        {
            "id": "task-2",
            "plan_id": "plan-1",
            "profile_id": ACTIVE_ID,
            "title": "背核心词",
            "subject": models.Subject.VOCAB.value,
            "scheduled_date": "2026-09-03",
        },
    )
    for vid, word, mastery in (("vocab-1", "persist", models.MasteryLevel.FUZZY.value), ("vocab-2", "ambiguity", models.MasteryLevel.UNKNOWN.value)):
        instance.insert(
            "vocab_item",
            {"id": vid, "profile_id": ACTIVE_ID, "word": word, "mastery": mastery},
        )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-obj",
            "profile_id": ACTIVE_ID,
            "subject": models.Subject.LISTENING.value,
            "stem": "What does the man mean?",
            "qtype": models.QuestionType.SINGLE.value,
            "options": json.dumps({"A": "He agrees.", "B": "He refuses."}, ensure_ascii=False),
            "answer": "A",
            "max_score": 1,
        },
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-essay",
            "profile_id": ACTIVE_ID,
            "subject": models.Subject.WRITING.value,
            "stem": "Write about the importance of reading.",
            "qtype": models.QuestionType.ESSAY.value,
            "max_score": 15,
        },
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-other",
            "profile_id": OTHER_ID,
            "subject": models.Subject.MAJOR.value,
            "stem": "简述教学原则。",
            "qtype": models.QuestionType.SHORT_ANSWER.value,
            "max_score": 8,
        },
    )
    instance.insert(
        "attempt",
        {
            "id": "att-obj",
            "profile_id": ACTIVE_ID,
            "track_type": models.TrackType.CET.value,
            "subject": models.Subject.LISTENING.value,
            "user_answer": "A",
            "question_id": "q-obj",
            "is_correct": 1,
            "score": 1,
            "max_score": 1,
        },
    )
    instance.insert(
        "attempt",
        {
            "id": "att-essay",
            "profile_id": ACTIVE_ID,
            "track_type": models.TrackType.CET.value,
            "subject": models.Subject.WRITING.value,
            "user_answer": "Reading matters.",
            "question_id": "q-essay",
            "session_type": models.SessionType.PRACTICE.value,
            "score": 11,
            "max_score": 15,
            "grading_json": json.dumps({"band": 11}, ensure_ascii=False),
            "degrade_level": 0,
            "model_used": "fake:model",
        },
    )
    instance.insert(
        "attempt",
        {
            "id": "att-other",
            "profile_id": OTHER_ID,
            "track_type": models.TrackType.CERT.value,
            "subject": models.Subject.MAJOR.value,
            "user_answer": "……",
            "question_id": "q-other",
        },
    )
    instance.insert(
        "mistake_book",
        {
            "id": "mist-1",
            "profile_id": ACTIVE_ID,
            "attempt_id": "att-essay",
            "track_type": models.TrackType.CET.value,
            "subject": models.Subject.WRITING.value,
            "question_id": "q-essay",
            "last_wrong_at": "2026-09-05T10:00:00Z",
        },
    )
    instance.insert(
        "review_queue",
        {
            "id": "rq-1",
            "profile_id": ACTIVE_ID,
            "item_type": models.ReviewItemType.VOCAB.value,
            "item_id": "vocab-2",
            "due_at": "2026-09-17T00:00:00Z",
        },
    )
    instance.insert(
        "mock_exam",
        {
            "id": "mock-1",
            "profile_id": ACTIVE_ID,
            "paper_title": "六级模考一",
            "started_at": "2026-09-06T09:00:00Z",
            "status": models.MockStatus.ONGOING.value,
        },
    )
    instance.insert(
        "assessment",
        {
            "id": "asmt-1",
            "profile_id": ACTIVE_ID,
            "started_at": "2026-09-01T10:00:00Z",
            "status": models.AssessmentStatus.FINISHED.value,
        },
    )
    instance.insert(
        "weekly_report",
        {
            "id": "wr-1",
            "profile_id": ACTIVE_ID,
            "week_start": "2026-08-31",
            "week_end": "2026-09-06",
            "content_md": "# 周报",
        },
    )
    instance.insert(
        "cert_deadline",
        {
            "id": "cd-1",
            "profile_id": OTHER_ID,
            "node_type": models.DeadlineNodeType.EXAM.value,
            "date": "2027-03-14",
        },
    )
    instance.set_state("active_profile_id", ACTIVE_ID)
    instance.set_state("campus_settings", {"daily_minutes": 90})


@pytest.fixture()
def client(manager: FakeManager, seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return TestClient(app)


@pytest.fixture()
def exports_dir() -> Any:
    return secrets.state_dir() / "campus" / "exports"


def _export(client: TestClient, fmt: str, profile_id: str = ACTIVE_ID):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/exports", json={"profile_id": profile_id, "format": fmt}
    )


def _detail(response) -> dict:
    return response.json()["detail"]


# -- fixtures used by the route layer -------------------------------------


@pytest.fixture()
def seeded_service(seeded_store: store.CampusStore) -> CampusService:
    return CampusService(seeded_store, load_campus_config())


# -- I4：导出落盘 ----------------------------------------------------------


def test_i4_json_export_is_a_full_database_package(
    client: TestClient, seeded_store: store.CampusStore, exports_dir: Any
) -> None:
    response = _export(client, "json")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"filename", "path"}
    assert body["filename"].endswith(".json")
    file = Path(body["path"])
    assert file == exports_dir / body["filename"]
    assert file.is_file()
    package = json.loads(file.read_text(encoding="utf-8"))
    assert package["kind"] == BACKUP_KIND
    assert package["schema_version"] == store.CURRENT_SCHEMA_VERSION
    assert set(package) == {"kind", "schema_version", "exported_at", "row_counts", "tables"}
    assert set(package["tables"]) == DATA_TABLES
    for table in DATA_TABLES:
        assert package["row_counts"][table] == seeded_store.count(table)
    profiles = {row["id"] for row in package["tables"]["exam_profile"]}
    assert profiles == {ACTIVE_ID, OTHER_ID, FINISHED_ID}


def test_i4_json_package_rows_keep_their_primary_keys(
    client: TestClient, seeded_store: store.CampusStore, exports_dir: Any
) -> None:
    body = _export(client, "json").json()
    package = json.loads((exports_dir / body["filename"]).read_text(encoding="utf-8"))
    attempt_rows = {row["id"]: row for row in package["tables"]["attempt"]}
    assert attempt_rows["att-essay"]["grading_json"] == json.dumps({"band": 11}, ensure_ascii=False)
    assert attempt_rows["att-essay"]["degrade_level"] == 0
    assert package["tables"]["app_state"]


def test_i4_md_export_reports_only_the_requested_profile(
    client: TestClient, exports_dir: Any
) -> None:
    response = _export(client, "md")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"].endswith(".md")
    text = (exports_dir / body["filename"]).read_text(encoding="utf-8")
    assert text.startswith("# 学习数据导出")
    assert "六级 12 月" in text
    assert "教资高中语文" not in text
    assert "## 知识点掌握" in text
    assert "## 学习进度" in text


def test_i4_csv_export_lists_the_attempt_log(
    client: TestClient, exports_dir: Any
) -> None:
    response = _export(client, "csv")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"].endswith(".csv")
    raw = (exports_dir / body["filename"]).read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header == (
        "id,created_at,track_type,subject,question_id,session_type,"
        "mock_exam_id,is_correct,score,max_score,degrade_level,model_used"
    )
    assert "att-obj" in text
    assert "att-essay" in text
    assert "att-other" not in text


def test_i4_refuses_an_undocumented_format(client: TestClient) -> None:
    response = _export(client, "xml")
    assert response.status_code == 422


def test_i4_validates_the_profile(client: TestClient) -> None:
    missing = client.post(f"{routes.CAMPUS_PREFIX}/exports", json={"format": "json"})
    assert missing.status_code == 400
    assert _detail(missing)["code"] == "PROFILE_REQUIRED"
    unknown = _export(client, "json", profile_id="no-such-profile")
    assert unknown.status_code == 404
    assert _detail(unknown)["code"] == "PROFILE_NOT_FOUND"


def test_i4_exports_a_finished_profile(client: TestClient) -> None:
    response = _export(client, "json", profile_id=FINISHED_ID)
    assert response.status_code == 200, response.text


def test_i4_filenames_never_collide(client: TestClient, exports_dir: Any) -> None:
    first = _export(client, "json").json()["filename"]
    second = _export(client, "json").json()["filename"]
    assert first != second
    assert (exports_dir / first).is_file() and (exports_dir / second).is_file()


# -- I5：附件下载 ----------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "media_prefix"),
    [("json", "application/json"), ("md", "text/markdown"), ("csv", "text/csv")],
)
def test_i5_downloads_the_file_as_an_attachment(
    client: TestClient, exports_dir: Any, fmt: str, media_prefix: str
) -> None:
    name = _export(client, fmt).json()["filename"]
    file = exports_dir / name
    response = client.get(f"{routes.CAMPUS_PREFIX}/exports/{name}")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-type"].startswith(media_prefix)
    assert response.content == file.read_bytes()


def test_i5_refuses_a_file_that_was_never_exported(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/exports/nope.json")
    assert response.status_code == 404
    assert _detail(response)["code"] == "EXPORT_NOT_FOUND"


@pytest.mark.parametrize(
    "filename",
    ["..\\campus.db", ".hidden.md", "campus.db", "backup.bak", "带空格.md", "站点.csv"],
)
def test_i5_filename_whitelist_blocks_non_export_names(
    client: TestClient, filename: str
) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/exports/{filename}")
    assert response.status_code == 404
    assert _detail(response)["code"] == "EXPORT_NOT_FOUND"


def test_service_layer_rejects_traversal_paths(
    seeded_store: store.CampusStore,
) -> None:
    service = CampusService(seeded_store, load_campus_config())
    for filename in ("../campus.db", "a/b.md", "..\\..\\coworker.db", "", "CON.md"):
        with pytest.raises(CampusError) as excinfo:
            service.resolve_export(filename)
        assert excinfo.value.code == "EXPORT_NOT_FOUND", filename


# -- I6：一键清除（02 §7.1） ----------------------------------------------

class _SoloWipe:
    """The wipe needs the single-handle reality of production (one CampusStore per process,
    test_mount.py): the seeding connection is closed before the request, and the assertions
    open their own connection afterwards."""

    def __init__(self, *, seed: Optional[Callable[[store.CampusStore], None]] = None) -> None:
        self.campus_db = secrets.state_dir() / "campus.db"
        seeder = store.CampusStore(self.campus_db)
        if seed is None:
            seeder.insert(
                "exam_profile",
                {
                    "id": ACTIVE_ID,
                    "track_type": models.TrackType.CET.value,
                    "title": "六级 12 月",
                },
            )
            seeder.set_state("active_profile_id", ACTIVE_ID)
        else:
            seed(seeder)
        seeder.close()

    def client(self) -> TestClient:
        app = FastAPI()
        app.include_router(routes.build_campus_router(FakeManager()))
        return TestClient(app)

    def verify(self) -> store.CampusStore:
        return store.CampusStore(self.campus_db)


def test_i6_wipes_the_database_and_the_campus_tree() -> None:
    harness = _SoloWipe()
    client = harness.client()
    export = client.post(
        f"{routes.CAMPUS_PREFIX}/exports", json={"profile_id": ACTIVE_ID, "format": "json"}
    )
    assert export.status_code == 200, export.text
    response = client.post(f"{routes.CAMPUS_PREFIX}/exports/wipe")
    assert response.status_code == 200, response.text
    assert response.json() == {"wiped": True}
    verifier = harness.verify()
    try:
        assert verifier.count("exam_profile") == 0
        assert verifier.count("app_state") == 0
        assert verifier.current_version() == store.CURRENT_SCHEMA_VERSION
    finally:
        verifier.close()
    root = secrets.state_dir()
    assert not (root / "campus" / "exports").exists()
    assert not (root / "campus" / "library").exists()
    assert (root / "campus.db").is_file()


def test_i6_wipe_is_repeatable() -> None:
    harness = _SoloWipe()
    client = harness.client()
    assert client.post(f"{routes.CAMPUS_PREFIX}/exports/wipe").status_code == 200
    assert client.post(f"{routes.CAMPUS_PREFIX}/exports/wipe").status_code == 200
    verifier = harness.verify()
    try:
        assert verifier.count("exam_profile") == 0
    finally:
        verifier.close()


# -- I6 恢复：INF-03 备份恢复（02 §7.4，I4 的逆过程） ----------------------


def _export_name(client: TestClient, fmt: str = "json") -> str:
    response = _export(client, fmt)
    assert response.status_code == 200, response.text
    return response.json()["filename"]


def _restore(client: TestClient, filename: str):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/exports/wipe", json={"restore_filename": filename}
    )


def _profile_count(verifier: store.CampusStore) -> int:
    try:
        return verifier.count("exam_profile")
    finally:
        verifier.close()


def test_i6_restore_round_trips_the_whole_database(exports_dir: Path) -> None:
    harness = _SoloWipe(seed=_seed_rich)
    client = harness.client()
    name = _export_name(client)
    package = json.loads((exports_dir / name).read_text(encoding="utf-8"))
    response = _restore(client, name)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["wiped"] is True
    assert body["schema_migration"] is None
    restored = body["restored"]
    assert restored["counts_match"] is True
    assert restored["rows"] == sum(package["row_counts"].values())
    assert restored["tables"] == package["row_counts"]
    verifier = harness.verify()
    for table, count in package["row_counts"].items():
        assert verifier.count(table) == count, table
    assert verifier.get_state("active_profile_id") == ACTIVE_ID
    assert _profile_count(verifier) == 3
    assert (exports_dir / name).is_file()


def test_i6_restore_reports_a_migration_for_an_older_package(
    monkeypatch: pytest.MonkeyPatch, exports_dir: Path
) -> None:
    harness = _SoloWipe(seed=_seed_rich)
    client = harness.client()
    name = _export_name(client)
    package = json.loads((exports_dir / name).read_text(encoding="utf-8"))
    assert package["schema_version"] == 1

    def _fake_v2(conn) -> None:
        conn.execute("ALTER TABLE app_state ADD COLUMN restore_note TEXT DEFAULT ''")

    monkeypatch.setitem(store._MIGRATIONS, 2, _fake_v2)
    monkeypatch.setattr(store, "CURRENT_SCHEMA_VERSION", 2)
    response = _restore(client, name)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_migration"] == {"from": 1, "to": 2}
    assert body["restored"]["counts_match"] is True
    verifier = harness.verify()
    try:
        assert verifier.current_version() == 2
        assert verifier.query_one('SELECT "restore_note" FROM "app_state"') is not None
    finally:
        verifier.close()


def test_i6_restore_refuses_a_newer_package_without_wiping(exports_dir: Path) -> None:
    harness = _SoloWipe(seed=_seed_rich)
    client = harness.client()
    name = _export_name(client)
    package = json.loads((exports_dir / name).read_text(encoding="utf-8"))
    package["schema_version"] = 99
    (exports_dir / "future.json").write_text(
        json.dumps(package, ensure_ascii=False), encoding="utf-8"
    )
    response = _restore(client, "future.json")
    assert response.status_code == 500, response.text
    assert _detail(response)["code"] == "SCHEMA_VERSION_ERROR"
    assert _profile_count(harness.verify()) == 3
    verifier = harness.verify()
    try:
        assert verifier.get_state("active_profile_id") == ACTIVE_ID
    finally:
        verifier.close()


@pytest.mark.parametrize(
    ("case", "status", "code"),
    [
        ("version_zero", 422, "PARSE_ERROR"),
        ("version_text", 422, "PARSE_ERROR"),
        ("unknown_table", 422, "PARSE_ERROR"),
        ("unknown_column", 422, "PARSE_ERROR"),
        ("missing_id", 422, "PARSE_ERROR"),
        ("row_not_object", 422, "PARSE_ERROR"),
        ("tables_missing", 422, "PARSE_ERROR"),
    ],
)
def test_i6_restore_refuses_malformed_packages_without_wiping(
    exports_dir: Path, case: str, status: int, code: str
) -> None:
    harness = _SoloWipe(seed=_seed_rich)
    client = harness.client()
    name = _export_name(client)
    package = json.loads((exports_dir / name).read_text(encoding="utf-8"))
    if case == "version_zero":
        package["schema_version"] = 0
    elif case == "version_text":
        package["schema_version"] = "one"
    elif case == "unknown_table":
        package["tables"]["bogus"] = []
    elif case == "unknown_column":
        package["tables"]["exam_profile"][0]["ghost"] = 1
    elif case == "missing_id":
        del package["tables"]["exam_profile"][0]["id"]
    elif case == "row_not_object":
        package["tables"]["exam_profile"] = ["not-a-row"]
    elif case == "tables_missing":
        del package["tables"]
    (exports_dir / "broken.json").write_text(
        json.dumps(package, ensure_ascii=False), encoding="utf-8"
    )
    response = _restore(client, "broken.json")
    assert response.status_code == status, response.text
    assert _detail(response)["code"] == code
    assert _profile_count(harness.verify()) == 3


def test_i6_restore_refuses_a_non_json_export(exports_dir: Path) -> None:
    harness = _SoloWipe(seed=_seed_rich)
    client = harness.client()
    name = _export_name(client, fmt="md")
    response = _restore(client, name)
    assert response.status_code == 422, response.text
    assert _detail(response)["code"] == "PARSE_ERROR"
    assert _profile_count(harness.verify()) == 3


@pytest.mark.parametrize("filename", ["ghost.json", "../campus.db", "bad\\name.json"])
def test_i6_restore_needs_an_existing_whitelisted_file(
    exports_dir: Path, filename: str
) -> None:
    harness = _SoloWipe(seed=_seed_rich)
    client = harness.client()
    response = _restore(client, filename)
    assert response.status_code == 404, response.text
    assert _detail(response)["code"] == "EXPORT_NOT_FOUND"
    assert _profile_count(harness.verify()) == 3


def test_i6_bare_wipe_accepts_an_empty_body(exports_dir: Path) -> None:
    harness = _SoloWipe()
    client = harness.client()
    response = client.post(f"{routes.CAMPUS_PREFIX}/exports/wipe", json={})
    assert response.status_code == 200, response.text
    assert response.json() == {"wiped": True}
    assert _profile_count(harness.verify()) == 0
