export const TIMELINE_VERSION = 1;
export const HEADER_BYTES = 16;
export const BAND_COUNT = 64;
export const LEVEL_COUNT = 5;
export const PEAK_SLOTS = 8;
export const FOURIER_BIN_COUNT = 200;
export const FOURIER_LOW_HZ = 30;
export const FOURIER_HIGH_HZ = 600;

const BYTE_SCALE = 255;
const PEAK_FIELDS = 2;
const FLOAT_BYTES = 4;
const LEVELS = ["kick", "bass", "mid", "high", "energy"] as const;

export type Level = (typeof LEVELS)[number];

export interface BarPeak {
  readonly freqHz: number;
  readonly amp: number;
}

export interface Timeline {
  readonly frameRateHz: number;
  readonly frameCount: number;
  readonly barCount: number;
  readonly peaks: Float32Array;
  readonly bands: Uint8Array;
  readonly levels: Uint8Array;
  readonly fourier: Uint8Array;
}

export class TimelineError extends Error {
  override readonly name = "TimelineError";
}

export function timelineLength(frameCount: number, barCount: number): number {
  return (
    HEADER_BYTES +
    barCount * PEAK_SLOTS * PEAK_FIELDS * FLOAT_BYTES +
    frameCount * (BAND_COUNT + LEVEL_COUNT) +
    barCount * FOURIER_BIN_COUNT
  );
}

export function decodeTimeline(buffer: ArrayBuffer): Timeline {
  if (buffer.byteLength < HEADER_BYTES) {
    throw new TimelineError(`a timeline needs ${HEADER_BYTES} header bytes`);
  }
  const header = new DataView(buffer, 0, HEADER_BYTES);
  const version = header.getUint32(0, true);
  const frameRateHz = header.getFloat32(4, true);
  const frameCount = header.getUint32(8, true);
  const barCount = header.getUint32(12, true);
  if (version !== TIMELINE_VERSION) {
    throw new TimelineError(`expected timeline version ${TIMELINE_VERSION}, got ${version}`);
  }
  if (!(Number.isFinite(frameRateHz) && frameRateHz > 0)) {
    throw new TimelineError(`the frame rate must be positive, got ${frameRateHz}`);
  }
  if (frameCount < 1 || barCount < 1) {
    throw new TimelineError("a timeline has at least one frame and one bar");
  }
  const expectedBytes = timelineLength(frameCount, barCount);
  if (buffer.byteLength !== expectedBytes) {
    throw new TimelineError(`expected ${expectedBytes} bytes, got ${buffer.byteLength}`);
  }
  const peakValues = barCount * PEAK_SLOTS * PEAK_FIELDS;
  const peaksBytes = peakValues * FLOAT_BYTES;
  const bandsAt = HEADER_BYTES + peaksBytes;
  const levelsAt = bandsAt + frameCount * BAND_COUNT;
  const fourierAt = levelsAt + frameCount * LEVEL_COUNT;
  return {
    frameRateHz,
    frameCount,
    barCount,
    peaks: readFloats(buffer, HEADER_BYTES, peakValues),
    bands: new Uint8Array(buffer, bandsAt, frameCount * BAND_COUNT),
    levels: new Uint8Array(buffer, levelsAt, frameCount * LEVEL_COUNT),
    fourier: new Uint8Array(buffer, fourierAt, barCount * FOURIER_BIN_COUNT),
  };
}

function readFloats(buffer: ArrayBuffer, offset: number, count: number): Float32Array {
  const view = new DataView(buffer, offset, count * FLOAT_BYTES);
  return Float32Array.from({ length: count }, (_, index) =>
    view.getFloat32(index * FLOAT_BYTES, true),
  );
}

export function bandsOf(timeline: Timeline, frame: number): Uint8Array {
  return timeline.bands.subarray(frame * BAND_COUNT, (frame + 1) * BAND_COUNT);
}

export function levelOf(timeline: Timeline, frame: number, level: Level): number {
  return (timeline.levels[frame * LEVEL_COUNT + LEVELS.indexOf(level)] ?? 0) / BYTE_SCALE;
}

export function fourierOf(timeline: Timeline, bar: number): Uint8Array {
  return timeline.fourier.subarray(bar * FOURIER_BIN_COUNT, (bar + 1) * FOURIER_BIN_COUNT);
}

export function peaksOf(timeline: Timeline, bar: number): BarPeak[] {
  const rows = timeline.peaks.subarray(
    bar * PEAK_SLOTS * PEAK_FIELDS,
    (bar + 1) * PEAK_SLOTS * PEAK_FIELDS,
  );
  const peaks: BarPeak[] = [];
  for (let slot = 0; slot < PEAK_SLOTS; slot += 1) {
    const freqHz = rows[slot * PEAK_FIELDS] ?? 0;
    if (freqHz === 0) {
      break;
    }
    peaks.push({ freqHz, amp: rows[slot * PEAK_FIELDS + 1] ?? 0 });
  }
  return peaks;
}

export function unit(byte: number): number {
  return byte / BYTE_SCALE;
}

export function fourierBinHz(bin: number): number {
  return FOURIER_LOW_HZ * (FOURIER_HIGH_HZ / FOURIER_LOW_HZ) ** (bin / (FOURIER_BIN_COUNT - 1));
}
