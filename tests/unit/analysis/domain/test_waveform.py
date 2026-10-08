import math

import numpy as np
import pytest

from spectra.analysis.domain.errors import InvalidShapeError, OutOfRangeError
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform


def test_waveform_accepts_full_scale_samples() -> None:
    samples = np.linspace(-1.0, 1.0, WAVEFORM_LENGTH, dtype=np.float32)
    waveform = Waveform(samples=samples)
    np.testing.assert_array_equal(waveform.samples, samples)


@pytest.mark.parametrize(
    "length", [WAVEFORM_LENGTH - 1, WAVEFORM_LENGTH + 1, 0], ids=["short", "long", "empty"]
)
def test_waveform_rejects_wrong_length(length: int) -> None:
    with pytest.raises(InvalidShapeError):
        Waveform(samples=np.zeros(length, dtype=np.float32))


@pytest.mark.parametrize(
    "value", [-1.01, 1.01, math.nan, -math.inf], ids=["below-minus-one", "above-one", "nan", "inf"]
)
def test_waveform_rejects_out_of_range_samples(value: float) -> None:
    samples = np.zeros(WAVEFORM_LENGTH, dtype=np.float32)
    samples[100] = value
    with pytest.raises(OutOfRangeError):
        Waveform(samples=samples)


def test_waveform_samples_are_read_only() -> None:
    waveform = Waveform(samples=np.zeros(WAVEFORM_LENGTH, dtype=np.float32))
    with pytest.raises(ValueError, match="read-only"):
        waveform.samples[0] = 0.5


def test_waveform_does_not_freeze_caller_array() -> None:
    samples = np.zeros(WAVEFORM_LENGTH, dtype=np.float32)
    Waveform(samples=samples)
    assert samples.flags.writeable


def test_waveforms_with_equal_samples_are_equal() -> None:
    first = Waveform(samples=np.full(WAVEFORM_LENGTH, -0.5, dtype=np.float32))
    second = Waveform(samples=np.full(WAVEFORM_LENGTH, -0.5, dtype=np.float32))
    assert first == second
    assert hash(first) == hash(second)
    assert first != Waveform(samples=np.zeros(WAVEFORM_LENGTH, dtype=np.float32))
