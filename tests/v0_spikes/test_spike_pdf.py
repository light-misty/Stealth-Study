"""T02 SPIKE-2 脚本的单元测试。

spike 脚本位于 scripts/v0-spikes/（目录名含连字符，不是可导入包），因此按路径加载。
量化指标口径见 docs/dev/08-测试与验收方案.md §3.2。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


sp = _load("spike_pdf", "scripts/v0-spikes/spike_pdf.py")
fc = _load("fetch_corpus", "scripts/v0-spikes/fetch_corpus.py")

QUESTIONS_PATH = ROOT / "scripts" / "v0-spikes" / "spike_pdf_questions.json"


# --- 文本归一化与标题匹配 -------------------------------------------------------


def test_normalize_title_strips_whitespace_and_punctuation():
    assert sp.normalize_title("第 1 章   初识算法") == "第1章初识算法"
    assert sp.normalize_title("  2.1 进程的基本概念  ") == "2.1进程的基本概念"


def test_title_matches_accepts_exact_and_containment():
    assert sp.title_matches("第 1 章 初识算法", "第1章初识算法")
    assert sp.title_matches("第 13 章 回溯", "回溯")
    assert sp.title_matches("回溯", "第 13 章 回溯")


def test_title_matches_rejects_empty_and_unrelated():
    assert not sp.title_matches("", "第 1 章")
    assert not sp.title_matches("第 1 章", "")
    assert not sp.title_matches("第 1 章 初识算法", "第 2 章 复杂度分析")


def test_heading_stem_keeps_only_cjk_characters():
    assert sp.heading_stem("第 0 章 前言 www .hello-algo.com 2") == "第章前言"
    assert sp.heading_stem("7.3.3 优点与局限性") == "优点与局限性"
    assert sp.heading_stem("2.1 进程的基本概念") == "进程的基本概念"


# --- 关键词抽取与打分 -----------------------------------------------------------


def test_extract_terms_keeps_latin_tokens_first():
    terms = sp.extract_terms("AVL 树在删除节点之后为什么会退化成链表？")
    assert terms[0] == "avl"


def test_extract_terms_filters_stopword_bigrams():
    terms = sp.extract_terms("哈希冲突有哪些解决办法？")
    assert "冲突" in terms
    assert "哪些" not in terms
    assert "有哪" not in terms


def test_extract_terms_keeps_meaningful_single_cjk_char():
    assert "树" in sp.extract_terms("树")


def test_extract_terms_dedupes_and_respects_limit():
    terms = sp.extract_terms("Docker docker DOCKER 镜像镜像镜像", max_terms=3)
    assert terms.count("docker") == 1
    assert len(terms) <= 3


def test_score_chunk_returns_zero_without_match():
    score, matched = sp.score_chunk("完全无关的一段文字", ["哈希", "冲突"])
    assert score == 0.0
    assert matched == []


def test_score_chunk_rewards_more_matched_terms_and_earlier_hits():
    early = "哈希冲突在开头，后面还有很多内容需要填充以拉长字符串"
    late = "前面有很多内容需要填充以拉长字符串，哈希冲突在最后"
    early_score, early_matched = sp.score_chunk(early, ["哈希", "冲突"])
    late_score, late_matched = sp.score_chunk(late, ["哈希", "冲突"])
    assert early_matched == late_matched == ["哈希", "冲突"]
    assert early_score > late_score


def test_score_chunk_applies_supplied_weights():
    plain, _ = sp.score_chunk("哈希冲突", ["哈希", "冲突"])
    weighted, _ = sp.score_chunk("哈希冲突", ["哈希", "冲突"], {"哈希": 3.0, "冲突": 1.0})
    assert weighted > plain


def test_term_weights_downweights_ubiquitous_terms():
    chunks = [
        {"page_no": 1, "content": "镜像与docker"},
        {"page_no": 2, "content": "镜像与docker"},
        {"page_no": 3, "content": "镜像与索树"},
    ]
    _, weights = sp.term_weights(chunks, ["镜像", "索树"])
    assert weights["索树"] > weights["镜像"]


def test_term_weights_ignores_chunks_outside_restriction():
    chunks = [
        {"page_no": 1, "content": "索树"},
        {"page_no": 2, "content": "索树"},
    ]
    total, weights = sp.term_weights(chunks, ["索树"], restrict_pages={1})
    assert total == 1
    assert weights["索树"] == pytest.approx(1.0, abs=1e-6)


# --- 按页切片 ------------------------------------------------------------------


def test_page_pieces_returns_whole_page_when_short():
    assert sp.page_pieces("短文本", max_chars=2000) == [(0, "短文本")]


def test_page_pieces_returns_nothing_for_empty_text():
    assert sp.page_pieces("", max_chars=2000) == []


def test_page_pieces_respects_max_chars():
    text = "\n\n".join("段落%d：%s" % (i, "字" * 300) for i in range(10))
    pieces = sp.page_pieces(text, max_chars=500)
    assert pieces
    assert all(len(piece) <= 500 for _, piece in pieces)


def test_page_pieces_hard_splits_oversized_paragraph():
    pieces = sp.page_pieces("字" * 5000, max_chars=2000)
    assert [len(piece) for _, piece in pieces] == [2000, 2000, 1000]


def test_page_pieces_offsets_are_monotonic():
    text = "\n\n".join("段落%d：%s" % (i, "字" * 100) for i in range(20))
    offsets = [offset for offset, _ in sp.page_pieces(text, max_chars=300)]
    assert offsets == sorted(offsets)
    assert len(set(offsets)) == len(offsets)


# --- 标题行判据 ----------------------------------------------------------------


def test_heading_hits_spec_requires_no_space_between_counter_and_chapter():
    assert sp.heading_hits("第一章 绪论\n", "spec")
    assert sp.heading_hits("第1章 绪论\n", "spec")
    assert not sp.heading_hits("第 1 章 绪论\n", "spec")


def test_heading_hits_spec_accepts_chapter_and_lecture_suffixes():
    assert sp.heading_hits("第三章 安装 Docker\n", "spec")
    assert sp.heading_hits("第一讲 导论\n", "spec")
    assert sp.heading_hits("Chapter 3 Installing\n", "spec")


def test_heading_hits_spec_rejects_overlong_line():
    long_line = "第一章 " + "长" * 60 + "\n"
    assert not sp.heading_hits(long_line, "spec")


def test_heading_hits_spec_only_matches_at_line_start():
    assert not sp.heading_hits("本章内容参考第一章 绪论\n", "spec")


def test_heading_hits_relaxed_accepts_spaced_and_numbered_titles():
    assert sp.heading_hits("第 0 章 前言\n", "relaxed")
    assert sp.heading_hits("2.1 进程的基本概念\n", "relaxed")
    assert sp.heading_hits("7.3.3 优点与局限性\n", "relaxed")


def test_heading_hits_reports_offset_and_stripped_text():
    hits = sp.heading_hits("正文\n2.1 进程的基本概念\n", "relaxed")
    assert hits == [(3, "2.1 进程的基本概念")]


# --- 文档切片与标题归属 ---------------------------------------------------------


def test_slice_document_carries_section_title_forward():
    pages = ["第一章 绪论\n正文甲", "正文乙", "正文丙"]
    chunks, fail = sp.slice_document(pages, "spec")
    assert fail is None
    assert [c["page_no"] for c in chunks] == [1, 2, 3]
    assert {c["section_title"] for c in chunks} == {"第一章 绪论"}


def test_slice_document_retitles_from_page_starting_with_heading():
    pages = ["第一章 甲\n正文", "第二讲 乙\n正文"]
    chunks, _ = sp.slice_document(pages, "spec")
    assert [(c["page_no"], c["section_title"]) for c in chunks] == [
        (1, "第一章 甲"),
        (2, "第二讲 乙"),
    ]


def test_slice_document_keeps_previous_title_for_chunk_holding_midpage_heading():
    pages = ["第一章 甲\n" + "字" * 2500 + "\n第二讲 乙\n正文"]
    chunks, _ = sp.slice_document(pages, "spec")
    assert len(chunks) == 2
    assert {c["section_title"] for c in chunks} == {"第一章 甲"}


def test_slice_document_aborts_past_max_chunks(monkeypatch):
    monkeypatch.setattr(sp, "MAX_CHUNKS", 3)
    chunks, fail = sp.slice_document(["正文"] * 10, "spec")
    assert fail == "too_many_chunks"
    assert len(chunks) == 3


def test_slice_document_reports_no_text_layer_for_empty_pages():
    chunks, fail = sp.slice_document(["", "", ""], "spec")
    assert chunks == []
    assert fail == "no_text_layer"


def test_slice_document_numbers_chunks_within_page():
    pages = ["第一段\n\n" + "字" * 2500]
    chunks, _ = sp.slice_document(pages, "spec")
    assert [c["chunk_seq"] for c in chunks] == list(range(len(chunks)))
    assert all(c["page_no"] == 1 for c in chunks)


# --- 判空与截断分支（06 §6.1） ---------------------------------------------------


def test_classify_extract_fails_on_zero_text_layer():
    assert sp.classify_extract(57, 0, 0, False) == ("failed", "no_text_layer")


def test_classify_extract_upgrades_mostly_blank_document_to_failed():
    assert sp.classify_extract(10, 1, 120, False) == ("failed", "no_text_layer")


def test_classify_extract_keeps_partially_blank_document_ready():
    status, reason = sp.classify_extract(10, 5, 120, False)
    assert status == "ready"
    assert reason is None


def test_classify_extract_marks_truncated_document():
    assert sp.classify_extract(200, 200, sp.MAX_EXTRACT_CHARS, True) == (
        "ready",
        "truncated_200k",
    )


def test_cap_page_text_truncates_at_running_cap():
    text, hit = sp.cap_page_text("字" * 100, running_total=50, max_chars=100)
    assert len(text) == 50
    assert hit is True


def test_cap_page_text_passes_through_under_cap():
    assert sp.cap_page_text("abc", running_total=0, max_chars=100) == ("abc", False)


# --- 目录聚合与跨度 ------------------------------------------------------------


def test_build_toc_takes_earliest_page_and_dedupes():
    chunks = [
        {"page_no": 5, "section_title": "第一章 甲"},
        {"page_no": 2, "section_title": "第一章   甲"},
        {"page_no": 9, "section_title": "第二章 乙"},
    ]
    toc = sp.build_toc(chunks)
    assert toc == [
        {"section_title": "第一章   甲", "page_no": 2, "depth": 0},
        {"section_title": "第二章 乙", "page_no": 9, "depth": 0},
    ]


def test_dedupe_toc_keeps_shallowest_depth():
    entries = [
        {"section_title": "1.1 快速上手", "page_no": 31, "depth": 1},
        {"section_title": "1.1 快速上手", "page_no": 31, "depth": 0},
    ]
    assert sp.dedupe_toc(entries)[0]["depth"] == 0


def test_section_spans_end_at_next_same_depth_entry():
    toc = [
        {"section_title": "第一章 甲", "page_no": 1, "depth": 0},
        {"section_title": "1.1 子节", "page_no": 2, "depth": 1},
        {"section_title": "1.2 子节", "page_no": 4, "depth": 1},
        {"section_title": "第二章 乙", "page_no": 6, "depth": 0},
    ]
    spans = {s["section_title"]: (s["page_no"], s["end_page"]) for s in sp.section_spans(toc, 10)}
    assert spans["第一章 甲"] == (1, 5)
    assert spans["1.1 子节"] == (2, 3)
    assert spans["第二章 乙"] == (6, 10)


def test_titled_ratio_counts_chunks_with_section_title():
    chunks = [{"section_title": "甲"}, {"section_title": None}, {"section_title": "乙"}]
    assert sp.titled_ratio(chunks) == pytest.approx(2 / 3, abs=1e-4)
    assert sp.titled_ratio([]) == 0.0


def test_repeated_titles_flags_running_headers():
    chunks = [
        {"page_no": p, "section_title": f"第 7 章 树 www.hello-algo.com {p}"}
        for p in range(1, 6)
    ] + [{"page_no": 6, "section_title": "7.5 AVL 树"}]
    repeated = sp.repeated_titles(chunks, min_pages=3)
    assert len(repeated) == 1
    assert repeated[0]["pages"] == 5


# --- 章节路由 ------------------------------------------------------------------


TOC = [
    {"section_title": "第 7 章 树", "page_no": 130, "depth": 0},
    {"section_title": "7.5 AVL 树", "page_no": 152, "depth": 1},
    {"section_title": "第 6 章 哈希表", "page_no": 111, "depth": 0},
]


def test_route_sections_heuristic_picks_term_overlap():
    picked, why = sp.route_sections(TOC, "AVL 树是怎么保持平衡的？", "heuristic", None)
    assert why == "heuristic"
    assert picked and picked[0]["section_title"] == "7.5 AVL 树"


def test_route_sections_heuristic_matches_latin_titles_case_insensitively():
    toc = [{"section_title": "Docker Hub", "page_no": 193, "depth": 0}]
    picked, _ = sp.route_sections(toc, "docker hub 是什么？", "heuristic", None)
    assert [p["section_title"] for p in picked] == ["Docker Hub"]


def test_route_sections_returns_empty_for_empty_toc():
    assert sp.route_sections([], "任意问题", "heuristic", None) == ([], "empty_toc")


def test_route_sections_agent_uses_recorded_picks():
    picked, why = sp.route_sections(TOC, "任意问题", "agent", ["第 6 章 哈希表"])
    assert why == "agent_recorded"
    assert [p["section_title"] for p in picked] == ["第 6 章 哈希表"]


def test_route_sections_agent_reports_empty_pick():
    picked, why = sp.route_sections(TOC, "任意问题", "agent", ["不存在的章节"])
    assert picked == []
    assert why == "empty_pick"


def test_route_sections_oracle_targets_expected_page():
    picked, why = sp.route_sections(
        TOC, "任意问题", "oracle", None, last_page=200, oracle_pages={111}
    )
    assert why == "oracle"
    assert [p["section_title"] for p in picked] == ["第 6 章 哈希表"]


def test_route_sections_caps_selection_at_three():
    toc = [
        {"section_title": f"第 {i} 章 测试", "page_no": i, "depth": 0} for i in range(1, 9)
    ]
    picked, _ = sp.route_sections(toc, "测试", "heuristic", None)
    assert len(picked) == sp.ROUTER_MAX_SECTIONS


def test_route_sections_ignores_blank_questions():
    picked, _ = sp.route_sections(TOC, "？？？", "heuristic", None)
    assert picked == []


# --- 关键词召回与三级检索 -------------------------------------------------------


def _chunks():
    return [
        {"page_no": 1, "chunk_seq": 0, "section_title": "第一章 甲", "content": "哈希冲突的处理办法"},
        {"page_no": 2, "chunk_seq": 0, "section_title": "第一章 甲", "content": "无关内容"},
        {"page_no": 3, "chunk_seq": 1, "section_title": "第一章 甲", "content": "哈希冲突的链式地址"},
    ]


def test_keyword_recall_restricts_to_allowed_pages():
    hits = sp.keyword_recall(_chunks(), "哈希冲突", 6, restrict_pages={3})
    assert [h["page_no"] for h in hits] == [3]


def test_keyword_recall_respects_top_k():
    hits = sp.keyword_recall(_chunks(), "哈希冲突", 1)
    assert len(hits) == 1


def test_keyword_recall_returns_matched_terms():
    hits = sp.keyword_recall(_chunks(), "哈希冲突", 6)
    assert "哈希" in hits[0]["matched_terms"]


def test_retrieve_falls_back_to_keyword_when_gate_fails():
    chunks = [dict(c, section_title=None) for c in _chunks()]
    outcome = sp.retrieve(chunks, [], 3, "哈希冲突", 6, "heuristic", "text")
    assert outcome["used_retrieval"] == "keyword"
    assert outcome["l1_gate_passed"] is False
    assert outcome["chunks"]


def test_retrieve_uses_toc_route_when_gate_passes():
    chunks = [dict(c, section_title="哈希冲突") for c in _chunks()]
    toc = [{"section_title": "哈希冲突", "page_no": 1, "depth": 0}]
    outcome = sp.retrieve(chunks, toc, 3, "哈希冲突的处理办法", 6, "heuristic", "text")
    assert outcome["used_retrieval"] == "toc_route"
    assert outcome["selected_sections"] == ["哈希冲突"]


def test_retrieve_falls_back_when_routed_sections_yield_no_hits():
    chunks = [dict(c, section_title="第二章 乙") for c in _chunks()]
    toc = [{"section_title": "第二章 乙", "page_no": 1, "depth": 0}]
    outcome = sp.retrieve(chunks, toc, 3, "完全无关的问题", 6, "heuristic", "text")
    assert outcome["used_retrieval"] == "keyword"


def test_qa_context_respects_budget():
    chunks = [
        {"page_no": i, "chunk_seq": 0, "content": "字" * 400} for i in range(1, 40)
    ]
    context = sp.qa_context(chunks, budget=1000)
    assert len(context) <= 1000 + len("[p.1] ")
    assert "[p.1]" in context


# --- 指标汇总 ------------------------------------------------------------------


def test_rate_returns_none_for_empty_denominator():
    assert sp._rate(0, 0) is None
    assert sp._rate(1, 4) == 0.25


def test_summarize_computes_expected_rates():
    results = [
        {"kind": "section", "l1_hit": True, "l1_gate_passed": True, "used_retrieval": "toc_route",
         "containment": True, "answerable": True, "l1_reachable": True},
        {"kind": "section", "l1_hit": False, "l1_gate_passed": True, "used_retrieval": "toc_route",
         "containment": False, "answerable": False, "l1_reachable": True},
        {"kind": "keyword", "l1_hit": None, "l1_gate_passed": True, "used_retrieval": "keyword",
         "containment": True, "answerable": True, "l1_reachable": None},
    ]
    metrics = sp.summarize(results)
    assert metrics["questions_active"] == 3
    assert metrics["l1_hit_rate_all_section"] == 0.5
    assert metrics["l1_hit_rate_l1_available"] == 0.5
    assert metrics["l1_reachable_rate"] == 1.0
    assert metrics["keyword_containment_rate"] == 1.0
    assert metrics["answerable_rate"] == pytest.approx(2 / 3, abs=1e-4)


def test_summarize_skips_skipped_questions():
    results = [{"qid": "S01", "kind": "section", "skipped": True, "reason": "document_not_indexed"}]
    metrics = sp.summarize(results)
    assert metrics["questions_skipped"] == 1
    assert metrics["questions_active"] == 0
    assert metrics["l1_hit_rate_all_section"] is None


def test_heading_success_matches_by_containment():
    doc = {
        "ground_truth_toc": [{"section_title": "第 1 章 初识算法", "page_no": 17}],
        "chunks": [{"section_title": "第 1 章 初识算法 www.hello-algo.com 10"}],
    }
    success = sp.heading_success(doc)
    assert success["matched"] == 1
    assert success["rate"] == 1.0


def test_heading_success_returns_none_without_ground_truth():
    assert sp.heading_success({"ground_truth_toc": [], "chunks": []}) is None


# --- PDF 级判空（构造 fixture，不依赖语料） -------------------------------------


def test_extract_document_reports_pdf_broken(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this file is definitely not a PDF document")
    result = sp.extract_document("broken", broken)
    assert result.status == "failed"
    assert result.fail_reason == "pdf_broken"


def test_extract_document_flags_pdf_without_text_layer(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    blank = tmp_path / "blank.pdf"
    with open(blank, "wb") as fh:
        writer.write(fh)

    result = sp.extract_document("blank", blank)
    assert result.status == "failed"
    assert result.fail_reason == "no_text_layer"
    assert result.blank_pages == [1, 2, 3]
    chunks, fail = sp.slice_document(result.pages, "spec")
    assert chunks == []
    assert fail == "no_text_layer"
    assert pypdf is not None


# --- 报告渲染与语料/评估集一致性 ------------------------------------------------


def test_markdown_report_renders_all_sections():
    payload = {
        "profile": "spec",
        "toc_source": "outline",
        "router_mode": "heuristic",
        "top_k": 6,
        "corpus_dir": "corpus",
        "documents": [
            {
                "doc_id": "d1",
                "doc_class": "textbook",
                "file": "d1.pdf",
                "present": True,
                "pages": 10,
                "pages_indexed": 10,
                "extraction_rate": 1.0,
                "chars_total": 100,
                "blank_pages": 0,
                "status": "ready",
                "fail_reason": None,
                "chunks": 10,
                "titled_ratio": 1.0,
                "text_toc_entries": 3,
                "outline_toc_only_entries": 3,
                "has_toc_page": True,
                "elapsed_ms": 5,
                "toc_entries": 3,
                "truncated": False,
                "heading_success": {"expected": 3, "matched": 3, "rate": 1.0, "distinct_titles": 3},
                "repeated_titles": [],
            }
        ],
        "truncated_documents": [],
        "evaluation": {
            "questions": [
                {
                    "qid": "S01",
                    "kind": "section",
                    "doc_id": "d1",
                    "used_retrieval": "toc_route",
                    "l1_gate_passed": True,
                    "l1_reachable": True,
                    "l1_hit": True,
                    "selected_sections": ["第一章 甲"],
                    "expected_pages": [1],
                    "retrieved_pages": [1],
                    "containment": True,
                    "answerable": True,
                    "skipped": False,
                }
            ],
            "metrics": sp.summarize(
                [
                    {
                        "kind": "section",
                        "l1_hit": True,
                        "l1_gate_passed": True,
                        "used_retrieval": "toc_route",
                        "containment": True,
                        "answerable": True,
                        "l1_reachable": True,
                    }
                ]
            ),
        },
    }
    report = sp.markdown_report(payload)
    assert "页数" in report
    assert "标题抽取成功率" in report
    assert "检索量化" in report
    assert "S01" in report
    assert "d1" in report


def test_corpus_manifest_and_questions_declare_same_documents():
    manifest_ids = {item["doc_id"] for item in fc.MANIFEST}
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    doc_ids = {doc["doc_id"] for doc in questions["documents"]}
    assert manifest_ids == doc_ids


def test_corpus_manifest_covers_required_document_classes():
    classes = [item["class"] for item in fc.MANIFEST]
    assert classes.count("handout") >= 2
    assert classes.count("textbook") >= 2
    assert classes.count("scan") >= 1
    assert len(fc.MANIFEST) == 5


def test_corpus_manifest_hashes_are_wellformed():
    for item in fc.MANIFEST:
        assert item["url"].startswith("http")
        assert len(item["sha256"]) == 64
        int(item["sha256"], 16)
        assert item["bytes"] > 0


def test_corpus_source_is_restricted_to_public_hosts():
    allowed = ("https://github.com/", "https://raw.githubusercontent.com/")
    for item in fc.MANIFEST:
        assert item["url"].startswith(allowed)


def test_questions_dataset_shape():
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    items = questions["questions"]
    assert len(items) == 20
    assert sum(1 for q in items if q["kind"] == "section") == 10
    assert sum(1 for q in items if q["kind"] == "keyword") == 10
    assert len({q["qid"] for q in items}) == 20
    doc_ids = {doc["doc_id"] for doc in questions["documents"]}
    for question in items:
        assert question["doc_id"] in doc_ids
        assert question["expected_pages"]
        assert all(page > 0 for page in question["expected_pages"])
        assert question["answer_key"]


def test_questions_never_target_the_scanned_document():
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    scan_ids = {d["doc_id"] for d in questions["documents"] if d["class"] == "scan"}
    assert scan_ids
    assert not scan_ids & {q["doc_id"] for q in questions["questions"]}


def test_section_questions_expect_a_routable_section():
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    for question in questions["questions"]:
        if question["kind"] == "section":
            assert question["expected_sections"]
            assert all(s.strip() for s in question["expected_sections"])
