"""app.core.routing.policy — YAML-driven overrides + budget guardrails.

The policy engine is the final stage of routing. It can:
  1. Pin a tier for a specific (task_type, project_phase, user_role) combo.
  2. Apply a budget guardrail: never exceed a max tier when cost must be capped.

It is deliberately declarative — the rules live in a YAML file so operators
can change routing policy without touching code (reloaded via ``reload``).

Design notes
------------
- An empty policy (no rules) is a no-op pass-through; the score-based tier wins.
- ``RoutingPolicy`` is a dataclass so it is trivially constructable in tests.
- YAML is parsed with PyYAML, imported lazily so importing this module does
  not require PyYAML unless a file is actually loaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.routing.models import build_decision
from app.core.routing.tiers import Tier, tier_for_score
from app.utils.logger import logger

if TYPE_CHECKING:
    from app.core.routing.router import RoutingContext
    from app.core.routing.signals import SignalResult


@dataclass
class OverrideRule:
    """A single policy override rule.

    Attributes:
        tier: Tier to force when this rule matches.
        task_type: Match this task type (None = wildcard).
        project_phase: Match this phase (None = wildcard).
        user_role: Match this role (None = wildcard).
        reason: Audit reason shown when the rule fires.
    """

    tier: Tier
    task_type: str | None = None
    project_phase: str | None = None
    user_role: str | None = None
    reason: str = ""


@dataclass
class RoutingPolicy:
    """The full declarative policy.

    Attributes:
        overrides: Ordered list of OverrideRule (first match wins).
        max_tier: Hard ceiling on the chosen tier (budget guardrail).
            None = no ceiling.
    """

    overrides: list[OverrideRule] = field(default_factory=list)
    max_tier: Tier | None = None


class PolicyEngine:
    """Applies enterprise overrides and budget guardrails.

    Args:
        policy: The policy to use. Defaults to an empty (pass-through) policy.
        source_path: Optional YAML path the policy was loaded from, so
            ``reload`` can re-read it.
    """

    def __init__(
        self,
        policy: RoutingPolicy | None = None,
        source_path: str | Path | None = None,
    ) -> None:
        self.policy = policy if policy is not None else RoutingPolicy()
        self._source_path = Path(source_path) if source_path else None

    def load(self, path: str | Path) -> None:
        """Load a policy from a YAML file (replaces the current policy).

        Args:
            path: Path to a YAML policy file.
        """
        self._source_path = Path(path)
        self.policy = _parse_policy_yaml(Path(path).read_text(encoding="utf-8"))
        logger.info("policy loaded from {} ({} overrides)", path, len(self.policy.overrides))

    def reload(self) -> bool:
        """Re-read the source YAML. Returns True if a source was reloaded.

        Use this for hot policy updates without restarting the process.
        """
        if not self._source_path or not self._source_path.exists():
            return False
        self.load(self._source_path)
        return True

    def apply(  # type: ignore[no-untyped-def]
        self,
        score_value: float,
        ctx: RoutingContext,
        signal_results: list[SignalResult],
        audit_reasons: list[str],
    ):
        """Apply policy to a scored message and produce a RoutingDecision.

        Order of operations:
          1. Score-based tier (the default).
          2. First matching override rule pins the tier (if any).
          3. Budget guardrail caps the tier at max_tier (if set).

        Args:
            score_value: Post-feedback score in [0, 100].
            ctx: Enterprise routing context.
            signal_results: Signal breakdown (attached to the decision).
            audit_reasons: Running audit trail (extended in place + returned).

        Returns:
            A RoutingDecision.
        """
        tier = tier_for_score(score_value)
        reasons = list(audit_reasons)

        # 1. Overrides: first match wins.
        rule = _match_override(self.policy.overrides, ctx)
        overridden = False
        if rule is not None:
            tier = rule.tier
            overridden = True
            reasons.append(f"policy override -> {tier.name}: {rule.reason}")

        # 2. Budget guardrail: never exceed max_tier.
        if self.policy.max_tier is not None and tier > self.policy.max_tier:
            tier = self.policy.max_tier
            overridden = True
            reasons.append(f"budget guardrail capped at {tier.name}")

        reasons.append(f"final tier -> {tier.name} (score {score_value:.1f})")
        return build_decision(
            tier=tier,
            score_value=score_value,
            signal_results=signal_results,
            audit_reasons=reasons,
            overridden=overridden,
        )


def _match_override(rules: list[OverrideRule], ctx: RoutingContext) -> OverrideRule | None:
    """Return the first rule whose non-None dimensions all match ctx."""
    for rule in rules:
        if rule.task_type is not None and rule.task_type != ctx.task_type:
            continue
        if rule.project_phase is not None and rule.project_phase != ctx.project_phase:
            continue
        if rule.user_role is not None and rule.user_role != ctx.user_role:
            continue
        return rule
    return None


def _parse_policy_yaml(text: str) -> RoutingPolicy:
    """Parse a YAML policy document into a RoutingPolicy.

    Expected shape (all keys optional):
        max_tier: CHAT        # PARSE | CHAT | COMPLEX
        overrides:
          - task_type: coding
            project_phase: implementation
            tier: COMPLEX
            reason: "coding in implementation needs the strong model"

    Raises:
        ValueError: If the YAML is malformed or references an unknown tier.
    """
    try:
        import yaml  # lazy import: PyYAML only needed when loading a file
    except ImportError as exc:  # pragma: no cover - covered by integration
        raise RuntimeError("PyYAML is required to load policy files") from exc

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("policy YAML must be a mapping at the top level")

    max_tier = None
    if "max_tier" in data and data["max_tier"] is not None:
        max_tier = _parse_tier(data["max_tier"])

    overrides: list[OverrideRule] = []
    for raw in data.get("overrides", []) or []:
        if not isinstance(raw, dict):
            raise ValueError("each override must be a mapping")
        overrides.append(
            OverrideRule(
                tier=_parse_tier(raw["tier"]),
                task_type=raw.get("task_type"),
                project_phase=raw.get("project_phase"),
                user_role=raw.get("user_role"),
                reason=raw.get("reason", ""),
            )
        )

    return RoutingPolicy(overrides=overrides, max_tier=max_tier)


def _parse_tier(name: str) -> Tier:
    try:
        return Tier[str(name).upper()]
    except KeyError as exc:
        raise ValueError(f"unknown tier '{name}' (expected PARSE/CHAT/COMPLEX)") from exc
