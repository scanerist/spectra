import { element } from "../app/dom";

export const LOADING_BLOCKS = 20;

export interface LoadingScreen {
  set(progress: number, label: string): void;
}

export function mountLoading(root: Document): LoadingScreen {
  const blocks = element(root, "#blocks", HTMLDivElement);
  const stage = element(root, "#stage", HTMLParagraphElement);
  const cells = Array.from({ length: LOADING_BLOCKS }, () => root.createElement("i"));
  blocks.replaceChildren(...cells);
  return {
    set(progress, label) {
      const lit = Math.round(Math.min(Math.max(progress, 0), 1) * LOADING_BLOCKS);
      cells.forEach((cell, index) => {
        cell.classList.toggle("on", index < lit);
      });
      stage.textContent = label;
    },
  };
}
