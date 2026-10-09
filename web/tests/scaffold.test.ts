import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("the page", () => {
  it("is in russian and loads the app module", () => {
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    expect(html).toContain('<html lang="ru">');
    expect(html).toContain('src="/src/main.ts"');
  });
});
