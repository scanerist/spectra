from dataclasses import dataclass
from typing import Final

import numpy as np

from spectra.analysis.domain.errors import InvalidSignalError
from spectra.analysis.domain.ranges import Float32Array

ANALYSIS_SAMPLE_RATE_HZ: Final = 44_100


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class AudioSignal:
    samples: Float32Array

    def __post_init__(self) -> None:
        samples = np.asarray(self.samples, dtype=np.float32)
        if samples.ndim != 1 or samples.size == 0:
            raise InvalidSignalError(
                f"signal must be a non-empty mono array, got shape {samples.shape}"
            )
        if not np.all(np.isfinite(samples)):
            raise InvalidSignalError("signal samples must be finite")
        if samples.flags.writeable:
            samples = samples.copy()
            samples.flags.writeable = False
        object.__setattr__(self, "samples", samples)

    @property
    def sample_count(self) -> int:
        return int(self.samples.size)

    @property
    def duration_s(self) -> float:
        return self.sample_count / ANALYSIS_SAMPLE_RATE_HZ
