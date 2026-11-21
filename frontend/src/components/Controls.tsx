import React from 'react'
import type { RemovalMode } from '../audio/engine'

interface ControlsProps {
  removalMode: RemovalMode
  onRemovalChange: (mode: RemovalMode) => void
  isPlaying: boolean
  currentTime: number
  duration: number
  guideVolume: number
  instrumentalVolume: number
  lyricOffsetMs: number
  onTogglePlay: () => void
  onSeek: (timeSec: number) => void
  onGuideVolumeChange: (vol: number) => void
  onInstrumentalVolumeChange: (vol: number) => void
  onLyricOffsetChange: (offsetMs: number) => void
  onToggleFullscreen: () => void
}

function formatTime(sec: number): string {
  if (isNaN(sec) || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function Controls({
  removalMode,
  onRemovalChange,
  isPlaying,
  currentTime,
  duration,
  guideVolume,
  instrumentalVolume,
  lyricOffsetMs,
  onTogglePlay,
  onSeek,
  onGuideVolumeChange,
  onInstrumentalVolumeChange,
  onLyricOffsetChange,
  onToggleFullscreen,
}: ControlsProps) {
  const handleSeekChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onSeek(parseFloat(e.target.value));
  };

  return (
    <div className="karaoke-controls">
      {/* Removal Mode Dropdown */}
      <div className="removal-row">
        <label htmlFor="removal-select">Vocal Removal</label>
        <select
          id="removal-select"
          value={removalMode}
          onChange={(e) => onRemovalChange(e.target.value as RemovalMode)}
        >
          <option value="both">Both vocals (full mix)</option>
          <option value="female">Remove Lead / Keep Backing</option>
          <option value="male">Remove Backing / Keep Lead</option>
        </select>
      </div>

      <div className="seek-row">
        <span className="time-display">{formatTime(currentTime)}</span>
        <input
          type="range"
          className="seek-slider"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeekChange}
        />
        <span className="time-display">{formatTime(duration)}</span>
      </div>

      {/* Main Controls Row */}
      <div className="buttons-row">
        <button className="play-btn" onClick={onTogglePlay} title="Play / Pause (Space)">
          {isPlaying ? '⏸ Pause' : '▶ Play'}
        </button>

        <button className="seek-btn" onClick={() => onSeek(Math.max(0, currentTime - 5))} title="Rewind 5s (Left Arrow)">
          ↺ 5s
        </button>

        <button className="seek-btn" onClick={() => onSeek(Math.min(duration, currentTime + 5))} title="Forward 5s (Right Arrow)">
          5s ↻
        </button>

        {/* Guide Vocal Volume Slider */}
        <div className="slider-group">
          <label title="Quiet guide vocals for pitch reference">
            Guide Vocals: {Math.round(guideVolume * 100)}%
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={guideVolume}
            onChange={(e) => onGuideVolumeChange(parseFloat(e.target.value))}
          />
        </div>

        {/* Instrumental Volume Slider */}
        <div className="slider-group">
          <label>Music: {Math.round(instrumentalVolume * 100)}%</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={instrumentalVolume}
            onChange={(e) => onInstrumentalVolumeChange(parseFloat(e.target.value))}
          />
        </div>

        {/* Lyric Offset (-2000 to +2000 ms, 50 ms steps) */}
        <div className="slider-group offset-group">
          <label title="Timing offset ([ and ] keys)">
            Lyric Offset: {lyricOffsetMs > 0 ? `+${lyricOffsetMs}` : lyricOffsetMs} ms
          </label>
          <div className="offset-control">
            <button
              className="step-btn"
              onClick={() => onLyricOffsetChange(Math.max(-2000, lyricOffsetMs - 50))}
              title="Shift earlier (-50ms, key [)"
            >
              -
            </button>
            <input
              type="range"
              min={-2000}
              max={2000}
              step={50}
              value={lyricOffsetMs}
              onChange={(e) => onLyricOffsetChange(parseInt(e.target.value, 10))}
            />
            <button
              className="step-btn"
              onClick={() => onLyricOffsetChange(Math.min(2000, lyricOffsetMs + 50))}
              title="Shift later (+50ms, key ])"
            >
              +
            </button>
          </div>
        </div>

        {/* Fullscreen Button */}
        <button className="fs-btn" onClick={onToggleFullscreen} title="Fullscreen">
          ⛶
        </button>
      </div>

      <style>{`
        .karaoke-controls {
          background: #181822;
          border: 1px solid #2e2e42;
          border-radius: 12px;
          padding: 1.25rem 1.5rem;
          margin-top: 1.5rem;
        }
        .seek-row {
          display: flex;
          align-items: center;
          gap: 1rem;
          margin-bottom: 1rem;
        }
        .time-display {
          font-family: monospace;
          font-size: 0.9rem;
          color: #a1a1b5;
          min-width: 45px;
        }
        .seek-slider {
          flex: 1;
          height: 6px;
          border-radius: 3px;
          accent-color: #ec4899;
          cursor: pointer;
        }
        .buttons-row {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 1.2rem;
        }
        .play-btn {
          background: #ec4899;
          color: #fff;
          border: none;
          padding: 0.65rem 1.5rem;
          border-radius: 6px;
          font-weight: 700;
          font-size: 1rem;
          cursor: pointer;
          transition: background 0.15s;
        }
        .play-btn:hover {
          background: #db2777;
        }
        .seek-btn, .step-btn {
          background: #272738;
          color: #e4e4ed;
          border: 1px solid #3d3d54;
          padding: 0.5rem 0.8rem;
          border-radius: 4px;
          font-size: 0.85rem;
          cursor: pointer;
        }
        .seek-btn:hover, .step-btn:hover {
          background: #36364d;
        }
        .slider-group {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .slider-group label {
          font-size: 0.75rem;
          color: #9494a8;
          font-weight: 500;
        }
        .slider-group input[type="range"] {
          width: 110px;
          height: 4px;
          accent-color: #a78bfa;
          cursor: pointer;
        }
        .offset-control {
          display: flex;
          align-items: center;
          gap: 0.35rem;
        }
        .offset-control input[type="range"] {
          width: 90px;
        }
        .fs-btn {
          margin-left: auto;
          background: transparent;
          border: 1px solid #3d3d54;
          color: #e4e4ed;
          padding: 0.5rem 0.8rem;
          border-radius: 6px;
          font-size: 1.1rem;
          cursor: pointer;
        }
        .fs-btn:hover {
          background: #272738;
        }
      `}</style>
    </div>
  )
}
