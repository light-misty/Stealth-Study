"""H1-H6 证书台知识树与掌握度端点（03 §4.8、07 §4 T12 验收①）。

验收口径：1000 字考纲生成的树 ≥2 层 ≥15 节点（H4，用回放式 provider 断言落库形状）；
掌握度 UPSERT 三态与维度行隔离（H5）；覆盖率与薄弱 TOP5 实时反映掌握度行（H6）。
横切（PROFILE_REQUIRED / PROFILE_READ_ONLY / FORBIDDEN_PROFILE）沿用 T06 守卫测试的约定。
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


def tree_payload(sections: int = 3, children: int = 2, leaves: int = 3) -> str:
    def section(index: int) -> dict:
        return {
            "title": f"第{index}章",
            "children": [
                {
                    "title": f"第{index}-{child}节",
                    "children": [
                        {"title": f"第{index}-{child}-{leaf}点"}
                        for leaf in range(1, leaves + 1)
                    ],
                }
                for child in range(1, children + 1)
            ],
        }

    return json.dumps({"sections": [section(index) for index in range(1, sections + 1)]})


class FakeProvider:
    """按调用序号回放文本的 provider（`ProviderClient.complete` 的假实现）。"""

    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses or {"default": tree_payload()}
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
    for point_id, parent_id, title, order in (
        ("p-a", None, "教育知识与能力", 0),
        ("p-a1", "p-a", "德育", 1),
        ("p-a0", "p-a", "教育基础", 0),
        ("p-b", None, "综合素质", 1),
    ):
        instance.insert(
            "knowledge_point",
            {
                "id": point_id,
                "profile_id": ACTIVE_ID,
                "title": title,
                "parent_id": parent_id,
                "order_index": order,
            },
        )
    instance.insert(
        "knowledge_point",
        {"id": "p-foreign", "profile_id": OTHER_ID, "title": "他人知识点"},
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-1",
            "profile_id": ACTIVE_ID,
            "subject": "教育学",
            "stem": "题干一",
            "point_id": "p-a1",
        },
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-2",
            "profile_id": ACTIVE_ID,
            "subject": "教育学",
            "stem": "题干二",
            "point_id": "p-a1",
        },
    )
    instance.insert(
        "question_bank_item",
        {
            "id": "q-other",
            "profile_id": OTHER_ID,
            "subject": "教育学",
            "stem": "他人题目",
            "point_id": "p-a1",
        },
    )
    instance.insert(
        "mistake_book",
        {
            "id": "m-1",
            "profile_id": ACTIVE_ID,
            "attempt_id": "attempt-1",
            "track_type": models.TrackType.CERT.value,
            "subject": "教育学",
            "point_id": "p-a0",
            "last_wrong_at": "2026-09-14T00:00:00Z",
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


# ---------------------------------------------------------------------------
# H1 — 知识树
# ---------------------------------------------------------------------------


def test_h1_returns_a_nested_tree_with_live_counts(client: TestClient) -> None:
    body = client.get(f"{_prefix()}/knowledge-tree", params={"profile_id": ACTIVE_ID}).json()

    titles = [root["title"] for root in body["roots"]]
    assert titles == ["教育知识与能力", "综合素质"]
    root = body["roots"][0]
    assert [child["title"] for child in root["children"]] == ["教育基础", "德育"]
    section = root["children"][0]
    assert section["question_count"] == 0
    assert section["mistake_count"] == 1
    moral = root["children"][1]
    assert moral["question_count"] == 2
    assert moral["mistake_count"] == 0
    assert set(root) == {
        "id",
        "profile_id",
        "title",
        "parent_id",
        "desc",
        "order_index",
        "source",
        "question_count",
        "mistake_count",
        "created_at",
        "updated_at",
        "children",
    }


def test_h1_orders_siblings_by_order_index_then_creation(client: TestClient) -> None:
    body = client.get(f"{_prefix()}/knowledge-tree", params={"profile_id": ACTIVE_ID}).json()
    assert [child["title"] for child in body["roots"][0]["children"]] == ["教育基础", "德育"]


def test_h1_treats_a_dangling_parent_as_a_root(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "knowledge_point",
        {
            "id": "p-orphan",
            "profile_id": ACTIVE_ID,
            "title": "悬空点",
            "parent_id": "p-deleted",
        },
    )
    body = client.get(f"{_prefix()}/knowledge-tree", params={"profile_id": ACTIVE_ID}).json()
    assert "悬空点" in [root["title"] for root in body["roots"]]


def test_h1_never_shows_another_profiles_points(client: TestClient) -> None:
    body = client.get(f"{_prefix()}/knowledge-tree", params={"profile_id": ACTIVE_ID}).json()
    titles = json.dumps(body, ensure_ascii=False)
    assert "他人知识点" not in titles


def test_h1_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{_prefix()}/knowledge-tree")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# H2 — 新建知识点
# ---------------------------------------------------------------------------


def test_h2_creates_a_child_point_with_the_manual_source(client: TestClient) -> None:
    response = client.post(
        f"{_prefix()}/knowledge-points",
        json={
            "profile_id": ACTIVE_ID,
            "parent_id": "p-a",
            "title": "教学设计",
            "desc": "教案撰写要点",
            "order_index": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "教学设计"
    assert body["parent_id"] == "p-a"
    assert body["source"] == models.KnowledgeSource.MANUAL.value
    assert body["order_index"] == 2
    assert body["question_count"] == 0


def test_h2_defaults_the_order_index_to_zero(client: TestClient) -> None:
    body = client.post(
        f"{_prefix()}/knowledge-points",
        json={"profile_id": ACTIVE_ID, "title": " standalone "},
    ).json()
    assert body["title"] == "standalone"
    assert body["parent_id"] is None
    assert body["order_index"] == 0


def test_h2_rejects_a_foreign_or_missing_parent(client: TestClient) -> None:
    for parent_id in ("p-foreign", "no-such-point"):
        response = client.post(
            f"{_prefix()}/knowledge-points",
            json={"profile_id": ACTIVE_ID, "parent_id": parent_id, "title": "x"},
        )
        assert response.status_code == 404, parent_id
        assert _detail(response)["code"] == "POINT_NOT_FOUND"


def test_h2_rejects_unknown_body_fields(client: TestClient) -> None:
    response = client.post(
        f"{_prefix()}/knowledge-points",
        json={"profile_id": ACTIVE_ID, "title": "x", "color": "red"},
    )
    assert response.status_code == 422


def test_h2_rejects_a_blank_title(client: TestClient) -> None:
    assert (
        client.post(
            f"{_prefix()}/knowledge-points",
            json={"profile_id": ACTIVE_ID, "title": "   "},
        ).status_code
        == 422
    )


def test_h2_refuses_a_finished_profile(client: TestClient) -> None:
    response = client.post(
        f"{_prefix()}/knowledge-points",
        json={"profile_id": FINISHED_ID, "title": "x"},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


# ---------------------------------------------------------------------------
# H3 — 改名/移动与删除
# ---------------------------------------------------------------------------


def test_h3_renames_and_reorders_a_point(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/knowledge-points/p-a0",
        json={"profile_id": ACTIVE_ID, "title": "教育学基础", "order_index": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "教育学基础"
    assert body["order_index"] == 5


def test_h3_moves_a_point_under_another_parent(client: TestClient) -> None:
    body = client.patch(
        f"{_prefix()}/knowledge-points/p-a1",
        json={"profile_id": ACTIVE_ID, "parent_id": "p-b"},
    ).json()
    assert body["parent_id"] == "p-b"


def test_h3_clears_a_parent_with_an_explicit_null(client: TestClient) -> None:
    body = client.patch(
        f"{_prefix()}/knowledge-points/p-a1",
        json={"profile_id": ACTIVE_ID, "parent_id": None},
    ).json()
    assert body["parent_id"] is None


def test_h3_refuses_a_self_parent(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/knowledge-points/p-a",
        json={"profile_id": ACTIVE_ID, "parent_id": "p-a"},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "ILLEGAL_TRANSITION"


def test_h3_refuses_a_descendant_parent(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/knowledge-points/p-a",
        json={"profile_id": ACTIVE_ID, "parent_id": "p-a1"},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "ILLEGAL_TRANSITION"


def test_h3_delete_promotes_the_children(client: TestClient, seeded_store: store.CampusStore) -> None:
    response = client.delete(
        f"{_prefix()}/knowledge-points/p-a", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"deleted": True, "orphaned_children": 2}
    assert seeded_store.get("knowledge_point", "p-a") is None
    for child_id in ("p-a0", "p-a1"):
        assert seeded_store.get("knowledge_point", child_id)["parent_id"] is None


def test_h3_delete_drops_the_points_mastery_rows(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "mastery",
        {
            "id": "mast-1",
            "profile_id": ACTIVE_ID,
            "point_id": "p-a0",
            "level": models.MasteryLevel.FUZZY.value,
        },
    )
    client.delete(f"{_prefix()}/knowledge-points/p-a0", params={"profile_id": ACTIVE_ID})
    assert seeded_store.get("mastery", "mast-1") is None


def test_h3_a_missing_point_is_point_not_found(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/knowledge-points/nope",
        json={"profile_id": ACTIVE_ID, "title": "x"},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "POINT_NOT_FOUND"


def test_h3_a_foreign_point_is_forbidden(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/knowledge-points/p-foreign",
        json={"profile_id": ACTIVE_ID, "title": "x"},
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


# ---------------------------------------------------------------------------
# H4 — 考纲抽树
# ---------------------------------------------------------------------------


def test_h4_generates_a_deep_tree_from_syllabus_text(
    client: TestClient, manager: FakeManager
) -> None:
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "一、教育学基础 （一）教育 1. 教育的概念……" * 40},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 27
    roots = body["roots"]
    assert len(roots) == 3
    assert all(root["source"] == models.KnowledgeSource.AI_GENERATED.value for root in roots)
    assert all(len(root["children"]) == 2 for root in roots)
    assert all(len(child["children"]) == 3 for root in roots for child in root["children"])
    assert [child["order_index"] for child in roots[0]["children"]] == [0, 1]
    assert manager.provider.seen[0]["settings"]["temperature"] == 0


def test_h4_keeps_the_syllabus_out_of_another_profile(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    before = seeded_store.count("knowledge_point", "profile_id = ?", (ACTIVE_ID,))
    client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "考纲内容"},
    )
    generated = seeded_store.count(
        "knowledge_point",
        '"profile_id" = ? AND "source" = ?',
        (OTHER_ID, models.KnowledgeSource.AI_GENERATED.value),
    )
    assert generated == 0
    assert seeded_store.count("knowledge_point", "profile_id = ?", (ACTIVE_ID,)) > before


def test_h4_reads_a_scoped_doc_when_only_the_doc_id_is_given(
    client: TestClient, seeded_store: store.CampusStore, manager: FakeManager
) -> None:
    seeded_store.insert(
        "source_doc",
        {
            "id": "doc-1",
            "profile_id": ACTIVE_ID,
            "title": "考纲",
            "file_path": "campus/library/doc-1/考纲.pdf",
            "parse_status": models.ParseStatus.READY.value,
            "imported_at": "2026-09-14T00:00:00Z",
        },
    )
    seeded_store.insert(
        "doc_chunk",
        {
            "id": "chunk-1",
            "doc_id": "doc-1",
            "profile_id": ACTIVE_ID,
            "page_no": 1,
            "content": "第一章 教育基础",
        },
    )
    seeded_store.insert(
        "doc_chunk",
        {
            "id": "chunk-2",
            "doc_id": "doc-1",
            "profile_id": ACTIVE_ID,
            "page_no": 2,
            "content": "第二章 学生指导",
        },
    )
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "doc_id": "doc-1"},
    )
    assert response.status_code == 200
    prompt = manager.provider.seen[0]["messages"][-1]["content"]
    assert "第一章 教育基础" in prompt and "第二章 学生指导" in prompt


def test_h4_requires_text_or_doc_id(client: TestClient) -> None:
    assert (
        client.post(
            f"{_prefix()}/knowledge-tree/generate", json={"profile_id": ACTIVE_ID}
        ).status_code
        == 422
    )


def test_h4_prefers_the_pasted_text_over_the_doc(
    client: TestClient, seeded_store: store.CampusStore, manager: FakeManager
) -> None:
    seeded_store.insert(
        "source_doc",
        {
            "id": "doc-1",
            "profile_id": ACTIVE_ID,
            "title": "考纲",
            "file_path": "campus/library/doc-1/考纲.pdf",
            "imported_at": "2026-09-14T00:00:00Z",
        },
    )
    client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "粘贴的考纲", "doc_id": "doc-1"},
    )
    assert manager.provider.seen[0]["messages"][-1]["content"] == "粘贴的考纲"


def test_h4_rejects_a_foreign_or_missing_doc(client: TestClient) -> None:
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "doc_id": "no-such-doc"},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "DOC_NOT_FOUND"


def test_h4_reports_a_doc_without_a_text_layer(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "source_doc",
        {
            "id": "doc-scan",
            "profile_id": ACTIVE_ID,
            "title": "扫描件",
            "file_path": "campus/library/doc-scan/扫描件.pdf",
            "parse_status": models.ParseStatus.FAILED.value,
            "fail_reason": "no_text_layer",
            "imported_at": "2026-09-14T00:00:00Z",
        },
    )
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "doc_id": "doc-scan"},
    )
    assert response.status_code == 422
    assert _detail(response)["code"] == "DOC_SCAN_EMPTY"


def test_h4_refuses_generation_without_a_configured_model(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(model="", ready=False)))
    client = TestClient(app)
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "考纲"},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"


def test_h4_reports_a_provider_timeout(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": TimeoutError("upstream timeout")})
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "考纲"},
    )
    assert response.status_code == 504
    assert _detail(response)["code"] == "MODEL_TIMEOUT"
    assert _detail(response)["retryable"] is True


def test_h4_reports_unparsable_model_output(client: TestClient, manager: FakeManager) -> None:
    manager.provider = FakeProvider({"default": "我觉得树是这样的，不给你 JSON"})
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "考纲"},
    )
    assert response.status_code == 502
    assert _detail(response)["code"] == "MODEL_OUTPUT_INVALID"


def test_h4_rolls_back_everything_when_a_section_is_invalid(
    client: TestClient, manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    manager.provider = FakeProvider({"default": json.dumps({"sections": [{"title": ""}]})})
    response = client.post(
        f"{_prefix()}/knowledge-tree/generate",
        json={"profile_id": ACTIVE_ID, "text": "考纲"},
    )
    assert response.status_code == 502
    assert (
        seeded_store.count(
            "knowledge_point",
            '"profile_id" = ? AND "source" = ?',
            (ACTIVE_ID, models.KnowledgeSource.AI_GENERATED.value),
        )
        == 0
    )


# ---------------------------------------------------------------------------
# H5 — 掌握度 UPSERT
# ---------------------------------------------------------------------------


def test_h5_upserts_a_point_level_mastery(client: TestClient) -> None:
    first = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-a1", "level": "fuzzy"},
    )
    assert first.status_code == 200
    created = first.json()
    assert created["level"] == models.MasteryLevel.FUZZY.value
    assert created["point_id"] == "p-a1"
    assert created["dimension"] is None

    second = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-a1", "level": "mastered"},
    ).json()
    assert second["id"] == created["id"]
    assert second["level"] == models.MasteryLevel.MASTERED.value


def test_h5_keeps_dimension_rows_separate(client: TestClient) -> None:
    point_row = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-a1", "level": "fuzzy"},
    ).json()
    dim_row = client.patch(
        f"{_prefix()}/mastery",
        json={
            "profile_id": ACTIVE_ID,
            "point_id": "p-a1",
            "dimension": "listening",
            "level": "mastered",
        },
    ).json()
    assert dim_row["id"] != point_row["id"]
    assert dim_row["dimension"] == models.MasteryDimension.LISTENING.value


def test_h5_stores_a_profile_level_row_without_a_point(client: TestClient) -> None:
    body = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "level": "mastered"},
    ).json()
    assert body["point_id"] is None
    assert body["dimension"] is None


def test_h5_rejects_an_unknown_level(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-a1", "level": "great"},
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "INVALID_LEVEL"


def test_h5_rejects_a_foreign_point(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-foreign", "level": "fuzzy"},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "POINT_NOT_FOUND"


def test_h5_refuses_a_finished_profile(client: TestClient) -> None:
    response = client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": FINISHED_ID, "level": "fuzzy"},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# H6 — 覆盖率与薄弱 TOP5
# ---------------------------------------------------------------------------


def test_h6_reports_coverage_and_the_weak_top5(client: TestClient) -> None:
    client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-a", "level": "fuzzy"},
    )
    client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-b", "level": "unknown"},
    )
    body = client.get(f"{_prefix()}/mastery/coverage", params={"profile_id": ACTIVE_ID}).json()

    assert body["coverage"] == 0.5
    assert body["weak_top5"] == [
        {"point_id": "p-b", "title": "综合素质", "level": "unknown"},
        {"point_id": "p-a", "title": "教育知识与能力", "level": "fuzzy"},
    ]


def test_h6_excludes_mastered_points_from_the_weak_list(client: TestClient) -> None:
    client.patch(
        f"{_prefix()}/mastery",
        json={"profile_id": ACTIVE_ID, "point_id": "p-a", "level": "mastered"},
    )
    body = client.get(f"{_prefix()}/mastery/coverage", params={"profile_id": ACTIVE_ID}).json()
    assert body["coverage"] == 0.25
    assert body["weak_top5"] == []


def test_h6_ignores_dimension_rows_for_coverage(client: TestClient) -> None:
    client.patch(
        f"{_prefix()}/mastery",
        json={
            "profile_id": ACTIVE_ID,
            "point_id": "p-a",
            "dimension": "reading",
            "level": "fuzzy",
        },
    )
    body = client.get(f"{_prefix()}/mastery/coverage", params={"profile_id": ACTIVE_ID}).json()
    assert body["coverage"] == 0.0


def test_h6_an_empty_tree_has_zero_coverage(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    seeded_store.insert(
        "exam_profile",
        {
            "id": "profile-bare",
            "track_type": models.TrackType.CERT.value,
            "title": "无知识树",
        },
    )
    body = client.get(
        f"{_prefix()}/mastery/coverage", params={"profile_id": "profile-bare"}
    ).json()
    assert body == {"coverage": 0.0, "weak_top5": []}
