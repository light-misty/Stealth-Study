"""C 组批改端点（03 §4.3 C1-C4、07 §4 T10 的"作文/翻译批改挂 C1"与"常见错误 TOP3"）。

C 组在 07 文档里没有被点名给任何任务（T09 交付文档 §5-13 已登记该缺口），但 T10 的两处交付直接
依赖它：写译批改必须挂在 C1 上、CET-12 的"我的常见错误 TOP3"就是 C4。因此本文件与 T10 同阶段交付。

C1 的响应形状按 03 §4.3 的 `GradeResult` 契约（`dimensions`/`errors[].offset`/`rubric`）从 T07 引擎的
`GradeResult` 适配而来；`errors[].offset` 由服务端在原文里定位片段得到（PRD CET4 ② "可点击定位到原文"）。
批改链本身走 T07 引擎与回放式 provider，不依赖真实模型。
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

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
CUSTOM_ANSWER = "I thinks it is very important to study hard, and we should persisting."


def essay_payload(band: int = 11, fragment: str = "I thinks", type_: str = "主谓一致") -> str:
    return json.dumps(
        {
            "band": band,
            "dimension_scores": {"content": 4, "structure": 4, "language": 3},
            "errors": [{"fragment": fragment, "suggestion": "I think", "type": type_}],
            "upgraded_demo": "rewritten paragraph",
            "model_answer_outline": "outline",
        }
    )


def translation_payload(band: int = 9) -> str:
    return json.dumps(
        {
            "band": band,
            "errors": [{"fragment": "漏译片段", "suggestion": "补充译文", "type": "漏译"}],
            "upgraded_demo": "rewritten translation",
        }
    )


def scoring_payload() -> str:
    return json.dumps(
        {
            "scoring_points": [
                {"point": "答出德育原则", "status": "hit", "note": "准确"},
                {"point": "结合材料", "status": "partial", "note": "只举一例"},
                {"point": "结构完整", "status": "miss", "note": ""},
            ],
            "overall_score": 6,
            "model_answer_outline": "outline",
        }
    )


class FakeProvider:
    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses if responses is not None else {"default": essay_payload()}
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    def __init__(self, model: str = "fake:model", *, ready: bool = True, provider: Any = None) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model] if self.model else []}


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
        {"id": "q-foreign", "profile_id": OTHER_ID, "subject": "writing", "stem": "他人题目"},
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


def _grade(client: TestClient, **overrides):
    payload = {"profile_id": ACTIVE_ID, "kind": "essay", "answer": CUSTOM_ANSWER}
    payload.update(overrides)
    return client.post(f"{routes.CAMPUS_PREFIX}/grading", json=payload)


def _stored(client: TestClient, attempt_id: str) -> dict:
    """The attempt as C2 serves it — where the fields 03 §4.3 does not echo back live."""
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/{attempt_id}", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# C1 POST /grading
# ---------------------------------------------------------------------------

def test_c1_returns_the_documented_grade_result_shape(client: TestClient) -> None:
    response = _grade(client)
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {
        "attempt_id",
        "degrade_level",
        "rubric",
        "dimensions",
        "errors",
        "model_answer_outline",
        "model_used",
        "notice",
    }
    assert body["degrade_level"] == 0
    assert body["notice"] is None
    assert body["model_used"] == "fake:model"
    assert body["model_answer_outline"] == "outline"


def test_c1_maps_essay_dimensions_onto_the_five_point_scale(client: TestClient) -> None:
    dims = _grade(client).json()["dimensions"]
    assert dims == [
        {"name": "内容", "score": 4, "max": 5, "comment": ""},
        {"name": "结构", "score": 4, "max": 5, "comment": ""},
        {"name": "语言", "score": 3, "max": 5, "comment": ""},
    ]


def test_c1_locates_each_error_in_the_submitted_text(client: TestClient) -> None:
    errors = _grade(client).json()["errors"]
    assert errors == [
        {
            "original": "I thinks",
            "suggestion": "I think",
            "type": "主谓一致",
            "offset": CUSTOM_ANSWER.index("I thinks"),
        }
    ]


def test_c1_reports_a_null_offset_when_the_fragment_is_absent(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": essay_payload(fragment="not in the text")})
    assert _grade(client).json()["errors"][0]["offset"] is None


def test_c1_carries_the_band_and_the_upgraded_demo(client: TestClient) -> None:
    body = _grade(client).json()
    assert body["band"] == 11
    assert body["upgraded_demo"] == "rewritten paragraph"


def test_c1_uses_the_essay_rubric_by_default(client: TestClient, manager: FakeManager) -> None:
    body = _grade(client).json()
    assert body["rubric"] == "cet-essay"
    assert "四六级短文写作评分标准" in manager.provider.seen[0]["messages"][0]["content"]


def test_c1_grades_a_translation_with_its_own_rubric(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": translation_payload()})
    body = _grade(client, kind="translation", answer="我认为读书很重要。").json()
    assert body["rubric"] == "cet-translation"
    assert body["dimensions"] == [{"name": "档位", "score": 9, "max": 15, "comment": ""}]
    assert body["errors"][0]["type"] == "漏译"
    assert "四六级段落翻译评分标准" in manager.provider.seen[0]["messages"][0]["content"]


def test_c1_maps_scoring_points_onto_dimensions(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": scoring_payload()})
    body = _grade(client, kind="short_answer", answer="德育原则包括……").json()
    assert body["rubric"] == "cert-scoring-points"
    assert body["dimensions"] == [
        {"name": "答出德育原则", "score": 1.0, "max": 1, "comment": "准确"},
        {"name": "结合材料", "score": 0.5, "max": 1, "comment": "只举一例"},
        {"name": "结构完整", "score": 0.0, "max": 1, "comment": ""},
    ]
    assert body["band"] is None


def test_c1_accepts_an_explicit_rubric_id(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": scoring_payload()})
    body = _grade(client, kind="practical", answer="操作步骤……", rubric_id="cert-scoring-points").json()
    assert body["rubric"] == "cert-scoring-points"
    assert "主观题评分点三态输出契约" in manager.provider.seen[0]["messages"][0]["content"]


def test_c1_rejects_an_unknown_rubric_id(client: TestClient) -> None:
    response = _grade(client, rubric_id="no-such-rubric")
    assert response.status_code == 404
    assert _detail(response)["code"] == "RUBRIC_NOT_FOUND"


def test_c1_lets_a_custom_rubric_override_the_built_in_one(client: TestClient, manager: FakeManager) -> None:
    body = _grade(client, custom_rubric="自定义评分标准：只看得分点。").json()
    assert body["rubric"] == "custom"
    assert "自定义评分标准：只看得分点。" in manager.provider.seen[0]["messages"][0]["content"]


def test_c1_takes_the_subject_from_the_question(client: TestClient) -> None:
    attempt_id = _grade(client, question_id="q-essay").json()["attempt_id"]
    stored = _stored(client, attempt_id)
    assert stored["subject"] == models.Subject.WRITING.value
    assert stored["question_id"] == "q-essay"


@pytest.mark.parametrize(
    "kind, subject, payload",
    [
        ("essay", models.Subject.WRITING.value, "essay"),
        ("lesson_plan", models.Subject.WRITING.value, "scoring"),
        ("translation", models.Subject.TRANSLATION.value, "essay"),
        ("short_answer", models.Subject.MAJOR.value, "scoring"),
        ("practical", models.Subject.MAJOR.value, "scoring"),
    ],
)
def test_c1_derives_the_subject_from_the_kind_when_no_question_is_given(
    client: TestClient, manager: FakeManager, kind: str, subject: str, payload: str
) -> None:
    manager.provider = FakeProvider({"default": scoring_payload() if payload == "scoring" else essay_payload()})
    attempt_id = _grade(client, kind=kind, answer="作答内容").json()["attempt_id"]
    stored = _stored(client, attempt_id)
    assert stored["subject"] == subject
    assert stored["question_id"] is None


def test_c1_refuses_another_profile_question(client: TestClient) -> None:
    response = _grade(client, question_id="q-foreign")
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_c1_returns_question_not_found_for_an_unknown_question(client: TestClient) -> None:
    response = _grade(client, question_id="no-such-question")
    assert response.status_code == 404
    assert _detail(response)["code"] == "QUESTION_NOT_FOUND"


def test_c1_records_the_attempt_with_the_grading_kind(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _grade(client).json()
    row = seeded_store.get("attempt", body["attempt_id"])
    assert row["session_type"] == models.SessionType.GRADING.value
    assert row["profile_id"] == ACTIVE_ID
    assert row["user_answer"] == CUSTOM_ANSWER
    assert row["degrade_level"] == 0
    assert row["score"] == 11 and row["max_score"] == 15
    assert json.loads(row["grading_json"])["kind"] == "essay"


def test_c1_marks_a_degraded_grading_with_a_notice(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": "not json at all"})
    body = _grade(client).json()
    assert body["degrade_level"] >= 1
    assert body["notice"]


def test_c1_reports_a_timeout_with_the_documented_error(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": TimeoutError("upstream timeout")})
    response = _grade(client)
    assert response.status_code == 504
    assert _detail(response)["code"] == "MODEL_TIMEOUT"


def test_c1_reports_unparsable_output_with_the_documented_error(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": ""})
    response = _grade(client)
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


def test_c1_refuses_grading_without_a_configured_model(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(model="", ready=False)))
    client = TestClient(app)
    response = _grade(client)
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"
    assert seeded_store.count("attempt", "profile_id = ?", (ACTIVE_ID,)) == 0


def test_c1_refuses_a_finished_profile(client: TestClient) -> None:
    response = _grade(client, profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_c1_requires_a_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/grading", json={"kind": "essay", "answer": CUSTOM_ANSWER}
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


@pytest.mark.parametrize(
    "payload",
    [
        {"profile_id": ACTIVE_ID, "kind": "nope", "answer": "x"},
        {"profile_id": ACTIVE_ID, "kind": "essay", "answer": "   "},
        {"profile_id": ACTIVE_ID, "kind": "essay"},
        {"profile_id": ACTIVE_ID, "kind": "essay", "answer": "x", "unknown": 1},
    ],
)
def test_c1_rejects_malformed_bodies(client: TestClient, payload: dict) -> None:
    assert client.post(f"{routes.CAMPUS_PREFIX}/grading", json=payload).status_code == 422


# ---------------------------------------------------------------------------
# C2 GET /grading/{attempt_id}
# ---------------------------------------------------------------------------

def test_c2_returns_the_stored_attempt(client: TestClient) -> None:
    attempt_id = _grade(client).json()["attempt_id"]
    body = _stored(client, attempt_id)
    assert body["id"] == attempt_id
    assert body["degrade_level"] == 0
    assert body["grading_json"]["band"] == 11


def test_c2_returns_attempt_not_found(client: TestClient) -> None:
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/no-such-attempt", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "ATTEMPT_NOT_FOUND"


def test_c2_refuses_another_profile_attempt(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "attempt",
        {
            "id": "attempt-foreign",
            "profile_id": OTHER_ID,
            "track_type": "cet",
            "subject": "writing",
            "user_answer": "x",
        },
    )
    response = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/attempt-foreign", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_c2_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/grading/whatever")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# C3 GET /grading/history
# ---------------------------------------------------------------------------

def test_c3_returns_a_page_envelope_newest_first(client: TestClient) -> None:
    first = _grade(client).json()["attempt_id"]
    second = _grade(client, kind="translation", answer="译文").json()["attempt_id"]
    body = client.get(f"{routes.CAMPUS_PREFIX}/grading/history", params={"profile_id": ACTIVE_ID}).json()
    assert body["total"] == 2
    assert body["page"] == 1 and body["page_size"] == 50
    assert [item["id"] for item in body["items"]] == [second, first]


def test_c3_filters_by_subject_and_kind(client: TestClient) -> None:
    _grade(client).json()
    _grade(client, kind="translation", answer="译文").json()
    by_subject = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/history",
        params={"profile_id": ACTIVE_ID, "subject": models.Subject.TRANSLATION.value},
    ).json()
    assert by_subject["total"] == 1
    by_kind = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/history",
        params={"profile_id": ACTIVE_ID, "kind": "essay"},
    ).json()
    assert by_kind["total"] == 1
    assert by_kind["items"][0]["grading_json"]["kind"] == "essay"


def test_c3_pages_through_the_history(client: TestClient) -> None:
    ids = [_grade(client).json()["attempt_id"] for _ in range(3)]
    page = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/history",
        params={"profile_id": ACTIVE_ID, "page": 2, "page_size": 2},
    ).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == ids[0]


def test_c3_never_leaks_another_profile_history(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "attempt",
        {
            "id": "attempt-foreign",
            "profile_id": OTHER_ID,
            "track_type": "cet",
            "subject": "writing",
            "user_answer": "x",
        },
    )
    body = client.get(f"{routes.CAMPUS_PREFIX}/grading/history", params={"profile_id": ACTIVE_ID}).json()
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# C4 GET /grading/common-errors
# ---------------------------------------------------------------------------

def test_c4_is_empty_before_any_grading(client: TestClient) -> None:
    body = client.get(f"{routes.CAMPUS_PREFIX}/grading/common-errors", params={"profile_id": ACTIVE_ID}).json()
    assert body == {"top3": []}


def test_c4_ranks_the_most_frequent_error_types(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider(
        {
            1: essay_payload(type_="主谓一致"),
            2: essay_payload(type_="主谓一致"),
            3: essay_payload(type_="拼写"),
        }
    )
    for index in range(3):
        assert _grade(client).status_code == 200
    body = client.get(f"{routes.CAMPUS_PREFIX}/grading/common-errors", params={"profile_id": ACTIVE_ID}).json()
    top3 = body["top3"]
    assert [item["type"] for item in top3] == ["主谓一致", "拼写"]
    assert top3[0]["count"] == 2
    assert top3[1]["count"] == 1
    assert top3[0]["samples"] == ["I thinks"]


def test_c4_caps_the_list_at_three_types(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider(
        {
            1: essay_payload(type_="主谓一致"),
            2: essay_payload(type_="拼写"),
            3: essay_payload(type_="时态语态"),
            4: essay_payload(type_="用词不当"),
        }
    )
    for index in range(4):
        _grade(client)
    body = client.get(f"{routes.CAMPUS_PREFIX}/grading/common-errors", params={"profile_id": ACTIVE_ID}).json()
    assert len(body["top3"]) == 3


def test_c4_filters_by_kind(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": essay_payload(type_="主谓一致")})
    _grade(client)
    manager.provider = FakeProvider({"default": translation_payload()})
    _grade(client, kind="translation", answer="译文")
    only_translation = client.get(
        f"{routes.CAMPUS_PREFIX}/grading/common-errors",
        params={"profile_id": ACTIVE_ID, "kind": "translation"},
    ).json()
    assert [item["type"] for item in only_translation["top3"]] == ["漏译"]


def test_c4_ignores_unparsable_stored_grading(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "attempt",
        {
            "id": "attempt-broken",
            "profile_id": ACTIVE_ID,
            "track_type": "cet",
            "subject": "writing",
            "user_answer": "x",
            "grading_json": "{not json",
        },
    )
    body = client.get(f"{routes.CAMPUS_PREFIX}/grading/common-errors", params={"profile_id": ACTIVE_ID}).json()
    assert body == {"top3": []}
