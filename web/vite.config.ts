import { defineConfig } from "vitest/config";

const ENGINE_URL = process.env.SPECTRA_ENGINE_URL ?? "http://127.0.0.1:8000";
const ENGINE_PATHS = ["/tracks", "/health", "/ready"];

export default defineConfig({
  server: {
    proxy: Object.fromEntries(ENGINE_PATHS.map((path) => [path, { target: ENGINE_URL }])),
  },
  build: {
    target: "es2023",
    assetsInlineLimit: 0,
  },
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
  },
});
