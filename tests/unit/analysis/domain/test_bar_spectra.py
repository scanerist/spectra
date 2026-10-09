from typing import Final

import numpy as np
import pytest

from spectra.analysis.domain.bar_spectra import (
    FOURIER_BIN_COUNT,
    bar_peaks,
    bar_spectra,
    fourier_bin_centers_hz,
)
from spectra.analysis.domain.beat_grid import BeatGrid
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.tempo import Tempo
from tests.signals import signal_of, silence, sine

GRID: Final = BeatGrid(tempo=Tempo(bpm=120.0), offset_s=0.0)
BAR_S: Final = 2.0
FREQ_TOLERANCE: Final = 0.015


def spectra_of(samples: Float32Array) -> Float32Array:
    signal = signal_of(samples)
    return bar_spectra(signal, grid=GRID, bar_count=GRID.bar_count(signal.duration_s))


def two_tones(duration_s: float, *, gain: float = 1.0) -> Float32Array:
    low = sine(55.0, duration_s, amplitude=0.6 * gain)
    octave = sine(110.0, duration_s, amplitude=0.3 * gain)
    return low + octave


def test_bin_centres_span_30_to_600_hz_log_spaced() -> None:
    centres_hz = fourier_bin_centers_hz()
    assert centres_hz.shape == (FOURIER_BIN_COUNT,)
    assert centres_hz[0] == pytest.approx(30.0)
    assert centres_hz[-1] == pytest.approx(600.0)
    np.testing.assert_allclose(np.diff(np.log(centres_hz)), np.log(20.0) / 199)


def test_spectra_are_one_float32_row_per_bar_normalised_to_the_track() -> None:
    spectra = spectra_of(two_tones(8 * BAR_S))
    assert spectra.dtype == np.float32
    assert spectra.shape == (8, FOURIER_BIN_COUNT)
    assert spectra.min() >= 0.0
    assert spectra.max() == pytest.approx(1.0)


@pytest.mark.parametrize("bar", [1, 4, 6], ids=lambda b: f"bar-{b}")
def test_peaks_find_both_tones_in_every_bar(bar: int) -> None:
    peaks = bar_peaks(spectra_of(two_tones(8 * BAR_S))[bar]).items
    assert peaks[0].freq_hz == pytest.approx(55.0, rel=FREQ_TOLERANCE)
    assert peaks[1].freq_hz == pytest.approx(110.0, rel=FREQ_TOLERANCE)
    assert peaks[1].amplitude / peaks[0].amplitude == pytest.approx(0.5, abs=0.08)


def test_quieter_bars_stay_quieter_than_the_loudest() -> None:
    samples = np.concatenate([two_tones(4 * BAR_S), two_tones(4 * BAR_S, gain=0.25)])
    spectra = spectra_of(samples)
    assert spectra[6].max() / spectra[1].max() == pytest.approx(0.25, abs=0.03)


def test_silent_bars_have_no_spectrum_and_no_peaks() -> None:
    spectra = spectra_of(np.concatenate([two_tones(4 * BAR_S), silence(4 * BAR_S)]))
    assert not spectra[6].any()
    assert bar_peaks(spectra[6]).items == ()


def test_peaks_ignore_ripples_below_a_fifth_of_the_bar_maximum() -> None:
    spectrum = np.zeros(FOURIER_BIN_COUNT, dtype=np.float32)
    spectrum[50] = 1.0
    spectrum[120] = 0.1
    peaks = bar_peaks(spectrum).items
    assert len(peaks) == 1
    assert peaks[0].freq_hz == pytest.approx(fourier_bin_centers_hz()[50])
