import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from spectra.analysis.application.ports import FeatureSource
from spectra.gateway.connection import ClientConnection
from spectra.gateway.errors import ClientDisconnectedError, UnreadableClientFrameError
from spectra.gateway.handlers import ClientMessageHandler
from spectra.gateway.pacing import FramePacer
from spectra.gateway.wire.frame_codec import encode_frame
from spectra.gateway.wire.messages import CLIENT_MESSAGE_ADAPTER, ServerMessage
from spectra.shared.clock import Clock

logger = logging.getLogger(__name__)

OUTBOX_CAPACITY: Final = 256


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionDependencies:
    source: FeatureSource
    handler: ClientMessageHandler
    clock: Clock
    frame_rate_hz: float
    greeting: ServerMessage


class ClientSession:
    def __init__(self, *, connection: ClientConnection, dependencies: SessionDependencies) -> None:
        self._connection = connection
        self._dependencies = dependencies
        self._outbox: asyncio.Queue[ServerMessage] = asyncio.Queue(maxsize=OUTBOX_CAPACITY)
        self.post(dependencies.greeting)

    def post(self, message: ServerMessage) -> None:
        try:
            self._outbox.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("control outbox full, dropping %s", message.type)

    async def run(self) -> None:
        async with asyncio.TaskGroup() as group:
            reader = group.create_task(self._until_disconnected(self._read_forever))
            writer = group.create_task(self._until_disconnected(self._write_forever))
            reader.add_done_callback(lambda _: writer.cancel())
            writer.add_done_callback(lambda _: reader.cancel())

    async def _until_disconnected(self, loop: Callable[[], Awaitable[None]]) -> None:
        try:
            await loop()
        except ClientDisconnectedError as error:
            logger.info("client session ended: %s", error)

    async def _write_forever(self) -> None:
        clock = self._dependencies.clock
        pacer = FramePacer(frame_rate_hz=self._dependencies.frame_rate_hz, start_s=clock.now_s())
        while True:
            await self._flush_outbox()
            await self._connection.send_bytes(encode_frame(self._dependencies.source.latest()))
            await clock.sleep(pacer.delay_s(clock.now_s()))

    async def _flush_outbox(self) -> None:
        while not self._outbox.empty():
            await self._connection.send_text(self._outbox.get_nowait().model_dump_json())

    async def _read_forever(self) -> None:
        while True:
            await self._read_one()

    async def _read_one(self) -> None:
        try:
            message = CLIENT_MESSAGE_ADAPTER.validate_json(await self._connection.receive_text())
        except ValidationError as error:
            logger.warning(
                "skipping invalid client message: %s", error.errors(include_url=False)[:1]
            )
            return
        except UnreadableClientFrameError as error:
            logger.warning("skipping invalid client message: %s", error)
            return
        for reply in self._dependencies.handler.handle(message):
            self.post(reply)
