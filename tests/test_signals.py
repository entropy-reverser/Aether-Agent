"""Tests for app.core.routing.signals.

Covers each of the 7 deterministic extractors, including the inverse
(command / conversation) signals, plus the extract_all entry point.
All offline, deterministic.
"""

from __future__ import annotations

import pytest

from app.core.routing import signals

# --- extract_all ----------------------------------------------------------


def test_extract_all_empty_message_raises():
    with pytest.raises(ValueError):
        signals.extract_all("")


def test_extract_all_whitespace_only_raises():
    with pytest.raises(ValueError):
        signals.extract_all("   \n\t  ")


def test_extract_all_returns_one_result_per_signal():
    results = signals.extract_all("hello world")
    assert len(results) == len(signals.SIGNALS)
    names_from_funcs = [fn.__name__.replace("_signal", "") for fn in signals.SIGNALS]
    assert [r.name for r in results] == names_from_funcs


# --- length_signal --------------------------------------------------------


def test_length_signal_empty_is_negative_contribution():
    # WHY: empty/very short messages lean toward PARSE, hence negative.
    res = signals.length_signal("")
    assert res.contribution == -0.5


def test_length_signal_short_message_negative():
    res = signals.length_signal("hi")
    assert res.contribution < 0.0


def test_length_signal_30_chars_nonnegative():
    # Crossover point: messages >= 30 chars use the positive saturating branch.
    res = signals.length_signal("x" * 30)
    assert res.contribution >= 0.0


def test_length_signal_long_message_saturates_high():
    res = signals.length_signal("word " * 400)
    assert res.contribution > 0.8
    assert res.raw == 2000


def test_length_signal_monotonic_non_decreasing():
    short = signals.length_signal("hi")
    medium = signals.length_signal("a reasonable sentence with some length")
    assert medium.contribution >= short.contribution


# --- code_signal ----------------------------------------------------------


def test_code_signal_fenced_block_detected():
    msg = "Here is code:\n```python\ndef f(x):\n    return x\n```\n"
    res = signals.code_signal(msg)
    assert res.raw >= 1
    assert res.contribution > 0


def test_code_signal_keywords_detected():
    res = signals.code_signal("import os and def main and return None")
    assert res.raw >= 3
    assert res.contribution > 0.5


def test_code_signal_plain_text_zero_contribution():
    res = signals.code_signal("just a normal sentence about the weather")
    assert res.contribution == 0.0


# --- question_signal ------------------------------------------------------


def test_question_signal_english_question_word():
    res = signals.question_signal("how do I do that?")
    assert res.raw >= 1
    assert res.contribution > 0


def test_question_signal_chinese_question():
    res = signals.question_signal("怎么实现这个功能？")
    assert res.raw >= 1
    assert res.contribution > 0


def test_question_signal_statement_zero():
    res = signals.question_signal("the sky is blue today")
    assert res.contribution == 0.0


# --- complexity_signal ----------------------------------------------------


def test_complexity_signal_reasoning_words_high():
    res = signals.complexity_signal("please analyze and compare the two designs")
    assert res.raw >= 2
    assert res.contribution >= 0.5


def test_complexity_signal_capped_at_one():
    msg = "analyze compare design refactor architect evaluate optimize reason"
    res = signals.complexity_signal(msg)
    assert res.contribution <= 1.0


def test_complexity_signal_absent_is_zero():
    res = signals.complexity_signal("hello there")
    assert res.contribution == 0.0


# --- command_signal (inverse) --------------------------------------------


def test_command_signal_short_command_negative_contribution():
    res = signals.command_signal("translate this to english")
    assert res.contribution < 0, "short commands should lean toward PARSE (negative)"


def test_command_signal_long_command_neutral():
    res = signals.command_signal("translate this to english " + "word " * 60)
    assert res.contribution == 0.0


def test_command_signal_no_command_zero():
    res = signals.command_signal("tell me about the weather")
    assert res.contribution == 0.0


# --- conversation_signal (inverse) ---------------------------------------


def test_conversation_signal_greeting_negative():
    res = signals.conversation_signal("hi there! thanks!")
    assert res.contribution < 0, "chat should lean away from COMPLEX (negative)"


def test_conversation_signal_emoji_negative():
    res = signals.conversation_signal("hello 🎉🚀✨")
    assert res.contribution < 0


def test_conversation_signal_suppressed_when_complexity_present():
    # Greeting + reasoning word -> complexity wins, conversation suppressed.
    res = signals.conversation_signal("hi, please analyze this design")
    assert res.contribution == 0.0


# --- multi_topic_signal ---------------------------------------------------


def test_multi_topic_signal_many_sentences_high():
    res = signals.multi_topic_signal("Do A. Then do B! After that, C? Finally D.")
    assert res.raw >= 3
    assert res.contribution > 0


def test_multi_topic_signal_list_markers_counted():
    res = signals.multi_topic_signal("1. first\n2. second\n3. third")
    assert res.raw >= 3


def test_multi_topic_signal_single_sentence_low():
    res = signals.multi_topic_signal("hello there friend")
    assert res.contribution <= 0.15
