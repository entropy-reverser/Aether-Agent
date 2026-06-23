"""Tests for app.core.routing.feedback — adaptive thumb feedback."""

from __future__ import annotations

from app.core.routing.feedback import FeedbackStore, message_signature


def test_message_signature_stable_for_same_tokens():
    a = message_signature("how do I build a rate limiter")
    b = message_signature("how do I build a rate limiter")
    assert a == b


def test_message_signature_order_invariant():
    # Bag of words: word order must not change the signature.
    a = message_signature("build a rate limiter in redis")
    b = message_signature("in redis build a rate limiter")
    assert a == b


def test_message_signature_differs_for_different_content():
    a = message_signature("translate this to english")
    b = message_signature("summarize the meeting notes")
    assert a != b


def test_record_thumbs_down_lowers_score():
    store = FeedbackStore()
    msg = "translate this sentence please"
    # No feedback yet -> no adjustment.
    assert store.adjust_for(msg, None, 60.0) == 60.0
    store.record(msg, None, positive=False)
    adjusted = store.adjust_for(msg, None, 60.0)
    assert adjusted < 60.0


def test_record_thumbs_up_raises_score():
    store = FeedbackStore()
    msg = "hello there friend"
    store.record(msg, None, positive=True)
    adjusted = store.adjust_for(msg, None, 30.0)
    assert adjusted > 30.0


def test_adjustment_clamped_to_max():
    store = FeedbackStore()
    msg = "the same message repeated"
    # Record many thumbs-downs; adjustment must saturate at -15.
    for _ in range(20):
        store.record(msg, None, positive=False)
    assert store.get_adjustment(msg) == -15.0
    # A score of 50 + (-15) = 35.
    assert store.adjust_for(msg, None, 50.0) == 35.0


def test_adjustment_clamps_score_to_zero():
    store = FeedbackStore()
    msg = "very low score message"
    for _ in range(20):
        store.record(msg, None, positive=False)
    # 10 - 15 = -5 -> clamped to 0.
    assert store.adjust_for(msg, None, 10.0) == 0.0


def test_feedback_persists_to_file(tmp_path):
    path = tmp_path / "feedback.json"
    store = FeedbackStore(persist_path=path)
    store.record("remember me please", None, positive=False)
    # New store loading from the same file sees the recorded adjustment.
    store2 = FeedbackStore(persist_path=path)
    assert store2.get_adjustment("remember me please") < 0.0
