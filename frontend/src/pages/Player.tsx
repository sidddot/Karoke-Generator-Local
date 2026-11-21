import React, { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api, type SongDetail, type Lyrics } from '../api'
import { AudioEngine } from '../audio/engine'
import type { RemovalMode } from '../audio/engine'
import { findLine } from '../lyrics/sync'
import LyricsView from '../components/LyricsView'
import Controls from '../components/Controls'

export default function Player() {
  const { id } = useParams<{ id: string }>()

  const [song, setSong] = useState<SongDetail | null>(null)
  const [lyrics, setLyrics] = useState<Lyrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [decodeError, setDecodeError] = useState<string | null>(null)

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [activeLineIdx, setActiveLineIdx] = useState(-1)

  const [guideVolume, setGuideVolume] = useState(0.15) // quiet guide vocals by default
  const [instrumentalVolume, setInstrumentalVolume] = useState(1.0) // default full volume
  const [removalMode, setRemovalMode] = useState<RemovalMode>('both')

  const [lyricOffsetMs, setLyricOffsetMs] = useState(0)

  const engineRef = useRef<AudioEngine | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const playerContainerRef = useRef<HTMLDivElement>(null)

  // Load offset from localStorage for this song
  useEffect(() => {
    if (!id) return
    const saved = localStorage.getItem(`karaoke_offset_${id}`)
    if (saved) {
      const val = parseInt(saved, 10)
      if (!isNaN(val)) setLyricOffsetMs(val)
    }
  }, [id])

  // Save offset to localStorage whenever changed
  const updateOffset = useCallback((ms: number) => {
    setLyricOffsetMs(ms)
    if (id) localStorage.setItem(`karaoke_offset_${id}`, ms.toString())
    if (engineRef.current) engineRef.current.setUserOffsetMs(ms)
  }, [id])

  // Initialize engine and load song data
  useEffect(() => {
    if (!id) return

    let cancelled = false
    const engine = new AudioEngine()
    engineRef.current = engine

    setLoading(true)
    setDecodeError(null)

    Promise.all([
      api.getSong(id),
      api.getLyrics(id),
      engine.load(id),
    ])
      .then(([songData, lyricsData]) => {
        if (cancelled) return
        setSong(songData)
        setLyrics(lyricsData)
        setDuration(engine.getDuration() || songData.meta.duration_sec)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        console.error('Player load error:', err)
        setDecodeError(String(err))
        setLoading(false)
      })

    return () => {
      cancelled = true
      engine.destroy()
    }
  }, [id])

  // Sync engine state
  useEffect(() => {
    const engine = engineRef.current
    if (!engine) return

    engine.setGuideVolume(guideVolume)
    engine.setInstrumentalVolume(instrumentalVolume)
    engine.setUserOffsetMs(lyricOffsetMs)
    engine.setRemovalMode(removalMode)
  }, [guideVolume, instrumentalVolume, lyricOffsetMs, removalMode])

  // Sync removal mode
  useEffect(() => {
    const engine = engineRef.current
    if (!engine) return
    engine.setRemovalMode(removalMode as any)
  }, [removalMode])
  useEffect(() => {
    const engine = engineRef.current
    if (!engine) return

    engine.setGuideVolume(guideVolume)
    engine.setInstrumentalVolume(instrumentalVolume)
    engine.setUserOffsetMs(lyricOffsetMs)
    engine.setRemovalMode(removalMode)
  }, [guideVolume, instrumentalVolume, lyricOffsetMs, removalMode])

  // Real-time animation loop for word sync
  useEffect(() => {
    const updateLoop = () => {
      const engine = engineRef.current
      if (engine) {
        const t = engine.getTime()
        setCurrentTime(t)

        if (lyrics && lyrics.lines) {
          const lIdx = findLine(lyrics.lines, t)
          setActiveLineIdx(lIdx)
        }
      }
      animFrameRef.current = requestAnimationFrame(updateLoop)
    }

    animFrameRef.current = requestAnimationFrame(updateLoop)
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [lyrics])

  // Playback control handlers
  const handleTogglePlay = useCallback(async () => {
    const engine = engineRef.current
    if (!engine) return

    if (engine.isPlaying()) {
      engine.pause()
      setIsPlaying(false)
    } else {
      await engine.play()
      setIsPlaying(true)
    }
  }, [])

  const handleSeek = useCallback((timeSec: number) => {
    const engine = engineRef.current
    if (!engine) return
    engine.seek(timeSec)
    setCurrentTime(timeSec)
  }, [])

  const handleToggleFullscreen = () => {
    if (!playerContainerRef.current) return
    if (!document.fullscreenElement) {
      playerContainerRef.current.requestFullscreen().catch(console.error)
    } else {
      document.exitFullscreen().catch(console.error)
    }
  }

  // Reprocess button action for low-confidence warnings
  const handleReprocessTranscription = async () => {
    if (!id) return
    try {
      await api.reprocess(id, 'align')
      window.location.href = '/'
    } catch (err) {
      alert(`Reprocess failed: ${err}`)
    }
  }

  // Keyboard shortcuts (Space = play/pause, Left/Right = seek 5s, [ and ] = offset -50/+50 ms)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['input', 'textarea'].includes((e.target as HTMLElement).tagName.toLowerCase())) {
        return
      }

      if (e.code === 'Space') {
        e.preventDefault()
        handleTogglePlay()
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault()
        handleSeek(Math.max(0, currentTime - 5))
      } else if (e.code === 'ArrowRight') {
        e.preventDefault()
        handleSeek(Math.min(duration, currentTime + 5))
      } else if (e.key === '[') {
        e.preventDefault()
        updateOffset(Math.max(-2000, lyricOffsetMs - 50))
      } else if (e.key === ']') {
        e.preventDefault()
        updateOffset(Math.min(2000, lyricOffsetMs + 50))
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleTogglePlay, handleSeek, currentTime, duration, lyricOffsetMs, updateOffset])

  if (loading) {
    return (
      <div className="player-loading">
        <div className="spinner" />
        <h2>Loading karaoke tracks…</h2>
        <p>Decoding high-fidelity instrumental and vocal audio buffers</p>
        <style>{`
          .player-loading {
            text-align: center;
            padding: 6rem 1rem;
            color: #a1a1aa;
          }
          .spinner {
            width: 48px;
            height: 48px;
            border: 4px solid #2e2e3d;
            border-top-color: #ec4899;
            border-radius: 50%;
            margin: 0 auto 1.5rem;
            animation: spin 1s linear infinite;
          }
          @keyframes spin { to { transform: rotate(360deg); } }
        `}</style>
      </div>
    )
  }

  if (decodeError) {
    return (
      <div className="player-error">
        <h2>Audio Decode Error</h2>
        <p className="err-msg">{decodeError}</p>
        <p>The browser could not decode the audio file stems. Ensure FFmpeg is present.</p>
        <Link to="/" className="back-btn">← Back to Library</Link>
        <style>{`
          .player-error {
            max-width: 600px;
            margin: 4rem auto;
            text-align: center;
            padding: 2rem;
            background: #251215;
            border: 1px solid #ef4444;
            border-radius: 8px;
          }
          .err-msg { color: #fca5a5; margin: 1rem 0; font-family: monospace; }
          .back-btn { display: inline-block; margin-top: 1.5rem; color: #a78bfa; }
        `}</style>
      </div>
    )
  }

  const showWarning = lyrics?.quality?.low_confidence || lyrics?.alignment === 'line-only'

  return (
    <div className="player-page" ref={playerContainerRef}>
      {/* Top Navigation & Info */}
      <div className="player-top-bar">
        <Link to="/" className="back-link">← Library</Link>
        <div className="track-title-info">
          <h3>{song?.meta.title}</h3>
          <span>{song?.meta.artist}</span>
        </div>
        <div className="format-indicator">
          <span>Source: {lyrics?.source}</span>
          <span>•</span>
          <span>Align: {lyrics?.alignment}</span>
          {id && (
            <>
              <span>•</span>
              <a className="video-dl" href={`/audio/${id}/karaoke.mp4`} download={`${song?.meta.title || 'song'}-karaoke.mp4`}>
                Download video
              </a>
              <span>•</span>
              <a className="video-dl" href={`/audio/${id}/instrumental.mp3`} download={`${song?.meta.title || 'song'}-instrumental.mp3`} title="Download Instrumental MP3">
                Download MP3
              </a>
            </>
          )}
        </div>
      </div>

      {/* Warning banner for low confidence or line-only alignment */}
      {showWarning && (
        <div className="quality-warning-banner">
          <span>
            ⚠️ Low timing confidence or line-only sync. Word timing may be approximate.
          </span>
          <button className="reprocess-banner-btn" onClick={handleReprocessTranscription}>
            Try transcription mode
          </button>
        </div>
      )}

      {/* Main Center Lyrics View */}
      <LyricsView
        lines={lyrics?.lines || []}
        currentTime={currentTime}
        activeLineIdx={activeLineIdx}
        onSeek={handleSeek}
      />

      {/* Bottom Audio & Lyric Controls */}
      <Controls
        removalMode={removalMode}
        onRemovalChange={setRemovalMode}
        isPlaying={isPlaying}
        currentTime={currentTime}
        duration={duration}
        guideVolume={guideVolume}
        instrumentalVolume={instrumentalVolume}
        lyricOffsetMs={lyricOffsetMs}
        onTogglePlay={handleTogglePlay}
        onSeek={handleSeek}
        onGuideVolumeChange={setGuideVolume}
        onInstrumentalVolumeChange={setInstrumentalVolume}
        onLyricOffsetChange={updateOffset}
        onToggleFullscreen={handleToggleFullscreen}
      />

      <style>{`
        .player-page {
          max-width: 950px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
        }
        .player-top-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1.25rem;
          padding-bottom: 0.75rem;
          border-bottom: 1px solid #232330;
        }
        .back-link {
          color: #a78bfa;
          font-weight: 500;
          font-size: 0.9rem;
        }
        .track-title-info {
          text-align: center;
        }
        .track-title-info h3 {
          margin: 0;
          color: #f4f4f5;
          font-size: 1.2rem;
        }
        .track-title-info span {
          color: #9999aa;
          font-size: 0.85rem;
        }
        .format-indicator {
          display: flex;
          gap: 0.4rem;
          font-size: 0.75rem;
          color: #71717a;
          align-items: center;
        }
        .video-dl {
          color: #a78bfa;
        }
        .quality-warning-banner {
          background: #3b280c;
          border: 1px solid #f59e0b;
          color: #fef3c7;
          padding: 0.65rem 1rem;
          border-radius: 8px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
          font-size: 0.85rem;
        }
        .reprocess-banner-btn {
          background: #f59e0b;
          color: #1c1917;
          border: none;
          padding: 0.35rem 0.75rem;
          border-radius: 4px;
          font-weight: 600;
          font-size: 0.8rem;
          cursor: pointer;
        }
        .reprocess-banner-btn:hover {
          background: #d97706;
        }
      `}</style>
    </div>
  )
}
