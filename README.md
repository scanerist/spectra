# spectra

spectra is an open-source music visualizer. You drop in a track; a Python engine decodes it, analyses the whole file once (spectrum, onsets, tempo, beat grid, sections, per-bar peaks) and serves the result to a browser renderer that plays the audio and draws pixel-art views of it.

## Quick start

With Docker:

```bash
docker compose up
```

Then open http://localhost:8080. The port can be changed with `SPECTRA_WEB_PORT` (see `.env.example`).

## Development

Engine, on http://127.0.0.1:8000:

```bash
uv sync
uv run spectra
```

Web client, with the Vite dev server proxying the engine routes:

```bash
cd web
npm ci
npm run dev
```

Checks before a commit: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports` and, in `web/`, `npm run check`.

## Docs

- [docs/CONTRACT.md](docs/CONTRACT.md) — HTTP API and the binary timeline
- [docs/DESIGN.md](docs/DESIGN.md) — everything visual
- [docs/DEPLOY.md](docs/DEPLOY.md) — production deployment and monitoring

## License

[MIT](LICENSE)
