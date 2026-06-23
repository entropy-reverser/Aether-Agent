"""Tests for app.core.routing.tiers — tier enum + score mapping."""

from __future__ import annotations

import pytest

from app.core.routing.tiers import MODEL_MAP, TIER_LABELS, Tier, tier_for_score


def test_tier_cost_ordering_ascending():
    assert Tier.PARSE < Tier.CHAT < Tier.COMPLEX


def test_tier_for_score_parse_boundary():
    assert tier_for_score(0) is Tier.PARSE
    assert tier_for_score(25, parse_max=25, chat_max=55) is Tier.PARSE


def test_tier_for_score_chat_middle():
    assert tier_for_score(40, parse_max=25, chat_max=55) is Tier.CHAT
    assert tier_for_score(55, parse_max=25, chat_max=55) is Tier.CHAT


def test_tier_for_score_complex_high():
    assert tier_for_score(56, parse_max=25, chat_max=55) is Tier.COMPLEX
    assert tier_for_score(100, parse_max=25, chat_max=55) is Tier.COMPLEX


def test_tier_for_score_uses_defaults_when_none():
    # Defaults come from settings: parse_max=25, chat_max=55.
    assert tier_for_score(10) is Tier.PARSE
    assert tier_for_score(100) is Tier.COMPLEX


def test_tier_for_score_rejects_out_of_range():
    with pytest.raises(ValueError):
        tier_for_score(-1)
    with pytest.raises(ValueError):
        tier_for_score(101)


def test_model_map_has_entry_for_every_tier():
    for tier in Tier:
        assert tier in MODEL_MAP
        assert MODEL_MAP[tier]  # non-empty


def test_tier_labels_cover_every_tier():
    assert set(TIER_LABELS) == set(Tier)
