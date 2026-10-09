import { type Api, ApiError, PROTOCOL_VERSION, type TrackInfo } from "../contract/api";
import type { Timeline } from "../contract/timeline";
import {
  AudioDecodeError,
  DONE_LABEL,
  ProtocolMismatchError,
  READING_LABEL,
  STAGE_LABELS,
} from "./messages";

export const UPLOAD_SHARE = 0.1;

const AUDIO_EXTENSION = /\.(mp3|wav|flac|ogg|oga)$/i;

export interface LoadedTrack<A> {
  readonly info: TrackInfo;
  readonly timeline: Timeline;
  readonly audio: A;
}

export interface SessionDeps<A> {
  readonly api: Api;
  readonly decode: (data: ArrayBuffer) => Promise<A>;
}

export type ProgressListener = (progress: number, label: string) => void;

type Outcome<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly error: unknown };

export function isAudioFile(file: File): boolean {
  return file.type.startsWith("audio/") || AUDIO_EXTENSION.test(file.name);
}

export async function loadTrack<A>(
  file: File,
  deps: SessionDeps<A>,
  onProgress: ProgressListener,
  signal: AbortSignal,
): Promise<LoadedTrack<A>> {
  if (!isAudioFile(file)) {
    throw new ApiError("unsupported_format", "the file is not audio");
  }
  onProgress(0, READING_LABEL);
  const protocol = await deps.api.protocol(signal);
  if (protocol !== PROTOCOL_VERSION) {
    throw new ProtocolMismatchError(`the engine speaks protocol ${protocol}`);
  }
  const data = await file.arrayBuffer();
  signal.throwIfAborted();
  const decoded = settle(deps.decode(data.slice(0)));
  const trackId = await deps.api.upload(file, file.name, signal);
  signal.throwIfAborted();
  onProgress(UPLOAD_SHARE, STAGE_LABELS.decoding);
  const info = await analysed(deps.api, trackId, onProgress, signal);
  const [timeline, audio] = await Promise.all([deps.api.timeline(trackId, signal), decoded]);
  signal.throwIfAborted();
  if (!audio.ok) {
    throw new AudioDecodeError(
      audio.error instanceof Error ? audio.error.message : "decoding failed",
    );
  }
  onProgress(1, DONE_LABEL);
  return { info, timeline, audio: audio.value };
}

function analysed(
  api: Api,
  trackId: string,
  onProgress: ProgressListener,
  signal: AbortSignal,
): Promise<TrackInfo> {
  return new Promise((resolve, reject) => {
    const abandon = () => {
      unsubscribe();
      reject(signal.reason);
    };
    const unsubscribe = api.follow(trackId, (event) => {
      switch (event.kind) {
        case "progress":
          onProgress(UPLOAD_SHARE + (1 - UPLOAD_SHARE) * event.progress, STAGE_LABELS[event.stage]);
          return;
        case "ready":
          signal.removeEventListener("abort", abandon);
          resolve(event.info);
          return;
        case "failed":
          signal.removeEventListener("abort", abandon);
          reject(event.error);
          return;
      }
    });
    signal.addEventListener("abort", abandon, { once: true });
  });
}

async function settle<T>(promise: Promise<T>): Promise<Outcome<T>> {
  try {
    return { ok: true, value: await promise };
  } catch (error) {
    return { ok: false, error };
  }
}
