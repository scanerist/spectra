import { describe, expect, it } from "vitest";
import { AudioDecodeError, messageFor, ProtocolMismatchError } from "../../src/app/messages";
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
  following = 0;
  constructor(
    private readonly events: TrackEvent[],
    private readonly uploadError: ApiError | null = null,
    private readonly protocolVersion = 1,
  ) {}

  async protocol(): Promise<number> {
    return this.protocolVersion;
  }

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
    this.following += 1;
    queueMicrotask(() => {
      for (const event of this.events) {
        onEvent(event);
      }
    });
    return () => {
      this.following -= 1;
    };
  }
}

const LIVE = new AbortController().signal;
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
    const loaded = await loadTrack(
      WAV,
      { api, decode: async () => "audio" },
      (share, label) => progress.push([share, label]),
      LIVE,
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
      await rejection(loadTrack(WAV, { api, decode: async () => "audio" }, () => undefined, LIVE)),
    ).toBe(failed);
  });

  it("stops when the browser cannot decode the file for playback", async () => {
    const decode = async (): Promise<string> => {
      throw new DOMException("unable to decode", "EncodingError");
    };
    const error = await rejection(
      loadTrack(WAV, { api: new FakeApi(READY), decode }, () => undefined, LIVE),
    );
    expect(error).toBeInstanceOf(AudioDecodeError);
  });

  it("refuses a file that is not audio before uploading it", async () => {
    const api = new FakeApi(READY);
    const text = new File(["hello"], "notes.txt", { type: "text/plain" });
    const error = await rejection(
      loadTrack(text, { api, decode: async () => "audio" }, () => undefined, LIVE),
    );
    expect(error instanceof ApiError && error.code).toBe("unsupported_format");
    expect(api.uploads).toEqual([]);
  });

  it("stops following the analysis once abandoned", async () => {
    const api = new FakeApi([{ kind: "progress", stage: "tempo", progress: 0.2 }]);
    const abandoned = new AbortController();
    const loading = loadTrack(
      WAV,
      { api, decode: async () => "audio" },
      (_share, label) => {
        if (label === "ищу темп") {
          abandoned.abort(new DOMException("left the screen", "AbortError"));
        }
      },
      abandoned.signal,
    );
    const error = await rejection(loading);
    expect(error instanceof DOMException && error.name).toBe("AbortError");
    expect(api.following).toBe(0);
  });

  it("does not upload a file abandoned while reading it", async () => {
    const api = new FakeApi(READY);
    const abandoned = new AbortController();
    abandoned.abort();
    await rejection(
      loadTrack(WAV, { api, decode: async () => "audio" }, () => undefined, abandoned.signal),
    );
    expect(api.uploads).toEqual([]);
  });

  it("asks for a reload before uploading to an engine that speaks another protocol", async () => {
    const api = new FakeApi(READY, null, 2);
    const error = await rejection(
      loadTrack(WAV, { api, decode: async () => "audio" }, () => undefined, LIVE),
    );
    expect(error).toBeInstanceOf(ProtocolMismatchError);
    expect(messageFor(error)).toContain("обнови страницу");
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
    expect(messageFor(new ApiError("track_not_found", ""))).toContain("закинь его ещё раз");
  });

  it("never show the engine's own message", () => {
    expect(messageFor(new ApiError("undecodable", "lost sync in frame 12"))).not.toContain("sync");
  });
});
