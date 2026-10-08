from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from spectra.bootstrap.app import create_app
from spectra.bootstrap.settings import Settings
from spectra.gateway.wire.frame_codec import PROTOCOL_VERSION, decode_frame
from spectra.gateway.wire.messages import DirectorLog, Prompt

HELLO = DirectorLog(bar=0, text="engine connected · fake source 128 BPM")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings())) as client:
        yield client


def next_text(websocket: WebSocketTestSession) -> str:
    while True:
        message = websocket.receive()
        if message.get("text") is not None:
            return str(message["text"])


def test_first_text_frame_is_the_hello_log(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        assert websocket.receive_text() == HELLO.model_dump_json()


def test_binary_frames_decode_into_a_running_groove(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_text()
        frames = [decode_frame(websocket.receive_bytes()) for _ in range(3)]
    assert all(frame.tempo.bpm == 128.0 for frame in frames)
    times_s = [frame.time_s for frame in frames]
    assert times_s == sorted(times_s)


def test_garbage_input_does_not_break_the_session(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_text()
        websocket.send_text("{not json")
        websocket.send_text('{"type":"nope"}')
        websocket.send_bytes(b"\xff\x00")
        websocket.send_text(Prompt(text="still listening?").model_dump_json())
        reply = DirectorLog.model_validate_json(next_text(websocket))
    assert reply.text == "prompt received: still listening?"


def test_prompt_is_echoed_as_director_log(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_text()
        websocket.send_text('{"type":"prompt","text":"холодно, бетон"}')
        reply = DirectorLog.model_validate_json(next_text(websocket))
    assert reply.text == "prompt received: холодно, бетон"
    assert reply.bar >= 0


def test_health_reports_the_protocol_version(client: TestClient) -> None:
    assert client.get("/health").json() == {"ok": True, "protocol": PROTOCOL_VERSION}


def test_greeting_follows_the_configured_bpm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECTRA_SYNTHETIC_BPM", "140")
    with (
        TestClient(create_app(Settings())) as client,
        client.websocket_connect("/ws") as websocket,
    ):
        hello = DirectorLog.model_validate_json(websocket.receive_text())
        frame = decode_frame(websocket.receive_bytes())
    assert hello.text == "engine connected · fake source 140 BPM"
    assert frame.tempo.bpm == 140.0
