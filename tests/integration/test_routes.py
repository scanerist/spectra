import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from spectra.gateway.errors import GatewayNotConfiguredError
from spectra.gateway.routes import create_router, install_session_dependencies
from spectra.gateway.session import SessionDependencies
from spectra.gateway.wire.frame_codec import PROTOCOL_VERSION, decode_frame
from spectra.gateway.wire.messages import DirectorLog, Prompt
from spectra.shared.clock import MonotonicClock
from tests.fakes import RecordingHandler, StaticFeatureSource, frame_at_bar

GREETING = DirectorLog(bar=0, text="hello from routes")
REPLY = DirectorLog(bar=9, text="noted")


@pytest.fixture
def source() -> StaticFeatureSource:
    return StaticFeatureSource(frame_at_bar(9))


@pytest.fixture
def handler() -> RecordingHandler:
    return RecordingHandler(replies=(REPLY,))


@pytest.fixture
def client(source: StaticFeatureSource, handler: RecordingHandler) -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    install_session_dependencies(
        app,
        SessionDependencies(
            source=source,
            handler=handler,
            clock=MonotonicClock(),
            frame_rate_hz=120.0,
            greeting=GREETING,
        ),
    )
    return TestClient(app)


def next_text(websocket: WebSocketTestSession) -> str:
    while True:
        message = websocket.receive()
        if message.get("text") is not None:
            return str(message["text"])


def test_health_reports_protocol_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "protocol": PROTOCOL_VERSION}


def test_stream_sends_greeting_then_source_frames(
    client: TestClient, source: StaticFeatureSource
) -> None:
    with client.websocket_connect("/ws") as websocket:
        assert websocket.receive_text() == GREETING.model_dump_json()
        assert decode_frame(websocket.receive_bytes()) == source.frame


def test_stream_routes_client_messages_to_the_handler(
    client: TestClient, handler: RecordingHandler
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_text()
        websocket.send_text(Prompt(text="darker").model_dump_json())
        assert next_text(websocket) == REPLY.model_dump_json()
    assert handler.received == [Prompt(text="darker")]


def test_stream_without_dependencies_is_a_configuration_error() -> None:
    app = FastAPI()
    app.include_router(create_router())
    with (
        pytest.raises(GatewayNotConfiguredError),
        TestClient(app).websocket_connect("/ws"),
    ):
        pass
