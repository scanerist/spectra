import type { PixelTarget } from "./draw";
import { BG } from "./palette";

export interface PixelView {
  readonly canvas: HTMLCanvasElement;
  readonly target: CanvasRenderingContext2D & PixelTarget;
  width: number;
  height: number;
}

export function pixelView(canvas: HTMLCanvasElement, pixelCssPx: number): PixelView {
  const box = canvas.parentElement;
  const target = canvas.getContext("2d");
  if (box === null || target === null) {
    throw new Error("a pixel canvas needs a parent box and a 2d context");
  }
  const view: PixelView = { canvas, target, width: 1, height: 1 };
  const resize = () => {
    const ratio = window.devicePixelRatio || 1;
    const cellCssPx = Math.max(1, Math.round(pixelCssPx * ratio)) / ratio;
    const rect = box.getBoundingClientRect();
    view.width = Math.max(1, Math.floor(rect.width / cellCssPx));
    view.height = Math.max(1, Math.floor(rect.height / cellCssPx));
    canvas.width = view.width;
    canvas.height = view.height;
    canvas.style.width = `${view.width * cellCssPx}px`;
    canvas.style.height = `${view.height * cellCssPx}px`;
  };
  new ResizeObserver(resize).observe(box);
  resize();
  return view;
}

export function clear(view: PixelView): void {
  view.target.globalAlpha = 1;
  view.target.fillStyle = BG;
  view.target.fillRect(0, 0, view.width, view.height);
}
