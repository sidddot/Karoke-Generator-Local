"""Batch 0 tests: health endpoint, schema round-trips."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import SongMeta, SongStatus, Lyrics, WordTiming, LyricLine, LyricsQuality

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

def test_health_returns_200():
    r = client.get("/api/health")
    assert r.status_code == 200


def test_health_shape():
    r = client.get("/api/health")
    body = r.json()
    assert "ok" in body
    assert "device" in body
    assert "ffmpeg" in body
    assert "ffprobe" in body
    assert "models_cached" in body
    assert isinstance(body["models_cached"], list)


def test_health_device_valid():
    r = client.get("/api/health")
    assert r.json()["device"] in ("cuda", "cpu")


# ---------------------------------------------------------------------------
# Schema round-trips
# ---------------------------------------------------------------------------

def test_song_status_defaults():
    s = SongStatus()
    assert s.state == "queued"
    assert s.progress == 0.0
    assert s.error is None


def test_song_status_round_trip():
    s = SongStatus(state="running", stage="prepare", message="hello")
    data = s.model_dump()
    s2 = SongStatus.model_validate(data)
    assert s2.stage == "prepare"
    assert s2.message == "hello"


def test_lyrics_round_trip():
    lyr = Lyrics(
        version=1,
        language="en",
        source="lrclib-synced",
        alignment="forced",
        quality=LyricsQuality(mean_word_score=0.8),
        lines=[
            LyricLine(
                start=1.0, end=3.0, text="Hello world",
                words=[
                    WordTiming(w="Hello", s=1.0, e=1.5, score=0.9),
                    WordTiming(w="world", s=1.5, e=3.0, score=0.8),
                ],
            )
        ],
    )
    data = lyr.model_dump()
    lyr2 = Lyrics.model_validate(data)
    assert lyr2.lines[0].words[0].w == "Hello"
    assert lyr2.quality.mean_word_score == 0.8


# ---------------------------------------------------------------------------
# Error format
# ---------------------------------------------------------------------------

def test_upload_bad_extension():
    from io import BytesIO
    r = client.post(
        "/api/songs",
        data={"title": "T", "artist": "A"},
        files={"file": ("test.xyz", BytesIO(b"data"), "application/octet-stream")},
    )
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert "code" in body["error"]


def test_get_missing_song():
    r = client.get("/api/songs/doesnotexist000")
    assert r.status_code == 404
    assert "error" in r.json()


def test_list_songs_is_list():
    r = client.get("/api/songs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
