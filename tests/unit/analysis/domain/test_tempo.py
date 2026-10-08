import math
from typing import Final

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.analysis.domain.errors import (
    InvalidBeatPositionError,
    InvalidTempoError,
    InvalidTimeError,
)
from spectra.analysis.domain.tempo import BEATS_PER_BAR, MAX_BPM, MIN_BPM, BeatPosition, Tempo

BPMS: Final = st.floats(min_value=MIN_BPM, max_value=MAX_BPM)
TIMES_S: Final = st.floats(min_value=0.0, max_value=1e6)


def test_beat_duration_at_120_bpm_is_half_second() -> None:
    assert Tempo(bpm=120.0).beat_duration_s == 0.5


@pytest.mark.parametrize(
    "bpm",
    [MIN_BPM - 1.0, MAX_BPM + 1.0, 0.0, -128.0, math.nan, math.inf],
    ids=["below-min", "above-max", "zero", "negative", "nan", "inf"],
)
def test_tempo_rejects_bpm_outside_range(bpm: float) -> None:
    with pytest.raises(InvalidTempoError):
        Tempo(bpm=bpm)


def test_position_at_start_is_bar_zero_beat_zero() -> None:
    assert Tempo(bpm=128.0).position_at(0.0) == BeatPosition(bar=0, beat_in_bar=0, phase=0.0)


def test_position_after_five_and_a_quarter_beats_is_bar_one_beat_one() -> None:
    position = Tempo(bpm=120.0).position_at(2.625)
    assert position == BeatPosition(bar=1, beat_in_bar=1, phase=0.25)


def test_beats_at_counts_fractional_beats() -> None:
    assert Tempo(bpm=120.0).beats_at(1.25) == 2.5


@pytest.mark.parametrize(
    "time_s",
    [-0.001, -math.inf, math.nan, math.inf],
    ids=["negative", "minus-inf", "nan", "inf"],
)
def test_position_rejects_invalid_time(time_s: float) -> None:
    with pytest.raises(InvalidTimeError):
        Tempo(bpm=128.0).position_at(time_s)


@given(bpm=BPMS, time_s=TIMES_S)
def test_position_invariants_hold_for_any_time_and_tempo(bpm: float, time_s: float) -> None:
    position = Tempo(bpm=bpm).position_at(time_s)
    assert position.bar >= 0
    assert 0 <= position.beat_in_bar < BEATS_PER_BAR
    assert 0.0 <= position.phase < 1.0


@given(bpm=BPMS, time_s=TIMES_S)
def test_position_reconstructs_elapsed_beats(bpm: float, time_s: float) -> None:
    tempo = Tempo(bpm=bpm)
    position = tempo.position_at(time_s)
    whole_beats = position.bar * BEATS_PER_BAR + position.beat_in_bar
    elapsed_s = (whole_beats + position.phase) * tempo.beat_duration_s
    assert elapsed_s == pytest.approx(time_s, rel=1e-9, abs=1e-9)


@pytest.mark.parametrize(
    ("bar", "beat_in_bar", "phase"),
    [
        (-1, 0, 0.0),
        (0, -1, 0.0),
        (0, BEATS_PER_BAR, 0.0),
        (0, 0, -0.1),
        (0, 0, 1.0),
        (0, 0, math.nan),
    ],
    ids=["negative-bar", "negative-beat", "beat-past-bar", "negative-phase", "phase-one", "nan"],
)
def test_beat_position_rejects_invalid(bar: int, beat_in_bar: int, phase: float) -> None:
    with pytest.raises(InvalidBeatPositionError):
        BeatPosition(bar=bar, beat_in_bar=beat_in_bar, phase=phase)
