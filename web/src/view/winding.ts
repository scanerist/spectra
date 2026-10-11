import { FOURIER_BIN_COUNT, FOURIER_HIGH_HZ, FOURIER_LOW_HZ } from "../contract/timeline";
import type { Epicycle } from "./fourier";

const TURN_RAD = 2 * Math.PI;

export function sweepHz(barPosition: number): number {
  const share = ((barPosition % 1) + 1) % 1;
  return FOURIER_LOW_HZ * (FOURIER_HIGH_HZ / FOURIER_LOW_HZ) ** share;
}

export function binOf(freqHz: number): number {
  return (
    (Math.log(freqHz / FOURIER_LOW_HZ) / Math.log(FOURIER_HIGH_HZ / FOURIER_LOW_HZ)) *
    (FOURIER_BIN_COUNT - 1)
  );
}

export function windowOf(
  epicycles: readonly Epicycle[],
  sampleRateHz: number,
  samples: Float32Array,
): number {
  let peak = 1e-6;
  for (let n = 0; n < samples.length; n += 1) {
    let sum = 0;
    for (const epicycle of epicycles) {
      sum +=
        epicycle.amp *
        Math.sin((TURN_RAD * epicycle.freqHz * n) / sampleRateHz + epicycle.startPhaseRad);
    }
    const value = sum * (0.5 - 0.5 * Math.cos((TURN_RAD * n) / (samples.length - 1)));
    samples[n] = value;
    peak = Math.max(peak, Math.abs(value));
  }
  return peak;
}

export function fourierAt(
  samples: Float32Array,
  freqHz: number,
  sampleRateHz: number,
): readonly [number, number] {
  const stepRad = (TURN_RAD * freqHz) / sampleRateHz;
  let real = 0;
  let imaginary = 0;
  for (let n = 0; n < samples.length; n += 1) {
    const value = samples[n] ?? 0;
    real += value * Math.cos(stepRad * n);
    imaginary -= value * Math.sin(stepRad * n);
  }
  return [real, imaginary];
}
