import { decodeTimeline, type Timeline } from "./timeline";

export const PROTOCOL_VERSION = 1;

const ERROR_CODES = [
  "no_file",
  "file_too_large",
  "unsupported_format",
  "undecodable",
  "analysis_failed",
  "track_not_found",
  "not_ready",
  "rate_limited",
  "busy",
  "unavailable",
  "internal",
] as const;
const STAGES = ["decoding", "spectrum", "tempo", "structure"] as const;
const SECTION_NAMES = ["intro", "buildup", "drop", "breakdown", "outro"] as const;

export type ErrorCode = (typeof ERROR_CODES)[number];
export type Stage = (typeof STAGES)[number];
export type SectionName = (typeof SECTION_NAMES)[number];

export interface Section {
  readonly name: SectionName;
  readonly startS: number;
  readonly endS: number;
  readonly loud: boolean;
}

export interface TrackInfo {
  readonly trackId: string;
  readonly durationS: number;
  readonly bpm: number;
  readonly beatOffsetS: number;
  readonly sections: readonly Section[];
}

export type TrackEvent =
  | { readonly kind: "progress"; readonly stage: Stage; readonly progress: number }
  | { readonly kind: "ready"; readonly info: TrackInfo }
  | { readonly kind: "failed"; readonly error: ApiError };

export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly code: ErrorCode,
    message: string,
    readonly retryAfterS: number | null = null,
  ) {
    super(message);
  }
}

export interface EventStream {
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void;
  close(): void;
  onerror: ((event: Event) => void) | null;
  readonly readyState: number;
}

export type Fetch = (input: string, init?: RequestInit) => Promise<Response>;
export type OpenEventStream = (url: string) => EventStream;

const CLOSED = 2;

export interface Api {
  protocol(signal?: AbortSignal): Promise<number>;
  upload(file: Blob, filename: string, signal?: AbortSignal): Promise<string>;
  track(trackId: string): Promise<TrackInfo>;
  timeline(trackId: string, signal?: AbortSignal): Promise<Timeline>;
  follow(trackId: string, onEvent: (event: TrackEvent) => void): () => void;
}

export function createApi(fetchFn: Fetch, openStream: OpenEventStream): Api {
  const request = async (path: string, init?: RequestInit): Promise<Response> => {
    const response = await reach(fetchFn, path, init);
    if (!response.ok) {
      throw await errorOf(response);
    }
    return response;
  };
  return {
    async protocol(signal) {
      const response = await request("/health", { signal: signal ?? null });
      return field(await response.json(), "protocol", isNumber);
    },
    async upload(file, filename, signal) {
      const form = new FormData();
      form.append("file", file, filename);
      const response = await request("/tracks", {
        method: "POST",
        body: form,
        signal: signal ?? null,
      });
      return field(await response.json(), "track_id", isString);
    },
    async track(trackId) {
      const response = await request(`/tracks/${encodeURIComponent(trackId)}`);
      return trackInfo(await response.json());
    },
    async timeline(trackId, signal) {
      const response = await request(`/tracks/${encodeURIComponent(trackId)}/timeline`, {
        signal: signal ?? null,
      });
      return decodeTimeline(await response.arrayBuffer());
    },
    follow(trackId, onEvent) {
      const stream = openStream(`/tracks/${encodeURIComponent(trackId)}/events`);
      let settled = false;
      const settle = (event: TrackEvent) => {
        settled = true;
        stream.close();
        onEvent(event);
      };
      const read = (build: () => TrackEvent) => {
        if (settled) {
          return;
        }
        let event: TrackEvent;
        try {
          event = build();
        } catch (error) {
          settle({ kind: "failed", error: unreadable(error) });
          return;
        }
        if (event.kind === "progress") {
          onEvent(event);
        } else {
          settle(event);
        }
      };
      stream.addEventListener("progress", (event) =>
        read(() => {
          const body = parse(event.data);
          return {
            kind: "progress",
            stage: field(body, "stage", isStage),
            progress: field(body, "progress", isNumber),
          };
        }),
      );
      stream.addEventListener("ready", (event) =>
        read(() => ({ kind: "ready", info: trackInfo(parse(event.data)) })),
      );
      stream.addEventListener("failed", (event) =>
        read(() => ({ kind: "failed", error: errorBody(parse(event.data)) })),
      );
      stream.onerror = () => {
        if (!settled && stream.readyState === CLOSED) {
          settle({ kind: "failed", error: new ApiError("internal", "the event stream closed") });
        }
      };
      return () => {
        settled = true;
        stream.close();
      };
    },
  };
}

async function reach(fetchFn: Fetch, path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetchFn(path, init);
  } catch (error) {
    if (init?.signal?.aborted === true) {
      throw init.signal.reason;
    }
    throw new ApiError(
      "unavailable",
      error instanceof Error ? error.message : "the engine is unreachable",
    );
  }
}

async function errorOf(response: Response): Promise<ApiError> {
  const retryAfterS = retryAfter(response.headers.get("retry-after"));
  try {
    const error = errorBody(await response.json());
    return new ApiError(error.code, error.message, retryAfterS);
  } catch {
    return new ApiError(
      response.status === 503 ? "unavailable" : "internal",
      `HTTP ${response.status}`,
      retryAfterS,
    );
  }
}

function retryAfter(header: string | null): number | null {
  const seconds = header === null ? Number.NaN : Number(header);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

function errorBody(body: unknown): ApiError {
  const code = field(body, "error", isString);
  const message = field(body, "message", isString);
  return new ApiError(isErrorCode(code) ? code : "internal", message);
}

function trackInfo(body: unknown): TrackInfo {
  const sections = field(body, "sections", Array.isArray);
  return {
    trackId: field(body, "track_id", isString),
    durationS: field(body, "duration_s", isNumber),
    bpm: field(body, "bpm", isNumber),
    beatOffsetS: field(body, "beat_offset_s", isNumber),
    sections: sections.map((section: unknown) => ({
      name: field(section, "name", isSectionName),
      startS: field(section, "start_s", isNumber),
      endS: field(section, "end_s", isNumber),
      loud: field(section, "loud", isBoolean),
    })),
  };
}

function unreadable(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("internal", "the engine sent an unreadable event");
}

function parse(data: string): unknown {
  return JSON.parse(data);
}

function field<T>(body: unknown, name: string, guard: (value: unknown) => value is T): T {
  const value =
    typeof body === "object" && body !== null ? (body as Record<string, unknown>)[name] : undefined;
  if (!guard(value)) {
    throw new ApiError("internal", `the engine sent an unexpected ${name}`);
  }
  return value;
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function isErrorCode(value: string): value is ErrorCode {
  return (ERROR_CODES as readonly string[]).includes(value);
}

function isStage(value: unknown): value is Stage {
  return typeof value === "string" && (STAGES as readonly string[]).includes(value);
}

function isSectionName(value: unknown): value is SectionName {
  return typeof value === "string" && (SECTION_NAMES as readonly string[]).includes(value);
}
