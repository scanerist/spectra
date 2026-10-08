import asyncio
import logging
from collections.abc import Callable
from typing import Final

import anyio
import pytest

from spectra.gateway.errors import ClientDisconnectedError
from spectra.gateway.session import OUTBOX_CAPACITY, ClientSession, SessionDependencies
from spectra.gateway.wire.frame_codec import decode_frame
from spectra.gateway.wire.messages import DirectorLog, Prompt, ServerMessage
from tests.fakes import (
    FakeClock,
    FakeConnection,
    RecordingHandler,
    StaticFeatureSource,
    frame_at_bar,
)

FRAME_RATE_HZ: Final = 60.0
GREETING: Final = DirectorLog(bar=0, text="engine connected")
TIMEOUT_S: Final = 2.0

pytestmark = pytest.mark.anyio


def make_session(
    connection: FakeConnection,
    *,
    handler: RecordingHandler | None = None,
    clock: FakeClock | None = None,
    source: StaticFeatureSource | None = None,
) -> ClientSession:
    dependencies = SessionDependencies(
        source=source or StaticFeatureSource(frame_at_bar(5)),
        handler=handler or RecordingHandler(),
        clock=clock or FakeClock(),
        frame_rate_hz=FRAME_RATE_HZ,
        greeting=GREETING,
    )
    return ClientSession(connection=connection, dependencies=dependencies)


def json_of(message: ServerMessage) -> str:
    return message.model_dump_json()


async def test_first_message_is_the_greeting_then_frames() -> None:
    connection = FakeConnection(frames_until_disconnect=3)
    async with asyncio.timeout(TIMEOUT_S):
        await make_session(connection).run()
    assert connection.sent[0] == json_of(GREETING)
    assert all(isinstance(item, bytes) for item in connection.sent[1:])
    assert len(connection.frames) == 3


async def test_frames_carry_the_latest_source_frame() -> None:
    source = StaticFeatureSource(frame_at_bar(42))
    connection = FakeConnection(frames_until_disconnect=1)
    async with asyncio.timeout(TIMEOUT_S):
        await make_session(connection, source=source).run()
    assert decode_frame(connection.frames[0]) == source.frame


async def test_writer_sleeps_one_frame_period_between_frames() -> None:
    clock = FakeClock(start_s=50.0)
    connection = FakeConnection(frames_until_disconnect=4)
    async with asyncio.timeout(TIMEOUT_S):
        await make_session(connection, clock=clock).run()
    assert clock.sleeps_s == pytest.approx([1.0 / FRAME_RATE_HZ] * 4)


async def test_control_reply_goes_out_before_the_next_frame() -> None:
    reply = DirectorLog(bar=5, text="heard you")
    connection = FakeConnection()
    session = make_session(connection, handler=RecordingHandler(replies=(reply,)))
    async with asyncio.timeout(TIMEOUT_S), asyncio.TaskGroup() as group:
        group.create_task(session.run())
        await connection.wait_until(lambda: len(connection.frames) >= 2)
        sent_before_prompt = len(connection.sent)
        connection.feed(Prompt(text="colder").model_dump_json())
        await connection.wait_until(lambda: json_of(reply) in connection.texts)
        connection.disconnect()
    reply_index = connection.sent.index(json_of(reply))
    assert reply_index <= sent_before_prompt + 1
    assert isinstance(connection.sent[reply_index + 1], bytes)


async def test_prompt_reaches_the_handler() -> None:
    handler = RecordingHandler()
    connection = FakeConnection()
    async with asyncio.timeout(TIMEOUT_S), asyncio.TaskGroup() as group:
        group.create_task(make_session(connection, handler=handler).run())
        connection.feed('{"type":"prompt","text":"strobes on the kick"}')
        await connection.wait_until(lambda: bool(handler.received))
        connection.disconnect()
    assert handler.received == [Prompt(text="strobes on the kick")]


@pytest.mark.parametrize(
    "invalid",
    ["not json", '{"type":"nope"}', '{"type":"prompt","text":""}', b"\x00binary"],
    ids=["not-json", "unknown-type", "invalid-field", "binary-frame"],
)
async def test_invalid_message_is_logged_and_skipped(
    invalid: str | bytes, caplog: pytest.LogCaptureFixture
) -> None:
    handler = RecordingHandler()
    connection = FakeConnection()
    with caplog.at_level(logging.WARNING, logger="spectra.gateway.session"):
        async with asyncio.timeout(TIMEOUT_S), asyncio.TaskGroup() as group:
            group.create_task(make_session(connection, handler=handler).run())
            connection.feed(invalid)
            connection.feed('{"type":"prompt","text":"after garbage"}')
            await connection.wait_until(lambda: bool(handler.received))
            connection.disconnect()
    assert handler.received == [Prompt(text="after garbage")]
    assert any("skipping invalid client message" in message for message in caplog.messages)


async def test_client_disconnect_stops_both_loops() -> None:
    connection = FakeConnection()
    session = make_session(connection)
    connection.disconnect()
    async with asyncio.timeout(TIMEOUT_S):
        await session.run()
    frames_after_run = len(connection.frames)
    await asyncio.sleep(0)
    assert len(connection.frames) == frames_after_run


async def test_writer_disconnect_stops_the_reader() -> None:
    connection = FakeConnection(frames_until_disconnect=1)
    async with asyncio.timeout(TIMEOUT_S):
        await make_session(connection).run()
    assert len(connection.frames) == 1


async def test_full_outbox_drops_new_messages_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = FakeConnection(frames_until_disconnect=1)
    session = make_session(connection)
    with caplog.at_level(logging.WARNING, logger="spectra.gateway.session"):
        for bar in range(OUTBOX_CAPACITY):
            session.post(DirectorLog(bar=bar, text="flood"))
    async with asyncio.timeout(TIMEOUT_S):
        await session.run()
    assert len(connection.texts) == OUTBOX_CAPACITY
    assert connection.texts[0] == json_of(GREETING)
    assert any("control outbox full" in message for message in caplog.messages)


async def test_unexpected_errors_propagate() -> None:
    class ExplodingHandler(RecordingHandler):
        def handle(self, message: object) -> tuple[()]:
            raise RuntimeError(message)

    connection = FakeConnection()
    connection.feed('{"type":"prompt","text":"boom"}')
    with pytest.raises(ExceptionGroup) as raised:
        async with asyncio.timeout(TIMEOUT_S):
            await make_session(connection, handler=ExplodingHandler()).run()
    assert raised.group_contains(RuntimeError)


class LeaveWhileCancelledConnection(FakeConnection):
    def __init__(self, cancel: Callable[[], object]) -> None:
        super().__init__()
        self._cancel = cancel

    async def receive_text(self) -> str:
        self._cancel()
        raise ClientDisconnectedError("client left while the host was cancelling")


async def test_host_cancellation_survives_a_simultaneous_disconnect() -> None:
    with anyio.CancelScope() as host_scope:
        connection = LeaveWhileCancelledConnection(host_scope.cancel)
        await make_session(connection).run()
    assert host_scope.cancelled_caught
