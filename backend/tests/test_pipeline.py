"""Unit tests for pipeline components: LRC parser, title matcher, interpolation, monotonic rules."""
from __future__ import annotations

import pytest

from app.pipeline.lrclib import matches_title, normalize_title, parse_lrc
from app.pipeline.finalize import compute_quality, enforce_monotonic_rules, interpolate_missing_words
from app.schemas import LyricLine, WordTiming


# ---------------------------------------------------------------------------
# LRC Parser Tests
# ---------------------------------------------------------------------------

def test_lrc_parser_standard():
    lrc = """
    [ti:Test Track]
    [ar:Artist]
    [00:01.00]First line
    [00:04.50]Second line
    """
    lines = parse_lrc(lrc)
    assert len(lines) == 2
    assert lines[0].timestamp_sec == 1.0
    assert lines[0].text == "First line"
    assert lines[1].timestamp_sec == 4.5
    assert lines[1].text == "Second line"


def test_lrc_parser_multi_timestamp():
    lrc = "[00:02.00][00:06.00]Repeated chorus line"
    lines = parse_lrc(lrc)
    assert len(lines) == 2
    assert lines[0].timestamp_sec == 2.0
    assert lines[1].timestamp_sec == 6.0
    assert lines[0].text == "Repeated chorus line"
    assert lines[1].text == "Repeated chorus line"


def test_lrc_parser_offset():
    # [offset:+500] shifts 500ms forward
    lrc = """
    [offset:+500]
    [00:01.00]Shifted line
    """
    lines = parse_lrc(lrc)
    assert len(lines) == 1
    assert lines[0].timestamp_sec == 1.5


# ---------------------------------------------------------------------------
# Title Matcher Tests
# ---------------------------------------------------------------------------

def test_title_matching_exact():
    assert matches_title("Bohemian Rhapsody", "Bohemian Rhapsody")


def test_title_matching_bracketed_and_case():
    assert matches_title("Bohemian Rhapsody (Official Video)", "bohemian rhapsody")
    assert matches_title("Yesterday [Remastered 2009]", "Yesterday")
    assert matches_title("Let It Be", "Let It Be (2021 Mix)")


def test_title_matching_mismatch():
    assert not matches_title("Bohemian Rhapsody", "We Will Rock You")


# ---------------------------------------------------------------------------
# Interpolation & Monotonic Rules Tests
# ---------------------------------------------------------------------------

def test_interpolate_all_missing():
    raw_words = [
        WordTiming(w="Hello", s=-1.0, e=-1.0),
        WordTiming(w="World", s=-1.0, e=-1.0),
    ]
    interp = interpolate_missing_words(10.0, 14.0, raw_words)
    assert len(interp) == 2
    assert interp[0].s == 10.0
    assert interp[0].e == 12.0
    assert interp[1].s == 12.0
    assert interp[1].e == 14.0


def test_enforce_monotonic_rules():
    words = [
        WordTiming(w="one", s=5.0, e=4.0),     # s > e
        WordTiming(w="two", s=3.0, e=6.0),     # s < previous
    ]
    corrected = enforce_monotonic_rules(0.0, 10.0, words)
    assert corrected[0].s <= corrected[0].e
    assert corrected[1].s >= corrected[0].e


def test_compute_quality():
    lines = [
        LyricLine(
            start=0.0, end=2.0, text="hi",
            words=[WordTiming(w="hi", s=0.0, e=2.0, score=0.85)],
        )
    ]
    q = compute_quality(lines)
    assert q.mean_word_score == 0.85
    assert q.low_confidence is False

    lines_low = [
        LyricLine(
            start=0.0, end=2.0, text="hi",
            words=[WordTiming(w="hi", s=0.0, e=2.0, score=0.20)],
        )
    ]
    q_low = compute_quality(lines_low)
    assert q_low.mean_word_score == 0.20
    assert q_low.low_confidence is True
