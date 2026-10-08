from dataclasses import dataclass
from typing import Final, override

import numpy as np

from spectra.analysis.domain.ranges import (
    Float32Array,
    read_only_float32,
    require_array_in_range,
)

WAVEFORM_LENGTH: Final = 512


@dataclass(frozen=True, slots=True, kw_only=True)
class Waveform:
    samples: Float32Array

    def __post_init__(self) -> None:
        samples = read_only_float32(self.samples, name="waveform samples", shape=(WAVEFORM_LENGTH,))
        require_array_in_range("waveform samples", samples, low=-1.0, high=1.0)
        object.__setattr__(self, "samples", samples)

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Waveform) and np.array_equal(self.samples, other.samples)

    @override
    def __hash__(self) -> int:
        return hash(self.samples.tobytes())
