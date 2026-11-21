/**
 * Web Audio playback engine for KarokeGen.
 * Plays instrumental + lead/backing vocal tracks sample-aligned via AudioContext.
 * removalMode controls which vocal stem(s) are audible:
 *   'both'   – instrumental + lead + backing (full mix)
 *   'female' – remove female/lead → instrumental + backing only
 *   'male'   – remove male/backing → instrumental + lead only
 */

export type PlaybackState = 'stopped' | 'loading' | 'playing' | 'paused'
export type RemovalMode = 'both' | 'female' | 'male'

export class AudioEngine {
  private ctx: AudioContext | null = null

  // Audio buffers
  private instrumentalBuffer: AudioBuffer | null = null
  private leadBuffer: AudioBuffer | null = null      // vocals_lead (main singer)
  private backingBuffer: AudioBuffer | null = null   // vocals_backing (harmonies)
  private vocalsBuffer: AudioBuffer | null = null    // fallback: full vocals mix

  // Active sources (recreated on every play/seek)
  private instrumentalSource: AudioBufferSourceNode | null = null
  private leadSource: AudioBufferSourceNode | null = null
  private backingSource: AudioBufferSourceNode | null = null
  private vocalsSource: AudioBufferSourceNode | null = null

  // Persistent gain nodes (kept across play/pause)
  private instrumentalGain: GainNode | null = null
  private leadGain: GainNode | null = null
  private backingGain: GainNode | null = null
  private vocalsGain: GainNode | null = null

  private startedAt = 0
  private seekOffset = 0
  private isCurrentlyPlaying = false

  private instVol = 1.0
  private guideVol = 0.15        // guide vocals volume
  private userOffsetSec = 0.0
  private removalMode: RemovalMode = 'both'

  public onStateChange?: (state: PlaybackState) => void
  public onEnded?: () => void

  constructor() {}

  private initContext(): AudioContext {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      this.ctx = new AudioCtx()
    }
    if (this.ctx.state === 'suspended') this.ctx.resume()
    return this.ctx
  }

  /** Fetch + decode FLAC with MP3 fallback. */
  private async loadBuffer(urlFlac: string, urlMp3: string): Promise<AudioBuffer> {
    const ctx = this.initContext()
    try {
      const res = await fetch(urlFlac)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await ctx.decodeAudioData(await res.arrayBuffer())
    } catch {
      const resMp3 = await fetch(urlMp3)
      if (!resMp3.ok) throw new Error(`Failed to load MP3 fallback: HTTP ${resMp3.status}`)
      return await ctx.decodeAudioData(await resMp3.arrayBuffer())
    }
  }

  /** Load instrumental + lead/backing stems. Falls back to full vocals if split stems are absent. */
  async load(songId: string): Promise<void> {
    this.onStateChange?.('loading')
    this.pause()

    // Always load instrumental
    this.instrumentalBuffer = await this.loadBuffer(
      `/audio/${songId}/instrumental.flac`,
      `/audio/${songId}/instrumental.mp3`,
    )

    // Try lead + backing stems (produced by Pass 2 in separate.py)
    try {
      const [lead, backing] = await Promise.all([
        this.loadBuffer(`/audio/${songId}/vocals_lead.flac`, `/audio/${songId}/vocals_lead.mp3`),
        this.loadBuffer(`/audio/${songId}/vocals_backing.flac`, `/audio/${songId}/vocals_backing.mp3`),
      ])
      this.leadBuffer = lead
      this.backingBuffer = backing
      this.vocalsBuffer = null
    } catch {
      // Fallback: no split stems available — load full vocals mix
      console.warn('Lead/backing stems not available, falling back to full vocals mix')
      this.leadBuffer = null
      this.backingBuffer = null
      try {
        this.vocalsBuffer = await this.loadBuffer(
          `/audio/${songId}/vocals.flac`,
          `/audio/${songId}/vocals.mp3`,
        )
      } catch {
        this.vocalsBuffer = null
      }
    }

    this.seekOffset = 0
    this.onStateChange?.('paused')
  }

  /** Returns true when split stems are loaded (gender separation is active). */
  private get hasSplitStems(): boolean {
    return !!(this.leadBuffer && this.backingBuffer)
  }

  /** Compute gain values for lead + backing based on current removalMode. */
  private _stemGains(): { lead: number; backing: number } {
    if (this.removalMode === 'female') {
      // "Remove Female" → mute lead (assumed lead = female in most songs), keep backing
      return { lead: 0, backing: this.guideVol }
    } else if (this.removalMode === 'male') {
      // "Remove Male" → mute backing, keep lead
      return { lead: this.guideVol, backing: 0 }
    }
    // 'both' → keep everything
    return { lead: this.guideVol, backing: this.guideVol }
  }

  async play(): Promise<void> {
    if (!this.instrumentalBuffer) return
    if (this.isCurrentlyPlaying) return

    const ctx = this.initContext()
    if (ctx.state === 'suspended') {
      try { await ctx.resume() } catch (err) { console.warn('AudioContext resume failed:', err) }
    }

    // --- Instrumental gain ---
    if (!this.instrumentalGain) {
      this.instrumentalGain = ctx.createGain()
      this.instrumentalGain.connect(ctx.destination)
    }
    this.instrumentalGain.gain.setValueAtTime(this.instVol, ctx.currentTime)

    // --- Vocal gains ---
    if (this.hasSplitStems) {
      if (!this.leadGain) {
        this.leadGain = ctx.createGain()
        this.leadGain.connect(ctx.destination)
      }
      if (!this.backingGain) {
        this.backingGain = ctx.createGain()
        this.backingGain.connect(ctx.destination)
      }
      const { lead, backing } = this._stemGains()
      this.leadGain.gain.setValueAtTime(lead, ctx.currentTime)
      this.backingGain.gain.setValueAtTime(backing, ctx.currentTime)
    } else if (this.vocalsBuffer) {
      if (!this.vocalsGain) {
        this.vocalsGain = ctx.createGain()
        this.vocalsGain.connect(ctx.destination)
      }
      this.vocalsGain.gain.setValueAtTime(this.guideVol, ctx.currentTime)
    }

    // --- Fresh buffer sources ---
    const when = ctx.currentTime + 0.05
    const offset = Math.min(this.seekOffset, this.getDuration())

    this.instrumentalSource = ctx.createBufferSource()
    this.instrumentalSource.buffer = this.instrumentalBuffer
    this.instrumentalSource.connect(this.instrumentalGain)
    this.instrumentalSource.onended = () => {
      if (this.getTime() >= this.getDuration() - 0.2) {
        this.isCurrentlyPlaying = false
        this.seekOffset = 0
        this.onStateChange?.('paused')
        this.onEnded?.()
      }
    }
    this.instrumentalSource.start(when, offset)

    if (this.hasSplitStems) {
      this.leadSource = ctx.createBufferSource()
      this.leadSource.buffer = this.leadBuffer!
      this.leadSource.connect(this.leadGain!)
      this.leadSource.start(when, offset)

      this.backingSource = ctx.createBufferSource()
      this.backingSource.buffer = this.backingBuffer!
      this.backingSource.connect(this.backingGain!)
      this.backingSource.start(when, offset)
    } else if (this.vocalsBuffer && this.vocalsGain) {
      this.vocalsSource = ctx.createBufferSource()
      this.vocalsSource.buffer = this.vocalsBuffer
      this.vocalsSource.connect(this.vocalsGain)
      this.vocalsSource.start(when, offset)
    }

    this.startedAt = when
    this.seekOffset = offset
    this.isCurrentlyPlaying = true
    this.onStateChange?.('playing')
  }

  pause(): void {
    if (!this.isCurrentlyPlaying) return
    this.seekOffset = this.getRawTime()
    this.isCurrentlyPlaying = false

    for (const src of [this.instrumentalSource, this.leadSource, this.backingSource, this.vocalsSource]) {
      if (src) { try { src.stop() } catch (_) {} src.disconnect() }
    }
    this.instrumentalSource = null
    this.leadSource = null
    this.backingSource = null
    this.vocalsSource = null

    this.onStateChange?.('paused')
  }

  seek(targetSeconds: number): void {
    const clamped = Math.max(0, Math.min(targetSeconds, this.getDuration()))
    const wasPlaying = this.isCurrentlyPlaying
    if (wasPlaying) {
      this.pause()
      this.seekOffset = clamped
      this.play()
    } else {
      this.seekOffset = clamped
    }
  }

  private getRawTime(): number {
    if (!this.isCurrentlyPlaying || !this.ctx) return this.seekOffset
    return Math.max(0, this.ctx.currentTime - this.startedAt + this.seekOffset)
  }

  getTime(): number {
    if (!this.isCurrentlyPlaying || !this.ctx) return this.seekOffset + this.userOffsetSec
    const outputLatency = (this.ctx as unknown as { outputLatency?: number }).outputLatency ?? 0
    const rawTime = this.ctx.currentTime - this.startedAt + this.seekOffset
    return Math.max(0, rawTime - outputLatency + this.userOffsetSec)
  }

  getDuration(): number {
    return this.instrumentalBuffer?.duration ?? 0
  }

  isPlaying(): boolean {
    return this.isCurrentlyPlaying
  }

  setGuideVolume(vol: number): void {
    this.guideVol = Math.max(0, Math.min(1, vol))
    const t = this.ctx?.currentTime ?? 0
    if (this.hasSplitStems) {
      const { lead, backing } = this._stemGains()
      this.leadGain?.gain.setValueAtTime(lead, t)
      this.backingGain?.gain.setValueAtTime(backing, t)
    } else {
      this.vocalsGain?.gain.setValueAtTime(this.guideVol, t)
    }
  }

  setInstrumentalVolume(vol: number): void {
    this.instVol = Math.max(0, Math.min(1, vol))
    if (this.instrumentalGain && this.ctx) {
      this.instrumentalGain.gain.setValueAtTime(this.instVol, this.ctx.currentTime)
    }
  }

  /**
   * Set vocal removal mode.
   * 'both'   – hear all vocals
   * 'female' – mute lead stem (primary/female singer)
   * 'male'   – mute backing stem (harmonies/male singer)
   * Falls back gracefully when split stems aren't available.
   */
  setRemovalMode(mode: RemovalMode): void {
    this.removalMode = mode
    if (!this.ctx) return
    const t = this.ctx.currentTime

    if (this.hasSplitStems && this.leadGain && this.backingGain) {
      const { lead, backing } = this._stemGains()
      this.leadGain.gain.setValueAtTime(lead, t)
      this.backingGain.gain.setValueAtTime(backing, t)
    } else if (this.vocalsGain) {
      // No split stems: 'both' = guide volume, any removal = mute
      const v = mode === 'both' ? this.guideVol : 0
      this.vocalsGain.gain.setValueAtTime(v, t)
    }
  }

  setUserOffsetMs(offsetMs: number): void {
    this.userOffsetSec = offsetMs / 1000.0
  }

  destroy(): void {
    this.pause()
    if (this.ctx && this.ctx.state !== 'closed') {
      this.ctx.close().catch(() => {})
    }
  }
}
