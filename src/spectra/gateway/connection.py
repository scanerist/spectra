from typing import Protocol

from fastapi import WebSocket, WebSocketDisconnect

from spectra.gateway.errors import ClientDisconnectedError, UnreadableClientFrameError


class ClientConnection(Protocol):
    async def send_bytes(self, data: bytes) -> None: ...

    async def send_text(self, text: str) -> None: ...

    async def receive_text(self) -> str: ...


class WebSocketConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket

    async def send_bytes(self, data: bytes) -> None:
        try:
            await self._websocket.send_bytes(data)
        except WebSocketDisconnect as error:
            raise ClientDisconnectedError(f"client left with code {error.code}") from error

    async def send_text(self, text: str) -> None:
        try:
            await self._websocket.send_text(text)
        except WebSocketDisconnect as error:
            raise ClientDisconnectedError(f"client left with code {error.code}") from error

    async def receive_text(self) -> str:
        match await self._websocket.receive():
            case {"type": "websocket.disconnect", "code": code}:
                raise ClientDisconnectedError(f"client left with code {code}")
            case {"type": "websocket.receive", "text": str() as text}:
                return text
            case {"type": "websocket.receive"}:
                raise UnreadableClientFrameError("client frames must be text")
            case unexpected:
                raise UnreadableClientFrameError(f"unexpected ASGI message {unexpected['type']}")
