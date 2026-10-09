from typing import Final

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

type Header = tuple[bytes, bytes]

SECURITY_HEADERS: Final[tuple[Header, ...]] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cross-origin-resource-policy", b"same-origin"),
)
STRICT_TRANSPORT: Final[Header] = (b"strict-transport-security", b"max-age=31536000")


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        extra = [*SECURITY_HEADERS, *([STRICT_TRANSPORT] if scope["scheme"] == "https" else [])]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self._app(scope, receive, send_with_headers)


def install_security_headers(app: FastAPI) -> None:
    app.add_middleware(SecurityHeaders)
