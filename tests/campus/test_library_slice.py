"""T08 资料库切片纯函数测试（06 §4.2/§4.3/§8-1 + T04 决策门约束）。

覆盖：pypdf 逐页提取、一页一片 + 超长页二切、section_title 归属（放宽正则 + 页眉过滤）、
3000 片上限中止、200k 截断。纯函数，不依赖模型、不落库。
"""

from __future__ import annotations

import io

import pytest

from ss.campus.library import (
    MAX_CHUNK_CHARS,
    MAX_DOC_CHUNKS,
    MAX_EXTRACT_CHARS,
    PAGE_TITLE_PATTERN,
    TooManyChunks,
    _bookmark_spans,
    extract_section_title,
    is_run_header,
    read_pdf_pages,
    slice_page,
    slice_document,
)


# ---------- read_pdf_pages ----------


def _write_blank_pdf(path, num_pages: int, *, encrypt: str | None = None) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    if encrypt:
        writer.encrypt(encrypt)
    buf = io.BytesIO()
    writer.write(buf)
    path.write_bytes(buf.getvalue())


def test_read_pdf_pages_extracts_each_page(tmp_path) -> None:
    _write_blank_pdf(tmp_path / "doc.pdf", 2)
    pages = read_pdf_pages(str(tmp_path / "doc.pdf"))
    assert len(pages) == 2
    assert pages[0][0] == 1 and pages[1][0] == 2


def test_read_pdf_pages_empty_pages_returned_as_empty_string(tmp_path) -> None:
    _write_blank_pdf(tmp_path / "scan.pdf", 2)
    pages = read_pdf_pages(str(tmp_path / "scan.pdf"))
    assert len(pages) == 2
    assert all(text == "" for _, text in pages)


def test_read_pdf_pages_broken_pdf_returns_empty(tmp_path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf at all")
    assert read_pdf_pages(str(path)) == []


def test_read_pdf_pages_missing_file_returns_empty(tmp_path) -> None:
    assert read_pdf_pages(str(tmp_path / "nope.pdf")) == []


def test_read_pdf_pages_encrypted_pdf_returns_empty(tmp_path) -> None:
    _write_blank_pdf(tmp_path / "enc.pdf", 1, encrypt="secret")
    assert read_pdf_pages(str(tmp_path / "enc.pdf")) == []


# ---------- slice_page ----------


def test_slice_page_short_page_single_chunk() -> None:
    chunks = slice_page("hello world")
    assert len(chunks) == 1
    start, end = chunks[0]
    assert start == 0 and end == 11


def test_slice_page_long_page_split_on_paragraph_boundary() -> None:
    para = "x" * 1500
    text = f"{para}\n\n{para}"
    chunks = slice_page(text)
    assert len(chunks) == 2
    first_start, first_end = chunks[0]
    second_start, second_end = chunks[1]
    assert first_start == 0 and first_end == 1500
    assert second_start == 1502
    assert all(end - start <= MAX_CHUNK_CHARS for start, end in chunks)


def test_slice_page_single_huge_paragraph_hard_split() -> None:
    chunks = slice_page("y" * 5000)
    assert len(chunks) >= 2
    assert all(end - start <= MAX_CHUNK_CHARS for start, end in chunks)
    assert chunks[0][0] == 0


def test_slice_page_empty_text_returns_empty_list() -> None:
    assert slice_page("") == []
    assert slice_page("   \n  ") == []


# ---------- extract_section_title / is_run_header ----------


def test_page_title_pattern_matches_chinese_chapter() -> None:
    assert PAGE_TITLE_PATTERN.match("第三章 数据结构")
    assert PAGE_TITLE_PATTERN.match("第 3 章 数据结构")
    assert PAGE_TITLE_PATTERN.match("第二讲 进程管理")


def test_page_title_pattern_matches_numbered_title() -> None:
    assert PAGE_TITLE_PATTERN.match("2.1 进程的基本概念")
    assert PAGE_TITLE_PATTERN.match("10.3.2 同步与互斥")


def test_page_title_pattern_rejects_long_lines() -> None:
    long_line = "第三章" + "数据" * 30
    assert not PAGE_TITLE_PATTERN.match(long_line)


def test_extract_section_title_returns_first_match() -> None:
    text = "前言\n第二章 排序\n正文内容"
    assert extract_section_title(text, None) == "第二章 排序"


def test_extract_section_title_inherits_from_history_when_no_match() -> None:
    assert extract_section_title("正文段落", "第一章 绪论") == "第一章 绪论"


def test_extract_section_title_returns_none_without_history() -> None:
    assert extract_section_title("正文段落", None) is None


def test_is_run_header_detects_repeated_header() -> None:
    assert is_run_header("第 7 章 树", {1, 2, 3, 4, 5})


def test_is_run_header_passes_for_unique_title() -> None:
    assert not is_run_header("第三章 查找", {1})


# ---------- slice_document ----------


def test_slice_document_one_page_one_chunk() -> None:
    chunks = slice_document([(1, "hello")])
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["page_no"] == 1 and chunk["chunk_seq"] == 0
    assert chunk["content"] == "hello"
    assert chunk["chunk_type"] == "page"
    assert chunk["char_start"] == 0 and chunk["char_end"] == 5
    assert chunk["section_title"] is None
    assert chunk["token_est"] > 0


def test_slice_document_assigns_section_title() -> None:
    pages = [
        (1, "第一章 绪论\n内容"),
        (2, "更多内容"),
        (3, "第二章 排序\n排序正文"),
    ]
    chunks = slice_document(pages)
    titles = {chunk["section_title"] for chunk in chunks}
    assert "第一章 绪论" in titles
    assert "第二章 排序" in titles
    page2 = next(chunk for chunk in chunks if chunk["page_no"] == 2)
    assert page2["section_title"] == "第一章 绪论"


def test_slice_document_long_page_marks_split_type() -> None:
    para = "x" * 1500
    chunks = slice_document([(1, f"{para}\n\n{para}")])
    assert len(chunks) == 2
    assert all(chunk["chunk_type"] == "split" for chunk in chunks)
    assert chunks[0]["chunk_seq"] == 0 and chunks[1]["chunk_seq"] == 1


def test_slice_document_caps_at_3000_chunks() -> None:
    pages = [(i, "x" * 3000) for i in range(1, 2000)]
    with pytest.raises(TooManyChunks):
        slice_document(pages)


def test_slice_document_filters_run_headers() -> None:
    header = "第 7 章 树"
    pages = [(i, f"{header}\n内容{i}") for i in range(1, 6)]
    pages.append((6, "第 8 章 图\n图论"))
    chunks = slice_document(pages)
    page6_title = next(chunk["section_title"] for chunk in chunks if chunk["page_no"] == 6)
    assert page6_title == "第 8 章 图"
    page1_title = next(chunk["section_title"] for chunk in chunks if chunk["page_no"] == 1)
    assert page1_title is None


def test_slice_document_empty_pages_yield_no_chunks() -> None:
    assert slice_document([]) == []
    assert slice_document([(1, ""), (2, "  ")]) == []


# ---------- 书签优先归属（T04 决策二：书签优先、文本行兜底） ----------


def test_slice_document_prefers_bookmarks_over_text_lines() -> None:
    pages = [(1, "第 7 章 树\n内容"), (2, "更多"), (3, "第 8 章 图\n图论")]
    bookmarks = [(0, "第一章 绪论", 1), (0, "第二章 排序", 2)]
    chunks = slice_document(pages, bookmarks=bookmarks)
    titles = {chunk["page_no"]: chunk["section_title"] for chunk in chunks}
    assert titles[1] == "第一章 绪论"
    assert titles[2] == "第二章 排序"
    assert titles[3] == "第二章 排序"


def test_slice_document_falls_back_to_text_lines_without_valid_bookmarks() -> None:
    pages = [(1, "第一章 绪论\n内容"), (2, "更多内容")]
    bookmarks = [(0, "A", 1), (0, "B", 1)]
    chunks = slice_document(pages, bookmarks=bookmarks)
    titles = {chunk["page_no"]: chunk["section_title"] for chunk in chunks}
    assert titles[1] == "第一章 绪论"
    assert titles[2] == "第一章 绪论"


def test_bookmark_spans_survive_same_page_collapse() -> None:
    bookmarks = [
        (0, "第一章 章节甲", 1),
        (1, "1.1 第一节", 2),
        (1, "1.2 第二节", 2),
        (0, "第二章 章节乙", 5),
    ]
    spans = _bookmark_spans(bookmarks, 10)
    table = {title: (start, end) for _level, title, start, end in spans}
    assert table["第一章 章节甲"] == (1, 4)
    assert table["1.1 第一节"] == (2, 4)
    assert table["1.2 第二节"] == (2, 4)
    assert table["第二章 章节乙"] == (5, 10)


def test_bookmark_spans_filter_short_and_out_of_range_items() -> None:
    bookmarks = [(0, "A", 1), (0, "B", 2), (0, "第一章 正常章节", 3), (0, "无效章节", 99)]
    spans = _bookmark_spans(bookmarks, 10)
    assert [title for _level, title, _start, _end in spans] == ["第一章 正常章节"]
