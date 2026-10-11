import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  ApiError,
  createApi,
  type EventStream,
  type Fetch,
  STREAM_RETRIES,
  type TrackEvent,
} from "../../src/contract/api";

const TRACK_JSON = {
  track_id: "9f2c41d07a3b55e1",
  duration_s: 432.17,
  bpm: 128,
  beat_offset_s: 0.312,
  sections: [
    { name: "intro", start_s: 0, end_s: 60.3, loud: false },
    { name: "drop", start_s: 60.3, end_s: 432.17, loud: true },
  ],
};

interface Call {
  readonly url: string;
  readonly init: RequestInit | undefined;
}

function answering(response: () => Response): { fetchFn: Fetch; calls: Call[] } {
  const calls: Call[] = [];
  const fetchFn: Fetch = async (url, init) => {
    calls.push({ url, init });
    return response();
  };
  return { fetchFn, calls };
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

class FakeStream implements EventStream {
  readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
  onerror: ((event: Event) => void) | null = null;
  readyState = 1;
  closed = false;

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(type, listener);
  }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  emit(type: string, data: unknown): void {
    this.emitRaw(type, JSON.stringify(data));
  }

  emitRaw(type: string, data: string): void {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }

  drop(readyState: number): void {
    this.readyState = readyState;
    this.onerror?.(new Event("error"));
  }
}

function following(answer: () => Response = () => json({})): {
  stream: FakeStream;
  streams: FakeStream[];
  events: TrackEvent[];
  urls: string[];
} {
  const streams: FakeStream[] = [];
  const urls: string[] = [];
  const events: TrackEvent[] = [];
  const api = createApi(
    answering(answer).fetchFn,
    (url) => {
      urls.push(url);
      const stream = new FakeStream();
      streams.push(stream);
      return stream;
    },
    async () => {},
  );
  api.follow("9f2c41d07a3b55e1", (event) => events.push(event));
  const [stream] = streams;
  if (stream === undefined) {
    throw new Error("follow opened no stream");
  }
  return { stream, streams, events, urls };
}

async function settled(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) {
      return error;
    }
    throw error;
  }
  throw new Error("expected the call to fail");
}

describe("uploading", () => {
  it("posts the file as the multipart part named file", async () => {
    const { fetchFn, calls } = answering(() => json({ track_id: "9f2c41d07a3b55e1" }, 202));
    const api = createApi(fetchFn, () => new FakeStream());
    const trackId = await api.upload(new Blob(["RIFF"]));
    expect(trackId).toBe("9f2c41d07a3b55e1");
    expect(calls[0]?.url).toBe("/tracks");
    expect(calls[0]?.init?.method).toBe("POST");
    const form = calls[0]?.init?.body;
    expect(form instanceof FormData && form.get("file") instanceof Blob).toBe(true);
  });

  it("keeps the name of the file on the listener's computer", async () => {
    const { fetchFn, calls } = answering(() => json({ track_id: "9f2c41d07a3b55e1" }, 202));
    const api = createApi(fetchFn, () => new FakeStream());
    await api.upload(new File(["RIFF"], "Personal Mix 2026.wav"));
    const form = calls[0]?.init?.body;
    const part = form instanceof FormData ? form.get("file") : null;
    expect(part instanceof File && part.name).toBe("track");
  });

  it("surfaces the contract error code and Retry-After", async () => {
    const limited = json({ error: "rate_limited", message: "too many" }, 429, {
      "retry-after": "42",
    });
    const api = createApi(answering(() => limited).fetchFn, () => new FakeStream());
    const error = await rejection(api.upload(new Blob(["RIFF"])));
    expect([error.code, error.retryAfterS]).toEqual(["rate_limited", 42]);
  });

  it("treats an unknown error code as internal", async () => {
    const odd = json({ error: "teapot", message: "short and stout" }, 418);
    const api = createApi(answering(() => odd).fetchFn, () => new FakeStream());
    expect((await rejection(api.upload(new Blob(["x"])))).code).toBe("internal");
  });

  it("reports an unreachable engine as unavailable", async () => {
    const offline: Fetch = async () => {
      throw new TypeError("failed to fetch");
    };
    const api = createApi(offline, () => new FakeStream());
    expect((await rejection(api.upload(new Blob(["x"])))).code).toBe("unavailable");
  });

  it("lets an abandoned upload stop with the abandoning reason", async () => {
    const abandoned = new AbortController();
    const reason = new DOMException("left the screen", "AbortError");
    const fetchFn: Fetch = async (_url, init) => {
      expect(init?.signal).toBe(abandoned.signal);
      abandoned.abort(reason);
      throw reason;
    };
    const api = createApi(fetchFn, () => new FakeStream());
    await expect(api.upload(new Blob(["x"]), abandoned.signal)).rejects.toBe(reason);
  });

  it.each([502, 503, 504])("reports a %i proxy page as unavailable", async (status) => {
    const gateway = () => new Response("<html>bad gateway</html>", { status });
    const api = createApi(answering(gateway).fetchFn, () => new FakeStream());
    expect((await rejection(api.upload(new Blob(["x"])))).code).toBe("unavailable");
  });

  it("reports any other page without an error body as internal", async () => {
    const odd = () => new Response("<html>teapot</html>", { status: 418 });
    const api = createApi(answering(odd).fetchFn, () => new FakeStream());
    expect((await rejection(api.upload(new Blob(["x"])))).code).toBe("internal");
  });
});

describe("checking the engine", () => {
  it("reads the protocol version from the health check", async () => {
    const { fetchFn, calls } = answering(() => json({ ok: true, protocol: 1 }));
    const api = createApi(fetchFn, () => new FakeStream());
    expect(await api.protocol()).toBe(1);
    expect(calls.map((call) => call.url)).toEqual(["/health"]);
  });
});

describe("reading a track", () => {
  it("maps the metadata to camel case", async () => {
    const api = createApi(answering(() => json(TRACK_JSON)).fetchFn, () => new FakeStream());
    const info = await api.track("9f2c41d07a3b55e1");
    expect(info).toEqual({
      trackId: "9f2c41d07a3b55e1",
      durationS: 432.17,
      bpm: 128,
      beatOffsetS: 0.312,
      sections: [
        { name: "intro", startS: 0, endS: 60.3, loud: false },
        { name: "drop", startS: 60.3, endS: 432.17, loud: true },
      ],
    });
  });

  it("refuses metadata that breaks the contract", async () => {
    const broken = {
      ...TRACK_JSON,
      sections: [{ name: "chorus", start_s: 0, end_s: 1, loud: true }],
    };
    const api = createApi(answering(() => json(broken)).fetchFn, () => new FakeStream());
    expect((await rejection(api.track("9f2c41d07a3b55e1"))).code).toBe("internal");
  });

  it("decodes the timeline", async () => {
    const golden = readFileSync(
      new URL("../../../tests/contract/golden/timeline_v1.bin", import.meta.url),
    );
    const api = createApi(answering(() => new Response(golden)).fetchFn, () => new FakeStream());
    expect((await api.timeline("9f2c41d07a3b55e1")).frameCount).toBe(70);
  });
});

describe("following the analysis", () => {
  it("opens the track's event stream", () => {
    expect(following().urls).toEqual(["/tracks/9f2c41d07a3b55e1/events"]);
  });

  it("passes progress on and settles with ready", () => {
    const { stream, events } = following();
    stream.emit("progress", { stage: "tempo", progress: 0.55 });
    stream.emit("ready", TRACK_JSON);
    expect(events.map((event) => event.kind)).toEqual(["progress", "ready"]);
    expect(events[0]).toEqual({ kind: "progress", stage: "tempo", progress: 0.55 });
    expect(stream.closed).toBe(true);
  });

  it("settles with the failure the engine reports", () => {
    const { stream, events } = following();
    stream.emit("failed", { error: "undecodable", message: "lost sync" });
    const last = events.at(-1);
    expect(last?.kind === "failed" && last.error.code).toBe("undecodable");
    expect(stream.closed).toBe(true);
  });

  it("asks for the track when the stream closes and settles with it when ready", async () => {
    const { stream, events } = following(() => json(TRACK_JSON));
    stream.drop(2);
    await settled();
    expect(events.map((event) => event.kind)).toEqual(["ready"]);
  });

  it("settles with the track's error when the stream closes on a failed track", async () => {
    const { stream, events } = following(() =>
      json({ error: "undecodable", message: "lost sync" }, 422),
    );
    stream.drop(2);
    await settled();
    const last = events.at(-1);
    expect(last?.kind === "failed" && last.error.code).toBe("undecodable");
  });

  it("opens the stream again while the track is still analysing", async () => {
    const { stream, streams, events, urls } = following(() =>
      json({ error: "not_ready", message: "running" }, 409),
    );
    stream.drop(2);
    await settled();
    expect(events).toEqual([]);
    expect(urls).toHaveLength(2);
    streams[1]?.emit("ready", TRACK_JSON);
    expect(events.map((event) => event.kind)).toEqual(["ready"]);
  });

  it("lets the browser reconnect while the stream is only interrupted", () => {
    const { stream, events } = following();
    stream.drop(0);
    expect(events).toEqual([]);
  });

  it("asks for the track after the stream keeps dropping while it reconnects", async () => {
    const { stream, events } = following(() => json(TRACK_JSON));
    for (let drop = 1; drop < STREAM_RETRIES; drop += 1) {
      stream.drop(0);
    }
    await settled();
    expect(events).toEqual([]);
    stream.drop(0);
    await settled();
    expect(stream.closed).toBe(true);
    expect(events.map((event) => event.kind)).toEqual(["ready"]);
  });

  it("counts drops again after an event arrives", async () => {
    const { stream, events } = following(() => json(TRACK_JSON));
    for (let drop = 1; drop < STREAM_RETRIES; drop += 1) {
      stream.drop(0);
    }
    stream.emit("progress", { stage: "tempo", progress: 0.55 });
    stream.drop(0);
    await settled();
    expect(events.map((event) => event.kind)).toEqual(["progress"]);
  });

  it("reports an unreachable engine once the stream keeps dropping", async () => {
    const streams: FakeStream[] = [];
    const events: TrackEvent[] = [];
    const api = createApi(
      async () => {
        throw new TypeError("network down");
      },
      () => {
        const stream = new FakeStream();
        streams.push(stream);
        return stream;
      },
      async () => {},
    );
    api.follow("9f2c41d07a3b55e1", (event) => events.push(event));
    for (let drop = 0; drop < STREAM_RETRIES; drop += 1) {
      streams[0]?.drop(0);
    }
    await settled();
    const last = events.at(-1);
    expect(last?.kind === "failed" && last.error.code).toBe("unavailable");
  });

  it("settles as failed when the ready event breaks the contract", () => {
    const { stream, events } = following();
    stream.emit("ready", { ...TRACK_JSON, bpm: "fast" });
    const last = events.at(-1);
    expect(events).toHaveLength(1);
    expect(last?.kind === "failed" && last.error.code).toBe("internal");
    expect(stream.closed).toBe(true);
  });

  it("settles as failed when an event is not json", () => {
    const { stream, events } = following();
    stream.emitRaw("progress", "{oops");
    expect(events.map((event) => event.kind)).toEqual(["failed"]);
    expect(stream.closed).toBe(true);
  });

  it("ignores events after settling", () => {
    const { stream, events } = following();
    stream.emit("failed", { error: "undecodable", message: "lost sync" });
    stream.emit("ready", TRACK_JSON);
    expect(events.map((event) => event.kind)).toEqual(["failed"]);
  });
});
