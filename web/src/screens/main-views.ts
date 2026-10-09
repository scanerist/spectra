import { BAND_COUNT, unit } from "../contract/timeline";
import { clear, type PixelView } from "../pixel/canvas";
import { ink, type Point, polyline } from "../pixel/draw";
import { ACC, BG, INK } from "../pixel/palette";
import { DECOMPOSITION_BANDS, strongestBands } from "../view/bands";

const TURN_RAD = 2 * Math.PI;
const SIGNAL_SAMPLES = 1300;

export function drawRidge(view: PixelView, rows: readonly Uint8Array[]): void {
  const { target, width, height } = view;
  clear(view);
  const last = Math.max(1, rows.length - 1);
  rows.forEach((row, index) => {
    const depth = index / last;
    const baseY = height * 0.1 + depth * height * 0.82;
    const amp = height * 0.36 * (0.45 + 0.55 * depth);
    const inset = (1 - depth) * width * 0.17;
    const left = Math.round(width * 0.04 + inset);
    const right = Math.round(width * 0.96 - inset);
    const yAt = (x: number) => {
      const share = (x - left) / Math.max(1, right - left);
      const position = share * (BAND_COUNT - 1);
      const band = Math.min(BAND_COUNT - 2, Math.floor(position));
      const blend = position - band;
      const level = unit(row[band] ?? 0) * (1 - blend) + unit(row[band + 1] ?? 0) * blend;
      return baseY - level * amp * Math.sin(Math.PI * share) ** 0.7;
    };
    ink(target, BG);
    for (let x = left; x <= right; x += 1) {
      const y = Math.round(yAt(x));
      target.fillRect(x, y, 1, Math.max(1, Math.round(baseY) - y + 1));
    }
    const front = index === rows.length - 1;
    ink(target, front ? ACC : INK, front ? 1 : 0.12 + 0.6 * depth);
    polyline(
      target,
      Array.from(
        { length: right - left + 1 },
        (_, offset): Point => [left + offset, yAt(left + offset)],
      ),
    );
  });
  target.globalAlpha = 1;
}

export function drawSignal(view: PixelView, samples: Float32Array | null): void {
  const { target, width, height } = view;
  clear(view);
  ink(target, INK, 0.12);
  target.fillRect(0, Math.round(height / 2), width, 1);
  if (samples === null) {
    target.globalAlpha = 1;
    return;
  }
  const span = Math.min(samples.length, SIGNAL_SAMPLES);
  ink(target, INK, 0.9);
  polyline(
    target,
    Array.from(
      { length: width },
      (_, x): Point => [
        x,
        height / 2 - (samples[Math.floor((x / width) * span)] ?? 0) * height * 0.42,
      ],
    ),
  );
  target.globalAlpha = 1;
}

export function drawDecomposition(view: PixelView, bands: Uint8Array, motionS: number): void {
  const { target, width, height } = view;
  clear(view);
  const strongest = strongestBands(bands);
  const rowHeight = height / DECOMPOSITION_BANDS;
  const top = strongest.reduce(
    (best, band) => (unit(bands[band] ?? 0) > unit(bands[best] ?? 0) ? band : best),
    strongest[0] ?? -1,
  );
  strongest.forEach((band, row) => {
    const amp = Math.min(1, unit(bands[band] ?? 0) * 1.4);
    const cycles = 1.2 + band / 7;
    const centreY = rowHeight * (row + 0.5);
    ink(target, band === top ? ACC : INK, band === top ? 1 : 0.3 + 0.6 * amp);
    polyline(
      target,
      Array.from(
        { length: width + 1 },
        (_, x): Point => [
          x,
          centreY -
            amp *
              rowHeight *
              0.42 *
              Math.sin((TURN_RAD * cycles * x) / width + motionS * (0.8 + row * 0.5) * TURN_RAD),
        ],
      ),
    );
  });
  target.globalAlpha = 1;
}

export function drawSpectrum(view: PixelView, bands: Uint8Array): void {
  const { target, width, height } = view;
  clear(view);
  const highlighted = new Set(strongestBands(bands));
  const barWidth = width / BAND_COUNT;
  for (let band = 0; band < BAND_COUNT; band += 1) {
    const barHeight = Math.round(unit(bands[band] ?? 0) * height * 0.92);
    const strong = highlighted.has(band);
    ink(target, strong ? ACC : INK, strong ? 1 : 0.5);
    target.fillRect(
      Math.floor(band * barWidth),
      height - barHeight,
      Math.max(1, Math.floor(barWidth) - 1),
      barHeight,
    );
  }
  target.globalAlpha = 1;
}
