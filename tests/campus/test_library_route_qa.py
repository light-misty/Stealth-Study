"""T08 L1 目录路由与 QA 组装测试（06 §5.1/§5.2/§5.3 + T04 决策二回退 + 03 §4.2 B6）。

`provider` 全部用 FakeProvider 按调用序号回放（不依赖真实模型）；门控（标题占比）、
0 命中降 L2（06 §8-4）、置信度不足与限域空回退全库（T04 §6-4）、citations 兜底
（06 §5.3-3）逐条固化。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ss.campus.library import (
    QA_SNIPPET_CHARS,
    CampusLibrary,
    LibraryError,
    build_citations,
    build_qa_messages,
    build_router_prompt,
    parse_router_output,
)
from ss.campus.store import CampusStore


class FakeProvider:
    """按调用序号回放 preset 输出的假 provider（`turn.text` 语义）。"""

    def __init__(self, responses: dict):
        self.responses = responses
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings) -> SimpleNamespace:
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


@pytest.fixture
def lib(tmp_path):
    store = CampusStore(tmp_path / "campus.db")
    library = CampusLibrary(store, lib_dir=tmp_path / "library")
    yield library
    store.close()


def _seed_doc(lib, doc_id, title, chunks, profile_id="p1") -> None:
    lib.store.insert(
        "source_doc",
        {
            "id": doc_id,
            "profile_id": profile_id,
            "title": title,
            "file_path": f"{doc_id}/x.pdf",
            "file_type": "pdf",
            "parse_status": "ready",
            "imported_at": "2026-09-15T00:00:00Z",
        },
    )
    page_offsets: dict[int, int] = {}
    for item in chunks:
        page_no, content, section = item[0], item[1], item[2]
        start = page_offsets.get(page_no, 0)
        lib.store.insert(
            "doc_chunk",
            {
                "doc_id": doc_id,
                "profile_id": profile_id,
                "page_no": page_no,
                "content": content,
                "chunk_type": "page",
                "section_title": section,
                "char_start": start,
                "char_end": start + len(content),
                "token_est": len(content),
            },
        )
        page_offsets[page_no] = start + len(content)


def _titled_doc(lib, doc_id="d1", profile_id="p1"):
    """带章节标题的教材（标题占比 100%，L1 门控通过）。"""
    _seed_doc(
        lib,
        doc_id,
        "深度学习讲义",
        [
            (1, "第一章 卷积\n卷积神经网络处理图像", "第一章 卷积"),
            (2, "第二章 反向传播\n反向传播通过链式法则更新梯度", "第二章 反向传播"),
            (3, "第三章 循环\n循环神经网络处理序列", "第三章 循环"),
        ],
        profile_id=profile_id,
    )


# ---------- L1 门控与路由 ----------


def test_route_prompt_lists_toc_and_question() -> None:
    prompt = build_router_prompt([("第一章 卷积", 1), ("第二章 反向传播", 2)], "讲讲反向传播")
    assert "第一章 卷积（p.1）" in prompt
    assert "第二章 反向传播（p.2）" in prompt
    assert "问题：讲讲反向传播" in prompt
    assert "最多 3 行" in prompt


def test_parse_router_output_matches_and_dedupes() -> None:
    toc = [("第一章 卷积", 1), ("第二章 反向传播", 2), ("第三章 循环网络", 3), ("A", 4)]
    text = "第二章 反向传播\n第二章 反向传播（p.2）\n第三章 循环网络\n第一章 卷积"
    assert parse_router_output(text, toc) == ["第二章 反向传播", "第三章 循环网络", "第一章 卷积"]


def test_parse_router_output_filters_short_items_and_caps_three() -> None:
    toc = [("A", 1), ("B", 2), ("第一章 卷积", 3), ("第二章 反向传播", 4), ("第三章 循环", 5)]
    text = "A\nB\n第一章 卷积\n第二章 反向传播\n第三章 循环"
    assert parse_router_output(text, toc) == ["第一章 卷积", "第二章 反向传播", "第三章 循环"]


def test_parse_router_output_no_hit_returns_empty() -> None:
    toc = [("第一章 卷积", 1)]
    assert parse_router_output("第四章 不存在的章节", toc) == []


def test_retrieve_without_provider_skips_route(lib) -> None:
    _titled_doc(lib)
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert results and results[0]["page_no"] == 2


def test_route_scopes_recall_to_selected_sections(lib) -> None:
    provider = FakeProvider({1: "第二章 反向传播"})
    lib._provider = provider
    _titled_doc(lib)
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert provider.seen, "L1 路由应发生一次模型调用"
    assert provider.seen[0]["settings"]["temperature"] == 0
    assert provider.seen[0]["settings"]["timeout"] == 90
    assert results
    assert all(row["section_title"] == "第二章 反向传播" for row in results)


def test_route_zero_hit_falls_back_to_keyword(lib) -> None:
    provider = FakeProvider({1: "第八章 完全无关"})
    lib._provider = provider
    _titled_doc(lib)
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert results and results[0]["page_no"] == 2


def test_route_low_confidence_falls_back_to_keyword(lib) -> None:
    provider = FakeProvider({1: "第三章 循环"})
    lib._provider = provider
    _titled_doc(lib)
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert results
    assert all(row["section_title"] != "第三章 循环" for row in results)


def test_route_scoped_empty_falls_back_to_full_library(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "讲义",
        [
            (1, "第一章 卷积\n卷积处理图像", "第一章 卷积"),
            (2, "第二章 反向传播\n反向传播更新梯度", "第二章 反向传播"),
            (9, "第九章 附录\n附录术语表", "第九章 附录"),
        ],
    )
    provider = FakeProvider({1: "第九章 附录"})
    lib._provider = provider
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert results and results[0]["page_no"] == 2


def test_route_provider_error_falls_back_without_retry(lib) -> None:
    provider = FakeProvider({1: RuntimeError("boom")})
    lib._provider = provider
    _titled_doc(lib)
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert len(provider.seen) == 1, "路由失败不应重试（06 §8-4）"
    assert results and results[0]["page_no"] == 2


def test_route_skipped_when_titled_ratio_below_threshold(lib) -> None:
    provider = FakeProvider({})
    lib._provider = provider
    _seed_doc(
        lib,
        "d1",
        "讲义",
        [
            (1, "无标题内容", None),
            (2, "也是无标题", None),
            (3, "第二章 反向传播\n内容", "第二章 反向传播"),
        ],
    )
    results = lib.retrieve("p1", "反向传播", doc_id="d1")
    assert provider.seen == [], "标题占比 1/3 < 50% 时不应发起路由"
    assert results and results[0]["page_no"] == 3


# ---------- QA 组装（06 §5.3 / 03 B6） ----------


def test_answer_qa_requires_provider(lib) -> None:
    _titled_doc(lib)
    with pytest.raises(LibraryError) as exc:
        _run(lib.answer_qa("p1", "讲讲反向传播", doc_id="d1"))
    assert exc.value.code == "MODEL_NOT_CONFIGURED"


def test_answer_qa_doc_not_found(lib) -> None:
    provider = FakeProvider({"default": "答案"})
    lib._provider = provider
    with pytest.raises(LibraryError) as exc:
        _run(lib.answer_qa("p1", "问题", doc_id="missing"))
    assert exc.value.code == "DOC_NOT_FOUND"


def test_answer_qa_scan_empty_maps_to_doc_scan_empty(lib, tmp_path) -> None:
    from ss.campus.library import FAIL_NO_TEXT_LAYER

    lib.store.insert(
        "source_doc",
        {
            "id": "scan1",
            "profile_id": "p1",
            "title": "扫描件",
            "file_path": "scan1/x.pdf",
            "file_type": "pdf",
            "parse_status": "failed",
            "fail_reason": FAIL_NO_TEXT_LAYER,
            "imported_at": "2026-09-15T00:00:00Z",
        },
    )
    provider = FakeProvider({"default": "答案"})
    lib._provider = provider
    with pytest.raises(LibraryError) as exc:
        _run(lib.answer_qa("p1", "问题", doc_id="scan1"))
    assert exc.value.code == "DOC_SCAN_EMPTY"


def test_answer_qa_pending_doc_maps_to_doc_not_ready(lib) -> None:
    lib.store.insert(
        "source_doc",
        {
            "id": "pending1",
            "profile_id": "p1",
            "title": "解析中",
            "file_path": "pending1/x.pdf",
            "file_type": "pdf",
            "parse_status": "pending",
            "imported_at": "2026-09-15T00:00:00Z",
        },
    )
    provider = FakeProvider({"default": "答案"})
    lib._provider = provider
    with pytest.raises(LibraryError) as exc:
        _run(lib.answer_qa("p1", "问题", doc_id="pending1"))
    assert exc.value.code == "DOC_NOT_READY"


def test_answer_qa_assembles_pages_and_citations(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "深度学习讲义",
        [
            (1, "卷积处理图像", None),
            (2, "反向传播更新梯度", None),
        ],
    )
    provider = FakeProvider({"default": "反向传播用链式法则 [p.2]"})
    lib._provider = provider
    result = _run(lib.answer_qa("p1", "反向传播怎么更新梯度", doc_id="d1"))
    assert result["answer"] == "反向传播用链式法则 [p.2]"
    assert result["chunks_used"] == 1
    assert result["used_retrieval"] == "keyword"
    assert [c["page_no"] for c in result["citations"]] == [2]
    prompt = provider.seen[0]["messages"][1]["content"]
    assert "[深度学习讲义 p.2]" in prompt
    assert "反向传播更新梯度" in prompt
    assert "问题：反向传播怎么更新梯度" in prompt


def test_answer_qa_citations_fall_back_to_all_chunks(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "讲义",
        [(1, "卷积处理图像", None), (2, "反向传播更新梯度", None)],
    )
    provider = FakeProvider({"default": "资料里没有直接答案"})
    lib._provider = provider
    result = _run(lib.answer_qa("p1", "反向传播怎么更新梯度", doc_id="d1"))
    assert result["chunks_used"] == 1
    assert result["citations"], "retrieval 成功过时 citations 兜底必填（06 §5.3-3）"
    assert {c["page_no"] for c in result["citations"]} == {2}
    assert result["citations"][0]["snippet"] == "反向传播更新梯度"


def test_answer_qa_uses_toc_route_flag(lib) -> None:
    _titled_doc(lib)
    provider = FakeProvider({1: "第二章 反向传播", 2: "反向传播用链式法则 [p.2]"})
    lib._provider = provider
    result = _run(lib.answer_qa("p1", "反向传播怎么更新梯度", doc_id="d1"))
    assert result["used_retrieval"] == "toc_route"


def test_answer_qa_timeout_maps_to_model_timeout(lib) -> None:
    _seed_doc(lib, "d1", "讲义", [(1, "卷积处理图像", None)])
    provider = FakeProvider({1: TimeoutError("timed out")})
    lib._provider = provider
    with pytest.raises(LibraryError) as exc:
        _run(lib.answer_qa("p1", "问题", doc_id="d1"))
    assert exc.value.code == "MODEL_TIMEOUT"


def test_answer_qa_provider_error_maps_to_model_output_invalid(lib) -> None:
    _seed_doc(lib, "d1", "讲义", [(1, "卷积处理图像", None)])
    provider = FakeProvider({1: RuntimeError("connection reset")})
    lib._provider = provider
    with pytest.raises(LibraryError) as exc:
        _run(lib.answer_qa("p1", "问题", doc_id="d1"))
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


# ---------- QA 上下文预算与引用纯函数 ----------


def test_build_qa_messages_truncates_long_chunk_and_budget() -> None:
    chunks = [
        {"doc_id": "d1", "page_no": page_no, "content": "x" * 5000, "doc_title": "讲义"}
        for page_no in range(1, 7)
    ]
    messages = build_qa_messages("问题", chunks)
    user_content = messages[1]["content"]
    assert user_content.count("[讲义 p.") == 5, "6 片 5000 字符超出 12000 预算,第 6 片不再装入"
    assert f"[讲义 p.1]\n{'x' * QA_SNIPPET_CHARS}" in user_content


def test_build_citations_snippets_are_truncated() -> None:
    chunks = [{"doc_id": "d1", "page_no": 1, "content": "y" * 500, "doc_title": "讲义"}]
    citations = build_citations("无关答案", chunks)
    assert citations[0]["snippet"] == "y" * 200


def _run(awaitable):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(awaitable)
