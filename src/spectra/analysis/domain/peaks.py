import math
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Self

import numpy as np

from spectra.analysis.domain.errors import InvalidPeaksError, OutOfRangeError
from spectra.analysis.domain.ranges import (
    Float32Array,
    read_only_float32,
    require_unit_interval,
)

PEAK_COUNT: Final = 8
PEAK_FIELD_COUNT: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class Peak:
    freq_hz: float
    amplitude: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.freq_hz) and self.freq_hz > 0.0):
            raise OutOfRangeError(f"peak freq_hz must be finite and > 0, got {self.freq_hz}")
        require_unit_interval("peak amplitude", self.amplitude)


@dataclass(frozen=True, slots=True, kw_only=True)
class Peaks:
    items: tuple[Peak, ...]

    def __post_init__(self) -> None:
        if len(self.items) > PEAK_COUNT:
            raise InvalidPeaksError(f"at most {PEAK_COUNT} peaks, got {len(self.items)}")
        if any(louder.amplitude < quieter.amplitude for louder, quieter in pairwise(self.items)):
            raise InvalidPeaksError("peaks must be sorted by amplitude, descending")

    @classmethod
    def ranked(cls, candidates: Iterable[Peak]) -> Self:
        strongest = sorted(candidates, key=lambda candidate: candidate.amplitude, reverse=True)
        return cls(items=tuple(strongest[:PEAK_COUNT]))

    @classmethod
    def from_padded_array(cls, padded: Float32Array) -> Self:
        rows = read_only_float32(padded, name="padded peaks", shape=(PEAK_COUNT, PEAK_FIELD_COUNT))
        count = int(np.count_nonzero(rows[:, 0]))
        if np.any(rows[:count, 0] == 0.0) or np.any(rows[count:] != 0.0):
            raise InvalidPeaksError("padding rows must be all zero and follow every peak")
        return cls(
            items=tuple(
                Peak(freq_hz=freq_hz, amplitude=amplitude)
                for freq_hz, amplitude in rows[:count].tolist()
            )
        )

    def as_padded_array(self) -> Float32Array:
        padded = np.zeros((PEAK_COUNT, PEAK_FIELD_COUNT), dtype=np.float32)
        rows = [(peak.freq_hz, peak.amplitude) for peak in self.items]
        padded[: len(rows)] = np.array(rows, dtype=np.float32).reshape(-1, PEAK_FIELD_COUNT)
        return padded
