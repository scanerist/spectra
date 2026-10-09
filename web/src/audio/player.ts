export const OUTPUT_GAIN = 0.8;
export const ANALYSER_FFT_SIZE = 2048;
export const ANALYSER_SMOOTHING = 0.55;

export function loopTimeS(clockS: number, startedAtS: number, durationS: number): number {
  if (durationS <= 0) {
    return 0;
  }
  const elapsedS = clockS - startedAtS;
  return ((elapsedS % durationS) + durationS) % durationS;
}

export class Player {
  readonly #context: AudioContext;
  readonly #output: GainNode;
  readonly #analyser: AnalyserNode;
  #buffer: AudioBuffer | null = null;
  #source: AudioBufferSourceNode | null = null;
  #startedAtS = 0;
  #pausedByUser = false;

  constructor(context: AudioContext) {
    this.#context = context;
    this.#output = context.createGain();
    this.#output.gain.value = OUTPUT_GAIN;
    this.#analyser = context.createAnalyser();
    this.#analyser.fftSize = ANALYSER_FFT_SIZE;
    this.#analyser.smoothingTimeConstant = ANALYSER_SMOOTHING;
    this.#output.connect(this.#analyser);
    this.#analyser.connect(context.destination);
  }

  get running(): boolean {
    return this.#context.state === "running";
  }

  get pausedByUser(): boolean {
    return this.#pausedByUser;
  }

  get durationS(): number {
    return this.#buffer?.duration ?? 0;
  }

  get sampleRateHz(): number {
    return this.#context.sampleRate;
  }

  async wake(): Promise<void> {
    if (this.#context.state === "suspended" && !this.#pausedByUser) {
      await this.#context.resume();
    }
  }

  decode(data: ArrayBuffer): Promise<AudioBuffer> {
    return this.#context.decodeAudioData(data);
  }

  play(buffer: AudioBuffer): void {
    this.#buffer = buffer;
    this.#pausedByUser = false;
    this.seek(0);
  }

  timeS(): number {
    return loopTimeS(this.#context.currentTime, this.#startedAtS, this.durationS);
  }

  seek(timeS: number): void {
    if (this.#buffer === null) {
      return;
    }
    const offsetS = Math.min(Math.max(timeS, 0), Math.max(0, this.durationS - 0.01));
    this.#stopSource();
    const source = this.#context.createBufferSource();
    source.buffer = this.#buffer;
    source.loop = true;
    source.connect(this.#output);
    source.start(0, offsetS);
    this.#source = source;
    this.#startedAtS = this.#context.currentTime - offsetS;
  }

  async toggle(): Promise<void> {
    if (this.running) {
      this.#pausedByUser = true;
      await this.#context.suspend();
    } else {
      this.#pausedByUser = false;
      await this.#context.resume();
    }
  }

  async resumeAfterBlock(): Promise<void> {
    this.#pausedByUser = false;
    await this.#context.resume();
  }

  stop(): void {
    this.#stopSource();
    this.#buffer = null;
  }

  waveform(samples: Float32Array<ArrayBuffer>): void {
    this.#analyser.getFloatTimeDomainData(samples);
  }

  #stopSource(): void {
    if (this.#source !== null) {
      this.#source.stop();
      this.#source.disconnect();
      this.#source = null;
    }
  }
}
