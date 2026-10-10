import math
from typing import Final

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.analysis.domain.errors import InvalidPeaksError, OutOfRangeError
from spectra.analysis.domain.peaks import PEAK_COUNT, PEAK_FIELD_COUNT, Peak, Peaks


def peak(amplitude: float, freq_hz: float = 440.0) -> Peak:
    return Peak(freq_hz=freq_hz, amplitude=amplitude)


@pytest.mark.parametrize(
    "freq_hz", [0.0, -55.0, math.nan, math.inf], ids=["zero", "negative", "nan", "inf"]
)
def test_peak_rejects_nonpositive_or_nonfinite_freq(freq_hz: float) -> None:
    with pytest.raises(OutOfRangeError):
        Peak(freq_hz=freq_hz, amplitude=0.5)


@pytest.mark.parametrize("amplitude", [-0.1, 1.1, math.nan], ids=["negative", "above-one", "nan"])
def test_peak_rejects_amplitude_outside_unit(amplitude: float) -> None:
    with pytest.raises(OutOfRangeError):
        Peak(freq_hz=440.0, amplitude=amplitude)


def test_peaks_may_be_empty() -> None:
    assert Peaks(items=()).items == ()


def test_peaks_reject_more_than_peak_count() -> None:
    with pytest.raises(InvalidPeaksError):
        Peaks(items=tuple(peak(0.5) for _ in range(PEAK_COUNT + 1)))


def test_peaks_reject_ascending_amplitudes() -> None:
    with pytest.raises(InvalidPeaksError):
        Peaks(items=(peak(0.2), peak(0.8)))


def test_ranked_sorts_by_amplitude_descending_and_keeps_ties_stable() -> None:
    ranked = Peaks.ranked([peak(0.2, 55.0), peak(0.9, 110.0), peak(0.2, 220.0), peak(0.5, 440.0)])
    assert [p.freq_hz for p in ranked.items] == [110.0, 440.0, 55.0, 220.0]


def test_ranked_keeps_only_the_strongest_peak_count() -> None:
    ranked = Peaks.ranked([peak(i / 10) for i in range(PEAK_COUNT + 2)])
    assert len(ranked.items) == PEAK_COUNT
    assert ranked.items[-1].amplitude == pytest.approx(0.2)


def test_padded_array_is_zero_filled_float32_rows() -> None:
    peaks = Peaks(items=(Peak(freq_hz=55.0, amplitude=0.75),))
    padded = peaks.as_padded_array()
    assert padded.dtype == np.float32
    assert padded.shape == (PEAK_COUNT, PEAK_FIELD_COUNT) == (8, 2)
    np.testing.assert_array_equal(padded[0], [55.0, 0.75])
    np.testing.assert_array_equal(padded[1:], 0.0)


PEAK_STRATEGY: Final = st.builds(
    Peak,
    freq_hz=st.floats(min_value=1.0, max_value=24_000.0),
    amplitude=st.floats(min_value=0.0, max_value=1.0),
)


@given(candidates=st.lists(PEAK_STRATEGY, max_size=PEAK_COUNT))
def test_padded_array_lists_every_peak_by_amplitude_before_zero_rows(
    candidates: list[Peak],
) -> None:
    padded = Peaks.ranked(candidates).as_padded_array()
    count = len(candidates)
    assert np.all(padded[:count, 0] > 0.0)
    assert np.all(np.diff(padded[:count, 1]) <= 0.0)
    np.testing.assert_array_equal(padded[count:], 0.0)
