"""Stage 3: lyrics lookup via LRCLIB, LRC parser, and matching logic."""
from __future__ import annotations

import json
import logging
import os
import re
import string
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlencode

import httpx

from app import library as lib

log = logging.getLogger(__name__)

LRCLIB_BASE_URL = "https://lrclib.net"
USER_AGENT = "KarokeGen/0.1.0 (https://github.com/local-karaoke)"


# ---------------------------------------------------------------------------
# Title normalisation & Matching
# ---------------------------------------------------------------------------

_BRACKET_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalize_title(title: str) -> str:
    """Lowercase, strip bracketed edition text, strip punctuation and extra spaces."""
    cleaned = _BRACKET_RE.sub(" ", title)
    cleaned = cleaned.translate(_PUNCT_TABLE)
    return " ".join(cleaned.lower().split())


def matches_title(query_title: str, candidate_title: str) -> bool:
    norm_q = normalize_title(query_title)
    norm_c = normalize_title(candidate_title)
    if not norm_q or not norm_c:
        return False
    return norm_q == norm_c or norm_q in norm_c or norm_c in norm_q


# ---------------------------------------------------------------------------
# LRC Parser
# ---------------------------------------------------------------------------

@dataclass
class LrcLine:
    timestamp_sec: float
    text: str


_TIME_TAG_RE = re.compile(r"\[(\d{1,2}):(\d{1,2}(?:\.\d+)?)\]")
_OFFSET_TAG_RE = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)


def parse_lrc(lrc_text: str) -> List[LrcLine]:
    """Parse LRC content into sorted timestamped lines.

    Handles multiple timestamps per line, honors [offset:+/-ms], ignores other tags.
    """
    offset_sec = 0.0
    lines = lrc_text.splitlines()

    # Look for [offset:+/-ms]
    for line in lines:
        offset_match = _OFFSET_TAG_RE.search(line)
        if offset_match:
            try:
                offset_sec = float(offset_match.group(1)) / 1000.0
            except ValueError:
                pass

    parsed: List[LrcLine] = []

    for line in lines:
        tags = _TIME_TAG_RE.findall(line)
        if not tags:
            continue

        clean_text = _TIME_TAG_RE.sub("", line).strip()

        for mm_str, ss_str in tags:
            try:
                seconds = int(mm_str) * 60 + float(ss_str) + offset_sec
                seconds = max(0.0, seconds)
                parsed.append(LrcLine(timestamp_sec=round(seconds, 3), text=clean_text))
            except ValueError:
                continue

    parsed.sort(key=lambda x: x.timestamp_sec)
    return parsed


# ---------------------------------------------------------------------------
# LRCLIB HTTP Client
# ---------------------------------------------------------------------------

def fetch_lrclib(
    title: str,
    artist: str,
    album: Optional[str],
    duration_sec: float,
) -> Optional[dict[str, Any]]:
    """Fetch lyrics from LRCLIB with /api/get and /api/search fallback."""
    headers = {"User-Agent": USER_AGENT}

    # 1. Direct GET
    get_params: dict[str, Any] = {
        "track_name": title,
        "artist_name": artist,
    }
    if album:
        get_params["album_name"] = album
    if duration_sec > 0:
        get_params["duration"] = round(duration_sec)

    url_get = f"{LRCLIB_BASE_URL}/api/get?{urlencode(get_params)}"
    log.info("LRCLIB /api/get: %s", url_get)

    candidate: Optional[dict[str, Any]] = None

    for attempt in range(2):
        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                resp = client.get(url_get)
                if resp.status_code == 200:
                    candidate = resp.json()
                    break
                elif resp.status_code == 404:
                    break
        except Exception as exc:
            log.warning("LRCLIB /api/get attempt %d failed: %s", attempt + 1, exc)
            time.sleep(0.5)

    # Validate direct get result if found
    if candidate:
        cand_dur = float(candidate.get("duration") or 0.0)
        cand_title = candidate.get("trackName") or ""
        dur_ok = duration_sec <= 0 or abs(duration_sec - cand_dur) <= 3.0
        if dur_ok and matches_title(title, cand_title):
            return candidate

    # 2. Search fallback
    search_params = {"track_name": title, "artist_name": artist}
    url_search = f"{LRCLIB_BASE_URL}/api/search?{urlencode(search_params)}"
    log.info("LRCLIB /api/search: %s", url_search)

    search_results: list[dict[str, Any]] = []
    for attempt in range(2):
        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                resp = client.get(url_search)
                if resp.status_code == 200:
                    search_results = resp.json()
                    break
        except Exception as exc:
            log.warning("LRCLIB /api/search attempt %d failed: %s", attempt + 1, exc)
            time.sleep(0.5)

    # Filter and sort matching search results
    valid_results: list[dict[str, Any]] = []
    for res in search_results:
        cand_dur = float(res.get("duration") or 0.0)
        cand_title = res.get("trackName") or ""
        dur_ok = duration_sec <= 0 or abs(duration_sec - cand_dur) <= 3.0
        if dur_ok and matches_title(title, cand_title):
            valid_results.append(res)

    if not valid_results:
        return None

    # Prefer one with syncedLyrics
    synced = [r for r in valid_results if r.get("syncedLyrics")]
    if synced:
        return synced[0]

    return valid_results[0]


# ---------------------------------------------------------------------------
# Pipeline Stage Runner
# ---------------------------------------------------------------------------

def run(song_id: str) -> None:
    """Execute lyrics fetch and write lyrics_raw.json."""
    raw_path = lib.lyrics_raw_path(song_id)

    # Idempotency check: if lyrics_raw.json already exists, skip
    if raw_path.exists() and raw_path.stat().st_size > 0:
        log.info("lyrics: %s already has lyrics_raw.json", song_id)
        return

    meta = lib.read_meta(song_id)

    # Check if manual lyrics was already written
    if raw_path.exists():
        try:
            with raw_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_manual"):
                log.info("lyrics: %s has manual lyrics, skipping LRCLIB", song_id)
                return
        except Exception:
            pass

    log.info("lyrics: looking up LRCLIB for '%s' by '%s'", meta.title, meta.artist)
    result = fetch_lrclib(
        title=meta.title,
        artist=meta.artist,
        album=meta.album,
        duration_sec=meta.duration_sec,
    )

    if result is None:
        log.info("lyrics: no LRCLIB match found for %s", song_id)
        result = {
            "id": None,
            "trackName": meta.title,
            "artistName": meta.artist,
            "syncedLyrics": None,
            "plainLyrics": None,
            "instrumental": False,
        }

    # Save to lyrics_raw.json atomically
    fd, tmp = tempfile.mkstemp(dir=lib.song_dir(song_id), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    os.replace(tmp, raw_path)

    log.info("lyrics: saved lyrics_raw.json for %s", song_id)
