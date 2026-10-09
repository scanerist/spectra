from typing import Final

import numpy as np

from spectra.analysis.domain.envelopes import normalise_db, power_to_db
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.spectrum import band_centers_hz

ONSET_MAX_FREQ_HZ: Final = 250.0
ONSET_RANGE_DB: Final = 50.0
ONSET_REFERENCE_PERCENTILE: Final = 99.5
ONSET_MIN_REFERENCE_DB: Final = -60.0
ONSET_FLOOR_DB: Final = -120.0
WINDOW_LEAD_FRAMES: Final = 1


def onset_envelope(
    band_power: Float32Array, *, max_freq_hz: float = ONSET_MAX_FREQ_HZ
) -> Float32Array:
    selected = band_power[:, band_centers_hz() <= max_freq_hz]
    scaled = normalise_db(
        power_to_db(selected, floor_db=ONSET_FLOOR_DB),
        range_db=ONSET_RANGE_DB,
        percentile=ONSET_REFERENCE_PERCENTILE,
        min_reference_db=ONSET_MIN_REFERENCE_DB,
    )
    rises = np.maximum(np.diff(scaled, axis=0, prepend=scaled[:1]), 0.0)
    flux = np.roll(rises.mean(axis=1), WINDOW_LEAD_FRAMES)
    flux[:WINDOW_LEAD_FRAMES] = 0.0
    peak = float(flux.max())
    return np.asarray(flux / peak if peak > 0.0 else flux, dtype=np.float32)
