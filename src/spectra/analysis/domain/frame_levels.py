from typing import Final

import numpy as np

from spectra.analysis.domain.envelopes import moving_average, normalise_db, power_to_db, release
from spectra.analysis.domain.onsets import onset_envelope
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.spectrum import band_centers_hz
from spectra.analysis.domain.stft import FRAME_RATE_HZ

LEVEL_COLUMNS: Final = ("kick", "bass", "mid", "high", "energy")
LEVEL_COUNT: Final = len(LEVEL_COLUMNS)
KICK_MIN_FREQ_HZ: Final = 40.0
KICK_MAX_FREQ_HZ: Final = 120.0
KICK_DECAY_S: Final = 0.12
KICK_REFERENCE_PERCENTILE: Final = 99.5
KICK_MIN_REFERENCE: Final = 0.25
BASS_HZ: Final = (60.0, 250.0)
MID_HZ: Final = (250.0, 4_000.0)
HIGH_HZ: Final = (4_000.0, 16_001.0)
RANGE_DB: Final = 48.0
RANGE_REFERENCE_PERCENTILE: Final = 99.5
RANGE_MIN_REFERENCE_DB: Final = -40.0
RANGE_FLOOR_DB: Final = -120.0
RANGE_RELEASE_S: Final = 0.12
ENERGY_WINDOW_S: Final = 6.0


def frame_levels(band_power: Float32Array, band_levels: Float32Array) -> Float32Array:
    columns = [
        kick_level(band_power),
        range_level(band_power, BASS_HZ),
        range_level(band_power, MID_HZ),
        range_level(band_power, HIGH_HZ),
        energy_level(band_levels),
    ]
    return np.stack(columns, axis=1).astype(np.float32)


def kick_level(band_power: Float32Array) -> Float32Array:
    attacks = onset_envelope(band_power, min_freq_hz=KICK_MIN_FREQ_HZ, max_freq_hz=KICK_MAX_FREQ_HZ)
    if not attacks.any():
        return attacks
    reference = max(float(np.percentile(attacks, KICK_REFERENCE_PERCENTILE)), KICK_MIN_REFERENCE)
    strikes = np.asarray(np.clip(attacks / reference, 0.0, 1.0), dtype=np.float32)
    return release(strikes, release_s=KICK_DECAY_S, frame_rate_hz=FRAME_RATE_HZ)


def range_level(band_power: Float32Array, span_hz: tuple[float, float]) -> Float32Array:
    centres_hz = band_centers_hz()
    inside = (centres_hz >= span_hz[0]) & (centres_hz < span_hz[1])
    level_db = power_to_db(band_power[:, inside].sum(axis=1), floor_db=RANGE_FLOOR_DB)
    scaled = normalise_db(
        level_db,
        range_db=RANGE_DB,
        percentile=RANGE_REFERENCE_PERCENTILE,
        min_reference_db=RANGE_MIN_REFERENCE_DB,
    )
    return release(scaled, release_s=RANGE_RELEASE_S, frame_rate_hz=FRAME_RATE_HZ)


def energy_level(band_levels: Float32Array) -> Float32Array:
    loudness = band_levels.mean(axis=1).astype(np.float32)
    slow = moving_average(loudness, width_frames=round(ENERGY_WINDOW_S * FRAME_RATE_HZ))
    peak = float(slow.max())
    return np.asarray(slow / peak if peak > 0.0 else slow, dtype=np.float32)
