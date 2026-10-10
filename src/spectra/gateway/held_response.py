import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Final, override

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from spectra.gateway.slots import Slot

logger = logging.getLogger(__name__)

CHUNK_BYTES: Final = 64 * 1024


async def chunks_of(content: bytes, chunk_bytes: int) -> AsyncIterator[bytes]:
    view = memoryview(content)
    for start in range(0, len(content), chunk_bytes):
        yield bytes(view[start : start + chunk_bytes])


class HeldStreamingResponse(StreamingResponse):
    def __init__(
        self,
        slot: Slot,
        *,
        content: bytes,
        media_type: str,
        headers: Mapping[str, str],
        deadline_s: float,
    ) -> None:
        super().__init__(
            chunks_of(content, CHUNK_BYTES),
            media_type=media_type,
            headers={**headers, "Content-Length": str(len(content))},
        )
        self._slot = slot
        self._deadline_s = deadline_s

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            async with asyncio.timeout(self._deadline_s):
                await super().__call__(scope, receive, send)
        except TimeoutError:
            logger.info("a reader took longer than %s s, dropped", self._deadline_s)
        finally:
            self._slot.release()
