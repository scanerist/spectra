import { element } from "../app/dom";
import { clear, pixelView } from "../pixel/canvas";
import { ink, type Point, polyline } from "../pixel/draw";
import { INK } from "../pixel/palette";

const HERO_PIXEL_CSS_PX = 2;
const HERO_PARTIALS: readonly (readonly [number, number])[] = [
  [1.1, 0.9],
  [2.3, 0.5],
  [4.7, 0.3],
  [9.1, 0.18],
  [17, 0.1],
];
const TURN_RAD = 2 * Math.PI;

export interface StartScreen {
  showError(message: string | null): void;
  draw(timeS: number): void;
}

export function mountStart(
  root: Document,
  onFile: (file: File) => void,
  onGesture: () => void,
): StartScreen {
  const drop = element(root, "#drop", HTMLLabelElement);
  const input = element(root, "#file", HTMLInputElement);
  const error = element(root, "#file-error", HTMLParagraphElement);
  const hero = pixelView(element(root, "#c-hero", HTMLCanvasElement), HERO_PIXEL_CSS_PX);
  drop.addEventListener("pointerdown", onGesture);
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    input.value = "";
    if (file !== undefined) {
      onFile(file);
    }
  });
  for (const type of ["dragenter", "dragover"]) {
    drop.addEventListener(type, (event) => {
      event.preventDefault();
      drop.classList.add("over");
    });
  }
  for (const type of ["dragover", "drop"]) {
    root.addEventListener(type, (event) => event.preventDefault());
  }
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("over");
    onGesture();
    const file = event.dataTransfer?.files[0];
    if (file !== undefined) {
      onFile(file);
    }
  });
  return {
    showError(message) {
      error.textContent = message ?? "";
      error.hidden = message === null;
    },
    draw(timeS) {
      const { target, width, height } = hero;
      clear(hero);
      ink(target, INK, 0.12);
      target.fillRect(0, Math.round(height / 2), width, 1);
      const points = Array.from({ length: width + 1 }, (_, x): Point => {
        const level = HERO_PARTIALS.reduce(
          (sum, [cycles, amp], index) =>
            sum + amp * Math.sin((TURN_RAD * cycles * x * 3) / width + timeS * (0.5 + index * 0.4)),
          0,
        );
        return [x, height / 2 - (level / 2) * height * 0.44];
      });
      ink(target, INK, 0.85);
      polyline(target, points);
      target.globalAlpha = 1;
    },
  };
}
