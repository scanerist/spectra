from __future__ import annotations

import math

import numpy as np

from spectra.legacy.protocol import (
    BANDS_FMAX_HZ,
    BANDS_FMIN_HZ,
    F32,
    N_BANDS,
    N_PEAKS,
    N_WAVEFORM,
    FeatureFrame,
)

KICK_DECAY_S = 0.12
HAT_DECAY_S = 0.04
WAVEFORM_WINDOW_S = 0.030
ENERGY_CYCLE_BARS = 32

# (freq_hz, which feature drives it)
_PEAK_SOURCES: list[tuple[float, str]] = [
    (55.0, "kick"),
    (110.0, "bass"),
    (165.0, "bass"),
    (440.0, "mid"),
    (1_000.0, "mid"),
    (3_200.0, "mid"),
    (8_000.0, "high"),
    (12_000.0, "high"),
]
assert len(_PEAK_SOURCES) == N_PEAKS


class FakeSource:
    def __init__(self, bpm: float = 128.0, seed: int = 0) -> None:
        self.bpm = bpm
        self._rng = np.random.default_rng(seed)
        self._log2f = np.log2(np.geomspace(BANDS_FMIN_HZ, BANDS_FMAX_HZ, N_BANDS))
        self._x = np.linspace(0.0, WAVEFORM_WINDOW_S, N_WAVEFORM, endpoint=False)

    def _bump(self, center_hz: float, width_oct: float) -> F32:
        z = (self._log2f - math.log2(center_hz)) / width_oct
        return np.exp(-0.5 * z * z).astype(np.float32)

    def frame(self, t: float) -> FeatureFrame:
        beat_s = 60.0 / self.bpm
        beats = t / beat_s
        beat_idx = int(beats)
        phase = beats - beat_idx
        bar, beat_in_bar = divmod(beat_idx, 4)

        kick = math.exp(-phase * beat_s / KICK_DECAY_S)
        hat = math.exp(-((phase - 0.5) % 1.0) * beat_s / HAT_DECAY_S)
        energy = 0.5 - 0.5 * math.cos(2 * math.pi * (beats / 4) / ENERGY_CYCLE_BARS)
        bass = (0.4 + 0.5 * energy) * (1.0 - 0.8 * kick)  # sidechain pump
        mid = 0.2 + 0.4 * energy
        high = hat * (0.4 + 0.6 * energy)
        level = {"kick": kick, "bass": bass, "mid": mid, "high": high}

        bands = (
            kick * self._bump(55, 0.5)
            + 0.8 * bass * self._bump(110, 0.7)
            + 0.5 * mid * self._bump(1_000, 1.5)
            + 0.6 * high * self._bump(8_000, 0.8)
            + self._rng.uniform(0.0, 0.03, N_BANDS).astype(np.float32)
        )
        bands = np.clip(bands, 0.0, 1.0).astype(np.float32)

        peaks = np.array(
            [
                (f, min(1.0, level[src] * (1.0 - i * 0.05)), (2 * math.pi * f * t) % (2 * math.pi))
                for i, (f, src) in enumerate(_PEAK_SOURCES)
            ],
            dtype=np.float32,
        )
        peaks = peaks[np.argsort(-peaks[:, 1], kind="stable")]

        tonal = sum(a * np.sin(2 * math.pi * f * self._x + ph) for f, a, ph in peaks if f < 4_000)
        noise = high * self._rng.normal(0.0, 0.3, N_WAVEFORM)
        wave = np.asarray(tonal + noise, dtype=np.float32)
        peak_abs = float(np.max(np.abs(wave)))
        if peak_abs > 1.0:
            wave /= peak_abs

        return FeatureFrame(
            t=t,
            bands=bands,
            waveform=wave,
            peaks=peaks,
            kick=kick,
            bass=bass,
            mid=mid,
            high=high,
            bpm=self.bpm,
            beat_phase=phase,
            bar=bar,
            beat_in_bar=beat_in_bar,
            energy=energy,
        )
