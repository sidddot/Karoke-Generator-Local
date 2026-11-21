import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type SongDetail } from '../api'

interface SongCardProps {
  song: SongDetail
  onRefresh: () => void
}

function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function SongCard({ song, onRefresh }: SongCardProps) {
  const { meta, status } = song
  const [busy, setBusy] = useState(false)
  const [errorText, setErrorText] = useState<string | null>(null)

  const isRunning = status.state === 'running' || status.state === 'queued'

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${meta.title}"?`)) return
    setBusy(true)
    setErrorText(null)
    try {
      await api.deleteSong(meta.id)
      onRefresh()
    } catch (e) {
      setErrorText(`Delete failed: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  const handleRerunLyrics = async () => {
    setBusy(true)
    setErrorText(null)
    try {
      await api.reprocess(meta.id, 'lyrics')
      onRefresh()
    } catch (e) {
      setErrorText(`Rerun lyrics failed: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`song-card state-${status.state}`}>
      <div className="card-header">
        <div className="title-row">
          <h4 className="song-title">{meta.title}</h4>
          <span className={`status-badge ${status.state}`}>
            {status.state.toUpperCase()}
          </span>
        </div>
        <div className="song-artist">
          {meta.artist} {meta.album ? `• ${meta.album}` : ''}
        </div>
      </div>

      <div className="card-body">
        <div className="song-info">
          <span>Duration: {formatDuration(meta.duration_sec)}</span>
          {meta.language && <span>Lang: {meta.language}</span>}
          <span>Device: {status.device}</span>
        </div>

        {isRunning && (
          <div className="progress-area">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${Math.round(status.progress * 100)}%` }}
              />
            </div>
            <div className="status-msg">{status.message || 'Processing…'}</div>
          </div>
        )}

        {status.state === 'failed' && (
          <div className="error-box">
            Failed: {status.error || status.message}
          </div>
        )}

        {errorText && <div className="error-box">{errorText}</div>}
      </div>

      <div className="card-footer">
        {status.state === 'done' && (
          <Link to={`/play/${meta.id}`} className="btn btn-play">
            ▶ Play Karaoke
          </Link>
        )}

        {status.state === 'done' && (
          <a
            className="btn btn-secondary"
            href={`/audio/${meta.id}/karaoke.mp4`}
            download={`${meta.title}-karaoke.mp4`}
          >
            Download video
          </a>
        )}

        {status.state === 'done' && (
          <a
            className="btn btn-secondary"
            href={`/audio/${meta.id}/instrumental.mp3`}
            download={`${meta.title}-instrumental.mp3`}
            title="Download Instrumental MP3"
          >
            Download MP3
          </a>
        )}

        <button
          className="btn btn-secondary"
          onClick={handleRerunLyrics}
          disabled={busy || isRunning}
          title="Re-run from lyrics stage"
        >
          Re-run Lyrics
        </button>

        <button
          className="btn btn-danger"
          onClick={handleDelete}
          disabled={busy || isRunning}
          title="Delete song"
        >
          Delete
        </button>
      </div>

      <style>{`
        .song-card {
          background: #181820;
          border: 1px solid #282835;
          border-radius: 8px;
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          transition: border-color 0.2s;
        }
        .song-card:hover {
          border-color: #3b3b4f;
        }
        .card-header .title-row {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 0.5rem;
        }
        .song-title {
          font-size: 1.1rem;
          font-weight: 600;
          color: #f0f0f5;
          margin: 0;
        }
        .song-artist {
          font-size: 0.85rem;
          color: #9999aa;
          margin-top: 0.2rem;
        }
        .status-badge {
          font-size: 0.7rem;
          font-weight: 700;
          letter-spacing: 0.05em;
          padding: 0.2rem 0.55rem;
          border-radius: 12px;
          text-transform: uppercase;
        }
        .status-badge.queued {
          background: #1e293b;
          color: #94a3b8;
        }
        .status-badge.running {
          background: #3b280c;
          color: #fbbf24;
          animation: pulse 1.5s infinite;
        }
        .status-badge.done {
          background: #0f3721;
          color: #4ade80;
        }
        .status-badge.failed {
          background: #3c1418;
          color: #f87171;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
        .song-info {
          display: flex;
          gap: 1rem;
          font-size: 0.75rem;
          color: #777788;
        }
        .progress-area {
          margin-top: 0.5rem;
        }
        .progress-bar {
          height: 6px;
          background: #232330;
          border-radius: 3px;
          overflow: hidden;
        }
        .progress-fill {
          height: 100%;
          background: #a78bfa;
          transition: width 0.3s ease;
        }
        .status-msg {
          font-size: 0.75rem;
          color: #a78bfa;
          margin-top: 0.35rem;
        }
        .error-box {
          background: #3a1518;
          border: 1px solid #dc2626;
          color: #fca5a5;
          padding: 0.4rem 0.6rem;
          border-radius: 4px;
          font-size: 0.75rem;
        }
        .card-footer {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.5rem;
          margin-top: auto;
          padding-top: 0.75rem;
          border-top: 1px solid #232330;
        }
        .btn {
          border: none;
          padding: 0.45rem 0.75rem;
          border-radius: 6px;
          font-size: 0.8rem;
          font-weight: 500;
          cursor: pointer;
          transition: background 0.15s;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          white-space: nowrap;
          text-decoration: none;
        }
        .btn-play {
          background: #10b981;
          color: white;
          text-decoration: none;
        }
        .btn-play:hover {
          background: #059669;
        }
        .btn-secondary {
          background: #2a2a3a;
          color: #d1d1e0;
        }
        .btn-secondary:hover:not(:disabled) {
          background: #3a3a50;
        }
        .btn-danger {
          background: #2b1c20;
          color: #f87171;
          margin-left: auto;
        }
        .btn-danger:hover:not(:disabled) {
          background: #471d24;
        }
        .btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  )
}
