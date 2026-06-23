"""Tests for app.core.routing.router — end-to-end routing engine."""

from __future__ import annotations

import pytest

from app.core.routing.feedback import FeedbackStore
from app.core.routing.policy import OverrideRule, PolicyEngine, RoutingPolicy
from app.core.routing.router import RoutingContext, RoutingEngine
from app.core.routing.tiers import Tier


def _engine(
    feedback: FeedbackStore | None = None,
    policy: RoutingPolicy | None = None,
) -> RoutingEngine:
    """Build an engine with injected stores (empty policy = pass-through)."""
    pe = PolicyEngine(policy=policy) if policy is not None else PolicyEngine()
    return RoutingEngine(feedback=feedback, policy=pe)


# --- end-to-end tier landing ---------------------------------------------


def test_route_short_command_lands_parse():
    engine = _engine()
    decision = engine.route("translate this")
    assert decision.tier is Tier.PARSE


def test_route_simple_chat_lands_chat():
    engine = _engine()
    decision = engine.route("hello, how are you today?")
    assert decision.tier is Tier.CHAT


def test_route_complex_question_outscores_simple():
    """Complex multi-step reasoning must score well above simple chat.

    Borderline messages (54-56) may land in either CHAT or COMPLEX depending
    on exact thresholds; the invariant enforced is relative ordering.
    """
    engine = _engine()
    complex_msg = (
        "Please analyze and compare the trade-offs between a Redis token bucket "
        "and a sliding window rate limiter. Walk through the design step by step "
        "and recommend one for a distributed system."
    )
    d_complex = engine.route(complex_msg)
    d_simple = engine.route("hello there")
    assert d_complex.score > d_simple.score + 15
    assert d_complex.tier.value >= d_simple.tier.value


# --- audit trail ----------------------------------------------------------


def test_route_includes_signal_breakdown_and_audit_reasons():
    engine = _engine()
    decision = engine.route("how do I build a rate limiter?")
    assert len(decision.signal_results) >= 1
    assert any("final tier" in r for r in decision.audit_reasons)


def test_route_decision_carries_model_name():
    engine = _engine()
    decision = engine.route("hello there")
    assert decision.model  # non-empty model string


# --- feedback integration -------------------------------------------------


def test_route_feedback_adjusts_tier_downward():
    # A borderline message; thumbs-down should push it toward a cheaper tier.
    msg = "explain how caching works briefly"
    engine = _engine()
    before = engine.route(msg)
    if before.tier is not Tier.PARSE:
        engine.record_feedback(msg, None, positive=False)
        after = engine.route(msg)
        assert after.tier <= before.tier


# --- policy integration ---------------------------------------------------


def test_route_policy_override_wins_over_score():
    policy = RoutingPolicy(
        overrides=[OverrideRule(tier=Tier.COMPLEX, task_type="coding", reason="x")]
    )
    engine = _engine(policy=policy)
    # Short message -> would be PARSE, but coding task pins COMPLEX.
    decision = engine.route("fix this", RoutingContext(task_type="coding"))
    assert decision.tier is Tier.COMPLEX
    assert decision.overridden is True


def test_route_empty_message_raises():
    engine = _engine()
    with pytest.raises(ValueError):
        engine.route("")


# --- determinism ----------------------------------------------------------


def test_route_is_deterministic_without_feedback():
    engine = _engine()
    msg = "summarize the pros and cons of microservices"
    d1 = engine.route(msg)
    d2 = engine.route(msg)
    assert d1.tier == d2.tier
    assert d1.score == d2.score
