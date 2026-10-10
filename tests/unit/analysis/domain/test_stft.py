import numpy as np
import pytest

from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ, AudioSignal
from spectra.analysis.domain.stft import (
    FRAME_RATE_HZ,
    HOP_SAMPLES,
    TIMELINE_STFT,
    WINDOW_SAMPLES,
    StftShape,
    bin_freqs_hz,
    frame_count,
    stft_chunks,
)
from tests.signals import impulse_at, noise, signal_of, sine, whole_stft

BIN_WIDTH_HZ = ANALYSIS_SAMPLE_RATE_HZ / WINDOW_SAMPLES


def test_frame_rate_is_sample_rate_over_hop() -> None:
    assert FRAME_RATE_HZ == 44_100 / 512 == 86.1328125


@pytest.mark.parametrize(
    ("sample_count", "frames"),
    [(1, 1), (HOP_SAMPLES, 1), (HOP_SAMPLES + 1, 2), (ANALYSIS_SAMPLE_RATE_HZ, 87)],
    ids=["one-sample", "one-hop", "hop-plus-one", "one-second"],
)
def test_frame_count_covers_every_sample(sample_count: int, frames: int) -> None:
    assert frame_count(sample_count) == frames


def test_magnitudes_have_one_float32_row_per_frame() -> None:
    signal = signal_of(sine(440.0, 1.0))
    magnitudes = whole_stft(signal)
    assert magnitudes.dtype == np.float32
    assert magnitudes.shape == (frame_count(signal.sample_count), bin_freqs_hz().size)


def test_one_khz_sine_peaks_at_one_khz() -> None:
    magnitudes = whole_stft(signal_of(sine(1_000.0, 1.0)))
    peak_hz = bin_freqs_hz()[np.argmax(magnitudes[10:-10].mean(axis=0))]
    assert abs(peak_hz - 1_000.0) <= BIN_WIDTH_HZ / 2


def test_bin_centred_sine_magnitude_equals_its_amplitude() -> None:
    freq_hz = 46 * BIN_WIDTH_HZ
    magnitudes = whole_stft(signal_of(sine(freq_hz, 1.0, amplitude=0.5)))
    assert magnitudes[40, 46] == pytest.approx(0.5, rel=1e-3)


def test_impulse_lands_in_the_frame_centred_on_it() -> None:
    magnitudes = whole_stft(signal_of(impulse_at(0.5, 1.0)))
    assert int(np.argmax(magnitudes.sum(axis=1))) == round(0.5 * FRAME_RATE_HZ)


def test_chunks_concatenate_to_the_whole_transform() -> None:
    signal = signal_of(noise(0.5))
    chunked = np.concatenate(list(stft_chunks(signal, chunk_frames=7)))
    np.testing.assert_array_equal(chunked, whole_stft(signal))


def test_silence_has_zero_magnitude() -> None:
    magnitudes = whole_stft(AudioSignal(samples=np.zeros(4_096, dtype=np.float32)))
    assert not magnitudes.any()


def test_longer_window_resolves_finer_frequencies() -> None:
    shape = StftShape(window_samples=16_384, hop_samples=8_192)
    magnitudes = np.concatenate(list(stft_chunks(signal_of(sine(55.0, 2.0)), shape=shape)))
    peak_hz = shape.bin_freqs_hz()[np.argmax(magnitudes[1:-1].mean(axis=0))]
    assert abs(peak_hz - 55.0) <= ANALYSIS_SAMPLE_RATE_HZ / 16_384 / 2


def test_bin_limit_keeps_only_the_lowest_bins() -> None:
    signal = signal_of(noise(0.5))
    limited = np.concatenate(list(stft_chunks(signal, bin_limit=100)))
    np.testing.assert_array_equal(limited, whole_stft(signal)[:, :100])


def test_frame_times_step_by_the_hop() -> None:
    times_s = TIMELINE_STFT.frame_times_s(3)
    np.testing.assert_allclose(times_s, [0.0, 512 / 44_100, 1_024 / 44_100])
