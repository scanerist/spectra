from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import numpy as np

from spectra.analysis.domain.bands import BAND_COUNT, band_levels, fold_to_bands
from spectra.analysis.domain.bar_spectra import FOURIER_BIN_COUNT, bar_peaks, bar_spectra
from spectra.analysis.domain.beat_grid import BeatGrid, locate_beat_grid
from spectra.analysis.domain.errors import (
    InvalidSectionError,
    InvalidShapeError,
    InvalidTrackAnalysisError,
    OutOfRangeError,
    UnanalysableSignalError,
)
from spectra.analysis.domain.frame_levels import LEVEL_COUNT, frame_levels
from spectra.analysis.domain.onsets import onset_envelope, upper_onset_envelope
from spectra.analysis.domain.peaks import Peaks
from spectra.analysis.domain.ranges import Float32Array, read_only_float32, require_array_in_range
from spectra.analysis.domain.sections import Section, find_sections, require_contiguous
from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ, AudioSignal
from spectra.analysis.domain.stft import FRAME_RATE_HZ, frame_count, stft_chunks
from spectra.analysis.domain.tempo_estimation import estimate_tempo

MIN_DURATION_S: Final = 8.0
SILENCE_PEAK: Final = 1e-4


class AnalysisStage(StrEnum):
    DECODING = "decoding"
    SPECTRUM = "spectrum"
    TEMPO = "tempo"
    STRUCTURE = "structure"


type StageListener = Callable[[AnalysisStage], None]


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class TrackAnalysis:
    sample_count: int
    grid: BeatGrid
    sections: tuple[Section, ...]
    bands: Float32Array
    levels: Float32Array
    bar_peaks: tuple[Peaks, ...]
    bar_spectra: Float32Array

    def __post_init__(self) -> None:
        if self.sample_count <= 0:
            raise InvalidTrackAnalysisError(f"sample_count must be > 0, got {self.sample_count}")
        try:
            self._freeze("bands", (self.frame_count, BAND_COUNT))
            self._freeze("levels", (self.frame_count, LEVEL_COUNT))
            self._freeze("bar_spectra", (self.bar_count, FOURIER_BIN_COUNT))
            require_contiguous(self.sections, duration_s=self.duration_s)
        except (InvalidShapeError, OutOfRangeError, InvalidSectionError) as error:
            raise InvalidTrackAnalysisError(str(error)) from error
        if len(self.bar_peaks) != self.bar_count:
            raise InvalidTrackAnalysisError(
                f"expected peaks for {self.bar_count} bars, got {len(self.bar_peaks)}"
            )

    @property
    def duration_s(self) -> float:
        return self.sample_count / ANALYSIS_SAMPLE_RATE_HZ

    @property
    def frame_rate_hz(self) -> float:
        return FRAME_RATE_HZ

    @property
    def frame_count(self) -> int:
        return frame_count(self.sample_count)

    @property
    def bar_count(self) -> int:
        return self.grid.bar_count(self.duration_s)

    def _freeze(self, name: str, shape: tuple[int, int]) -> None:
        frozen = read_only_float32(getattr(self, name), name=name, shape=shape)
        require_array_in_range(name, frozen, low=0.0, high=1.0)
        object.__setattr__(self, name, frozen)


def ignore_stage(_stage: AnalysisStage) -> None:
    return None


def analyse_signal(signal: AudioSignal, *, on_stage: StageListener = ignore_stage) -> TrackAnalysis:
    require_analysable(signal)
    on_stage(AnalysisStage.SPECTRUM)
    power = fold_to_bands(stft_chunks(signal))
    bands = band_levels(power)
    levels = frame_levels(power, bands)
    on_stage(AnalysisStage.TEMPO)
    pulses = onset_envelope(power)
    tempo = estimate_tempo(
        pulses, upper_envelope=upper_onset_envelope(power), frame_rate_hz=FRAME_RATE_HZ
    )
    grid = locate_beat_grid(pulses, bands, tempo=tempo, frame_rate_hz=FRAME_RATE_HZ)
    on_stage(AnalysisStage.STRUCTURE)
    sections = find_sections(power, bands, grid=grid, duration_s=signal.duration_s)
    spectra = bar_spectra(signal, grid=grid, bar_count=grid.bar_count(signal.duration_s))
    return TrackAnalysis(
        sample_count=signal.sample_count,
        grid=grid,
        sections=sections,
        bands=bands,
        levels=levels,
        bar_peaks=tuple(bar_peaks(row) for row in spectra),
        bar_spectra=spectra,
    )


def require_analysable(signal: AudioSignal) -> None:
    if signal.duration_s < MIN_DURATION_S:
        raise UnanalysableSignalError(
            f"a track needs at least {MIN_DURATION_S:g} s, got {signal.duration_s:.2f} s"
        )
    if float(np.abs(signal.samples).max()) < SILENCE_PEAK:
        raise UnanalysableSignalError("the track is silent")
