"""FastAPI app. /ws streams FeatureFrame (binary msgpack, 60 Hz) and control messages (JSON).

Run:  uv run uvicorn spectra.legacy.server:app --reload
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from spectra.legacy.fake_source import FakeSource
from spectra.legacy.protocol import (
    PROTOCOL_VERSION,
    ClientMessage,
    DirectorLog,
    Prompt,
    ServerMessage,
    ShaderCompiled,
    client_message_adapter,
)

FRAME_HZ = 60.0
CONTROL_QUEUE_MAX = 256

log = logging.getLogger("spectra.server")

# Stage 0: one global synthetic source shared by all clients (browser + OBS see the same frame).
# Stage 1 replaces this with the real capture/DSP pipeline publishing the latest frame.
_source = FakeSource(bpm=128.0)
_t0 = time.monotonic()


def engine_time() -> float:
    return time.monotonic() - _t0


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _t0
    _t0 = time.monotonic()
    yield


app = FastAPI(title="spectra engine", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "protocol": PROTOCOL_VERSION}


class Connection:
    """One client. A single writer task owns ws.send_*: control messages are drained
    each tick, then the *latest* frame is sent. Nothing queues up behind a slow client —
    if it lags, ticks are skipped, never bursted."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self._control: asyncio.Queue[ServerMessage] = asyncio.Queue(maxsize=CONTROL_QUEUE_MAX)

    def send_control(self, msg: ServerMessage) -> None:
        try:
            self._control.put_nowait(msg)
        except asyncio.QueueFull:
            log.warning("control queue full, dropping %s", msg.type)

    async def writer(self) -> None:
        loop = asyncio.get_running_loop()
        period = 1.0 / FRAME_HZ
        next_tick = loop.time()
        while True:
            while not self._control.empty():
                await self.ws.send_text(self._control.get_nowait().model_dump_json())
            await self.ws.send_bytes(_source.frame(engine_time()).pack())

            next_tick += period
            delay = next_tick - loop.time()
            if delay < -period:  # fell behind by more than a frame: resync instead of bursting
                next_tick = loop.time()
                delay = 0.0
            await asyncio.sleep(max(delay, 0.0))


def handle_client_message(conn: Connection, msg: ClientMessage) -> None:
    bar = _source.frame(engine_time()).bar
    match msg:
        case ShaderCompiled(ok=False, id=sid, error=err):
            log.info("shader %s failed to compile: %s", sid, err)
        case ShaderCompiled(id=sid):
            log.info("shader %s compiled", sid)
        case Prompt(text=text):
            # Stage 3+: goes to the blackboard -> art director. For now just echo.
            conn.send_control(DirectorLog(bar=bar, text=f"prompt received: {text}"))
        case _:
            pass


def _log_task_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        log.debug("writer stopped: %r", exc)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    conn = Connection(ws)
    conn.send_control(
        DirectorLog(bar=0, text=f"engine connected · fake source {_source.bpm:g} BPM")
    )
    writer = asyncio.create_task(conn.writer())
    writer.add_done_callback(_log_task_error)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = client_message_adapter.validate_json(raw)
            except ValidationError as e:
                log.warning("bad client message: %s", e.errors(include_url=False)[:1])
                continue
            handle_client_message(conn, msg)
    except WebSocketDisconnect:
        pass
    finally:
        writer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await writer
