"""Stage 2: separate — neural vocal separation via audio-separator."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

from app import library as lib
from app.config import (
    DEFAULT_SEPARATION_MODEL,
    KARAOKE_SEPARATION_MODEL,
    DEVICE,
    MODEL_CACHE_DIR,
)

log = logging.getLogger(__name__)

FFMPEG = "ffmpeg"


def _run_cli_separation(
    audio_path: Path,
    out_dir: Path,
    model_name: str,
) -> None:
    """Fallback CLI separation call if Python API fails."""
    cmd = [
        "audio-separator",
        str(audio_path),
        "--model_filename", model_name,
        "--output_dir", str(out_dir),
        "--output_format", "FLAC",
        "--model_file_dir", str(MODEL_CACHE_DIR),
    ]
    log.info("Running audio-separator CLI: %s", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"audio-separator CLI failed: {res.stderr[-1000:]}")


def _run_python_separation(
    audio_path: Path,
    out_dir: Path,
    model_name: str,
) -> None:
    """Run separation via audio-separator Python API."""
    from audio_separator.separator import Separator

    separator = Separator(
        model_file_dir=str(MODEL_CACHE_DIR),
        output_dir=str(out_dir),
        output_format="FLAC",
        sample_rate=44100,
    )
    separator.load_model(model_filename=model_name)
    separator.separate(str(audio_path))


def _find_stem(directory: Path, keywords: List[str]) -> Path | None:
    """Find a file in directory matching any of the given keywords."""
    for file in directory.iterdir():
        if not file.is_file():
            continue
        lower_name = file.name.lower()
        if any(kw in lower_name for kw in keywords):
            return file
    return None


def _create_vocals_16k(vocals_flac: Path, out_wav: Path) -> None:
    """Downmix/resample vocals to 16 kHz mono WAV for WhisperX."""
    tmp_wav = out_wav.with_suffix(".tmp.wav")
    cmd = [
        FFMPEG, "-y",
        "-i", str(vocals_flac),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(tmp_wav),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg 16k resample failed: {res.stderr[-500:]}")
    os.replace(tmp_wav, out_wav)


def _create_mp3_copy(src_audio: Path, out_mp3: Path) -> None:
    """Create 320 kbps MP3 copy for browser fallback."""
    tmp_mp3 = out_mp3.with_suffix(".tmp.mp3")
    cmd = [
        FFMPEG, "-y",
        "-i", str(src_audio),
        "-b:a", "320k",
        str(tmp_mp3),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        os.replace(tmp_mp3, out_mp3)


def run(song_id: str) -> None:
    """Execute vocal separation and produce instrumental/vocal stems, then split vocals into lead/backing."""
    inst_flac = lib.instrumental_path(song_id)
    voc_flac = lib.vocals_path(song_id)
    voc_16k = lib.vocals_16k_path(song_id)
    lead_flac = lib.vocals_lead_path(song_id)
    backing_flac = lib.vocals_backing_path(song_id)

    # 1. Idempotency check — skip if all 5 outputs already exist
    if (
        inst_flac.exists() and inst_flac.stat().st_size > 0
        and voc_flac.exists() and voc_flac.stat().st_size > 0
        and voc_16k.exists() and voc_16k.stat().st_size > 0
        and lead_flac.exists() and lead_flac.stat().st_size > 0
        and backing_flac.exists() and backing_flac.stat().st_size > 0
    ):
        log.info("separate: %s stems already exist, skipping", song_id)
        return

    prep_wav = lib.prep_wav_path(song_id)
    if not prep_wav.exists() or prep_wav.stat().st_size == 0:
        raise RuntimeError(f"Prepared WAV not found: {prep_wav}")

    meta = lib.read_meta(song_id)
    model_name = meta.settings.separation_model or DEFAULT_SEPARATION_MODEL

    log.info("separate: running on %s (model=%s, device=%s)", song_id, model_name, DEVICE)

    # Use a scratch output folder inside work/
    temp_dir = lib.work_dir(song_id) / "sep_temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        try:
            _run_python_separation(prep_wav, temp_dir, model_name)
        except Exception as exc:
            log.warning("Python separation failed (%s), falling back to CLI", exc)
            _run_cli_separation(prep_wav, temp_dir, model_name)

        # Identify stems
        voc_found = _find_stem(temp_dir, ["vocal", "(vocals)"])
        inst_found = _find_stem(temp_dir, ["instrumental", "(instrumental)", "no_vocals", "other"])

        if not voc_found or not inst_found:
            all_files = [f.name for f in temp_dir.iterdir()]
            raise RuntimeError(f"Separation failed to output both stems. Found: {all_files}")

        # Atomic move to final destinations
        tmp_voc = voc_flac.with_suffix(".tmp.flac")
        tmp_inst = inst_flac.with_suffix(".tmp.flac")

        shutil.move(str(voc_found), str(tmp_voc))
        shutil.move(str(inst_found), str(tmp_inst))

        os.replace(tmp_voc, voc_flac)
        os.replace(tmp_inst, inst_flac)

        # Resample vocals to 16 kHz mono WAV
        _create_vocals_16k(voc_flac, voc_16k)

        # Generate MP3 copies for browser compatibility
        _create_mp3_copy(voc_flac, voc_flac.with_suffix(".mp3"))
        _create_mp3_copy(inst_flac, inst_flac.with_suffix(".mp3"))

        log.info("separate: completed successfully for %s", song_id)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Pass 2: split vocals.flac → vocals_lead.flac + vocals_backing.flac
    # Uses KARAOKE_SEPARATION_MODEL which separates lead vs. backing vocals.
    # lead    = main/solo vocalist  (maps to primary gender singer)
    # backing = harmonies / chorus  (the other voice or background singers)
    # -----------------------------------------------------------------------
    _run_vocal_split(song_id, voc_flac)


def _run_vocal_split(song_id: str, voc_flac: Path) -> None:
    """Second-pass: split vocals.flac into lead + backing stems."""
    lead_flac = lib.vocals_lead_path(song_id)
    backing_flac = lib.vocals_backing_path(song_id)

    if (lead_flac.exists() and lead_flac.stat().st_size > 0
            and backing_flac.exists() and backing_flac.stat().st_size > 0):
        log.info("separate: vocal split already exists for %s, skipping", song_id)
        return

    temp_dir2 = lib.work_dir(song_id) / "voc_split_temp"
    if temp_dir2.exists():
        shutil.rmtree(temp_dir2)
    temp_dir2.mkdir(parents=True, exist_ok=True)

    try:
        try:
            _run_python_separation(voc_flac, temp_dir2, KARAOKE_SEPARATION_MODEL)
        except Exception as exc:
            log.warning("Python vocal split failed (%s), falling back to CLI", exc)
            _run_cli_separation(voc_flac, temp_dir2, KARAOKE_SEPARATION_MODEL)

        # Karaoke model outputs lead vocals and backing/karaoke track
        lead_found = _find_stem(temp_dir2, ["lead", "vocal", "(vocals)"])
        backing_found = _find_stem(temp_dir2, ["instrumental", "backing", "no_lead", "other", "karaoke"])

        if not lead_found or not backing_found:
            all_files = [f.name for f in temp_dir2.iterdir()]
            log.warning("vocal split incomplete (%s) — using full vocals as both stems", all_files)
            shutil.copy2(voc_flac, lead_flac)
            shutil.copy2(voc_flac, backing_flac)
            return

        tmp_lead = lead_flac.with_suffix(".tmp.flac")
        tmp_backing = backing_flac.with_suffix(".tmp.flac")
        shutil.move(str(lead_found), str(tmp_lead))
        shutil.move(str(backing_found), str(tmp_backing))
        os.replace(tmp_lead, lead_flac)
        os.replace(tmp_backing, backing_flac)

        _create_mp3_copy(lead_flac, lead_flac.with_suffix(".mp3"))
        _create_mp3_copy(backing_flac, backing_flac.with_suffix(".mp3"))

        log.info("separate: vocal split completed for %s", song_id)

    except Exception as exc:
        log.warning("vocal split failed (%s) — using full vocals as fallback", exc)
        shutil.copy2(voc_flac, lead_flac)
        shutil.copy2(voc_flac, backing_flac)

    finally:
        shutil.rmtree(temp_dir2, ignore_errors=True)
