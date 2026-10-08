from dataclasses import dataclass
from typing import Final, override

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.ranges import (
    Float32Array,
    read_only_float32,
    require_array_in_range,
)

BAND_COUNT: Final = 64
MIN_BAND_FREQ_HZ: Final = 30.0
MAX_BAND_FREQ_HZ: Final = 16_000.0


def band_centers_hz() -> NDArray[np.float64]:
    return np.geomspace(MIN_BAND_FREQ_HZ, MAX_BAND_FREQ_HZ, BAND_COUNT)


@dataclass(frozen=True, slots=True, kw_only=True)
class Spectrum:
    bands: Float32Array

    def __post_init__(self) -> None:
        bands = read_only_float32(self.bands, name="spectrum bands", shape=(BAND_COUNT,))
        require_array_in_range("spectrum bands", bands, low=0.0, high=1.0)
        object.__setattr__(self, "bands", bands)

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Spectrum) and np.array_equal(self.bands, other.bands)

    @override
    def __hash__(self) -> int:
        return hash(self.bands.tobytes())
