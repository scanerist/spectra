import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.errors import InvalidBeatGridError
from spectra.analysis.domain.ranges import Float32Array, require_time
from spectra.analysis.domain.tempo import BEATS_PER_BAR, BeatPosition, Tempo
from spectra.analysis.domain.tempo_estimation import detrended, fit_grid, period_frames

DOWNBEAT_CANDIDATES: Final = BEATS_PER_BAR
TOP_FRACTION_DIVISOR: Final = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class BeatGrid:
    tempo: Tempo
    offset_s: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.offset_s) and 0.0 <= self.offset_s < self.bar_duration_s):
            raise InvalidBeatGridError(
                f"offset_s must be in [0, {self.bar_duration_s}), got {self.offset_s}"
            )

    @property
    def bar_duration_s(self) -> float:
        return BEATS_PER_BAR * self.tempo.beat_duration_s

    def bar_start_s(self, bar: int) -> float:
        return self.offset_s + bar * self.bar_duration_s

    def bar_count(self, duration_s: float) -> int:
        return max(1, math.ceil((duration_s - self.offset_s) / self.bar_duration_s))

    def position_at(self, time_s: float) -> BeatPosition:
        require_time(time_s)
        beats = (time_s - self.offset_s) / self.tempo.beat_duration_s
        index = math.floor(beats)
        phase = beats - index
        if phase >= 1.0:
            index, phase = index + 1, 0.0
        return BeatPosition(
            bar=max(0, index // BEATS_PER_BAR),
            beat_in_bar=index % BEATS_PER_BAR,
            phase=phase,
        )

    def bars_at(self, times_s: NDArray[np.float64], *, bar_count: int) -> NDArray[np.int64]:
        bars = np.floor((times_s - self.offset_s) / self.bar_duration_s)
        return np.clip(bars, 0, bar_count - 1).astype(np.int64)


def locate_beat_grid(
    pulses: Float32Array, band_levels: Float32Array, *, tempo: Tempo, frame_rate_hz: float
) -> BeatGrid:
    period = period_frames(tempo.bpm, frame_rate_hz)
    first_beat = fit_grid(detrended(pulses, frame_rate_hz=frame_rate_hz), period_frames=period)
    rises = beat_rises(band_levels, first_beat_frames=first_beat.phase_frames, period_frames=period)
    downbeat = first_beat.phase_frames + period * strongest_beat(rises)
    bar_duration_s = BEATS_PER_BAR * tempo.beat_duration_s
    offset_s = (downbeat / frame_rate_hz) % bar_duration_s
    return BeatGrid(tempo=tempo, offset_s=offset_s if offset_s < bar_duration_s else 0.0)


def beat_rises(
    band_levels: Float32Array, *, first_beat_frames: float, period_frames: float
) -> NDArray[np.float64]:
    frame_total = band_levels.shape[0]
    beat_total = math.floor((frame_total - first_beat_frames) / period_frames)
    if beat_total < 1:
        return np.zeros(0)
    starts = np.ceil(first_beat_frames + period_frames * np.arange(beat_total)).astype(np.int64)
    sums = np.add.reduceat(band_levels.astype(np.float64), starts, axis=0)
    lengths = np.diff(np.append(starts, frame_total)).astype(np.float64)
    beat_levels = sums / lengths[:, np.newaxis]
    rises = np.maximum(np.diff(beat_levels, axis=0), 0.0).sum(axis=1)
    return np.concatenate([[0.0], rises])


def strongest_beat(rises: NDArray[np.float64]) -> int:
    scores = [
        top_quarter_mean(rises[beat::DOWNBEAT_CANDIDATES]) for beat in range(DOWNBEAT_CANDIDATES)
    ]
    return int(np.argmax(scores))


def top_quarter_mean(values: NDArray[np.float64]) -> float:
    if values.size == 0:
        return 0.0
    count = max(1, values.size // TOP_FRACTION_DIVISOR)
    return float(np.sort(values)[-count:].mean())
