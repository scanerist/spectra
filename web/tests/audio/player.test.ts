import { describe, expect, it } from "vitest";
import { loopTimeS } from "../../src/audio/player";

describe("playback time", () => {
  it("counts from the moment the track started", () => {
    expect(loopTimeS(12.5, 10, 100)).toBeCloseTo(2.5);
  });

  it("loops back to the start after the end", () => {
    expect(loopTimeS(115, 10, 100)).toBeCloseTo(5);
  });

  it("stays inside the track after a seek into the past", () => {
    expect(loopTimeS(9, 10, 100)).toBeCloseTo(99);
  });

  it("is zero without a track", () => {
    expect(loopTimeS(5, 0, 0)).toBe(0);
  });
});
