from typing import Final

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from spectra.gateway.errors import ErrorCode, error_response

MULTIPART_OVERHEAD_BYTES: Final = 64 << 10


def declared_length(scope: Scope) -> int:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            return int(value) if value.isdigit() else 0
    return 0


class BodyGuard:
    def __init__(self, receive: Receive, *, limit_bytes: int) -> None:
        self._receive = receive
        self._limit_bytes = limit_bytes
        self._received_bytes = 0
        self.exceeded = False

    async def receive(self) -> Message:
        if self.exceeded:
            return {"type": "http.disconnect"}
        message = await self._receive()
        if message["type"] == "http.request":
            self._received_bytes += len(message.get("body", b""))
            if self._received_bytes > self._limit_bytes:
                self.exceeded = True
                return {"type": "http.disconnect"}
        return message

    def guard(self, send: Send) -> Send:
        async def guarded(message: Message) -> None:
            if not self.exceeded:
                await send(message)

        return guarded


class UploadLimit:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self._app(scope, receive, send)
            return
        if declared_length(scope) > self._max_body_bytes:
            await self._refuse(scope, receive, send)
            return
        body = BodyGuard(receive, limit_bytes=self._max_body_bytes)
        await self._app(scope, body.receive, body.guard(send))
        if body.exceeded:
            await self._refuse(scope, receive, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        message = f"the request body is larger than {self._max_body_bytes} bytes"
        await error_response(ErrorCode.FILE_TOO_LARGE, message)(scope, receive, send)


def install_upload_limit(app: FastAPI, *, max_upload_bytes: int) -> None:
    app.add_middleware(UploadLimit, max_body_bytes=max_upload_bytes + MULTIPART_OVERHEAD_BYTES)
