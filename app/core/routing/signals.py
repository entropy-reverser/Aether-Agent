"""app.core.routing.signals — deterministic complexity-signal extractors.

Each extractor inspects one facet of a message and returns its
**complexity contribution** in [0.0, 1.0], where higher means "this message
looks more complex / should use a stronger model". ``extract_all`` runs every
extractor and returns the full set for the scorer.

Design notes
------------
- Pure functions: no I/O, no globals, no LLM calls. Deterministic given input.
- A "contribution" of 0.0 means "no evidence of complexity", NOT "evidence of
  simplicity". Some signals (command, conversation) instead return a
  *negative* contribution to actively push the score down toward PARSE/CHAT.
- Keyword lists are tuned for a bilingual (EN/ZH) user base. Keep them short
  and high-precision; false positives are worse than missed signals.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

# --- Keyword vocabularies (kept module-level for easy tuning + testing) ---

_CODE_KEYWORDS = (
    "def ",
    "class ",
    "import ",
    "return ",
    "async ",
    "await ",
    "function",
    "const ",
    "let ",
    "var ",
    "SELECT ",
    "FROM ",
    "WHERE ",
    "println!",
    "print(",
    "console.log",
    "fmt.",
    "docker",
    "kubernetes",
    "git ",
    "python",
    "javascript",
    "typescript",
    "rust",
    "golang",
    "algorithm",
    "api ",
    "endpoint",
    "database",
    "server",
    "implement",
    "interface",
    "abstract",
    "inheritance",
)
_QUESTION_WORDS = (
    "?",
    "怎么",
    "如何",
    "为什么",
    "怎么办",
    "吗？",
    "吗?",
    "why",
    "how",
    "what",
    "when",
    "where",
    "which",
    "who",
    "explain",
    "could you",
    "can you",
    "please",
    "is it",
    "are there",
    "what's",
)
_COMPLEXITY_WORDS = (
    "分析",
    "对比",
    "权衡",
    "权衡利弊",
    "总结",
    "梳理",
    "设计",
    "重构",
    "架构",
    "步进",
    "分步骤",
    "推理",
    "证明",
    "优化",
    "analyze",
    "compare",
    "trade-off",
    "tradeoff",
    "summarize",
    "design",
    "refactor",
    "architect",
    "step-by-step",
    "step by step",
    "reason",
    "optimize",
    "evaluate",
    "diagnose",
)
_COMMAND_WORDS = (
    "翻译",
    "提取",
    "解析",
    "转成",
    "转码",
    "格式化",
    "命名",
    "translate",
    "extract",
    "parse",
    "convert",
    "format",
    "rename",
    "summarize this",
)
_CONVERSATION_WORDS = (
    "你好",
    "嗨",
    "早上好",
    "晚上好",
    "谢谢",
    "辛苦",
    "再见",
    "拜拜",
    "hello",
    "hi",
    "hey",
    "thanks",
    "thank you",
    "morning",
    "bye",
)
_LISTING_MARKERS = ("1.", "2.", "3.", "- ", "* ", "•", "、", "；", "; ", " and ", " or ", "，以及")


@dataclass(frozen=True)
class SignalResult:
    """Outcome of one signal extractor.

    Attributes:
        name: Signal identifier (e.g. "length", "code").
        raw: The raw measured value (e.g. character count). For auditing.
        contribution: Complexity contribution in [-1.0, 1.0]. Positive pushes
            toward COMPLEX; negative pushes toward PARSE/CHAT; 0 is neutral.
        note: Optional short human-readable explanation for the audit trail.
    """

    name: str
    raw: float
    contribution: float
    note: str = ""


# --- Individual extractors -------------------------------------------------


def length_signal(message: str) -> SignalResult:
    """Complexity from message length.

    Short messages tend to be simple (PARSE-tier); long ones need more model
    (COMPLEX-tier). Uses a piecewise curve:
      - Below 30 chars: contribution is negative (pulls toward PARSE).
      - Above 30 chars: standard saturating curve toward +1.

    Args:
        message: Raw user message.

    Returns:
        SignalResult with raw=char count, contribution in [-0.5, 1].
    """
    n = len(message)
    if n < 30:
        # WHY: very short messages (commands, greetings) should lean toward PARSE.
        contrib = -0.5 + (n / 30.0) * 0.5  # -0.5 at 0 chars, 0.0 at 30 chars.
    else:
        # Saturating curve: contribution ~ n / (n + k). k=350 tuned so ~200 chars -> 0.36.
        k = 350.0
        contrib = n / (n + k)
    return SignalResult("length", float(n), round(contrib, 3), f"{n} chars")


def _count_matches(message: str, needles: tuple[str, ...]) -> int:
    """Count case-insensitive substring matches for any of ``needles``."""
    low = message.lower()
    return sum(1 for kw in needles if kw.lower() in low)


def code_signal(message: str) -> SignalResult:
    """Complexity from code-like structure and keywords.

    Detects fenced code blocks, heavy indentation, and code keywords.

    Returns:
        SignalResult; high contribution when code is present.
    """
    raw = 0
    # Fenced code blocks ```...``` or indented blocks (4+ leading spaces on a line).
    if "```" in message:
        raw += 2
    raw += len(re.findall(r"^\s{4,}\S", message, flags=re.MULTILINE))
    raw += _count_matches(message, _CODE_KEYWORDS)
    # Code usually needs a capable model; cap contribution at 1.0.
    contrib = min(1.0, raw * 0.4)
    return SignalResult("code", float(raw), round(contrib, 3), f"{raw} code markers")


def question_signal(message: str) -> SignalResult:
    """Complexity from question markers.

    A genuine question usually needs an explanation (CHAT-ish at least).

    Returns:
        SignalResult with contribution based on question-word density.
    """
    raw = _count_matches(message, _QUESTION_WORDS)
    contrib = min(0.6, raw * 0.3)  # questions help but don't dominate
    return SignalResult("question", float(raw), round(contrib, 3), f"{raw} question markers")


def complexity_signal(message: str) -> SignalResult:
    """Complexity from reasoning / analysis keywords.

    Words like "analyze", "compare", "design" are strong signals that the
    user wants multi-step reasoning — a COMPLEX-tier task.

    Returns:
        SignalResult with high contribution when reasoning words appear.
    """
    raw = _count_matches(message, _COMPLEXITY_WORDS)
    contrib = min(1.0, raw * 0.35)
    return SignalResult("complexity", float(raw), round(contrib, 3), f"{raw} reasoning markers")


def command_signal(message: str) -> SignalResult:
    """Inverse signal: short imperative commands lean toward PARSE.

    Detects command verbs ("translate", "extract", "parse") and, when the
    message is short, returns a *negative* contribution to push the score
    down toward the cheap local tier.

    Returns:
        SignalResult with contribution in [-1.0, 0] when a command is matched.
    """
    raw = _count_matches(message, _COMMAND_WORDS)
    if raw == 0:
        return SignalResult("command", 0.0, 0.0, "no command verbs")
    # Short command -> strong PARSE lean; long message with command verb stays neutral.
    # WHY: a terse imperative ("translate this") is a textbook PARSE-tier task, so the
    # negative contribution must be strong enough to pull the base score below PARSE_MAX.
    contrib = -min(1.0, 0.7 * raw) if len(message) <= 200 else 0.0
    return SignalResult("command", float(raw), round(contrib, 3), f"{raw} command verbs")


def conversation_signal(message: str) -> SignalResult:
    """Inverse signal: casual chat leans toward CHAT (not COMPLEX).

    Detects greetings/thanks/farewells and emoji density. Returns a negative
    contribution to pull the score down — chat doesn't need a strong model.

    Returns:
        SignalResult with contribution in [-0.5, 0] for casual messages.
    """
    raw = _count_matches(message, _CONVERSATION_WORDS)
    # Emoji heuristic: count non-ASCII, non-CJK punctuation/symbol glyphs.
    emoji_like = sum(1 for ch in message if ord(ch) > 0x2000 and ch not in string.printable)
    raw += min(3, emoji_like)
    if raw == 0:
        return SignalResult("conversation", 0.0, 0.0, "no chat markers")
    contrib = -min(0.5, 0.2 * raw)
    # Suppress the lean if there's also heavy complexity content.
    if _count_matches(message, _COMPLEXITY_WORDS) > 0:
        contrib = 0.0
    return SignalResult("conversation", float(raw), round(contrib, 3), f"{raw} chat markers")


def multi_topic_signal(message: str) -> SignalResult:
    """Complexity from multi-topic / multi-sentence structure.

    Many list markers or multiple sentences suggest the user wants several
    things handled — typically a COMPLEX-tier task.

    Returns:
        SignalResult with contribution scaling with structural density.
    """
    # Sentence count via terminal punctuation (EN + ZH).
    sentences = len(re.findall(r"[.!?。！？]", message))
    list_markers = sum(1 for m in _LISTING_MARKERS if m in message)
    raw = sentences + list_markers
    contrib = min(0.8, raw * 0.15)
    return SignalResult("multi_topic", float(raw), round(contrib, 3), f"{raw} structural markers")


# Ordered list of all extractors. The scorer walks this in order.
SIGNALS: tuple[SignalResultExtractor, ...] = (
    length_signal,
    code_signal,
    question_signal,
    complexity_signal,
    command_signal,
    conversation_signal,
    multi_topic_signal,
)


def extract_all(message: str) -> list[SignalResult]:
    """Run every signal extractor against ``message``.

    Args:
        message: Raw user message. Must be non-empty.

    Returns:
        List of SignalResult, one per extractor, in SIGNALS order.

    Raises:
        ValueError: If ``message`` is empty or whitespace-only.
    """
    if not message or not message.strip():
        raise ValueError("message must be non-empty")
    return [fn(message) for fn in SIGNALS]
