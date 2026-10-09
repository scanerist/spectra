from collections.abc import Iterable
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.envelopes import normalise_db, power_to_db, release
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.spectrum import BAND_COUNT, band_centers_hz
from spectra.analysis.domain.stft import FRAME_RATE_HZ, bin_freqs_hz

BAND_RANGE_DB: Final = 60.0
BAND_REFERENCE_PERCENTILE: Final = 99.5
MIN_REFERENCE_DB: Final = -40.0
FLOOR_DB: Final = -120.0
BAND_RELEASE_S: Final = 0.08


def band_edges_hz() -> NDArray[np.float64]:
    log_centers = np.log(band_centers_hz())
    half_step = (log_centers[1] - log_centers[0]) / 2.0
    edges = np.concatenate([[log_centers[0] - half_step], log_centers + half_step])
    return np.exp(edges)


def interpolation_weights(
    targets_hz: NDArray[np.float64], freqs_hz: NDArray[np.float64]
) -> NDArray[np.float64]:
    positions = np.interp(targets_hz, freqs_hz, np.arange(freqs_hz.size, dtype=np.float64))
    lower = np.floor(positions).astype(np.int64)
    upper = np.minimum(lower + 1, freqs_hz.size - 1)
    fraction = positions - lower
    rows = np.arange(targets_hz.size)
    weights = np.zeros((targets_hz.size, freqs_hz.size))
    np.add.at(weights, (rows, lower), 1.0 - fraction)
    np.add.at(weights, (rows, upper), fraction)
    return weights


def band_weights(freqs_hz: NDArray[np.float64]) -> NDArray[np.float64]:
    edges = band_edges_hz()
    inside = (freqs_hz >= edges[:-1, np.newaxis]) & (freqs_hz < edges[1:, np.newaxis])
    counts = inside.sum(axis=1, keepdims=True)
    averaged = inside / np.maximum(counts, 1)
    return np.where(counts > 0, averaged, interpolation_weights(band_centers_hz(), freqs_hz))


def fold_to_bands(magnitude_chunks: Iterable[Float32Array]) -> Float32Array:
    weights = band_weights(bin_freqs_hz()).T.astype(np.float32)
    folded = [np.square(chunk) @ weights for chunk in magnitude_chunks]
    if not folded:
        return np.zeros((0, BAND_COUNT), dtype=np.float32)
    return np.concatenate(folded).astype(np.float32)


def band_levels(band_power: Float32Array) -> Float32Array:
    level_db = power_to_db(band_power, floor_db=FLOOR_DB)
    scaled = normalise_db(
        level_db,
        range_db=BAND_RANGE_DB,
        percentile=BAND_REFERENCE_PERCENTILE,
        min_reference_db=MIN_REFERENCE_DB,
    )
    smoothed = release(scaled, release_s=BAND_RELEASE_S, frame_rate_hz=FRAME_RATE_HZ)
    return np.clip(smoothed, 0.0, 1.0).astype(np.float32)
