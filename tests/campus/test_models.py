"""Unit tests for `ss.campus.models` — enums, row dataclasses and the static model list."""

from __future__ import annotations

import dataclasses
import sqlite3

import pytest

from ss.campus import models

EXPECTED_ENUM_VALUES: dict[str, list[str]] = {
    "TrackType": ["cet", "kaoyan", "cert", "other"],
    "CertType": ["teaching", "ncre", "law", "cpa", "other"],
    "CetLevel": ["cet4", "cet6"],
    "ProfileStatus": ["active", "archived", "finished"],
    "DegreeType": ["academic", "professional"],
    "DocFileType": ["pdf", "md", "txt"],
    "ParseStatus": ["pending", "ready", "failed"],
    "ChunkType": ["page", "section", "split"],
    "KnowledgeSource": ["manual", "ai_generated", "imported"],
    "MasteryLevel": ["unknown", "fuzzy", "mastered"],
    "MasteryDimension": ["concept", "listening", "reading", "writing", "translation"],
    "Subject": [
        "listening",
        "reading",
        "writing",
        "translation",
        "vocab",
        "politics",
        "english",
        "math",
        "major",
    ],
    "PlanTrack": ["overall", "politics", "english", "math", "major"],
    "PlanStage": ["foundation", "intensive", "pastpaper", "sprint"],
    "PlanSource": ["ai_generated", "manual"],
    "PlanTaskStatus": ["todo", "doing", "review", "done", "skipped"],
    "ExampleSource": ["past_paper", "ai"],
    "QuestionType": [
        "single",
        "multiple",
        "judge",
        "blank",
        "short_answer",
        "essay",
        "material",
        "lesson_plan",
        "practical",
    ],
    "QuestionSource": ["manual", "ai", "imported", "past_paper"],
    "SessionType": ["practice", "mock", "assessment", "grading"],
    "Attribution": [
        "concept_unclear",
        "misread",
        "calculation_or_operation",
        "out_of_scope",
        "time_short",
        "pending",
    ],
    "ReviewItemType": ["mistake", "vocab", "knowledge_point"],
    "ReviewStatus": ["pending", "done", "dropped"],
    "MockStage": ["writing", "listening", "reading_translation", "graded"],
    "MockStatus": ["ongoing", "submitted", "graded", "abandoned"],
    "AssessmentStatus": ["draft", "finished"],
    "DeadlineNodeType": [
        "registration_open",
        "registration_close",
        "payment_close",
        "admission_ticket",
        "exam",
        "score_query",
    ],
    "ReviewIntensity": ["light", "standard", "intense"],
    "CampusTask": ["grading", "question", "explain"],
}

EXPECTED_ROW_MODELS: dict[str, list[str]] = {
    "schema_meta": ["SchemaMeta"],
    "app_state": ["AppState"],
    "exam_profile": ["ExamProfile"],
    "school_profile": ["SchoolProfile"],
    "source_doc": ["SourceDoc"],
    "doc_chunk": ["DocChunk"],
    "knowledge_point": ["KnowledgePoint"],
    "mastery": ["Mastery"],
    "study_plan": ["StudyPlan"],
    "plan_task": ["PlanTask"],
    "vocab_item": ["VocabItem"],
    "question_bank_item": ["QuestionBankItem"],
    "attempt": ["Attempt"],
    "mistake_book": ["MistakeBookEntry"],
    "review_queue": ["ReviewItem"],
    "mock_exam": ["MockExam"],
    "assessment": ["Assessment"],
    "weekly_report": ["WeeklyReport"],
    "cert_deadline": ["CertDeadline"],
}


@pytest.mark.parametrize("enum_name", sorted(EXPECTED_ENUM_VALUES))
def test_enum_values_match_schema_doc(enum_name: str) -> None:
    enum_cls = getattr(models, enum_name)
    assert issubclass(enum_cls, str)
    assert [member.value for member in enum_cls] == EXPECTED_ENUM_VALUES[enum_name]


def test_all_enums_registered_in_all_enums() -> None:
    assert {cls.__name__ for cls in models.ALL_ENUMS} == set(EXPECTED_ENUM_VALUES)


def test_row_models_cover_the_nineteen_tables() -> None:
    assert set(models.ROW_MODELS) == set(EXPECTED_ROW_MODELS)
    assert len(models.ROW_MODELS) == 19
    for table, (cls_name,) in EXPECTED_ROW_MODELS.items():
        assert models.ROW_MODELS[table] is getattr(models, cls_name)


def test_str_enum_members_serialize_as_plain_values() -> None:
    assert models.TrackType.CET == "cet"
    assert f"{models.ParseStatus.READY}" == "ready"
    assert models.Attribution.from_value("misread") is models.Attribution.MISREAD


def test_from_value_rejects_unknown_member() -> None:
    with pytest.raises(ValueError):
        models.ParseStatus.from_value("done")
    with pytest.raises(ValueError):
        models.TrackType.from_value("CET")


def test_row_dataclasses_are_not_frozen_and_carry_schema_defaults() -> None:
    profile = models.ExamProfile(id="p1", track_type="cet", title="2026年12月 四级")
    assert profile.daily_minutes == 60
    assert profile.status == models.ProfileStatus.ACTIVE
    assert profile.subjects == "[]"
    profile.title = "改名"
    assert profile.title == "改名"
    assert models.PlanTask(id="t", plan_id="p", profile_id="p", title="x", subject="listening", scheduled_date="2026-09-14").priority == 2
    assert models.Attempt(id="a", profile_id="p", track_type="cet", subject="writing", user_answer="x").degrade_level is None


def test_every_row_model_is_a_dataclass_with_a_primary_key() -> None:
    for cls in models.ROW_MODELS.values():
        assert dataclasses.is_dataclass(cls)
        assert {"id", "key"} & {f.name for f in dataclasses.fields(cls)}
        assert hasattr(cls, "from_row")


def test_from_row_accepts_sqlite_row_and_mapping() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 'p1' AS id, 'cet' AS track_type, '标题' AS title").fetchone()
    from_mapping = models.ExamProfile.from_row(
        {"id": "p1", "track_type": "cet", "title": "标题"}
    )
    from_sqlite = models.ExamProfile.from_row(row)
    assert from_mapping == from_sqlite
    assert from_sqlite.id == "p1"
    assert from_sqlite.status == models.ProfileStatus.ACTIVE


def test_from_row_copies_every_declared_column_of_a_full_row() -> None:
    full = {
        "id": "p1",
        "track_type": "kaoyan",
        "title": "2027 考研",
        "cert_type": None,
        "level": None,
        "exam_date": "2026-12-19",
        "target_score": 380,
        "current_estimate": 350,
        "subjects": '["politics"]',
        "daily_minutes": 120,
        "status": "active",
        "created_at": "2026-09-14T00:00:00Z",
        "updated_at": "2026-09-14T00:00:00Z",
    }
    profile = models.ExamProfile.from_row(full)
    assert profile.exam_date == "2026-12-19"
    assert profile.target_score == 380
    assert profile.daily_minutes == 120


def test_from_row_tolerates_missing_columns() -> None:
    state = models.AppState.from_row({"key": "active_profile_id"})
    assert state.key == "active_profile_id"
    assert state.value is None
    assert state.updated_at is None


def test_from_row_rejects_none() -> None:
    with pytest.raises(ValueError):
        models.AppState.from_row(None)


def test_row_model_field_names_match_table_columns() -> None:
    for table, cls in models.ROW_MODELS.items():
        declared = {f.name for f in dataclasses.fields(cls)}
        assert declared == set(models.TABLE_COLUMNS[table]), table


def test_static_model_list_covers_every_campus_task() -> None:
    assert set(models.TASK_MODEL_CHOICES) == {task.value for task in models.CampusTask}
    for task, choice in models.TASK_MODEL_CHOICES.items():
        assert choice.task == task
        assert choice.recommended != choice.minimum


def test_static_model_list_ids_exist_in_the_provider_matrix() -> None:
    from ss.providers.matrix import MATRIX

    for choice in models.TASK_MODEL_CHOICES.values():
        assert choice.recommended in MATRIX, choice.recommended
        assert choice.minimum in MATRIX, choice.minimum


@pytest.mark.parametrize("kind", sorted(models.GRADING_KINDS))
def test_pick_routes_grading_kinds_to_the_grading_task(kind: str) -> None:
    recommended, minimum = models.pick(kind, "cet")
    assert (recommended, minimum) == models.pick_for_task(models.CampusTask.GRADING)


def test_pick_routes_unknown_kind_to_explain_task() -> None:
    assert models.pick("something-else") == models.pick_for_task(models.CampusTask.EXPLAIN)


def test_pick_accepts_track_type_for_signature_compatibility() -> None:
    assert models.pick("essay", None) == models.pick("essay", "kaoyan")


def test_pick_for_task_rejects_unknown_task() -> None:
    with pytest.raises(KeyError):
        models.pick_for_task("nope")
