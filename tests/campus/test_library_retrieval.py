"""T08 关键词检索测试（06 §5.1 的 L2/L3 层 + T04 §6-4 IDF 加权 + 02 §5.2 FTS 兜底）。

切片数据直插 `doc_chunk`（默认构造不建 FTS 虚表，不影响 19 表断言）；
FTS 路径通过 `enable_fts=True` 显式启用后验证探测、维护与运行时降级。
"""

from __future__ import annotations

import sqlite3

import pytest

from ss.campus.library import CampusLibrary, extract_keywords, score_chunk
from ss.campus.store import CampusStore


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
    for page_no, content, section in chunks:
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


# ---------- 关键词抽取与评分 ----------


def test_extract_keywords_latin_and_cjk_bigrams() -> None:
    assert extract_keywords("反向传播 backprop") == ["backprop", "反向", "向传", "传播"]


def test_extract_keywords_drops_stopword_grams() -> None:
    assert "的了" not in extract_keywords("的了如何")
    assert extract_keywords("的了") == []


def test_extract_keywords_deduplicates_and_caps() -> None:
    keywords = extract_keywords("反向传播 反向传播 学习学习")
    assert len(keywords) == len(set(keywords))
    assert len(keywords) <= 32


def test_score_chunk_counts_hits_and_position() -> None:
    idf = {"反向": 1.0, "传播": 1.0}
    hit = score_chunk("反向传播是反向的过程", ["反向", "传播"], idf)
    assert hit > 0
    assert score_chunk("完全不相关的内容", ["反向", "传播"], idf) == 0


# ---------- L2：doc 限域关键词召回 ----------


def test_retrieve_keyword_ranks_top_match_first(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "深度学习讲义",
        [
            (1, "卷积神经网络处理图像特征", "第一章 卷积"),
            (2, "反向传播通过链式法则更新梯度，反向传播需要误差项", "第二章 反向传播"),
            (3, "循环神经网络处理序列", "第三章 循环"),
        ],
    )
    results = lib.retrieve("p1", "反向传播如何更新梯度", doc_id="d1")
    assert results
    assert "反向传播" in results[0]["content"]
    top = results[0]
    assert top["doc_id"] == "d1" and top["page_no"] == 2
    assert top["score"] > 0
    assert top["chunk_seq"] == 0
    for key in ("doc_id", "page_no", "chunk_seq", "section_title", "content", "score"):
        assert key in top


def test_retrieve_returns_empty_for_stopword_only_query(lib) -> None:
    _seed_doc(lib, "d1", "教材", [(1, "第一章 内容", "第一章")])
    assert lib.retrieve("p1", "的了", doc_id="d1") == []
    assert lib.retrieve("p1", "", doc_id="d1") == []


def test_retrieve_chunk_seq_counts_page_slices(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "教材",
        [
            (1, "第一章 起点内容", "第一章"),
            (2, "第二章 前半部分", "第二章"),
            (2, "第二章 后半部分", "第二章"),
        ],
    )
    results = lib.retrieve("p1", "后半部分", doc_id="d1")
    assert results
    target = next(row for row in results if "后半部分" in row["content"])
    assert target["chunk_seq"] == 1


# ---------- L3：跨档案域全扫 ----------


def test_retrieve_l3_scans_profile_when_doc_id_none(lib) -> None:
    _seed_doc(
        lib, "d1", "讲义一", [(1, "卷积神经网络处理图像", "第一章")], profile_id="p1"
    )
    _seed_doc(
        lib, "d2", "讲义二", [(5, "反向传播更新梯度", "第二章")], profile_id="p1"
    )
    _seed_doc(
        lib, "d3", "他人资料", [(1, "反向传播的秘密", "第一章")], profile_id="p2"
    )
    results = lib.retrieve("p1", "反向传播")
    assert [row["doc_id"] for row in results] == ["d2"]


def test_retrieve_respects_top_k(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "教材",
        [(page_no, f"第{page_no}章 反向传播变体{page_no}", f"第{page_no}章") for page_no in range(1, 6)],
    )
    results = lib.retrieve("p1", "反向传播", doc_id="d1", top_k=2)
    assert len(results) == 2


def test_retrieve_unknown_doc_returns_empty(lib) -> None:
    assert lib.retrieve("p1", "反向传播", doc_id="missing") == []


# ---------- IDF 加权（T04 §6-4：2-gram 必须 IDF 加权） ----------


def test_idf_weighting_ranks_rare_section_higher(lib) -> None:
    common_pages = [
        (page_no, f"第{page_no}章 学习方法与学习方法论{page_no}", f"第{page_no}章")
        for page_no in range(1, 7)
    ]
    _seed_doc(lib, "d1", "教材", common_pages + [(9, "反向传播推导过程", "第九章 反向传播")])
    results = lib.retrieve("p1", "反向传播 学习", doc_id="d1")
    assert results[0]["page_no"] == 9


# ---------- FTS5 加速档与 LIKE 兜底（02 §5.2 / 验收③） ----------


def _fts_available() -> bool:
    probe = CampusStore(":memory:")
    try:
        try:
            probe.execute(
                "CREATE VIRTUAL TABLE fts_probe USING fts5(content, tokenize='trigram')"
            )
            return True
        except sqlite3.OperationalError:
            return False
    finally:
        probe.close()


@pytest.mark.skipif(not _fts_available(), reason="sqlite build has no FTS5")
def test_fts_enabled_builds_virtual_table_and_searches(lib) -> None:
    _seed_doc(
        lib,
        "d1",
        "教材",
        [(1, "backpropagation updates the weights", "Chapter 1"), (2, "convolution scans images", "Chapter 2")],
    )
    fts_lib = CampusLibrary(lib.store, lib_dir=None, enable_fts=True)
    assert fts_lib._fts_ready
    assert "doc_chunk_fts" in fts_lib.store.table_names()
    results = fts_lib.retrieve("p1", "backpropagation weights", doc_id="d1")
    assert results and results[0]["page_no"] == 1


@pytest.mark.skipif(not _fts_available(), reason="sqlite build has no FTS5")
def test_import_maintains_fts_index(lib, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ss.campus.library._read_pdf_with_meta",
        lambda p: ([(1, "backpropagation updates the weights")], False, []),
    )
    fts_lib = CampusLibrary(lib.store, lib_dir=tmp_path / "library", enable_fts=True)
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = fts_lib.import_pdf("p1", str(path))
    results = fts_lib.retrieve("p1", "backpropagation", doc_id=doc["id"])
    assert results and results[0]["page_no"] == 1


def test_fts_detection_failure_falls_back_to_like(lib, monkeypatch) -> None:
    _seed_doc(lib, "d1", "教材", [(1, "反向传播更新梯度", "第一章")])
    monkeypatch.setattr(CampusLibrary, "_detect_fts5", lambda self: False)
    fts_lib = CampusLibrary(lib.store, lib_dir=None, enable_fts=True)
    assert fts_lib._fts_ready is False
    assert "doc_chunk_fts" not in fts_lib.store.table_names()
    results = fts_lib.retrieve("p1", "反向传播", doc_id="d1")
    assert results and "反向传播" in results[0]["content"]


@pytest.mark.skipif(not _fts_available(), reason="sqlite build has no FTS5")
def test_fts_runtime_failure_degrades_to_like(lib, monkeypatch) -> None:
    _seed_doc(
        lib,
        "d1",
        "教材",
        [(1, "反向传播更新梯度 backpropagation updates", "第一章")],
    )
    fts_lib = CampusLibrary(lib.store, lib_dir=None, enable_fts=True)

    def broken_match(terms, scope, params):
        raise sqlite3.OperationalError("fts5: syntax error")

    monkeypatch.setattr(fts_lib, "_fts_match", broken_match)
    results = fts_lib.retrieve("p1", "backpropagation", doc_id="d1")
    assert results and "backpropagation" in results[0]["content"]
    assert fts_lib._fts_ready is False
