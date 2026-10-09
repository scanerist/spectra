import { element } from "../app/dom";
import { bpmText, clockText } from "../app/format";
import type { LoadedTrack } from "../app/session";
import { beatAt, frameAt, sectionAt } from "../contract/lookup";
import { bandsOf } from "../contract/timeline";
import { pixelView } from "../pixel/canvas";
import { bandHistory } from "../view/bands";
import { drawDecomposition, drawRidge, drawSignal, drawSpectrum } from "./main-views";
import { SECTION_LABELS } from "./sections";

export const SEEK_STEP_S = 10;
export const RIDGE_ROWS = 28;
export const HISTORY_STEP_FRAMES = 3;
const SIGNAL_SIZE = 2048;

export interface Moment {
  readonly timeS: number;
  readonly clockS: number;
  readonly dtS: number;
  readonly running: boolean;
}

export interface MainScreen {
  enter(track: LoadedTrack<AudioBuffer>): void;
  draw(moment: Moment): void;
}

export interface MainControls {
  readonly seek: (timeS: number) => void;
  readonly timeS: () => number;
  readonly waveform: (samples: Float32Array<ArrayBuffer>) => boolean;
}

export function mountMain(root: Document, controls: MainControls): MainScreen {
  const bpm = element(root, "#bpm", HTMLElement);
  const beats = Array.from(element(root, "#beats", HTMLDivElement).children);
  const strip = element(root, "#sections", HTMLDivElement);
  const playhead = element(root, "#playhead", HTMLDivElement);
  const ridge = pixelView(element(root, "#c-ridge", HTMLCanvasElement), 3);
  const signal = pixelView(element(root, "#c-signal", HTMLCanvasElement), 2);
  const decomposition = pixelView(element(root, "#c-decomposition", HTMLCanvasElement), 2);
  const spectrum = pixelView(element(root, "#c-spectrum", HTMLCanvasElement), 2);
  const samples = new Float32Array(SIGNAL_SIZE);
  let track: LoadedTrack<AudioBuffer> | null = null;
  let spans: HTMLSpanElement[] = [];

  strip.addEventListener("click", (event) => {
    if (track !== null) {
      const box = strip.getBoundingClientRect();
      controls.seek(((event.clientX - box.left) / box.width) * track.info.durationS);
    }
  });
  strip.addEventListener("keydown", (event) => {
    const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (direction !== 0) {
      event.preventDefault();
      controls.seek(controls.timeS() + direction * SEEK_STEP_S);
    }
  });

  return {
    enter(loaded) {
      track = loaded;
      bpm.textContent = bpmText(loaded.info.bpm);
      spans = loaded.info.sections.map((section) => {
        const span = root.createElement("span");
        span.style.flex = `${section.endS - section.startS} 1 0`;
        span.title = SECTION_LABELS[section.name];
        return span;
      });
      strip.replaceChildren(...spans, playhead);
    },
    draw({ timeS, clockS }) {
      if (track === null) {
        return;
      }
      const { info, timeline } = track;
      const frame = frameAt(timeS, timeline.frameRateHz, timeline.frameCount);
      const bands = bandsOf(timeline, frame);
      drawRidge(ridge, bandHistory(timeline, frame, RIDGE_ROWS, HISTORY_STEP_FRAMES));
      drawSignal(signal, controls.waveform(samples) ? samples : null);
      drawDecomposition(decomposition, bands, clockS);
      drawSpectrum(spectrum, bands);
      const current = sectionAt(timeS, info.sections);
      info.sections.forEach((section, index) => {
        spans[index]?.classList.toggle("on", index === current);
        spans[index]?.classList.toggle("loud", section.loud);
      });
      const share = info.durationS > 0 ? timeS / info.durationS : 0;
      playhead.style.left = `${(share * 100).toFixed(2)}%`;
      strip.setAttribute("aria-valuenow", String(Math.round(share * 100)));
      const section = info.sections[current];
      strip.setAttribute(
        "aria-valuetext",
        `${clockText(timeS)}${section === undefined ? "" : `, ${SECTION_LABELS[section.name]}`}`,
      );
      const { beatInBar } = beatAt(timeS, { bpm: info.bpm, beatOffsetS: info.beatOffsetS });
      beats.forEach((beat, index) => {
        beat.className = index === beatInBar ? "now" : index < beatInBar ? "past" : "";
      });
    },
  };
}
