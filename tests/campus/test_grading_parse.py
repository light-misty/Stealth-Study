"""T07 批改解析器测试（06 §7-1 的 17 用例：`_extract_json` 8 + L1 填空 6 + L2 聚合 3）。

全部为纯函数单测，不依赖模型（08 §1 的模型依赖策略）：解析器直接吃 T01 spike 的文本，
验证四级降级链的每一级解析都正确。翻译与评分点两路做基础正反例覆盖。
"""

from __future__ import annotations

from ss.campus.grading import (
    MAX_ERROR_ROWS,
    band_for_sum,
    extract_json,
    parse_l0,
    parse_l1,
    parse_l2_rounds,
    parse_scoring_points_l0,
    parse_translation_l1,
)


def valid_payload(**overrides: object) -> dict:
    payload: dict = {
        "band": 11,
        "dimension_scores": {"content": 4, "structure": 4, "language": 3},
        "errors": [{"fragment": "a b c", "suggestion": "abc", "type": "拼写"}],
        "upgraded_demo": "demo",
        "model_answer_outline": "outline",
    }
    payload.update(overrides)
    return payload


def l1_text(band: int = 11, content: int = 4, structure: int = 4, language: int = 3, errors: int = 1) -> str:
    rows: list[str] = [
        f"档位：{band}",
        f"内容分：{content}",
        f"结构分：{structure}",
        f"语言分：{language}",
    ]
    for index in range(1, 9):
        rows.append(f"错误{index}：frag{index} || sug{index} || 拼写" if index <= errors else f"错误{index}：")
    rows.append("升格示范：rewritten")
    return "\n".join(rows)


# ---------- _extract_json（06 §3.2 的 JSON 提取器，8 例） ----------


def test_extract_json_plain() -> None:
    data, reason = extract_json('{"band": 11}')
    assert data == {"band": 11} and reason is None


def test_extract_json_fenced_json() -> None:
    data, reason = extract_json('```json\n{"band": 14}\n```')
    assert data == {"band": 14} and reason is None


def test_extract_json_fenced_without_language() -> None:
    data, reason = extract_json('```\n{"band": 8}\n```')
    assert data == {"band": 8} and reason is None


def test_extract_json_brace_inside_string() -> None:
    data, reason = extract_json('{"fragment": "use { } here", "band": 5}')
    assert data is not None and data["fragment"] == "use { } here" and reason is None


def test_extract_json_nested_braces() -> None:
    raw = '{"band": 14, "dimension_scores": {"content": 5, "structure": 5, "language": 4}}'
    data, reason = extract_json(raw)
    assert reason is None and data["dimension_scores"]["language"] == 4


def test_extract_json_surrounded_by_prose() -> None:
    data, reason = extract_json('好的，批改如下：\n{"band": 8}\n以上仅供参考。')
    assert data == {"band": 8} and reason is None


def test_extract_json_truncated_is_invalid() -> None:
    data, reason = extract_json('{"band": 11, "dimension_scores": {"content": 4')
    assert data is None and reason == "json_invalid"


def test_extract_json_empty_is_flagged() -> None:
    data, reason = extract_json("   ")
    assert data is None and reason == "empty_response"


def test_extract_json_no_aggressive_repair() -> None:
    data, reason = extract_json('说明 {x} 然后 {"band": 11}')
    assert data is None and reason == "json_invalid"


# ---------- L0 校验（schema 白名单） ----------


def test_validate_accepts_valid_payload() -> None:
    ok, data, flags, reason = parse_l0(valid_payload())
    assert ok and reason is None and data["band"] == 11 and flags == []


def test_validate_rejects_band_outside_whitelist() -> None:
    ok, _, flags, reason = parse_l0(valid_payload(band=13))
    assert not ok and reason == "schema_violation"
    assert "schema_violation:band_out_of_whitelist" in flags


def test_validate_rejects_dimension_out_of_range() -> None:
    ok, _, flags, _ = parse_l0(valid_payload(dimension_scores={"content": 6, "structure": 3, "language": 3}))
    assert not ok and "schema_violation:dimension_content_invalid" in flags


def test_validate_flags_band_dimension_mismatch() -> None:
    ok, _, flags, reason = parse_l0(valid_payload(band=14, dimension_scores={"content": 1, "structure": 1, "language": 1}))
    assert not ok and reason == "schema_violation" and "schema_violation:band_dimension_mismatch" in flags


def test_validate_rejects_unknown_error_type() -> None:
    ok, _, flags, _ = parse_l0(valid_payload(errors=[{"fragment": "x", "suggestion": "y", "type": "语法"}]))
    assert not ok and "schema_violation:error_0_type_unknown" in flags


# ---------- L1 填空模板（06 §3.3，6 例） ----------


def test_parse_l1_wellformed() -> None:
    ok, data, flags, reason = parse_l1(l1_text())
    assert ok and reason is None
    assert data["band"] == 11 and data["dimension_scores"]["language"] == 3
    assert len(data["errors"]) == 1 and flags == []


def test_parse_l1_accepts_ascii_colons() -> None:
    ok, data, _, reason = parse_l1(l1_text().replace("：", ": "))
    assert ok and reason is None and data["band"] == 11


def test_parse_l1_missing_band_line_fails() -> None:
    text = "\n".join(line for line in l1_text().splitlines() if not line.startswith("档位"))
    ok, _, _, reason = parse_l1(text)
    assert not ok and reason == "schema_violation"


def test_parse_l1_missing_language_line_fails() -> None:
    text = "\n".join(line for line in l1_text().splitlines() if not line.startswith("语言分"))
    ok, _, _, reason = parse_l1(text)
    assert not ok and reason == "schema_violation"


def test_parse_l1_truncates_errors_over_limit() -> None:
    rows = ["档位：11", "内容分：4", "结构分：4", "语言分：3"]
    rows += [f"错误{index}：frag{index} || sug{index} || 拼写" for index in range(1, 11)]
    ok, data, flags, reason = parse_l1("\n".join(rows))
    assert ok and reason is None
    assert len(data["errors"]) == MAX_ERROR_ROWS
    assert "schema_violation:errors_truncated" in flags


def test_parse_l1_ignores_blank_error_slots() -> None:
    ok, data, _, _ = parse_l1(l1_text(errors=2))
    assert ok and len(data["errors"]) == 2


def test_parse_l1_band_dimension_mismatch_degrades() -> None:
    ok, _, flags, reason = parse_l1(l1_text(band=14, content=1, structure=1, language=1))
    assert not ok and reason == "schema_violation"
    assert "schema_violation:band_dimension_mismatch" in flags


def test_parse_l1_unknown_error_type_degrades() -> None:
    text = l1_text().replace("|| 拼写", "|| 语态")
    ok, _, flags, reason = parse_l1(text)
    assert not ok and reason == "schema_violation"
    assert "schema_violation:error_0_type_unknown" in flags


def test_parse_l1_out_of_range_dimension_degrades() -> None:
    ok, _, _, reason = parse_l1(l1_text(content=7))
    assert not ok and reason == "schema_violation"


# ---------- L2 逐维度拆分聚合（06 §3.4，3 例） ----------


def test_parse_l2_three_rounds_ok() -> None:
    rounds = ["结论：11\n依据：语言基本准确。", "结论：4,4,3\n依据：三维综合。", "frag || sug || 拼写"]
    ok, data, flags, reason = parse_l2_rounds(rounds)
    assert ok and reason is None and flags == []
    assert data["band"] == 11 and len(data["errors"]) == 1


def test_parse_l2_reconciles_conflicting_band() -> None:
    rounds = ["结论：14\n依据：主观上不错。", "结论：4,4,4\n依据：三维综合。", "frag || sug || 拼写"]
    ok, data, flags, reason = parse_l2_rounds(rounds)
    assert ok and reason is None
    assert data["band"] == band_for_sum(12) == 11
    assert "schema_violation:band_reconciled" in flags


def test_parse_l2_reconciles_when_band_unparseable() -> None:
    rounds = ["我无法定档。", "结论：5,5,5\n依据：三维综合。", "frag || sug || 拼写"]
    ok, data, flags, _ = parse_l2_rounds(rounds)
    assert ok and data["band"] == 14 and "schema_violation:band_reconciled" in flags


def test_parse_l2_insufficient_rounds_fails() -> None:
    ok, _, _, reason = parse_l2_rounds(["结论：11\n依据：x"])
    assert not ok and reason == "round_budget_exhausted"


def test_parse_l2_missing_dimension_round_fails() -> None:
    ok, _, _, reason = parse_l2_rounds(["结论：11", "无法给出三维分", "frag || sug || 拼写"])
    assert not ok and reason == "schema_violation"


def test_parse_l2_truncates_and_degrades_on_bad_type() -> None:
    rows = "\n".join(f"f{i} || s{i} || 拼写" for i in range(10))
    ok, data, flags, _ = parse_l2_rounds(["结论：11", "结论：4,4,3", rows])
    assert ok and len(data["errors"]) == MAX_ERROR_ROWS
    assert "schema_violation:errors_truncated" in flags


def test_band_for_sum_covers_all_buckets() -> None:
    assert band_for_sum(15) == 14 and band_for_sum(13) == 14
    assert band_for_sum(12) == 11 and band_for_sum(10) == 11
    assert band_for_sum(9) == 8 and band_for_sum(7) == 8
    assert band_for_sum(6) == 5 and band_for_sum(4) == 5
    assert band_for_sum(3) == 2 and band_for_sum(1) == 2
    assert band_for_sum(0) == 0


def test_band_intervals_cover_zero_to_fifteen() -> None:
    covered: set[int] = set()
    for band, (low, high) in __import__("ss.campus.rubrics", fromlist=["ESSAY_BAND_INTERVALS"]).ESSAY_BAND_INTERVALS.items():
        covered.update(range(low, high + 1))
    assert covered == set(range(0, 16))


# ---------- 翻译：L1 逐句批改（基础正反例） ----------


def test_parse_translation_l1_ok() -> None:
    text = "档位：10\n错误1：missed phrase || 漏译\n升格示范：demo"
    ok, data, flags, reason = parse_translation_l1(text)
    assert ok and reason is None
    assert data["band"] == 10 and len(data["errors"]) == 1 and flags == []


def test_parse_translation_l1_rejects_unknown_error_type() -> None:
    text = "档位：10\n错误1：x || 时态语态\n升格示范：demo"
    ok, _, flags, reason = parse_translation_l1(text)
    assert not ok and reason == "schema_violation"
    assert "schema_violation:error_0_type_unknown" in flags


def test_parse_translation_l1_rejects_band_out_of_range() -> None:
    text = "档位：16\n升格示范：demo"
    ok, _, _, reason = parse_translation_l1(text)
    assert not ok and reason == "schema_violation"


# ---------- 评分点：L0 JSON（基础正反例） ----------


def test_parse_scoring_points_l0_ok() -> None:
    payload = {"scoring_points": [{"point": "原理点名", "status": "hit", "note": "…", "point_ref": "原理"}],
               "overall_score": 8, "upgraded_demo": "demo", "model_answer_outline": "o"}
    ok, data, flags, reason = parse_scoring_points_l0(payload)
    assert ok and reason is None and flags == []
    assert data["scoring_points"][0]["status"] == "hit"


def test_parse_scoring_points_l0_rejects_bad_status() -> None:
    payload = {"scoring_points": [{"point": "p", "status": "wrong", "note": "n", "point_ref": "r"}],
               "overall_score": 8}
    ok, _, flags, reason = parse_scoring_points_l0(payload)
    assert not ok and reason == "schema_violation"
    assert "schema_violation:scoring_point_0_status_unknown" in flags