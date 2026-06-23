"""app.core.routing.models — routing data models (no logic, no cycles).

Holds ``RoutingDecision`` and ``build_decision`` so that both ``router.py``
and ``policy.py`` can import them without creating a circular dependency.

Design notes
------------
- Keeping the decision dataclass here (rather than in router.py) breaks the
  router<->policy cycle cleanly: policy imports models, router imports both.
- No business logic lives here — just data + a tiny constructor helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.routing.signals import SignalResult
from app.core.routing.tiers import Tier, model_for_tier


@dataclass
class RoutingDecision:
    """The full, auditable outcome of routing one message.

    Attributes:
        tier: Chosen tier.
        model: Model name mapped from the tier.
        score: Final 0-100 complexity score (after feedback + policy).
        signal_results: Per-signal breakdown for audit/explainability.
        audit_reasons: Ordered human-readable reasons explaining the decision.
        overridden: True when policy forced a tier different from score-based.
    """

    tier: Tier
    model: str
    score: float
    signal_results: list[SignalResult]
    audit_reasons: list[str] = field(default_factory=list)
    overridden: bool = False


def build_decision(
    tier: Tier,
    score_value: float,
    signal_results: list[SignalResult],
    audit_reasons: list[str],
    overridden: bool = False,
) -> RoutingDecision:
    """Construct a RoutingDecision (shared by engine + policy)."""
    return RoutingDecision(
        tier=tier,
        model=model_for_tier(tier),
        score=round(score_value, 2),
        signal_results=signal_results,
        audit_reasons=audit_reasons,
        overridden=overridden,
    )
