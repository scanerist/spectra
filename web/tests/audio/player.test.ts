import { describe, expect, it } from "vitest";
import { type Media, seekTargetS, whenPlayable } from "../../src/audio/player";

class FakeMedia extends EventTarget implements Media {
  constructor(
    public readyState = 0,
    public duration = Number.NaN,
  ) {
    super();
  }

  load(durationS: number): void {
    this.duration = durationS;
    this.readyState = 2;
    this.dispatchEvent(new Event("loadeddata"));
  }

  fail(): void {
    this.dispatchEvent(new Event("error"));
  }
}

const PATIENT = new AbortController().signal;

describe("preparing playback", () => {
  it("is ready once the browser has decoded the first frames", async () => {
    const media = new FakeMedia();
    const ready = whenPlayable(media, PATIENT);
    media.load(432.17);
    await expect(ready).resolves.toBeUndefined();
  });

  it("is ready at once when the media already has data", async () => {
    await expect(whenPlayable(new FakeMedia(4, 12), PATIENT)).resolves.toBeUndefined();
  });

  it("fails as soon as the browser cannot play the file", async () => {
    const media = new FakeMedia();
    const ready = whenPlayable(media, PATIENT);
    media.fail();
    await expect(ready).rejects.toThrow("cannot play");
  });

  it("fails on media without a known length", async () => {
    const media = new FakeMedia();
    const ready = whenPlayable(media, PATIENT);
    media.load(Number.POSITIVE_INFINITY);
    await expect(ready).rejects.toThrow("no duration");
  });

  it("fails when the browser loads nothing before the deadline", async () => {
    const deadline = new AbortController();
    const ready = whenPlayable(new FakeMedia(), deadline.signal);
    deadline.abort();
    await expect(ready).rejects.toThrow("in time");
  });

  it("fails at once when the deadline has already passed", async () => {
    await expect(whenPlayable(new FakeMedia(), AbortSignal.abort())).rejects.toThrow("in time");
  });

  it("stays ready when the deadline passes after the data arrived", async () => {
    const deadline = new AbortController();
    const media = new FakeMedia();
    const ready = whenPlayable(media, deadline.signal);
    media.load(12);
    deadline.abort();
    await expect(ready).resolves.toBeUndefined();
  });
});

describe("seeking", () => {
  it("stays inside the track", () => {
    expect(seekTargetS(12.5, 100)).toBe(12.5);
    expect(seekTargetS(-3, 100)).toBe(0);
    expect(seekTargetS(250, 100)).toBeCloseTo(99.99);
  });

  it("stays at the start of an empty track", () => {
    expect(seekTargetS(5, 0)).toBe(0);
  });
});
