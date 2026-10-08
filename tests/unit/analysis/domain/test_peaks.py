import math
from typing import Final

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.analysis.domain.errors import InvalidPeaksError, InvalidShapeError, OutOfRangeError
from spectra.analysis.domain.peaks import PEAK_COUNT, PEAK_FIELD_COUNT, Peak, Peaks


def peak(amplitude: float, freq_hz: float = 440.0) -> Peak:
    return Peak(freq_hz=freq_hz, amplitude=amplitude, phase_rad=0.0)


@pytest.mark.parametrize(
    "freq_hz", [0.0, -55.0, math.nan, math.inf], ids=["zero", "negative", "nan", "inf"]
)
def test_peak_rejects_nonpositive_or_nonfinite_freq(freq_hz: float) -> None:
    with pytest.raises(OutOfRangeError):
        Peak(freq_hz=freq_hz, amplitude=0.5, phase_rad=0.0)


@pytest.mark.parametrize("amplitude", [-0.1, 1.1, math.nan], ids=["negative", "above-one", "nan"])
def test_peak_rejects_amplitude_outside_unit(amplitude: float) -> None:
    with pytest.raises(OutOfRangeError):
        Peak(freq_hz=440.0, amplitude=amplitude, phase_rad=0.0)


@pytest.mark.parametrize("phase_rad", [math.nan, math.inf], ids=["nan", "inf"])
def test_peak_rejects_nonfinite_phase(phase_rad: float) -> None:
    with pytest.raises(OutOfRangeError):
        Peak(freq_hz=440.0, amplitude=0.5, phase_rad=phase_rad)


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
    peaks = Peaks(items=(Peak(freq_hz=55.0, amplitude=0.75, phase_rad=0.5),))
    padded = peaks.as_padded_array()
    assert padded.dtype == np.float32
    assert padded.shape == (PEAK_COUNT, PEAK_FIELD_COUNT)
    np.testing.assert_array_equal(padded[0], [55.0, 0.75, 0.5])
    np.testing.assert_array_equal(padded[1:], 0.0)


def test_from_padded_array_drops_padding_rows() -> None:
    padded = np.zeros((PEAK_COUNT, PEAK_FIELD_COUNT), dtype=np.float32)
    padded[0] = (55.0, 0.75, 0.5)
    padded[1] = (440.0, 0.5, 1.25)
    peaks = Peaks.from_padded_array(padded)
    assert peaks.items == (
        Peak(freq_hz=55.0, amplitude=0.75, phase_rad=0.5),
        Peak(freq_hz=440.0, amplitude=0.5, phase_rad=1.25),
    )


def test_from_padded_array_rejects_wrong_shape() -> None:
    with pytest.raises(InvalidShapeError):
        Peaks.from_padded_array(np.zeros((PEAK_COUNT, 2), dtype=np.float32))


@pytest.mark.parametrize(
    "rows",
    [
        [(0.0, 0.0, 0.0), (440.0, 0.5, 0.0)],
        [(55.0, 0.75, 0.0), (0.0, 0.5, 0.0)],
    ],
    ids=["gap-before-peak", "padding-with-amplitude"],
)
def test_from_padded_array_rejects_malformed_padding(
    rows: list[tuple[float, float, float]],
) -> None:
    padded = np.zeros((PEAK_COUNT, PEAK_FIELD_COUNT), dtype=np.float32)
    padded[: len(rows)] = rows
    with pytest.raises(InvalidPeaksError):
        Peaks.from_padded_array(padded)


PEAK_STRATEGY: Final = st.builds(
    Peak,
    freq_hz=st.floats(min_value=1.0, max_value=24_000.0),
    amplitude=st.floats(min_value=0.0, max_value=1.0),
    phase_rad=st.floats(min_value=-2 * math.pi, max_value=2 * math.pi),
)


@given(candidates=st.lists(PEAK_STRATEGY, max_size=PEAK_COUNT))
def test_padded_array_round_trip(candidates: list[Peak]) -> None:
    padded = Peaks.ranked(candidates).as_padded_array()
    restored = Peaks.from_padded_array(padded)
    assert len(restored.items) == len(candidates)
    np.testing.assert_array_equal(restored.as_padded_array(), padded)
