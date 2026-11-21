"""Pydantic v2 models mirroring the on-disk JSON contracts in §2.4."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------

class SongSettings(BaseModel):
    separation_model: str
    whisper_model: str


class SongMeta(BaseModel):
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_sec: float = 0.0
    language: Optional[str] = None
    created_at: str
    source_filename: str
    settings: SongSettings


# ---------------------------------------------------------------------------
# status.json
# ---------------------------------------------------------------------------

Stage = Literal["prepare", "separate", "lyrics", "align", "finalize", "video"]
State = Literal["queued", "running", "done", "failed"]


class SongStatus(BaseModel):
    state: State = "queued"
    stage: Optional[Stage] = None
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    device: str = "cpu"
    timings_sec: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# lyrics.json
# ---------------------------------------------------------------------------

class WordTiming(BaseModel):
    w: str
    s: float = 0.0
    e: float = 0.0
    score: Optional[float] = None

    @field_validator("s", "e", mode="before")
    @classmethod
    def convert_none_to_zero(cls, v: Any) -> float:
        return 0.0 if v is None else v


class LyricLine(BaseModel):
    start: float
    end: float
    text: str
    words: list[WordTiming]


LyricsSource = Literal["lrclib-synced", "whisper", "manual-lrc", "manual-plain"]
LyricsAlignment = Literal["forced", "transcribed", "line-only"]


class LyricsQuality(BaseModel):
    mean_word_score: Optional[float] = None
    low_confidence: bool = False


class Lyrics(BaseModel):
    version: int = 1
    language: str
    source: LyricsSource
    alignment: LyricsAlignment
    quality: LyricsQuality
    lines: list[LyricLine]


# ---------------------------------------------------------------------------
# API request/response shapes
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SongCreateResponse(BaseModel):
    id: str


class SongDetail(BaseModel):
    meta: SongMeta
    status: SongStatus


class HealthResponse(BaseModel):
    ok: bool
    device: str
    ffmpeg: bool
    ffprobe: bool
    models_cached: list[str]


class ReprocessRequest(BaseModel):
    from_stage: Stage


class ManualLyricsRequest(BaseModel):
    format: Literal["lrc", "plain"]
    text: str


class YoutubeRequest(BaseModel):
    url: str
    title: str
    artist: str
    album: Optional[str] = None
    language: Optional[str] = None
