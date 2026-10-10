import { describe, expect, it } from "vitest";
import { repositoryLink } from "../../src/app/repository";

describe("the repository link", () => {
  it("keeps an https address", () => {
    expect(repositoryLink("https://github.com/scanerist/spectra")).toBe(
      "https://github.com/scanerist/spectra",
    );
  });

  it.each([
    ["javascript:alert(1)"],
    ["http://github.com/scanerist/spectra"],
    ["data:text/html,hi"],
    ["//github.com/scanerist/spectra"],
    ["not a url"],
    [""],
  ])("drops %j", (raw) => {
    expect(repositoryLink(raw)).toBe("");
  });
});
