import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    def now_s(self) -> float: ...

    async def sleep(self, duration_s: float) -> None: ...


class MonotonicClock:
    def now_s(self) -> float:
        return time.monotonic()

    async def sleep(self, duration_s: float) -> None:
        await asyncio.sleep(duration_s)
