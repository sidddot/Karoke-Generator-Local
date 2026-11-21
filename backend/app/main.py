"""FastAPI application: routes, middleware, startup."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import library as lib
from app import jobs
from app.config import (
    ALLOWED_EXTENSIONS,
    DEFAULT_SEPARATION_MODEL,
    DEVICE,
    LIBRARY_DIR,
    MAX_DURATION_SEC,
    MAX_FILE_BYTES,
    WHISPER_MODEL_CPU,
    WHISPER_MODEL_GPU,
    ffmpeg_present,
    ffprobe_present,
)
from app.schemas import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    Lyrics,
    ManualLyricsRequest,
    ReprocessRequest,
    SongCreateResponse,
    SongDetail,
    SongMeta,
    SongSettings,
    SongStatus,
    YoutubeRequest,
)
from app.pipeline.transcribe import normalize_lang_code

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="KarokeGen", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _err(code: str, message: str, http_status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail=ErrorResponse(error=ErrorDetail(code=code, message=message)).model_dump(),
    )


# ---------------------------------------------------------------------------
# Static audio mount (Range-request support via StaticFiles)
# ---------------------------------------------------------------------------
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(LIBRARY_DIR)), name="audio")


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    # Register real pipeline stages first
    try:
        from app.pipeline.prepare import run as run_prepare
        jobs.register_stage("prepare", run_prepare)
    except Exception as exc:
        log.warning("prepare stage not registered: %s", exc)

    try:
        from app.pipeline.separate import run as run_separate
        jobs.register_stage("separate", run_separate)
    except Exception as exc:
        log.warning("separate stage not registered: %s", exc)

    try:
        from app.pipeline.lrclib import run as run_lyrics
        jobs.register_stage("lyrics", run_lyrics)
    except Exception as exc:
        log.warning("lyrics stage not registered: %s", exc)

    try:
        from app.pipeline.align import run as run_align
        jobs.register_stage("align", run_align)
    except Exception as exc:
        log.warning("align stage not registered: %s", exc)

    try:
        from app.pipeline.finalize import run as run_finalize
        jobs.register_stage("finalize", run_finalize)
    except Exception as exc:
        log.warning("finalize stage not registered: %s", exc)

    try:
        from app.pipeline.video import run as run_video
        jobs.register_stage("video", run_video)
    except Exception as exc:
        log.warning("video stage not registered: %s", exc)

    # Start worker and resume jobs
    jobs.start_worker()
    jobs.resume_incomplete_jobs()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    cached: list[str] = []
    # Check common model cache locations
    import os
    cache_dirs = [
        Path.home() / ".cache" / "audio-separator",
        Path.home() / "AppData" / "Local" / "audio-separator",
    ]
    for cd in cache_dirs:
        if cd.exists():
            cached += [p.name for p in cd.rglob("*.ckpt")]
            cached += [p.name for p in cd.rglob("*.pth")]

    return HealthResponse(
        ok=ffmpeg_present() and ffprobe_present(),
        device=DEVICE,
        ffmpeg=ffmpeg_present(),
        ffprobe=ffprobe_present(),
        models_cached=cached,
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

_SANITIZE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize(name: str) -> str:
    return _SANITIZE_RE.sub("_", name)[:200]


def _new_song_id() -> str:
    return uuid.uuid4().hex[:12]


def _whisper_model() -> str:
    return WHISPER_MODEL_GPU if DEVICE == "cuda" else WHISPER_MODEL_CPU


# ---------------------------------------------------------------------------
# POST /api/songs — upload
# ---------------------------------------------------------------------------

@app.post("/api/songs", response_model=SongCreateResponse, status_code=201)
async def upload_song(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(...),
    album: str | None = Form(None),
    language: str | None = Form(None),
) -> SongCreateResponse:
    # --- extension check ---
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise _err("invalid_extension", f"File type '{suffix}' not supported.", 400)

    # --- size check (stream into temp buffer) ---
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise _err("file_too_large", "File exceeds 500 MB limit.", 413)

    # --- create song folder ---
    song_id = _new_song_id()
    lib.ensure_song_dirs(song_id)

    # --- save original ---
    safe_name = _sanitize(Path(file.filename or "upload").stem) + suffix
    original_path = lib.song_dir(song_id) / f"original{suffix}"
    original_path.write_bytes(content)

    # --- probe duration (needs ffprobe) ---
    duration = 0.0
    if ffprobe_present():
        try:
            from app.pipeline.prepare import probe_duration
            duration = probe_duration(original_path)
            if duration > MAX_DURATION_SEC:
                import shutil
                shutil.rmtree(lib.song_dir(song_id), ignore_errors=True)
                raise _err("too_long", "Audio longer than 12 minutes.", 400)
        except ImportError:
            pass  # prepare not installed yet; skip duration check

    # --- write meta ---
    meta = SongMeta(
        id=song_id,
        title=title.strip(),
        artist=artist.strip(),
        album=album.strip() if album else None,
        duration_sec=duration,
        language=normalize_lang_code(language),
        created_at=datetime.now(timezone.utc).isoformat(),
        source_filename=safe_name,
        settings=SongSettings(
            separation_model=DEFAULT_SEPARATION_MODEL,
            whisper_model=_whisper_model(),
        ),
    )
    lib.write_meta(meta)
    lib.write_status(song_id, SongStatus(device=DEVICE))

    # --- enqueue ---
    jobs.enqueue(song_id)
    return SongCreateResponse(id=song_id)


# ---------------------------------------------------------------------------
# POST /api/songs/from-youtube — add song from YouTube URL
# ---------------------------------------------------------------------------

@app.post("/api/songs/from-youtube", response_model=SongCreateResponse, status_code=201)
async def add_from_youtube(body: YoutubeRequest) -> SongCreateResponse:
    # Validate URL looks like YouTube
    url = body.url.strip()
    if not ("youtube.com" in url or "youtu.be" in url):
        raise _err("invalid_url", "URL must be a YouTube link (youtube.com or youtu.be).", 400)

    song_id = _new_song_id()
    lib.ensure_song_dirs(song_id)

    # Download audio using yt-dlp (runs synchronously — may take 10–60 s)
    try:
        from app.pipeline.youtube import download as yt_download
        downloaded = yt_download(url, lib.song_dir(song_id), song_id)
    except Exception as exc:
        import shutil
        shutil.rmtree(lib.song_dir(song_id), ignore_errors=True)
        raise _err("download_failed", f"yt-dlp download failed: {exc}", 500)

    # Probe duration
    duration = 0.0
    if ffprobe_present():
        try:
            from app.pipeline.prepare import probe_duration
            duration = probe_duration(downloaded)
            if duration > MAX_DURATION_SEC:
                import shutil
                shutil.rmtree(lib.song_dir(song_id), ignore_errors=True)
                raise _err("too_long", "Audio longer than 12 minutes.", 400)
        except ImportError:
            pass

    safe_name = _sanitize(body.title) + downloaded.suffix
    meta = SongMeta(
        id=song_id,
        title=body.title.strip(),
        artist=body.artist.strip(),
        album=body.album.strip() if body.album else None,
        duration_sec=duration,
        language=normalize_lang_code(body.language),
        created_at=datetime.now(timezone.utc).isoformat(),
        source_filename=safe_name,
        settings=SongSettings(
            separation_model=DEFAULT_SEPARATION_MODEL,
            whisper_model=_whisper_model(),
        ),
    )
    lib.write_meta(meta)
    lib.write_status(song_id, SongStatus(device=DEVICE))

    jobs.enqueue(song_id)
    return SongCreateResponse(id=song_id)


# ---------------------------------------------------------------------------
# GET /api/songs
# ---------------------------------------------------------------------------

@app.get("/api/songs", response_model=list[SongDetail])
async def list_songs() -> list[SongDetail]:
    result = []
    for sid in lib.list_songs():
        try:
            result.append(SongDetail(meta=lib.read_meta(sid), status=lib.read_status(sid)))
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# GET /api/songs/{id}
# ---------------------------------------------------------------------------

@app.get("/api/songs/{song_id}", response_model=SongDetail)
async def get_song(song_id: str) -> SongDetail:
    if not lib.song_exists(song_id):
        raise _err("not_found", "Song not found.", 404)
    return SongDetail(meta=lib.read_meta(song_id), status=lib.read_status(song_id))


# ---------------------------------------------------------------------------
# GET /api/songs/{id}/lyrics
# ---------------------------------------------------------------------------

@app.get("/api/songs/{song_id}/lyrics", response_model=Lyrics)
async def get_lyrics(song_id: str) -> Lyrics:
    if not lib.song_exists(song_id):
        raise _err("not_found", "Song not found.", 404)
    lyrics = lib.read_lyrics(song_id)
    if lyrics is None:
        raise _err("not_ready", "Lyrics not yet available.", 404)
    return lyrics


# ---------------------------------------------------------------------------
# PUT /api/songs/{id}/lyrics
# ---------------------------------------------------------------------------

@app.put("/api/songs/{song_id}/lyrics", status_code=202)
async def put_lyrics(song_id: str, body: ManualLyricsRequest) -> dict:
    if not lib.song_exists(song_id):
        raise _err("not_found", "Song not found.", 404)
    status_obj = lib.read_status(song_id)
    if status_obj.state == "running":
        raise _err("busy", "Song is currently processing.", 409)

    # Store raw lyrics to be picked up by the lyrics stage
    import json, os, tempfile
    raw_path = lib.lyrics_raw_path(song_id)
    manual_data = {"_manual": True, "format": body.format, "text": body.text}
    fd, tmp = tempfile.mkstemp(dir=lib.song_dir(song_id), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manual_data, f)
    os.replace(tmp, raw_path)

    # Remove downstream outputs so they're regenerated
    for p in [
        lib.align_intermediate_path(song_id),
        lib.lyrics_path(song_id),
        lib.karaoke_ass_path(song_id),
        lib.karaoke_video_path(song_id),
    ]:
        p.unlink(missing_ok=True)

    jobs.enqueue(song_id, from_stage="lyrics")
    return {"queued": True}


# ---------------------------------------------------------------------------
# POST /api/songs/{id}/reprocess
# ---------------------------------------------------------------------------

@app.post("/api/songs/{song_id}/reprocess", status_code=202)
async def reprocess(song_id: str, body: ReprocessRequest) -> dict:
    if not lib.song_exists(song_id):
        raise _err("not_found", "Song not found.", 404)
    status_obj = lib.read_status(song_id)
    if status_obj.state == "running":
        raise _err("busy", "Song is currently processing.", 409)

    stage = body.from_stage
    idx = jobs.STAGE_ORDER.index(stage)

    # Delete outputs for this stage and all later stages
    outputs_map = {
        "prepare":  [lib.prep_wav_path(song_id)],
        "separate": [lib.instrumental_path(song_id), lib.vocals_path(song_id),
                     lib.vocals_16k_path(song_id), lib.vocals_lead_path(song_id),
                     lib.vocals_backing_path(song_id)],
        "lyrics":   [lib.lyrics_raw_path(song_id)],
        "align":    [lib.align_intermediate_path(song_id)],
        "finalize": [lib.lyrics_path(song_id)],
        "video":    [lib.karaoke_ass_path(song_id), lib.karaoke_video_path(song_id)],
    }
    for s in jobs.STAGE_ORDER[idx:]:
        for p in outputs_map.get(s, []):
            p.unlink(missing_ok=True)

    jobs.enqueue(song_id, from_stage=stage)
    return {"queued": True, "from_stage": stage}


# ---------------------------------------------------------------------------
# DELETE /api/songs/{id}
# ---------------------------------------------------------------------------

@app.delete("/api/songs/{song_id}", status_code=204)
async def delete_song(song_id: str) -> None:
    if not lib.song_exists(song_id):
        raise _err("not_found", "Song not found.", 404)
    if jobs.current_running_id() == song_id:
        raise _err("busy", "Cannot delete a song that is currently processing.", 409)
    lib.delete_song(song_id)


# ---------------------------------------------------------------------------
# Custom error handler to enforce {error: {code, message}} format
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )
