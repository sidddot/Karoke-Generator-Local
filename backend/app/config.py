"""Application configuration: paths, model names, device detection."""
from __future__ import annotations

import shutil
from pathlib import Path

import torch

# ---------------------------------------------------------------------------
# Repository-relative paths (resolved from this file's location)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent          # backend/app/
_BACKEND = _HERE.parent                # backend/
_ROOT = _BACKEND.parent               # local-karaoke/

LIBRARY_DIR: Path = _ROOT / "data" / "library"
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Audio separation models
# VERIFIED: run `audio-separator --list_models` to confirm names.
# ---------------------------------------------------------------------------
DEFAULT_SEPARATION_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
KARAOKE_SEPARATION_MODEL = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
MODEL_CACHE_DIR = Path.home() / ".cache" / "audio-separator"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Whisper / WhisperX settings
# ---------------------------------------------------------------------------
# CPU: use small to keep memory and time manageable.
# GPU: large-v2 by default; large-v3 is a config option.
WHISPER_MODEL_GPU = "large-v2"
WHISPER_MODEL_CPU = "small"

# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

def detect_device() -> str:
    """Return 'cuda' if a CUDA GPU is available, else 'cpu'."""
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


DEVICE: str = detect_device()

# ---------------------------------------------------------------------------
# Tool presence helpers (called at startup)
# ---------------------------------------------------------------------------

def ffmpeg_present() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_present() -> bool:
    return shutil.which("ffprobe") is not None


# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
MAX_FILE_BYTES = 500 * 1024 * 1024   # 500 MB
MAX_DURATION_SEC = 12 * 60           # 12 minutes

ALLOWED_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".mp4", ".mkv",
}
