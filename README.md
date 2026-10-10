# spectra

spectra is an open-source music visualizer. You drop in a track; a Python engine decodes it, analyses the whole file once (spectrum, onsets, tempo, beat grid, sections, per-bar peaks) and serves the result to a browser renderer that plays the audio and draws pixel-art views of it.

## Quick start

With Docker:

```bash
docker compose up
```

Then open http://localhost:8080. The port can be changed with `SPECTRA_WEB_PORT` (see `.env.example`). This demo keeps everything in memory and needs no `.env`.

## Ways to run it

The compose files are layers, each one an override of the files before it:

| Mode | Command | What runs |
|---|---|---|
| Demo | `docker compose up` | the engine in local mode and the web client |
| Local hosted | `docker compose -f compose.yaml -f compose.hosted.yaml up --build --wait` | the full server stack: Postgres, Redis, versitygw for S3, migrations and a separate worker |
| Production | `COMPOSE_FILE=compose.yaml:compose.hosted.yaml:compose.prod.yaml` in the server's `.env` | the hosted stack with production images, limits, TLS and monitoring |

The local hosted stack reads its development passwords from `.env`: run `cp .env.example .env` once. Production needs docker compose 2.24.4 or newer; [docs/DEPLOY.md](docs/DEPLOY.md) describes it, including how to run several workers with `--scale worker=N`.

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

### Integration tests

The adapter tests need Postgres, Redis and S3 and are skipped without them. `compose.test.yaml` starts the three as a separate project, `spectra-test`, with their ports on `127.0.0.1`, so the tests never touch the data of your local hosted stack:

```bash
cp .env.test.example .env.test
docker compose --env-file .env.test -f compose.yaml -f compose.hosted.yaml -f compose.test.yaml up --detach --wait postgres redis s3
uv run --env-file .env.test pytest
```

With the services up, no test is skipped.

## Docs

- [docs/CONTRACT.md](docs/CONTRACT.md) — HTTP API and the binary timeline
- [docs/DESIGN.md](docs/DESIGN.md) — everything visual
- [docs/DEPLOY.md](docs/DEPLOY.md) — production deployment and monitoring

## License

[MIT](LICENSE)
