import {
  type BarPeak,
  FOURIER_BIN_COUNT,
  fourierOf,
  peaksOf,
  type Timeline,
  unit,
} from "../contract/timeline";

export const EPICYCLE_LIMIT = 4;
export const EASE_RATE_PER_S = 3.5;
export const MAX_TURNS_PER_BAR = 8;
export const BREATH_FLOOR = 0.7;

const MATCH_DISTANCE = 0.2;
const FADED_AMP = 0.01;
const SILENT_LEVEL = 1e-4;
const TURN_RAD = 2 * Math.PI;

export interface BarSnapshot {
  readonly magnitude: Float32Array;
  readonly components: readonly BarPeak[];
}

export interface Epicycle {
  freqHz: number;
  amp: number;
  targetFreqHz: number;
  targetAmp: number;
  angleRad: number;
  readonly startPhaseRad: number;
}

export function snapshotOf(timeline: Timeline, bar: number): BarSnapshot {
  const magnitude = Float32Array.from(fourierOf(timeline, bar), unit);
  const silent = Math.max(...magnitude) < SILENT_LEVEL;
  return { magnitude, components: silent ? [] : peaksOf(timeline, bar).slice(0, EPICYCLE_LIMIT) };
}

export function easeFactor(dtS: number): number {
  return 1 - Math.exp(-dtS * EASE_RATE_PER_S);
}

export function turnsPerBar(freqHz: number, lowestHz: number): number {
  return Math.min(MAX_TURNS_PER_BAR, Math.max(1, Math.round(freqHz / lowestHz)));
}

export function breathOf(level: number): number {
  return BREATH_FLOOR + (1 - BREATH_FLOOR) * level;
}

export class FourierMorph {
  readonly magnitude = new Float32Array(FOURIER_BIN_COUNT);
  epicycles: Epicycle[] = [];
  #started = false;

  constructor(private readonly random: () => number) {}

  step(target: BarSnapshot, dtS: number): void {
    const k = this.#started ? easeFactor(dtS) : 1;
    this.#started = true;
    for (let bin = 0; bin < FOURIER_BIN_COUNT; bin += 1) {
      const current = this.magnitude[bin] ?? 0;
      this.magnitude[bin] = current + ((target.magnitude[bin] ?? 0) - current) * k;
    }
    this.#retarget(target.components);
    for (const epicycle of this.epicycles) {
      epicycle.amp += (epicycle.targetAmp - epicycle.amp) * k;
      epicycle.freqHz += (epicycle.targetFreqHz - epicycle.freqHz) * k;
    }
    const visible = this.epicycles.filter(
      (epicycle) => epicycle.targetAmp > 0 || epicycle.amp > FADED_AMP,
    );
    const fading = visible
      .filter((epicycle) => epicycle.targetAmp === 0)
      .sort((left, right) => right.amp - left.amp);
    const room = EPICYCLE_LIMIT - (visible.length - fading.length);
    const kept = new Set(fading.slice(0, Math.max(0, room)));
    this.epicycles = visible
      .filter((epicycle) => epicycle.targetAmp > 0 || kept.has(epicycle))
      .sort((left, right) => left.targetFreqHz - right.targetFreqHz);
  }

  turn(barPosition: number): void {
    const sounding = this.epicycles.filter((epicycle) => epicycle.targetAmp > 0);
    const lowestHz = Math.min(
      ...(sounding.length > 0 ? sounding : this.epicycles).map((epicycle) => epicycle.targetFreqHz),
    );
    for (const epicycle of this.epicycles) {
      const turns = turnsPerBar(epicycle.targetFreqHz, lowestHz);
      epicycle.angleRad = epicycle.startPhaseRad + TURN_RAD * turns * barPosition;
    }
  }

  #retarget(components: readonly BarPeak[]): void {
    const used = new Set<number>();
    for (const epicycle of this.epicycles) {
      const match = closest(components, epicycle.targetFreqHz, used);
      const component = match === -1 ? undefined : components[match];
      if (component === undefined) {
        epicycle.targetAmp = 0;
        continue;
      }
      used.add(match);
      epicycle.targetAmp = component.amp;
      epicycle.targetFreqHz = component.freqHz;
    }
    components.forEach((component, index) => {
      if (!used.has(index)) {
        const startPhaseRad = this.random() * TURN_RAD;
        this.epicycles.push({
          freqHz: component.freqHz,
          amp: 0,
          targetFreqHz: component.freqHz,
          targetAmp: component.amp,
          angleRad: startPhaseRad,
          startPhaseRad,
        });
      }
    });
  }
}

function closest(
  components: readonly BarPeak[],
  freqHz: number,
  used: ReadonlySet<number>,
): number {
  let best = -1;
  let bestDistance = MATCH_DISTANCE;
  components.forEach((component, index) => {
    const distance = Math.abs(Math.log(component.freqHz / freqHz));
    if (!used.has(index) && distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  });
  return best;
}
