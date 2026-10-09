from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.bands import interpolation_weights
from spectra.analysis.domain.beat_grid import BeatGrid
from spectra.analysis.domain.peaks import Peak, Peaks
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.signal import AudioSignal
from spectra.analysis.domain.stft import StftShape, stft_chunks

FOURIER_BIN_COUNT: Final = 200
FOURIER_MIN_FREQ_HZ: Final = 30.0
FOURIER_MAX_FREQ_HZ: Final = 600.0
BAR_STFT: Final = StftShape(window_samples=16_384, hop_samples=8_192)
BAR_STFT_CHUNK_FRAMES: Final = 64
PEAK_RELATIVE_FLOOR: Final = 0.2
PEAK_ABSOLUTE_FLOOR: Final = 1e-3


def fourier_bin_centers_hz() -> NDArray[np.float64]:
    return np.geomspace(FOURIER_MIN_FREQ_HZ, FOURIER_MAX_FREQ_HZ, FOURIER_BIN_COUNT)


def bar_spectra(signal: AudioSignal, *, grid: BeatGrid, bar_count: int) -> Float32Array:
    freqs_hz = BAR_STFT.bin_freqs_hz()
    bin_limit = int(np.searchsorted(freqs_hz, FOURIER_MAX_FREQ_HZ)) + 2
    weights = interpolation_weights(fourier_bin_centers_hz(), freqs_hz[:bin_limit])
    projection = weights.T.astype(np.float32)
    sums = np.zeros((bar_count, FOURIER_BIN_COUNT))
    counts = np.zeros(bar_count)
    first_frame = 0
    for chunk in stft_chunks(
        signal, shape=BAR_STFT, chunk_frames=BAR_STFT_CHUNK_FRAMES, bin_limit=bin_limit
    ):
        times_s = BAR_STFT.frame_times_s(first_frame + chunk.shape[0])[first_frame:]
        bars = grid.bars_at(times_s, bar_count=bar_count)
        np.add.at(sums, bars, chunk @ projection)
        np.add.at(counts, bars, 1.0)
        first_frame += chunk.shape[0]
    means = sums / np.maximum(counts, 1.0)[:, np.newaxis]
    loudest = float(means.max())
    return np.asarray(means / loudest if loudest > 0.0 else means, dtype=np.float32)


def bar_peaks(spectrum: Float32Array) -> Peaks:
    loudest = float(spectrum.max())
    if loudest <= PEAK_ABSOLUTE_FLOOR:
        return Peaks(items=())
    inner = np.arange(1, spectrum.size - 1)
    centre = spectrum[inner]
    is_peak = (
        (centre > spectrum[inner - 1])
        & (centre >= spectrum[inner + 1])
        & (centre >= PEAK_RELATIVE_FLOOR * loudest)
    )
    return Peaks.ranked(refined_peak(spectrum, int(index)) for index in inner[is_peak])


def refined_peak(spectrum: Float32Array, index: int) -> Peak:
    left, centre, right = (float(value) for value in spectrum[index - 1 : index + 2])
    curvature = left - 2.0 * centre + right
    shift = 0.5 * (left - right) / curvature if curvature < 0.0 else 0.0
    shift = min(max(shift, -0.5), 0.5)
    position = index + shift
    ratio = FOURIER_MAX_FREQ_HZ / FOURIER_MIN_FREQ_HZ
    freq_hz = FOURIER_MIN_FREQ_HZ * ratio ** (position / (FOURIER_BIN_COUNT - 1))
    amplitude = centre - 0.25 * (left - right) * shift
    return Peak(freq_hz=freq_hz, amplitude=min(max(amplitude, 0.0), 1.0))
