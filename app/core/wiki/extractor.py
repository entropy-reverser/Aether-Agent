"""app.core.wiki.extractor — turn conversation turns into permanent Facts.

Two strategies:
  - ``extract_from_turns``: deterministic rule-based extraction (default).
    Runs offline, no LLM. Catches high-precision patterns: "my name is X",
    "I prefer X", "remember that ...", "the project uses X".
  - ``LLMFactExtractor``: pluggable LLM-based extraction (reserved hook).
    Lazy-imports the model caller; if unavailable, falls back to rules.

Design notes
------------
- Deterministic first: tests run without network/LLM. The LLM hook is a
  drop-in that returns the same list[Fact] shape.
- Every extracted Fact gets source="extracted" and a confidence score so the
  caller can filter low-certainty facts.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.wiki.models import Fact

if TYPE_CHECKING:
    from collections.abc import Iterable


# High-precision bilingual patterns. Each: (regex, subject, predicate).
# WHY: precision over recall — wrong facts pollute memory worse than missed ones.
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(?:my name is|i am|i'm) ([A-Z][a-z]+)", re.IGNORECASE), "user", "name"),
    (re.compile(r"(?:my name is|我叫|我是) (\S+)", re.IGNORECASE), "user", "name"),
    (re.compile(r"i (?:prefer|like|love) (.+?)(?:[.!?,]|$)", re.IGNORECASE), "user", "prefers"),
    (re.compile(r"i (?:use|work with|develop in) (.+?)(?:[.!?,]|$)", re.IGNORECASE), "user", "uses"),
    (re.compile(r"remember (?:that )?(.+?)(?:[.!?,]|$)", re.IGNORECASE), "user", "fact"),
    (re.compile(r"(?:the )?project uses (.+?)(?:[.!?,]|$)", re.IGNORECASE), "project", "uses"),
    (re.compile(r"(?:the )?project is (?:a |an )?(.+?)(?:[.!?,]|$)", re.IGNORECASE), "project", "is"),
]


def extract_from_turns(turns: "Iterable[str]", confidence: float = 0.7) -> list[Fact]:
    """Extract facts from conversation turns using deterministic rules.

    Args:
        turns: Iterable of user message strings.
        confidence: Confidence to assign to rule-extracted facts.

    Returns:
        Deduplicated list of Facts (by id).
    """
    facts: dict[str, Fact] = {}
    for turn in turns:
        for pattern, subject, predicate in _PATTERNS:
            for match in pattern.finditer(turn):
                value = match.group(1).strip()
                if not value or len(value) > 200:
                    continue
                fact = Fact(
                    subject=subject,
                    predicate=predicate,
                    object=value,
                    source="extracted",
                    confidence=confidence,
                )
                facts[fact.id] = fact  # dedup by content hash
    return list(facts.values())


class LLMFactExtractor:
    """Pluggable LLM-based fact extractor (reserved hook).

    When wired (Stage 3), this calls the model caller to extract richer facts
    than regex can. Until then it raises on construction so callers know it
    is not yet available, and ``extract_from_turns`` remains the default.
    """

    def __init__(self, model_caller: object | None = None) -> None:
        raise NotImplementedError(
            "LLMFactExtractor is reserved for Stage 3 (LangGraph). "
            "Use extract_from_turns() for deterministic extraction."
        )
