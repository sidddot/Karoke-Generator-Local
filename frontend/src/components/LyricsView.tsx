import React from 'react'
import type { LyricLine } from '../api'
import { findWord, wordProgress } from '../lyrics/sync'

interface LyricsViewProps {
  lines: LyricLine[]
  currentTime: number
  activeLineIdx: number
  onSeek: (timeSec: number) => void
}

export default function LyricsView({
  lines,
  currentTime,
  activeLineIdx,
  onSeek,
}: LyricsViewProps) {
  if (!lines || lines.length === 0) {
    return (
      <div className="lyrics-empty">
        <p>No timed lyrics available for this song.</p>
      </div>
    )
  }

  // Display previous line, current line (large and centered), and next two lines
  const prevLine = activeLineIdx > 0 ? lines[activeLineIdx - 1] : null
  const currentLine = activeLineIdx >= 0 ? lines[activeLineIdx] : lines[0]
  const nextLine1 = activeLineIdx + 1 < lines.length ? lines[activeLineIdx + 1] : null
  const nextLine2 = activeLineIdx + 2 < lines.length ? lines[activeLineIdx + 2] : null

  const currentWordIdx = currentLine ? findWord(currentLine, currentTime) : -1

  return (
    <div className="lyrics-display-card">
      {/* Previous line (dimmed) */}
      <div
        className={`line line-prev ${prevLine ? 'visible' : ''}`}
        onClick={() => prevLine && onSeek(prevLine.start)}
      >
        {prevLine?.text || '\u00A0'}
      </div>

      {/* Current line (large and centered) */}
      <div
        className="line line-current"
        onClick={() => currentLine && onSeek(currentLine.start)}
      >
        {currentLine ? (
          currentLine.words.map((word, idx) => {
            let progress = 0
            if (idx < currentWordIdx) {
              progress = 1.0 // already sung
            } else if (idx === currentWordIdx) {
              progress = wordProgress(word, currentTime) // currently singing
            }

            const pct = Math.round(progress * 100)

            return (
              <span
                key={`${word.w}-${idx}`}
                className="karaoke-word"
                style={{
                  background: `linear-gradient(to right, #ec4899 ${pct}%, rgba(255, 255, 255, 0.45) ${pct}%)`,
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                {word.w}{' '}
              </span>
            )
          })
        ) : (
          <span>Waiting for lyrics…</span>
        )}
      </div>

      {/* Next line 1 */}
      <div
        className={`line line-next1 ${nextLine1 ? 'visible' : ''}`}
        onClick={() => nextLine1 && onSeek(nextLine1.start)}
      >
        {nextLine1?.text || '\u00A0'}
      </div>

      {/* Next line 2 */}
      <div
        className={`line line-next2 ${nextLine2 ? 'visible' : ''}`}
        onClick={() => nextLine2 && onSeek(nextLine2.start)}
      >
        {nextLine2?.text || '\u00A0'}
      </div>

      <style>{`
        .lyrics-display-card {
          background: radial-gradient(circle at center, #1c1c28 0%, #121218 100%);
          border: 1px solid #2e2e40;
          border-radius: 12px;
          min-height: 380px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          padding: 2.5rem 1.5rem;
          text-align: center;
          user-select: none;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }
        .lyrics-empty {
          padding: 4rem 1rem;
          text-align: center;
          color: #71717a;
          font-size: 1.1rem;
        }
        .line {
          width: 100%;
          cursor: pointer;
          transition: all 0.25s ease-out;
          padding: 0.4rem 0.5rem;
        }
        .line:hover {
          filter: brightness(1.2);
        }
        .line-prev {
          font-size: 1.2rem;
          color: rgba(255, 255, 255, 0.4);
          margin-bottom: 1.25rem;
        }
        .line-current {
          font-size: 2.2rem;
          font-weight: 700;
          letter-spacing: -0.02em;
          margin: 0.8rem 0;
          line-height: 1.35;
          text-shadow: 0 4px 20px rgba(236, 72, 153, 0.25);
        }
        .karaoke-word {
          display: inline-block;
          white-space: pre;
          transition: transform 0.05s ease-out;
        }
        .line-next1 {
          font-size: 1.35rem;
          color: rgba(255, 255, 255, 0.6);
          margin-top: 1.25rem;
        }
        .line-next2 {
          font-size: 1.05rem;
          color: rgba(255, 255, 255, 0.35);
          margin-top: 0.5rem;
        }
      `}</style>
    </div>
  )
}
