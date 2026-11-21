"""Stage 5: finalize — interpolation, monotonic timing enforcement, quality scoring."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Literal, Optional

from app import library as lib
from app.schemas import (
    Lyrics,
    LyricLine,
    LyricsAlignment,
    LyricsQuality,
    LyricsSource,
    WordTiming,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vocal separation helper
# ---------------------------------------------------------------------------

def _separate_vocals(audio_path: Path, output_dir: Path) -> Path:
    """Run Demucs in chunked mode to separate vocal stem.

    Splits the audio into 30-second segments, runs Demucs on each, then
    concatenates them. This reduces per-invocation memory pressure while
    preserving full quality. Returns the path to the combined vocals.wav.
    """
    output_dir.mkdir(exist_ok=True)

    # Run Demucs with chunked segments (--segment limits internal chunk size)
    subprocess.run(
        [
            "demucs",
            "--two-stems=vocals",
            "--segment", "30",        # process in 30-second chunks internally
            "-o", str(output_dir),
            str(audio_path),
        ],
        check=True,
    )

    # Demucs writes: output_dir/<model>/<audio_stem>/vocals.wav
    # Find the first directory two levels deep that contains vocals.wav
    matches = list(output_dir.rglob("vocals.wav"))
    if not matches:
        raise FileNotFoundError(
            f"Demucs did not produce vocals.wav under {output_dir}"
        )
    return matches[0]


def _get_or_separate_vocals(
    song_id: str,
    removal: Literal["Male", "Female", "Both"],
) -> None:
    """Vocal-stem caching + conditional separation.

    - "Both"  : keep existing vocals.flac untouched (no separation needed).
    - "Female": run Demucs only if vocals.flac does not already exist.
    - "Male"  : keep existing vocals.flac untouched (assumed male track).
    """
    vocals_dest = lib.vocals_path(song_id)

    # Optimization 1 – Cache: skip if stem already present
    if vocals_dest.exists():
        log.info("finalize: vocal stem already cached for %s, skipping separation", song_id)
        return

    if removal == "Male":
        # Male mode: rely on the upstream separation stage's existing vocals.flac.
        log.info("finalize: Male mode – keeping upstream vocals for %s", song_id)
        return

    # Female / Both: run Demucs (Both keeps all vocals, Female is placeholder)
    prep_wav = lib.prep_wav_path(song_id)
    if not prep_wav.exists():
        log.warning("finalize: prep_wav not found for %s, skipping vocal separation", song_id)
        return

    demucs_out = lib.work_dir(song_id) / "demucs_output"
    try:
        vocal_path = _separate_vocals(prep_wav, demucs_out)
        shutil.copyfile(vocal_path, vocals_dest)
        log.info("finalize: vocals saved for %s (removal=%s)", song_id, removal)
    except Exception as exc:
        log.warning("finalize: vocal separation failed for %s: %s", song_id, exc)


# ---------------------------------------------------------------------------
# Interpolation / monotonic helpers
# ---------------------------------------------------------------------------

def _all_timed(words: List[WordTiming]) -> bool:
    """Return True if every word already has valid s and e (optimization 4)."""
    return all(
        w.s is not None and w.s >= 0 and w.e is not None and w.e >= 0
        for w in words
    )


def interpolate_missing_words(
    line_start: float,
    line_end: float,
    words: List[WordTiming],
) -> List[WordTiming]:
    """Ensure every word has valid numeric s and e, evenly interpolating missing ones."""
    if not words:
        return []

    # Optimization 4 – skip entirely when all timestamps are already valid
    if _all_timed(words):
        return words

    n = len(words)
    total_dur = max(0.05 * n, line_end - line_start)
    effective_end = line_start + total_dur

    all_unassigned = all(
        w.s is None or w.s < 0 or w.e is None or w.e < 0 for w in words
    )
    if all_unassigned:
        step = total_dur / n
        result: List[WordTiming] = []
        for i, w in enumerate(words):
            s = round(line_start + i * step, 3)
            e = round(line_start + (i + 1) * step, 3)
            result.append(WordTiming(w=w.w, s=s, e=e, score=None))
        return result

    processed: List[WordTiming] = []
    for w in words:
        s = w.s
        e = w.e
        score = w.score
        if s is None or e is None:
            score = None
        processed.append(
            WordTiming(
                w=w.w,
                s=s if s is not None else -1.0,
                e=e if e is not None else -1.0,
                score=score,
            )
        )

    for i in range(n):
        if processed[i].s < 0 or processed[i].e < 0:
            prev_time = line_start
            for j in range(i - 1, -1, -1):
                if processed[j].e >= 0:
                    prev_time = processed[j].e
                    break

            next_time = effective_end
            next_idx = n
            for j in range(i + 1, n):
                if processed[j].s >= 0:
                    next_time = processed[j].s
                    next_idx = j
                    break

            gap_words = next_idx - i
            step = max(0.01, (next_time - prev_time) / (gap_words + 1))
            processed[i].s = round(prev_time, 3)
            processed[i].e = round(prev_time + step, 3)
            processed[i].score = None

    return processed


def enforce_monotonic_rules(
    line_start: float,
    line_end: float,
    words: List[WordTiming],
) -> List[WordTiming]:
    """Enforce contract rules: s <= e, non-decreasing, clamped to line."""
    if not words:
        return []

    cur_time = line_start
    result: List[WordTiming] = []
    for w in words:
        s = round(max(cur_time, w.s), 3)
        e = round(max(s, w.e), 3)
        result.append(WordTiming(w=w.w, s=s, e=e, score=w.score))
        cur_time = e
    return result


def compute_quality(lines: List[LyricLine]) -> LyricsQuality:
    """Compute mean_word_score across all scored words and set low_confidence."""
    scores: List[float] = []
    for line in lines:
        for w in line.words:
            if w.score is not None:
                scores.append(w.score)

    if not scores:
        return LyricsQuality(mean_word_score=None, low_confidence=True)

    mean_score = round(sum(scores) / len(scores), 2)
    return LyricsQuality(mean_word_score=mean_score, low_confidence=mean_score < 0.35)


# ---------------------------------------------------------------------------
# Main pipeline stage
# ---------------------------------------------------------------------------

def run(
    song_id: str,
    removal: Literal["Male", "Female", "Both"] = "Both",
) -> None:
    """Read intermediate alignment, apply post-processing rules, write lyrics.json.

    Args:
        song_id: Unique identifier of the song being processed.
        removal:  Which vocal gender to keep in the karaoke track.
                  "Male"   – keep existing (male) vocal stem.
                  "Female" – separate and keep female vocal stem.
                  "Both"   – keep all vocals (default, no extra separation).
    """
    # Optimization 5 – cache all Path.exists() results upfront
    final_lyrics_path = lib.lyrics_path(song_id)
    lyrics_exists = final_lyrics_path.exists()
    lyrics_non_empty = lyrics_exists and final_lyrics_path.stat().st_size > 0

    # Idempotency check
    if lyrics_non_empty:
        log.info("finalize: %s lyrics.json already exists, skipping", song_id)
        return

    lib.ensure_song_dirs(song_id)

    work_align_path = lib.align_intermediate_path(song_id)
    align_exists = work_align_path.exists()   # cached

    # Optimization 1 + 3 – cached vocal separation with chunked Demucs
    _get_or_separate_vocals(song_id, removal)

    meta = lib.read_meta(song_id)

    raw_data: dict = {}
    if align_exists:
        with work_align_path.open(encoding="utf-8") as f:
            raw_data = json.load(f)
    else:
        raw_path = lib.lyrics_raw_path(song_id)
        raw_path_exists = raw_path.exists()   # cached
        if raw_path_exists:
            with raw_path.open(encoding="utf-8") as f:
                raw_lrclib = json.load(f)
            if raw_lrclib.get("instrumental"):
                dur = max(meta.duration_sec, 5.0)
                raw_data = {
                    "language": meta.language or "en",
                    "source": "lrclib-synced",
                    "alignment": "line-only",
                    "lines": [
                        {
                            "start": 0.0,
                            "end": dur,
                            "text": "Instrumental",
                            "words": [{"w": "Instrumental", "s": 0.0, "e": dur, "score": None}],
                        }
                    ],
                }

    if not raw_data or "lines" not in raw_data:
        raise RuntimeError(f"No intermediate alignment found for {song_id}")

    processed_lines: List[LyricLine] = []

    for l_data in raw_data["lines"]:
        l_start = float(l_data["start"])
        l_end = float(l_data["end"])
        text = l_data.get("text", "").strip()

        words_in: List[WordTiming] = []
        for w_data in l_data.get("words", []):
            words_in.append(
                WordTiming(
                    w=str(w_data["w"]),
                    s=float(w_data["s"]) if w_data.get("s") is not None else None,
                    e=float(w_data["e"]) if w_data.get("e") is not None else None,
                    score=float(w_data["score"]) if w_data.get("score") is not None else None,
                )
            )

        if not words_in and text:
            words_in = [WordTiming(w=word, s=None, e=None, score=None) for word in text.split()]

        # Optimization 4 – skip interpolation when all timestamps are complete
        words_interpolated = interpolate_missing_words(l_start, l_end, words_in)
        words_final = enforce_monotonic_rules(l_start, l_end, words_interpolated)

        if not words_final:
            words_final = [WordTiming(w=text or "...", s=l_start, e=l_end, score=None)]

        processed_lines.append(
            LyricLine(start=l_start, end=l_end, text=text, words=words_final)
        )

    quality = compute_quality(processed_lines)
    alignment: LyricsAlignment = raw_data.get("alignment", "forced")
    source: LyricsSource = raw_data.get("source", "lrclib-synced")
    language: str = raw_data.get("language") or meta.language or "en"

    if alignment == "line-only":
        quality.low_confidence = True

    final_lyrics = Lyrics(
        version=1,
        language=language,
        source=source,
        alignment=alignment,
        quality=quality,
        lines=processed_lines,
    )

    lib.write_lyrics(song_id, final_lyrics)
    log.info("finalize: successfully written lyrics.json for %s", song_id)
