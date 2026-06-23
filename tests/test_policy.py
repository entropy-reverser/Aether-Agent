"""Tests for app.core.routing.policy — YAML overrides + budget guardrails."""

from __future__ import annotations

import pytest

from app.core.routing.policy import OverrideRule, PolicyEngine, RoutingPolicy
from app.core.routing.router import RoutingContext
from app.core.routing.signals import SignalResult
from app.core.routing.tiers import Tier


def _empty_signals() -> list[SignalResult]:
    return [SignalResult(name="length", raw=0.0, contribution=0.0)]


def _ctx(**kwargs) -> RoutingContext:
    return RoutingContext(**kwargs)


def test_empty_policy_passes_score_through():
    engine = PolicyEngine(policy=RoutingPolicy())
    decision = engine.apply(40.0, _ctx(), _empty_signals(), ["start"])
    # Score 40 -> CHAT (25 < 40 <= 55), no override.
    assert decision.tier is Tier.CHAT
    assert decision.overridden is False


def test_override_pins_tier_by_task_type():
    policy = RoutingPolicy(
        overrides=[
            OverrideRule(tier=Tier.COMPLEX, task_type="coding", reason="coding needs strong model")
        ]
    )
    engine = PolicyEngine(policy=policy)
    # Score 10 would be PARSE, but override forces COMPLEX.
    decision = engine.apply(10.0, _ctx(task_type="coding"), _empty_signals(), [])
    assert decision.tier is Tier.COMPLEX
    assert decision.overridden is True
    assert any("override" in r for r in decision.audit_reasons)


def test_override_does_not_match_other_task():
    policy = RoutingPolicy(
        overrides=[OverrideRule(tier=Tier.COMPLEX, task_type="coding", reason="x")]
    )
    engine = PolicyEngine(policy=policy)
    decision = engine.apply(10.0, _ctx(task_type="support"), _empty_signals(), [])
    assert decision.tier is Tier.PARSE  # score-based, no override
    assert decision.overridden is False


def test_override_wildcards_match_when_none():
    # Rule with only user_role set; task_type/phase are wildcards (None).
    policy = RoutingPolicy(
        overrides=[OverrideRule(tier=Tier.CHAT, user_role="analyst", reason="x")]
    )
    engine = PolicyEngine(policy=policy)
    decision = engine.apply(
        80.0,
        _ctx(user_role="analyst", task_type="anything"),
        _empty_signals(),
        [],
    )
    assert decision.tier is Tier.CHAT
    assert decision.overridden is True


def test_first_matching_override_wins():
    policy = RoutingPolicy(
        overrides=[
            OverrideRule(tier=Tier.COMPLEX, task_type="coding", reason="first"),
            OverrideRule(tier=Tier.PARSE, task_type="coding", reason="second"),
        ]
    )
    engine = PolicyEngine(policy=policy)
    decision = engine.apply(10.0, _ctx(task_type="coding"), _empty_signals(), [])
    assert decision.tier is Tier.COMPLEX  # first rule wins


def test_max_tier_guardrail_caps_tier():
    policy = RoutingPolicy(max_tier=Tier.CHAT)
    engine = PolicyEngine(policy=policy)
    # Score 90 -> COMPLEX, but guardrail caps at CHAT.
    decision = engine.apply(90.0, _ctx(), _empty_signals(), [])
    assert decision.tier is Tier.CHAT
    assert decision.overridden is True
    assert any("guardrail" in r for r in decision.audit_reasons)


def test_max_tier_allows_lower_tier_unchanged():
    policy = RoutingPolicy(max_tier=Tier.COMPLEX)
    engine = PolicyEngine(policy=policy)
    decision = engine.apply(10.0, _ctx(), _empty_signals(), [])
    assert decision.tier is Tier.PARSE
    assert decision.overridden is False


def test_load_policy_from_yaml(tmp_path):
    yaml_text = """
max_tier: CHAT
overrides:
  - task_type: coding
    tier: COMPLEX
    reason: "coding needs strong model"
"""
    path = tmp_path / "policy.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    engine = PolicyEngine()
    engine.load(path)

    assert engine.policy.max_tier is Tier.CHAT
    assert engine.policy.overrides[0].tier is Tier.COMPLEX

    decision = engine.apply(10.0, _ctx(task_type="coding"), _empty_signals(), [])
    # Override wins over guardrail ordering: override sets COMPLEX, then guardrail caps CHAT.
    assert decision.tier is Tier.CHAT


def test_load_invalid_tier_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("max_tier: ULTRA\n", encoding="utf-8")
    engine = PolicyEngine()
    with pytest.raises(ValueError):
        engine.load(path)


def test_reload_without_source_returns_false():
    engine = PolicyEngine()
    assert engine.reload() is False
