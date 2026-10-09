import math
from collections.abc import Iterator
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True, kw_only=True)
class StftShape:
    window_samples: int
    hop_samples: int

    def frame_count(self, sample_count: int) -> int:
        return max(1, math.ceil(sample_count / self.hop_samples))

    def bin_freqs_hz(self) -> NDArray[np.float64]:
        return np.fft.rfftfreq(self.window_samples, d=1.0 / ANALYSIS_SAMPLE_RATE_HZ)

    def frame_times_s(self, frame_count: int) -> NDArray[np.float64]:
        return np.arange(frame_count) * self.hop_samples / ANALYSIS_SAMPLE_RATE_HZ


TIMELINE_STFT: Final = StftShape(window_samples=WINDOW_SAMPLES, hop_samples=HOP_SAMPLES)


def frame_count(sample_count: int) -> int:
    return TIMELINE_STFT.frame_count(sample_count)


def bin_freqs_hz() -> NDArray[np.float64]:
    return TIMELINE_STFT.bin_freqs_hz()


def hann_window(length: int) -> NDArray[np.float64]:
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(length) / length)


def stft_chunks(
    signal: AudioSignal,
    *,
    shape: StftShape = TIMELINE_STFT,
    chunk_frames: int = CHUNK_FRAMES,
    bin_limit: int | None = None,
) -> Iterator[Float32Array]:
    total = shape.frame_count(signal.sample_count)
    padded = centred(signal.samples, total, shape=shape)
    windows = np.lib.stride_tricks.sliding_window_view(padded, shape.window_samples)
    window = hann_window(shape.window_samples)
    taper = (window * (2.0 / window.sum())).astype(np.float32)
    for start in range(0, total, chunk_frames):
        stop = min(start + chunk_frames, total)
        frames = windows[start * shape.hop_samples : stop * shape.hop_samples : shape.hop_samples]
        spectrum = np.fft.rfft(frames * taper, axis=1)[:, :bin_limit]
        yield np.abs(spectrum).astype(np.float32)


def stft_magnitudes(signal: AudioSignal) -> Float32Array:
    return np.concatenate(list(stft_chunks(signal)))


def centred(samples: Float32Array, total_frames: int, *, shape: StftShape) -> Float32Array:
    lead = shape.window_samples // 2
    tail = (total_frames - 1) * shape.hop_samples + shape.window_samples - lead - samples.size
    return np.concatenate(
        [np.zeros(lead, dtype=np.float32), samples, np.zeros(tail, dtype=np.float32)]
    )
