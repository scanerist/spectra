import { describe, expect, it } from "vitest";
import { FOURIER_BIN_COUNT, type Timeline } from "../../src/contract/timeline";
import {
  type BarSnapshot,
  BREATH_FLOOR,
  breathOf,
  EPICYCLE_LIMIT,
  easeFactor,
  FourierMorph,
  MAX_TURNS_PER_BAR,
  snapshotOf,
  turnsPerBar,
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
    fourier.step(snapshot(0.8, []), 0.016);
    expect(fourier.magnitude[0]).toBeCloseTo(0.8);
  });

  it("moves the spectrum part of the way each frame", () => {
    const fourier = morph();
    fourier.step(snapshot(0, []), 0.016);
    fourier.step(snapshot(1, []), 0.1);
    expect(fourier.magnitude[0]).toBeCloseTo(easeFactor(0.1));
  });
});

describe("epicycles", () => {
  it("grow a new frequency from nothing", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 55, amp: 1 }]), 0.016);
    expect(fourier.epicycles[0]?.amp).toBe(1);
    fourier.step(
      snapshot(1, [
        { freqHz: 55, amp: 1 },
        { freqHz: 220, amp: 0.5 },
      ]),
      0.1,
    );
    const grown = fourier.epicycles[1];
    expect(grown?.targetFreqHz).toBe(220);
    expect(grown?.amp).toBeCloseTo(0.5 * easeFactor(0.1));
  });

  it("follow a frequency that moved a little instead of replacing it", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.016);
    fourier.step(snapshot(1, [{ freqHz: 110, amp: 1 }]), 0.1);
    expect(fourier.epicycles).toHaveLength(1);
    expect(fourier.epicycles[0]?.targetFreqHz).toBe(110);
  });

  it("fade out a frequency that disappeared and then drop it", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.016);
    fourier.step(snapshot(1, []), 0.1);
    expect(fourier.epicycles[0]?.amp).toBeCloseTo(1 - easeFactor(0.1));
    for (let frame = 0; frame < 120; frame += 1) {
      fourier.step(snapshot(1, []), 0.016);
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
    );
    expect(fourier.epicycles.map((epicycle) => epicycle.freqHz)).toEqual([60, 300]);
  });

  it("turn in bars of the track: the lowest once per bar", () => {
    const fourier = morph();
    fourier.step(snapshot(1, [{ freqHz: 100, amp: 1 }]), 0.016);
    const startRad = fourier.epicycles[0]?.startPhaseRad ?? 0;
    fourier.turn(0.25);
    expect(fourier.epicycles[0]?.angleRad).toBeCloseTo(startRad + Math.PI / 2);
    fourier.turn(0.25);
    expect(fourier.epicycles[0]?.angleRad).toBeCloseTo(startRad + Math.PI / 2);
  });

  it("turn higher frequencies a whole number of times per bar and meet on every downbeat", () => {
    const fourier = morph();
    fourier.step(
      snapshot(1, [
        { freqHz: 60, amp: 1 },
        { freqHz: 130, amp: 0.5 },
      ]),
      0.016,
    );
    fourier.turn(3);
    for (const epicycle of fourier.epicycles) {
      expect(Math.cos(epicycle.angleRad - epicycle.startPhaseRad)).toBeCloseTo(1);
    }
    fourier.turn(3.25);
    const [low, high] = fourier.epicycles;
    expect((high?.angleRad ?? 0) - (high?.startPhaseRad ?? 0)).toBeCloseTo(
      2 * ((low?.angleRad ?? 0) - (low?.startPhaseRad ?? 0)),
    );
  });

  it("never show more than four, letting the weakest fading ones go first", () => {
    const fourier = morph();
    const low = [40, 80, 160, 320].map((freqHz, index) => ({ freqHz, amp: 1 - index * 0.2 }));
    const high = [1000, 2000, 4000, 8000].map((freqHz) => ({ freqHz, amp: 1 }));
    fourier.step(snapshot(1, low), 0.016);
    fourier.step(snapshot(1, high.slice(0, 2)), 0.016);
    expect(fourier.epicycles).toHaveLength(EPICYCLE_LIMIT);
    expect(fourier.epicycles.map((epicycle) => epicycle.targetFreqHz)).toEqual([
      40, 80, 1000, 2000,
    ]);
    fourier.step(snapshot(1, high), 0.016);
    expect(fourier.epicycles.map((epicycle) => epicycle.targetFreqHz)).toEqual([
      1000, 2000, 4000, 8000,
    ]);
  });
});

describe("motion in time with the track", () => {
  it("rounds frequency ratios to whole turns per bar within limits", () => {
    expect(turnsPerBar(55, 55)).toBe(1);
    expect(turnsPerBar(170, 55)).toBe(3);
    expect(turnsPerBar(600, 30)).toBe(MAX_TURNS_PER_BAR);
  });

  it("breathes between a floor at silence and full size at full level", () => {
    expect(breathOf(0)).toBe(BREATH_FLOOR);
    expect(breathOf(1)).toBe(1);
    expect(breathOf(0.5)).toBeCloseTo((BREATH_FLOOR + 1) / 2);
  });
});
