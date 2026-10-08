import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from spectra.gateway.connection import ClientConnection, WebSocketConnection
from spectra.gateway.errors import ClientDisconnectedError, UnreadableClientFrameError


def echo_app(outcomes: list[str]) -> FastAPI:
    app = FastAPI()

    @app.websocket("/echo")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        connection: ClientConnection = WebSocketConnection(websocket)
        while True:
            try:
                text = await connection.receive_text()
            except UnreadableClientFrameError:
                outcomes.append("unreadable")
                await connection.send_text("unreadable")
                continue
            except ClientDisconnectedError:
                outcomes.append("disconnected")
                return
            await connection.send_text(text)
            await connection.send_bytes(text.encode())

    return app


@pytest.fixture
def outcomes() -> list[str]:
    return []


@pytest.fixture
def client(outcomes: list[str]) -> TestClient:
    return TestClient(echo_app(outcomes))


def test_connection_sends_and_receives_text_and_bytes(client: TestClient) -> None:
    with client.websocket_connect("/echo") as websocket:
        websocket.send_text("hello")
        assert websocket.receive_text() == "hello"
        assert websocket.receive_bytes() == b"hello"


def test_binary_client_frame_is_unreadable_not_fatal(
    client: TestClient, outcomes: list[str]
) -> None:
    with client.websocket_connect("/echo") as websocket:
        websocket.send_bytes(b"\x00\x01")
        assert websocket.receive_text() == "unreadable"
        websocket.send_text("still here")
        assert websocket.receive_text() == "still here"
    assert outcomes[0] == "unreadable"


def test_client_close_surfaces_as_client_disconnected(
    client: TestClient, outcomes: list[str]
) -> None:
    with client.websocket_connect("/echo") as websocket:
        websocket.send_text("bye")
        websocket.receive_text()
        websocket.receive_bytes()
    assert outcomes == ["disconnected"]
