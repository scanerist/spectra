import math

import numpy as np
import pytest

from spectra.analysis.domain.errors import InvalidSignalError
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ, AudioSignal


def test_duration_counts_samples_at_the_analysis_rate() -> None:
    signal = AudioSignal(samples=np.zeros(ANALYSIS_SAMPLE_RATE_HZ * 3, dtype=np.float32))
    assert signal.sample_count == ANALYSIS_SAMPLE_RATE_HZ * 3
    assert signal.duration_s == 3.0


@pytest.mark.parametrize(
    "samples",
    [np.zeros(0, dtype=np.float32), np.zeros((2, 8), dtype=np.float32)],
    ids=["empty", "stereo"],
)
def test_signal_rejects_non_mono_or_empty_arrays(samples: Float32Array) -> None:
    with pytest.raises(InvalidSignalError):
        AudioSignal(samples=samples)


@pytest.mark.parametrize("value", [math.nan, math.inf], ids=["nan", "inf"])
def test_signal_rejects_non_finite_samples(value: float) -> None:
    samples = np.zeros(16, dtype=np.float32)
    samples[3] = value
    with pytest.raises(InvalidSignalError):
        AudioSignal(samples=samples)


def test_signal_samples_are_read_only_float32() -> None:
    signal = AudioSignal(samples=np.zeros(16, dtype=np.float64))
    assert signal.samples.dtype == np.float32
    with pytest.raises(ValueError, match="read-only"):
        signal.samples[0] = 1.0


def test_signal_does_not_freeze_caller_array() -> None:
    samples = np.zeros(16, dtype=np.float32)
    AudioSignal(samples=samples)
    samples[0] = 1.0
    assert samples.flags.writeable
