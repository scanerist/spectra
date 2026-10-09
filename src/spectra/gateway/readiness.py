import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Final

from fastapi import FastAPI
from fastapi.requests import HTTPConnection

type Probe = Callable[[], Awaitable[bool]]

READINESS_STATE: Final = "readiness"
PROBE_TIMEOUT_S: Final = 2.0


@dataclass(frozen=True, slots=True, kw_only=True)
class Readiness:
    probes: Mapping[str, Probe] = field(default_factory=dict)
    timeout_s: float = PROBE_TIMEOUT_S

    async def silent(self) -> list[str]:
        async with asyncio.TaskGroup() as group:
            answers = {
                name: group.create_task(self._answers(probe)) for name, probe in self.probes.items()
            }
        return sorted(name for name, answer in answers.items() if not answer.result())

    async def _answers(self, probe: Probe) -> bool:
        try:
            async with asyncio.timeout(self.timeout_s):
                return await probe()
        except TimeoutError:
            return False


def install_readiness(app: FastAPI, readiness: Readiness) -> None:
    setattr(app.state, READINESS_STATE, readiness)


def readiness(connection: HTTPConnection) -> Readiness:
    installed = getattr(connection.app.state, READINESS_STATE, None)
    return installed if isinstance(installed, Readiness) else Readiness()
