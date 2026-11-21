import { useEffect, useState, useCallback, useRef } from 'react'
import { api, type SongDetail, type HealthResponse } from '../api'
import UploadForm from '../components/UploadForm'
import SongCard from '../components/SongCard'

export default function Library() {
  const [songs, setSongs] = useState<SongDetail[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const pollTimerRef = useRef<number | null>(null)

  const fetchSongs = useCallback(async () => {
    try {
      const list = await api.listSongs()
      setSongs(list)
    } catch (err) {
      console.error('Failed to fetch songs:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial health & song fetch
  useEffect(() => {
    api.health().then(setHealth).catch(console.error)
    fetchSongs()
  }, [fetchSongs])

  // Polling every 1.5 seconds while any song is queued or running
  useEffect(() => {
    const hasActiveJobs = songs.some(
      (s) => s.status.state === 'running' || s.status.state === 'queued'
    )

    if (hasActiveJobs) {
      pollTimerRef.current = window.setInterval(fetchSongs, 1500)
    } else if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [songs, fetchSongs])

  return (
    <div className="library-container">
      <div className="header-bar">
        <h2>KarokeGen Library</h2>
        {health && (
          <div className="health-badge">
            <span className={`indicator ${health.ok ? 'ok' : 'warn'}`} />
            <span>Device: {health.device.toUpperCase()}</span>
            <span>•</span>
            <span>FFmpeg: {health.ffmpeg ? 'Ready' : 'Missing'}</span>
          </div>
        )}
      </div>

      <UploadForm onUploaded={fetchSongs} />

      <section className="song-grid-section">
        <div className="section-title-row">
          <h3>Your Songs ({songs.length})</h3>
          <button className="refresh-btn" onClick={fetchSongs}>
            ↻ Refresh
          </button>
        </div>

        {loading ? (
          <div className="loading-state">Loading your library…</div>
        ) : songs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🎵</div>
            <p>No songs added yet.</p>
            <p className="subtext">Upload an audio or video file above to get started!</p>
          </div>
        ) : (
          <div className="song-grid">
            {songs.map((song) => (
              <SongCard key={song.meta.id} song={song} onRefresh={fetchSongs} />
            ))}
          </div>
        )}
      </section>

      <style>{`
        .library-container {
          max-width: 1320px;
          width: 95%;
          margin: 0 auto;
        }
        .header-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }
        .header-bar h2 {
          color: #f3f3f8;
          font-size: 1.6rem;
        }
        .health-badge {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background: #181822;
          border: 1px solid #282835;
          padding: 0.35rem 0.75rem;
          border-radius: 20px;
          font-size: 0.75rem;
          color: #9494a8;
        }
        .indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .indicator.ok {
          background: #10b981;
          box-shadow: 0 0 6px #10b981;
        }
        .indicator.warn {
          background: #f59e0b;
        }
        .section-title-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .section-title-row h3 {
          font-size: 1.15rem;
          color: #c4c4d4;
        }
        .refresh-btn {
          background: transparent;
          border: 1px solid #363648;
          color: #a4a4b8;
          padding: 0.3rem 0.7rem;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.8rem;
          transition: all 0.2s;
        }
        .refresh-btn:hover {
          color: #fff;
          border-color: #555570;
        }
        .song-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 1.25rem;
        }
        .loading-state, .empty-state {
          text-align: center;
          padding: 3rem 1rem;
          background: #14141c;
          border-radius: 8px;
          border: 1px dashed #2a2a38;
          color: #888899;
        }
        .empty-icon {
          font-size: 2.5rem;
          margin-bottom: 0.5rem;
        }
        .empty-state .subtext {
          font-size: 0.85rem;
          color: #666677;
          margin-top: 0.25rem;
        }
      `}</style>
    </div>
  )
}
