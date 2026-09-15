"""T21 rubric 一致性测试（08 §5.1 的 CI 硬门禁）。

权威文本落在 `ss/campus/rubrics.py`（05 §4.2 约定）；技能包 SKILL.md 的「评分标准」章节
逐字引用同一份文本（05 §4.2 第 2 条：单一来源 + 一致性测试）。T21 把 SKILL.md 落盘后，
本测试的取源从 `docs/dev/05` 文档正文切换为
`personas/builtin/<id>/skills/<name>/SKILL.md`——比对口径不变：剥掉 YAML 前言后
`strip()` 全等，兼容 markdown 表格行内空白差异（08 §5.1 末句口径）。

尚未落盘为 SKILL.md 的技能包仍暂以 05 文档代码块为取源，落盘一笔即切换一条，不留空窗。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ROOT / "ss" / "personas" / "builtin"
DOC = ROOT / "docs" / "dev" / "05-人设与技能包设计.md"

from ss.campus import rubrics


def _skill_body(relative_path: str) -> str:
    """SKILL.md 的正文（YAML 前言之后）——即与常量比对的 rubric 章节全文。"""
    text = (PERSONAS / relative_path).read_text(encoding="utf-8")
    assert text.startswith("---"), f"{relative_path} 缺少 YAML 前言"
    end = text.find("\n---", 3)
    assert end != -1, f"{relative_path} 的 YAML 前言未闭合"
    return text[end + 4 :].strip()


def _doc_block_body(header: str) -> str:
    """05 文档 `<header>` 章节 markdown 代码块的正文（去掉 YAML 前言）。

    仅用于尚未落盘为 SKILL.md 的技能包，作为切换前的过渡取源。
    """
    doc = DOC.read_text(encoding="utf-8")
    match = re.search(rf"### {re.escape(header)}.*?```markdown\n(.*?)\n```", doc, re.S)
    assert match, f"未在 05 文档中找到 {header} 章节"
    lines = match.group(1).split("\n")
    if lines and lines[0].strip() == "---":
        closing: list[int] = [
            index for index, line in enumerate(lines) if line.strip() == "---"
        ][1]
        lines = lines[closing + 1 :]
    return "\n".join(lines).strip()


def test_four_rubric_constants_declared_nonempty() -> None:
    assert isinstance(rubrics.CET_ESSAY_RUBRIC, str) and rubrics.CET_ESSAY_RUBRIC.strip()
    assert isinstance(rubrics.CET_TRANSLATION_RUBRIC, str) and rubrics.CET_TRANSLATION_RUBRIC.strip()
    assert isinstance(rubrics.ATTRIBUTION_TAXONOMY, str) and rubrics.ATTRIBUTION_TAXONOMY.strip()
    assert isinstance(rubrics.CERT_SCORING_POINTS_SPEC, str) and rubrics.CERT_SCORING_POINTS_SPEC.strip()
    assert isinstance(rubrics.ERROR_TYPES_CET, tuple) and rubrics.ERROR_TYPES_CET


def test_essay_rubric_is_byte_for_byte_the_cet_grader_skill() -> None:
    assert rubrics.CET_ESSAY_RUBRIC.strip() == _skill_body(
        "cet-grader/skills/cet-essay-grading/SKILL.md"
    )


def test_translation_rubric_is_byte_for_byte_the_cet_grader_skill() -> None:
    assert rubrics.CET_TRANSLATION_RUBRIC.strip() == _skill_body(
        "cet-grader/skills/cet-translation-grading/SKILL.md"
    )


def test_attribution_taxonomy_is_byte_for_byte_the_4_9_section() -> None:
    assert rubrics.ATTRIBUTION_TAXONOMY.strip() == _doc_block_body("4.9")


def test_error_types_complete_and_unique() -> None:
    compact = re.sub(r"\s+", "", rubrics.CET_ESSAY_RUBRIC)
    for error_type in rubrics.ERROR_TYPES_CET:
        assert error_type in compact
    assert len(set(rubrics.ERROR_TYPES_CET)) == len(rubrics.ERROR_TYPES_CET)


def test_essay_bands_and_dimensions_match_the_rubric_document() -> None:
    assert set(rubrics.ESSAY_BANDS) == {0, 2, 5, 8, 11, 14}
    assert set(rubrics.ESSAY_DIMENSIONS) == {"content", "structure", "language"}
    assert rubrics.ESSAY_BAND_INTERVALS[14] == (13, 15)
    assert rubrics.ESSAY_BAND_INTERVALS[0] == (0, 0)


def test_translation_error_types_are_subset_of_the_translation_rubric() -> None:
    compact = re.sub(r"\s+", "", rubrics.CET_TRANSLATION_RUBRIC)
    for error_type in rubrics.TRANSLATION_ERROR_TYPES:
        assert error_type in compact
    assert len(rubrics.TRANSLATION_ERROR_TYPES) == len(set(rubrics.TRANSLATION_ERROR_TYPES))


def test_translation_band_range_spans_zero_to_fifteen() -> None:
    assert rubrics.TRANSLATION_BAND_MIN == 0
    assert rubrics.TRANSLATION_BAND_MAX == 15


def test_scoring_point_statuses_are_the_three_state_contract() -> None:
    assert tuple(rubrics.SCORING_POINT_STATUSES) == ("hit", "partial", "miss")
