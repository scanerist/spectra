import math
from typing import Final

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.analysis.domain.bands import band_levels, fold_to_bands
from spectra.analysis.domain.beat_grid import (
    BeatGrid,
    beat_rises,
    locate_beat_grid,
    strongest_beat,
)
from spectra.analysis.domain.errors import InvalidBeatGridError, InvalidTimeError
from spectra.analysis.domain.onsets import onset_envelope
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.stft import FRAME_RATE_HZ, stft_chunks
from spectra.analysis.domain.tempo import BEATS_PER_BAR, MAX_BPM, MIN_BPM, BeatPosition, Tempo
from tests.signals import Accent, kick_train, signal_of

BEAT_128_S: Final = 60.0 / 128.0
BAR_128_S: Final = 4 * BEAT_128_S
GRID_TOLERANCE_S: Final = 0.01


def grid_120(offset_s: float = 0.5) -> BeatGrid:
    return BeatGrid(tempo=Tempo(bpm=120.0), offset_s=offset_s)


def located(samples: Float32Array) -> BeatGrid:
    power = fold_to_bands(stft_chunks(signal_of(samples)))
    return locate_beat_grid(
        onset_envelope(power),
        band_levels(power),
        tempo=Tempo(bpm=128.0),
        frame_rate_hz=FRAME_RATE_HZ,
    )


@pytest.mark.parametrize(
    "offset_s", [-0.01, 2.0, math.nan, math.inf], ids=["negative", "one-bar", "nan", "inf"]
)
def test_grid_rejects_offset_outside_the_first_bar(offset_s: float) -> None:
    with pytest.raises(InvalidBeatGridError):
        grid_120(offset_s)


def test_bar_duration_at_120_bpm_is_two_seconds() -> None:
    assert grid_120().bar_duration_s == 2.0


def test_bar_starts_step_by_bar_duration_from_the_offset() -> None:
    assert [grid_120().bar_start_s(bar) for bar in range(3)] == [0.5, 2.5, 4.5]


@pytest.mark.parametrize(
    ("duration_s", "bars"),
    [(10.0, 5), (10.5, 5), (10.6, 6), (0.2, 1)],
    ids=["partial-last-bar", "exact", "just-over", "shorter-than-offset"],
)
def test_bar_count_covers_the_track_from_the_offset(duration_s: float, bars: int) -> None:
    assert grid_120().bar_count(duration_s) == bars


def test_position_at_the_offset_is_the_first_downbeat() -> None:
    assert grid_120().position_at(0.5) == BeatPosition(bar=0, beat_in_bar=0, phase=0.0)


def test_before_the_offset_the_bar_clamps_and_beats_count_backwards() -> None:
    assert grid_120().position_at(0.375) == BeatPosition(bar=0, beat_in_bar=3, phase=0.75)


def test_position_rejects_negative_time() -> None:
    with pytest.raises(InvalidTimeError):
        grid_120().position_at(-0.1)


GRIDS: Final = st.builds(
    lambda bpm, fraction: BeatGrid(
        tempo=Tempo(bpm=bpm), offset_s=fraction * BEATS_PER_BAR * 60.0 / bpm
    ),
    st.floats(min_value=MIN_BPM, max_value=MAX_BPM),
    st.floats(min_value=0.0, max_value=0.999),
)


@given(grid=GRIDS, time_s=st.floats(min_value=0.0, max_value=1e5))
def test_position_invariants_hold_for_any_grid_and_time(grid: BeatGrid, time_s: float) -> None:
    position = grid.position_at(time_s)
    assert position.bar >= 0
    assert 0 <= position.beat_in_bar < BEATS_PER_BAR
    assert 0.0 <= position.phase < 1.0


@given(grid=GRIDS, after_s=st.floats(min_value=0.0, max_value=1e5))
def test_position_after_the_offset_reconstructs_the_time(grid: BeatGrid, after_s: float) -> None:
    time_s = grid.offset_s + after_s
    position = grid.position_at(time_s)
    beats = position.bar * BEATS_PER_BAR + position.beat_in_bar + position.phase
    assert grid.offset_s + beats * grid.tempo.beat_duration_s == pytest.approx(
        time_s, rel=1e-9, abs=1e-6
    )


def test_bars_at_clamps_to_the_first_and_last_bar() -> None:
    times_s = np.array([0.0, 0.5, 2.49, 2.5, 99.0])
    np.testing.assert_array_equal(grid_120().bars_at(times_s, bar_count=5), [0, 0, 0, 1, 4])


def test_located_grid_puts_the_downbeat_on_the_accented_kick() -> None:
    samples = kick_train(128.0, 30.0, offset_s=0.4, accent=Accent(every=4, first=1))
    grid = located(samples)
    assert grid.offset_s == pytest.approx(0.4 + BEAT_128_S, abs=GRID_TOLERANCE_S)


def test_located_grid_wraps_a_late_downbeat_into_the_first_bar() -> None:
    samples = kick_train(128.0, 30.0, offset_s=0.4, accent=Accent(every=4, first=3))
    grid = located(samples)
    assert grid.offset_s == pytest.approx(0.4 + 3 * BEAT_128_S, abs=GRID_TOLERANCE_S)


def test_beat_rises_count_only_increases_from_the_previous_beat() -> None:
    levels = np.zeros((100, 2), dtype=np.float32)
    levels[20:30] = 1.0
    rises = beat_rises(levels, first_beat_frames=0.0, period_frames=10.0)
    np.testing.assert_allclose(rises, [0, 0, 2, 0, 0, 0, 0, 0, 0, 0])


def test_strongest_beat_follows_the_biggest_rises() -> None:
    rises = np.zeros(32)
    rises[2::4] = 1.0
    assert strongest_beat(rises) == 2


def test_located_grid_lands_on_a_kick_without_accents() -> None:
    grid = located(kick_train(128.0, 30.0, offset_s=0.4))
    beat_offset_s = grid.offset_s % BEAT_128_S
    assert beat_offset_s == pytest.approx(0.4, abs=GRID_TOLERANCE_S)
    assert grid.offset_s < BAR_128_S
