import { describe, expect, it } from "vitest";
import { dot, type PixelTarget, polyline, ring, segment } from "../../src/pixel/draw";

class Recorder implements PixelTarget {
  fillStyle: string | CanvasGradient | CanvasPattern = "";
  globalAlpha = 1;
  readonly pixels: [number, number][] = [];

  fillRect(x: number, y: number, width: number, height: number): void {
    expect([width, height]).toEqual([1, 1]);
    this.pixels.push([x, y]);
  }
}

function drawn(draw: (target: Recorder) => void): [number, number][] {
  const recorder = new Recorder();
  draw(recorder);
  return recorder.pixels;
}

function connected(pixels: [number, number][]): boolean {
  return pixels.every((pixel, index) => {
    const previous = pixels[index - 1];
    return (
      previous === undefined ||
      (Math.abs(pixel[0] - previous[0]) <= 1 && Math.abs(pixel[1] - previous[1]) <= 1)
    );
  });
}

describe("a segment", () => {
  it("covers both ends on whole pixels", () => {
    expect(drawn((target) => segment(target, [0.4, 0.4], [3.4, 0]))).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
      [3, 0],
    ]);
  });

  it("steps diagonally without doubling pixels", () => {
    expect(drawn((target) => segment(target, [0, 0], [3, 3]))).toEqual([
      [0, 0],
      [1, 1],
      [2, 2],
      [3, 3],
    ]);
  });

  it("draws one pixel per step along the longer axis in any direction", () => {
    const pixels = drawn((target) => segment(target, [10, 2], [-5, 9]));
    expect(pixels).toHaveLength(16);
    expect(connected(pixels)).toBe(true);
    expect(pixels.at(-1)).toEqual([-5, 9]);
  });

  it("is a single pixel when both ends meet", () => {
    expect(drawn((target) => segment(target, [2, 2], [2, 2]))).toEqual([[2, 2]]);
  });
});

describe("shapes", () => {
  it("join a polyline without gaps", () => {
    const pixels = drawn((target) =>
      polyline(target, [
        [0, 0],
        [4, 2],
        [4, 6],
      ]),
    );
    expect(connected(pixels)).toBe(true);
  });

  it("close a ring on itself", () => {
    const pixels = drawn((target) => ring(target, [10, 10], 5, 5));
    expect(pixels[0]).toEqual(pixels.at(-1));
    expect(connected(pixels)).toBe(true);
  });

  it("round a dot to the pixel grid", () => {
    expect(drawn((target) => dot(target, 1.6, 2.4))).toEqual([[2, 2]]);
  });
});
