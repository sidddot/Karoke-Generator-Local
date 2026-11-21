"""YouTube audio download via yt-dlp."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_YT_DLP = "yt-dlp"


def download(url: str, out_dir: Path, song_id: str) -> Path:
    """Download best-quality audio from a YouTube URL into out_dir.

    Returns the path to the downloaded file (webm/m4a/opus).
    Raises RuntimeError on failure.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / f"original.%(ext)s")

    cmd = [
        _YT_DLP,
        "--no-playlist",
        "--format", "bestaudio/best",
        "--output", output_template,
        "--no-progress",
        url,
    ]

    log.info("youtube: downloading %s", url)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp failed (exit {result.returncode}): {result.stderr[-800:]}"
        )

    # Find the downloaded file
    candidates = sorted(out_dir.glob("original.*"))
    if not candidates:
        raise RuntimeError("yt-dlp ran but no output file found in directory")

    downloaded = candidates[0]
    log.info("youtube: downloaded to %s (%d bytes)", downloaded, downloaded.stat().st_size)
    return downloaded
