import { element } from "../app/dom";
import type { LoadedTrack } from "../app/session";
import { barAt, frameAt } from "../contract/lookup";
import { pixelView } from "../pixel/canvas";
import { bandHistory } from "../view/bands";
import { type BarSnapshot, FourierMorph, snapshotOf } from "../view/fourier";
import { createWindingView, drawEpicycles, drawMagnitude, drawWire } from "./analysis-views";
import { HISTORY_STEP_FRAMES, type Moment } from "./main";

export const WIRE_ROWS = 22;

export interface AnalysisScreen {
  enter(track: LoadedTrack<AudioBuffer>): void;
  draw(moment: Moment): void;
}

export function mountAnalysis(
  root: Document,
  sampleRateHz: () => number,
  random: () => number,
): AnalysisScreen {
  const wire = pixelView(element(root, "#c-wire", HTMLCanvasElement), 3);
  const epicycles = pixelView(element(root, "#c-epicycles", HTMLCanvasElement), 2);
  const winding = pixelView(element(root, "#c-winding", HTMLCanvasElement), 2);
  const magnitude = pixelView(element(root, "#c-magnitude", HTMLCanvasElement), 2);
  let track: LoadedTrack<AudioBuffer> | null = null;
  let morph = new FourierMorph(random);
  let bar = -1;
  let snapshot: BarSnapshot | null = null;
  let drawWinding: ReturnType<typeof createWindingView> | null = null;

  return {
    enter(loaded) {
      track = loaded;
      morph = new FourierMorph(random);
      bar = -1;
      snapshot = null;
      drawWinding = createWindingView(sampleRateHz());
    },
    draw({ timeS, dtS, running, motionS }) {
      if (track === null || drawWinding === null) {
        return;
      }
      const { info, timeline } = track;
      const currentBar = barAt(
        timeS,
        { bpm: info.bpm, beatOffsetS: info.beatOffsetS },
        timeline.barCount,
      );
      if (currentBar !== bar || snapshot === null) {
        bar = currentBar;
        snapshot = snapshotOf(timeline, bar);
      }
      morph.step(snapshot, running ? dtS : 0, running);
      const frame = frameAt(timeS, timeline.frameRateHz, timeline.frameCount);
      drawWire(wire, bandHistory(timeline, frame, WIRE_ROWS, HISTORY_STEP_FRAMES));
      drawEpicycles(epicycles, morph.epicycles);
      drawWinding(winding, morph.epicycles, motionS);
      drawMagnitude(magnitude, morph.magnitude, morph.epicycles, motionS);
    },
  };
}
