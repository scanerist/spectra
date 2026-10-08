import math

import numpy as np
import pytest

from spectra.analysis.domain.errors import InvalidTimeError, OutOfRangeError
from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import Peak, Peaks
from spectra.analysis.domain.spectrum import BAND_COUNT, Spectrum
from spectra.analysis.domain.tempo import BeatPosition, Tempo
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform


def make_frame(*, time_s: float = 1.5, energy: float = 0.5) -> FeatureFrame:
    return FeatureFrame(
        time_s=time_s,
        spectrum=Spectrum(bands=np.full(BAND_COUNT, 0.25, dtype=np.float32)),
        waveform=Waveform(samples=np.zeros(WAVEFORM_LENGTH, dtype=np.float32)),
        peaks=Peaks(items=(Peak(freq_hz=55.0, amplitude=0.75, phase_rad=0.5),)),
        levels=Levels(kick=0.75, bass=0.5, mid=0.25, high=0.125),
        tempo=Tempo(bpm=128.0),
        position=BeatPosition(bar=3, beat_in_bar=2, phase=0.25),
        energy=energy,
    )


def test_frames_with_equal_parts_are_equal() -> None:
    assert make_frame() == make_frame()
    assert make_frame() != make_frame(energy=0.75)


@pytest.mark.parametrize("time_s", [-0.5, math.nan, math.inf], ids=["negative", "nan", "inf"])
def test_frame_rejects_invalid_time(time_s: float) -> None:
    with pytest.raises(InvalidTimeError):
        make_frame(time_s=time_s)


@pytest.mark.parametrize("energy", [-0.01, 1.01, math.nan], ids=["negative", "above-one", "nan"])
def test_frame_rejects_energy_outside_unit(energy: float) -> None:
    with pytest.raises(OutOfRangeError):
        make_frame(energy=energy)
