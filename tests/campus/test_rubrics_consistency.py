"""T07 rubric 一致性测试（08 §5.1 的 CI 硬门禁，师资包落盘前的占位实现）。

一致性测试的最终目标：`rubrics.py` 常量与 `personas/builtin/<id>/skills/<name>/SKILL.md`
的对应章节 `strip()` 后逐字全等（05 §4.2）。SKILL.md 要到 T21 才落盘，因此本阶段先把
锁定目标对准 05 文档 §4.3/§4.4/§4.9 的原文——T21 落盘后只需把 `_rubric_body` 的取源
从 05 文档换成 SKILL.md 路径即可无缝切换到逐字比对，断言结构无需改动。

本组用例 `strip()` 后比对，兼容 markdown 表格行内空白差异（08 §5.1 末句口径）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "dev" / "05-人设与技能包设计.md"

from ss.campus import rubrics


def _rubric_body(header: str) -> str:
    """从 05 文档取 `<header>` 章节的 markdown 代码块正文，去掉 YAML 前言。

    块结构固定为 `---\nname: ...\ndescription: ...\n---\n<body>`，`<body>` 即 rubric
    正文（从一级标题开始），与 `spike_grading` 对 §4.3 的提取口径一致。
    """
    doc = DOC.read_text(encoding="utf-8")
    match = re.search(rf"### {re.escape(header)}.*?```markdown\n(.*?)\n```", doc, re.S)
    assert match, f"未在 05 文档中找到 {header} 章节"
    lines = match.group(1).split("\n")
    if lines and lines[0].strip() == "---":
        closing: list[int] = [
            index for index, line in enumerate(lines) if line.strip() == "---"
        ][1]
        body = lines[closing + 1 :]
    else:
        body = lines
    return "\n".join(body).strip()


def test_five_rubric_constants_declared_nonempty() -> None:
    assert isinstance(rubrics.CET_ESSAY_RUBRIC, str) and rubrics.CET_ESSAY_RUBRIC.strip()
    assert isinstance(rubrics.CET_TRANSLATION_RUBRIC, str) and rubrics.CET_TRANSLATION_RUBRIC.strip()
    assert isinstance(rubrics.ATTRIBUTION_TAXONOMY, str) and rubrics.ATTRIBUTION_TAXONOMY.strip()
    assert isinstance(rubrics.CERT_SCORING_POINTS_SPEC, str) and rubrics.CERT_SCORING_POINTS_SPEC.strip()
    assert isinstance(rubrics.ERROR_TYPES_CET, tuple) and rubrics.ERROR_TYPES_CET


def test_essay_rubric_is_byte_for_byte_the_4_3_section() -> None:
    assert rubrics.CET_ESSAY_RUBRIC.strip() == _rubric_body("4.3")


def test_translation_rubric_is_byte_for_byte_the_4_4_section() -> None:
    assert rubrics.CET_TRANSLATION_RUBRIC.strip() == _rubric_body("4.4")


def test_attribution_taxonomy_is_byte_for_byte_the_4_9_section() -> None:
    assert rubrics.ATTRIBUTION_TAXONOMY.strip() == _rubric_body("4.9")


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