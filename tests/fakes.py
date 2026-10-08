import asyncio
from collections.abc import Callable, Sequence

import numpy as np

from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import Peak, Peaks
from spectra.analysis.domain.spectrum import BAND_COUNT, Spectrum
from spectra.analysis.domain.tempo import BeatPosition, Tempo
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform
from spectra.gateway.errors import ClientDisconnectedError, UnreadableClientFrameError
from spectra.gateway.wire.messages import ClientMessage, ServerMessage


class FakeClock:
    def __init__(self, start_s: float = 0.0) -> None:
        self._now_s = start_s
        self.sleeps_s: list[float] = []

    def now_s(self) -> float:
        return self._now_s

    def set_now_s(self, now_s: float) -> None:
        self._now_s = now_s

    def advance(self, duration_s: float) -> None:
        self._now_s += duration_s

    async def sleep(self, duration_s: float) -> None:
        self.sleeps_s.append(duration_s)
        self._now_s += duration_s
        await asyncio.sleep(0)


def frame_at_bar(bar: int) -> FeatureFrame:
    return FeatureFrame(
        time_s=1.0,
        spectrum=Spectrum(bands=np.full(BAND_COUNT, 0.25, dtype=np.float32)),
        waveform=Waveform(samples=np.zeros(WAVEFORM_LENGTH, dtype=np.float32)),
        peaks=Peaks(items=(Peak(freq_hz=55.0, amplitude=1.0, phase_rad=0.0),)),
        levels=Levels(kick=1.0, bass=0.5, mid=0.25, high=0.0),
        tempo=Tempo(bpm=128.0),
        position=BeatPosition(bar=bar, beat_in_bar=0, phase=0.0),
        energy=0.5,
    )


class StaticFeatureSource:
    def __init__(self, frame: FeatureFrame) -> None:
        self.frame = frame

    def latest(self) -> FeatureFrame:
        return self.frame


class FakeConnection:
    def __init__(self, *, frames_until_disconnect: int | None = None) -> None:
        self.sent: list[str | bytes] = []
        self._incoming: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self._frames_until_disconnect = frames_until_disconnect
        self._sent_more = asyncio.Condition()

    @property
    def texts(self) -> list[str]:
        return [item for item in self.sent if isinstance(item, str)]

    @property
    def frames(self) -> list[bytes]:
        return [item for item in self.sent if isinstance(item, bytes)]

    def feed(self, message: str | bytes) -> None:
        self._incoming.put_nowait(message)

    def disconnect(self) -> None:
        self._incoming.put_nowait(None)

    async def receive_text(self) -> str:
        match await self._incoming.get():
            case None:
                raise ClientDisconnectedError("fake client left")
            case bytes():
                raise UnreadableClientFrameError("fake client sent a binary frame")
            case str() as text:
                return text

    async def wait_until(self, condition: Callable[[], bool]) -> None:
        async with self._sent_more:
            await self._sent_more.wait_for(condition)

    async def send_text(self, text: str) -> None:
        await self._record(text)

    async def send_bytes(self, data: bytes) -> None:
        limit = self._frames_until_disconnect
        if limit is not None and len(self.frames) >= limit:
            raise ClientDisconnectedError("fake client stopped reading")
        await self._record(data)

    async def _record(self, item: str | bytes) -> None:
        self.sent.append(item)
        async with self._sent_more:
            self._sent_more.notify_all()


class RecordingHandler:
    def __init__(self, replies: Sequence[ServerMessage] = ()) -> None:
        self.received: list[ClientMessage] = []
        self._replies = replies

    def handle(self, message: ClientMessage) -> Sequence[ServerMessage]:
        self.received.append(message)
        return self._replies
