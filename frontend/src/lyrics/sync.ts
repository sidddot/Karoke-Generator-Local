/** Pure lyric-sync functions — implemented fully in Batch 6. */
import type { LyricLine, WordTiming } from '../api'

export function findLine(lines: LyricLine[], t: number): number {
  let lo = 0, hi = lines.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (lines[mid].end <= t) lo = mid + 1
    else if (lines[mid].start > t) hi = mid - 1
    else return mid
  }
  return -1
}

export function findWord(line: LyricLine, t: number): number {
  const words = line.words
  let lo = 0, hi = words.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (words[mid].e <= t) lo = mid + 1
    else if (words[mid].s > t) hi = mid - 1
    else return mid
  }
  return -1
}

export function wordProgress(word: WordTiming, t: number): number {
  if (t <= word.s) return 0
  if (t >= word.e) return 1
  return (t - word.s) / (word.e - word.s)
}
