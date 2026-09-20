"""T07 批改引擎测试（08 §5.4 的降级链路 mock 回放 + 06 §2.2 引擎契约）。

全部 mock 掉 `ProviderClient.complete`（按调用序号回放 T01 spike 的文本形态），覆盖：
T07 验收①（解析链复用）、③（温度 0 / ≤5 次 / 90s 超时生效）、④（档位矛盾反推 `band_reconciled`），
以及 08 §5.4 的"先坏后好"降级回放、降级提示字段。不依赖真实模型。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from stealth_study.campus.grading import (
    CALL_BUDGET,
    DEGRADE_NOTICE,
    PROVIDER_TIMEOUT_S,
    TEMPERATURE,
    GradingEngine,
    GradeRequest,
)


def valid_essay(band: int = 11) -> str:
    return json.dumps(
        {
            "band": band,
            "dimension_scores": {"content": 4, "structure": 4, "language": 3},
            "errors": [{"fragment": "a b c", "suggestion": "abc", "type": "拼写"}],
            "upgraded_demo": "demo",
            "model_answer_outline": "outline",
        }
    )


def l1_text(band: int = 11) -> str:
    rows = ["档位：11", "内容分：4", "结构分：4", "语言分：3"]
    rows += [f"错误{i}：" for i in range(1, 9)]
    rows.append("升格示范：rewritten")
    rows[0] = f"档位：{band}"
    return "\n".join(rows)


class FakeProvider:
    """按调用序号回放 preset 输出的假 provider（`turn.text` 语义）。"""

    def __init__(self, responses: dict):
        self.responses = responses
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings) -> SimpleNamespace:
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


def picker(kind: str, track_type: str) -> tuple[str, str]:
    del kind, track_type
    return ("model-a", "model-fallback")


def request(**overrides: object) -> GradeRequest:
    base = GradeRequest(
        profile_id="p",
        track_type="cet4",
        kind="essay",
        question="题目：test",
        answer="This is an essay.",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


async def grade(provider: FakeProvider, /, start_level: int = 0) -> tuple[GradingEngine, object]:
    engine = GradingEngine(provider, picker, start_level=start_level)
    result = await engine.grade(request())
    return engine, result


# ---------- 基础：L0 成功 ----------


async def test_grade_l0_success() -> None:
    provider = FakeProvider({1: valid_essay()})
    _, result = await grade(provider)
    assert result.ok and result.degrade_level == 0 and result.band == 11
    assert result.calls == 1 and result.model_used == "model-a"
    assert result.notice is None


async def test_grade_l0_success_uses_response_format_then_drops_on_reject() -> None:
    seen_settings: list[dict] = []

    def complete(*, model: str, messages: list[dict], **settings) -> SimpleNamespace:
        del model, messages
        seen_settings.append(settings)
        if "response_format" in settings:
            raise RuntimeError("unsupported parameter: response_format")
        return SimpleNamespace(text=valid_essay())

    engine = GradingEngine(SimpleNamespace(complete=complete), picker)
    result = await engine.grade(request())
    assert result.ok and result.degrade_level == 0
    assert len(seen_settings) == 2
    assert "response_format" in seen_settings[0]
    assert "response_format" not in seen_settings[1]
    assert result.retries == 1


# ---------- 降级链路 ----------


async def test_grade_falls_back_to_l1() -> None:
    provider = FakeProvider({1: "这不是 JSON", 2: l1_text()})
    _, result = await grade(provider)
    assert result.ok and result.degrade_level == 1 and result.band == 11
    assert result.calls == 2
    assert result.degrade_trace[0]["reason"] == "json_invalid"
    assert result.notice == DEGRADE_NOTICE


async def test_grade_falls_back_to_l2_and_reconciles_band() -> None:
    provider = FakeProvider(
        {
            1: '{"band": 11, "dimension_scores": {"content": 9}}',
            2: "模板填不出来",
            3: "结论：14\n依据：主观上不错。",
            4: "结论：4,4,4\n依据：三维综合。",
            5: "frag || sug || 拼写",
        }
    )
    _, result = await grade(provider)
    assert result.ok and result.degrade_level == 2
    assert result.band == 11
    assert result.calls == CALL_BUDGET
    assert any("band_reconciled" in flag for flag in result.schema_flags)


async def test_grade_l3_keeps_raw_text() -> None:
    provider = FakeProvider({"default": "这是一段没有结构的批改文字。"})
    _, result = await grade(provider)
    assert result.ok and result.degrade_level == 3
    assert result.band is None and result.calls == CALL_BUDGET
    assert result.raw_text and result.notice == DEGRADE_NOTICE


async def test_grade_l3_failure_reports_empty() -> None:
    provider = FakeProvider({"default": "   "})
    _, result = await grade(provider)
    assert not result.ok and result.degrade_level == 3
    assert result.fail_reason == "MODEL_EMPTY" and result.calls == CALL_BUDGET


async def test_grade_provider_error_degrades_instead_of_aborting() -> None:
    provider = FakeProvider(
        {1: RuntimeError("APITimeoutError"), 2: RuntimeError("APITimeoutError"), 3: l1_text()}
    )
    _, result = await grade(provider)
    assert result.ok and result.degrade_level == 1
    assert result.degrade_trace[0]["reason"] == "provider_error:RuntimeError"


async def test_grade_timeout_without_text_reports_timeout() -> None:
    provider = FakeProvider({"default": RuntimeError("ReadTimeout")})
    _, result = await grade(provider)
    assert not result.ok and result.fail_reason == "MODEL_TIMEOUT"


# ---------- 三项参数生效（T07 验收③） ----------


async def test_every_call_passes_temperature_zero_and_timeout() -> None:
    provider = FakeProvider({"default": valid_essay()})
    await grade(provider)
    for call in provider.seen:
        assert call["settings"]["temperature"] == TEMPERATURE == 0
        assert call["settings"]["timeout"] == PROVIDER_TIMEOUT_S == 90


async def test_call_budget_never_exceeded() -> None:
    provider = FakeProvider({"default": "no structure at all"})
    _, result = await grade(provider)
    assert result.calls == CALL_BUDGET == 5
    assert len(provider.seen) <= CALL_BUDGET * 2  # L0 的 response_format 重试至多 1 次


# ---------- 起点档位（06 §8-3 GRADING_START_LEVEL） ----------


async def test_start_level_1_skips_l0() -> None:
    provider = FakeProvider({1: l1_text()})
    engine = GradingEngine(provider, picker, start_level=1)
    result = await engine.grade(request())
    assert result.degrade_level == 1
    assert len(provider.seen) == 1
    assert "行式模板" in provider.seen[0]["messages"][0]["content"]
    assert "response_format" not in provider.seen[0]["settings"]


# ---------- 多 kind 路由 ----------


async def test_grade_translation_kind_parses_band() -> None:
    provider = FakeProvider(
        {1: '{"band": 10, "errors": [{"fragment": "x", "suggestion": "", "type": "漏译"}]}'}
    )
    engine = GradingEngine(provider, picker)
    result = await engine.grade(request(kind="translation"))
    assert result.ok and result.degrade_level == 0 and result.band == 10


async def test_grade_scoring_points_kind_parses_statuses() -> None:
    payload = {
        "scoring_points": [
            {"point": "原理点名", "status": "hit", "note": "…", "point_ref": "原理"}
        ],
        "overall_score": 8,
    }
    provider = FakeProvider({1: json.dumps(payload)})
    engine = GradingEngine(provider, picker)
    result = await engine.grade(request(kind="short_answer"))
    assert result.ok and result.degrade_level == 0
    assert result.scoring_points[0]["status"] == "hit"
    assert result.band is None


async def test_grade_unknown_kind_falls_back_by_rubric_id_request_shape() -> None:
    provider = FakeProvider({1: valid_essay()})
    engine = GradingEngine(provider, picker)
    result = await engine.grade(request(kind="essay", custom_rubric="自定义细则"))
    assert result.ok and result.degrade_level == 0
    assert "自定义细则" in provider.seen[0]["messages"][0]["content"]


# ---------- rubric / kind 兜底 ----------


async def test_default_start_level_constant_is_zero() -> None:
    from stealth_study.campus.grading import DEFAULT_GRADING_START_LEVEL

    assert DEFAULT_GRADING_START_LEVEL == 0
    engine = GradingEngine(FakeProvider({1: valid_essay()}), picker)
    assert engine.start_level == 0