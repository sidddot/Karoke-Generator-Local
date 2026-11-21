"""Stage: fallback transcription via WhisperX / faster-whisper."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, List, Optional

from app import library as lib
from app.config import (
    DEVICE,
    WHISPER_MODEL_CPU,
    WHISPER_MODEL_GPU,
)

log = logging.getLogger(__name__)


LANG_NAME_TO_CODE: dict[str, str] = {
    "hindi": "hi",
    "english": "en",
    "malayalam": "ml",
    "tamil": "ta",
    "telugu": "te",
    "bengali": "bn",
    "marathi": "mr",
    "gujarati": "gu",
    "kannada": "kn",
    "punjabi": "pa",
    "urdu": "ur",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh",
}


def normalize_lang_code(raw: Optional[str]) -> Optional[str]:
    """Map common language names (e.g. 'hindi') to 2-letter ISO codes (e.g. 'hi')."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    return LANG_NAME_TO_CODE.get(cleaned, cleaned[:2] if len(cleaned) > 2 else cleaned)


def _is_hallucination(text: str) -> bool:
    """Detect repetitive single-token or degenerate hallucinated text like 'ლ ლ ლ'."""
    tokens = text.strip().split()
    if not tokens:
        return True
    # If all tokens are identical and repeat 3+ times (e.g. 'ლ ლ ლ')
    if len(tokens) >= 3 and len(set(tokens)) == 1:
        return True
    # If 4+ tokens with only 1 or 2 distinct words
    if len(tokens) >= 5 and len(set(w.lower() for w in tokens)) <= 2:
        return True
    return False


def _transcribe_audio(
    audio_path: Path,
    device: str,
    requested_lang: Optional[str],
) -> tuple[List[dict[str, Any]], str]:
    """Transcribe audio using WhisperX with language normalization and anti-hallucination settings."""
    import whisperx

    model_name = WHISPER_MODEL_GPU if device == "cuda" else WHISPER_MODEL_CPU
    if device == "cpu":
        log.warning("WhisperX running on CPU using model '%s'", model_name)

    compute_type = "int8" if device == "cpu" else "float16"
    log.info("Loading WhisperX model '%s' (compute_type=%s)", model_name, compute_type)

    lang_to_use = normalize_lang_code(requested_lang)

    model = whisperx.load_model(
        model_name,
        device=device,
        compute_type=compute_type,
        language=lang_to_use,
    )

    audio = whisperx.load_audio(str(audio_path))

    transcribe_options: dict[str, Any] = {
        "batch_size": 4,
    }
    if lang_to_use:
        transcribe_options["language"] = lang_to_use

    result = model.transcribe(audio, **transcribe_options)
    detected_lang = result.get("language") or lang_to_use or "en"
    raw_segments = result.get("segments", [])

    # Filter out empty or hallucinated repetitive segments
    clean_segments = [s for s in raw_segments if not _is_hallucination(s.get("text", ""))]
    log.info("transcribe: %d segments retained (%d filtered as hallucinations)",
             len(clean_segments), len(raw_segments) - len(clean_segments))

    return clean_segments, detected_lang


def run(song_id: str) -> None:
    """Run transcription on vocals_16k.wav and align word timings."""
    meta = lib.read_meta(song_id)
    vocals_16k = lib.vocals_16k_path(song_id)

    log.info("transcribe: starting WhisperX transcription for %s", song_id)

    try:
        segments, lang = _transcribe_audio(vocals_16k, DEVICE, meta.language)
        if not segments:
            log.info("transcribe: no speech segments detected for %s — setting Instrumental", song_id)
            segments = [{"text": "Instrumental", "start": 0.0, "end": max(meta.duration_sec, 5.0)}]
    except Exception as exc:
        log.warning("WhisperX transcription failed: %s — generating placeholder line", exc)
        segments = [{"text": "Transcription unavailable", "start": 0.0, "end": max(meta.duration_sec, 5.0)}]
        lang = meta.language or "en"

    # Try word-level alignment on the transcribed segments
    aligned_segments = None
    try:
        import whisperx
        log.info("Aligning transcribed segments for language '%s'", lang)
        align_model, metadata = whisperx.load_align_model(language_code=lang, device=DEVICE)
        audio = whisperx.load_audio(str(vocals_16k))
        align_res = whisperx.align(
            segments,
            align_model,
            metadata,
            audio,
            DEVICE,
            return_char_alignments=False,
        )
        aligned_segments = align_res.get("segments", [])
    except Exception as exc:
        log.warning("WhisperX alignment on transcribed segments failed (%s) — using line-only", exc)

    final_lines: List[dict[str, Any]] = []
    alignment_type = "transcribed" if aligned_segments is not None else "line-only"

    if aligned_segments is not None:
        for seg in aligned_segments:
            words = []
            for w in seg.get("words", []):
                words.append({
                    "w": w.get("word", ""),
                    "s": w.get("start"),
                    "e": w.get("end"),
                    "score": w.get("score"),
                })
            final_lines.append({
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", "").strip(),
                "words": words,
            })
    else:
        for seg in segments:
            text = seg.get("text", "").strip()
            words = [{"w": word, "s": None, "e": None, "score": None} for word in text.split()]
            final_lines.append({
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": text,
                "words": words,
            })

    intermediate = {
        "language": lang,
        "source": "whisper",
        "alignment": alignment_type,
        "lines": final_lines,
    }

    path = lib.align_intermediate_path(song_id)
    fd, tmp = tempfile.mkstemp(dir=lib.work_dir(song_id), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(intermediate, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

    log.info("transcribe: successfully generated align_intermediate.json for %s", song_id)
