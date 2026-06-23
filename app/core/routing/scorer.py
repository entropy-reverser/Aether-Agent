"""app.core.routing.scorer — combine signals into a 0-100 complexity score.

Takes the list of SignalResult from ``signals.extract_all`` and produces a
single weighted score plus a breakdown for auditability.

Design notes
------------
- Weights are centralized in SIGNAL_WEIGHTS so tuning lives in one place.
- Contributions are in [-1, 1]; negative contributions (command/conversation)
  pull the score down. The weighted sum is shifted to [0, 100].
- ``ScoreBreakdown`` exposes each signal's weighted points so the audit trail
  can show "why this score".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.routing.signals import SignalResult

# Weight per signal name. Must cover every signal in signals.SIGNALS.
# WHY: complexity/code dominate positive contributions; command gets high
#      weight because it is the primary signal that pushes toward PARSE.
#      conversation gets moderate weight for similar CHAT-leaning reasons.
SIGNAL_WEIGHTS: dict[str, float] = {
    "length": 0.12,
    "code": 0.20,
    "question": 0.10,
    "complexity": 0.22,
    "command": 0.20,
    "conversation": 0.10,
    "multi_topic": 0.06,
}

# Sum of weights (asserted to equal 1.0 in tests) so the math stays sane.
assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-6, "signal weights must sum to 1.0"

# Scale factor: weighted sum is in roughly [-1, 1]; multiply by 48 then shift
# +40 to land in [0, 100]. A perfectly neutral message -> 40 (CHAT-ish).
# WHY: base=40 puts short commands naturally near PARSE (≤35) and conversation
# near CHAT (36-55). scale=48 gives enough dynamic range for COMPLEX (>55).
_BASE_SCORE = 40.0
_SCALE = 48.0


@dataclass
class ScoreBreakdown:
    """Weighted score breakdown for one message.

    Attributes:
        total: Final score in [0, 100].
        per_signal: Ordered (name, weighted_points) pairs for the audit trail.
    """

    total: float
    per_signal: list[tuple[str, float]] = field(default_factory=list)


def score(results: list[SignalResult]) -> ScoreBreakdown:
    """Combine signal contributions into a 0-100 complexity score.

    Args:
        results: Output of ``signals.extract_all`` (one per extractor).

    Returns:
        ScoreBreakdown with the clamped total and per-signal weighted points.

    Raises:
        ValueError: If a signal name has no configured weight.
    """
    per_signal: list[tuple[str, float]] = []
    weighted_sum = 0.0
    for res in results:
        weight = SIGNAL_WEIGHTS.get(res.name)
        if weight is None:
            raise ValueError(f"no weight configured for signal '{res.name}'")
        pts = res.contribution * weight
        weighted_sum += pts
        per_signal.append((res.name, round(pts, 4)))

    total = _BASE_SCORE + weighted_sum * _SCALE
    total = max(0.0, min(100.0, total))
    return ScoreBreakdown(total=round(total, 2), per_signal=per_signal)
