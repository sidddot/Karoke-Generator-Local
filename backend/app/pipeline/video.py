"""Stage 6: render karaoke.mp4 (instrumental + word-timed lyric overlay)."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from app import library as lib
from app.schemas import LyricLine, Lyrics

log = logging.getLogger(__name__)

FFMPEG = "ffmpeg"
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 30

# Hardware encoder probe order: try fastest available encoder, fall back to libx264.
# Each entry: (encoder_name, extra_flags)
_HW_ENCODERS = [
    ("h264_nvenc",  ["-preset", "fast"]),                    # NVIDIA
    ("h264_qsv",   ["-preset", "fast"]),                    # Intel QuickSync
    ("h264_amf",   ["-quality", "speed"]),                  # AMD
]


def _probe_hw_encoder() -> tuple[str, list[str]]:
    """Return the first hardware H.264 encoder available, or fall back to libx264."""
    for enc, extra in _HW_ENCODERS:
        try:
            result = subprocess.run(
                [FFMPEG, "-hide_banner", "-f", "lavfi", "-i",
                 "nullsrc=s=16x16:d=0.1", "-c:v", enc, "-f", "null", "NUL"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                log.info("video: using hardware encoder %s", enc)
                return enc, extra
        except Exception:
            continue
    log.info("video: no hardware encoder found, falling back to libx264")
    return "libx264", ["-preset", "veryfast", "-crf", "23"]


def ass_time(seconds: float) -> str:
    """ASS timestamp H:MM:SS.cc (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", " ")
        .replace("\r", "")
    )


def karaoke_text_for_line(line: LyricLine) -> str:
    """Build an ASS karaoke line using \\k tags (duration in centiseconds)."""
    if not line.words:
        return escape_ass(line.text or "...")

    parts: list[str] = []
    cursor = line.start
    for i, word in enumerate(line.words):
        gap = word.s - cursor
        if gap > 0.005:
            parts.append(f"{{\\k{max(1, int(round(gap * 100)))}}}")
        dur = max(word.e - word.s, 0.01)
        k = max(1, int(round(dur * 100)))
        spacer = " " if i < len(line.words) - 1 else ""
        parts.append(f"{{\\k{k}}}{escape_ass(word.w)}{spacer}")
        cursor = word.e
    return "".join(parts)


def lyrics_to_ass(lyrics: Lyrics, title: str, artist: str, duration_sec: float) -> str:
    """Convert lyrics.json into an ASS script with karaoke highlighting."""
    dur = max(duration_sec, 1.0)
    header = (
        "[Script Info]\n"
        "Title: KarokeGen\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {VIDEO_WIDTH}\n"
        f"PlayResY: {VIDEO_HEIGHT}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Primary = sung (gold), Secondary = upcoming (grey). &HAABBGGRR
        # Nirmala UI provides native Windows support for English, Hindi (Devanagari), Malayalam, Tamil, etc.
        "Style: Default,Nirmala UI,58,&H0000D7FF,&H00B0B0B0,&H00101010,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,3,0,2,70,70,90,1\n"
        "Style: Meta,Nirmala UI,32,&H00E8E8E8,&H00E8E8E8,&H00101010,&H80000000,"
        "0,0,0,0,100,100,0,0,1,2,0,8,50,50,48,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events: list[str] = [
        f"Dialogue: 0,{ass_time(0)},{ass_time(dur)},Meta,,0,0,0,,"
        f"{escape_ass(title)}\\N{escape_ass(artist)}",
    ]
    for line in lyrics.lines:
        start = max(0.0, line.start)
        end = max(start + 0.05, line.end)
        text = karaoke_text_for_line(line)
        events.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def ass_filter_path(path: Path) -> str:
    """Escape a Windows path for ffmpeg's ass= filter."""
    posix = path.resolve().as_posix()
    return posix.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def build_ffmpeg_cmd(
    audio_path: Path,
    ass_path: Path,
    out_path: Path,
    duration_sec: float,
) -> list[str]:
    dur = max(duration_sec, 0.2)
    # Optimization 2: auto-select hardware encoder; fall back to libx264
    encoder, enc_flags = _probe_hw_encoder()
    return [
        FFMPEG, "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x0b0b14:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}:d={dur:.3f}",
        "-i", str(audio_path),
        "-vf", f"ass='{ass_filter_path(ass_path)}'",
        "-c:v", encoder,
        "-pix_fmt", "yuv420p",
        *enc_flags,
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]


def _has_audible_content(path: Path) -> bool:
    """Check if audio has audible sound (mean_volume > -50 dB)."""
    try:
        cmd = [FFMPEG, "-i", str(path), "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "NUL"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        for line in res.stderr.splitlines():
            if "mean_volume:" in line:
                val = float(line.split("mean_volume:")[1].split("dB")[0].strip())
                return val > -50.0
    except Exception:
        pass
    return True


def run(song_id: str) -> None:
    """Write work/karaoke.ass and karaoke.mp4 from lyrics.json + instrumental."""
    out_path = lib.karaoke_video_path(song_id)
    if out_path.exists() and out_path.stat().st_size > 0:
        log.info("video: %s karaoke.mp4 already exists", song_id)
        return

    lyrics = lib.read_lyrics(song_id)
    if lyrics is None:
        raise RuntimeError(f"No lyrics.json for {song_id}; finalize must run first")

    audio_path = lib.instrumental_path(song_id)
    if not audio_path.exists() or audio_path.stat().st_size == 0 or not _has_audible_content(audio_path):
        log.info("video: instrumental.flac missing or silent for %s — using prep_44k.wav", song_id)
        audio_path = lib.prep_wav_path(song_id)

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError(f"No valid audio track for video encoding of {song_id}")

    meta = lib.read_meta(song_id)
    duration = max(meta.duration_sec, 0.5)
    ass_text = lyrics_to_ass(lyrics, meta.title, meta.artist, duration)

    ass_path = lib.karaoke_ass_path(song_id)
    lib.work_dir(song_id).mkdir(parents=True, exist_ok=True)
    fd, tmp_ass = _tmp_in(ass_path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(ass_text)
    os.replace(tmp_ass, ass_path)

    tmp_mp4 = out_path.with_name("karaoke.tmp.mp4")
    if tmp_mp4.exists():
        tmp_mp4.unlink()
    cmd = build_ffmpeg_cmd(audio_path, ass_path, tmp_mp4, duration)
    log.info("video: encoding karaoke.mp4 for %s", song_id)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not tmp_mp4.exists() or tmp_mp4.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg video encode failed: {(result.stderr or '')[-1500:]}")
    os.replace(tmp_mp4, out_path)
    log.info("video: wrote %s", out_path)


def _tmp_in(directory: Path) -> tuple[int, str]:
    import tempfile
    return tempfile.mkstemp(dir=directory, suffix=".tmp")
