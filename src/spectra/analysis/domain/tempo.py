import math
from dataclasses import dataclass
from typing import Final

from spectra.analysis.domain.errors import InvalidBeatPositionError, InvalidTempoError
from spectra.analysis.domain.ranges import require_time

BEATS_PER_BAR: Final = 4
MIN_BPM: Final = 20.0
MAX_BPM: Final = 300.0
SECONDS_PER_MINUTE: Final = 60.0


@dataclass(frozen=True, slots=True, kw_only=True)
class BeatPosition:
    bar: int
    beat_in_bar: int
    phase: float

    def __post_init__(self) -> None:
        if self.bar < 0:
            raise InvalidBeatPositionError(f"bar must be >= 0, got {self.bar}")
        if not 0 <= self.beat_in_bar < BEATS_PER_BAR:
            raise InvalidBeatPositionError(
                f"beat_in_bar must be in [0, {BEATS_PER_BAR}), got {self.beat_in_bar}"
            )
        if not 0.0 <= self.phase < 1.0:
            raise InvalidBeatPositionError(f"phase must be in [0, 1), got {self.phase}")


@dataclass(frozen=True, slots=True, kw_only=True)
class Tempo:
    bpm: float

    def __post_init__(self) -> None:
        if not MIN_BPM <= self.bpm <= MAX_BPM:
            raise InvalidTempoError(f"bpm must be in [{MIN_BPM}, {MAX_BPM}], got {self.bpm}")

    @property
    def beat_duration_s(self) -> float:
        return SECONDS_PER_MINUTE / self.bpm

    def beats_at(self, time_s: float) -> float:
        require_time(time_s)
        return time_s / self.beat_duration_s

    def position_at(self, time_s: float) -> BeatPosition:
        beats = self.beats_at(time_s)
        beat_index = math.floor(beats)
        bar, beat_in_bar = divmod(beat_index, BEATS_PER_BAR)
        return BeatPosition(bar=bar, beat_in_bar=beat_in_bar, phase=beats - beat_index)
