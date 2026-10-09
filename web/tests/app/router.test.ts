import { describe, expect, it } from "vitest";
import { shuffledOrder } from "../../src/app/dissolve";
import { resolveRoute } from "../../src/app/router";

const FRESH = { trackLoaded: false, loading: false };
const LOADED = { trackLoaded: true, loading: false };

describe("routes", () => {
  it("show the start screen to a fresh visitor", () => {
    expect(resolveRoute("#start", FRESH)).toEqual({ kind: "show", route: "start" });
  });

  it("send unknown routes to the start screen", () => {
    expect(resolveRoute("#generate", LOADED)).toEqual({ kind: "redirect", route: "start" });
    expect(resolveRoute("", FRESH)).toEqual({ kind: "redirect", route: "start" });
  });

  it("guard the track screens until a track is loaded", () => {
    expect(resolveRoute("#main", FRESH)).toEqual({ kind: "redirect", route: "start" });
    expect(resolveRoute("#analysis", FRESH)).toEqual({ kind: "redirect", route: "start" });
    expect(resolveRoute("#analysis", LOADED)).toEqual({ kind: "show", route: "analysis" });
  });

  it("never return to the loading screen once it is done", () => {
    expect(resolveRoute("#loading", LOADED)).toEqual({ kind: "redirect", route: "main" });
    expect(resolveRoute("#loading", FRESH)).toEqual({ kind: "redirect", route: "start" });
    expect(resolveRoute("#loading", { trackLoaded: false, loading: true })).toEqual({
      kind: "show",
      route: "loading",
    });
  });
});

describe("the dissolve order", () => {
  it("visits every cell exactly once", () => {
    let seed = 7;
    const random = () => {
      seed = (seed * 16_807) % 2_147_483_647;
      return seed / 2_147_483_647;
    };
    const order = shuffledOrder(500, random);
    expect([...order].sort((left, right) => left - right)).toEqual(
      Array.from({ length: 500 }, (_, index) => index),
    );
    expect(order).not.toEqual(Array.from({ length: 500 }, (_, index) => index));
  });
});
