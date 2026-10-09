import { describe, expect, it } from "vitest";
import { bpmText, clockText } from "../../src/app/format";

describe("the clock", () => {
  it("shows minutes and two-digit seconds", () => {
    expect(clockText(151.9)).toBe("2:31");
    expect(clockText(432.17)).toBe("7:12");
    expect(clockText(5)).toBe("0:05");
  });

  it("never goes below zero", () => {
    expect(clockText(-1)).toBe("0:00");
  });
});

describe("the tempo", () => {
  it("shows one decimal", () => {
    expect(bpmText(127.9963)).toBe("128.0");
  });
});
