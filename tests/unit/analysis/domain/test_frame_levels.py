from typing import Final

import numpy as np
import pytest

from spectra.analysis.domain.bands import band_levels, fold_to_bands
from spectra.analysis.domain.frame_levels import LEVEL_COLUMNS, LEVEL_COUNT, frame_levels
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.stft import FRAME_RATE_HZ, stft_chunks
from tests.signals import kick_train, signal_of, silence, sine

KICK: Final = LEVEL_COLUMNS.index("kick")
BASS: Final = LEVEL_COLUMNS.index("bass")
MID: Final = LEVEL_COLUMNS.index("mid")
HIGH: Final = LEVEL_COLUMNS.index("high")
ENERGY: Final = LEVEL_COLUMNS.index("energy")


def levels_of(samples: Float32Array) -> Float32Array:
    power = fold_to_bands(stft_chunks(signal_of(samples)))
    return frame_levels(power, band_levels(power))


def test_columns_are_kick_bass_mid_high_energy() -> None:
    assert LEVEL_COLUMNS == ("kick", "bass", "mid", "high", "energy")


def test_levels_are_float32_unit_interval_with_five_columns() -> None:
    levels = levels_of(kick_train(128.0, 3.0))
    assert levels.dtype == np.float32
    assert levels.shape[1] == LEVEL_COUNT
    assert levels.min() >= 0.0
    assert levels.max() <= 1.0


def test_kick_level_strikes_on_every_kick_and_fades_before_the_next() -> None:
    levels = levels_of(kick_train(120.0, 4.0, offset_s=0.25))
    for beat in range(7):
        frame = round((0.25 + 0.5 * beat) * FRAME_RATE_HZ)
        assert levels[frame, KICK] > 0.7
        assert levels[frame + round(0.45 * FRAME_RATE_HZ), KICK] < 0.3


@pytest.mark.parametrize(
    ("freq_hz", "loud", "quiet"),
    [(80.0, BASS, HIGH), (1_000.0, MID, BASS), (8_000.0, HIGH, BASS)],
    ids=["bass", "mid", "high"],
)
def test_tone_lights_its_own_range_only(freq_hz: float, loud: int, quiet: int) -> None:
    levels = levels_of(sine(freq_hz, 2.0))[60:-60]
    assert levels[:, loud].min() > 0.9
    assert levels[:, quiet].max() < 0.1


def test_energy_rises_when_the_track_gets_louder() -> None:
    quiet = sine(1_000.0, 8.0, amplitude=0.05)
    loud = sine(1_000.0, 8.0)
    levels = levels_of(np.concatenate([quiet, loud]))
    half = levels.shape[0] // 2
    assert levels[half + 100 :, ENERGY].mean() > levels[: half - 100, ENERGY].mean() + 0.2


def test_silence_has_zero_levels() -> None:
    assert not levels_of(silence(2.0)).any()
