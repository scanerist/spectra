import { describe, expect, it } from "vitest";
import { fourierAt, sweepHz, windowOf } from "../../src/screens/analysis-views";
import type { Epicycle } from "../../src/view/fourier";

const SAMPLE_RATE_HZ = 44_100;

function epicycle(freqHz: number, amp: number): Epicycle {
  return { freqHz, amp, targetFreqHz: freqHz, targetAmp: amp, angleRad: 0, startPhaseRad: 0 };
}

describe("the winding view", () => {
  it("sweeps the fourier range once per bar from the downbeat", () => {
    expect(sweepHz(0)).toBeCloseTo(30);
    expect(sweepHz(4.5)).toBeCloseTo(Math.sqrt(30 * 600));
    expect(sweepHz(5)).toBeCloseTo(30);
    expect(sweepHz(-0.5)).toBeCloseTo(Math.sqrt(30 * 600));
  });

  it("finds a bar's frequency in the window it synthesises", () => {
    const samples = new Float32Array(2048);
    windowOf([epicycle(220, 1)], SAMPLE_RATE_HZ, samples);
    const magnitude = (freqHz: number) => Math.hypot(...fourierAt(samples, freqHz, SAMPLE_RATE_HZ));
    expect(magnitude(220)).toBeGreaterThan(10 * magnitude(440));
  });

  it("returns the window's peak for scaling", () => {
    const samples = new Float32Array(2048);
    const peak = windowOf([epicycle(100, 0.5)], SAMPLE_RATE_HZ, samples);
    expect(peak).toBeCloseTo(0.5, 1);
    expect(Math.max(...samples.map(Math.abs))).toBeCloseTo(peak, 5);
  });
});
