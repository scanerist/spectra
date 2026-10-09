import math
from collections.abc import Iterator
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ, AudioSignal

WINDOW_SAMPLES: Final = 2048
HOP_SAMPLES: Final = 512
FRAME_RATE_HZ: Final = ANALYSIS_SAMPLE_RATE_HZ / HOP_SAMPLES
BIN_COUNT: Final = WINDOW_SAMPLES // 2 + 1
CHUNK_FRAMES: Final = 1024


def frame_count(sample_count: int) -> int:
    return max(1, math.ceil(sample_count / HOP_SAMPLES))


def bin_freqs_hz() -> NDArray[np.float64]:
    return np.fft.rfftfreq(WINDOW_SAMPLES, d=1.0 / ANALYSIS_SAMPLE_RATE_HZ)


def hann_window(length: int) -> NDArray[np.float64]:
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(length) / length)


def stft_chunks(signal: AudioSignal, *, chunk_frames: int = CHUNK_FRAMES) -> Iterator[Float32Array]:
    total = frame_count(signal.sample_count)
    padded = centred(signal.samples, total)
    windows = np.lib.stride_tricks.sliding_window_view(padded, WINDOW_SAMPLES)[::HOP_SAMPLES]
    window = hann_window(WINDOW_SAMPLES)
    taper = (window * (2.0 / window.sum())).astype(np.float32)
    for start in range(0, total, chunk_frames):
        frames = windows[start : min(start + chunk_frames, total)] * taper
        yield np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)


def stft_magnitudes(signal: AudioSignal) -> Float32Array:
    return np.concatenate(list(stft_chunks(signal)))


def centred(samples: Float32Array, total_frames: int) -> Float32Array:
    lead = WINDOW_SAMPLES // 2
    tail = (total_frames - 1) * HOP_SAMPLES + WINDOW_SAMPLES - lead - samples.size
    return np.concatenate(
        [np.zeros(lead, dtype=np.float32), samples, np.zeros(tail, dtype=np.float32)]
    )
