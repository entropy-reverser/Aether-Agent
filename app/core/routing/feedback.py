"""app.core.routing.feedback — adaptive thumb-feedback store.

Learns a per-message-signature adjustment: when a user gives thumbs-down on a
decision, future similar messages get their score nudged; thumbs-up nudges
the other way (or just reinforces). The signature is a lightweight content
fingerprint, so "similar" means "structurally similar", not "identical text".

Design notes
------------
- No Redis dependency: an in-process dict with optional JSON persistence.
  The MVP is single-process; multi-process sharding comes at Stage 6.
- The signature hashes the *sorted token multiset* (bag of words), so word
  order and small edits don't change the fingerprint. This is deliberately
  coarse — it groups paraphrases of the same intent.
- Adjustment magnitude is bounded so feedback can refine but never hijack
  routing: at most ±15 points per signature, decaying toward 0 as feedback
  balances out.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from app.utils.logger import logger

# Maximum |adjustment| a single signature can apply (points on the 0-100 score).
_MAX_ADJUSTMENT = 15.0
# Each thumbs-down shifts the score by this many points (negative = toward cheaper).
_STEP = 3.0


def message_signature(message: str) -> str:
    """Compute a coarse content fingerprint for ``message``.

    Uses the sorted lowercased token multiset (bag of words), so order and
    minor edits don't affect the signature. Returns a hex digest.

    Args:
        message: Raw user message.

    Returns:
        A stable hex string signature.
    """
    tokens = sorted(message.lower().split())
    bag = Counter(tokens)
    payload = " ".join(f"{w}:{c}" for w, c in sorted(bag.items()))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class FeedbackStore:
    """In-process adaptive feedback store keyed by message signature.

    Args:
        persist_path: Optional path to a JSON file for durability across
            restarts. If None, feedback is memory-only (lost on restart).
    """

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else None
        # signature -> signed accumulation (positive = was too cheap, nudge up;
        # negative = was too expensive, nudge down toward PARSE/CHAT).
        self._adjustments: dict[str, float] = {}
        self._load()

    def record(self, message: str, user_id: str | None, positive: bool) -> None:
        """Record a thumbs-up/down for a message's signature.

        Args:
            message: The message whose routing the user is rating.
            user_id: Optional user id (currently unused for per-user splits;
                reserved for future per-user feedback).
            positive: True for thumbs-up (was right), False for thumbs-down.
        """
        sig = message_signature(message)
        # Thumbs-down: nudge score DOWN (the chosen tier was too strong/pricey).
        # Thumbs-up: nudge score UP slightly to reinforce, but gently.
        delta = -_STEP if not positive else _STEP * 0.5
        current = self._adjustments.get(sig, 0.0)
        # Clamp so no signature accumulates an outsized adjustment.
        self._adjustments[sig] = max(-_MAX_ADJUSTMENT, min(_MAX_ADJUSTMENT, current + delta))
        logger.debug(
            "feedback recorded sig={} positive={} -> adjustment={:.1f}",
            sig,
            positive,
            self._adjustments[sig],
        )
        self._save()

    def adjust_for(self, message: str, user_id: str | None, score_value: float) -> float:
        """Apply the learned adjustment for a message signature to a score.

        Args:
            message: The incoming message.
            user_id: Optional user id.
            score_value: The pre-feedback score in [0, 100].

        Returns:
            The adjusted score, clamped to [0, 100].
        """
        sig = message_signature(message)
        adj = self._adjustments.get(sig, 0.0)
        if adj == 0.0:
            return score_value
        adjusted = max(0.0, min(100.0, score_value + adj))
        return round(adjusted, 2)

    def get_adjustment(self, message: str) -> float:
        """Inspect the current learned adjustment for a signature (for tests)."""
        return self._adjustments.get(message_signature(message), 0.0)

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._adjustments = {k: float(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("feedback store load failed (resetting): {}", exc)
            self._adjustments = {}

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps(self._adjustments), encoding="utf-8")
        except OSError as exc:
            logger.warning("feedback store save failed: {}", exc)
