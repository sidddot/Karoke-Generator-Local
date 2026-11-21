"""Stage 1: prepare — ffprobe + ffmpeg to 44.1 kHz stereo WAV."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from app import library as lib

log = logging.getLogger(__name__)

FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"


def probe_duration(path: Path) -> float:
    """Return audio duration in seconds using ffprobe."""
    cmd = [
        FFPROBE, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "a:0", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    if not streams:
        raise RuntimeError(f"No audio stream found in {path}")
    stream = streams[0]
    # Try duration tag first, then calculated from nb_frames/r_frame_rate
    if "duration" in stream:
        return float(stream["duration"])
    # Fallback: container duration
    cmd2 = [
        FFPROBE, "-v", "quiet", "-print_format", "json",
        "-show_format", str(path),
    ]
    r2 = subprocess.run(cmd2, capture_output=True, text=True, check=True)
    fmt = json.loads(r2.stdout).get("format", {})
    if "duration" in fmt:
        return float(fmt["duration"])
    raise RuntimeError(f"Could not determine duration of {path}")


def run(song_id: str) -> None:
    """Convert uploaded file to 44.1 kHz stereo WAV."""
    meta = lib.read_meta(song_id)
    song_folder = lib.song_dir(song_id)

    # Find original file
    originals = list(song_folder.glob("original.*"))
    if not originals:
        raise RuntimeError("No original file found in song folder")
    original = originals[0]

    out_path = lib.prep_wav_path(song_id)
    if out_path.exists() and out_path.stat().st_size > 0:
        log.info("prepare: %s already done", song_id)
        return

    # Probe duration and update meta
    duration = probe_duration(original)
    meta.duration_sec = duration
    lib.write_meta(meta)

    tmp_path = out_path.with_suffix(".tmp.wav")
    cmd = [
        FFMPEG, "-y",
        "-i", str(original),
        "-map", "0:a:0",          # first audio stream
        "-af", "dynaudnorm=f=150:g=15:m=10.0",  # normalize loudness for clean separation & playback
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(tmp_path),
    ]
    log.info("prepare: running ffmpeg for %s", song_id)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-1000:]}")

    tmp_path.rename(out_path)
    log.info("prepare: done for %s (%.1f s)", song_id, duration)
