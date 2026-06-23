"""app.core.routing — zero-LLM score-based model routing engine.

Deterministic 4-stage pipeline: signals -> scorer -> feedback -> policy.
No LLM calls are made for classification, saving token cost and latency.

Public API (§8.2 contract):
    RoutingEngine.route(message, ctx) -> RoutingDecision

Convenience exports:
    Tier, RoutingDecision, RoutingContext, routing_engine
"""

from app.core.routing.models import RoutingDecision
from app.core.routing.router import RoutingContext, RoutingEngine
from app.core.routing.tiers import Tier

__all__ = [
    "RoutingContext",
    "RoutingDecision",
    "RoutingEngine",
    "Tier",
    "routing_engine",
]

# Module-level singleton (per §8.1 singletons at module bottom).
routing_engine = RoutingEngine()
