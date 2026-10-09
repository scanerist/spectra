import math

import numpy as np
import pytest

from spectra.analysis.domain.bands import fold_to_bands
from spectra.analysis.domain.errors import TempoNotFoundError
from spectra.analysis.domain.onsets import onset_envelope, upper_onset_envelope
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.stft import FRAME_RATE_HZ, stft_chunks
from spectra.analysis.domain.tempo_estimation import (
    estimate_tempo,
    fit_grid,
    period_frames,
    tempo_prior,
)
from tests.signals import Accent, kick_train, noise, signal_of, silence

TOLERANCE_BPM = 0.5


def tempo_of(samples: Float32Array) -> float:
    power = fold_to_bands(stft_chunks(signal_of(samples)))
    return estimate_tempo(
        onset_envelope(power),
        upper_envelope=upper_onset_envelope(power),
        frame_rate_hz=FRAME_RATE_HZ,
    ).bpm


@pytest.mark.parametrize("bpm", [90.0, 122.0, 128.0, 140.0, 174.0], ids=lambda b: f"{b:g}")
def test_click_train_estimates_its_tempo(bpm: float) -> None:
    assert tempo_of(kick_train(bpm, 30.0)) == pytest.approx(bpm, abs=TOLERANCE_BPM)


def test_click_train_at_128_bpm_beats_its_half_and_double() -> None:
    estimate = tempo_of(kick_train(128.0, 30.0, offset_s=0.37))
    assert estimate == pytest.approx(128.0, abs=TOLERANCE_BPM)
    assert abs(estimate - 64.0) > 10.0
    assert abs(estimate - 256.0) > 10.0


def test_accented_downbeats_do_not_halve_the_tempo() -> None:
    samples = kick_train(128.0, 30.0, accent=Accent(every=4, gain=2.0))
    assert tempo_of(samples) == pytest.approx(128.0, abs=TOLERANCE_BPM)


def test_offbeat_hats_do_not_double_the_tempo() -> None:
    beat_s = 60.0 / 128.0
    hats = np.zeros(round(30.0 * 44_100), dtype=np.float32)
    burst = noise(0.03, amplitude=0.3)
    for beat in range(63):
        start = round((beat + 0.5) * beat_s * 44_100)
        hats[start : start + burst.size] += burst
    hats = hats - np.convolve(hats, np.ones(8) / 8, mode="same").astype(np.float32)
    samples = kick_train(128.0, 30.0) + hats
    assert tempo_of(samples) == pytest.approx(128.0, abs=TOLERANCE_BPM)


def test_half_time_drums_with_hats_on_every_beat_keep_the_full_tempo() -> None:
    bpm = 145.0
    beat_s = 60.0 / bpm
    duration_s = 30.0
    kicks = kick_train(bpm / 4.0, duration_s)
    snares = silence(duration_s)
    hats = silence(duration_s)
    snare = noise(0.12, amplitude=0.4, seed=1) * np.exp(-np.arange(5_292) / 1_500).astype(
        np.float32
    )
    hat = np.diff(noise(0.03, amplitude=0.25, seed=2), prepend=np.float32(0.0))
    for beat in range(math.floor(duration_s / beat_s)):
        start = round(beat * beat_s * 44_100)
        if beat % 4 == 2:
            snares[start : start + snare.size] += snare[: snares.size - start]
        hats[start : start + hat.size] += hat[: hats.size - start]
    assert tempo_of(kicks + snares + hats) == pytest.approx(bpm, abs=TOLERANCE_BPM)


def test_leading_silence_does_not_change_the_tempo() -> None:
    samples = np.concatenate([silence(5.0), kick_train(128.0, 25.0)])
    assert tempo_of(samples) == pytest.approx(128.0, abs=TOLERANCE_BPM)


def test_silence_has_no_tempo() -> None:
    with pytest.raises(TempoNotFoundError):
        tempo_of(silence(10.0))


def test_prior_peaks_at_120_and_falls_by_octave() -> None:
    assert tempo_prior(120.0) == 1.0
    assert tempo_prior(60.0) == pytest.approx(tempo_prior(240.0))
    assert tempo_prior(60.0) < tempo_prior(90.0) < tempo_prior(120.0)


def test_grid_fit_finds_the_phase_of_a_pulse_train() -> None:
    pulses = np.zeros(1_000)
    pulses[13::40] = 1.0
    fit = fit_grid(pulses, period_frames=40.0)
    assert fit.phase_frames == pytest.approx(13.0, abs=0.25)
    assert fit.salience == pytest.approx(1.0)


def test_period_of_120_bpm_at_100_frames_per_second_is_50_frames() -> None:
    assert period_frames(120.0, 100.0) == 50.0


@pytest.mark.parametrize("bpm", [124.0, 145.0], ids=lambda b: f"{b:g}")
def test_seven_minute_track_tempo_is_exact_enough_not_to_drift(bpm: float) -> None:
    assert tempo_of(kick_train(bpm, 420.0)) == pytest.approx(bpm, abs=0.002)
