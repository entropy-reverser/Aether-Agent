"""app.core.routing.tiers — routing tier enum + model mapping.

Defines the three model tiers and the rules that map a 0-100 complexity
score onto a tier. This module is pure data + one small function: it has no
state, no I/O, and no dependencies beyond the stdlib, so it is trivially
unit-testable.

Design notes
------------
- Tiers are ordered cheapest -> most expensive (PARSE < CHAT < COMPLEX) so
  the enum's integer value doubles as a cost rank.
- ``tier_for_score`` is the single place where score thresholds are applied.
  Routing thresholds live in config (``routing_parse_max`` /
  ``routing_chat_max``) and are passed in explicitly so tests can vary them.
"""

from __future__ import annotations

from enum import IntEnum

from app.config import settings


class Tier(IntEnum):
    """Model tiers, ordered by cost/complexity (lowest first).

    Attributes:
        PARSE: cheap local model — extract/translate/parse, short commands.
        CHAT: fast model — everyday conversation.
        COMPLEX: strong model — reasoning, code, multi-step tasks.
    """

    PARSE = 1
    CHAT = 2
    COMPLEX = 3


# Default model name per tier. Overridden at runtime by app.config settings,
# which read ROUTER_MODEL_* from the environment.
MODEL_MAP: dict[Tier, str] = {
    Tier.PARSE: settings.router_model_parse,
    Tier.CHAT: settings.router_model_chat,
    Tier.COMPLEX: settings.router_model_complex,
}

# Human-readable label for audit output / API responses.
TIER_LABELS: dict[Tier, str] = {
    Tier.PARSE: "parse (local, cheap)",
    Tier.CHAT: "chat (fast)",
    Tier.COMPLEX: "complex (strong, costly)",
}


def tier_for_score(score: float, parse_max: int | None = None, chat_max: int | None = None) -> Tier:
    """Map a 0-100 complexity score onto a Tier.

    Thresholds (default 25 / 55, configurable via config):
        score <= parse_max        -> PARSE
        parse_max < score <= chat_max -> CHAT
        score > chat_max          -> COMPLEX

    Args:
        score: Complexity score in [0, 100].
        parse_max: Upper bound for PARSE (defaults to settings.routing_parse_max).
        chat_max: Upper bound for CHAT (defaults to settings.routing_chat_max).

    Returns:
        The Tier the score falls into.

    Raises:
        ValueError: If score is outside [0, 100].
    """
    if not 0 <= score <= 100:
        raise ValueError(f"score must be in [0, 100], got {score}")

    p_max = settings.routing_parse_max if parse_max is None else parse_max
    c_max = settings.routing_chat_max if chat_max is None else chat_max

    if score <= p_max:
        return Tier.PARSE
    if score <= c_max:
        return Tier.CHAT
    return Tier.COMPLEX


def model_for_tier(tier: Tier) -> str:
    """Return the configured model name for a tier."""
    return MODEL_MAP[tier]
