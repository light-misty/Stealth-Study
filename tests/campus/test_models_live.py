"""Opt-in live check of the static model list (INF-08 / ADR-06).

`test_models.py` proves offline that every declared id exists in `ss.providers.matrix`. It
cannot prove the ids actually answer — and T04 §4 决策一 requires exactly that before a
vendor is trusted: "V0.1 接入任何新厂商模型前，须先用该厂商模型重跑…". This module closes
that gap for the DeepSeek entries, which are the ones the static list declares as the
*minimum* usable model for a task.

Skipped unless `DEEPSEEK_API_KEY` is set. Each case asks for a one-token reply, so a full run
costs a handful of tokens.
"""

from __future__ import annotations

import os

import pytest

from ss.campus import models
from ss.providers import registry

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="set DEEPSEEK_API_KEY to run the live model check",
)

DEEPSEEK_PREFIX = "deepseek:"
PROMPT = "只回复两个字：收到"
# `deepseek-v4-*` answer with a reasoning span before the reply, so a budget sized for a
# two-character answer returns an empty `text` with `finish_reason='length'`. 128 leaves
# room for the reasoning span plus the reply and still costs a few dozen tokens.
REPLY_BUDGET = 128


def deepseek_minimum_models() -> list[str]:
    """The DeepSeek ids the static list promises as task minimums."""
    return sorted(
        {
            choice.minimum
            for choice in models.TASK_MODEL_CHOICES.values()
            if choice.minimum.startswith(DEEPSEEK_PREFIX)
        }
    )


def test_the_static_list_names_a_deepseek_minimum_for_some_task() -> None:
    assert deepseek_minimum_models()


@pytest.mark.parametrize("model_id", deepseek_minimum_models())
def test_minimum_model_answers_a_one_token_prompt(model_id: str) -> None:
    provider = registry.build_provider_client("deepseek", {}, None)
    turn = provider.complete(
        model=model_id.split(":", 1)[1],
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=REPLY_BUDGET,
    )
    assert turn.usage and turn.usage.input > 0
    assert turn.text and turn.text.strip()
    assert turn.finish_reason != "length"


def test_a_declared_minimum_can_be_reached_through_the_router_shape() -> None:
    """The picker returns `(model, fallback)` in the id form the router consumes."""
    recommended, minimum = models.pick("essay", "cet")
    assert recommended in registry.provider_names() or ":" in recommended
    assert minimum.split(":", 1)[0] in registry.provider_names()
