import { FOURIER_BIN_COUNT, FOURIER_HIGH_HZ, FOURIER_LOW_HZ, unit } from "../contract/timeline";
import { clear, type PixelView } from "../pixel/canvas";
import { dot, ink, type Point, polyline, ring, segment } from "../pixel/draw";
import { ACC, INK } from "../pixel/palette";
import type { Epicycle } from "../view/fourier";

const TURN_RAD = 2 * Math.PI;
const WIRE_COLUMNS = 40;
const WINDOW_SAMPLES = 2048;
const SWEEP_RATE_PER_S = 0.08;
const VISIBLE_AMP = 0.01;
const SILENT_LEVEL = 1e-4;

export function sweepHz(motionS: number): number {
  return FOURIER_LOW_HZ * (FOURIER_HIGH_HZ / FOURIER_LOW_HZ) ** ((motionS * SWEEP_RATE_PER_S) % 1);
}

function binOf(freqHz: number): number {
  return (
    (Math.log(freqHz / FOURIER_LOW_HZ) / Math.log(FOURIER_HIGH_HZ / FOURIER_LOW_HZ)) *
    (FOURIER_BIN_COUNT - 1)
  );
}

export function drawWire(view: PixelView, rows: readonly Uint8Array[]): void {
  const { target, width, height } = view;
  clear(view);
  const last = Math.max(1, rows.length - 1);
  const point = (row: number, column: number): Point => {
    const depth = row / last;
    const across = column / (WIRE_COLUMNS - 1);
    const scale = 0.32 + 0.68 * depth;
    const baseY = height * 0.12 + depth ** 1.5 * height * 0.8;
    const taper = Math.sin(Math.PI * across) ** 0.6;
    const level = unit(rows[row]?.[Math.floor((column * 64) / WIRE_COLUMNS)] ?? 0);
    return [
      width / 2 + (across - 0.5) * width * 0.96 * scale,
      baseY - level * height * 0.36 * scale * taper,
    ];
  };
  ink(target, INK, 0.13);
  for (let column = 0; column < WIRE_COLUMNS; column += 3) {
    polyline(
      target,
      rows.map((_, row) => point(row, column)),
    );
  }
  rows.forEach((_, row) => {
    const front = row === rows.length - 1;
    ink(target, front ? ACC : INK, front ? 1 : 0.14 + (0.62 * row) / last);
    polyline(
      target,
      Array.from({ length: WIRE_COLUMNS }, (_, column) => point(row, column)),
    );
  });
  target.globalAlpha = 1;
}

export function drawEpicycles(view: PixelView, epicycles: readonly Epicycle[]): void {
  const { target, width, height } = view;
  clear(view);
  ink(target, INK, 0.12);
  target.fillRect(0, Math.round(height / 2), width, 1);
  const visible = epicycles.filter((epicycle) => epicycle.amp > VISIBLE_AMP);
  if (visible.length === 0) {
    target.globalAlpha = 1;
    return;
  }
  const ampSum = Math.max(
    0.6,
    visible.reduce((sum, epicycle) => sum + epicycle.amp, 0),
  );
  const centreY = height / 2;
  const radiusScale = (height / 2 - 4) / ampSum;
  let tip: Point = [radiusScale * ampSum + 4, centreY];
  for (const epicycle of visible) {
    const radius = epicycle.amp * radiusScale;
    ink(target, INK, 0.28);
    if (radius > 1) {
      ring(target, tip, radius, radius);
    }
    const next: Point = [
      tip[0] + radius * Math.cos(epicycle.angleRad),
      tip[1] - radius * Math.sin(epicycle.angleRad),
    ];
    ink(target, INK);
    segment(target, tip, next);
    tip = next;
  }
  const traceX = Math.round(2 * radiusScale * ampSum + 10);
  const lowestHz = Math.min(...visible.map((epicycle) => epicycle.freqHz));
  const spanS = 2 / lowestHz;
  const steps = Math.max(1, width - 2 - traceX);
  ink(target, INK, 0.35);
  for (let x = Math.ceil(tip[0]); x < traceX; x += 3) {
    dot(target, x, tip[1]);
  }
  const level = (delayS: number) =>
    visible.reduce(
      (sum, epicycle) =>
        sum + epicycle.amp * Math.sin(epicycle.angleRad - TURN_RAD * epicycle.freqHz * delayS),
      0,
    );
  ink(target, INK, 0.9);
  polyline(
    target,
    Array.from(
      { length: steps },
      (_, step): Point => [traceX + step, centreY - radiusScale * level((step * spanS) / steps)],
    ),
  );
  ink(target, INK);
  target.fillRect(Math.round(tip[0]) - 1, Math.round(tip[1]) - 1, 2, 2);
  target.globalAlpha = 1;
}

export function windowOf(
  epicycles: readonly Epicycle[],
  sampleRateHz: number,
  samples: Float32Array,
): number {
  let peak = 1e-6;
  for (let n = 0; n < samples.length; n += 1) {
    let sum = 0;
    for (const epicycle of epicycles) {
      sum +=
        epicycle.amp *
        Math.sin((TURN_RAD * epicycle.freqHz * n) / sampleRateHz + epicycle.startPhaseRad);
    }
    const value = sum * (0.5 - 0.5 * Math.cos((TURN_RAD * n) / (samples.length - 1)));
    samples[n] = value;
    peak = Math.max(peak, Math.abs(value));
  }
  return peak;
}

export function fourierAt(
  samples: Float32Array,
  freqHz: number,
  sampleRateHz: number,
): readonly [number, number] {
  const stepRad = (TURN_RAD * freqHz) / sampleRateHz;
  let real = 0;
  let imaginary = 0;
  for (let n = 0; n < samples.length; n += 1) {
    const value = samples[n] ?? 0;
    real += value * Math.cos(stepRad * n);
    imaginary -= value * Math.sin(stepRad * n);
  }
  return [real, imaginary];
}

export function createWindingView(sampleRateHz: number) {
  const samples = new Float32Array(WINDOW_SAMPLES);
  return (view: PixelView, epicycles: readonly Epicycle[], motionS: number): void => {
    const { target, width, height } = view;
    clear(view);
    const size = Math.min(width, height);
    const centreX = width / 2;
    const centreY = height / 2;
    ink(target, INK, 0.1);
    target.fillRect(Math.round(centreX - size / 2), Math.round(centreY), size, 1);
    target.fillRect(Math.round(centreX), Math.round(centreY - size / 2), 1, size);
    if (epicycles.length === 0) {
      target.globalAlpha = 1;
      return;
    }
    const peak = windowOf(epicycles, sampleRateHz, samples);
    const freqHz = sweepHz(motionS);
    const stepRad = (TURN_RAD * freqHz) / sampleRateHz;
    const scale = (size / 2 - 3) / peak;
    const points: Point[] = [];
    for (let n = 0; n < samples.length; n += 4) {
      const value = samples[n] ?? 0;
      points.push([
        centreX + value * Math.cos(stepRad * n) * scale,
        centreY + value * Math.sin(stepRad * n) * scale,
      ]);
    }
    ink(target, INK, 0.55);
    polyline(target, points);
    const ampSum = Math.max(
      0.6,
      epicycles.reduce((sum, epicycle) => sum + epicycle.amp, 0),
    );
    const [real, imaginary] = fourierAt(samples, freqHz, sampleRateHz);
    const centroidScale = (0.8 * (size / 2)) / ((ampSum * samples.length) / 4);
    const centroid: Point = [centreX + real * centroidScale, centreY - imaginary * centroidScale];
    ink(target, INK);
    segment(target, [centreX, centreY], centroid);
    target.fillRect(Math.round(centroid[0]) - 1, Math.round(centroid[1]) - 1, 3, 3);
    target.globalAlpha = 1;
  };
}

export function drawMagnitude(
  view: PixelView,
  magnitude: Float32Array,
  epicycles: readonly Epicycle[],
  motionS: number,
): void {
  const { target, width, height } = view;
  clear(view);
  ink(target, INK, 0.12);
  target.fillRect(0, height - 3, width, 1);
  if (Math.max(...magnitude) < SILENT_LEVEL) {
    target.globalAlpha = 1;
    return;
  }
  const x = (bin: number) => 2 + (bin / (FOURIER_BIN_COUNT - 1)) * (width - 4);
  const y = (level: number) => height - 3 - level * (height - 8);
  const curve = Array.from(magnitude, (level, bin): Point => [x(bin), y(level)]);
  const cursor = Math.round(binOf(sweepHz(motionS)));
  ink(target, INK, 0.18);
  polyline(target, curve);
  ink(target, INK);
  polyline(target, curve.slice(0, cursor + 1));
  for (const epicycle of epicycles) {
    ink(target, ACC, Math.min(1, epicycle.amp * 1.5));
    target.fillRect(Math.round(x(binOf(epicycle.freqHz))), height - 2, 1, 2);
  }
  ink(target, INK, 0.5);
  target.fillRect(Math.round(x(cursor)), 2, 1, height - 5);
  target.globalAlpha = 1;
}
