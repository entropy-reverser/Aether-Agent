"""scripts.demo_routing — CLI demo of the routing engine.

Prints a table showing how various messages route to tiers, with their score
breakdown. No server, no Redis, no LLM needed.

Usage: python scripts/demo_routing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.routing import RoutingContext, routing_engine  # noqa: E402
from app.core.routing.policy import PolicyEngine  # noqa: E402
from app.core.routing.tiers import Tier  # noqa: E402

# Load the example enterprise policy so the demo shows overrides in action.
_POLICY_PATH = Path(__file__).resolve().parent.parent / "enterprise_routing.example.yaml"
if _POLICY_PATH.exists():
    routing_engine.policy = PolicyEngine()
    routing_engine.policy.load(_POLICY_PATH)

DEMO_CASES: list[tuple[str, RoutingContext | None, str]] = [
    ("translate this to english", None, "short command -> PARSE"),
    ("parse this JSON for me", None, "parse command -> PARSE"),
    ("hello, how are you today?", None, "casual greeting -> CHAT"),
    ("how do I build a rate limiter in Redis?", None, "technical question -> CHAT"),
    (
        "Please analyze and compare the trade-offs between a Redis token bucket "
        "and a sliding window rate limiter. Walk through the design step by step.",
        None,
        "deep analysis -> COMPLEX",
    ),
    (
        "fix this bug",
        RoutingContext(task_type="coding", project_phase="implementation"),
        "coding task -> policy override -> COMPLEX",
    ),
]


def _color(tier: Tier) -> str:
    return {
        Tier.PARSE: "\033[36m",
        Tier.CHAT: "\033[32m",
        Tier.COMPLEX: "\033[35m",
    }.get(tier, "")


def main() -> None:
    print("=" * 90)
    print("Aether-Agent v2 — Routing Engine Demo")
    print("=" * 90)
    for message, ctx, expected in DEMO_CASES:
        decision = routing_engine.route(message, ctx)
        color = _color(decision.tier)
        reset = "\033[0m"
        print(
            f"\n{color}[{decision.tier.name}]{reset} score={decision.score:5.1f} "
            f"model={decision.model}  overridden={decision.overridden}"
        )
        print(f"  msg: {message[:70]}")
        print(f"  expect: {expected}")
        print("  signals:")
        for s in decision.signal_results:
            if s.contribution != 0.0:
                print(f"    {s.name:14s} contrib={s.contribution:+.3f}  ({s.note})")
        print("  audit:")
        for reason in decision.audit_reasons[-2:]:
            print(f"    - {reason}")


if __name__ == "__main__":
    main()
