"""Job queue with a single background worker thread."""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app import library as lib
from app.config import DEVICE
from app.schemas import SongStatus, Stage

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage ordering and output file mapping
# ---------------------------------------------------------------------------

STAGE_ORDER: list[Stage] = ["prepare", "separate", "lyrics", "align", "finalize", "video"]


def _stage_outputs(song_id: str) -> dict[str, list[Path]]:
    """Files that must exist for a stage to be considered complete.

    lyrics always writes lyrics_raw.json (even on LRCLIB miss / instrumental).
    align / transcribe always write work/align_intermediate.json.
    """
    return {
        "prepare":  [lib.prep_wav_path(song_id)],
        "separate": [lib.instrumental_path(song_id), lib.vocals_path(song_id),
                     lib.vocals_16k_path(song_id)],
        "lyrics":   [lib.lyrics_raw_path(song_id)],
        "align":    [lib.align_intermediate_path(song_id)],
        "finalize": [lib.lyrics_path(song_id)],
        "video":    [lib.karaoke_video_path(song_id)],
    }


def _stage_done(song_id: str, stage: Stage) -> bool:
    outputs = _stage_outputs(song_id)[stage]
    # all([]) is True in Python — never treat an undeclared-output stage as done
    if not outputs:
        return False
    return all(p.exists() and p.stat().st_size > 0 for p in outputs)


# ---------------------------------------------------------------------------
# Registry of real stage functions (injected at startup)
# ---------------------------------------------------------------------------

_stage_registry: dict[str, Callable[[str], None]] = {}


def register_stage(name: str, fn: Callable[[str], None]) -> None:
    _stage_registry[name] = fn


# ---------------------------------------------------------------------------
# Job record
# ---------------------------------------------------------------------------

@dataclass
class Job:
    song_id: str
    from_stage: Stage = "prepare"


# ---------------------------------------------------------------------------
# Queue and worker
# ---------------------------------------------------------------------------

_job_queue: queue.Queue[Job] = queue.Queue()
_running_id: str | None = None
_lock = threading.Lock()


def enqueue(song_id: str, from_stage: Stage = "prepare") -> None:
    status = lib.read_status(song_id)
    status.state = "queued"
    status.stage = from_stage
    status.error = None
    status.message = "Waiting in queue"
    lib.write_status(song_id, status)
    _job_queue.put(Job(song_id=song_id, from_stage=from_stage))
    log.info("Enqueued song %s from stage %s", song_id, from_stage)


def current_running_id() -> str | None:
    with _lock:
        return _running_id


def _run_job(job: Job) -> None:
    global _running_id
    song_id = job.song_id

    with _lock:
        _running_id = song_id

    status = lib.read_status(song_id)
    status.state = "running"
    status.device = DEVICE
    lib.write_status(song_id, status)

    start_idx = STAGE_ORDER.index(job.from_stage)

    for idx, stage in enumerate(STAGE_ORDER[start_idx:], start=start_idx):
        if _stage_done(song_id, stage):
            log.info("Song %s: stage %s already done — skipping", song_id, stage)
            continue

        status = lib.read_status(song_id)
        status.stage = stage
        status.progress = round(idx / len(STAGE_ORDER), 2)
        status.message = f"Running stage: {stage}"
        lib.write_status(song_id, status)

        t0 = time.monotonic()
        try:
            fn = _stage_registry.get(stage)
            if fn is None:
                log.warning("No handler for stage %s — sleeping 0.2 s (stub)", stage)
                time.sleep(0.2)
            else:
                fn(song_id)
        except Exception as exc:
            log.exception("Song %s failed at stage %s", song_id, stage)
            status = lib.read_status(song_id)
            status.state = "failed"
            status.error = str(exc)
            status.message = f"Failed at {stage}: {exc}"
            lib.write_status(song_id, status)
            with _lock:
                _running_id = None
            return

        elapsed = time.monotonic() - t0
        status = lib.read_status(song_id)
        status.timings_sec[stage] = round(elapsed, 2)
        lib.write_status(song_id, status)
        log.info("Song %s: stage %s done in %.1f s", song_id, stage, elapsed)

    status = lib.read_status(song_id)
    status.state = "done"
    status.stage = None
    status.message = "Processing complete"
    status.progress = 1.0
    lib.write_status(song_id, status)

    with _lock:
        _running_id = None


def _worker() -> None:
    log.info("Job worker started")
    while True:
        job = _job_queue.get()
        try:
            _run_job(job)
        except Exception:
            log.exception("Unhandled error in worker for song %s", job.song_id)
        finally:
            _job_queue.task_done()


def start_worker() -> None:
    t = threading.Thread(target=_worker, daemon=True, name="job-worker")
    t.start()
    log.info("Background job worker thread started")


# ---------------------------------------------------------------------------
# Resume on server restart
# ---------------------------------------------------------------------------

def resume_incomplete_jobs() -> None:
    """Re-queue any songs that were 'running' or 'queued' when the server stopped."""
    for song_id in lib.list_songs():
        try:
            status = lib.read_status(song_id)
        except Exception:
            continue
        if status.state in ("running", "queued"):
            log.info("Resuming incomplete job for song %s", song_id)
            from_stage = status.stage or "prepare"
            enqueue(song_id, from_stage=from_stage)
