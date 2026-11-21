"""Read/write song folders with atomic JSON operations."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.config import LIBRARY_DIR
from app.schemas import SongMeta, SongStatus, Lyrics


# ---------------------------------------------------------------------------
# Folder helpers
# ---------------------------------------------------------------------------

def song_dir(song_id: str) -> Path:
    return LIBRARY_DIR / song_id


def work_dir(song_id: str) -> Path:
    return song_dir(song_id) / "work"


def ensure_song_dirs(song_id: str) -> None:
    work_dir(song_id).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Atomic JSON I/O
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON to a temp file in the same directory, then rename atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)   # atomic on NTFS within same volume
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------

def write_meta(meta: SongMeta) -> None:
    _atomic_write_json(song_dir(meta.id) / "meta.json", meta.model_dump())


def read_meta(song_id: str) -> SongMeta:
    data = _read_json(song_dir(song_id) / "meta.json")
    return SongMeta.model_validate(data)


# ---------------------------------------------------------------------------
# status.json
# ---------------------------------------------------------------------------

def write_status(song_id: str, status: SongStatus) -> None:
    _atomic_write_json(song_dir(song_id) / "status.json", status.model_dump())


def read_status(song_id: str) -> SongStatus:
    path = song_dir(song_id) / "status.json"
    if not path.exists():
        return SongStatus()
    data = _read_json(path)
    return SongStatus.model_validate(data)


# ---------------------------------------------------------------------------
# lyrics.json
# ---------------------------------------------------------------------------

def write_lyrics(song_id: str, lyrics: Lyrics) -> None:
    _atomic_write_json(song_dir(song_id) / "lyrics.json", lyrics.model_dump())


def read_lyrics(song_id: str) -> Lyrics | None:
    path = song_dir(song_id) / "lyrics.json"
    if not path.exists():
        return None
    return Lyrics.model_validate(_read_json(path))


# ---------------------------------------------------------------------------
# Library listing and deletion
# ---------------------------------------------------------------------------

def list_songs() -> list[str]:
    """Return all song IDs found in the library directory."""
    if not LIBRARY_DIR.exists():
        return []
    return [
        d.name for d in LIBRARY_DIR.iterdir()
        if d.is_dir() and (d / "meta.json").exists()
    ]


def delete_song(song_id: str) -> None:
    """Remove a song folder entirely."""
    shutil.rmtree(song_dir(song_id), ignore_errors=False)


def song_exists(song_id: str) -> bool:
    return (song_dir(song_id) / "meta.json").exists()


# ---------------------------------------------------------------------------
# Output file paths (single source of truth)
# ---------------------------------------------------------------------------

def prep_wav_path(song_id: str) -> Path:
    return work_dir(song_id) / "prep_44k.wav"


def vocals_16k_path(song_id: str) -> Path:
    return work_dir(song_id) / "vocals_16k.wav"


def instrumental_path(song_id: str) -> Path:
    return song_dir(song_id) / "instrumental.flac"


def vocals_path(song_id: str) -> Path:
    return song_dir(song_id) / "vocals.flac"


def lyrics_raw_path(song_id: str) -> Path:
    return song_dir(song_id) / "lyrics_raw.json"


def align_intermediate_path(song_id: str) -> Path:
    return work_dir(song_id) / "align_intermediate.json"


def lyrics_path(song_id: str) -> Path:
    return song_dir(song_id) / "lyrics.json"


def karaoke_ass_path(song_id: str) -> Path:
    return work_dir(song_id) / "karaoke.ass"


def karaoke_video_path(song_id: str) -> Path:
    return song_dir(song_id) / "karaoke.mp4"


def vocals_lead_path(song_id: str) -> Path:
    return song_dir(song_id) / "vocals_lead.flac"


def vocals_backing_path(song_id: str) -> Path:
    return song_dir(song_id) / "vocals_backing.flac"
