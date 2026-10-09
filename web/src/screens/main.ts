import { element } from "../app/dom";
import { bpmText, clockText } from "../app/format";
import type { LoadedTrack } from "../app/session";
import { beatAt, sectionAt } from "../contract/lookup";
import { SECTION_LABELS } from "./sections";

export const SEEK_STEP_S = 10;

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

export function mountMain(
  root: Document,
  onSeek: (timeS: number) => void,
  currentTimeS: () => number,
): MainScreen {
  const bpm = element(root, "#bpm", HTMLElement);
  const beats = Array.from(element(root, "#beats", HTMLDivElement).children);
  const strip = element(root, "#sections", HTMLDivElement);
  const playhead = element(root, "#playhead", HTMLDivElement);
  let track: LoadedTrack<AudioBuffer> | null = null;
  let spans: HTMLSpanElement[] = [];

  strip.addEventListener("click", (event) => {
    if (track !== null) {
      const box = strip.getBoundingClientRect();
      onSeek(((event.clientX - box.left) / box.width) * track.info.durationS);
    }
  });
  strip.addEventListener("keydown", (event) => {
    const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (direction !== 0) {
      event.preventDefault();
      onSeek(currentTimeS() + direction * SEEK_STEP_S);
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
    draw({ timeS }) {
      if (track === null) {
        return;
      }
      const { info } = track;
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
