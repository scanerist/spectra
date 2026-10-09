import { describe, expect, it } from "vitest";
import { BAND_COUNT, type Timeline } from "../../src/contract/timeline";
import { bandHistory, strongestBands } from "../../src/view/bands";

function timelineOf(frames: number): Timeline {
  const bands = new Uint8Array(frames * BAND_COUNT);
  for (let frame = 0; frame < frames; frame += 1) {
    bands.fill(frame, frame * BAND_COUNT, (frame + 1) * BAND_COUNT);
  }
  return {
    frameRateHz: 44_100 / 512,
    frameCount: frames,
    barCount: 1,
    peaks: new Float32Array(16),
    bands,
    levels: new Uint8Array(frames * 5),
    fourier: new Uint8Array(200),
  };
}

describe("the strongest bands", () => {
  it("are local maxima, strongest first, returned in band order", () => {
    const bands = new Uint8Array(BAND_COUNT);
    bands.set([0, 9, 0, 0, 5, 0, 0, 7, 0], 0);
    expect(strongestBands(bands, 2)).toEqual([1, 7]);
  });

  it("are at most six by default", () => {
    const bands = Uint8Array.from({ length: BAND_COUNT }, (_, band) => (band % 2 === 1 ? band : 0));
    expect(strongestBands(bands)).toEqual([51, 53, 55, 57, 59, 61]);
  });

  it("ignore the edge bands, which have one neighbour", () => {
    const bands = new Uint8Array(BAND_COUNT);
    bands[0] = 255;
    bands[63] = 255;
    expect(strongestBands(bands)).toEqual([2, 3, 4, 5, 6, 7]);
  });

  it("fall back to the lowest bands on silence", () => {
    expect(strongestBands(new Uint8Array(BAND_COUNT), 3)).toEqual([1, 2, 3]);
  });
});

describe("the band history", () => {
  const timeline = timelineOf(100);

  it("runs from the oldest row to the current frame", () => {
    const rows = bandHistory(timeline, 50, 4, 2).map((row) => row[0]);
    expect(rows).toEqual([44, 46, 48, 50]);
  });

  it("repeats the first frame at the start of the track", () => {
    const rows = bandHistory(timeline, 1, 3, 2).map((row) => row[0]);
    expect(rows).toEqual([0, 0, 1]);
  });
});
