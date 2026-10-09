import { describe, expect, it } from "vitest";
import { FOURIER_BIN_COUNT, type Timeline } from "../../src/contract/timeline";
import {
  type BarSnapshot,
  EPICYCLE_LIMIT,
  easeFactor,
  FourierMorph,
  snapshotOf,
} from "../../src/view/fourier";

function snapshot(level: number, components: { freqHz: number; amp: number }[]): BarSnapshot {
  return { magnitude: new Float32Array(FOURIER_BIN_COUNT).fill(level), components };
}

function morph(): FourierMorph {
  return new FourierMorph(() => 0.25);
}

function timelineWith(peaks: number[], fourierLevel: number): Timeline {
  return {
    frameRateHz: 44_100 / 512,
    frameCount: 1,
    barCount: 1,
    peaks: Float32Array.from({ length: 16 }, (_, index) => peaks[index] ?? 0),
    bands: new Uint8Array(64),
    levels: new Uint8Array(5),
    fourier: new Uint8Array(FOURIER_BIN_COUNT).fill(fourierLevel),
  };
}

describe("a bar snapshot", () => {
  it("takes at most four of the bar's peaks", () => {
    const peaks = [55, 1, 110, 0.9, 165, 0.8, 220, 0.7, 275, 0.6];
    expect(snapshotOf(timelineWith(peaks, 255), 0).components).toHaveLength(EPICYCLE_LIMIT);
  });

  it("has no components when the bar is silent", () => {
    expect(snapshotOf(timelineWith([55, 1], 0), 0).components).toEqual([]);
  });

  it("scales the spectrum to 0..1", () => {
    expect(snapshotOf(timelineWith([], 255), 0).magnitude[0]).toBe(1);
  });
});

describe("easing between bars", () => {
  it("takes half a second to cover most of the way", () => {
    expect(easeFactor(0.5)).toBeCloseTo(1 - Math.exp(-1.75));
  });

  it("starts from the first bar instead of rising from zero", () => {
    const fourier = morph();
    fourier.step(snapshot(0.8, []), 0.016, true);
    expect(fourier.magnitude[0]).toBeCloseTo(0.8);
  });

  it("moves the spectrum part of the way each frame", () => {
    const fourier = morph();
    fourier.step(snapshot(0, []), 0.016, true);
    fourier.step(snapshot(1, []), 0.1, true);
    expect(fourier.magnitude[0]).toBeCloseTo(easeFactor(0.1));
  });
});

describe("epicycles", () => {
  it("grow a new frequency from nothing", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 55, amp: 1 }]), 0.016, true);
    expect(fourier.epicycles[0]?.amp).toBe(1);
    fourier.step(
      snapshot(1, [
        { freqHz: 55, amp: 1 },
        { freqHz: 220, amp: 0.5 },
      ]),
      0.1,
      true,
    );
    const grown = fourier.epicycles[1];
    expect(grown?.targetFreqHz).toBe(220);
    expect(grown?.amp).toBeCloseTo(0.5 * easeFactor(0.1));
  });

  it("follow a frequency that moved a little instead of replacing it", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.016, true);
    fourier.step(snapshot(1, [{ freqHz: 110, amp: 1 }]), 0.1, true);
    expect(fourier.epicycles).toHaveLength(1);
    expect(fourier.epicycles[0]?.targetFreqHz).toBe(110);
  });

  it("fade out a frequency that disappeared and then drop it", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.016, true);
    fourier.step(snapshot(1, []), 0.1, true);
    expect(fourier.epicycles[0]?.amp).toBeCloseTo(1 - easeFactor(0.1));
    for (let frame = 0; frame < 120; frame += 1) {
      fourier.step(snapshot(1, []), 0.016, true);
    }
    expect(fourier.epicycles).toEqual([]);
  });

  it("stay ordered by frequency from low to high", () => {
    const fourier = morph();
    fourier.step(
      snapshot(1, [
        { freqHz: 300, amp: 1 },
        { freqHz: 60, amp: 0.4 },
      ]),
      0.016,
      true,
    );
    expect(fourier.epicycles.map((epicycle) => epicycle.freqHz)).toEqual([60, 300]);
  });

  it("turn only while the music plays", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.016, false);
    const angleRad = fourier.epicycles[0]?.angleRad;
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.5, false);
    expect(fourier.epicycles[0]?.angleRad).toBe(angleRad);
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.5, true);
    expect(fourier.epicycles[0]?.angleRad).toBeGreaterThan(angleRad ?? 0);
  });
});
