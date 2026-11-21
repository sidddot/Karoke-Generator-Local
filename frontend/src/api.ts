/** Typed API client for the KarokeGen backend. */

export interface SongSettings {
  separation_model: string
  whisper_model: string
}

export interface SongMeta {
  id: string
  title: string
  artist: string
  album: string | null
  duration_sec: number
  language: string | null
  created_at: string
  source_filename: string
  settings: SongSettings
}

export interface SongStatus {
  state: 'queued' | 'running' | 'done' | 'failed'
  stage: 'prepare' | 'separate' | 'lyrics' | 'align' | 'finalize' | 'video' | null
  progress: number
  message: string
  error: string | null
  device: string
  timings_sec: Record<string, number>
}

export interface SongDetail {
  meta: SongMeta
  status: SongStatus
}

export interface WordTiming {
  w: string
  s: number
  e: number
  score: number | null
}

export interface LyricLine {
  start: number
  end: number
  text: string
  words: WordTiming[]
}

export interface Lyrics {
  version: number
  language: string
  source: 'lrclib-synced' | 'whisper' | 'manual-lrc' | 'manual-plain'
  alignment: 'forced' | 'transcribed' | 'line-only'
  quality: { mean_word_score: number | null; low_confidence: boolean }
  lines: LyricLine[]
}

export interface HealthResponse {
  ok: boolean
  device: string
  ffmpeg: boolean
  ffprobe: boolean
  models_cached: string[]
}

// ---------------------------------------------------------------------------
// Base fetch with error normalisation
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(path, init)
  if (!r.ok) {
    let code = 'http_error'
    let msg = r.statusText
    try {
      const body = await r.json()
      code = body?.error?.code ?? code
      msg = body?.error?.message ?? msg
    } catch (_) { /* ignore */ }
    throw new ApiError(code, msg, r.status)
  }
  if (r.status === 204) return undefined as T
  return r.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

export const api = {
  health: (): Promise<HealthResponse> =>
    apiFetch('/api/health'),

  listSongs: (): Promise<SongDetail[]> =>
    apiFetch('/api/songs'),

  getSong: (id: string): Promise<SongDetail> =>
    apiFetch(`/api/songs/${id}`),

  uploadSong: (form: FormData): Promise<{ id: string }> =>
    apiFetch('/api/songs', { method: 'POST', body: form }),

  getLyrics: (id: string): Promise<Lyrics> =>
    apiFetch(`/api/songs/${id}/lyrics`),

  putLyrics: (id: string, format: 'lrc' | 'plain', text: string): Promise<unknown> =>
    apiFetch(`/api/songs/${id}/lyrics`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, text }),
    }),

  reprocess: (id: string, from_stage: string): Promise<unknown> =>
    apiFetch(`/api/songs/${id}/reprocess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_stage }),
    }),

  deleteSong: (id: string): Promise<void> =>
    apiFetch(`/api/songs/${id}`, { method: 'DELETE' }),

  addFromYoutube: (params: {
    url: string
    title: string
    artist: string
    album?: string
    language?: string
  }): Promise<{ id: string }> =>
    apiFetch('/api/songs/from-youtube', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),
}

export { ApiError }
