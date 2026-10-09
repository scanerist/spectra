import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  BAND_COUNT,
  bandsOf,
  decodeTimeline,
  FOURIER_BIN_COUNT,
  fourierBinHz,
  fourierOf,
  levelOf,
  peaksOf,
  TimelineError,
  timelineLength,
} from "../../src/contract/timeline";

const GOLDEN_FRAMES = 70;
const GOLDEN_BARS = 2;

function golden(): ArrayBuffer {
  const bytes = readFileSync(
    new URL("../../../tests/contract/golden/timeline_v1.bin", import.meta.url),
  );
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function patched(offset: number, value: number): ArrayBuffer {
  const buffer = golden();
  new DataView(buffer).setUint32(offset, value, true);
  return buffer;
}

describe("the golden timeline shared with the engine", () => {
  const timeline = decodeTimeline(golden());

  it("carries the frame rate and counts from the header", () => {
    expect(timeline.frameRateHz).toBe(44_100 / 512);
    expect(timeline.frameCount).toBe(GOLDEN_FRAMES);
    expect(timeline.barCount).toBe(GOLDEN_BARS);
  });

  it("has the length the contract gives", () => {
    expect(golden().byteLength).toBe(timelineLength(GOLDEN_FRAMES, GOLDEN_BARS));
  });

  it("lists a bar's peaks until the first empty row", () => {
    expect(peaksOf(timeline, 0)).toEqual([
      { freqHz: 55, amp: 1 },
      { freqHz: 110, amp: 0.5 },
    ]);
    expect(peaksOf(timeline, 1)).toEqual([]);
  });

  it("reads 64 bands per frame", () => {
    expect(Array.from(bandsOf(timeline, 0))).toEqual(
      Array.from({ length: BAND_COUNT }, (_, i) => i),
    );
    expect(bandsOf(timeline, 4)[0]).toBe(0);
    expect(bandsOf(timeline, 3)[63]).toBe(255);
  });

  it("reads levels as kick, bass, mid, high and energy", () => {
    expect(levelOf(timeline, 0, "bass")).toBeCloseTo(64 / 255);
    expect(levelOf(timeline, 0, "energy")).toBe(1);
    expect(levelOf(timeline, 1, "kick")).toBe(1);
    expect(levelOf(timeline, 1, "bass")).toBe(0);
  });

  it("reads 200 fourier bins per bar", () => {
    const first = fourierOf(timeline, 0);
    const second = fourierOf(timeline, 1);
    expect(first.length).toBe(FOURIER_BIN_COUNT);
    expect([first[0], first[199], second[0], second[199]]).toEqual([0, 255, 255, 0]);
  });
});

describe("decoding refuses", () => {
  it("another protocol version", () => {
    expect(() => decodeTimeline(patched(0, 2))).toThrow(TimelineError);
  });

  it("a timeline without frames", () => {
    expect(() => decodeTimeline(patched(8, 0))).toThrow(TimelineError);
  });

  it("a cut timeline", () => {
    expect(() => decodeTimeline(golden().slice(0, -1))).toThrow(TimelineError);
  });

  it("a buffer shorter than the header", () => {
    expect(() => decodeTimeline(new ArrayBuffer(8))).toThrow(TimelineError);
  });
});

describe("fourier bins", () => {
  it("run from 30 to 600 Hz on a log scale", () => {
    expect(fourierBinHz(0)).toBeCloseTo(30);
    expect(fourierBinHz(FOURIER_BIN_COUNT - 1)).toBeCloseTo(600);
    expect(fourierBinHz(99.5)).toBeCloseTo(Math.sqrt(30 * 600));
  });
});
