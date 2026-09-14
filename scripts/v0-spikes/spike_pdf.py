"""SPIKE-2 / T02：中文 PDF 按页召回验证（V0.0 临时脚本，非入库代码）。

实现依据 docs/dev/06-批改与检索引擎设计.md：
  §4.2 按页切片（pypdf 逐页提取、一页一片、超长页二切、章节标题归属）
  §4.3 Chunk 数据契约
  §5   三级检索（L1 目录路由 / L2 关键词召回 / L3 全扫兜底）
  §6.1 扫描件与异常分支（no_text_layer / pdf_broken / truncated_200k 判空分支）
  §8-1 pypdf 逐页直接提取，pdf_support.py 零修改
量化口径依据 docs/dev/08-测试与验收方案.md §3.2。

目录来源（--toc-source）：
  text    — 06 §4.2-3 口径：由页文本行正则抽出 section_title 后聚合
  outline — 08 §3.2 兜底口径：直接采用 PDF 书签（L1 仅限书签完整文档）

用法：
  python scripts/v0-spikes/spike_pdf.py --corpus scripts/v0-spikes/corpus \
      --questions scripts/v0-spikes/spike_pdf_questions.json --out scripts/v0-spikes/out \
      --profile spec --toc-source text --router heuristic
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field

MAX_EXTRACT_CHARS = 200_000
CHUNK_MAX_CHARS = 2000
MAX_CHUNKS = 3000
BLANK_PAGE_RATIO = 0.8
HEADING_MAX_LEN = 40
DEFAULT_TOP_K = 6
QA_CHAR_BUDGET = 12_000
L1_MIN_TITLED_RATIO = 0.5
ROUTER_MAX_SECTIONS = 3
TOC_PAGE_SCAN_LIMIT = 40
REPEAT_MIN_PAGES = 3

SPEC_HEADING = re.compile(
    r"^\s*(第[一二三四五六七八九十\d]+[章讲部分节]|Chapter|章节编号\s+\S)"
)
RELAXED_HEADING = re.compile(
    r"^\s*(第\s*[一二三四五六七八九十百零\d]+\s*[章讲部分节篇]"
    r"|[Cc]hapter\s*\d+"
    r"|\d+(?:\.\d+)*\s+\S)"
)
HEADING_PROFILES = {"spec": SPEC_HEADING, "relaxed": RELAXED_HEADING}
TOC_PAGE_RE = re.compile(r"^\s*目\s*录\s*$")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]*|\d+")
CJK_STOPCHARS = frozenset(
    "的了和与及或在是为对从到把被让给并且但而所以就都可以需要那这我们你们他它好么"
    "很更最多少上下着过之其此该等如什怎哪"
)
WORD_STOPWORDS = frozenset(
    "the a an of in on at to for and or is are was were be been what which how why "
    "does do did can could should would will shall this that these those it its".split()
)


def normalize_title(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = re.sub(r"\s+", "", s)
    return s.strip("　·:：.。、,，-—_").lower()


def heading_stem(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"[^\u4e00-\u9fff]+", "", s)


def title_matches(extracted: str, expected: str) -> bool:
    a, b = normalize_title(extracted), normalize_title(expected)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def extract_terms(query: str, max_terms: int = 32) -> list[str]:
    terms: list[str] = []
    for token in LATIN_RUN.findall(query or ""):
        low = token.lower()
        if len(low) > 1 and low not in WORD_STOPWORDS:
            terms.append(low)
    for run in CJK_RUN.findall(query or ""):
        if len(run) == 1:
            if run not in CJK_STOPCHARS:
                terms.append(run)
            continue
        for i in range(len(run) - 1):
            bigram = run[i : i + 2]
            if bigram[0] in CJK_STOPCHARS or bigram[1] in CJK_STOPCHARS:
                continue
            terms.append(bigram)
    seen: dict[str, None] = {}
    for term in terms:
        seen.setdefault(term, None)
    return list(seen)[:max_terms]


def term_weights(
    chunks: list[dict], terms: list[str], restrict_pages: set[int] | None = None
) -> tuple[int, dict[str, float]]:
    total = 0
    df = {term: 0 for term in terms}
    for chunk in chunks:
        if restrict_pages is not None and chunk["page_no"] not in restrict_pages:
            continue
        total += 1
        content = chunk["content"]
        lowered = content.lower()
        for term in terms:
            if term in content or term.lower() in lowered:
                df[term] += 1
    weights = {
        term: math.log((total + 1) / (df[term] + 1)) + 1.0 for term in terms
    }
    return total, weights


def score_chunk(
    content: str, terms: list[str], weights: dict[str, float] | None = None
) -> tuple[float, list[str]]:
    if not content:
        return 0.0, []
    matched: list[str] = []
    first_pos = None
    for term in terms:
        pos = content.find(term)
        if pos < 0:
            pos = content.lower().find(term.lower())
        if pos >= 0:
            matched.append(term)
            if first_pos is None or pos < first_pos:
                first_pos = pos
    if not matched:
        return 0.0, []
    weight = sum((weights or {}).get(term, 1.0) for term in matched)
    return round(weight + (1.0 - first_pos / max(1, len(content))), 4), matched


def page_pieces(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[tuple[int, str]]:
    if not text:
        return []
    if len(text) <= max_chars:
        return [(0, text)]
    paragraphs: list[tuple[int, str]] = []
    for match in re.finditer(r"[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*", text):
        para = match.group(0)
        if para.strip() == "":
            continue
        start = match.start()
        while len(para) > max_chars:
            paragraphs.append((start, para[:max_chars]))
            para = para[max_chars:]
            start += max_chars
        paragraphs.append((start, para))
    pieces: list[tuple[int, str]] = []
    cur_start = None
    cur = ""
    for start, para in paragraphs:
        if cur_start is None:
            cur_start, cur = start, para
            continue
        if len(cur) + 1 + len(para) <= max_chars:
            cur = cur + "\n" + para
        else:
            pieces.append((cur_start, cur))
            cur_start, cur = start, para
    if cur_start is not None:
        pieces.append((cur_start, cur))
    return pieces


def heading_hits(text: str, profile: str) -> list[tuple[int, str]]:
    pattern = HEADING_PROFILES[profile]
    hits: list[tuple[int, str]] = []
    offset = 0
    for line in (text or "").splitlines(keepends=True):
        stripped = line.strip()
        if stripped and len(stripped) <= HEADING_MAX_LEN and pattern.match(line):
            hits.append((offset, stripped))
        offset += len(line)
    return hits


@dataclass
class DocExtract:
    doc_id: str
    file: str
    pages: list[str] = field(default_factory=list)
    total_pages: int = 0
    chars_total: int = 0
    blank_pages: list[int] = field(default_factory=list)
    truncated: bool = False
    status: str = "ready"
    fail_reason: str | None = None
    outline_items: int = 0
    outline_toc: list[dict] = field(default_factory=list)
    has_toc_page: bool = False
    elapsed_ms: int = 0


def _load_reader(path: pathlib.Path):
    from pypdf import PdfReader

    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted:
        reader.decrypt("")
    return reader


def outline_entries(reader, max_depth: int = 1) -> list[dict]:
    entries: list[dict] = []

    def walk(items, depth: int = 0) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            title = getattr(item, "title", None)
            if title is None and isinstance(item, dict):
                title = item.get("/Title")
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                page = None
            if title and page and depth <= max_depth:
                entries.append(
                    {"section_title": str(title).strip(), "page_no": page, "depth": depth}
                )

    try:
        walk(reader.outline)
    except Exception:
        return []
    return entries


def cap_page_text(text: str, running_total: int, max_chars: int = MAX_EXTRACT_CHARS) -> tuple[str, bool]:
    remain = max_chars - running_total
    if len(text) > remain:
        return text[: max(0, remain)], True
    return text, False


def classify_extract(
    page_count: int, text_pages: int, chars_total: int, truncated: bool
) -> tuple[str, str | None]:
    if chars_total == 0 or (page_count and text_pages == 0):
        return "failed", "no_text_layer"
    if page_count and (page_count - text_pages) / page_count > BLANK_PAGE_RATIO:
        return "failed", "no_text_layer"
    if truncated:
        return "ready", "truncated_200k"
    return "ready", None


def extract_document(doc_id: str, path: pathlib.Path, outline_max_depth: int = 1) -> DocExtract:
    started = time.perf_counter()
    out = DocExtract(doc_id=doc_id, file=path.name)
    try:
        reader = _load_reader(path)
    except Exception:
        out.status, out.fail_reason = "failed", "pdf_broken"
        out.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return out
    out.total_pages = len(reader.pages)
    try:
        out.outline_items = len(reader.outline)
    except Exception:
        out.outline_items = 0
    out.outline_toc = outline_entries(reader, max_depth=outline_max_depth)
    total = 0
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text, hit_cap = cap_page_text(text, total)
        if hit_cap:
            out.truncated = True
        out.pages.append(text)
        total += len(text)
        if text == "":
            out.blank_pages.append(index + 1)
        elif (index + 1) <= TOC_PAGE_SCAN_LIMIT and any(
            TOC_PAGE_RE.match(line) for line in text.splitlines()
        ):
            out.has_toc_page = True
        if total >= MAX_EXTRACT_CHARS:
            out.truncated = True
            break
    out.chars_total = total
    text_pages = len(out.pages) - len(out.blank_pages)
    out.status, out.fail_reason = classify_extract(
        len(out.pages), text_pages, total, out.truncated
    )
    out.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return out


def slice_document(pages: list[str], profile: str) -> tuple[list[dict], str | None]:
    chunks: list[dict] = []
    current_title: str | None = None
    for page_index, text in enumerate(pages):
        page_no = page_index + 1
        hits = heading_hits(text, profile)
        for seq, (start, piece) in enumerate(page_pieces(text)):
            if len(chunks) >= MAX_CHUNKS:
                return chunks, "too_many_chunks"
            title = current_title
            for offset, heading in hits:
                if offset <= start:
                    title = heading
            chunks.append(
                {
                    "page_no": page_no,
                    "chunk_seq": seq,
                    "section_title": title,
                    "content": piece,
                    "char_count": len(piece),
                }
            )
        if hits:
            current_title = hits[-1][1]
    if not chunks:
        return [], "no_text_layer"
    return chunks, None


def dedupe_toc(entries: list[dict]) -> list[dict]:
    ordered: dict[str, dict] = {}
    for entry in entries:
        title = entry.get("section_title")
        page = entry.get("page_no")
        if not title or not page:
            continue
        key = normalize_title(title)
        depth = int(entry.get("depth") or 0)
        current = ordered.get(key)
        if (
            current is None
            or page < current["page_no"]
            or (page == current["page_no"] and depth < current["depth"])
        ):
            ordered[key] = {"section_title": title, "page_no": page, "depth": depth}
    toc = list(ordered.values())
    toc.sort(key=lambda e: (e["page_no"], e["depth"], e["section_title"]))
    return toc


def build_toc(chunks: list[dict]) -> list[dict]:
    return dedupe_toc(
        [
            {"section_title": c["section_title"], "page_no": c["page_no"], "depth": 0}
            for c in chunks
        ]
    )


def titled_ratio(chunks: list[dict]) -> float:
    if not chunks:
        return 0.0
    return round(sum(1 for c in chunks if c["section_title"]) / len(chunks), 4)


def repeated_titles(chunks: list[dict], min_pages: int = REPEAT_MIN_PAGES, limit: int = 5) -> list[dict]:
    pages_by_stem: dict[str, set[int]] = {}
    label: dict[str, str] = {}
    for chunk in chunks:
        title = chunk["section_title"]
        if not title:
            continue
        stem = heading_stem(title)
        if not stem:
            continue
        pages_by_stem.setdefault(stem, set()).add(chunk["page_no"])
        label.setdefault(stem, title)
    repeated = [
        {"title": label[stem], "pages": len(pages)}
        for stem, pages in pages_by_stem.items()
        if len(pages) >= min_pages
    ]
    repeated.sort(key=lambda e: -e["pages"])
    return repeated[:limit]


def section_spans(toc: list[dict], last_page: int) -> list[dict]:
    spans = []
    for i, entry in enumerate(toc):
        depth = int(entry.get("depth") or 0)
        end = last_page
        for nxt in toc[i + 1 :]:
            if int(nxt.get("depth") or 0) <= depth:
                end = nxt["page_no"] - 1
                break
        spans.append({**entry, "end_page": max(end, entry["page_no"])})
    return spans


def route_sections(
    toc: list[dict],
    query: str,
    mode: str,
    recorded: list[str] | None,
    last_page: int = 0,
    oracle_pages: set[int] | None = None,
) -> tuple[list[dict], str]:
    if not toc:
        return [], "empty_toc"
    if mode == "agent":
        picks = [str(x) for x in (recorded or [])]
        selected = [
            entry
            for pick in picks
            for entry in toc
            if title_matches(entry["section_title"], pick)
        ]
        return selected[:ROUTER_MAX_SECTIONS], "agent_recorded" if selected else "empty_pick"
    if mode == "oracle":
        targets = oracle_pages or set()
        selected = [
            span
            for span in section_spans(toc, last_page)
            if targets & set(range(span["page_no"], span["end_page"] + 1))
        ]
        return selected[:ROUTER_MAX_SECTIONS], "oracle" if selected else "empty_pick"
    terms = extract_terms(query)
    scored = []
    for entry in toc:
        normalized = normalize_title(entry["section_title"])
        score = sum(1 for term in terms if term and term in normalized)
        if score > 0:
            scored.append((score, entry["page_no"], entry))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [entry for _, _, entry in scored[:ROUTER_MAX_SECTIONS]], "heuristic"


def keyword_recall(
    chunks: list[dict], query: str, top_k: int, restrict_pages: set[int] | None = None
) -> list[dict]:
    terms = extract_terms(query)
    _, weights = term_weights(chunks, terms, restrict_pages)
    scored = []
    for chunk in chunks:
        if restrict_pages is not None and chunk["page_no"] not in restrict_pages:
            continue
        score, matched = score_chunk(chunk["content"], terms, weights)
        if score > 0:
            scored.append(
                {
                    **chunk,
                    "score": score,
                    "matched_terms": matched,
                    "term_weights": {t: round(weights[t], 3) for t in matched},
                    "terms": terms,
                }
            )
    scored.sort(key=lambda c: (-c["score"], c["page_no"], c["chunk_seq"]))
    return scored[:top_k]


def retrieve(
    chunks: list[dict],
    toc: list[dict],
    last_page: int,
    query: str,
    top_k: int,
    router_mode: str,
    toc_source: str,
    recorded: list[str] | None = None,
    oracle_pages: set[int] | None = None,
    force_l2: bool = False,
) -> dict:
    gate = len(toc) > 0 if toc_source == "outline" else titled_ratio(chunks) >= L1_MIN_TITLED_RATIO
    selected: list[dict] = []
    if gate and not force_l2:
        selected, why = route_sections(
            toc, query, router_mode, recorded, last_page=last_page, oracle_pages=oracle_pages
        )
        if selected:
            picked = {normalize_title(e["section_title"]) for e in selected}
            pages: set[int] = set()
            for span in section_spans(toc, last_page):
                if normalize_title(span["section_title"]) in picked:
                    pages.update(range(span["page_no"], span["end_page"] + 1))
            hits = keyword_recall(chunks, query, top_k, restrict_pages=pages)
            if hits:
                return {
                    "used_retrieval": "toc_route",
                    "selected_sections": [e["section_title"] for e in selected],
                    "router": why,
                    "l1_gate_passed": True,
                    "l1_span_pages": sorted(pages),
                    "chunks": hits,
                }
    hits = keyword_recall(chunks, query, top_k)
    return {
        "used_retrieval": "keyword",
        "selected_sections": [e["section_title"] for e in selected],
        "router": router_mode,
        "l1_gate_passed": gate,
        "l1_span_pages": [],
        "chunks": hits,
    }


def qa_context(chunks: list[dict], budget: int = QA_CHAR_BUDGET) -> str:
    parts, used = [], 0
    for chunk in chunks:
        block = f"[p.{chunk['page_no']}] {chunk['content'][:CHUNK_MAX_CHARS]}"
        if used + len(block) > budget:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def evaluate_questions(
    questions: list[dict],
    docs: dict[str, dict],
    top_k: int,
    router_mode: str,
    toc_source: str,
    force_l2: bool = False,
) -> dict:
    results = []
    for question in questions:
        doc = docs.get(question["doc_id"])
        if not doc or doc["extract"].status != "ready" or not doc["chunks"]:
            results.append({**question, "skipped": True, "reason": "document_not_indexed"})
            continue
        outcome = retrieve(
            doc["chunks"],
            doc["toc"],
            doc["extract"].total_pages,
            question["question"],
            top_k,
            router_mode,
            toc_source,
            question.get("router_pick_agent"),
            set(question.get("expected_pages") or []),
            force_l2,
        )
        pages = [c["page_no"] for c in outcome["chunks"]]
        expected_pages = set(question.get("expected_pages") or [])
        l1_hit = None
        l1_reachable = None
        if question["kind"] == "section":
            l1_hit = bool(expected_pages & set(outcome["l1_span_pages"]))
            covered = set()
            for span in section_spans(doc["toc"], doc["extract"].total_pages):
                covered.update(range(span["page_no"], span["end_page"] + 1))
            l1_reachable = bool(expected_pages & covered)
        results.append(
            {
                "qid": question["qid"],
                "kind": question["kind"],
                "doc_id": question["doc_id"],
                "question": question["question"],
                "skipped": False,
                "used_retrieval": outcome["used_retrieval"],
                "l1_gate_passed": outcome["l1_gate_passed"],
                "selected_sections": outcome["selected_sections"],
                "l1_hit": l1_hit,
                "l1_reachable": l1_reachable,
                "expected_pages": sorted(expected_pages),
                "retrieved_pages": pages,
                "containment": bool(expected_pages & set(pages)),
                "answerable": question.get("answerable"),
                "answer_evidence": question.get("answer_evidence"),
                "context_chars": len(qa_context(outcome["chunks"])),
            }
        )
    return {"questions": results, "metrics": summarize(results)}


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def summarize(results: list[dict]) -> dict:
    active = [r for r in results if not r.get("skipped")]
    section_qs = [r for r in active if r["kind"] == "section"]
    keyword_qs = [r for r in active if r["kind"] == "keyword"]
    l1_available = [r for r in section_qs if r["l1_gate_passed"] and r["used_retrieval"] == "toc_route"]
    return {
        "questions_total": len(results),
        "questions_active": len(active),
        "questions_skipped": len(results) - len(active),
        "l1_hit_rate_all_section": _rate(sum(1 for r in section_qs if r["l1_hit"]), len(section_qs)),
        "l1_hit_rate_l1_available": _rate(
            sum(1 for r in l1_available if r["l1_hit"]), len(l1_available)
        ),
        "l1_reachable_rate": _rate(
            sum(1 for r in section_qs if r.get("l1_reachable")), len(section_qs)
        ),
        "l1_available_questions": len(l1_available),
        "keyword_containment_rate": _rate(
            sum(1 for r in keyword_qs if r["containment"]), len(keyword_qs)
        ),
        "containment_rate_all": _rate(sum(1 for r in active if r["containment"]), len(active)),
        "answerable_rate": _rate(sum(1 for r in active if r["answerable"]), len(active)),
        "toc_route_used": sum(1 for r in active if r["used_retrieval"] == "toc_route"),
    }


def heading_success(doc: dict) -> dict | None:
    truth = doc.get("ground_truth_toc") or []
    if not truth:
        return None
    extracted = [c["section_title"] for c in doc["chunks"] if c["section_title"]]
    matched = 0
    detail = []
    for entry in truth:
        ok = any(title_matches(e, entry["section_title"]) for e in extracted)
        matched += 1 if ok else 0
        detail.append({"section_title": entry["section_title"], "matched": ok})
    return {
        "expected": len(truth),
        "matched": matched,
        "rate": _rate(matched, len(truth)),
        "distinct_titles": len(set(extracted)),
        "detail": detail,
    }


def run(args) -> dict:
    questions_file = json.loads(pathlib.Path(args.questions).read_text(encoding="utf-8"))
    corpus_dir = pathlib.Path(args.corpus)
    docs: dict[str, dict] = {}
    manifest_docs = []
    for spec in questions_file["documents"]:
        doc_id = spec["doc_id"]
        path = corpus_dir / spec["file"]
        if not path.exists():
            manifest_docs.append(
                {"doc_id": doc_id, "doc_class": spec["class"], "file": spec["file"], "present": False}
            )
            continue
        extract = extract_document(doc_id, path, outline_max_depth=args.outline_max_depth)
        chunks, chunk_fail = slice_document(extract.pages, args.profile)
        text_toc = build_toc(chunks)
        outline_toc = dedupe_toc(extract.outline_toc)
        toc = outline_toc if args.toc_source == "outline" else text_toc
        docs[doc_id] = {
            "doc_id": doc_id,
            "doc_class": spec["class"],
            "file": spec["file"],
            "source": spec.get("source"),
            "extract": extract,
            "chunks": chunks,
            "chunk_fail_reason": chunk_fail,
            "toc": toc,
            "titled_ratio": titled_ratio(chunks),
            "ground_truth_toc": spec.get("ground_truth_toc"),
        }
        entry = {
            "doc_id": doc_id,
            "doc_class": spec["class"],
            "file": spec["file"],
            "source": spec.get("source"),
            "present": True,
            "pages": extract.total_pages,
            "pages_indexed": len(extract.pages),
            "chars_total": extract.chars_total,
            "blank_pages": len(extract.blank_pages),
            "status": extract.status,
            "fail_reason": extract.fail_reason,
            "extraction_rate": _rate(
                len(extract.pages) - len(extract.blank_pages), len(extract.pages)
            ),
            "truncated": extract.truncated,
            "truncation_ratio": _rate(
                extract.total_pages - len(extract.pages), extract.total_pages
            ),
            "outline_items": extract.outline_items,
            "outline_toc_entries": len(outline_toc),
            "has_toc_page": extract.has_toc_page,
            "chunks": len(chunks),
            "chunk_fail_reason": chunk_fail,
            "titled_ratio": titled_ratio(chunks),
            "toc_source": args.toc_source,
            "toc_entries": len(toc),
            "text_toc_entries": len(text_toc),
            "outline_toc_only_entries": len(outline_toc),
            "repeated_titles": repeated_titles(chunks),
            "heading_success": heading_success(docs[doc_id]),
            "elapsed_ms": extract.elapsed_ms,
        }
        manifest_docs.append(entry)
    evaluation = evaluate_questions(
        questions_file["questions"],
        docs,
        args.top_k,
        args.router,
        args.toc_source,
        args.force_l2,
    )
    truncated = [
        {
            "doc_id": d["doc_id"],
            "pages_total": d["pages"],
            "pages_indexed": d["pages_indexed"],
            "indexed_pct": _rate(d["pages_indexed"], d["pages"]),
        }
        for d in manifest_docs
        if d.get("present") and d.get("truncated")
    ]
    return {
        "profile": args.profile,
        "toc_source": args.toc_source,
        "outline_max_depth": args.outline_max_depth,
        "router_mode": args.router,
        "force_l2": bool(args.force_l2),
        "top_k": args.top_k,
        "corpus_dir": str(corpus_dir),
        "documents": manifest_docs,
        "truncated_documents": truncated,
        "evaluation": evaluation,
    }


def markdown_report(payload: dict) -> str:
    lines = [
        f"#### 组合 profile={payload['profile']} / toc_source={payload['toc_source']} / router={payload['router_mode']} / top_k={payload['top_k']} / l2_only={payload.get('force_l2', False)}\n",
        "| 文档 | 类别 | 页数 | 已索引页 | 有文字页占比 | 字符数 | 空页 | 状态 | 失败原因 | 切片数 | 有标题切片占比 | 目录条目(文本) | 目录条目(书签) | 目录页 | 耗时ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for d in payload["documents"]:
        if not d.get("present"):
            lines.append(f"| {d['doc_id']} | - | - | - | - | - | - | 缺失 | - | - | - | - | - | - | - |")
            continue
        lines.append(
            "| {doc_id} | {cls} | {pages} | {idx} | {rate} | {chars} | {blank} | {status} | {reason} | {chunks} | {titled} | {texttoc} | {outtoc} | {tocp} | {ms} |".format(
                doc_id=d["doc_id"],
                cls=d["doc_class"],
                pages=d["pages"],
                idx=d["pages_indexed"],
                rate=d["extraction_rate"],
                chars=d["chars_total"],
                blank=d["blank_pages"],
                status=d["status"],
                reason=d["fail_reason"] or "-",
                chunks=d["chunks"],
                titled=d["titled_ratio"],
                texttoc=d["text_toc_entries"],
                outtoc=d["outline_toc_only_entries"],
                tocp="Y" if d["has_toc_page"] else "N",
                ms=d["elapsed_ms"],
            )
        )
    if payload["truncated_documents"]:
        lines.append("\n**200k 截断**：" + "；".join(
            f"{t['doc_id']} 索引 {t['pages_indexed']}/{t['pages_total']} 页（{t['indexed_pct']}）"
            for t in payload["truncated_documents"]
        ))
    lines.append("\n| 文档 | 类别 | 期望标题 | 命中标题 | 标题抽取成功率 | 抽出的不同标题数 | 目录条目数 | 最高频重复标题 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for d in payload["documents"]:
        if not d.get("present"):
            continue
        hs = d.get("heading_success") or {}
        top = d["repeated_titles"][0] if d["repeated_titles"] else None
        lines.append(
            f"| {d['doc_id']} | {d['doc_class']} | {hs.get('expected', '-')} | {hs.get('matched', '-')} | "
            f"{hs.get('rate', '-')} | {hs.get('distinct_titles', '-')} | {d['toc_entries']} | "
            + (f"{top['title'][:26]}（{top['pages']}页）" if top else "-")
            + " |"
        )
    m = payload["evaluation"]["metrics"]
    lines.append("\n**检索量化**：")
    lines.append(f"- 章节型 L1 命中率（全部章节型问题）：{m['l1_hit_rate_all_section']}")
    lines.append(f"- 章节型 L1 命中率（实际走通 L1 的问题）：{m['l1_hit_rate_l1_available']}（走通 {m['l1_available_questions']} 题）")
    lines.append(f"- 关键词型 top6 召回包含率：{m['keyword_containment_rate']}")
    lines.append(f"- 全部问题 top6 包含率：{m['containment_rate_all']}")
    lines.append(f"- 20 问答案可用率：{m['answerable_rate']}")
    lines.append(f"- 走 L1 目录路由：{m['toc_route_used']} 题 / 跳过：{m['questions_skipped']} 题")
    lines.append("\n| 题号 | 类型 | 文档 | 检索层 | L1门控 | L1可达 | L1命中 | 选中章节 | 期望页 | 命中页 | 包含 | 可用 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in payload["evaluation"]["questions"]:
        if r.get("skipped"):
            lines.append(f"| {r['qid']} | {r['kind']} | {r['doc_id']} | 跳过 | - | - | - | - | - | - | - | - |")
            continue
        lines.append(
            "| {qid} | {kind} | {doc} | {layer} | {gate} | {reach} | {l1} | {sel} | {exp} | {got} | {cont} | {ans} |".format(
                qid=r["qid"],
                kind=r["kind"],
                doc=r["doc_id"],
                layer=r["used_retrieval"],
                gate="Y" if r["l1_gate_passed"] else "N",
                reach=("Y" if r["l1_reachable"] else "N") if r.get("l1_reachable") is not None else "-",
                l1=("Y" if r["l1_hit"] else "N") if r["l1_hit"] is not None else "-",
                sel=";".join(s[:16] for s in r["selected_sections"]) or "-",
                exp=",".join(str(p) for p in r["expected_pages"]),
                got=",".join(str(p) for p in r["retrieved_pages"]),
                cont="Y" if r["containment"] else "N",
                ans="Y" if r["answerable"] else "N",
            )
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SPIKE-2 中文 PDF 按页召回验证")
    parser.add_argument("--corpus", default="scripts/v0-spikes/corpus")
    parser.add_argument("--questions", default="scripts/v0-spikes/spike_pdf_questions.json")
    parser.add_argument("--out", default="scripts/v0-spikes/out")
    parser.add_argument("--profile", choices=sorted(HEADING_PROFILES), default="spec")
    parser.add_argument("--toc-source", choices=["text", "outline"], default="text")
    parser.add_argument("--outline-max-depth", type=int, default=1)
    parser.add_argument("--router", choices=["heuristic", "agent", "oracle"], default="heuristic")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--force-l2", action="store_true")
    args = parser.parse_args(argv)

    payload = run(args)
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{args.profile}_{args.toc_source}_d{args.outline_max_depth}_{args.router}_k{args.top_k}"
    if args.force_l2:
        stamp += "_l2only"
    (out_dir / f"spike_pdf_results_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = markdown_report(payload)
    (out_dir / f"spike_pdf_report_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
