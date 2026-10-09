import { BAND_COUNT, bandsOf, type Timeline } from "../contract/timeline";

export const DECOMPOSITION_BANDS = 6;

export function strongestBands(bands: ArrayLike<number>, count = DECOMPOSITION_BANDS): number[] {
  const maxima: number[] = [];
  for (let band = 1; band < bands.length - 1; band += 1) {
    const level = bands[band] ?? 0;
    if (level >= (bands[band - 1] ?? 0) && level >= (bands[band + 1] ?? 0)) {
      maxima.push(band);
    }
  }
  return maxima
    .sort((left, right) => (bands[right] ?? 0) - (bands[left] ?? 0) || left - right)
    .slice(0, count)
    .sort((left, right) => left - right);
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
