import { BAND_COUNT, bandsOf, type Timeline } from "../contract/timeline";

export const DECOMPOSITION_BANDS = 6;

export function strongestBands(bands: ArrayLike<number>, count = DECOMPOSITION_BANDS): number[] {
  const peaks = peakBands(bands);
  const rank = (band: number) => (peaks.has(band) ? 1 : 0);
  return Array.from({ length: Math.max(0, bands.length - 2) }, (_, index) => index + 1)
    .sort(
      (left, right) =>
        rank(right) - rank(left) || (bands[right] ?? 0) - (bands[left] ?? 0) || left - right,
    )
    .slice(0, count)
    .sort((left, right) => left - right);
}

function peakBands(bands: ArrayLike<number>): Set<number> {
  const peaks = new Set<number>();
  let start = 0;
  while (start < bands.length) {
    const end = runEnd(bands, start);
    const level = bands[start] ?? 0;
    const rises = start === 0 || (bands[start - 1] ?? 0) < level;
    const falls = end === bands.length - 1 || (bands[end + 1] ?? 0) < level;
    const first = Math.max(start, 1);
    if (rises && falls && first <= Math.min(end, bands.length - 2)) {
      peaks.add(first);
    }
    start = end + 1;
  }
  return peaks;
}

function runEnd(bands: ArrayLike<number>, start: number): number {
  let end = start;
  while (end + 1 < bands.length && bands[end + 1] === bands[start]) {
    end += 1;
  }
  return end;
}

export function bandHistory(
  timeline: Timeline,
  frame: number,
  rows: number,
  stepFrames: number,
): Uint8Array[] {
  return Array.from({ length: rows }, (_, row) =>
    bandsOf(timeline, Math.max(0, frame - (rows - 1 - row) * stepFrames)),
  );
}

export function emptyBands(): Uint8Array {
  return new Uint8Array(BAND_COUNT);
}
