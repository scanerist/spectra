import { describe, expect, it } from "vitest";
import {
  barAt,
  barPosition,
  beatAt,
  beatDurationS,
  frameAt,
  sectionAt,
} from "../../src/contract/lookup";

const FRAME_RATE_HZ = 44_100 / 512;
const GRID = { bpm: 120, beatOffsetS: 0.3 };

function times(count: number): number[] {
  return Array.from({ length: count }, (_, index) => ((index * 7919) % 100_000) / 100 - 50);
}

describe("frames", () => {
  it("start at the frame whose window centre has passed", () => {
    expect(frameAt(0, FRAME_RATE_HZ, 100)).toBe(0);
    expect(frameAt(1 / FRAME_RATE_HZ, FRAME_RATE_HZ, 100)).toBe(1);
    expect(frameAt(1.5 / FRAME_RATE_HZ, FRAME_RATE_HZ, 100)).toBe(1);
  });

  it("stay inside the track", () => {
    expect(frameAt(-3, FRAME_RATE_HZ, 100)).toBe(0);
    expect(frameAt(3_600, FRAME_RATE_HZ, 100)).toBe(99);
  });
});

describe("beats", () => {
  it("last sixty seconds over the tempo", () => {
    expect(beatDurationS(GRID)).toBe(0.5);
  });

  it("count from the start of bar zero", () => {
    expect(beatAt(0.3, GRID)).toEqual({ beat: 0, beatInBar: 0, phase: 0 });
    expect(beatAt(1.05, GRID)).toEqual({ beat: 1, beatInBar: 1, phase: expect.closeTo(0.5) });
    expect(beatAt(2.31, GRID).beatInBar).toBe(0);
  });

  it("continue the grid backwards before the offset", () => {
    const before = beatAt(0.1, GRID);
    expect(before.beat).toBe(-1);
    expect(before.beatInBar).toBe(3);
    expect(before.phase).toBeCloseTo(0.6);
  });

  it("always sit in the bar and in the beat for any time", () => {
    for (const timeS of times(500)) {
      const { beatInBar, phase } = beatAt(timeS, GRID);
      expect(beatInBar).toBeGreaterThanOrEqual(0);
      expect(beatInBar).toBeLessThan(4);
      expect(phase).toBeGreaterThanOrEqual(0);
      expect(phase).toBeLessThan(1);
    }
  });
});

describe("bars", () => {
  it("count continuously from the grid's first downbeat", () => {
    expect(barPosition(0.3, GRID)).toBe(0);
    expect(barPosition(0.3 + 3, GRID)).toBeCloseTo(1.5);
    expect(barPosition(0.1, GRID)).toBeCloseTo(-0.1);
  });

  it("hold four beats", () => {
    expect(barAt(0.3 + 1.99, GRID, 10)).toBe(0);
    expect(barAt(0.3 + 2.01, GRID, 10)).toBe(1);
  });

  it("stay at the first bar before the offset and at the last after the end", () => {
    expect(barAt(0, GRID, 10)).toBe(0);
    expect(barAt(1_000, GRID, 10)).toBe(9);
  });
});

describe("sections", () => {
  const sections = [
    { startS: 0, endS: 10 },
    { startS: 10, endS: 20 },
  ];

  it("are found by the time they cover", () => {
    expect(sectionAt(0, sections)).toBe(0);
    expect(sectionAt(10, sections)).toBe(1);
  });

  it("end with the last one", () => {
    expect(sectionAt(25, sections)).toBe(1);
  });
});
