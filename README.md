# Local Karaoke

A personal karaoke web app that runs entirely on one Windows 11 PC. Upload a local audio or video file; get an instrumental track, a vocals guide track, and word-timed lyrics synced in the browser with word-by-word highlighting.

---

## 1. System Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | 3.10.0 verified |
| Node.js | 18+ | 24.10.0 verified |
| ffmpeg & ffprobe | Recent build | Must be accessible on PATH |
| NVIDIA GPU (optional) | CUDA 12+ | MX250 detected; automatically falls back to CPU if GPU memory is constrained |

---

## 2. Installation & Setup

### A. Backend Setup

```powershell
cd local-karaoke\backend

# Activate virtual environment
.venv\Scripts\Activate.ps1

# All dependencies (FastAPI, Uvicorn, audio-separator, whisperx) are pinned:
pip install -r requirements.txt
```

### B. Frontend Setup

```powershell
cd local-karaoke\frontend
npm install
```

---

## 3. Running the Application

Open **two** PowerShell terminals:

**Terminal 1 — Backend API Server:**
```powershell
cd local-karaoke\backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend Dev Server:**
```powershell
cd local-karaoke\frontend
npm run dev
```

Open your browser to: **http://localhost:5173**

---

## 4. Repository Layout & Architecture

```
local-karaoke/
  backend/
    app/
      main.py            FastAPI application, routes, and /audio static mount
      config.py          paths, model names, device detection
      schemas.py         Pydantic v2 data models for meta, status, and lyrics
      library.py         atomic song folder operations (NTFS safe)
      jobs.py            single background worker thread and pipeline runner
      pipeline/
        prepare.py       ffprobe duration probing and ffmpeg 44.1kHz stereo conversion
        separate.py      audio-separator wrapper with BS-RoFormer and stems extraction
        lrclib.py        LRCLIB client, LRC parser, and fuzzy title matcher
        align.py         WhisperX forced alignment with line-only fallback
        transcribe.py    WhisperX fallback transcription (condition_on_previous_text=False)
        finalize.py      word interpolation, monotonic enforcement, and quality scoring
    requirements.txt     pinned working dependencies
  frontend/
    src/
      api.ts             strongly-typed API client
      pages/
        Library.tsx      song management, upload form, and live job polling
        Player.tsx       karaoke player with real-time lyric highlighting
      audio/
        engine.ts        Web Audio API dual-track playback engine
      lyrics/
        sync.ts          pure binary search lyric lookup functions
      components/
        UploadForm.tsx   drag-and-drop / file selector and metadata input
        SongCard.tsx     song status badge, stage progress, and actions
        LyricsView.tsx   animated word-by-word text gradient rendering
        Controls.tsx     seek bar, guide vocal volume, instrumental volume, offset
  scripts/
    smoke.py             end-to-end synthetic tone test runner
  data/library/<id>/     runtime song data directory
```

---

## 5. Keyboard Shortcuts in Karaoke Player

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `Left Arrow` | Rewind 5 seconds |
| `Right Arrow` | Forward 5 seconds |
| `[` | Shift lyric timing earlier by 50 ms |
| `]` | Shift lyric timing later by 50 ms |

---

## 6. Build Batches Status

| Batch | Description | Implementation Status |
|-------|-------------|-----------------------|
| 0 | Environment, scaffold, health endpoint, Vite app | ✅ Complete |
| 1 | Data model, atomic library, job runner | ✅ Complete |
| 2 | Prepare stage (FFmpeg) and separation stage (BS-RoFormer) | ✅ Complete |
| 3 | LRCLIB client, LRC parser, forced alignment, finalize | ✅ Complete |
| 4 | Transcription fallback and manual lyrics update | ✅ Complete |
| 5 | Frontend library page, upload form, song cards, polling | ✅ Complete |
| 6 | Web Audio dual-track engine, player UI, synchronized lyrics | ✅ Complete |
| 7 | End-to-end smoke test script and hardening | ✅ Complete |
