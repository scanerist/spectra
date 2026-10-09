import math
from typing import Final

import numpy as np
import pytest

from spectra.analysis.domain.bar_spectra import FOURIER_BIN_COUNT
from spectra.analysis.domain.beat_grid import BeatGrid
from spectra.analysis.domain.errors import InvalidTrackAnalysisError, UnanalysableSignalError
from spectra.analysis.domain.frame_levels import LEVEL_COUNT
from spectra.analysis.domain.peaks import Peaks
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.sections import Section, SectionName
from spectra.analysis.domain.spectrum import BAND_COUNT
from spectra.analysis.domain.tempo import Tempo
from spectra.analysis.domain.track_analysis import (
    AnalysisStage,
    TrackAnalysis,
    analyse_signal,
)
from tests.signals import SAMPLE_RATE_HZ, kick_train, noise, signal_of, silence, sine

BPM: Final = 128.0
BAR_S: Final = 4 * 60.0 / BPM
BLOCK_BARS: Final = 16


def gain_curve(gains: list[tuple[float, float]]) -> Float32Array:
    block = round(BLOCK_BARS * BAR_S * SAMPLE_RATE_HZ)
    return np.concatenate([np.linspace(start, end, block) for start, end in gains]).astype(
        np.float32
    )


def dance_track() -> Float32Array:
    kick_gains = [(0.1, 0.1), (0.1, 0.1), (0.5, 0.5), (0.0, 0.0), (0.5, 0.5), (0.1, 0.1)]
    noise_gains = [(0.0, 0.0), (0.0, 0.15), (0.1, 0.1), (0.03, 0.03), (0.1, 0.1), (0.0, 0.0)]
    duration_s = len(kick_gains) * BLOCK_BARS * BAR_S
    kicks = kick_train(BPM, duration_s, gain=1.0)
    hiss = noise(duration_s)
    kick_gain = gain_curve(kick_gains)
    noise_gain = gain_curve(noise_gains)
    length = min(kicks.size, kick_gain.size)
    return kicks[:length] * kick_gain[:length] + hiss[:length] * noise_gain[:length]


@pytest.fixture(scope="module")
def stages_and_analysis() -> tuple[list[AnalysisStage], TrackAnalysis]:
    stages: list[AnalysisStage] = []
    analysis = analyse_signal(signal_of(dance_track()), on_stage=stages.append)
    return stages, analysis


@pytest.fixture(scope="module")
def analysis(stages_and_analysis: tuple[list[AnalysisStage], TrackAnalysis]) -> TrackAnalysis:
    return stages_and_analysis[1]


def test_analysis_reports_spectrum_tempo_and_structure_in_order(
    stages_and_analysis: tuple[list[AnalysisStage], TrackAnalysis],
) -> None:
    assert stages_and_analysis[0] == ["spectrum", "tempo", "structure"]


def test_analysis_finds_the_tempo(analysis: TrackAnalysis) -> None:
    assert analysis.grid.tempo.bpm == pytest.approx(BPM, abs=0.5)


def test_analysis_finds_the_dance_track_shape(analysis: TrackAnalysis) -> None:
    assert [section.name for section in analysis.sections] == [
        "intro",
        "buildup",
        "drop",
        "breakdown",
        "drop",
        "outro",
    ]
    starts_bars = [section.start_s / BAR_S for section in analysis.sections[1:]]
    assert starts_bars == pytest.approx([16, 32, 48, 64, 80], abs=1)


def test_analysis_puts_bar_zero_on_a_section_downbeat(analysis: TrackAnalysis) -> None:
    beats_off = analysis.grid.offset_s / (60.0 / BPM)
    assert min(beats_off, 4 - beats_off) == pytest.approx(0.0, abs=0.05)


def test_analysis_arrays_match_the_contract_shapes(analysis: TrackAnalysis) -> None:
    frames = math.ceil(analysis.sample_count / 512)
    assert analysis.frame_count == frames
    assert analysis.bands.shape == (frames, BAND_COUNT)
    assert analysis.levels.shape == (frames, LEVEL_COUNT)
    assert analysis.bar_spectra.shape == (analysis.bar_count, FOURIER_BIN_COUNT)
    assert len(analysis.bar_peaks) == analysis.bar_count
    assert analysis.bar_count == math.ceil(
        (analysis.duration_s - analysis.grid.offset_s) / analysis.grid.bar_duration_s
    )


def test_loud_bars_carry_the_kick_as_their_main_peak(analysis: TrackAnalysis) -> None:
    drop_bar = 40
    assert analysis.bar_peaks[drop_bar].items[0].freq_hz == pytest.approx(55.0, rel=0.05)


@pytest.mark.parametrize(
    "samples",
    [silence(30.0), kick_train(BPM, 4.0), sine(440.0, 30.0, amplitude=1e-6)],
    ids=["silence", "too-short", "near-silence"],
)
def test_unanalysable_signals_are_rejected(samples: Float32Array) -> None:
    with pytest.raises(UnanalysableSignalError):
        analyse_signal(signal_of(samples))


def minimal_analysis(**overrides: object) -> TrackAnalysis:
    grid = BeatGrid(tempo=Tempo(bpm=120.0), offset_s=0.0)
    sample_count = SAMPLE_RATE_HZ * 4
    frames = math.ceil(sample_count / 512)
    fields: dict[str, object] = {
        "sample_count": sample_count,
        "grid": grid,
        "sections": (Section(name=SectionName.DROP, start_s=0.0, end_s=4.0, loud=True),),
        "bands": np.zeros((frames, BAND_COUNT), dtype=np.float32),
        "levels": np.zeros((frames, LEVEL_COUNT), dtype=np.float32),
        "bar_peaks": (Peaks(items=()), Peaks(items=())),
        "bar_spectra": np.zeros((2, FOURIER_BIN_COUNT), dtype=np.float32),
    }
    fields.update(overrides)
    return TrackAnalysis(**fields)  # type: ignore[arg-type]


def test_minimal_analysis_is_valid_and_read_only() -> None:
    analysis = minimal_analysis()
    with pytest.raises(ValueError, match="read-only"):
        analysis.bands[0, 0] = 1.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"bands": np.zeros((3, BAND_COUNT), dtype=np.float32)},
        {"levels": np.full((345, LEVEL_COUNT), 2.0, dtype=np.float32)},
        {"bar_spectra": np.zeros((3, FOURIER_BIN_COUNT), dtype=np.float32)},
        {"bar_peaks": (Peaks(items=()),)},
        {"sections": (Section(name=SectionName.DROP, start_s=0.0, end_s=3.0, loud=True),)},
        {"sample_count": 0},
    ],
    ids=["bands-shape", "levels-range", "spectra-bars", "peaks-bars", "sections-cover", "empty"],
)
def test_analysis_rejects_inconsistent_parts(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidTrackAnalysisError):
        minimal_analysis(**overrides)
