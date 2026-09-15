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
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..secrets import state_dir
from . import models
from .store import CampusStore

# ---------------------------------------------------------------------------
# 常量（06 §4.2 / T04 决策门 §6）
# ---------------------------------------------------------------------------

MAX_CHUNK_CHARS = 2000
MAX_DOC_CHUNKS = 3000
MAX_EXTRACT_CHARS = 200_000
MAX_TITLE_CHARS = 40
RUN_HEADER_MIN_PAGES = 3
BLANK_PAGE_FAIL_RATIO = 0.8

# 扫描件与异常分支的 `fail_reason` 值域（06 §6.1；截断按 T04 §6-1 的资料库独立上限口径）
FAIL_NO_TEXT_LAYER = "no_text_layer"
FAIL_PDF_BROKEN = "pdf_broken"
FAIL_TRUNCATED = "truncated_2m"
FAIL_TOO_MANY_CHUNKS = "too_many_chunks"

# 检索（06 §5.1；T04 §6-4：2-gram 必须 IDF 加权；L1 置信度不足回退全库）
DEFAULT_TOP_K = 6
MAX_KEYWORDS = 32
FTS_MIN_TERM_CHARS = 3
L1_MIN_SECTION_RATIO = 0.5
TOC_MAX_LINES = 200
ROUTER_MAX_SECTIONS = 3
RETRIEVAL_TIMEOUT_S = 90

# 02 §5.2：V0.1 默认启用 L1 + L2b（LIKE，零探测成本）；trigram FTS 是可选加速档，
# 显式 `enable_fts=True` 时才探测 `ENABLE_FTS5` 并建虚表，探测/建表/运行时任何一步
# 失败都自动退回 LIKE——两态对上层透明（T08 验收③）。
FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunk_fts USING "
    "fts5(content, content='doc_chunk', content_rowid='rowid', tokenize='trigram')"
)
FTS_TRIGGER_DDLS = (
    "CREATE TRIGGER IF NOT EXISTS doc_chunk_fts_ai AFTER INSERT ON doc_chunk BEGIN "
    "INSERT INTO doc_chunk_fts(rowid, content) VALUES (new.rowid, new.content); END",
    "CREATE TRIGGER IF NOT EXISTS doc_chunk_fts_ad AFTER DELETE ON doc_chunk BEGIN "
    "INSERT INTO doc_chunk_fts(doc_chunk_fts, rowid, content) "
    "VALUES ('delete', old.rowid, old.content); END",
)

_FILE_TYPES = {
    ".pdf": models.DocFileType.PDF.value,
    ".md": models.DocFileType.MD.value,
    ".txt": models.DocFileType.TXT.value,
}

_TITLE_BODY = (
    r"(?:第\s*[一二三四五六七八九十百零\d]+\s*[章讲部分节篇]"
    r"|Chapter\s+\S+"
    r"|\d+(?:\.\d+)*\s+\S)"
)
PAGE_TITLE_PATTERN = re.compile(rf"^(?=.{{0,{MAX_TITLE_CHARS}}}$)\s*{_TITLE_BODY}\S?.*$")

_PARAGRAPH_GAP = re.compile(r"\n\s*\n")
_URL_PART = re.compile(r"(?:https?://\S+|www\.\S+)")
_TRAILING_NUMBERS = re.compile(r"[\d\s]+$")
_MD_HEADING = re.compile(r"^(#{1,3})\s+(\S.*)$")
_MD_HEADING_TOP = re.compile(r"^#{1,3}\s+", re.M)


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
    return _read_pdf_with_meta(path)[0]


def _read_pdf_with_meta(path: str) -> tuple[list[tuple[int, str]], bool]:
    """`read_pdf_pages` 的完整形态：附带截断标记（T04 §6-1 资料库独立上限）。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(Path(path).read_bytes()), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return [], False
        pages: list[tuple[int, str]] = []
        total = 0
        truncated = False
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append((index, text))
            total += len(text)
            if total >= MAX_EXTRACT_CHARS:
                truncated = True
                break
        return pages, truncated
    except Exception:
        return [], False


def _read_text_pages(path: Path) -> list[tuple[int, str]]:
    """MD/TXT 按 `\\n#{1,3} ` 标题切伪页（06 §4.2-4）；无标题整文一页。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    matches = list(_MD_HEADING_TOP.finditer(text))
    if not matches:
        return [(1, text)]
    page_texts: list[str] = []
    if matches[0].start() > 0:
        page_texts.append(text[: matches[0].start()])
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_texts.append(text[match.start() : end])
    return [(order + 1, page) for order, page in enumerate(page_texts)]


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


def slice_document(pages: list[tuple[int, str]], *, markdown: bool = False) -> list[dict]:
    """页文本序列 → `doc_chunk` 行 dict 列表（02 §4.6 形状，06 §4.3）。

    `section_title` 取"自文档开头到该片为止最近一次匹配的标题行"（行偏移 ≤ 片
    全文起始偏移；页内偏移精确继承），运行页眉剔除后不参与归属。超出
    `MAX_DOC_CHUNKS` 抛 `TooManyChunks` 中止导入。`markdown=True` 时标题行改用
    `#{1,3}` 形式（MD 伪页，06 §4.2-4），`section_title` 取剥掉井号后的标题文本。
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
            if not stripped:
                continue
            if markdown:
                match = _MD_HEADING.match(stripped)
                title_text = match.group(2).strip() if match else ""
            else:
                title_text = stripped if PAGE_TITLE_PATTERN.match(stripped) else ""
            if not title_text or len(title_text) > MAX_TITLE_CHARS:
                continue
            line_offset = base + text.find(line)
            candidates.append((line_offset, page_no, title_text))
            pages_by_title.setdefault(_title_stem(title_text), set()).add(page_no)

    kept = [
        (line_offset, page_no, title)
        for line_offset, page_no, title in candidates
        if not is_run_header(title, pages_by_title[_title_stem(title)])
    ]

    chunks: list[dict] = []
    global_offset = 0
    history: Optional[str] = None
    for page_no, text in pages:
        page_spans = slice_page(text)
        for seq, (start, end) in enumerate(page_spans):
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
                    "chunk_type": "page" if len(page_spans) == 1 else "split",
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


# ---------------------------------------------------------------------------
# 关键词抽取与评分（06 §5.1 L2；实现逐字对齐 T02 spike `extract_terms`，
# T04 决策二：T08 落地沿用 spike 已验证的实现，无新设计）
# ---------------------------------------------------------------------------

_CJK_STOPCHARS = frozenset(
    "的了和与及或在是为对从到把被让给并且但而所以就都可以需要那这我们你们他它好么"
    "很更最多少上下着过之其此该等如什怎哪"
)
_WORD_STOPWORDS = frozenset(
    "the a an of in on at to for and or is are was were be been what which how why "
    "does do did can could should would will shall this that these those it its".split()
)
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]*|\d+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def extract_keywords(query: str) -> list[str]:
    """问题 → 关键词序列：拉丁词元优先，中文在原文上滑窗取 2-gram（06 §5.1）。

    含停用字的窗口整窗跳过——不在停用字处拼接，避免产出"反传"这类跨虚词的
    假 gram；停用字表与拉丁词规则逐字沿用 T02 spike 的 `extract_terms`。
    """
    keywords: list[str] = []
    for token in _LATIN_WORD.findall(query or ""):
        lowered = token.lower()
        if len(lowered) > 1 and lowered not in _WORD_STOPWORDS and lowered not in keywords:
            keywords.append(lowered)
    for run in _CJK_RUN.findall(query or ""):
        if len(run) == 1:
            if run not in _CJK_STOPCHARS and run not in keywords:
                keywords.append(run)
            continue
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram[0] in _CJK_STOPCHARS or bigram[1] in _CJK_STOPCHARS:
                continue
            if bigram not in keywords:
                keywords.append(bigram)
    return keywords[:MAX_KEYWORDS]


def score_chunk(content: str, keywords: list[str], idf: dict[str, float]) -> float:
    """命中词 IDF 加权 + 首次命中位置评分（T02 §3 的 L2 评分口径）。"""
    haystack = content.lower()
    total = 0.0
    length = max(len(content), 1)
    for keyword in keywords:
        position = haystack.find(keyword.lower())
        if position < 0:
            continue
        weight = idf.get(keyword, 0.0)
        hits = haystack.count(keyword.lower())
        total += weight * (1 + min(hits, 3))
        total += weight * (1 - position / length)
    return total


def _idf_of(total: int, doc_freq: int) -> float:
    return math.log(1 + total / (1 + doc_freq))


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# CampusLibrary：导入 / 重试 / 删除（06 §4.1 + 03 §4.2 B1/B3/B4/B5 库层）
# ---------------------------------------------------------------------------


class LibraryError(Exception):
    """资料库领域错误；`code` 对应 03 §6 错误码表，端点层据此映射 HTTP 错误体。"""

    def __init__(self, code: str, message: Optional[str] = None, **extra: object) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.extra = extra


class _ParseFailure(Exception):
    """解析阶段的内部失败信号，`_parse_into` 捕获后落 `parse_status=failed`。"""

    def __init__(self, reason: str, page_count: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.page_count = page_count


class CampusLibrary:
    """`campus/library/<profile_id>/<doc_id>/` 的库层句柄（02 §1.1 目录布局）。

    `provider`/`model_picker` 供检索 L1 章节路由与 `answer_qa` 复用批改同款
    provider 链路（06 §4.1；T08 接口先行，注入即用）。
    """

    def __init__(
        self,
        store: CampusStore,
        lib_dir: Optional[Path] = None,
        provider: Optional[object] = None,
        model_picker: Optional[Callable[[str, str], tuple[str, str]]] = None,
        *,
        enable_fts: bool = False,
    ) -> None:
        self.store = store
        self._lib_dir = Path(lib_dir) if lib_dir is not None else (state_dir() / "campus" / "library")
        self._provider = provider
        self._model_picker = model_picker
        self._fts_ready = bool(enable_fts) and self._detect_fts5() and self._ensure_fts_table()

    # ---- 导入（B1 库层：落盘 + 建行 + 同步解析，06 §6.1 判定时机） ----

    def import_pdf(self, profile_id: str, file_path: str) -> dict:
        src = Path(file_path)
        if not src.is_file():
            raise LibraryError("PARSE_ERROR", f"文件不存在：{src}")
        file_type = _FILE_TYPES.get(src.suffix.lower())
        if file_type is None:
            raise LibraryError("UNSUPPORTED_TYPE", f"不支持的文件类型：{src.suffix}")
        doc_id = self.store.new_id()
        dest_dir = self._lib_dir / profile_id / doc_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        self.store.insert(
            "source_doc",
            {
                "id": doc_id,
                "profile_id": profile_id,
                "title": src.stem,
                "file_path": f"{doc_id}/{src.name}",
                "file_type": file_type,
                "parse_status": models.ParseStatus.PENDING.value,
                "imported_at": _utcnow(),
            },
        )
        self._parse_into(doc_id, profile_id, dest, file_type)
        return dict(self.store.get("source_doc", doc_id))

    # ---- 重试（B5：扫描件幂等拒绝，不再烧解析；06 §6.1） ----

    def retry_parse(self, profile_id: str, doc_id: str) -> dict:
        row = self.store.get_scoped("source_doc", doc_id, profile_id)
        if row is None:
            raise LibraryError("DOC_NOT_FOUND", f"资料不存在：{doc_id}")
        doc = models.SourceDoc.from_row(row)
        if doc.parse_status == models.ParseStatus.READY.value:
            return dict(row)
        if doc.parse_status == models.ParseStatus.FAILED.value and doc.fail_reason == FAIL_NO_TEXT_LAYER:
            raise LibraryError("DOC_SCAN_EMPTY", "扫描件无可提取文字层，请转文字版后重新导入")
        path = self._doc_path(profile_id, doc)
        if path is None:
            raise LibraryError("DOC_NOT_FOUND", f"资料文件已丢失：{doc_id}")
        with self.store.transaction():
            self.store.delete_where("doc_chunk", "doc_id = ?", (doc_id,))
            self.store.update(
                "source_doc",
                doc_id,
                {
                    "parse_status": models.ParseStatus.PENDING.value,
                    "fail_reason": None,
                    "chunk_count": 0,
                    "char_count": 0,
                },
            )
        self._parse_into(doc_id, profile_id, path, doc.file_type or "pdf")
        return dict(self.store.get("source_doc", doc_id))

    # ---- 删除（B4：级联 chunk + 文件，顺序按 02 §5.3） ----

    def delete_doc(self, profile_id: str, doc_id: str) -> bool:
        row = self.store.get_scoped("source_doc", doc_id, profile_id)
        if row is None:
            raise LibraryError("DOC_NOT_FOUND", f"资料不存在：{doc_id}")
        with self.store.transaction():
            self.store.delete_where("doc_chunk", "doc_id = ?", (doc_id,))
            self.store.delete("source_doc", doc_id)
        shutil.rmtree(self._lib_dir / profile_id / doc_id, ignore_errors=True)
        return True

    # ---- 解析状态机 ----

    def _parse_into(self, doc_id: str, profile_id: str, path: Path, file_type: str) -> None:
        truncated = False
        pages: list[tuple[int, str]] = []
        try:
            if file_type == models.DocFileType.PDF.value:
                pages, truncated = _read_pdf_with_meta(str(path))
                if not pages:
                    raise _ParseFailure(FAIL_PDF_BROKEN, 0)
            else:
                pages = _read_text_pages(path)
                if not any(text.strip() for _, text in pages):
                    raise _ParseFailure(FAIL_NO_TEXT_LAYER, len(pages))
            slices = slice_document(pages, markdown=file_type != models.DocFileType.PDF.value)
            page_count = len(pages)
            char_count = sum(len(text) for _, text in pages)
            blank = sum(1 for _, text in pages if not text.strip())
            if char_count == 0 or (page_count and blank / page_count > BLANK_PAGE_FAIL_RATIO):
                raise _ParseFailure(FAIL_NO_TEXT_LAYER, page_count)
        except TooManyChunks:
            self._mark_failed(doc_id, FAIL_TOO_MANY_CHUNKS, len(pages))
            return
        except _ParseFailure as exc:
            self._mark_failed(doc_id, exc.reason, exc.page_count)
            return
        with self.store.transaction():
            self._insert_chunks(doc_id, profile_id, slices)
            self.store.update(
                "source_doc",
                doc_id,
                {
                    "parse_status": models.ParseStatus.READY.value,
                    "fail_reason": FAIL_TRUNCATED if truncated else None,
                    "page_count": page_count,
                    "chunk_count": len(slices),
                    "char_count": char_count,
                },
            )

    def _mark_failed(self, doc_id: str, reason: str, page_count: int) -> None:
        self.store.update(
            "source_doc",
            doc_id,
            {
                "parse_status": models.ParseStatus.FAILED.value,
                "fail_reason": reason,
                "page_count": page_count,
                "chunk_count": 0,
                "char_count": 0,
            },
        )

    def _insert_chunks(self, doc_id: str, profile_id: str, slices: list[dict]) -> None:
        now = _utcnow()
        rows = [
            (
                self.store.new_id(),
                doc_id,
                profile_id,
                piece["page_no"],
                piece["content"],
                piece["chunk_type"],
                piece["section_title"],
                piece["char_start"],
                piece["char_end"],
                piece["token_est"],
                now,
            )
            for piece in slices
        ]
        self.store.executemany(
            'INSERT INTO "doc_chunk" ("id", "doc_id", "profile_id", "page_no", "content", '
            '"chunk_type", "section_title", "char_start", "char_end", "token_est", "created_at") '
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    def _doc_path(self, profile_id: str, doc: models.SourceDoc) -> Optional[Path]:
        path = self._lib_dir / profile_id / (doc.file_path or "")
        return path if path.is_file() else None

    # ---- 检索（06 §5.1：L2 关键词召回 / L3 全扫兜底；L1 目录路由见下） ----

    def retrieve(
        self,
        profile_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        doc_id: Optional[str] = None,
    ) -> list[dict]:
        """三级检索的统一入口（06 §5.1；L1 目录路由在 `_search` 的 `sections` 限域内）。

        返回 `[{doc_id, page_no, chunk_seq, section_title, content, score}]`（06 §4.1）。
        """
        if doc_id is not None:
            row = self.store.get_scoped("source_doc", doc_id, profile_id)
            if row is None:
                return []
            doc = models.SourceDoc.from_row(row)
            if doc.parse_status != models.ParseStatus.READY.value:
                return []
        chunks, _used = self._search(profile_id, query, doc_id=doc_id, top_k=top_k)
        return chunks

    def _search(
        self,
        profile_id: str,
        query: str,
        *,
        doc_id: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
        sections: Optional[list[str]] = None,
    ) -> tuple[list[dict], str]:
        """L2/L3 关键词召回，返回 `(chunks, used_retrieval)`（06 §5.1 输出标记）。"""
        keywords = extract_keywords(query)
        if not keywords:
            return [], "toc_route" if sections else "keyword"
        scope, params = self._scope(profile_id, doc_id, sections)
        rows = self._candidate_rows(scope, params, keywords)
        if not rows:
            return [], "toc_route" if sections else "keyword"
        idf = self._idf(scope, params, keywords)
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            score = score_chunk(row["content"], keywords, idf)
            if score > 0:
                scored.append((score, row))
        scored.sort(
            key=lambda item: (
                -item[0],
                item[1]["doc_id"],
                item[1]["page_no"],
                item[1]["char_start"],
            )
        )
        return [self._chunk_dict(row, score) for score, row in scored[:top_k]], (
            "toc_route" if sections else "keyword"
        )

    def _scope(
        self,
        profile_id: str,
        doc_id: Optional[str],
        sections: Optional[list[str]],
    ) -> tuple[str, list]:
        """检索域 SQL（白名单片段拼装，值全部参数化）：doc 限域 / 档案全扫 / L1 限域。"""
        if doc_id is not None:
            scope, params = '"doc_id" = ?', [doc_id]
        else:
            scope, params = '"profile_id" = ?', [profile_id]
        if sections:
            placeholders = ", ".join("?" for _ in sections)
            scope += f' AND "section_title" IN ({placeholders})'
            params = params + list(sections)
        return scope, params

    def _candidate_rows(self, scope: str, params: list, keywords: list[str]) -> list[sqlite3.Row]:
        """候选行：FTS 加速档就绪且存在长词元时走 MATCH，否则 LIKE 全扫兜底。"""
        if self._fts_ready:
            terms = [keyword for keyword in keywords if len(keyword) >= FTS_MIN_TERM_CHARS]
            if terms:
                try:
                    return self._fts_match(terms, scope, params)
                except Exception:
                    self._fts_ready = False
        likes = " OR ".join('"content" LIKE ?' for _ in keywords)
        sql = f'SELECT * FROM "doc_chunk" WHERE {scope} AND ({likes})'
        return self.store.query_all(sql, (*params, *[f"%{keyword}%" for keyword in keywords]))

    def _fts_match(self, terms: list[str], scope: str, params: list) -> list[sqlite3.Row]:
        match = " OR ".join(f'"{term}"' for term in terms)
        sql = (
            'SELECT * FROM "doc_chunk" WHERE rowid IN '
            "(SELECT rowid FROM doc_chunk_fts WHERE doc_chunk_fts MATCH ?) "
            f"AND {scope}"
        )
        return self.store.query_all(sql, (match, *params))

    def _idf(self, scope: str, params: list, keywords: list[str]) -> dict[str, float]:
        total = self.store.scalar(f'SELECT COUNT(*) FROM "doc_chunk" WHERE {scope}', params) or 0
        idf: dict[str, float] = {}
        for keyword in keywords:
            doc_freq = self.store.scalar(
                f'SELECT COUNT(*) FROM "doc_chunk" WHERE {scope} AND "content" LIKE ?',
                (*params, f"%{keyword}%"),
            )
            idf[keyword] = _idf_of(total, doc_freq or 0)
        return idf

    def _chunk_dict(self, row: sqlite3.Row, score: float) -> dict:
        """检索行 → 06 §4.1 返回形状；`chunk_seq` 取页内切片序（与导入一致）。"""
        chunk_seq = self.store.scalar(
            'SELECT COUNT(*) FROM "doc_chunk" WHERE "doc_id" = ? AND "page_no" = ? '
            'AND "char_start" < ?',
            (row["doc_id"], row["page_no"], row["char_start"]),
        )
        return {
            "doc_id": row["doc_id"],
            "page_no": row["page_no"],
            "chunk_seq": int(chunk_seq or 0),
            "section_title": row["section_title"],
            "content": row["content"],
            "score": score,
        }

    # ---- FTS5 加速档（02 §5.2 L2a；探测/建表/运行时失败均退回 LIKE） ----

    def _detect_fts5(self) -> bool:
        try:
            options = self.store.query_all("PRAGMA compile_options")
        except Exception:
            return False
        return any("ENABLE_FTS5" in str(row[0]) for row in options)

    def _ensure_fts_table(self) -> bool:
        try:
            self.store.execute(FTS_DDL)
            for ddl in FTS_TRIGGER_DDLS:
                self.store.execute(ddl)
            self.store.execute("INSERT INTO doc_chunk_fts(doc_chunk_fts) VALUES('rebuild')")
            return True
        except Exception:
            return False
