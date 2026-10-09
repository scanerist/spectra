from typing import Final

import numpy as np
import pytest

from spectra.analysis.domain.bands import fold_to_bands
from spectra.analysis.domain.onsets import onset_envelope
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.stft import FRAME_RATE_HZ, stft_chunks
from tests.signals import kick_train, signal_of, silence, sine

KICK_TIMES_S: Final = [0.25 + 0.5 * beat for beat in range(7)]


def envelope_of(samples: Float32Array) -> Float32Array:
    return onset_envelope(fold_to_bands(stft_chunks(signal_of(samples))))


@pytest.fixture
def kicks() -> Float32Array:
    return envelope_of(kick_train(120.0, 4.0, offset_s=0.25))


@pytest.mark.parametrize("kick_s", KICK_TIMES_S, ids=lambda t: f"{t}s")
def test_click_train_gives_an_onset_peak_at_every_kick(kicks: Float32Array, kick_s: float) -> None:
    frame = round(kick_s * FRAME_RATE_HZ)
    window = kicks[frame - 4 : frame + 5]
    assert frame - 4 + int(np.argmax(window)) == frame
    assert window.max() > 0.5


def test_envelope_is_quiet_between_kicks(kicks: Float32Array) -> None:
    between = kicks[round(0.4 * FRAME_RATE_HZ) : round(0.65 * FRAME_RATE_HZ)]
    assert between.max() < 0.1


def test_envelope_is_float32_normalised_to_a_unit_peak(kicks: Float32Array) -> None:
    assert kicks.dtype == np.float32
    assert kicks.max() == pytest.approx(1.0)
    assert kicks.min() >= 0.0


def test_steady_tone_has_no_onsets_between_its_start_and_end() -> None:
    envelope = envelope_of(np.concatenate([kick_train(120.0, 0.5), sine(80.0, 2.0)]))
    steady = envelope[round(0.8 * FRAME_RATE_HZ) : -round(0.3 * FRAME_RATE_HZ)]
    assert steady.max() < 0.05


def test_silence_has_a_flat_zero_envelope() -> None:
    assert not envelope_of(silence(1.0)).any()
