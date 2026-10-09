import { describe, expect, it } from "vitest";
import { AudioDecodeError, messageFor } from "../../src/app/messages";
import { isAudioFile, loadTrack, UPLOAD_SHARE } from "../../src/app/session";
import { type Api, ApiError, type TrackEvent, type TrackInfo } from "../../src/contract/api";
import type { Timeline } from "../../src/contract/timeline";

const INFO: TrackInfo = {
  trackId: "9f2c41d07a3b55e1",
  durationS: 12,
  bpm: 128,
  beatOffsetS: 0.1,
  sections: [{ name: "drop", startS: 0, endS: 12, loud: true }],
};
const TIMELINE = { frameCount: 1 } as Timeline;

class FakeApi implements Api {
  uploads: string[] = [];
  constructor(
    private readonly events: TrackEvent[],
    private readonly uploadError: ApiError | null = null,
  ) {}

  async upload(_file: Blob, filename: string): Promise<string> {
    if (this.uploadError !== null) {
      throw this.uploadError;
    }
    this.uploads.push(filename);
    return INFO.trackId;
  }

  async track(): Promise<TrackInfo> {
    return INFO;
  }

  async timeline(): Promise<Timeline> {
    return TIMELINE;
  }

  follow(_trackId: string, onEvent: (event: TrackEvent) => void): () => void {
    queueMicrotask(() => {
      for (const event of this.events) {
        onEvent(event);
      }
    });
    return () => undefined;
  }
}

const WAV = new File(["RIFF"], "kicks.wav", { type: "audio/wav" });
const READY: TrackEvent[] = [
  { kind: "progress", stage: "tempo", progress: 0.55 },
  { kind: "ready", info: INFO },
];

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected loading to fail");
}

describe("loading a track", () => {
  it("uploads the file, follows the analysis and returns everything needed to play", async () => {
    const api = new FakeApi(READY);
    const progress: [number, string][] = [];
    const loaded = await loadTrack(WAV, { api, decode: async () => "audio" }, (share, label) =>
      progress.push([share, label]),
    );
    expect(loaded).toEqual({ info: INFO, timeline: TIMELINE, audio: "audio" });
    expect(api.uploads).toEqual(["kicks.wav"]);
    expect(progress).toEqual([
      [0, "читаю файл"],
      [UPLOAD_SHARE, "декодирую"],
      [UPLOAD_SHARE + (1 - UPLOAD_SHARE) * 0.55, "ищу темп"],
      [1, "готово"],
    ]);
  });

  it("stops with the engine's failure", async () => {
    const failed = new ApiError("analysis_failed", "silence");
    const api = new FakeApi([{ kind: "failed", error: failed }]);
    expect(
      await rejection(loadTrack(WAV, { api, decode: async () => "audio" }, () => undefined)),
    ).toBe(failed);
  });

  it("stops when the browser cannot decode the file for playback", async () => {
    const decode = async (): Promise<string> => {
      throw new DOMException("unable to decode", "EncodingError");
    };
    const error = await rejection(
      loadTrack(WAV, { api: new FakeApi(READY), decode }, () => undefined),
    );
    expect(error).toBeInstanceOf(AudioDecodeError);
  });

  it("refuses a file that is not audio before uploading it", async () => {
    const api = new FakeApi(READY);
    const text = new File(["hello"], "notes.txt", { type: "text/plain" });
    const error = await rejection(
      loadTrack(text, { api, decode: async () => "audio" }, () => undefined),
    );
    expect(error instanceof ApiError && error.code).toBe("unsupported_format");
    expect(api.uploads).toEqual([]);
  });

  it("recognises audio by type or by extension", () => {
    expect(isAudioFile(new File([""], "a.bin", { type: "audio/mpeg" }))).toBe(true);
    expect(isAudioFile(new File([""], "set.FLAC"))).toBe(true);
    expect(isAudioFile(new File([""], "cover.png", { type: "image/png" }))).toBe(false);
  });
});

describe("messages", () => {
  it("tell how long to wait after too many uploads", () => {
    expect(messageFor(new ApiError("rate_limited", "", 61))).toBe(
      "слишком много загрузок. попробуй через 2 мин.",
    );
  });

  it("explain every contract failure in plain words", () => {
    expect(messageFor(new ApiError("unsupported_format", ""))).toContain("mp3, wav, flac или ogg");
    expect(messageFor(new ApiError("busy", ""))).toContain("через минуту");
    expect(messageFor(new ApiError("internal", ""))).toBe("что-то сломалось. попробуй ещё раз.");
  });

  it("never show the engine's own message", () => {
    expect(messageFor(new ApiError("undecodable", "lost sync in frame 12"))).not.toContain("sync");
  });
});
