/** Tiny WebAudio kit: water ambience, chimes, a splash and a distant boom. */
export class ShangyuanAudio {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  private ambient: { src: AudioBufferSourceNode; gain: GainNode } | null = null
  private muted = false

  unlock() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') void this.ctx.resume()
      return
    }
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return
    this.ctx = new Ctor()
    this.master = this.ctx.createGain()
    this.master.gain.value = this.muted ? 0 : 0.55
    this.master.connect(this.ctx.destination)
    this.startAmbience()
  }

  private startAmbience() {
    const ctx = this.ctx
    if (!ctx || !this.master || this.ambient) return
    const seconds = 4
    const buffer = ctx.createBuffer(2, ctx.sampleRate * seconds, ctx.sampleRate)
    for (let ch = 0; ch < 2; ch++) {
      const data = buffer.getChannelData(ch)
      let last = 0
      for (let i = 0; i < data.length; i++) {
        const white = Math.random() * 2 - 1
        last = (last + 0.02 * white) / 1.02
        data[i] = last * 3.2
      }
    }
    const src = ctx.createBufferSource()
    src.buffer = buffer
    src.loop = true
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.value = 620
    const gain = ctx.createGain()
    gain.gain.value = 0.16
    src.connect(filter).connect(gain).connect(this.master)
    src.start()
    this.ambient = { src, gain }
  }

  private tone(freq: number, duration: number, type: OscillatorType, level: number, delay = 0) {
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const t0 = ctx.currentTime + delay
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = type
    osc.frequency.setValueAtTime(freq, t0)
    gain.gain.setValueAtTime(0, t0)
    gain.gain.linearRampToValueAtTime(level, t0 + 0.012)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration)
    osc.connect(gain).connect(this.master)
    osc.start(t0)
    osc.stop(t0 + duration + 0.05)
  }

  chime(freq = 880) {
    this.unlock()
    this.tone(freq, 1.1, 'sine', 0.16)
    this.tone(freq * 1.5, 0.9, 'sine', 0.07, 0.02)
  }

  thud() {
    this.unlock()
    this.tone(150, 0.28, 'triangle', 0.12)
  }

  splash() {
    this.unlock()
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const t0 = ctx.currentTime
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 0.5, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i++)
      data[i] = (Math.random() * 2 - 1) * (1 - i / data.length) ** 3
    const src = ctx.createBufferSource()
    src.buffer = buffer
    const filter = ctx.createBiquadFilter()
    filter.type = 'bandpass'
    filter.frequency.value = 900
    const gain = ctx.createGain()
    gain.gain.value = 0.3
    src.connect(filter).connect(gain).connect(this.master)
    src.start(t0)
    this.tone(320, 0.5, 'sine', 0.08)
  }

  boom(level = 0.6) {
    this.unlock()
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const t0 = ctx.currentTime
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 1.6, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i++) {
      const t = i / data.length
      data[i] = (Math.random() * 2 - 1) * (1 - t) ** 2.4
    }
    const src = ctx.createBufferSource()
    src.buffer = buffer
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.setValueAtTime(900, t0)
    filter.frequency.exponentialRampToValueAtTime(120, t0 + 1.2)
    const gain = ctx.createGain()
    gain.gain.value = 0.5 * level
    src.connect(filter).connect(gain).connect(this.master)
    src.start(t0)
  }

  /** A rising shell: a thin sine sweep under a breath of noise. */
  whistle(duration = 1.1) {
    this.unlock()
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const t0 = ctx.currentTime
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(520, t0)
    osc.frequency.exponentialRampToValueAtTime(1680, t0 + duration)
    gain.gain.setValueAtTime(0.0001, t0)
    gain.gain.exponentialRampToValueAtTime(0.03, t0 + duration * 0.6)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration)
    osc.connect(gain).connect(this.master)
    osc.start(t0)
    osc.stop(t0 + duration + 0.05)
  }

  /** A short, friendly cat call: two syllables with a falling tail. */
  meow() {
    this.unlock()
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const t0 = ctx.currentTime
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sawtooth'
    osc.frequency.setValueAtTime(620, t0)
    osc.frequency.linearRampToValueAtTime(940, t0 + 0.16)
    osc.frequency.linearRampToValueAtTime(520, t0 + 0.42)
    gain.gain.setValueAtTime(0.0001, t0)
    gain.gain.exponentialRampToValueAtTime(0.09, t0 + 0.05)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.46)
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.value = 1800
    osc.connect(filter).connect(gain).connect(this.master)
    osc.start(t0)
    osc.stop(t0 + 0.5)
  }

  /** Bamboo knocking and tangerines scattering: one soft noise burst. */
  rustle(level = 0.5) {
    this.unlock()
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const t0 = ctx.currentTime
    const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.5), ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i++) {
      const t = i / data.length
      data[i] = (Math.random() * 2 - 1) * (1 - t) ** 2 * (0.5 + 0.5 * Math.sin(i * 0.02))
    }
    const src = ctx.createBufferSource()
    src.buffer = buffer
    const filter = ctx.createBiquadFilter()
    filter.type = 'bandpass'
    filter.frequency.value = 1400
    const gain = ctx.createGain()
    gain.gain.value = 0.22 * level
    src.connect(filter).connect(gain).connect(this.master)
    src.start(t0)
    this.tone(190, 0.18, 'triangle', 0.05)
  }

  /** Sparse high clicks: the crackling tail after a shell breaks. */
  crackle(level = 0.6, duration = 1.4) {
    this.unlock()
    const ctx = this.ctx
    if (!ctx || !this.master) return
    const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * duration), ctx.sampleRate)
    const data = buffer.getChannelData(0)
    const clicks = 34
    for (let c = 0; c < clicks; c++) {
      const at = Math.floor(Math.random() * (data.length - 320))
      const amp = (0.35 + Math.random() * 0.65) * (1 - at / data.length) ** 1.6
      for (let i = 0; i < 260; i++) {
        data[at + i] += (Math.random() * 2 - 1) * amp * (1 - i / 260) ** 2
      }
    }
    const src = ctx.createBufferSource()
    src.buffer = buffer
    const filter = ctx.createBiquadFilter()
    filter.type = 'highpass'
    filter.frequency.value = 1800
    const gain = ctx.createGain()
    gain.gain.value = 0.22 * level
    src.connect(filter).connect(gain).connect(this.master)
    src.start(ctx.currentTime + 0.04)
  }

  setMuted(muted: boolean) {
    this.muted = muted
    if (this.master) this.master.gain.value = muted ? 0 : 0.55
  }

  dispose() {
    this.ambient?.src.stop()
    void this.ctx?.close()
    this.ctx = null
    this.master = null
    this.ambient = null
  }
}
