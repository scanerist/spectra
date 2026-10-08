import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from spectra.analysis.domain.errors import InvalidShapeError, InvalidTimeError, OutOfRangeError

type Float32Array = NDArray[np.float32]


def require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise OutOfRangeError(f"{name} must be finite, got {value}")


def require_time(time_s: float) -> None:
    if not (math.isfinite(time_s) and time_s >= 0.0):
        raise InvalidTimeError(f"time must be finite and >= 0, got {time_s}")


def require_in_range(name: str, value: float, *, low: float, high: float) -> None:
    if not low <= value <= high:
        raise OutOfRangeError(f"{name} must be in [{low}, {high}], got {value}")


def require_unit_interval(name: str, value: float) -> None:
    require_in_range(name, value, low=0.0, high=1.0)


def read_only_float32(values: ArrayLike, *, name: str, shape: tuple[int, ...]) -> Float32Array:
    array = np.array(values, dtype=np.float32)
    if array.shape != shape:
        raise InvalidShapeError(f"{name} must have shape {shape}, got {array.shape}")
    array.flags.writeable = False
    return array


def require_array_in_range(name: str, values: Float32Array, *, low: float, high: float) -> None:
    if not np.all((values >= low) & (values <= high)):
        raise OutOfRangeError(f"{name} must lie in [{low}, {high}]")
