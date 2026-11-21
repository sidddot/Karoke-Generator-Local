"""Regression: empty stage-output lists must not mark lyrics/align as done."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app import jobs, library as lib


def _with_tmp_library(fn):
    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    try:
        lib.LIBRARY_DIR = tmp
        sid = "abc123def456"
        lib.ensure_song_dirs(sid)
        fn(sid)
    finally:
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)


def test_lyrics_and_align_not_done_without_outputs():
    def body(song_id: str) -> None:
        lib.prep_wav_path(song_id).write_bytes(b"x")
        lib.instrumental_path(song_id).write_bytes(b"x")
        lib.vocals_path(song_id).write_bytes(b"x")
        lib.vocals_16k_path(song_id).write_bytes(b"x")

        assert jobs._stage_done(song_id, "prepare") is True
        assert jobs._stage_done(song_id, "separate") is True
        assert jobs._stage_done(song_id, "lyrics") is False
        assert jobs._stage_done(song_id, "align") is False
        assert jobs._stage_done(song_id, "finalize") is False
        assert jobs._stage_done(song_id, "video") is False

    _with_tmp_library(body)


def test_lyrics_and_align_done_when_outputs_exist():
    def body(song_id: str) -> None:
        lib.lyrics_raw_path(song_id).write_text("{}", encoding="utf-8")
        lib.align_intermediate_path(song_id).write_text('{"lines":[]}', encoding="utf-8")
        lib.lyrics_path(song_id).write_text("{}", encoding="utf-8")
        lib.karaoke_video_path(song_id).write_bytes(b"mp4")

        assert jobs._stage_done(song_id, "lyrics") is True
        assert jobs._stage_done(song_id, "align") is True
        assert jobs._stage_done(song_id, "finalize") is True
        assert jobs._stage_done(song_id, "video") is True

    _with_tmp_library(body)
