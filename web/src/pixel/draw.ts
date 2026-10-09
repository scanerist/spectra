export type Point = readonly [number, number];

export interface PixelTarget {
  fillStyle: string | CanvasGradient | CanvasPattern;
  globalAlpha: number;
  fillRect(x: number, y: number, width: number, height: number): void;
}

const SEGMENT_PIXEL_LIMIT = 8_192;
const TURN_RAD = 2 * Math.PI;
const RING_MIN_POINTS = 12;

export function ink(target: PixelTarget, color: string, alpha = 1): void {
  target.fillStyle = color;
  target.globalAlpha = alpha;
}

export function dot(target: PixelTarget, x: number, y: number): void {
  target.fillRect(Math.round(x), Math.round(y), 1, 1);
}

export function segment(target: PixelTarget, from: Point, to: Point): void {
  let x = Math.round(from[0]);
  let y = Math.round(from[1]);
  const endX = Math.round(to[0]);
  const endY = Math.round(to[1]);
  const dx = Math.abs(endX - x);
  const dy = -Math.abs(endY - y);
  const stepX = x < endX ? 1 : -1;
  const stepY = y < endY ? 1 : -1;
  let error = dx + dy;
  for (let drawn = 0; drawn < SEGMENT_PIXEL_LIMIT; drawn += 1) {
    target.fillRect(x, y, 1, 1);
    if (x === endX && y === endY) {
      return;
    }
    const doubled = 2 * error;
    if (doubled >= dy) {
      error += dy;
      x += stepX;
    }
    if (doubled <= dx) {
      error += dx;
      y += stepY;
    }
  }
}

export function polyline(target: PixelTarget, points: readonly Point[]): void {
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1];
    const to = points[index];
    if (from !== undefined && to !== undefined) {
      segment(target, from, to);
    }
  }
}

export function ring(target: PixelTarget, centre: Point, radiusX: number, radiusY: number): void {
  const count = Math.max(RING_MIN_POINTS, Math.ceil((TURN_RAD * Math.max(radiusX, radiusY)) / 2));
  const points = Array.from({ length: count + 1 }, (_, index): Point => {
    const angleRad = (index / count) * TURN_RAD;
    return [centre[0] + Math.cos(angleRad) * radiusX, centre[1] + Math.sin(angleRad) * radiusY];
  });
  polyline(target, points);
}
