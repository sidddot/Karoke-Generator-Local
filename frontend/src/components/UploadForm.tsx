import React, { useState, useRef } from 'react'
import { api, ApiError } from '../api'

interface UploadFormProps {
  onUploaded: (songId: string) => void
}

const ALLOWED_EXTS = ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.mp4', '.mkv']
const MAX_BYTES = 500 * 1024 * 1024

type Tab = 'file' | 'youtube'

export default function UploadForm({ onUploaded }: UploadFormProps) {
  const [tab, setTab] = useState<Tab>('file')

  // File upload state
  const [file, setFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Shared metadata
  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')
  const [album, setAlbum] = useState('')
  const [language, setLanguage] = useState('')

  // YouTube state
  const [ytUrl, setYtUrl] = useState('')

  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorMsg(null)
    const selected = e.target.files?.[0]
    if (!selected) { setFile(null); return }

    const ext = '.' + selected.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED_EXTS.includes(ext)) {
      setErrorMsg(`Unsupported file type '${ext}'. Supported: ${ALLOWED_EXTS.join(', ')}`)
      setFile(null)
      return
    }
    if (selected.size > MAX_BYTES) {
      setErrorMsg('File exceeds maximum size limit of 500 MB.')
      setFile(null)
      return
    }
    setFile(selected)
    if (!title) {
      const baseName = selected.name.replace(/\.[^/.]+$/, '')
      const parts = baseName.split(' - ')
      if (parts.length >= 2) {
        setArtist(parts[0].trim())
        setTitle(parts.slice(1).join(' - ').trim())
      } else {
        setTitle(baseName.trim())
      }
    }
  }

  const resetForm = () => {
    setFile(null); setTitle(''); setArtist(''); setAlbum(''); setLanguage(''); setYtUrl('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg(null)

    if (!title.trim() || !artist.trim()) {
      setErrorMsg('Title and artist are required.')
      return
    }

    if (tab === 'file') {
      if (!file) { setErrorMsg('Please select an audio or video file.'); return }
      setSubmitting(true)
      try {
        const form = new FormData()
        form.append('file', file)
        form.append('title', title.trim())
        form.append('artist', artist.trim())
        if (album.trim()) form.append('album', album.trim())
        if (language.trim()) form.append('language', language.trim().toLowerCase())
        const res = await api.uploadSong(form)
        resetForm()
        onUploaded(res.id)
      } catch (err) {
        setErrorMsg(err instanceof ApiError ? `[${err.code}] ${err.message}` : String(err))
      } finally {
        setSubmitting(false)
      }
    } else {
      if (!ytUrl.trim()) { setErrorMsg('Please enter a YouTube URL.'); return }
      if (!ytUrl.includes('youtube.com') && !ytUrl.includes('youtu.be')) {
        setErrorMsg('URL must be a YouTube link.')
        return
      }
      setSubmitting(true)
      try {
        const res = await api.addFromYoutube({
          url: ytUrl.trim(),
          title: title.trim(),
          artist: artist.trim(),
          album: album.trim() || undefined,
          language: language.trim().toLowerCase() || undefined,
        })
        resetForm()
        onUploaded(res.id)
      } catch (err) {
        setErrorMsg(err instanceof ApiError ? `[${err.code}] ${err.message}` : String(err))
      } finally {
        setSubmitting(false)
      }
    }
  }

  const isDisabled = submitting || (tab === 'file' ? !file : !ytUrl.trim())

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <h3>Add a Song</h3>

      {/* Tab switcher */}
      <div className="tab-row">
        <button type="button" className={`tab-btn${tab === 'file' ? ' active' : ''}`} onClick={() => { setTab('file'); setErrorMsg(null) }}>
          📁 Local File
        </button>
        <button type="button" className={`tab-btn${tab === 'youtube' ? ' active' : ''}`} onClick={() => { setTab('youtube'); setErrorMsg(null) }}>
          ▶ YouTube URL
        </button>
      </div>

      {errorMsg && <div className="form-error">{errorMsg}</div>}

      {tab === 'file' ? (
        <div className="form-group">
          <label>File (Audio or Video):</label>
          <input
            type="file"
            ref={fileInputRef}
            accept={ALLOWED_EXTS.join(',')}
            onChange={handleFileChange}
            disabled={submitting}
          />
          <span className="form-hint">Max 500 MB · mp3, wav, flac, m4a, ogg, mp4, mkv</span>
        </div>
      ) : (
        <div className="form-group">
          <label>YouTube URL:</label>
          <input
            type="url"
            value={ytUrl}
            onChange={(e) => setYtUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            disabled={submitting}
          />
          <span className="form-hint">Audio is downloaded server-side via yt-dlp</span>
        </div>
      )}

      <div className="form-row">
        <div className="form-group">
          <label>Title *</label>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Bohemian Rhapsody" disabled={submitting} required />
        </div>
        <div className="form-group">
          <label>Artist *</label>
          <input type="text" value={artist} onChange={(e) => setArtist(e.target.value)} placeholder="e.g. Queen" disabled={submitting} required />
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Album (optional)</label>
          <input type="text" value={album} onChange={(e) => setAlbum(e.target.value)} placeholder="e.g. A Night at the Opera" disabled={submitting} />
        </div>
        <div className="form-group">
          <label>Language (optional)</label>
          <input type="text" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="e.g. hi / hindi, en, ml" maxLength={20} disabled={submitting} />
        </div>
      </div>

      <button type="submit" className="submit-btn" disabled={isDisabled}>
        {submitting
          ? (tab === 'youtube' ? 'Downloading… (may take ~30s)' : 'Uploading…')
          : 'Process Song'}
      </button>

      <style>{`
        .upload-form {
          background: #181820;
          border: 1px solid #2a2a35;
          border-radius: 8px;
          padding: 1.5rem;
          margin-bottom: 2rem;
        }
        .upload-form h3 {
          margin-bottom: 1rem;
          color: #a78bfa;
          font-size: 1.15rem;
        }
        .tab-row {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 1.25rem;
        }
        .tab-btn {
          background: #0f0f14;
          border: 1px solid #363645;
          border-radius: 6px;
          color: #9999aa;
          padding: 0.4rem 1rem;
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.15s;
        }
        .tab-btn.active {
          border-color: #a78bfa;
          color: #a78bfa;
          background: #1a1a2e;
        }
        .tab-btn:hover:not(.active) {
          border-color: #55556a;
          color: #ccccdd;
        }
        .form-row {
          display: flex;
          gap: 1rem;
        }
        .form-row .form-group { flex: 1; }
        .form-group {
          margin-bottom: 1rem;
          display: flex;
          flex-direction: column;
        }
        .form-group label {
          font-size: 0.85rem;
          font-weight: 500;
          margin-bottom: 0.35rem;
          color: #c4c4d4;
        }
        .form-group input[type="text"],
        .form-group input[type="url"] {
          background: #0f0f14;
          border: 1px solid #363645;
          border-radius: 4px;
          color: #f0f0f5;
          padding: 0.5rem 0.75rem;
          font-size: 0.9rem;
          outline: none;
        }
        .form-group input[type="text"]:focus,
        .form-group input[type="url"]:focus {
          border-color: #a78bfa;
        }
        .form-group input[type="file"] {
          color: #9999aa;
          font-size: 0.85rem;
        }
        .form-hint {
          font-size: 0.75rem;
          color: #777788;
          margin-top: 0.25rem;
        }
        .form-error {
          background: #3b1c1c;
          border: 1px solid #ef4444;
          color: #fca5a5;
          padding: 0.6rem 0.8rem;
          border-radius: 4px;
          font-size: 0.85rem;
          margin-bottom: 1rem;
        }
        .submit-btn {
          background: #8b5cf6;
          color: white;
          border: none;
          padding: 0.65rem 1.4rem;
          border-radius: 6px;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s;
        }
        .submit-btn:hover:not(:disabled) { background: #7c3aed; }
        .submit-btn:disabled { background: #4c4465; cursor: not-allowed; }
      `}</style>
    </form>
  )
}
