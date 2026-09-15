"""T08 扫描件与异常分支测试（06 §6.1 四情形全覆盖 + B5 幂等 + 级联删除）。

扫描件 fixture 用 pypdf 在测试内生成空白页 PDF（零文字层，不依赖 T02 语料）；
部分页空 / 截断 / 3000 片上限通过 monkeypatch 解析层注入，验证 `import_pdf` 的
状态机与 `source_doc` 落库行为。不依赖模型。
"""

from __future__ import annotations

import io
from typing import Optional

import pytest

from ss.campus.library import (
    FAIL_NO_TEXT_LAYER,
    FAIL_PDF_BROKEN,
    FAIL_TOO_MANY_CHUNKS,
    FAIL_TRUNCATED,
    CampusLibrary,
    LibraryError,
)
from ss.campus.store import CampusStore


def _write_blank_pdf(path, num_pages: int) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    path.write_bytes(buf.getvalue())


@pytest.fixture
def library(tmp_path):
    store = CampusStore(tmp_path / "campus.db")
    lib = CampusLibrary(store, lib_dir=tmp_path / "library")
    yield lib
    store.close()


def _chunk_count(lib: CampusLibrary, doc_id: str) -> int:
    return lib.store.count("doc_chunk", "doc_id = ?", (doc_id,))


# ---------- 情形一：整本无文字层（扫描件） ----------


def test_import_scanned_pdf_marks_failed_no_text_layer(library, tmp_path) -> None:
    path = tmp_path / "scan.pdf"
    _write_blank_pdf(path, 3)
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "failed"
    assert doc["fail_reason"] == FAIL_NO_TEXT_LAYER
    assert doc["page_count"] == 3
    assert doc["chunk_count"] == 0 and doc["char_count"] == 0
    assert _chunk_count(library, doc["id"]) == 0


def test_retry_scan_empty_is_idempotent(library, tmp_path) -> None:
    path = tmp_path / "scan.pdf"
    _write_blank_pdf(path, 2)
    doc = library.import_pdf("p1", str(path))
    with pytest.raises(LibraryError) as first:
        library.retry_parse("p1", doc["id"])
    assert first.value.code == "DOC_SCAN_EMPTY"
    with pytest.raises(LibraryError) as second:
        library.retry_parse("p1", doc["id"])
    assert second.value.code == "DOC_SCAN_EMPTY"
    assert _chunk_count(library, doc["id"]) == 0


def test_retry_unknown_doc_raises_doc_not_found(library) -> None:
    with pytest.raises(LibraryError) as exc:
        library.retry_parse("p1", "no-such-doc")
    assert exc.value.code == "DOC_NOT_FOUND"


def test_retry_ready_doc_returns_same_row(library, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ss.campus.library._read_pdf_with_meta",
        lambda p: ([(1, "第一章 绪论\n内容")], False, []),
    )
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    again = library.retry_parse("p1", doc["id"])
    assert again["parse_status"] == "ready"
    assert again["chunk_count"] == doc["chunk_count"] == 1


# ---------- 情形二：部分页空 ----------


def test_partial_blank_pages_below_ratio_stays_ready(library, tmp_path, monkeypatch) -> None:
    pages = [(1, "第一章 绪论\n内容"), (2, ""), (3, ""), (4, "")]
    monkeypatch.setattr("ss.campus.library._read_pdf_with_meta", lambda p: (pages, False, []))
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "ready"
    assert doc["page_count"] == 4 and doc["chunk_count"] == 1


def test_partial_blank_pages_above_ratio_fails(library, tmp_path, monkeypatch) -> None:
    pages = [(1, "第一章 绪论\n内容"), (2, ""), (3, ""), (4, ""), (5, ""), (6, "")]
    monkeypatch.setattr("ss.campus.library._read_pdf_with_meta", lambda p: (pages, False, []))
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "failed"
    assert doc["fail_reason"] == FAIL_NO_TEXT_LAYER
    assert _chunk_count(library, doc["id"]) == 0


# ---------- 情形三：加密 / 损坏 PDF ----------


def test_import_broken_pdf_fails(library, tmp_path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf at all")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "failed"
    assert doc["fail_reason"] == FAIL_PDF_BROKEN
    assert _chunk_count(library, doc["id"]) == 0


def test_import_encrypted_pdf_fails(library, tmp_path) -> None:
    path = tmp_path / "enc.pdf"
    _write_blank_pdf(path, 1)
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=io.BytesIO(path.read_bytes()))
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    path.write_bytes(out.getvalue())
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "failed"
    assert doc["fail_reason"] == FAIL_PDF_BROKEN


def test_import_missing_file_raises(library, tmp_path) -> None:
    with pytest.raises(LibraryError) as exc:
        library.import_pdf("p1", str(tmp_path / "missing.pdf"))
    assert exc.value.code == "PARSE_ERROR"


def test_import_unsupported_type_raises(library, tmp_path) -> None:
    path = tmp_path / "doc.docx"
    path.write_bytes(b"whatever")
    with pytest.raises(LibraryError) as exc:
        library.import_pdf("p1", str(path))
    assert exc.value.code == "UNSUPPORTED_TYPE"


# ---------- 情形四：截断（资料库独立上限，T04 §6-1） ----------


def test_import_truncated_pdf_keeps_extracted_pages(library, tmp_path, monkeypatch) -> None:
    pages = [(1, "第一章 绪论\n" + "内容" * 500)]
    monkeypatch.setattr("ss.campus.library._read_pdf_with_meta", lambda p: (pages, True, []))
    path = tmp_path / "big.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "ready"
    assert doc["fail_reason"] == FAIL_TRUNCATED
    assert doc["chunk_count"] == 1


# ---------- 切片上限中止（06 §4.2-2 too_many_chunks） ----------


def test_import_too_many_chunks_fails(library, tmp_path, monkeypatch) -> None:
    pages = [(i, f"第{i}章 内容") for i in range(1, 6)]
    monkeypatch.setattr("ss.campus.library._read_pdf_with_meta", lambda p: (pages, False, []))
    monkeypatch.setattr("ss.campus.library.MAX_DOC_CHUNKS", 2)
    path = tmp_path / "huge.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "failed"
    assert doc["fail_reason"] == FAIL_TOO_MANY_CHUNKS
    assert _chunk_count(library, doc["id"]) == 0


# ---------- 删除与文件联动（02 §5.3） ----------


def test_delete_doc_cascades_chunks_and_files(library, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ss.campus.library._read_pdf_with_meta",
        lambda p: ([(1, "第一章 绪论\n内容")], False, []),
    )
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    doc_id = doc["id"]
    doc_dir = tmp_path / "library" / "p1" / doc_id
    assert doc_dir.is_dir()

    assert library.delete_doc("p1", doc_id) is True
    assert _chunk_count(library, doc_id) == 0
    assert library.store.get("source_doc", doc_id) is None
    assert not doc_dir.exists()
    with pytest.raises(LibraryError) as exc:
        library.delete_doc("p1", doc_id)
    assert exc.value.code == "DOC_NOT_FOUND"


def test_delete_doc_of_other_profile_raises(library, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ss.campus.library._read_pdf_with_meta",
        lambda p: ([(1, "第一章 绪论\n内容")], False, []),
    )
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-fake")
    doc = library.import_pdf("p1", str(path))
    with pytest.raises(LibraryError) as exc:
        library.delete_doc("p2", doc["id"])
    assert exc.value.code == "DOC_NOT_FOUND"


# ---------- MD/TXT 导入（06 §4.2-4 伪页） ----------


def test_import_md_creates_pseudo_pages_with_titles(library, tmp_path) -> None:
    md = "# 第一章 绪论\n内容A\n\n## 1.1 背景\n内容B\n\n# 第二章 方法\n内容C"
    path = tmp_path / "notes.md"
    path.write_text(md, encoding="utf-8")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "ready"
    assert doc["file_type"] == "md"
    chunks = library.store.list_rows("doc_chunk", profile_id="p1", order_by="page_no, char_start")
    titles = [chunk["section_title"] for chunk in chunks]
    assert "第一章 绪论" in titles
    assert "1.1 背景" in titles
    assert "第二章 方法" in titles


def test_import_txt_single_page(library, tmp_path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("纯文本内容没有标题", encoding="utf-8")
    doc = library.import_pdf("p1", str(path))
    assert doc["parse_status"] == "ready"
    assert doc["file_type"] == "txt"
    assert doc["chunk_count"] == 1
