import asyncio

from spectra.analysis.application.ports import AudioFormat
from spectra.analysis.domain.signal import AudioSignal
from spectra.tracks.application.ports import AnalysisJob


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


class FakeDecoder:
    def __init__(
        self,
        *,
        signal: AudioSignal | None = None,
        probe_error: Exception | None = None,
        decode_error: Exception | None = None,
    ) -> None:
        self._signal = signal
        self._probe_error = probe_error
        self._decode_error = decode_error
        self.decoded: list[bytes] = []

    def probe(self, data: bytes) -> AudioFormat:
        if self._probe_error is not None:
            raise self._probe_error
        return AudioFormat.WAV if data else AudioFormat.MP3

    def decode(self, data: bytes) -> AudioSignal:
        self.decoded.append(data)
        if self._decode_error is not None:
            raise self._decode_error
        if self._signal is None:
            raise AssertionError("FakeDecoder has no signal to return")
        return self._signal


class FakeJobQueue:
    def __init__(self) -> None:
        self.jobs: list[AnalysisJob] = []

    def enqueue(self, job: AnalysisJob) -> None:
        self.jobs.append(job)
