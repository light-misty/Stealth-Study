"""B 组资料库与按页问答端点（03 §4.2 B1-B7、G-07/G-10/G-11、KY-09/KY-10）。

`stealth_study/campus/library.py` 在 T08 就交付了库层（解析、切片、三级检索、QA 组装），但端点从未挂载：
前端 `campus/api.ts` 一直声明着 B1-B7，`LibraryPanel` / `MajorQAView` 也照常渲染，于是浏览器
里点一次导入就是 404。本文件把这条链路钉死在 HTTP 层，同时覆盖 03 §4.2 的全部错误码分支。

模型依赖（B6 的问答、B7 的出题）一律用 FakeProvider 回放，不依赖真实模型；B1-B5 完全不碰模型。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, store

CAMPUS = routes.CAMPUS_PREFIX
ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"

DOC_TEXT = "第一章 阅读\n\n长难句的主干是主语加谓语加宾语，先找谓语再找主语。\n\n第一节 细节题\n\n细节题先定位关键词。"
ANSWER = "长难句的主干是主语加谓语加宾语 [p.1]。"


def question_payload(count: int = 2) -> str:
    return json.dumps(
        {
            "items": [
                {
                    "subject": "reading",
                    "qtype": "single",
                    "stem": f"细节题 {index + 1}：先定位什么？",
                    "options": [{"key": "A", "text": "关键词"}, {"key": "B", "text": "段落数"}],
                    "answer": "A",
                }
                for index in range(count)
            ]
        }
    )


class FakeProvider:
    """Answers whichever schema the prompt asks for (QA text vs question JSON)."""

    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses if responses is not None else {"default": ANSWER}
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    def __init__(self, *, ready: bool = True, provider: Any = None) -> None:
        self.model = "fake:model"
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model]}


@pytest.fixture()
def library_dir() -> Path:
    return secrets.state_dir() / "campus" / "library"


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture()
def seeded_store() -> store.CampusStore:
    instance = store.CampusStore(secrets.state_dir() / "campus.db")
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.CET.value,
                "title": title,
                "status": status,
            },
        )
    instance.insert(
        "knowledge_point",
        {"id": "p-1", "profile_id": ACTIVE_ID, "title": "长难句主干"},
    )
    instance.insert(
        "knowledge_point",
        {"id": "p-foreign", "profile_id": OTHER_ID, "title": "他人的知识点"},
    )
    try:
        yield instance
    finally:
        instance.close()


def make_client(manager: FakeManager) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return TestClient(app)


@pytest.fixture()
def client(manager: FakeManager, seeded_store: store.CampusStore) -> TestClient:
    del seeded_store
    return make_client(manager)


def upload(
    client: TestClient,
    name: str = "notes.md",
    content: str = DOC_TEXT,
    profile_id: str = ACTIVE_ID,
):
    return client.post(
        f"{CAMPUS}/library/import",
        data={"profile_id": profile_id},
        files={"file": (name, content.encode("utf-8"), "text/markdown")},
    )


def seeded_doc(
    store_handle: store.CampusStore,
    library_dir: Path,
    *,
    doc_id: str,
    status: str,
    fail_reason: str | None = None,
    profile_id: str = ACTIVE_ID,
    body: str = DOC_TEXT,
) -> None:
    """Write the file the parse reads and the row the endpoint resolves it through."""
    folder = library_dir / profile_id / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "notes.md").write_text(body, encoding="utf-8")
    store_handle.insert(
        "source_doc",
        {
            "id": doc_id,
            "profile_id": profile_id,
            "title": "notes",
            "file_path": f"{doc_id}/notes.md",
            "file_type": models.DocFileType.MD.value,
            "parse_status": status,
            "fail_reason": fail_reason,
            "imported_at": "2026-09-16T00:00:00Z",
        },
    )


# -- B1 导入 ----------------------------------------------------------------


def test_b1_imports_a_markdown_file_and_parses_it_into_chunks(
    client: TestClient, library_dir: Path
) -> None:
    response = upload(client)
    assert response.status_code == 200
    body = response.json()
    # B1 answers with the bare SourceDoc — the hook appends it straight to its list.
    assert body["profile_id"] == ACTIVE_ID
    assert body["file_type"] == models.DocFileType.MD.value
    assert body["parse_status"] == models.ParseStatus.READY.value
    assert body["page_count"] == 1
    assert body["chunk_count"] >= 1
    assert body["char_count"] == len(DOC_TEXT)
    assert (library_dir / ACTIVE_ID / body["id"] / "notes.md").is_file()


def test_b1_stores_the_parsed_chunks_so_retrieval_can_find_them(client: TestClient) -> None:
    doc_id = upload(client).json()["id"]
    handle = store.CampusStore(secrets.state_dir() / "campus.db")
    try:
        chunks = handle.list_rows(
            "doc_chunk", where='"doc_id" = ?', params=[doc_id], order_by="page_no"
        )
    finally:
        handle.close()
    assert chunks
    assert any("谓语" in row["content"] for row in chunks)


def test_b1_accepts_a_txt_file(client: TestClient) -> None:
    body = upload(client, name="notes.txt", content="纯文本资料\n\n第二页内容").json()
    assert body["file_type"] == models.DocFileType.TXT.value
    assert body["parse_status"] == models.ParseStatus.READY.value


def test_b1_keeps_a_broken_pdf_as_a_documented_parse_failure(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/library/import",
        data={"profile_id": ACTIVE_ID},
        files={"file": ("broken.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parse_status"] == models.ParseStatus.FAILED.value
    assert body["fail_reason"] == "pdf_broken"


def test_b1_refuses_an_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/library/import",
        data={"profile_id": ACTIVE_ID},
        files={"file": ("notes.docx", b"PK", "application/msword")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_TYPE"


def test_b1_refuses_an_oversized_upload_before_it_lands_on_disk(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_LIBRARY_UPLOAD_BYTES", 64)
    response = upload(client, content="x" * 4096)
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "FILE_TOO_LARGE"
    assert detail["retryable"] is False


def test_b1_requires_the_profile_id_on_the_form(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/library/import",
        files={"file": ("notes.md", DOC_TEXT.encode("utf-8"), "text/markdown")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_b1_refuses_a_read_only_profile(client: TestClient) -> None:
    response = upload(client, profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


# -- B2 列表 ----------------------------------------------------------------


def test_b2_lists_the_profiles_documents_newest_first(client: TestClient) -> None:
    first = upload(client, name="a.md").json()["id"]
    second = upload(client, name="b.md").json()["id"]
    body = client.get(f"{CAMPUS}/library", params={"profile_id": ACTIVE_ID}).json()
    assert [row["id"] for row in body["items"]] == [second, first]
    assert set(body["items"][0]) >= {"id", "title", "parse_status", "chunk_count", "imported_at"}


def test_b2_never_returns_another_profiles_documents(client: TestClient) -> None:
    upload(client)
    upload(client, profile_id=OTHER_ID, name="other.md")
    body = client.get(f"{CAMPUS}/library", params={"profile_id": OTHER_ID}).json()
    assert [row["profile_id"] for row in body["items"]] == [OTHER_ID]


def test_b2_filters_by_parse_status(client: TestClient) -> None:
    upload(client, name="ok.md")
    client.post(
        f"{CAMPUS}/library/import",
        data={"profile_id": ACTIVE_ID},
        files={"file": ("broken.pdf", b"not-a-pdf", "application/pdf")},
    )
    ready = client.get(
        f"{CAMPUS}/library", params={"profile_id": ACTIVE_ID, "parse_status": "ready"}
    ).json()
    failed = client.get(
        f"{CAMPUS}/library", params={"profile_id": ACTIVE_ID, "parse_status": "failed"}
    ).json()
    assert [row["parse_status"] for row in ready["items"]] == ["ready"]
    assert [row["parse_status"] for row in failed["items"]] == ["failed"]


def test_b2_rejects_an_unknown_parse_status(client: TestClient) -> None:
    response = client.get(
        f"{CAMPUS}/library", params={"profile_id": ACTIVE_ID, "parse_status": "halfway"}
    )
    assert response.status_code == 422


def test_b2_requires_the_profile_id(client: TestClient) -> None:
    response = client.get(f"{CAMPUS}/library")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


# -- B3 / B4 / B5 -----------------------------------------------------------


def test_b3_returns_the_document_the_status_poll_reads(client: TestClient) -> None:
    doc_id = upload(client).json()["id"]
    body = client.get(f"{CAMPUS}/library/{doc_id}", params={"profile_id": ACTIVE_ID}).json()
    assert body["id"] == doc_id
    assert body["parse_status"] == models.ParseStatus.READY.value


def test_b3_unknown_document_is_doc_not_found(client: TestClient) -> None:
    response = client.get(f"{CAMPUS}/library/doc-nope", params={"profile_id": ACTIVE_ID})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DOC_NOT_FOUND"


def test_b3_refuses_another_profiles_document(client: TestClient) -> None:
    doc_id = upload(client, profile_id=OTHER_ID, name="other.md").json()["id"]
    response = client.get(f"{CAMPUS}/library/{doc_id}", params={"profile_id": ACTIVE_ID})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_b4_deletes_the_row_its_chunks_and_the_stored_file(
    client: TestClient, library_dir: Path
) -> None:
    doc_id = upload(client).json()["id"]
    assert (
        client.delete(f"{CAMPUS}/library/{doc_id}", params={"profile_id": ACTIVE_ID}).json()
        == {"deleted": True}
    )
    assert (
        client.get(f"{CAMPUS}/library/{doc_id}", params={"profile_id": ACTIVE_ID}).status_code
        == 404
    )
    assert client.get(f"{CAMPUS}/library", params={"profile_id": ACTIVE_ID}).json() == {"items": []}
    assert not (library_dir / ACTIVE_ID / doc_id).exists()
    handle = store.CampusStore(secrets.state_dir() / "campus.db")
    try:
        assert handle.count("doc_chunk", "doc_id = ?", (doc_id,)) == 0
    finally:
        handle.close()


def test_b4_refuses_another_profiles_document(client: TestClient) -> None:
    doc_id = upload(client, profile_id=OTHER_ID, name="other.md").json()["id"]
    params = {"profile_id": ACTIVE_ID}
    assert client.delete(f"{CAMPUS}/library/{doc_id}", params=params).status_code == 403
    assert client.get(f"{CAMPUS}/library/{doc_id}", params=params).status_code == 403


def test_b5_retries_a_failed_document_and_reaches_ready(
    client: TestClient, seeded_store: store.CampusStore, library_dir: Path
) -> None:
    seeded_doc(seeded_store, library_dir, doc_id="doc-retry", status="failed", fail_reason="pdf_broken")
    body = client.post(
        f"{CAMPUS}/library/doc-retry/retry", params={"profile_id": ACTIVE_ID}
    ).json()
    assert body["parse_status"] == models.ParseStatus.READY.value
    assert body["fail_reason"] is None
    assert body["chunk_count"] >= 1


def test_b5_returns_an_already_ready_document_untouched(
    client: TestClient, seeded_store: store.CampusStore, library_dir: Path
) -> None:
    seeded_doc(seeded_store, library_dir, doc_id="doc-ready", status="ready")
    body = client.post(
        f"{CAMPUS}/library/doc-ready/retry", params={"profile_id": ACTIVE_ID}
    ).json()
    assert body["parse_status"] == models.ParseStatus.READY.value


def test_b5_refuses_a_scanned_document_instead_of_burning_another_parse(
    client: TestClient, seeded_store: store.CampusStore, library_dir: Path
) -> None:
    seeded_doc(
        seeded_store,
        library_dir,
        doc_id="doc-scan",
        status="failed",
        fail_reason="no_text_layer",
    )
    response = client.post(
        f"{CAMPUS}/library/doc-scan/retry", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "DOC_SCAN_EMPTY"
    assert detail["retryable"] is False


def test_b5_refuses_another_profiles_document(client: TestClient) -> None:
    doc_id = upload(client, profile_id=OTHER_ID, name="other.md").json()["id"]
    assert (
        client.post(
            f"{CAMPUS}/library/{doc_id}/retry", params={"profile_id": ACTIVE_ID}
        ).status_code
        == 403
    )


# -- B6 按页问答 ------------------------------------------------------------


def test_b6_answers_with_citations_into_the_imported_document(client: TestClient) -> None:
    doc_id = upload(client).json()["id"]
    response = client.post(
        f"{CAMPUS}/qa",
        json={"profile_id": ACTIVE_ID, "doc_id": doc_id, "question": "长难句的主干是什么？"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ANSWER
    assert body["chunks_used"] >= 1
    assert body["used_retrieval"] in {"toc_route", "keyword"}
    assert body["citations"]
    citation = body["citations"][0]
    assert citation["doc_id"] == doc_id
    assert citation["page_no"] == 1
    assert "谓语" in citation["snippet"]


def test_b6_answers_across_the_whole_library_when_no_document_is_named(
    client: TestClient,
) -> None:
    upload(client)
    body = client.post(
        f"{CAMPUS}/qa", json={"profile_id": ACTIVE_ID, "question": "细节题先做什么？"}
    ).json()
    assert body["answer"] == ANSWER
    assert body["citations"]


def test_b6_refuses_an_empty_question(client: TestClient) -> None:
    response = client.post(f"{CAMPUS}/qa", json={"profile_id": ACTIVE_ID, "question": "   "})
    assert response.status_code == 422


def test_b6_refuses_a_document_that_is_still_parsing(
    client: TestClient, seeded_store: store.CampusStore, library_dir: Path
) -> None:
    seeded_doc(seeded_store, library_dir, doc_id="doc-pending", status="pending")
    response = client.post(
        f"{CAMPUS}/qa", json={"profile_id": ACTIVE_ID, "doc_id": "doc-pending", "question": "主干？"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DOC_NOT_READY"


def test_b6_refuses_a_scanned_document(
    client: TestClient, seeded_store: store.CampusStore, library_dir: Path
) -> None:
    seeded_doc(
        seeded_store,
        library_dir,
        doc_id="doc-scan",
        status="failed",
        fail_reason="no_text_layer",
    )
    response = client.post(
        f"{CAMPUS}/qa", json={"profile_id": ACTIVE_ID, "doc_id": "doc-scan", "question": "主干？"}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DOC_SCAN_EMPTY"


def test_b6_refuses_another_profiles_document(client: TestClient) -> None:
    doc_id = upload(client, profile_id=OTHER_ID, name="other.md").json()["id"]
    response = client.post(
        f"{CAMPUS}/qa", json={"profile_id": ACTIVE_ID, "doc_id": doc_id, "question": "主干？"}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN_PROFILE"


def test_b6_refuses_when_no_model_is_callable(seeded_store: store.CampusStore) -> None:
    del seeded_store
    manager = FakeManager(ready=False)
    manager.provider = None
    client = make_client(manager)
    response = client.post(f"{CAMPUS}/qa", json={"profile_id": ACTIVE_ID, "question": "主干？"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"


# -- B7 出题 ----------------------------------------------------------------


def test_b7_generates_and_stores_questions_from_a_document(
    manager: FakeManager, seeded_store: store.CampusStore, client: TestClient
) -> None:
    del seeded_store
    # B7 and B6 share one configured model, so the provider answers the question schema here and
    # the QA text elsewhere: the replay keys on the response index, not on the endpoint.
    manager.provider = FakeProvider({"default": question_payload(2)})
    doc_id = upload(client).json()["id"]
    response = client.post(
        f"{CAMPUS}/qa/generate-questions",
        json={"profile_id": ACTIVE_ID, "doc_id": doc_id, "count": 2},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert {item["source"] for item in items} == {models.QuestionSource.AI.value}
    assert {item["doc_id"] for item in items} == {doc_id}
    stored = client.get(f"{CAMPUS}/questions", params={"profile_id": ACTIVE_ID, "page_size": 10}).json()
    assert stored["total"] == 2
    assert stored["items"][0]["stem"].startswith("细节题")


def test_b7_anchors_the_generated_questions_on_a_knowledge_point(
    manager: FakeManager, seeded_store: store.CampusStore, client: TestClient
) -> None:
    del seeded_store
    manager.provider = FakeProvider({"default": question_payload(1)})
    body = client.post(
        f"{CAMPUS}/qa/generate-questions",
        json={"profile_id": ACTIVE_ID, "point_id": "p-1", "count": 1},
    ).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["point_id"] == "p-1"


def test_b7_defaults_to_five_questions(manager: FakeManager, seeded_store: store.CampusStore) -> None:
    del seeded_store
    manager.provider = FakeProvider({"default": question_payload(5)})
    client = make_client(manager)
    body = client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID}).json()
    assert len(body["items"]) == 5


def test_b7_accepts_the_boundary_counts(manager: FakeManager, seeded_store: store.CampusStore) -> None:
    del seeded_store
    manager.provider = FakeProvider({"default": question_payload(1)})
    client = make_client(manager)
    assert len(client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "count": 1}).json()["items"]) == 1
    manager.provider = FakeProvider({"default": question_payload(20)})
    assert len(client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "count": 20}).json()["items"]) == 20


def test_b7_rejects_a_count_outside_the_bounds(client: TestClient) -> None:
    assert client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "count": 0}).status_code == 422
    assert client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "count": 99}).status_code == 422


def test_b7_refuses_an_unknown_knowledge_point(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "point_id": "p-nope"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "POINT_NOT_FOUND"


def test_b7_refuses_another_profiles_knowledge_point(client: TestClient) -> None:
    # `_require_point` refuses out-of-scope points as POINT_NOT_FOUND (the same answer E3
    # and E5 give), while documents go through the library gate and answer
    # FORBIDDEN_PROFILE — both refuse, and 08 §4's P-3 only names the document case.
    response = client.post(
        f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "point_id": "p-foreign"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "POINT_NOT_FOUND"


def test_b7_refuses_a_document_that_is_still_parsing(
    client: TestClient, seeded_store: store.CampusStore, library_dir: Path
) -> None:
    seeded_doc(seeded_store, library_dir, doc_id="doc-pending", status="pending")
    response = client.post(
        f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "doc_id": "doc-pending"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DOC_NOT_READY"


def test_b7_refuses_unparsable_model_output_without_storing_anything(
    manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    del seeded_store
    manager.provider = FakeProvider({"default": "I cannot help with that."})
    client = make_client(manager)
    response = client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "MODEL_OUTPUT_INVALID"
    assert client.get(f"{CAMPUS}/questions", params={"profile_id": ACTIVE_ID}).json()["total"] == 0


def test_b7_refuses_an_item_with_an_unknown_subject(
    manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    del seeded_store
    payload = json.loads(question_payload(1))
    payload["items"][0]["subject"] = "astrophysics"
    manager.provider = FakeProvider({"default": json.dumps(payload)})
    client = make_client(manager)
    response = client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID})
    assert response.status_code == 502
    assert "subject" in response.json()["detail"]["message"]


def test_b7_refuses_a_choice_item_without_options(
    manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    del seeded_store
    payload = json.loads(question_payload(1))
    payload["items"][0].pop("options")
    manager.provider = FakeProvider({"default": json.dumps(payload)})
    client = make_client(manager)
    response = client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID})
    assert response.status_code == 502


def test_b7_keeps_a_short_batch_but_refuses_an_over_long_one(
    manager: FakeManager, seeded_store: store.CampusStore
) -> None:
    del seeded_store
    manager.provider = FakeProvider({"default": question_payload(3)})
    client = make_client(manager)
    body = client.post(
        f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "count": 5}
    ).json()
    assert len(body["items"]) == 3
    manager.provider = FakeProvider({"default": question_payload(6)})
    over = client.post(f"{CAMPUS}/qa/generate-questions", json={"profile_id": ACTIVE_ID, "count": 5})
    assert over.status_code == 502
    assert "出题数量超出请求" in over.json()["detail"]["message"]


def test_b7_refuses_a_read_only_profile(client: TestClient) -> None:
    response = client.post(
        f"{CAMPUS}/qa/generate-questions", json={"profile_id": FINISHED_ID}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


# -- 挂载与守卫（B 组随 03 §1 一起受既有 token 中间件保护） ------------------


def test_the_b_group_never_answers_a_missing_profile(client: TestClient) -> None:
    for method, path in (
        ("get", "/library"),
        ("get", "/library/doc-1"),
        ("delete", "/library/doc-1"),
        ("post", "/library/doc-1/retry"),
    ):
        response = getattr(client, method)(f"{CAMPUS}{path}")
        assert response.status_code == 400, f"{method} {path}"
        assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_b6_requires_a_body_rather_than_a_query(seeded_store: store.CampusStore) -> None:
    del seeded_store
    client = make_client(FakeManager())
    response = client.post(f"{CAMPUS}/qa", params={"profile_id": ACTIVE_ID, "question": "主干？"})
    assert response.status_code == 422


def test_the_router_carries_every_b_endpoint() -> None:
    router = routes.build_campus_router(object())
    declared = {(method, path) for route in router.routes for method in route.methods for path in [route.path]}
    for method, path in (
        ("POST", "/library/import"),
        ("GET", "/library"),
        ("GET", "/library/{doc_id}"),
        ("DELETE", "/library/{doc_id}"),
        ("POST", "/library/{doc_id}/retry"),
        ("POST", "/qa"),
        ("POST", "/qa/generate-questions"),
    ):
        assert (method, f"{CAMPUS}{path}") in declared, f"{method} {path}"
