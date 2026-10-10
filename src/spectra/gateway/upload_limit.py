import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from spectra.gateway.errors import ErrorCode, error_response
from spectra.shared.clock import Clock

MULTIPART_OVERHEAD_BYTES: Final = 64 << 10


def declared_length(scope: Scope) -> int:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            return int(value) if value.isdigit() else 0
    return 0


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadPace:
    min_bytes_per_s: float
    grace_s: float
    idle_s: float


class Refusal(StrEnum):
    TOO_LARGE = "too_large"
    TOO_SLOW = "too_slow"


DISCONNECT: Final[Message] = {"type": "http.disconnect"}


class BodyGuard:
    def __init__(
        self, receive: Receive, *, limit_bytes: int, pace: UploadPace, clock: Clock
    ) -> None:
        self._receive = receive
        self._limit_bytes = limit_bytes
        self._pace = pace
        self._clock = clock
        self._started_s = clock.now_s()
        self._received_bytes = 0
        self._complete = False
        self.refusal: Refusal | None = None

    async def receive(self) -> Message:
        if self.refusal is not None:
            return DISCONNECT
        if self._complete:
            return await self._receive()
        try:
            async with asyncio.timeout(self._pace.idle_s):
                message = await self._receive()
        except TimeoutError:
            self.refusal = Refusal.TOO_SLOW
            return DISCONNECT
        if message["type"] != "http.request":
            return message
        self._received_bytes += len(message.get("body", b""))
        self._complete = not message.get("more_body", False)
        self.refusal = self._judge()
        return DISCONNECT if self.refusal is not None else message

    def guard(self, send: Send) -> Send:
        async def guarded(message: Message) -> None:
            if self.refusal is None:
                await send(message)

        return guarded

    def _judge(self) -> Refusal | None:
        if self._received_bytes > self._limit_bytes:
            return Refusal.TOO_LARGE
        paced_s = self._clock.now_s() - self._started_s - self._pace.grace_s
        if not self._complete and self._received_bytes < self._pace.min_bytes_per_s * paced_s:
            return Refusal.TOO_SLOW
        return None


class UploadLimit:
    def __init__(
        self, app: ASGIApp, *, max_body_bytes: int, pace: UploadPace, clock: Clock
    ) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes
        self._pace = pace
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self._app(scope, receive, send)
            return
        if declared_length(scope) > self._max_body_bytes:
            await self._refuse(Refusal.TOO_LARGE, scope, receive, send)
            return
        body = BodyGuard(
            receive, limit_bytes=self._max_body_bytes, pace=self._pace, clock=self._clock
        )
        await self._app(scope, body.receive, body.guard(send))
        if body.refusal is not None:
            await self._refuse(body.refusal, scope, receive, send)

    async def _refuse(self, refusal: Refusal, scope: Scope, receive: Receive, send: Send) -> None:
        match refusal:
            case Refusal.TOO_LARGE:
                message = f"the request body is larger than {self._max_body_bytes} bytes"
                response = error_response(ErrorCode.FILE_TOO_LARGE, message)
            case Refusal.TOO_SLOW:
                rate = self._pace.min_bytes_per_s
                response = error_response(
                    ErrorCode.NO_FILE, f"the upload arrived slower than {rate:.0f} bytes per second"
                )
        await response(scope, receive, send)


def install_upload_limit(
    app: FastAPI, *, max_upload_bytes: int, pace: UploadPace, clock: Clock
) -> None:
    app.add_middleware(
        UploadLimit,
        max_body_bytes=max_upload_bytes + MULTIPART_OVERHEAD_BYTES,
        pace=pace,
        clock=clock,
    )
