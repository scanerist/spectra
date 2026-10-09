export const BEATS_PER_BAR = 4;
const SECONDS_PER_MINUTE = 60;

export interface BeatGrid {
  readonly bpm: number;
  readonly beatOffsetS: number;
}

export interface BeatPosition {
  readonly beat: number;
  readonly beatInBar: number;
  readonly phase: number;
}

export interface Span {
  readonly startS: number;
  readonly endS: number;
}

export function beatDurationS(grid: BeatGrid): number {
  return SECONDS_PER_MINUTE / grid.bpm;
}

export function frameAt(timeS: number, frameRateHz: number, frameCount: number): number {
  return clamp(Math.floor(timeS * frameRateHz), 0, frameCount - 1);
}

export function beatAt(timeS: number, grid: BeatGrid): BeatPosition {
  const beats = (timeS - grid.beatOffsetS) / beatDurationS(grid);
  const beat = Math.floor(beats);
  return {
    beat,
    beatInBar: ((beat % BEATS_PER_BAR) + BEATS_PER_BAR) % BEATS_PER_BAR,
    phase: beats - beat,
  };
}

export function barAt(timeS: number, grid: BeatGrid, barCount: number): number {
  return clamp(Math.floor(beatAt(timeS, grid).beat / BEATS_PER_BAR), 0, barCount - 1);
}

export function sectionAt(timeS: number, sections: readonly Span[]): number {
  const index = sections.findIndex((section) => timeS < section.endS);
  return index === -1 ? sections.length - 1 : index;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}
