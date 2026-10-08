# spectra — engineering conventions

spectra is an open-source audio-reactive visualizer for techno. A Python engine analyses audio in real time and streams features over one WebSocket to a browser renderer; LLM agents direct the visuals on slower time scales. Product and architecture docs live in `docs/`; `docs/CONTRACT.md` is the single source of truth for the wire protocol and shader uniforms.

## Non-negotiable rules

- No LLM call is ever on the real-time path (frame = 16 ms, bar ≈ 1.8 s). Anything that reacts to a beat is deterministic code.
- The wire protocol in `docs/CONTRACT.md` never changes silently. Contract tests in `tests/contract/` pin it. A change to the wire format is a separate, explicit commit that updates the contract doc, the golden tests and lists what the web client and agent prompts must change.
- Photosensitivity checks are deterministic code, never an LLM judgement.
- The browser client in `web/` holds no business logic. It renders what arrives.

## Stack

- Python 3.14, managed with `uv`, packaged with `uv_build`, `src/` layout.
- FastAPI + uvicorn for the gateway, msgpack for binary frames, JSON for control messages.
- numpy in the hot path. pydantic v2 only at system boundaries: wire messages, settings, LLM structured outputs.
- Quality gates: ruff (lint + format), mypy `--strict`, pytest 9 in strict mode, hypothesis, import-linter.

## Architecture

Strategic DDD with ports and adapters. Each bounded context is a package under `src/spectra/` with up to three layers:

```
<context>/
  domain/        entities, value objects, domain services, domain errors — pure Python + numpy, no I/O
  application/   use cases and ports (typing.Protocol) the context needs from the outside world
  adapters/      implementations of ports: audio devices, synthetic sources, libraries, sidecars
```

Dependency rule: `adapters → application → domain`, never the reverse. import-linter enforces it.

Bounded contexts:

| Context | Status | Ubiquitous language |
|---|---|---|
| `analysis` | exists | sample, spectrum, band, waveform, peak, kick, levels, tempo, beat position, bar, energy |
| `direction` | stage 4 | set plan, scene, palette, intensity, transition, order (prefetch) |
| `studio` | stage 3–5 | brief, shader, compile result, photosafe verdict, critique |
| `library` | stage 3 | stored scene, embedding, showing history |
| `decks` | stage 6 | deck, track, phrase, hot cue, crossfader, on air |

Shared and outer packages:

- `spectra.shared` — shared kernel only: `Clock` port and its adapters, tiny cross-context value objects. Keep it small.
- `spectra.gateway` — the WebSocket boundary: wire codec, wire message schemas, client session, FastAPI routes. Maps domain objects to the contract and back.
- `spectra.bootstrap` — composition root: settings, wiring, `create_app()`. The only place that knows concrete adapters.

Do not create packages for contexts that have no code yet. Add a port only when there is a real second implementation or a test needs a fake.

## Code style

- No comments and no docstrings. Intent lives in names, types and tests. The only allowed `#` lines are tool pragmas (`# noqa: XXX`, `# type: ignore[code]`) with a specific code, and only when unavoidable.
- Units are part of names: `duration_s`, `latency_ms`, `freq_hz`, `phase_rad`, `level_db`.
- Full type annotations everywhere, mypy `--strict` clean. No `Any` in `domain/`. `cast` only at I/O boundaries.
- Modern typing: PEP 695 `type` aliases and generic syntax, `Self`, `@override`, `Final`, `Literal`. No `from __future__ import annotations`: 3.14 defers annotation evaluation natively.
- Value objects: `@dataclass(frozen=True, slots=True, kw_only=True)`, invariants checked in `__post_init__`, numpy arrays stored read-only (`flags.writeable = False`).
- Closed sets of strings are `StrEnum`. Ports are `typing.Protocol`, not ABCs.
- Dependencies arrive through constructors. No module-level mutable state, no singletons, no `global`.
- Small functions, early returns, `match` for dispatch on message kinds, comprehensions instead of append loops (max two levels).
- Errors: each context has a base exception in `domain/errors.py`. No bare `except`, no `except Exception: pass`, no silent fallbacks.
- Async: `asyncio.TaskGroup` for concurrent work, `except*` for exception groups, `asyncio.timeout` for deadlines. No fire-and-forget `create_task`.
- Logging: `logger = logging.getLogger(__name__)`, lazy `%s` formatting, configured only in `bootstrap`. No `print`.
- Absolute imports only. `__init__.py` files are empty unless they declare a deliberate public API with `__all__`.
- Constants are `Final`, UPPER_SNAKE_CASE, defined in the module that owns the concept.

## Testing — TDD

- Red → green → refactor. Write the failing test first; commit the test together with the code that makes it pass.
- Layout mirrors the source tree:
  - `tests/unit/<context>/...` — domain and application, fast, no I/O.
  - `tests/integration/` — adapters and the FastAPI app (`TestClient`).
  - `tests/contract/` — golden tests for the wire format from `docs/CONTRACT.md`.
- Fakes over mocks: implement ports in `tests/fakes.py` (e.g. `FakeClock`, `FakeConnection`). `unittest.mock` only at third-party boundaries.
- hypothesis for invariants: value ranges, codec round-trips, beat-position math for any time and tempo.
- DSP is tested with synthetic signals that have a known answer (a 1 kHz sine peaks at 1 kHz; a click train at 128 BPM gives 128 BPM), with explicit tolerances via `pytest.approx` or `numpy.testing`.
- Test names state the behaviour: `test_kick_envelope_halves_after_decay_time`.
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
