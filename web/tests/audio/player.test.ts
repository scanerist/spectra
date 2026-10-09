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

describe("preparing playback", () => {
  it("is ready once the browser has decoded the first frames", async () => {
    const media = new FakeMedia();
    const ready = whenPlayable(media);
    media.load(432.17);
    await expect(ready).resolves.toBeUndefined();
  });

  it("is ready at once when the media already has data", async () => {
    await expect(whenPlayable(new FakeMedia(4, 12))).resolves.toBeUndefined();
  });

  it("fails as soon as the browser cannot play the file", async () => {
    const media = new FakeMedia();
    const ready = whenPlayable(media);
    media.fail();
    await expect(ready).rejects.toThrow("cannot play");
  });

  it("fails on media without a known length", async () => {
    const media = new FakeMedia();
    const ready = whenPlayable(media);
    media.load(Number.POSITIVE_INFINITY);
    await expect(ready).rejects.toThrow("no duration");
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
