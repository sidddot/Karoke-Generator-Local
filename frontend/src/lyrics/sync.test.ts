/** Batch 0 Vitest: sync.ts pure functions */
import { describe, it, expect } from 'vitest'
import type { LyricLine } from '../api'
import { findLine, findWord, wordProgress } from '../lyrics/sync'

const lines: LyricLine[] = [
  { start: 0, end: 3, text: 'line one', words: [
    { w: 'line', s: 0, e: 1.5, score: 0.9 },
    { w: 'one', s: 1.5, e: 3, score: 0.8 },
  ]},
  { start: 3, end: 6, text: 'line two', words: [
    { w: 'line', s: 3, e: 4.5, score: 0.9 },
    { w: 'two', s: 4.5, e: 6, score: 0.7 },
  ]},
]

describe('findLine', () => {
  it('returns correct index mid-line', () => expect(findLine(lines, 1.0)).toBe(0))
  it('returns second line', () => expect(findLine(lines, 4.0)).toBe(1))
  it('returns -1 before all lines', () => expect(findLine(lines, -1)).toBe(-1))
  it('returns -1 after all lines', () => expect(findLine(lines, 100)).toBe(-1))
  it('returns line at exact start', () => expect(findLine(lines, 0)).toBe(0))
})

describe('findWord', () => {
  it('finds first word', () => expect(findWord(lines[0], 0.5)).toBe(0))
  it('finds second word', () => expect(findWord(lines[0], 2.0)).toBe(1))
  it('returns -1 when no word active', () => expect(findWord(lines[0], 3.5)).toBe(-1))
})

describe('wordProgress', () => {
  const w = { w: 'hi', s: 2, e: 4, score: null }
  it('0 before word', () => expect(wordProgress(w, 1)).toBe(0))
  it('1 after word', () => expect(wordProgress(w, 5)).toBe(1))
  it('0.5 at midpoint', () => expect(wordProgress(w, 3)).toBe(0.5))
})
