import asyncio

import numpy as np

from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import Peak, Peaks
from spectra.analysis.domain.spectrum import BAND_COUNT, Spectrum
from spectra.analysis.domain.tempo import BeatPosition, Tempo
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform


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
