import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ, AudioSignal

SAMPLE_RATE_HZ: Final = ANALYSIS_SAMPLE_RATE_HZ
KICK_LENGTH_S: Final = 0.25
KICK_FREQ_HZ: Final = 55.0
KICK_DECAY_S: Final = 0.06


def times_s(duration_s: float) -> NDArray[np.float64]:
    return np.arange(round(duration_s * SAMPLE_RATE_HZ)) / SAMPLE_RATE_HZ


def sine(freq_hz: float, duration_s: float, *, amplitude: float = 1.0) -> Float32Array:
    return (amplitude * np.sin(2.0 * math.pi * freq_hz * times_s(duration_s))).astype(np.float32)


def silence(duration_s: float) -> Float32Array:
    return np.zeros(round(duration_s * SAMPLE_RATE_HZ), dtype=np.float32)


def noise(duration_s: float, *, amplitude: float = 1.0, seed: int = 0) -> Float32Array:
    rng = np.random.default_rng(seed)
    count = round(duration_s * SAMPLE_RATE_HZ)
    return rng.uniform(-amplitude, amplitude, count).astype(np.float32)


def kick() -> Float32Array:
    t_s = times_s(KICK_LENGTH_S)
    body = np.sin(2.0 * math.pi * KICK_FREQ_HZ * t_s) * np.exp(-t_s / KICK_DECAY_S)
    return body.astype(np.float32)


@dataclass(frozen=True, slots=True, kw_only=True)
class Accent:
    every: int
    first: int = 0
    gain: float = 2.0


def kick_train(
    bpm: float,
    duration_s: float,
    *,
    offset_s: float = 0.0,
    gain: float = 0.5,
    accent: Accent | None = None,
) -> Float32Array:
    out = silence(duration_s)
    hit = kick()
    beat_s = 60.0 / bpm
    beat_count = math.floor((duration_s - offset_s) / beat_s) + 1
    for beat in range(beat_count):
        start = round((offset_s + beat * beat_s) * SAMPLE_RATE_HZ)
        accented = accent is not None and beat % accent.every == accent.first
        level = gain * (accent.gain if accent is not None and accented else 1.0)
        end = min(out.size, start + hit.size)
        out[start:end] += level * hit[: end - start]
    return out


def impulse_at(time_s: float, duration_s: float) -> Float32Array:
    out = silence(duration_s)
    out[round(time_s * SAMPLE_RATE_HZ)] = 1.0
    return out


def signal_of(*parts: Float32Array) -> AudioSignal:
    return AudioSignal(samples=np.concatenate(parts))
