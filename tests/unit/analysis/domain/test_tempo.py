import math

import pytest

from spectra.analysis.domain.errors import InvalidBeatPositionError, InvalidTempoError
from spectra.analysis.domain.tempo import BEATS_PER_BAR, MAX_BPM, MIN_BPM, BeatPosition, Tempo


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
