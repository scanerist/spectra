from typing import Final

import numpy as np

from spectra.analysis.domain.ranges import Float32Array

LOG_FLOOR: Final = 1e-30
RELEASE_FLOOR: Final = 1e-12


def release(values: Float32Array, *, release_s: float, frame_rate_hz: float) -> Float32Array:
    log_decay = -1.0 / (release_s * frame_rate_hz)
    ramp = np.arange(values.shape[0], dtype=np.float64).reshape((-1,) + (1,) * (values.ndim - 1))
    logs = np.log(np.maximum(values.astype(np.float64), LOG_FLOOR))
    held = np.maximum.accumulate(logs - ramp * log_decay, axis=0) + ramp * log_decay
    envelope = np.exp(held)
    return np.where(envelope < RELEASE_FLOOR, 0.0, envelope).astype(np.float32)


def moving_average(values: Float32Array, *, width_frames: int) -> Float32Array:
    width = max(1, width_frames)
    kernel = np.full(width, 1.0 / width)
    padded = np.pad(values.astype(np.float64), (width // 2, width - 1 - width // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


def normalise_db(
    level_db: Float32Array, *, range_db: float, percentile: float, min_reference_db: float
) -> Float32Array:
    reference_db = max(float(np.percentile(level_db, percentile)), min_reference_db)
    scaled = (level_db - (reference_db - range_db)) / range_db
    return np.asarray(np.clip(scaled, 0.0, 1.0), dtype=np.float32)


def power_to_db(power: Float32Array, *, floor_db: float) -> Float32Array:
    floor = 10.0 ** (floor_db / 10.0)
    return np.asarray(10.0 * np.log10(np.maximum(power, floor)), dtype=np.float32)
