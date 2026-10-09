from typing import Final

import numpy as np
import pytest

from spectra.analysis.domain.bands import band_levels, fold_to_bands
from spectra.analysis.domain.beat_grid import BeatGrid
from spectra.analysis.domain.errors import InvalidSectionError
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.sections import (
    Section,
    SectionName,
    find_sections,
    require_contiguous,
)
from spectra.analysis.domain.stft import stft_chunks
from spectra.analysis.domain.tempo import Tempo
from tests.signals import SAMPLE_RATE_HZ, kick_train, noise, signal_of

BPM: Final = 128.0
BAR_S: Final = 4 * 60.0 / BPM
GRID: Final = BeatGrid(tempo=Tempo(bpm=BPM), offset_s=0.0)
BLOCK_BARS: Final = 16


def gain_curve(gains: list[tuple[float, float]]) -> Float32Array:
    return np.concatenate(
        [
            np.linspace(start, end, round(BLOCK_BARS * BAR_S * SAMPLE_RATE_HZ))
            for start, end in gains
        ]
    ).astype(np.float32)


def track(
    kick_gains: list[tuple[float, float]], noise_gains: list[tuple[float, float]]
) -> Float32Array:
    duration_s = len(kick_gains) * BLOCK_BARS * BAR_S
    kicks = kick_train(BPM, duration_s, gain=1.0)
    hiss = noise(duration_s)
    kick_gain = gain_curve(kick_gains)
    noise_gain = gain_curve(noise_gains)
    length = min(kicks.size, kick_gain.size)
    return kicks[:length] * kick_gain[:length] + hiss[:length] * noise_gain[:length]


def sections_of(samples: Float32Array) -> tuple[Section, ...]:
    signal = signal_of(samples)
    power = fold_to_bands(stft_chunks(signal))
    return find_sections(power, band_levels(power), grid=GRID, duration_s=signal.duration_s)


def boundaries_in_bars(sections: tuple[Section, ...]) -> list[float]:
    return [section.start_s / BAR_S for section in sections[1:]]


def test_quiet_loud_quiet_gives_three_sections_within_a_bar() -> None:
    samples = track([(0.05, 0.05), (0.5, 0.5), (0.05, 0.05)], [(0.0, 0.0)] * 3)
    sections = sections_of(samples)
    assert [section.name for section in sections] == ["intro", "drop", "outro"]
    assert [section.loud for section in sections] == [False, True, False]
    assert boundaries_in_bars(sections) == pytest.approx([16, 32], abs=1)


def test_steady_track_is_one_loud_section() -> None:
    sections = sections_of(track([(0.5, 0.5)] * 3, [(0.0, 0.0)] * 3))
    assert len(sections) == 1
    assert sections[0].name is SectionName.DROP
    assert sections[0].loud


def test_dance_track_shape_is_named_section_by_section() -> None:
    samples = track(
        [(0.1, 0.1), (0.1, 0.1), (0.5, 0.5), (0.0, 0.0), (0.5, 0.5), (0.1, 0.1)],
        [(0.0, 0.0), (0.0, 0.15), (0.1, 0.1), (0.03, 0.03), (0.1, 0.1), (0.0, 0.0)],
    )
    sections = sections_of(samples)
    assert [section.name for section in sections] == [
        "intro",
        "buildup",
        "drop",
        "breakdown",
        "drop",
        "outro",
    ]
    assert boundaries_in_bars(sections) == pytest.approx([16, 32, 48, 64, 80], abs=1)


def test_sections_cover_the_track_without_gaps() -> None:
    signal = signal_of(track([(0.05, 0.05), (0.5, 0.5), (0.05, 0.05)], [(0.0, 0.0)] * 3))
    sections = sections_of(signal.samples)
    require_contiguous(sections, duration_s=signal.duration_s)


def test_section_rejects_an_empty_or_reversed_span() -> None:
    with pytest.raises(InvalidSectionError):
        Section(name=SectionName.DROP, start_s=2.0, end_s=2.0, loud=True)


@pytest.mark.parametrize(
    "spans",
    [[], [(0.5, 4.0)], [(0.0, 2.0), (2.5, 4.0)], [(0.0, 3.0)], [(0.0, 2.0), (1.5, 4.0)]],
    ids=["empty", "late-start", "gap", "short", "overlap"],
)
def test_require_contiguous_rejects_broken_cover(spans: list[tuple[float, float]]) -> None:
    sections = [
        Section(name=SectionName.DROP, start_s=start, end_s=end, loud=True) for start, end in spans
    ]
    with pytest.raises(InvalidSectionError):
        require_contiguous(sections, duration_s=4.0)


def test_section_names_are_the_contract_strings() -> None:
    assert [name.value for name in SectionName] == [
        "intro",
        "buildup",
        "drop",
        "breakdown",
        "outro",
    ]
