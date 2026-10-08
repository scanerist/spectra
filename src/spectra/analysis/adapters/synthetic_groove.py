import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import Peak, Peaks
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.spectrum import BAND_COUNT, Spectrum, band_centers_hz
from spectra.analysis.domain.tempo import BEATS_PER_BAR, Tempo
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform
from spectra.shared.clock import Clock

KICK_DECAY_S: Final = 0.12
HAT_DECAY_S: Final = 0.04
OFFBEAT_PHASE: Final = 0.5
ENERGY_CYCLE_BARS: Final = 32
SIDECHAIN_DEPTH: Final = 0.8
WAVEFORM_WINDOW_S: Final = 0.030
TONAL_CEILING_HZ: Final = 4_000.0
SPECTRUM_NOISE_CEILING: Final = 0.03
WAVEFORM_NOISE_STD: Final = 0.3
PEAK_ROLLOFF_PER_RANK: Final = 0.05
TAU: Final = 2.0 * math.pi

type LevelOf = Callable[[Levels], float]


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectralVoice:
    center_hz: float
    width_octaves: float
    gain: float
    level: LevelOf


@dataclass(frozen=True, slots=True, kw_only=True)
class PeakVoice:
    freq_hz: float
    level: LevelOf


def kick_of(levels: Levels) -> float:
    return levels.kick


def bass_of(levels: Levels) -> float:
    return levels.bass


def mid_of(levels: Levels) -> float:
    return levels.mid


def high_of(levels: Levels) -> float:
    return levels.high


SPECTRAL_VOICES: Final = (
    SpectralVoice(center_hz=55.0, width_octaves=0.5, gain=1.0, level=kick_of),
    SpectralVoice(center_hz=110.0, width_octaves=0.7, gain=0.8, level=bass_of),
    SpectralVoice(center_hz=1_000.0, width_octaves=1.5, gain=0.5, level=mid_of),
    SpectralVoice(center_hz=8_000.0, width_octaves=0.8, gain=0.6, level=high_of),
)

PEAK_VOICES: Final = (
    PeakVoice(freq_hz=55.0, level=kick_of),
    PeakVoice(freq_hz=110.0, level=bass_of),
    PeakVoice(freq_hz=165.0, level=bass_of),
    PeakVoice(freq_hz=440.0, level=mid_of),
    PeakVoice(freq_hz=1_000.0, level=mid_of),
    PeakVoice(freq_hz=3_200.0, level=mid_of),
    PeakVoice(freq_hz=8_000.0, level=high_of),
    PeakVoice(freq_hz=12_000.0, level=high_of),
)


class SyntheticGroove:
    def __init__(self, *, clock: Clock, tempo: Tempo, seed: int) -> None:
        self._clock = clock
        self._tempo = tempo
        self._origin_s = clock.now_s()
        self._rng = np.random.default_rng(seed)
        log2_centers = np.log2(band_centers_hz())
        self._voice_shapes = [spectral_shape(log2_centers, voice) for voice in SPECTRAL_VOICES]
        self._waveform_times_s = np.linspace(
            0.0, WAVEFORM_WINDOW_S, WAVEFORM_LENGTH, endpoint=False
        )

    def latest(self) -> FeatureFrame:
        time_s = self._clock.now_s() - self._origin_s
        position = self._tempo.position_at(time_s)
        energy = self._energy_at(self._tempo.beats_at(time_s))
        levels = self._levels_at(position.phase, energy)
        peaks = self._peaks_at(levels, time_s)
        return FeatureFrame(
            time_s=time_s,
            spectrum=self._spectrum_of(levels),
            waveform=self._waveform_of(peaks, levels.high),
            peaks=peaks,
            levels=levels,
            tempo=self._tempo,
            position=position,
            energy=energy,
        )

    def _energy_at(self, beats: float) -> float:
        bars = beats / BEATS_PER_BAR
        return 0.5 - 0.5 * math.cos(TAU * bars / ENERGY_CYCLE_BARS)

    def _levels_at(self, phase: float, energy: float) -> Levels:
        beat_s = self._tempo.beat_duration_s
        kick = math.exp(-phase * beat_s / KICK_DECAY_S)
        hat = math.exp(-((phase - OFFBEAT_PHASE) % 1.0) * beat_s / HAT_DECAY_S)
        return Levels(
            kick=kick,
            bass=(0.4 + 0.5 * energy) * (1.0 - SIDECHAIN_DEPTH * kick),
            mid=0.2 + 0.4 * energy,
            high=hat * (0.4 + 0.6 * energy),
        )

    def _peaks_at(self, levels: Levels, time_s: float) -> Peaks:
        return Peaks.ranked(
            Peak(
                freq_hz=voice.freq_hz,
                amplitude=min(1.0, voice.level(levels) * (1.0 - rank * PEAK_ROLLOFF_PER_RANK)),
                phase_rad=(TAU * voice.freq_hz * time_s) % TAU,
            )
            for rank, voice in enumerate(PEAK_VOICES)
        )

    def _spectrum_of(self, levels: Levels) -> Spectrum:
        voiced = sum(
            (
                voice.gain * voice.level(levels) * shape
                for voice, shape in zip(SPECTRAL_VOICES, self._voice_shapes, strict=True)
            ),
            start=np.zeros(BAND_COUNT, dtype=np.float32),
        )
        noise = self._rng.uniform(0.0, SPECTRUM_NOISE_CEILING, BAND_COUNT).astype(np.float32)
        return Spectrum(bands=np.clip(voiced + noise, 0.0, 1.0).astype(np.float32))

    def _waveform_of(self, peaks: Peaks, high: float) -> Waveform:
        tonal = [peak for peak in peaks.items if peak.freq_hz < TONAL_CEILING_HZ]
        freqs_hz = np.array([peak.freq_hz for peak in tonal]).reshape(-1, 1)
        amplitudes = np.array([peak.amplitude for peak in tonal]).reshape(-1, 1)
        phases_rad = np.array([peak.phase_rad for peak in tonal]).reshape(-1, 1)
        partials = amplitudes * np.sin(TAU * freqs_hz * self._waveform_times_s + phases_rad)
        noise = high * self._rng.normal(0.0, WAVEFORM_NOISE_STD, WAVEFORM_LENGTH)
        samples = (partials.sum(axis=0) + noise).astype(np.float32)
        peak_abs = max(1.0, float(np.max(np.abs(samples))))
        return Waveform(samples=np.clip(samples / peak_abs, -1.0, 1.0).astype(np.float32))


def spectral_shape(log2_centers: NDArray[np.float64], voice: SpectralVoice) -> Float32Array:
    z = (log2_centers - math.log2(voice.center_hz)) / voice.width_octaves
    return np.exp(-0.5 * z * z).astype(np.float32)
