"""app.core.routing.router — the routing engine orchestrator.

Wires the 4-stage deterministic pipeline:
    signals -> scorer -> feedback -> policy -> RoutingDecision

This is the single public entry point for the routing engine. Everything
else in this package is an internal building block.

Design notes
------------
- The engine holds no per-request mutable state; it is safe to call
  ``routing_engine.route`` concurrently. The only mutable state (feedback)
  lives in its own store with explicit update methods.
- ``RoutingContext`` carries enterprise dimensions (task_type, project_phase,
  user_role) that the policy engine uses for overrides. It is optional — a
  plain chat message has no context.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.routing.feedback import FeedbackStore
from app.core.routing.models import RoutingDecision
from app.core.routing.policy import PolicyEngine
from app.core.routing.scorer import score
from app.core.routing.signals import extract_all


@dataclass
class RoutingContext:
    """Enterprise routing dimensions for policy overrides.

    All fields optional — a plain conversational message has empty context.

    Attributes:
        user_id: Stable user identifier (for per-user feedback signatures).
        task_type: Coarse task category (e.g. "coding", "support", "general").
        project_phase: Current project phase (e.g. "planning", "implementation").
        user_role: User's role (e.g. "engineer", "analyst").
    """

    user_id: str | None = None
    task_type: str | None = None
    project_phase: str | None = None
    user_role: str | None = None


class RoutingEngine:
    """Deterministic, zero-LLM model routing engine.

    Orchestrates signal extraction, scoring, adaptive feedback, and policy
    overrides into a single ``route`` call.

    Args:
        feedback: Optional custom FeedbackStore (injected for testing).
        policy: Optional custom PolicyEngine (injected for testing).
    """

    def __init__(
        self,
        feedback: FeedbackStore | None = None,
        policy: PolicyEngine | None = None,
    ) -> None:
        self.feedback = feedback if feedback is not None else FeedbackStore()
        self.policy = policy if policy is not None else PolicyEngine()

    def route(self, message: str, ctx: RoutingContext | None = None) -> RoutingDecision:
        """Route a message to the appropriate model tier.

        Runs the deterministic 4-stage pipeline with zero LLM calls.

        Args:
            message: The user's input message (1-8000 chars).
            ctx: Optional enterprise routing context.

        Returns:
            A RoutingDecision with tier, model, score, signal breakdown, and
            audit reasons.

        Raises:
            ValueError: If message is empty.
        """
        ctx = ctx or RoutingContext()

        # Stage 1: extract deterministic signals.
        signal_results = extract_all(message)

        # Stage 2: weighted score in [0, 100].
        score_obj = score(signal_results)
        audit = [f"signals -> raw score {score_obj.total:.1f}"]

        # Stage 3: adaptive feedback adjustment.
        score_value = self.feedback.adjust_for(message, ctx.user_id, score_obj.total)
        if abs(score_value - score_obj.total) > 0.01:
            audit.append(f"feedback adjusted -> {score_value:.1f}")

        # Stage 4: policy overrides + budget guardrails.
        decision: RoutingDecision = self.policy.apply(
            score_value=score_value,
            ctx=ctx,
            signal_results=signal_results,
            audit_reasons=audit,
        )
        return decision

    def record_feedback(self, message: str, user_id: str | None, positive: bool) -> None:
        """Record thumb-up/down feedback for adaptive learning."""
        self.feedback.record(message, user_id, positive)
