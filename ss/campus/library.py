"""`library.py` — campus 资料库：导入解析、按页切片、三级检索、QA 组装（06 §4/§5）。

职责边界（06 §1）：只做资料导入、按页切片、三级检索与 QA 上下文组装；不做批改、
不落批改结果、**不修改 `ss/pdf_support.py`**。pypdf **逐页**提取（06 §8-1：
`extract_text()` 返回整本文本，页边界在 join 时不可靠，拿不到 `page_no`），与
`pdf_support.py:117` 同款容错（`strict=False`、逐页 try/except、空文本合法）。

切片直接落 02 §4.6 `doc_chunk` 表的行形状（内存侧不另设 dataclass，06 §4.3）：
一页一片（`chunk_type=page`）、单页超 `MAX_CHUNK_CHARS` 按段落边界二切
（`chunk_type=split`，重叠 0，`char_start/char_end` 为全文精确偏移）、单文档
`MAX_DOC_CHUNKS` 片上限（超出中止导入）。`section_title` 归属按 06 §4.2-3 与
T04 决策二执行：标题行放宽正则（容忍空白 + 编号式），同一标题出现在 ≥3 个不同
页面视为运行页眉剔除；无任何标题的文档 `section_title=NULL`，检索自然分流 L2。

本模块自顶向下分三段：解析与切片（纯函数为主，06 §4）、检索（06 §5）、
导入/删除等 store 侧编排放最后。
"""

from __future__ import annotations

import io
import math
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 常量（06 §4.2 / T04 决策门 §6）
# ---------------------------------------------------------------------------

MAX_CHUNK_CHARS = 2000
MAX_DOC_CHUNKS = 3000
MAX_EXTRACT_CHARS = 200_000
MAX_TITLE_CHARS = 40
RUN_HEADER_MIN_PAGES = 3

_TITLE_BODY = (
    r"(?:第\s*[一二三四五六七八九十百零\d]+\s*[章讲部分节篇]"
    r"|Chapter\s+\S+"
    r"|\d+(?:\.\d+)*\s+\S)"
)
PAGE_TITLE_PATTERN = re.compile(rf"^(?=.{{0,{MAX_TITLE_CHARS}}}$)\s*{_TITLE_BODY}\S?.*$")

_PARAGRAPH_GAP = re.compile(r"\n\s*\n")
_URL_PART = re.compile(r"(?:https?://\S+|www\.\S+)")
_TRAILING_NUMBERS = re.compile(r"[\d\s]+$")


class TooManyChunks(Exception):
    """切片数超过 `MAX_DOC_CHUNKS`，导入中止（06 §4.2-2 `fail_reason=too_many_chunks`）。"""


def _title_stem(title: str) -> str:
    cleaned = _URL_PART.sub("", title)
    return _TRAILING_NUMBERS.sub("", cleaned).strip()


# ---------------------------------------------------------------------------
# 解析与切片（06 §4.2）
# ---------------------------------------------------------------------------


def read_pdf_pages(path: str) -> list[tuple[int, str]]:
    """pypdf 逐页提取，返回 `(page_no, text)`（1 起页码）。

    与 `pdf_support.extract_text()` 同款容错：`strict=False` 打开、逐页 try/except、
    空文本合法（扫描件）。无法读取（缺文件/损坏/带口令）返回空列表——判空分支在
    `import_pdf` 里落 `fail_reason=pdf_broken`，这里不静默吞掉任何中间页。
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(Path(path).read_bytes()), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return []
        pages: list[tuple[int, str]] = []
        total = 0
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append((index, text))
            total += len(text)
            if total >= MAX_EXTRACT_CHARS:
                break
        return pages
    except Exception:
        return []


def slice_page(text: str) -> list[tuple[int, int]]:
    """一页 → `(char_start, char_end)` 偏移对（相对本页文本，重叠 0，06 §4.2-2）。

    短页整页一片；超长页按段落边界（`\\n\\s*\\n`）聚合到 `MAX_CHUNK_CHARS`，单段
    超长则硬切。偏移对保真：`content` 永远等于原文区间，不做摘要与空白重排。
    """
    if not text or not text.strip():
        return []
    if len(text) <= MAX_CHUNK_CHARS:
        return [(0, len(text))]
    paragraphs: list[tuple[int, int]] = []
    cursor = 0
    for match in _PARAGRAPH_GAP.finditer(text):
        if match.start() > cursor:
            paragraphs.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        paragraphs.append((cursor, len(text)))
    spans: list[tuple[int, int]] = []
    open_start: Optional[int] = None
    open_end = 0
    for start, end in paragraphs:
        if end - start > MAX_CHUNK_CHARS:
            if open_start is not None:
                spans.append((open_start, open_end))
                open_start = None
            offset = start
            while offset < end:
                spans.append((offset, min(offset + MAX_CHUNK_CHARS, end)))
                offset += MAX_CHUNK_CHARS
            continue
        if open_start is None:
            open_start, open_end = start, end
        elif end - open_start <= MAX_CHUNK_CHARS:
            open_end = end
        else:
            spans.append((open_start, open_end))
            open_start, open_end = start, end
    if open_start is not None:
        spans.append((open_start, open_end))
    return spans or [(0, len(text))]


def extract_section_title(text: str, history: Optional[str]) -> Optional[str]:
    """本页文本中第一条标题行；找不到则继承上游标题（06 §4.2-3）。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and PAGE_TITLE_PATTERN.match(stripped):
            return stripped
    return history


def is_run_header(title: str, pages_seen: set[int]) -> bool:
    """同一标题出现在 ≥`RUN_HEADER_MIN_PAGES` 个不同页面 → 运行页眉（T04 决策二）。"""
    return len(pages_seen) >= RUN_HEADER_MIN_PAGES


def slice_document(pages: list[tuple[int, str]]) -> list[dict]:
    """页文本序列 → `doc_chunk` 行 dict 列表（02 §4.6 形状，06 §4.3）。

    `section_title` 取"自文档开头到该片为止最近一次匹配的标题行"（行偏移 ≤ 片
    全文起始偏移；页内偏移精确继承），运行页眉剔除后不参与归属。超出
    `MAX_DOC_CHUNKS` 抛 `TooManyChunks` 中止导入。
    """
    page_offsets: dict[int, int] = {}
    offset = 0
    for page_no, text in pages:
        page_offsets[page_no] = offset
        offset += len(text)

    candidates: list[tuple[int, int, str]] = []
    pages_by_title: dict[str, set[int]] = {}
    for page_no, text in pages:
        base = page_offsets[page_no]
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or not PAGE_TITLE_PATTERN.match(stripped):
                continue
            line_offset = base + text.find(line)
            candidates.append((line_offset, page_no, stripped))
            pages_by_title.setdefault(_title_stem(stripped), set()).add(page_no)

    kept = [
        (line_offset, page_no, title)
        for line_offset, page_no, title in candidates
        if not is_run_header(title, pages_by_title[_title_stem(title)])
    ]

    chunks: list[dict] = []
    global_offset = 0
    history: Optional[str] = None
    for page_no, text in pages:
        for seq, (start, end) in enumerate(slice_page(text)):
            if len(chunks) >= MAX_DOC_CHUNKS:
                raise TooManyChunks(
                    f"document exceeds {MAX_DOC_CHUNKS} chunks (fail_reason=too_many_chunks)"
                )
            piece_start = global_offset + start
            title = history
            for line_offset, _page_no, line_title in kept:
                if line_offset <= piece_start:
                    title = line_title
                else:
                    break
            history = title
            content = text[start:end]
            chunks.append(
                {
                    "doc_id": "",
                    "page_no": page_no,
                    "chunk_seq": seq,
                    "chunk_type": "page" if len(slice_page(text)) == 1 else "split",
                    "section_title": title,
                    "content": content,
                    "char_start": piece_start,
                    "char_end": piece_start + (end - start),
                    "token_est": _token_estimate(content),
                }
            )
        global_offset += len(text)
    return chunks


def _token_estimate(text: str) -> int:
    """估算 token 数：中文 ≈ 字符数，英文 ≈ /4（02 §4.6）。"""
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return cjk + (len(text) - cjk) // 4
