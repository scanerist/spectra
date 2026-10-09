import numpy as np

from spectra.analysis.domain.bands import BAND_COUNT
from spectra.analysis.domain.bar_spectra import FOURIER_BIN_COUNT
from spectra.analysis.domain.beat_grid import BeatGrid
from spectra.analysis.domain.frame_levels import LEVEL_COUNT
from spectra.analysis.domain.peaks import Peak, Peaks
from spectra.analysis.domain.sections import Section, SectionName
from spectra.analysis.domain.stft import HOP_SAMPLES
from spectra.analysis.domain.tempo import Tempo
from spectra.analysis.domain.track_analysis import TrackAnalysis

GOLDEN_FRAMES = 70
GOLDEN_BARS = 2


def golden_analysis() -> TrackAnalysis:
    sample_count = GOLDEN_FRAMES * HOP_SAMPLES
    grid = BeatGrid(tempo=Tempo(bpm=300.0), offset_s=0.0)
    duration_s = sample_count / 44_100
    cells = np.arange(GOLDEN_FRAMES * BAND_COUNT, dtype=np.float64)
    bands = ((cells % 256) / 255.0).reshape(GOLDEN_FRAMES, BAND_COUNT)
    levels = np.tile(
        [[0.0, 0.25, 0.5, 0.75, 1.0], [1.0, 0.0, 0.002, 0.998, 0.5]], (GOLDEN_FRAMES // 2, 1)
    )
    spectra = np.stack(
        [np.linspace(0.0, 1.0, FOURIER_BIN_COUNT), np.linspace(1.0, 0.0, FOURIER_BIN_COUNT)]
    )
    return TrackAnalysis(
        sample_count=sample_count,
        grid=grid,
        sections=(Section(name=SectionName.DROP, start_s=0.0, end_s=duration_s, loud=True),),
        bands=bands.astype(np.float32),
        levels=levels.astype(np.float32).reshape(GOLDEN_FRAMES, LEVEL_COUNT),
        bar_peaks=(
            Peaks(items=(Peak(freq_hz=55.0, amplitude=1.0), Peak(freq_hz=110.0, amplitude=0.5))),
            Peaks(items=()),
        ),
        bar_spectra=spectra.astype(np.float32),
    )
