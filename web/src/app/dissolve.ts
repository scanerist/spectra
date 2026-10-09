import { ACC, BG } from "../pixel/palette";

export const CELL_CSS_PX = 24;
export const PHASE_MS = 200;
const ACCENT_EVERY = 47;

export type Dissolve = (swap: () => void) => void;

export function shuffledOrder(count: number, random: () => number): number[] {
  const order = Array.from({ length: count }, (_, index) => index);
  for (let index = count - 1; index > 0; index -= 1) {
    const other = Math.floor(random() * (index + 1));
    const value = order[index] ?? index;
    order[index] = order[other] ?? other;
    order[other] = value;
  }
  return order;
}

export function createDissolve(
  canvas: HTMLCanvasElement,
  reducedMotion: boolean,
  random: () => number,
): Dissolve {
  const target = canvas.getContext("2d");
  let busy = false;
  let first = true;
  let covered = false;
  let pending: (() => void) | null = null;
  return (swap) => {
    if (reducedMotion || first || target === null || (busy && covered)) {
      first = false;
      swap();
      return;
    }
    pending = swap;
    if (busy) {
      return;
    }
    busy = true;
    covered = false;
    const columns = Math.ceil(innerWidth / CELL_CSS_PX);
    const rows = Math.ceil(innerHeight / CELL_CSS_PX);
    const cells = columns * rows;
    const order = shuffledOrder(cells, random);
    canvas.width = columns;
    canvas.height = rows;
    canvas.hidden = false;
    const paint = (cell: number) => {
      target.fillStyle = cell % ACCENT_EVERY === 0 ? ACC : BG;
      target.fillRect(cell % columns, Math.floor(cell / columns), 1, 1);
    };
    let startMs: number | null = null;
    const frame = (nowMs: number) => {
      startMs ??= nowMs;
      const elapsedMs = nowMs - startMs;
      target.clearRect(0, 0, columns, rows);
      if (elapsedMs < PHASE_MS) {
        order.slice(0, Math.floor((cells * elapsedMs) / PHASE_MS)).forEach(paint);
      } else {
        if (!covered) {
          covered = true;
          pending?.();
          pending = null;
        }
        const revealed = Math.floor(cells * Math.min(1, (elapsedMs - PHASE_MS) / PHASE_MS));
        order.slice(revealed).forEach(paint);
      }
      if (elapsedMs < 2 * PHASE_MS) {
        requestAnimationFrame(frame);
      } else {
        canvas.hidden = true;
        busy = false;
      }
    };
    requestAnimationFrame(frame);
  };
}
