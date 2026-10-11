export const OUTPUT_GAIN = 0.8;
export const ANALYSER_FFT_SIZE = 2048;
export const ANALYSER_SMOOTHING = 0.55;

const SEEK_MARGIN_S = 0.01;
const PLAYABLE_TIMEOUT_MS = 30_000;
const HAVE_CURRENT_DATA = 2;
const INTERRUPTIONS: readonly string[] = ["NotAllowedError", "AbortError"];

export interface Media extends EventTarget {
  readonly readyState: number;
  readonly duration: number;
}

export interface PreparedAudio {
  readonly element: HTMLAudioElement;
  readonly url: string;
}

interface Playing {
  readonly audio: PreparedAudio;
  readonly source: MediaElementAudioSourceNode;
}

export function whenPlayable(media: Media, deadline: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const stop = () => {
      media.removeEventListener("loadeddata", ready);
      media.removeEventListener("error", failed);
      deadline.removeEventListener("abort", late);
    };
    const ready = () => {
      stop();
      if (Number.isFinite(media.duration) && media.duration > 0) {
        resolve();
      } else {
        reject(new Error("the browser reports no duration"));
      }
    };
    const failed = () => {
      stop();
      reject(new Error("the browser cannot play this file"));
    };
    const late = () => {
      stop();
      reject(new Error("the browser did not load the file in time"));
    };
    media.addEventListener("loadeddata", ready);
    media.addEventListener("error", failed);
    deadline.addEventListener("abort", late);
    if (media.readyState >= HAVE_CURRENT_DATA) {
      ready();
    } else if (deadline.aborted) {
      late();
    }
  });
}

export function seekTargetS(timeS: number, durationS: number): number {
  return Math.min(Math.max(timeS, 0), Math.max(0, durationS - SEEK_MARGIN_S));
}

export class Player {
  readonly #context: AudioContext;
  readonly #output: GainNode;
  readonly #analyser: AnalyserNode;
  #playing: Playing | null = null;
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
    return (
      this.#playing !== null &&
      !this.#playing.audio.element.paused &&
      this.#context.state === "running"
    );
  }

  get pausedByUser(): boolean {
    return this.#pausedByUser;
  }

  get sampleRateHz(): number {
    return this.#context.sampleRate;
  }

  async wake(): Promise<void> {
    if (this.#context.state === "suspended" && !this.#pausedByUser) {
      await this.#context.resume();
    }
  }

  async prepare(file: File): Promise<PreparedAudio> {
    const element = new Audio();
    const audio = { element, url: URL.createObjectURL(file) };
    element.loop = true;
    element.preload = "auto";
    element.src = audio.url;
    try {
      await whenPlayable(element, AbortSignal.timeout(PLAYABLE_TIMEOUT_MS));
    } catch (error) {
      this.release(audio);
      throw error;
    }
    return audio;
  }

  release(audio: PreparedAudio): void {
    audio.element.pause();
    audio.element.removeAttribute("src");
    audio.element.load();
    URL.revokeObjectURL(audio.url);
  }

  play(audio: PreparedAudio): void {
    if (this.#playing !== null) {
      this.#playing.source.disconnect();
      this.release(this.#playing.audio);
    }
    const source = this.#context.createMediaElementSource(audio.element);
    source.connect(this.#output);
    this.#playing = { audio, source };
    audio.element.currentTime = 0;
    void this.#resume();
  }

  timeS(): number {
    return this.#playing?.audio.element.currentTime ?? 0;
  }

  seek(timeS: number): void {
    if (this.#playing !== null) {
      const { element } = this.#playing.audio;
      element.currentTime = seekTargetS(timeS, element.duration);
    }
  }

  async toggle(): Promise<void> {
    if (this.running) {
      this.#pausedByUser = true;
      this.#playing?.audio.element.pause();
    } else {
      await this.#resume();
    }
  }

  async resumeAfterBlock(): Promise<void> {
    await this.#resume();
  }

  waveform(samples: Float32Array<ArrayBuffer>): void {
    this.#analyser.getFloatTimeDomainData(samples);
  }

  async #resume(): Promise<void> {
    this.#pausedByUser = false;
    try {
      await this.#context.resume();
      await this.#playing?.audio.element.play();
    } catch (error) {
      if (!(error instanceof DOMException && INTERRUPTIONS.includes(error.name))) {
        throw error;
      }
    }
  }
}
