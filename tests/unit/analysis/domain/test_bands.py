import numpy as np
import pytest

from spectra.analysis.domain.bands import (
    BAND_COUNT,
    MAX_BAND_FREQ_HZ,
    MIN_BAND_FREQ_HZ,
    band_centers_hz,
    band_edges_hz,
    band_levels,
    band_weights,
    fold_to_bands,
)
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.stft import bin_freqs_hz, stft_chunks
from tests.signals import noise, signal_of, silence, sine


def band_power_of(samples: Float32Array) -> Float32Array:
    return fold_to_bands(stft_chunks(signal_of(samples)))


def nearest_band(freq_hz: float) -> int:
    return int(np.argmin(np.abs(np.log(band_centers_hz() / freq_hz))))


def test_band_centers_span_log_range() -> None:
    centers_hz = band_centers_hz()
    assert centers_hz.shape == (BAND_COUNT,)
    assert centers_hz[0] == pytest.approx(MIN_BAND_FREQ_HZ)
    assert centers_hz[-1] == pytest.approx(MAX_BAND_FREQ_HZ)
    np.testing.assert_allclose(np.diff(np.log(centers_hz)), np.log(centers_hz[1] / centers_hz[0]))


def test_band_edges_bracket_every_centre() -> None:
    edges = band_edges_hz()
    centres = band_centers_hz()
    assert edges.shape == (BAND_COUNT + 1,)
    assert np.all(edges[:-1] < centres)
    assert np.all(centres < edges[1:])


def test_every_band_weight_row_sums_to_one() -> None:
    weights = band_weights(bin_freqs_hz())
    assert weights.shape == (BAND_COUNT, bin_freqs_hz().size)
    np.testing.assert_allclose(weights.sum(axis=1), 1.0)


@pytest.mark.parametrize("freq_hz", [1_000.0, 5_000.0, 12_000.0], ids=["1k", "5k", "12k"])
def test_sine_is_loudest_in_the_band_around_it(freq_hz: float) -> None:
    power = band_power_of(sine(freq_hz, 1.0))
    assert int(np.argmax(power[20:-20].mean(axis=0))) == nearest_band(freq_hz)


def test_low_sine_is_loudest_within_one_band_of_it() -> None:
    power = band_power_of(sine(45.0, 2.0))
    assert abs(int(np.argmax(power[20:-20].mean(axis=0))) - nearest_band(45.0)) <= 1


def test_white_noise_folds_into_roughly_equal_band_power() -> None:
    mean_power = band_power_of(noise(4.0))[20:-20].mean(axis=0)
    assert mean_power.max() / mean_power.min() < 1.6


def test_fold_keeps_one_row_per_frame() -> None:
    power = band_power_of(sine(440.0, 0.5))
    assert power.dtype == np.float32
    assert power.shape[1] == BAND_COUNT


def test_band_levels_are_float32_in_unit_interval() -> None:
    levels = band_levels(band_power_of(noise(1.0)))
    assert levels.dtype == np.float32
    assert levels.min() >= 0.0
    assert levels.max() <= 1.0


def test_band_levels_of_silence_are_zero() -> None:
    assert not band_levels(band_power_of(silence(1.0))).any()


def test_quieter_passage_reads_lower_by_its_level_difference() -> None:
    loud = sine(1_000.0, 1.0)
    quiet = sine(1_000.0, 1.0, amplitude=10 ** (-30 / 20))
    levels = band_levels(band_power_of(np.concatenate([loud, quiet])))
    band = nearest_band(1_000.0)
    assert levels[40, band] == pytest.approx(1.0, abs=0.02)
    assert levels[-40, band] == pytest.approx(0.5, abs=0.02)
