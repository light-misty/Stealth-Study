"""E5 作答端点（03 §4.5 E5、07 §4 T09 验收②③）。

E5 是全局域里唯一的 AI 端点，因此它同时钉住三件事：

* 客观题（single/multiple/judge/blank）在服务端即判分，响应带 `is_correct` 与标准答案；
* 主观题落 `attempt` 后**同步**走 C1 批改链（T07 `GradingEngine`，provider 取 sidecar 的
  `manager.provider`），批改结果回写 `attempt.grading_json` / `degrade_level` / `model_used`；
* 批改链的失败语义按 T07 §6-6 映射回 03 文档错误码（`MODEL_TIMEOUT` / `MODEL_OUTPUT_INVALID`）。

provider 用回放式假实现（同 `test_grading_engine.py` 的形态），因此这里跑的是真实降级链，
不依赖真实模型；测试同时断言引擎参数（温度 0、90s 超时、单次预算）确实透传到 provider。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
MOCK_ID = "mock-1"
FOREIGN_MOCK_ID = "mock-foreign"


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


def l1_text(band: int = 11) -> str:
    rows = ["档位：11", "内容分：4", "结构分：4", "语言分：3"]
    rows += [f"错误{i}：" for i in range(1, 9)]
    rows.append("升格示范：rewritten")
    rows[0] = f"档位：{band}"
    return "\n".join(rows)


def scoring_payload() -> str:
    return json.dumps(
        {
            "scoring_points": [
                {"point": "答出德育原则", "status": "hit", "note": ""},
                {"point": "结合材料", "status": "miss", "note": ""},
            ],
            "overall_score": 8,
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
        models: tuple[str, ...] | None = None,
    ) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()
        self._models = models if models is not None else ((model,) if model else ())

    def get_settings(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "model_ready": self._ready,
            "models": list(self._models),
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
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {"id": profile_id, "track_type": models.TrackType.CET.value, "title": title, "status": status},
        )
    instance.insert(
        "mock_exam",
        {"id": MOCK_ID, "profile_id": ACTIVE_ID, "paper_title": "2026 年 6 月真题", "started_at": "2026-09-14T00:00:00Z"},
    )
    instance.insert(
        "mock_exam",
        {"id": FOREIGN_MOCK_ID, "profile_id": OTHER_ID, "paper_title": "他人模考", "started_at": "2026-09-14T00:00:00Z"},
    )
    for index, (subject, qtype, answer, max_score) in enumerate(
        (
            (models.Subject.READING.value, models.QuestionType.SINGLE.value, "A", 2),
            (models.Subject.READING.value, models.QuestionType.MULTIPLE.value, "AC", 3),
            (models.Subject.LISTENING.value, models.QuestionType.JUDGE.value, "T", 1),
            (models.Subject.VOCAB.value, models.QuestionType.BLANK.value, "abandon|apple", 2),
            (models.Subject.WRITING.value, models.QuestionType.ESSAY.value, "参考范文", 15),
            (models.Subject.POLITICS.value, models.QuestionType.SHORT_ANSWER.value, "要点", 8),
        )
    ):
        instance.insert(
            "question_bank_item",
            {
                "id": f"q{index}",
                "profile_id": ACTIVE_ID,
                "subject": subject,
                "stem": f"题干 q{index}",
                "qtype": qtype,
                "answer": answer,
                "max_score": max_score,
            },
        )
    instance.insert(
        "question_bank_item",
        {"id": "q-single", "profile_id": ACTIVE_ID, "subject": "reading", "stem": "无答案", "qtype": "single"},
    )
    instance.insert(
        "question_bank_item",
        {"id": "q-foreign", "profile_id": OTHER_ID, "subject": "reading", "stem": "他人题目", "answer": "A"},
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


def _detail(response) -> dict:
    return response.json()["detail"]


def _attempt(client: TestClient, question_id: str = "q0", **overrides):
    payload = {"profile_id": ACTIVE_ID, "question_id": question_id, "answer": "A"}
    payload.update(overrides)
    return client.post(f"{routes.CAMPUS_PREFIX}/attempts", json=payload)


# ---------------------------------------------------------------------------
# 客观题即判分
# ---------------------------------------------------------------------------

def test_e5_marks_a_correct_single_choice(client: TestClient) -> None:
    response = _attempt(client, "q0", answer="a")
    assert response.status_code == 200
    body = response.json()
    assert body["is_correct"] == 1
    assert body["score"] == 2
    assert body["max_score"] == 2
    assert body["standard_answer"] == "A"
    assert body["pending_grading"] is False
    assert body["degrade_level"] is None
    assert body["grading_json"] is None
    assert body["question_id"] == "q0"
    assert body["track_type"] == models.TrackType.CET.value
    assert body["subject"] == models.Subject.READING.value
    assert body["session_type"] == models.SessionType.PRACTICE.value


def test_e5_marks_a_wrong_single_choice_with_zero(client: TestClient) -> None:
    body = _attempt(client, "q0", answer="B").json()
    assert body["is_correct"] == 0
    assert body["score"] == 0
    assert body["max_score"] == 2


def test_e5_ignores_the_order_of_a_multiple_choice_answer(client: TestClient) -> None:
    assert _attempt(client, "q1", answer="C,A").json()["is_correct"] == 1


def test_e5_marks_a_wrong_multiple_choice_answer(client: TestClient) -> None:
    assert _attempt(client, "q1", answer="A").json()["is_correct"] == 0


@pytest.mark.parametrize("answer", ["T", "t", "对", "true"])
def test_e5_accepts_the_documented_judge_spellings(client: TestClient, answer: str) -> None:
    assert _attempt(client, "q2", answer=answer).json()["is_correct"] == 1


@pytest.mark.parametrize("answer", ["F", "错", "false"])
def test_e5_marks_the_other_judge_side_wrong(client: TestClient, answer: str) -> None:
    assert _attempt(client, "q2", answer=answer).json()["is_correct"] == 0


def test_e5_compares_blank_answers_without_case_or_padding(client: TestClient) -> None:
    assert _attempt(client, "q3", answer=" ABANDON | Apple ").json()["is_correct"] == 1


def test_e5_requires_every_blank_to_match(client: TestClient) -> None:
    assert _attempt(client, "q3", answer="abandon").json()["is_correct"] == 0


def test_e5_treats_a_question_without_a_key_as_incorrect(client: TestClient) -> None:
    body = _attempt(client, "q-single", answer="A").json()
    assert body["is_correct"] == 0
    assert body["standard_answer"] is None


def test_e5_records_the_session_type_and_mock(client: TestClient) -> None:
    body = _attempt(
        client, "q0", session_type=models.SessionType.MOCK.value, mock_exam_id=MOCK_ID
    ).json()
    assert body["session_type"] == models.SessionType.MOCK.value
    assert body["mock_exam_id"] == MOCK_ID


def test_e5_rejects_an_unknown_session_type(client: TestClient) -> None:
    assert _attempt(client, "q0", session_type="cram").status_code == 422


def test_e5_rejects_an_unknown_or_foreign_mock(client: TestClient) -> None:
    unknown = _attempt(client, "q0", mock_exam_id="no-such-mock")
    foreign = _attempt(client, "q0", mock_exam_id=FOREIGN_MOCK_ID)
    assert unknown.status_code == 404 and _detail(unknown)["code"] == "MOCK_NOT_FOUND"
    assert foreign.status_code == 404 and _detail(foreign)["code"] == "MOCK_NOT_FOUND"


def test_e5_rejects_a_blank_answer(client: TestClient) -> None:
    assert _attempt(client, "q0", answer="   ").status_code == 422


def test_e5_rejects_unknown_body_fields(client: TestClient) -> None:
    assert _attempt(client, "q0", answer_for_real="A").status_code == 422


# ---------------------------------------------------------------------------
# 主观题同步批改
# ---------------------------------------------------------------------------

def test_e5_grades_an_essay_through_the_real_engine(client: TestClient, manager: FakeManager) -> None:
    response = _attempt(client, "q4", answer="I thinks it is good.")
    assert response.status_code == 200
    body = response.json()
    assert body["pending_grading"] is True
    assert body["degrade_level"] == 0
    assert body["model_used"] == "fake:model"
    assert body["score"] == 11
    assert body["max_score"] == 15
    grading = body["grading_json"]
    assert grading["band"] == 11
    assert grading["dimension_scores"] == {"content": 4, "structure": 4, "language": 3}
    assert grading["errors"][0]["type"] == "主谓一致"
    assert grading["model_answer_outline"] == "outline"
    assert grading["notice"] is None
    assert manager.provider.seen[0]["model"] == "fake:model"
    assert manager.provider.seen[0]["settings"]["temperature"] == 0
    assert manager.provider.seen[0]["settings"]["timeout"] == 90


def test_e5_keeps_the_engine_whitelist_out_of_grading_json(client: TestClient) -> None:
    grading = _attempt(client, "q4", answer="essay").json()["grading_json"]
    for dropped in ("ok", "model_used", "usage", "fail_reason", "degrade_level"):
        assert dropped not in grading
    assert grading["_degrade_trace"]
    assert grading["calls"] >= 1


def test_e5_stores_a_degraded_grading_with_its_notice(
    client: TestClient, manager: FakeManager
) -> None:
    manager.provider = FakeProvider({1: "not json at all", 2: l1_text(11), "default": l1_text(11)})
    body = _attempt(client, "q4", answer="essay").json()
    assert body["degrade_level"] == 1
    assert body["grading_json"]["notice"]
    assert body["grading_json"]["band"] == 11


def test_e5_grades_a_scoring_point_question_without_a_score(
    client: TestClient, manager: FakeManager
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload()})
    body = _attempt(client, "q5", answer="德育原则是……").json()
    assert body["pending_grading"] is True
    assert body["score"] is None
    assert body["max_score"] is None
    points = body["grading_json"]["scoring_points"]
    assert [point["status"] for point in points] == ["hit", "miss"]


def test_e5_reports_a_timeout_with_the_documented_error(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": TimeoutError("upstream timeout")})
    response = _attempt(client, "q4", answer="essay")
    assert response.status_code == 504
    assert _detail(response)["code"] == "MODEL_TIMEOUT"
    assert _detail(response)["retryable"] is True
    rows = seeded_store.list_rows("attempt", profile_id=ACTIVE_ID)
    assert len(rows) == 1
    assert rows[0]["degrade_level"] == 3


def test_e5_reports_unparsable_output_with_the_documented_error(
    client: TestClient, manager: FakeManager
) -> None:
    manager.provider = FakeProvider({"default": ""})
    response = _attempt(client, "q4", answer="essay")
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


def test_e5_refuses_grading_without_a_configured_model(
    seeded_store: store.CampusStore,
) -> None:
    manager = FakeManager(model="", ready=False)
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    client = TestClient(app)
    response = _attempt(client, "q4", answer="essay")
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"
    assert seeded_store.count("attempt", "profile_id = ?", (ACTIVE_ID,)) == 0


def test_e5_uses_the_model_chosen_in_the_settings(
    seeded_store: store.CampusStore,
) -> None:
    provider = FakeProvider()
    manager = FakeManager(model="active:model", models=("active:model", "picked:model"), provider=provider)
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    client = TestClient(app)
    client.patch(
        f"{routes.CAMPUS_PREFIX}/app-state",
        json={"settings": {"task_models": {models.CampusTask.GRADING.value: "picked:model"}}},
    )
    assert _attempt(client, "q4", answer="essay").status_code == 200
    assert provider.seen[0]["model"] == "picked:model"


# ---------------------------------------------------------------------------
# 守卫与契约
# ---------------------------------------------------------------------------

def test_e5_returns_question_not_found(client: TestClient) -> None:
    response = _attempt(client, "no-such-question")
    assert response.status_code == 404
    assert _detail(response)["code"] == "QUESTION_NOT_FOUND"


def test_e5_refuses_another_profile_question(client: TestClient) -> None:
    response = _attempt(client, "q-foreign")
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_e5_refuses_a_finished_profile(client: TestClient, seeded_store: store.CampusStore) -> None:
    response = _attempt(client, "q0", profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"
    assert seeded_store.count("attempt", "profile_id = ?", (FINISHED_ID,)) == 0


def test_e5_requires_a_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/attempts", json={"question_id": "q0", "answer": "A"}
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_e5_is_write_only(client: TestClient) -> None:
    assert client.get(f"{routes.CAMPUS_PREFIX}/attempts").status_code == 405


def test_e5_writes_one_attempt_row_per_submission(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    _attempt(client, "q0", answer="A")
    _attempt(client, "q0", answer="B")
    rows = seeded_store.list_rows("attempt", profile_id=ACTIVE_ID)
    assert len(rows) == 2
    assert {row["is_correct"] for row in rows} == {0, 1}


def test_e5_keeps_the_attempt_out_of_another_profile_view(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    assert _attempt(client, "q0", answer="A").status_code == 200
    assert seeded_store.count("attempt", "profile_id = ?", (ACTIVE_ID,)) == 1
    assert seeded_store.count("attempt", "profile_id = ?", (OTHER_ID,)) == 0


def test_every_question_type_is_either_objective_or_gradable() -> None:
    from stealth_study.campus import service

    for qtype in models.QuestionType:
        objective = qtype.value in service.OBJECTIVE_QUESTION_TYPES
        gradable = qtype.value in service.GRADING_KIND_BY_QTYPE
        assert objective != gradable, qtype
