import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.envelopes import moving_average
from spectra.analysis.domain.errors import TempoNotFoundError
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.tempo import SECONDS_PER_MINUTE, Tempo

MIN_SEARCH_BPM: Final = 60.0
MAX_SEARCH_BPM: Final = 200.0
PRIOR_CENTRE_BPM: Final = 120.0
PRIOR_WIDTH_OCTAVES: Final = 1.0
COARSE_HARMONICS: Final = 4
REFINE_HARMONICS: Final = 16
REFINE_SPAN: Final = 0.03
REFINE_STEP_BPM: Final = 0.01
DETREND_S: Final = 0.5
PHASE_STEP_FRAMES: Final = 0.25
OCTAVE_FACTORS: Final = (0.5, 1.0, 2.0)

type Float64Array = NDArray[np.float64]


@dataclass(frozen=True, slots=True, kw_only=True)
class GridFit:
    salience: float
    phase_frames: float


def estimate_tempo(envelope: Float32Array, *, frame_rate_hz: float) -> Tempo:
    pulses = detrended(envelope, frame_rate_hz=frame_rate_hz)
    if not pulses.any():
        raise TempoNotFoundError("the onset envelope has no pulses to measure a tempo from")
    correlation = autocorrelation(pulses)
    coarse_bpm = coarse_tempo(correlation, frame_rate_hz=frame_rate_hz)
    candidates = [
        refine_tempo(correlation, bpm=coarse_bpm * factor, frame_rate_hz=frame_rate_hz)
        for factor in OCTAVE_FACTORS
        if MIN_SEARCH_BPM <= coarse_bpm * factor <= MAX_SEARCH_BPM
    ]
    best = max(
        candidates,
        key=lambda bpm: (
            fit_grid(pulses, period_frames=period_frames(bpm, frame_rate_hz)).salience
            * tempo_prior(bpm)
        ),
    )
    return Tempo(bpm=best)


def detrended(envelope: Float32Array, *, frame_rate_hz: float) -> Float64Array:
    local_mean = moving_average(envelope, width_frames=round(DETREND_S * frame_rate_hz))
    return np.maximum(envelope.astype(np.float64) - local_mean, 0.0)


def autocorrelation(pulses: Float64Array) -> Float64Array:
    count = pulses.size
    spectrum = np.fft.rfft(pulses, n=2 * count)
    raw = np.fft.irfft(np.abs(spectrum) ** 2, n=2 * count)[:count]
    unbiased = raw / (count - np.arange(count))
    return np.asarray(unbiased / unbiased[0], dtype=np.float64)


def period_frames(bpm: float, frame_rate_hz: float) -> float:
    return SECONDS_PER_MINUTE * frame_rate_hz / bpm


def tempo_prior(bpm: float) -> float:
    octaves = math.log2(bpm / PRIOR_CENTRE_BPM) / PRIOR_WIDTH_OCTAVES
    return math.exp(-0.5 * octaves * octaves)


def harmonic_score(correlation: Float64Array, *, period: float, harmonics: int) -> float:
    usable_lag = correlation.size // 2
    lags = period * np.arange(1, harmonics + 1)
    lags = lags[lags < usable_lag]
    if lags.size == 0:
        return 0.0
    return float(np.interp(lags, np.arange(correlation.size), correlation).mean())


def coarse_tempo(correlation: Float64Array, *, frame_rate_hz: float) -> float:
    shortest = math.ceil(period_frames(MAX_SEARCH_BPM, frame_rate_hz))
    longest = math.floor(period_frames(MIN_SEARCH_BPM, frame_rate_hz))
    lags = range(shortest, longest + 1)
    scores = [
        harmonic_score(correlation, period=lag, harmonics=COARSE_HARMONICS)
        * tempo_prior(SECONDS_PER_MINUTE * frame_rate_hz / lag)
        for lag in lags
    ]
    best_lag = lags[int(np.argmax(scores))]
    return SECONDS_PER_MINUTE * frame_rate_hz / best_lag


def refine_tempo(correlation: Float64Array, *, bpm: float, frame_rate_hz: float) -> float:
    grid = np.arange(bpm * (1 - REFINE_SPAN), bpm * (1 + REFINE_SPAN), REFINE_STEP_BPM)
    grid = grid[(grid >= MIN_SEARCH_BPM) & (grid <= MAX_SEARCH_BPM)]
    if grid.size == 0:
        return bpm
    scores = [
        harmonic_score(
            correlation, period=period_frames(candidate, frame_rate_hz), harmonics=REFINE_HARMONICS
        )
        for candidate in grid
    ]
    return float(grid[int(np.argmax(scores))])


def fit_grid(pulses: Float64Array, *, period_frames: float) -> GridFit:
    beats = np.arange(math.floor((pulses.size - 1) / period_frames))
    if beats.size == 0:
        return GridFit(salience=0.0, phase_frames=0.0)
    phases = np.arange(0.0, period_frames, PHASE_STEP_FRAMES)
    on_beat = phases[:, np.newaxis] + beats[np.newaxis, :] * period_frames
    frames = np.arange(pulses.size)
    on = np.interp(on_beat, frames, pulses).mean(axis=1)
    off = np.interp(on_beat + period_frames / 2.0, frames, pulses).mean(axis=1)
    salience = on - off
    best = int(np.argmax(salience))
    return GridFit(salience=float(salience[best]), phase_frames=float(phases[best]))
