import { describe, expect, it } from "vitest";
import { chromeFor } from "../../src/app/chrome";

const LOADED = { trackLoaded: true, hasRepository: true };
const EMPTY = { trackLoaded: false, hasRepository: true };

describe("header chrome", () => {
  it("shows the transport only while a track is on screen", () => {
    expect(chromeFor("main", LOADED)).toMatchObject({ clock: true, play: true });
    expect(chromeFor("start", LOADED)).toMatchObject({ clock: false, play: false });
    expect(chromeFor("loading", LOADED)).toMatchObject({ clock: false, play: false });
  });

  it("offers the way back to the loaded track from the start screen", () => {
    expect(chromeFor("start", LOADED).back).toBe(true);
    expect(chromeFor("start", EMPTY).back).toBe(false);
    expect(chromeFor("analysis", LOADED).back).toBe(true);
    expect(chromeFor("main", LOADED).back).toBe(false);
  });

  it("links the repository from the start screen when it is known", () => {
    expect(chromeFor("start", EMPTY).repo).toBe(true);
    expect(chromeFor("start", { ...EMPTY, hasRepository: false }).repo).toBe(false);
    expect(chromeFor("main", LOADED).repo).toBe(false);
  });
});
