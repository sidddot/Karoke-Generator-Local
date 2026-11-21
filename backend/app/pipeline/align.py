"""Stage 4: forced alignment via WhisperX or line-only fallback."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, List, Optional

from app import library as lib
from app.config import DEVICE
from app.pipeline.lrclib import parse_lrc
from app.pipeline.transcribe import normalize_lang_code

log = logging.getLogger(__name__)


def _run_whisperx_alignment(
    vocals_16k: Path,
    segments: List[dict[str, Any]],
    lang_code: str,
    device: str,
) -> Optional[List[dict[str, Any]]]:
    """Execute WhisperX forced alignment on provided segments."""
    try:
        import whisperx
    except ImportError:
        log.warning("WhisperX not installed — using line-only timing")
        return None

    try:
        log.info("Loading align model for language '%s' on %s", lang_code, device)
        align_model, metadata = whisperx.load_align_model(
            language_code=lang_code,
            device=device,
        )
        audio = whisperx.load_audio(str(vocals_16k))
        aligned_result = whisperx.align(
            segments,
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        return aligned_result.get("segments", [])
    except Exception as exc:
        log.warning("WhisperX alignment failed or language '%s' unsupported: %s", lang_code, exc)
        return None


def run(song_id: str) -> None:
    """Run forced alignment on lyrics (LRCLIB or manual LRC). Fall back to transcribe if needed."""
    meta = lib.read_meta(song_id)
    duration = max(meta.duration_sec, 5.0)
    raw_path = lib.lyrics_raw_path(song_id)
    intermediate_path = lib.align_intermediate_path(song_id)
    vocals_16k = lib.vocals_16k_path(song_id)

    # 1. Inspect lyrics_raw.json
    raw_data: dict[str, Any] = {}
    if raw_path.exists():
        with raw_path.open(encoding="utf-8") as f:
            raw_data = json.load(f)

    # Check if song is instrumental
    if raw_data.get("instrumental"):
        log.info("align: song %s is instrumental, generating dummy instrumental line", song_id)
        intermediate = {
            "language": meta.language or "en",
            "source": "lrclib-synced",
            "alignment": "line-only",
            "lines": [
                {
                    "start": 0.0,
                    "end": duration,
                    "text": "Instrumental",
                    "words": [{"w": "Instrumental", "s": 0.0, "e": duration, "score": None}],
                }
            ],
        }
        _save_intermediate(song_id, intermediate)
        return

    # 2. Extract LRC text
    lrc_text: Optional[str] = None
    source = "lrclib-synced"

    if raw_data.get("_manual"):
        if raw_data.get("format") == "lrc":
            lrc_text = raw_data.get("text")
            source = "manual-lrc"
        else:
            # Plain manual text -> run transcription/alignment
            from app.pipeline import transcribe
            transcribe.run(song_id)
            return
    elif raw_data.get("syncedLyrics"):
        lrc_text = raw_data["syncedLyrics"]

    # If no synced lyrics, trigger transcribe fallback
    if not lrc_text or not lrc_text.strip():
        log.info("align: no synced lyrics available for %s — triggering transcribe fallback", song_id)
        from app.pipeline import transcribe
        transcribe.run(song_id)
        return

    # 3. Parse LRC
    parsed_lines = parse_lrc(lrc_text)
    if not parsed_lines:
        log.info("align: LRC parsing yielded 0 lines for %s — falling back to transcribe", song_id)
        from app.pipeline import transcribe
        transcribe.run(song_id)
        return

    # Optimization 3: If every LRC line already carries word-level timestamps
    # (enhanced LRC / word-synced format), skip WhisperX entirely and write
    # directly to the intermediate file — saving 10-20 min per song.
    def _has_word_timestamps(lines: list) -> bool:
        """Return True if every parsed line has word-level timing data."""
        return all(
            hasattr(line, "words") and line.words and len(line.words) > 0
            for line in lines
        )

    if _has_word_timestamps(parsed_lines):
        log.info(
            "align: LRC contains word-level timestamps for %s — skipping WhisperX", song_id
        )
        final_lines_direct: list[dict] = []
        for i, line in enumerate(parsed_lines):
            start = line.timestamp_sec
            end = (
                parsed_lines[i + 1].timestamp_sec
                if i + 1 < len(parsed_lines)
                else min(start + 8.0, duration)
            )
            end = max(start + 0.5, end)
            words = [
                {"w": w.text, "s": w.start_sec, "e": w.end_sec, "score": None}
                for w in line.words
            ]
            final_lines_direct.append(
                {"start": start, "end": end, "text": line.text, "words": words}
            )
        intermediate_direct = {
            "language": normalize_lang_code(meta.language) or "en",
            "source": source,
            "alignment": "forced",
            "lines": final_lines_direct,
        }
        _save_intermediate(song_id, intermediate_direct)
        return

    # 4. Build segments
    raw_segments: List[dict[str, Any]] = []
    for i, line in enumerate(parsed_lines):
        start = line.timestamp_sec
        if i + 1 < len(parsed_lines):
            end = parsed_lines[i + 1].timestamp_sec
        else:
            end = min(start + 8.0, duration)
        end = max(start + 0.5, end)
        raw_segments.append({"text": line.text, "start": start, "end": end})

    # Pad segments by 0.3s on both sides (clamped to [0, duration])
    padded_segments: List[dict[str, Any]] = []
    for seg in raw_segments:
        p_start = max(0.0, seg["start"] - 0.3)
        p_end = min(duration, seg["end"] + 0.3)
        padded_segments.append({"text": seg["text"], "start": p_start, "end": p_end})

    # 5. WhisperX forced alignment
    lang_code = normalize_lang_code(meta.language) or "en"
    aligned_segments = _run_whisperx_alignment(vocals_16k, padded_segments, lang_code, DEVICE)

    final_lines: List[dict[str, Any]] = []
    alignment_type = "forced" if aligned_segments is not None else "line-only"

    if aligned_segments is not None and len(aligned_segments) == len(raw_segments):
        for orig_seg, alg_seg in zip(raw_segments, aligned_segments):
            words = []
            for w in alg_seg.get("words", []):
                words.append({
                    "w": w.get("word", ""),
                    "s": w.get("start"),
                    "e": w.get("end"),
                    "score": w.get("score"),
                })
            final_lines.append({
                "start": orig_seg["start"],
                "end": orig_seg["end"],
                "text": orig_seg["text"],
                "words": words,
            })
    else:
        # Line-only fallback: split text into words, interpolate evenly
        alignment_type = "line-only"
        for seg in raw_segments:
            words = [{"w": word, "s": None, "e": None, "score": None} for word in seg["text"].split()]
            final_lines.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
                "words": words,
            })

    intermediate = {
        "language": lang_code,
        "source": source,
        "alignment": alignment_type,
        "lines": final_lines,
    }
    _save_intermediate(song_id, intermediate)


def _save_intermediate(song_id: str, data: dict[str, Any]) -> None:
    path = lib.align_intermediate_path(song_id)
    fd, tmp = tempfile.mkstemp(dir=lib.work_dir(song_id), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
