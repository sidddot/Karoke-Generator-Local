"""Tests for karaoke video export: ASS karaoke, ffmpeg command, job flow."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app import jobs, library as lib
from app.pipeline.video import (
    ass_filter_path,
    ass_time,
    build_ffmpeg_cmd,
    escape_ass,
    karaoke_text_for_line,
    lyrics_to_ass,
    run as run_video,
)
from app.schemas import (
    LyricLine,
    Lyrics,
    LyricsQuality,
    SongMeta,
    SongSettings,
    SongStatus,
    WordTiming,
)


def _sample_lyrics() -> Lyrics:
    return Lyrics(
        version=1,
        language="en",
        source="lrclib-synced",
        alignment="forced",
        quality=LyricsQuality(mean_word_score=0.9, low_confidence=False),
        lines=[
            LyricLine(
                start=1.0,
                end=3.0,
                text="Hello world",
                words=[
                    WordTiming(w="Hello", s=1.0, e=1.5, score=0.9),
                    WordTiming(w="world", s=1.6, e=2.8, score=0.8),
                ],
            ),
            LyricLine(
                start=4.0,
                end=6.0,
                text="Brace {me}",
                words=[
                    WordTiming(w="Brace", s=4.0, e=4.5, score=0.7),
                    WordTiming(w="{me}", s=4.5, e=5.5, score=0.7),
                ],
            ),
        ],
    )


def test_ass_time_format():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(1.5) == "0:00:01.50"
    assert ass_time(65.03) == "0:01:05.03"
    assert ass_time(-1) == "0:00:00.00"


def test_escape_ass_braces_and_slashes():
    assert r"\{me\}" in escape_ass("{me}")
    assert r"\\" in escape_ass("a\\b")


def test_karaoke_k_tags_match_word_durations():
    line = _sample_lyrics().lines[0]
    text = karaoke_text_for_line(line)
    # Hello is 0.50s -> \k50; gap 0.10s before world -> \k10; world 1.20s -> \k120
    assert r"{\k50}Hello " in text
    assert r"{\k10}" in text
    assert r"{\k120}world" in text


def test_lyrics_to_ass_contains_events_and_styles():
    ass = lyrics_to_ass(_sample_lyrics(), "Best Time", "Me", 8.0)
    assert "[Script Info]" in ass
    assert "PlayResX: 1280" in ass
    assert "Style: Default" in ass
    assert "Dialogue:" in ass
    assert "Best Time" in ass
    assert r"{\k50}Hello" in ass
    assert r"\{me\}" in ass
    assert ass_time(1.0) in ass
    assert ass_time(3.0) in ass


def test_ffmpeg_cmd_uses_libx264_aac_and_ass_filter():
    audio = Path("C:/tmp/instrumental.flac")
    ass = Path("C:/tmp/work/karaoke.ass")
    out = Path("C:/tmp/karaoke.tmp.mp4")
    cmd = build_ffmpeg_cmd(audio, ass, out, 12.5)
    joined = " ".join(cmd)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "libx264" in cmd
    assert "aac" in cmd
    assert "-shortest" in cmd
    assert "color=c=0x0b0b14" in joined
    assert "ass=" in joined
    assert str(audio) in cmd
    assert str(out) in cmd


def test_ass_filter_path_escapes_drive_colon():
    escaped = ass_filter_path(Path("C:/data/library/id/work/karaoke.ass"))
    assert r"\:" in escaped
    assert "'" not in escaped


def test_video_stage_not_done_without_mp4():
    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    try:
        lib.LIBRARY_DIR = tmp
        sid = "vidtest000001"
        lib.ensure_song_dirs(sid)
        lib.lyrics_path(sid).write_text("{}", encoding="utf-8")
        assert jobs._stage_done(sid, "finalize") is True
        assert jobs._stage_done(sid, "video") is False
        lib.karaoke_video_path(sid).write_bytes(b"mp4")
        assert jobs._stage_done(sid, "video") is True
    finally:
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)


def test_video_run_mocked_ffmpeg_writes_mp4_and_ass():
    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    calls: list[list[str]] = []

    class FakeProc:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"\x00\x00fake-mp4")
        return FakeProc()

    try:
        lib.LIBRARY_DIR = tmp
        sid = "vidtest000002"
        lib.ensure_song_dirs(sid)
        lib.write_meta(
            SongMeta(
                id=sid,
                title="Best Time",
                artist="Me",
                duration_sec=8.0,
                created_at="2026-11-08T00:00:00Z",
                source_filename="song.wav",
                settings=SongSettings(
                    separation_model="m.ckpt",
                    whisper_model="small",
                ),
            )
        )
        lib.write_lyrics(sid, _sample_lyrics())
        lib.instrumental_path(sid).write_bytes(b"flac-bytes")

        orig = __import__("app.pipeline.video", fromlist=["subprocess"]).subprocess
        import app.pipeline.video as video_mod
        video_mod.subprocess.run = fake_run  # type: ignore[method-assign]
        try:
            run_video(sid)
        finally:
            video_mod.subprocess.run = orig.run

        assert lib.karaoke_ass_path(sid).exists()
        ass_text = lib.karaoke_ass_path(sid).read_text(encoding="utf-8")
        assert "Hello" in ass_text
        assert lib.karaoke_video_path(sid).exists()
        assert lib.karaoke_video_path(sid).stat().st_size > 0
        assert calls, "ffmpeg should have been invoked"
        assert "libx264" in calls[0]
    finally:
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)


def test_video_run_fails_without_lyrics():
    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    try:
        lib.LIBRARY_DIR = tmp
        sid = "vidtest000003"
        lib.ensure_song_dirs(sid)
        lib.instrumental_path(sid).write_bytes(b"flac")
        lib.write_meta(
            SongMeta(
                id=sid,
                title="T",
                artist="A",
                duration_sec=1.0,
                created_at="2026-11-08T00:00:00Z",
                source_filename="s.wav",
                settings=SongSettings(separation_model="m", whisper_model="small"),
            )
        )
        try:
            run_video(sid)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "lyrics.json" in str(exc)
    finally:
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)


def test_job_flow_runs_video_after_finalize():
    """Worker must execute video after finalize when karaoke.mp4 is missing."""
    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    order: list[str] = []
    saved_registry = dict(jobs._stage_registry)

    def stub(name: str):
        def _fn(song_id: str) -> None:
            order.append(name)
            if name == "prepare":
                lib.prep_wav_path(song_id).write_bytes(b"x")
            elif name == "separate":
                lib.instrumental_path(song_id).write_bytes(b"x")
                lib.vocals_path(song_id).write_bytes(b"x")
                lib.vocals_16k_path(song_id).write_bytes(b"x")
            elif name == "lyrics":
                lib.lyrics_raw_path(song_id).write_text("{}", encoding="utf-8")
            elif name == "align":
                lib.align_intermediate_path(song_id).write_text("{}", encoding="utf-8")
            elif name == "finalize":
                lib.lyrics_path(song_id).write_text("{}", encoding="utf-8")
            elif name == "video":
                lib.karaoke_video_path(song_id).write_bytes(b"mp4")
        return _fn

    try:
        lib.LIBRARY_DIR = tmp
        sid = "jobflowvideo01"
        lib.ensure_song_dirs(sid)
        lib.write_meta(
            SongMeta(
                id=sid,
                title="T",
                artist="A",
                duration_sec=1.0,
                created_at="2026-11-08T00:00:00Z",
                source_filename="s.wav",
                settings=SongSettings(separation_model="m", whisper_model="small"),
            )
        )
        lib.write_status(sid, SongStatus())
        for name in jobs.STAGE_ORDER:
            jobs.register_stage(name, stub(name))
        jobs._run_job(jobs.Job(song_id=sid, from_stage="prepare"))
        assert order == ["prepare", "separate", "lyrics", "align", "finalize", "video"]
        status = lib.read_status(sid)
        assert status.state == "done"
        assert jobs._stage_done(sid, "video") is True
    finally:
        jobs._stage_registry.clear()
        jobs._stage_registry.update(saved_registry)
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)


def test_job_skips_video_when_mp4_exists():
    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    order: list[str] = []
    saved_registry = dict(jobs._stage_registry)

    def mark(name: str):
        def _fn(song_id: str) -> None:
            order.append(name)
        return _fn

    try:
        lib.LIBRARY_DIR = tmp
        sid = "jobflowvideo02"
        lib.ensure_song_dirs(sid)
        lib.write_meta(
            SongMeta(
                id=sid,
                title="T",
                artist="A",
                duration_sec=1.0,
                created_at="2026-11-08T00:00:00Z",
                source_filename="s.wav",
                settings=SongSettings(separation_model="m", whisper_model="small"),
            )
        )
        lib.write_status(sid, SongStatus())
        lib.prep_wav_path(sid).write_bytes(b"x")
        lib.instrumental_path(sid).write_bytes(b"x")
        lib.vocals_path(sid).write_bytes(b"x")
        lib.vocals_16k_path(sid).write_bytes(b"x")
        lib.lyrics_raw_path(sid).write_text("{}", encoding="utf-8")
        lib.align_intermediate_path(sid).write_text("{}", encoding="utf-8")
        lib.lyrics_path(sid).write_text("{}", encoding="utf-8")
        lib.karaoke_video_path(sid).write_bytes(b"mp4")
        for name in jobs.STAGE_ORDER:
            jobs.register_stage(name, mark(name))
        jobs._run_job(jobs.Job(song_id=sid, from_stage="prepare"))
        assert order == []
        assert lib.read_status(sid).state == "done"
    finally:
        jobs._stage_registry.clear()
        jobs._stage_registry.update(saved_registry)
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)


def test_real_ffmpeg_produces_mp4_with_audio_and_video():
    """If ffmpeg/ffprobe are on PATH, encode a ~0.5s karaoke clip and probe it."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return  # environment without ffmpeg: skip (runner has no pytest.skip)

    prev = lib.LIBRARY_DIR
    tmp = Path(tempfile.mkdtemp())
    try:
        lib.LIBRARY_DIR = tmp
        sid = "vidreal000001"
        lib.ensure_song_dirs(sid)
        audio = lib.instrumental_path(sid)
        gen = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
                "-c:a", "flac", str(audio),
            ],
            capture_output=True,
            text=True,
        )
        assert gen.returncode == 0, gen.stderr[-500:]
        lib.write_meta(
            SongMeta(
                id=sid,
                title="Sine",
                artist="Test",
                duration_sec=0.6,
                created_at="2026-11-08T00:00:00Z",
                source_filename="sine.wav",
                settings=SongSettings(separation_model="m", whisper_model="small"),
            )
        )
        lib.write_lyrics(
            sid,
            Lyrics(
                version=1,
                language="en",
                source="whisper",
                alignment="line-only",
                quality=LyricsQuality(mean_word_score=None, low_confidence=True),
                lines=[
                    LyricLine(
                        start=0.0,
                        end=0.55,
                        text="La la",
                        words=[
                            WordTiming(w="La", s=0.0, e=0.25, score=None),
                            WordTiming(w="la", s=0.25, e=0.5, score=None),
                        ],
                    )
                ],
            ),
        )
        run_video(sid)
        mp4 = lib.karaoke_video_path(sid)
        assert mp4.exists() and mp4.stat().st_size > 1000
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(mp4),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        kinds = {s.get("codec_type") for s in streams}
        assert "video" in kinds
        assert "audio" in kinds
    finally:
        lib.LIBRARY_DIR = prev
        shutil.rmtree(tmp, ignore_errors=True)
