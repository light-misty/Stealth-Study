"""T01 SPIKE-1：批改解析器、校验器、降级链与语料的一致性/边界测试。

全部为纯函数与假 caller 测试，不依赖真实模型（08 文档 §1 的模型依赖策略）。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = ROOT / "scripts" / "v0-spikes"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


spike = _load("ss_v0_spike_grading", SPIKE_DIR / "spike_grading.py")
corpus_builder = _load("ss_v0_spike_fetch_corpus", SPIKE_DIR / "fetch_corpus.py")


def valid_payload(**overrides) -> dict:
    payload = {
        "band": 11,
        "dimension_scores": {"content": 4, "structure": 4, "language": 3},
        "errors": [{"fragment": "a b c", "suggestion": "abc", "type": "拼写"}],
        "upgraded_demo": "demo",
        "model_answer_outline": "outline",
    }
    payload.update(overrides)
    return payload


def l1_text(band=11, content=4, structure=4, language=3, errors=1) -> str:
    rows = [f"档位：{band}", f"内容分：{content}", f"结构分：{structure}", f"语言分：{language}"]
    for index in range(1, 9):
        if index <= errors:
            rows.append(f"错误{index}：frag{index} || sug{index} || 拼写")
        else:
            rows.append(f"错误{index}：")
    rows.append("升格示范：rewritten")
    return "\n".join(rows)


class FakeCaller:
    def __init__(self, responses: dict):
        self.responses = responses
        self.seen: list[dict] = []

    def __call__(self, messages, response_format: bool = False):
        self.seen.append({"messages": messages, "response_format": response_format})
        key = len(self.seen)
        value = self.responses.get(key, self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return value, 0


def request() -> "spike.GradeRequest":
    return spike.GradeRequest(essay_id="T01", question="话题：test", answer="This is an essay.")


def test_rubric_matches_design_doc_4_3():
    doc = (ROOT / "docs" / "dev" / "05-人设与技能包设计.md").read_text(encoding="utf-8")
    match = re.search(r"### 4\.3 .*?\n```markdown\n(.*?)\n```", doc, re.S)
    assert match, "未在 05 文档中找到 §4.3 的 markdown 代码块"
    lines = match.group(1).split("\n")
    assert lines[0].strip() == "---"
    closing = [index for index, line in enumerate(lines) if line.strip() == "---"][1]
    expected = "\n".join(lines[closing + 1 :]).strip()
    assert spike.CET_ESSAY_RUBRIC.strip() == expected


def test_rubric_error_types_enumeration_complete():
    declared = spike.rubric_section(spike.RUBRIC_ERROR_TYPES)
    compact = re.sub(r"\s+", "", declared)
    for error_type in spike.ERROR_TYPES_CET:
        assert error_type in compact
    assert len(spike.ERROR_TYPES_CET) == len(set(spike.ERROR_TYPES_CET)) == 8
    assert "\n" in declared, "05 §4.3 的枚举存在硬换行，逐字比对必须先归一化空白"


def test_rubric_sections_extractable():
    assert spike.rubric_section(spike.RUBRIC_BAND_TABLE).startswith("| 档位 |")
    assert spike.rubric_section(spike.RUBRIC_DIMENSIONS).startswith("分项维度")
    assert spike.rubric_section(spike.RUBRIC_ERROR_TYPES).startswith("错误类型枚举")


def test_extract_json_plain():
    data, reason = spike.extract_json('{"band": 11}')
    assert data == {"band": 11} and reason is None


def test_extract_json_fenced_json():
    data, reason = spike.extract_json('```json\n{"band": 14}\n```')
    assert data == {"band": 14} and reason is None


def test_extract_json_fenced_without_language():
    data, reason = spike.extract_json('```\n{"band": 8}\n```')
    assert data == {"band": 8} and reason is None


def test_extract_json_brace_inside_string():
    data, reason = spike.extract_json('{"fragment": "use { } here", "band": 5}')
    assert data is not None and data["fragment"] == "use { } here" and reason is None


def test_extract_json_nested_braces():
    raw = '{"band": 14, "dimension_scores": {"content": 5, "structure": 5, "language": 4}}'
    data, reason = spike.extract_json(raw)
    assert reason is None and data["dimension_scores"]["language"] == 4


def test_extract_json_surrounded_by_prose():
    raw = '好的，批改如下：\n{"band": 8}\n以上仅供参考。'
    data, reason = spike.extract_json(raw)
    assert data == {"band": 8} and reason is None


def test_extract_json_truncated_is_invalid():
    data, reason = spike.extract_json('{"band": 11, "dimension_scores": {"content": 4')
    assert data is None and reason == "json_invalid"


def test_extract_json_empty_is_flagged():
    data, reason = spike.extract_json("   ")
    assert data is None and reason == "empty_response"


def test_extract_json_no_aggressive_repair():
    data, reason = spike.extract_json('说明 {x} 然后 {"band": 11}')
    assert data is None and reason == "json_invalid"


def test_validate_accepts_valid_payload():
    ok, flags = spike.validate_essay_payload(valid_payload())
    assert ok and flags == []


def test_validate_rejects_band_outside_whitelist():
    ok, flags = spike.validate_essay_payload(valid_payload(band=13))
    assert not ok and "schema_violation:band_out_of_whitelist" in flags


def test_validate_rejects_dimension_out_of_range():
    ok, flags = spike.validate_essay_payload(
        valid_payload(dimension_scores={"content": 6, "structure": 3, "language": 3})
    )
    assert not ok and "schema_violation:dimension_content_invalid" in flags


def test_validate_flags_band_dimension_mismatch():
    ok, flags = spike.validate_essay_payload(
        valid_payload(band=14, dimension_scores={"content": 1, "structure": 1, "language": 1})
    )
    assert not ok and "schema_violation:band_dimension_mismatch" in flags


def test_validate_rejects_unknown_error_type():
    ok, flags = spike.validate_essay_payload(
        valid_payload(errors=[{"fragment": "x", "suggestion": "y", "type": "语法"}])
    )
    assert not ok and "schema_violation:error_0_type_unknown" in flags


def test_validate_rejects_missing_dimension_key():
    ok, flags = spike.validate_essay_payload(
        valid_payload(dimension_scores={"content": 4, "structure": 4})
    )
    assert not ok and "schema_violation:dimension_language_invalid" in flags


def test_validate_allows_empty_error_list():
    ok, flags = spike.validate_essay_payload(valid_payload(band=14, dimension_scores={"content": 5, "structure": 5, "language": 4}, errors=[]))
    assert ok and flags == []


def test_parse_l1_wellformed():
    ok, data, flags, reason = spike.parse_l1(l1_text())
    assert ok and reason is None
    assert data["band"] == 11 and data["dimension_scores"]["language"] == 3
    assert len(data["errors"]) == 1 and flags == []


def test_parse_l1_accepts_ascii_colons():
    text = l1_text().replace("：", ": ")
    ok, data, _, reason = spike.parse_l1(text)
    assert ok and reason is None and data["band"] == 11


def test_parse_l1_missing_band_line_fails():
    text = "\n".join(line for line in l1_text().splitlines() if not line.startswith("档位"))
    ok, data, _, reason = spike.parse_l1(text)
    assert not ok and reason == "schema_violation"


def test_parse_l1_missing_language_line_fails():
    text = "\n".join(line for line in l1_text().splitlines() if not line.startswith("语言分"))
    ok, data, _, reason = spike.parse_l1(text)
    assert not ok and reason == "schema_violation"


def test_parse_l1_truncates_errors_over_limit():
    rows = ["档位：11", "内容分：4", "结构分：4", "语言分：3"]
    rows += [f"错误{index}：frag{index} || sug{index} || 拼写" for index in range(1, 11)]
    ok, data, flags, reason = spike.parse_l1("\n".join(rows))
    assert ok and reason is None
    assert len(data["errors"]) == spike.MAX_ERROR_ROWS
    assert "schema_violation:errors_truncated" in flags


def test_parse_l1_ignores_blank_error_slots():
    ok, data, _, _ = spike.parse_l1(l1_text(errors=2))
    assert ok and len(data["errors"]) == 2


def test_parse_l1_band_dimension_mismatch_degrades():
    ok, data, flags, reason = spike.parse_l1(l1_text(band=14, content=1, structure=1, language=1))
    assert not ok and reason == "schema_violation"
    assert "schema_violation:band_dimension_mismatch" in flags


def test_parse_l1_unknown_error_type_degrades():
    text = l1_text().replace("|| 拼写", "|| 语态")
    ok, data, flags, reason = spike.parse_l1(text)
    assert not ok and reason == "schema_violation"
    assert "schema_violation:error_0_type_unknown" in flags


def test_parse_l1_out_of_range_dimension_degrades():
    ok, data, _, reason = spike.parse_l1(l1_text(content=7))
    assert not ok and reason == "schema_violation"


def test_parse_l2_three_rounds_ok():
    rounds = ["结论：11\n依据：语言基本准确。", "结论：4,4,3\n依据：三维综合。", "frag || sug || 拼写"]
    ok, data, flags, reason = spike.parse_l2_rounds(rounds)
    assert ok and reason is None and flags == []
    assert data["band"] == 11 and len(data["errors"]) == 1


def test_parse_l2_reconciles_conflicting_band():
    rounds = ["结论：14\n依据：主观上不错。", "结论：4,4,4\n依据：三维综合。", "frag || sug || 拼写"]
    ok, data, flags, reason = spike.parse_l2_rounds(rounds)
    assert ok and reason is None
    assert data["band"] == spike.band_for_sum(12) == 11
    assert "schema_violation:band_reconciled" in flags


def test_parse_l2_reconciles_when_band_unparseable():
    rounds = ["我无法定档。", "结论：5,5,5\n依据：三维综合。", "frag || sug || 拼写"]
    ok, data, flags, _ = spike.parse_l2_rounds(rounds)
    assert ok and data["band"] == 14 and "schema_violation:band_reconciled" in flags


def test_parse_l2_insufficient_rounds_fails():
    ok, data, _, reason = spike.parse_l2_rounds(["结论：11\n依据：x"])
    assert not ok and reason == "round_budget_exhausted"


def test_parse_l2_missing_dimension_round_fails():
    ok, data, _, reason = spike.parse_l2_rounds(["结论：11", "无法给出三维分", "frag || sug || 拼写"])
    assert not ok and reason == "schema_violation"


def test_parse_l2_truncates_and_degrades_on_bad_type():
    rows = "\n".join(f"f{i} || s{i} || 拼写" for i in range(10))
    ok, data, flags, _ = spike.parse_l2_rounds(["结论：11", "结论：4,4,3", rows])
    assert ok and len(data["errors"]) == spike.MAX_ERROR_ROWS


def test_band_for_sum_covers_all_buckets():
    assert spike.band_for_sum(15) == 14
    assert spike.band_for_sum(13) == 14
    assert spike.band_for_sum(12) == 11
    assert spike.band_for_sum(10) == 11
    assert spike.band_for_sum(9) == 8
    assert spike.band_for_sum(7) == 8
    assert spike.band_for_sum(6) == 5
    assert spike.band_for_sum(4) == 5
    assert spike.band_for_sum(3) == 2
    assert spike.band_for_sum(1) == 2
    assert spike.band_for_sum(0) == 0


def test_band_intervals_cover_zero_to_fifteen():
    covered = set()
    for band, (low, high) in spike.BAND_INTERVALS.items():
        assert band in spike.BAND_VALUES
        covered.update(range(low, high + 1))
    assert covered == set(range(0, 16))


def test_l0_prompt_contains_rubric_schema_and_instruction():
    messages = spike.build_l0_messages(request())
    system = messages[0]["content"]
    assert spike.CET_ESSAY_RUBRIC in system
    assert '"dimension_scores"' in system
    assert "只输出一个 JSON 对象" in system
    assert messages[1]["content"].startswith("题目：")


def test_l1_prompt_contains_all_template_rows():
    messages = spike.build_l1_messages(request())
    system = messages[0]["content"]
    for row in spike.L1_TEMPLATE.splitlines():
        assert row in system
    assert "不要增删行" in system


def test_l2_prompts_use_level_specific_sections():
    first = spike.build_l2_messages(0, request())[0]["content"]
    second = spike.build_l2_messages(1, request())[0]["content"]
    third = spike.build_l2_messages(2, request())[0]["content"]
    assert "| 一档 | 14 分 |" in first and "定档" in first
    assert "各 0-5 分" in second and "内容" in second
    assert "原片段 || 修改建议 || 类型" in third


def test_grade_one_l0_success():
    caller = FakeCaller({1: json.dumps(valid_payload())})
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert outcome.ok and outcome.degrade_level == 0 and outcome.band == 11
    assert outcome.calls == 1 and outcome.transport_retries == 0
    assert len(caller.seen) == 1 and caller.seen[0]["response_format"] is False


def test_grade_one_response_format_passed_for_l0_variant():
    caller = FakeCaller({1: json.dumps(valid_payload())})
    outcome = spike.grade_one(caller, request(), "l0_response_format")
    assert outcome.degrade_level == 0
    assert caller.seen[0]["response_format"] is True


def test_grade_one_falls_back_to_l1():
    caller = FakeCaller({1: "这不是 JSON", 2: l1_text()})
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert outcome.ok and outcome.degrade_level == 1 and outcome.calls == 2
    assert outcome.trace[0]["reason"] == "json_invalid"


def test_grade_one_falls_back_to_l2():
    caller = FakeCaller(
        {
            1: "{\"band\": 11, \"dimension_scores\": {\"content\": 9}}",
            2: "模板填不出来",
            3: "结论：11\n依据：x",
            4: "结论：4,4,3\n依据：x",
            5: "frag || sug || 拼写",
        }
    )
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert outcome.ok and outcome.degrade_level == 2 and outcome.calls == spike.CALL_BUDGET
    assert outcome.band == 11


def test_grade_one_l3_keeps_raw_text():
    caller = FakeCaller({"default": "这是一段没有结构的批改文字。"})
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert outcome.ok and outcome.degrade_level == 3
    assert outcome.band is None and outcome.calls == spike.CALL_BUDGET


def test_grade_one_l3_failure_reports_empty():
    caller = FakeCaller({"default": "   "})
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert not outcome.ok and outcome.degrade_level == 3
    assert outcome.fail_reason == "MODEL_EMPTY" and outcome.calls == spike.CALL_BUDGET


def test_grade_one_provider_error_degrades_instead_of_aborting():
    caller = FakeCaller({1: RuntimeError("APITimeoutError"), 2: l1_text()})
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert outcome.degrade_level == 1
    assert outcome.trace[0]["reason"] == "provider_error:RuntimeError"


def test_grade_one_timeout_without_text_reports_timeout():
    caller = FakeCaller({"default": RuntimeError("ReadTimeout")})
    outcome = spike.grade_one(caller, request(), "l0_plain")
    assert not outcome.ok and outcome.fail_reason == "MODEL_TIMEOUT"


def test_model_caller_retries_without_response_format():
    provider = SimpleNamespace(complete=None)
    seen: list[dict] = []

    def complete(*, model, messages, **settings):
        seen.append(settings)
        if "response_format" in settings:
            raise RuntimeError("unsupported parameter: response_format")
        return SimpleNamespace(text='{"band": 11}')

    provider.complete = complete
    caller = spike.ModelCaller(provider, "m")
    text, retries = caller([{"role": "user", "content": "x"}], response_format=True)
    assert text == '{"band": 11}' and retries == 1 and len(seen) == 2
    assert "response_format" not in seen[1]


def test_model_caller_keeps_response_format_when_accepted():
    seen: list[dict] = []

    def complete(*, model, messages, **settings):
        seen.append(settings)
        return SimpleNamespace(text='{"band": 11}')

    caller = spike.ModelCaller(SimpleNamespace(complete=complete), "m")
    _, retries = caller([{"role": "user", "content": "x"}], response_format=True)
    assert retries == 0 and len(seen) == 1 and "response_format" in seen[0]


def test_model_caller_passes_temperature_zero_and_timeout():
    seen: list[dict] = []

    def complete(*, model, messages, **settings):
        seen.append(settings)
        return SimpleNamespace(text="{}")

    caller = spike.ModelCaller(SimpleNamespace(complete=complete), "m")
    caller([{"role": "user", "content": "x"}])
    assert seen[0]["temperature"] == 0
    assert seen[0]["timeout"] == spike.PROVIDER_TIMEOUT_S


def fake_record(essay_id, model, condition, level, ok=True, calls=1, flags=None, band=11, retries=0):
    return {
        "essay_id": essay_id,
        "model": model,
        "condition": condition,
        "ok": ok,
        "degrade_level": level,
        "band": band,
        "schema_flags": flags or [],
        "calls": calls,
        "transport_retries": retries,
    }


def test_summarize_distribution_math():
    records = [
        fake_record("E01", "m1", "l0_plain", 0),
        fake_record("E02", "m1", "l0_plain", 1, calls=2),
        fake_record("E03", "m1", "l0_plain", 2, calls=5),
        fake_record("E04", "m1", "l0_plain", 3, calls=5, band=None),
        fake_record("E05", "m1", "l0_plain", 0),
    ]
    summary = spike.summarize(records, ["m1"], ["l0_plain"])
    cell = summary["grid"]["m1|l0_plain"]
    assert cell["samples"] == 5
    assert cell["degrade_distribution"] == {"0": 2, "1": 1, "2": 1, "3": 1}
    assert cell["l0_success_rate"] == 0.4
    assert cell["l0_l1_success_rate"] == 0.6
    assert cell["calls_max"] == 5 and cell["calls_budget_ok"] is True
    assert summary["pooled_by_model"]["m1"]["l0_l1_success_rate"] == 0.6


def test_summarize_flags_budget_violation():
    records = [fake_record("E01", "m1", "l0_plain", 0, calls=6)]
    summary = spike.summarize(records, ["m1"], ["l0_plain"])
    assert summary["grid"]["m1|l0_plain"]["calls_budget_ok"] is False


def test_corpus_shape():
    payload = json.loads((SPIKE_DIR / "corpus" / "cet_essays.json").read_text(encoding="utf-8"))
    essays = payload["essays"]
    assert len(essays) == 20
    assert len({essay["essay_id"] for essay in essays}) == 20
    paired = [essay for essay in essays if essay["role_group"] == "paired"]
    solo = [essay for essay in essays if essay["role_group"] == "solo"]
    assert len(paired) == 10 and len(solo) == 10
    assert all(essay["reference"] for essay in paired)
    assert all(essay["reference"] is None for essay in solo)
    assert {essay["track"] for essay in essays} == {"cet4", "cet6"}


def test_corpus_text_integrity():
    payload = json.loads((SPIKE_DIR / "corpus" / "cet_essays.json").read_text(encoding="utf-8"))
    problems = corpus_builder.verify_corpus(payload)
    assert problems == []


def test_corpus_manifest_repairs_all_hit():
    manifest = json.loads(
        (SPIKE_DIR / "corpus" / "corpus_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["essay_count"] == 20
    corpus_builder.verify_repairs(manifest["applied_repairs"])
    assert len(manifest["applied_repairs"]) == len(corpus_builder.ARTIFACT_REPAIRS)
    for group in manifest["groups"]:
        assert group["essay_count"] >= 3 and len(group["sha256"]) == 64
    assert manifest["source"]["license"] == "MIT"


def test_corpus_artifact_repairs_are_context_anchored():
    for broken, fixed in corpus_builder.ARTIFACT_REPAIRS:
        assert broken != fixed and len(broken.split()) >= 3
        assert broken not in fixed
