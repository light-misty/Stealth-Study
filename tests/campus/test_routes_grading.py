"""C1 共享批改端点与 CERT-15 服务端掌握度降级（03 §4.3/§4.8、07 §4 T12 验收②）。

C1 是 CET/KY/CERT 三台共用的主观题批改入口：落 `attempt`（失败也保留）→ 同步走
T07 批改链 → 响应体为 03 §4.3 的 GradeResult 视图 + `attempt_id`（另附
`grading_json`/`band`/`scoring_points` 等 attempt 列，前端得分点三态直接可用）。
CERT-15 是 C1/E5 批改链的服务端副作用：未命中（miss）得分点把关联知识点的掌握度
在同一次事务里降一档（mastered→fuzzy→unknown），树中即标记"待加强"。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store
from ss.campus.rubrics import CERT_SCORING_POINTS_SPEC, CET_ESSAY_RUBRIC

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"


def essay_payload(band: int = 11, content: int = 4, structure: int = 4, language: int = 3) -> str:
    return json.dumps(
        {
            "band": band,
            "dimension_scores": {"content": content, "structure": structure, "language": language},
            "errors": [{"fragment": "I thinks", "suggestion": "I think", "type": "主谓一致"}],
            "upgraded_demo": "rewritten",
            "model_answer_outline": "outline",
        }
    )


def scoring_payload(*statuses: str) -> str:
    return json.dumps(
        {
            "scoring_points": [
                {"point": f"得分点{index}", "status": status, "note": ""}
                for index, status in enumerate(statuses, start=1)
            ],
            "overall_score": 6,
            "model_answer_outline": "outline",
        }
    )


class FakeProvider:
    """按调用序号回放文本的 provider（`ProviderClient.complete` 的假实现）。"""

    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses or {"default": essay_payload()}
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    """The slice of `SessionManager` campus reads."""

    def __init__(
        self,
        model: str = "fake:model",
        *,
        ready: bool = True,
        provider: FakeProvider | None = None,
    ) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "model_ready": self._ready,
            "models": [self.model] if self.model else [],
        }


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture()
def seeded_store(campus_db_path: Path) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "教资高中语文"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.CERT.value,
                "title": title,
                "status": status,
            },
        )
    instance.insert(
        "knowledge_point",
        {"id": "p-1", "profile_id": ACTIVE_ID, "title": "德育"},
    )
    instance.insert(
        "knowledge_point",
        {"id": "p-2", "profile_id": ACTIVE_ID, "title": "教学原则"},
    )
    instance.insert(
        "knowledge_point",
        {"id": "p-3", "profile_id": ACTIVE_ID, "title": "学习动机"},
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-essay",
            "profile_id": ACTIVE_ID,
            "subject": "综合素质",
            "stem": "写一段议论文",
            "qtype": models.QuestionType.ESSAY.value,
            "max_score": 15,
        },
    )
    for point_id, question_id in (
        ("p-1", "q-p1"),
        ("p-2", "q-p2"),
        ("p-3", "q-p3"),
    ):
        instance.insert(
            "question_bank_item",
            {
                "id": question_id,
                "profile_id": ACTIVE_ID,
                "subject": "教育知识与能力",
                "stem": f"简答：{point_id}",
                "qtype": models.QuestionType.SHORT_ANSWER.value,
                "point_id": point_id,
                "max_score": 8,
            },
        )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-nopoint",
            "profile_id": ACTIVE_ID,
            "subject": "教育知识与能力",
            "stem": "简答：无知识点",
            "qtype": models.QuestionType.SHORT_ANSWER.value,
        },
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-foreign",
            "profile_id": OTHER_ID,
            "subject": "综合素质",
            "stem": "他人题目",
            "qtype": models.QuestionType.ESSAY.value,
        },
    )
    instance.insert(
        "mastery",
        {
            "id": "mast-p1",
            "profile_id": ACTIVE_ID,
            "point_id": "p-1",
            "level": models.MasteryLevel.MASTERED.value,
        },
    )
    instance.insert(
        "mastery",
        {
            "id": "mast-p2",
            "profile_id": ACTIVE_ID,
            "point_id": "p-2",
            "level": models.MasteryLevel.FUZZY.value,
        },
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(manager: FakeManager, seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return TestClient(app)


def _prefix() -> str:
    return routes.CAMPUS_PREFIX


def _detail(response) -> dict:
    return response.json()["detail"]


def _grade(client: TestClient, **overrides):
    payload = {
        "profile_id": ACTIVE_ID,
        "kind": "short_answer",
        "answer": "德育原则是……",
    }
    payload.update(overrides)
    return client.post(f"{_prefix()}/grading", json=payload)


# ---------------------------------------------------------------------------
# C1 — 批改主链与响应形状
# ---------------------------------------------------------------------------


def test_c1_grades_an_essay_into_the_documented_shape(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    response = _grade(
        client, kind="essay", question_id="q-essay", answer="I thinks it is good."
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attempt_id"] == seeded_store.get("attempt", body["attempt_id"])["id"]
    assert body["degrade_level"] == 0
    assert body["rubric"] == "四六级短文写作评分标准"
    assert body["dimensions"] == [
        {"name": "内容", "score": 4, "max": 5, "comment": ""},
        {"name": "结构", "score": 4, "max": 5, "comment": ""},
        {"name": "语言", "score": 3, "max": 5, "comment": ""},
    ]
    assert body["errors"] == [
        {"original": "I thinks", "suggestion": "I think", "type": "主谓一致", "offset": None}
    ]
    assert body["model_answer_outline"] == "outline"
    assert body["model_used"] == "fake:model"
    assert body["notice"] is None
    assert body["band"] == 11
    assert body["score"] == 11
    assert body["max_score"] == 15
    assert body["grading_json"]["band"] == 11
    assert manager.provider.seen[0]["settings"]["temperature"] == 0
    assert manager.provider.seen[0]["settings"]["timeout"] == 90


def test_c1_records_a_grading_session_attempt_with_the_question(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    body = _grade(
        client, kind="essay", question_id="q-essay", answer="essay"
    ).json()
    row = seeded_store.get("attempt", body["attempt_id"])
    assert row["question_id"] == "q-essay"
    assert row["subject"] == "综合素质"
    assert row["session_type"] == models.SessionType.GRADING.value
    assert row["degrade_level"] == 0


def test_c1_without_a_question_still_lands_the_attempt(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    body = _grade(client, kind="short_answer", answer="答：……").json()
    row = seeded_store.get("attempt", body["attempt_id"])
    assert row["question_id"] is None
    assert row["subject"] == "general"
    assert row["track_type"] == models.TrackType.CERT.value
    assert row["user_answer"] == "答：……"


def test_c1_returns_scoring_points_for_cert_kinds(
    client: TestClient, manager: FakeManager
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("hit", "miss")})
    body = _grade(client, question_id="q-p1", answer="……").json()
    statuses = [point["status"] for point in body["scoring_points"]]
    assert statuses == ["hit", "miss"]


def test_c1_uses_the_named_rubric_text(client: TestClient, manager: FakeManager) -> None:
    _grade(client, kind="essay", question_id="q-essay", answer="essay", rubric_id="cet_essay")
    system = manager.provider.seen[0]["messages"][0]["content"]
    assert CET_ESSAY_RUBRIC in system


def test_c1_cert_kinds_grade_against_the_scoring_contract(
    client: TestClient, manager: FakeManager
) -> None:
    _grade(client, question_id="q-p1", answer="……")
    system = manager.provider.seen[0]["messages"][0]["content"]
    assert CERT_SCORING_POINTS_SPEC in system


def test_c1_custom_rubric_replaces_the_text(client: TestClient, manager: FakeManager) -> None:
    body = _grade(
        client,
        question_id="q-p1",
        answer="……",
        custom_rubric="只看论证是否引用原文，三档评分",
    ).json()
    system = manager.provider.seen[0]["messages"][0]["content"]
    assert "只看论证是否引用原文，三档评分" in system
    assert body["rubric"] == "自定义评分标准"


def test_c1_rejects_an_unknown_rubric_id(client: TestClient, seeded_store: store.CampusStore) -> None:
    response = _grade(client, rubric_id="no-such-rubric", answer="……")
    assert response.status_code == 404
    assert _detail(response)["code"] == "RUBRIC_NOT_FOUND"
    assert seeded_store.count("attempt", "profile_id = ?", (ACTIVE_ID,)) == 0


def test_c1_keeps_the_attempt_when_the_model_times_out(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": TimeoutError("upstream timeout")})
    response = _grade(client, question_id="q-p1", answer="……")
    assert response.status_code == 504
    assert _detail(response)["code"] == "MODEL_TIMEOUT"
    rows = seeded_store.list_rows("attempt", profile_id=ACTIVE_ID)
    assert len(rows) == 1
    assert rows[0]["degrade_level"] == 3


def test_c1_rejects_an_unknown_kind(client: TestClient) -> None:
    response = _grade(client, kind="poem", answer="……")
    assert response.status_code == 422


def test_c1_rejects_a_blank_answer(client: TestClient) -> None:
    assert _grade(client, answer="   ").status_code == 422


def test_c1_rejects_unknown_body_fields(client: TestClient) -> None:
    assert _grade(client, answer_meta={"x": 1}).status_code == 422


def test_c1_refuses_without_a_configured_model(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(model="", ready=False)))
    client = TestClient(app)
    payload = {"profile_id": ACTIVE_ID, "kind": "short_answer", "answer": "……"}
    response = client.post(f"{routes.CAMPUS_PREFIX}/grading", json=payload)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"
    assert seeded_store.count("attempt", "profile_id = ?", (ACTIVE_ID,)) == 0


# ---------------------------------------------------------------------------
# C1 — 守卫与契约
# ---------------------------------------------------------------------------


def test_c1_rejects_a_missing_question(client: TestClient) -> None:
    response = _grade(client, question_id="no-such-question")
    assert response.status_code == 404
    assert _detail(response)["code"] == "QUESTION_NOT_FOUND"


def test_c1_rejects_a_foreign_question(client: TestClient) -> None:
    response = _grade(client, question_id="q-foreign")
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_c1_refuses_a_finished_profile(client: TestClient) -> None:
    response = _grade(client, profile_id=FINISHED_ID, answer="……")
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_c1_requires_a_profile(client: TestClient) -> None:
    response = client.post(
        f"{_prefix()}/grading", json={"kind": "short_answer", "answer": "……"}
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# CERT-15 — 未命中得分点降级掌握度（服务端副作用，单事务）
# ---------------------------------------------------------------------------


def test_cert15_downgrades_mastered_to_fuzzy_on_a_miss(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("hit", "miss")})
    _grade(client, question_id="q-p1", answer="……").json()
    row = seeded_store.get("mastery", "mast-p1")
    assert row["level"] == models.MasteryLevel.FUZZY.value
    assert "得分点2" in row["evidence"]


def test_cert15_downgrades_fuzzy_to_unknown(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("miss")})
    _grade(client, question_id="q-p2", answer="……").json()
    row = seeded_store.get("mastery", "mast-p2")
    assert row["level"] == models.MasteryLevel.UNKNOWN.value


def test_cert15_creates_an_unknown_row_when_none_exists(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("hit", "miss")})
    _grade(client, question_id="q-p3", answer="……").json()
    rows = seeded_store.list_rows(
        "mastery", profile_id=ACTIVE_ID, where='"point_id" = ?', params=["p-3"]
    )
    assert len(rows) == 1
    assert rows[0]["level"] == models.MasteryLevel.UNKNOWN.value
    assert rows[0]["dimension"] is None
    assert "得分点2" in rows[0]["evidence"]


def test_cert15_leaves_mastery_alone_when_everything_hits(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("hit", "partial")})
    _grade(client, question_id="q-p1", answer="……").json()
    row = seeded_store.get("mastery", "mast-p1")
    assert row["level"] == models.MasteryLevel.MASTERED.value
    assert row["evidence"] == ""


def test_cert15_ignores_a_question_without_a_point(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("miss")})
    before = seeded_store.count("mastery", "profile_id = ?", (ACTIVE_ID,))
    _grade(client, question_id="q-nopoint", answer="……").json()
    assert seeded_store.count("mastery", "profile_id = ?", (ACTIVE_ID,)) == before


def test_cert15_runs_for_e5_subjective_grading_too(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("hit", "miss")})
    response = client.post(
        f"{_prefix()}/attempts",
        json={
            "profile_id": ACTIVE_ID,
            "question_id": "q-p1",
            "answer": "德育原则是……",
        },
    )
    assert response.status_code == 200
    assert response.json()["pending_grading"] is True
    row = seeded_store.get("mastery", "mast-p1")
    assert row["level"] == models.MasteryLevel.FUZZY.value


def test_cert15_lands_in_the_same_transaction_as_the_attempt_write(
    client: TestClient, manager: FakeManager, monkeypatch, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload("hit", "miss")})
    original = store.CampusStore.update

    def failing_update(self, table, row_id, values):
        if table == "mastery":
            raise RuntimeError("boom")
        return original(self, table, row_id, values)

    monkeypatch.setattr(store.CampusStore, "update", failing_update)
    with pytest.raises(RuntimeError):
        _grade(client, question_id="q-p1", answer="……")
    row = seeded_store.get("mastery", "mast-p1")
    assert row["level"] == models.MasteryLevel.MASTERED.value
    assert row["evidence"] == ""
