"""Tests for app.core.routing.scorer — weighted score combination."""

from __future__ import annotations

from app.core.routing.scorer import SIGNAL_WEIGHTS, ScoreBreakdown, score
from app.core.routing.signals import SignalResult


def _results(*contribs: float) -> list[SignalResult]:
    """Build SignalResults in SIGNAL_WEIGHTS key order with given contributions."""
    names = list(SIGNAL_WEIGHTS.keys())
    assert len(contribs) == len(names), "provide one contribution per signal"
    return [
        SignalResult(name=names[i], raw=1.0, contribution=contribs[i]) for i in range(len(names))
    ]


def test_signal_weights_sum_to_one():
    assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-6


def test_score_neutral_message_around_base():
    # All-zero contributions -> base score (40 with current config).
    breakdown = score(_results(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    assert breakdown.total == 40.0


def test_score_all_max_high():
    breakdown = score(_results(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))
    assert breakdown.total >= 85.0


def test_score_all_min_clamped_at_zero():
    # All-negative contributions push below 0 -> clamped to 0.
    breakdown = score(_results(-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0))
    assert breakdown.total == 0.0


def test_score_clamped_at_hundred():
    breakdown = score(_results(2.0, 2.0, 2.0, 2.0, 0.0, 0.0, 2.0))
    assert breakdown.total == 100.0


def test_score_per_signal_breakdown_has_every_signal():
    breakdown: ScoreBreakdown = score(_results(0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.1))
    names = [name for name, _ in breakdown.per_signal]
    assert names == list(SIGNAL_WEIGHTS.keys())
    # weighted points should be contribution * weight.
    expected = [0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.1]
    for (name, pts), contrib in zip(breakdown.per_signal, expected, strict=False):
        assert abs(pts - round(contrib * SIGNAL_WEIGHTS[name], 4)) < 1e-6


def test_score_unknown_signal_raises():
    bad = [SignalResult(name="bogus", raw=1.0, contribution=0.5)]
    import pytest

    with pytest.raises(ValueError):
        score(bad)
