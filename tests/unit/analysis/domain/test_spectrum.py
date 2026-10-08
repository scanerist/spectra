import math

import numpy as np
import pytest

from spectra.analysis.domain.errors import InvalidShapeError, OutOfRangeError
from spectra.analysis.domain.spectrum import (
    BAND_COUNT,
    MAX_BAND_FREQ_HZ,
    MIN_BAND_FREQ_HZ,
    Spectrum,
    band_centers_hz,
)


def test_spectrum_holds_bands_of_band_count() -> None:
    spectrum = Spectrum(bands=np.full(BAND_COUNT, 0.5, dtype=np.float32))
    assert spectrum.bands.dtype == np.float32
    assert spectrum.bands.shape == (BAND_COUNT,)


@pytest.mark.parametrize(
    "length", [BAND_COUNT - 1, BAND_COUNT + 1, 0], ids=["short", "long", "empty"]
)
def test_spectrum_rejects_wrong_length(length: int) -> None:
    with pytest.raises(InvalidShapeError):
        Spectrum(bands=np.zeros(length, dtype=np.float32))


@pytest.mark.parametrize(
    "value", [-0.01, 1.01, math.nan, math.inf], ids=["negative", "above-one", "nan", "inf"]
)
def test_spectrum_rejects_out_of_range_values(value: float) -> None:
    bands = np.zeros(BAND_COUNT, dtype=np.float32)
    bands[7] = value
    with pytest.raises(OutOfRangeError):
        Spectrum(bands=bands)


def test_spectrum_bands_are_read_only() -> None:
    spectrum = Spectrum(bands=np.zeros(BAND_COUNT, dtype=np.float32))
    with pytest.raises(ValueError, match="read-only"):
        spectrum.bands[0] = 1.0


def test_spectrum_does_not_freeze_caller_array() -> None:
    bands = np.zeros(BAND_COUNT, dtype=np.float32)
    Spectrum(bands=bands)
    bands[0] = 1.0
    assert bands.flags.writeable


def test_spectra_with_equal_bands_are_equal() -> None:
    first = Spectrum(bands=np.linspace(0.0, 1.0, BAND_COUNT, dtype=np.float32))
    second = Spectrum(bands=np.linspace(0.0, 1.0, BAND_COUNT, dtype=np.float32))
    assert first == second
    assert hash(first) == hash(second)
    assert first != Spectrum(bands=np.zeros(BAND_COUNT, dtype=np.float32))


def test_band_centers_span_log_range() -> None:
    centers_hz = band_centers_hz()
    assert centers_hz.shape == (BAND_COUNT,)
    assert centers_hz[0] == pytest.approx(MIN_BAND_FREQ_HZ)
    assert centers_hz[-1] == pytest.approx(MAX_BAND_FREQ_HZ)
    np.testing.assert_allclose(np.diff(np.log(centers_hz)), np.log(centers_hz[1] / centers_hz[0]))
