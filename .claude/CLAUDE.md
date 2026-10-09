# spectra — engineering conventions

spectra is an open-source music visualizer. You drop in a track; a Python engine decodes it, analyses the whole file once (spectrum, onsets, tempo, beat grid, sections, per-bar peaks) and serves the result to a browser renderer that plays the audio and draws pixel-art views of it. Product docs live in `docs/`: `docs/CONTRACT.md` is the single source of truth for the HTTP API and the binary timeline, `docs/DESIGN.md` for everything visual.

## Non-negotiable rules

- No LLM anywhere in the product. Every feature is deterministic signal processing.
- The protocol in `docs/CONTRACT.md` never changes silently. Contract tests in `tests/contract/` pin it. A change to the protocol is a separate, explicit commit that updates the contract doc, the golden tests and lists what the web client must change.
- The browser client in `web/` holds no analysis logic. It plays the audio, looks up precomputed features by playback time and renders them. Reading the raw signal from an `AnalyserNode` to draw a waveform is allowed; deriving bands, tempo, peaks or sections in the browser is not.
- Every pixel the user sees follows `docs/DESIGN.md`.

## Stack

- Python 3.14, managed with `uv`, packaged with `uv_build`, `src/` layout.
- FastAPI + uvicorn for the gateway, msgpack or packed numpy arrays for binary payloads, JSON for metadata.
- numpy for all DSP. pydantic v2 only at system boundaries: API messages and settings.
- Quality gates: ruff (lint + format), mypy `--strict`, pytest 9 in strict mode, hypothesis, import-linter.
- `web/`: Vite + TypeScript, no UI framework, Canvas 2D, Web Audio.

## Architecture

Strategic DDD with ports and adapters. Each bounded context is a package under `src/spectra/` with up to three layers:

```
<context>/
  domain/        entities, value objects, domain services, domain errors — pure Python + numpy, no I/O
  application/   use cases and ports (typing.Protocol) the context needs from the outside world
  adapters/      implementations of ports: audio decoders, synthetic sources, storage
```

Dependency rule: `adapters → application → domain`, never the reverse. import-linter enforces it.

Bounded contexts:

| Context | Status | Ubiquitous language |
|---|---|---|
| `analysis` | exists | sample, frame, spectrum, band, waveform, onset, peak, kick, levels, tempo, beat grid, beat position, bar, section, energy, track analysis |
| `tracks` | stage 2 | track, upload, file hash, analysis job, progress, timeline |

Shared and outer packages:

- `spectra.shared` — shared kernel only: `Clock` port and its adapters, tiny cross-context value objects. Keep it small.
- `spectra.gateway` — the HTTP boundary: timeline codec, API schemas, FastAPI routes. Maps domain objects to the contract and back.
- `spectra.bootstrap` — composition root: settings, wiring, `create_app()`. The only place that knows concrete adapters.

Do not create packages for contexts that have no code yet. Add a port only when there is a real second implementation or a test needs a fake.

## Code style

- No comments and no docstrings. Intent lives in names, types and tests. The only allowed `#` lines are tool pragmas (`# noqa: XXX`, `# type: ignore[code]`) with a specific code, and only when unavoidable.
- Units are part of names: `duration_s`, `latency_ms`, `freq_hz`, `phase_rad`, `level_db`, `hop_samples`.
- Full type annotations everywhere, mypy `--strict` clean. No `Any` in `domain/`. `cast` only at I/O boundaries.
- Modern typing: PEP 695 `type` aliases and generic syntax, `Self`, `@override`, `Final`, `Literal`. No `from __future__ import annotations`: 3.14 defers annotation evaluation natively.
- Value objects: `@dataclass(frozen=True, slots=True, kw_only=True)`, invariants checked in `__post_init__`, numpy arrays stored read-only (`flags.writeable = False`).
- Closed sets of strings are `StrEnum`. Ports are `typing.Protocol`, not ABCs.
- Dependencies arrive through constructors. No module-level mutable state, no singletons, no `global`.
- Small functions, early returns, `match` for dispatch, comprehensions instead of append loops (max two levels). Vectorise DSP with numpy instead of Python loops over samples.
- Errors: each context has a base exception in `domain/errors.py`. No bare `except`, no `except Exception: pass`, no silent fallbacks.
- Async: `asyncio.TaskGroup` for concurrent work, `except*` for exception groups, `asyncio.timeout` for deadlines. No fire-and-forget `create_task`. CPU-bound analysis runs off the event loop.
- Logging: `logger = logging.getLogger(__name__)`, lazy `%s` formatting, configured only in `bootstrap`. No `print`.
- Absolute imports only. `__init__.py` files are empty unless they declare a deliberate public API with `__all__`.
- Constants are `Final`, UPPER_SNAKE_CASE, defined in the module that owns the concept.

## Testing — TDD

- Red → green → refactor. Write the failing test first; commit the test together with the code that makes it pass.
- Layout mirrors the source tree:
  - `tests/unit/<context>/...` — domain and application, fast, no I/O.
  - `tests/integration/` — adapters and the FastAPI app (`TestClient`).
  - `tests/contract/` — golden tests for the protocol from `docs/CONTRACT.md`.
- Fakes over mocks: implement ports in `tests/fakes.py` (e.g. `FakeClock`, `FakeDecoder`). `unittest.mock` only at third-party boundaries.
- hypothesis for invariants: value ranges, codec round-trips, beat-position math for any time and tempo.
- DSP is tested with synthetic signals that have a known answer (a 1 kHz sine peaks at 1 kHz; a click train at 128 BPM gives 128 BPM; quiet–loud–quiet blocks give three sections), with explicit tolerances via `pytest.approx` or `numpy.testing`.
- Test names state the behaviour: `test_click_train_at_128_bpm_estimates_128_bpm`.
- Plain `assert`, fixtures in `conftest.py`, `pytest.mark.parametrize` with `ids`.

## Commands

```bash
uv sync
uv run pytest
uv run ruff check --fix && uv run ruff format
uv run mypy
uv run lint-imports
uv run spectra
```

All five checks must pass before a commit.

## Commits

Conventional Commits in English (`feat(analysis): ...`, `refactor(gateway): ...`, `test(contract): ...`). One logical change per commit.
