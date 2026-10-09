import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.beat_grid import BeatGrid
from spectra.analysis.domain.envelopes import power_to_db
from spectra.analysis.domain.errors import InvalidSectionError
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.stft import FRAME_RATE_HZ

SUDDEN_WINDOW_BARS: Final = 2
SUSTAINED_WINDOW_BARS: Final = 8
MIN_SECTION_BARS: Final = 8
LOUDNESS_SCALE_DB: Final = 6.0
TIMBRE_SCALE: Final = 0.1
SUDDEN_THRESHOLD: Final = 0.5
SUSTAINED_THRESHOLD: Final = 0.5
LOUD_MARGIN_DB: Final = 3.0
RISE_DB: Final = 1.5
LOUDNESS_FLOOR_DB: Final = -120.0

type Float64Array = NDArray[np.float64]


class SectionName(StrEnum):
    INTRO = "intro"
    BUILDUP = "buildup"
    DROP = "drop"
    BREAKDOWN = "breakdown"
    OUTRO = "outro"


@dataclass(frozen=True, slots=True, kw_only=True)
class Section:
    name: SectionName
    start_s: float
    end_s: float
    loud: bool

    def __post_init__(self) -> None:
        if not (math.isfinite(self.end_s) and 0.0 <= self.start_s < self.end_s):
            raise InvalidSectionError(
                f"section must satisfy 0 <= start_s < end_s, got [{self.start_s}, {self.end_s})"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class BarFeatures:
    loudness_db: Float64Array
    profiles: Float64Array


def require_contiguous(sections: Sequence[Section], *, duration_s: float) -> None:
    if not sections:
        raise InvalidSectionError("a track has at least one section")
    if sections[0].start_s != 0.0 or sections[-1].end_s != duration_s:
        raise InvalidSectionError(f"sections must cover [0, {duration_s}] exactly")
    if any(left.end_s != right.start_s for left, right in pairwise(sections)):
        raise InvalidSectionError("sections must follow each other without gaps or overlaps")


def find_sections(
    band_power: Float32Array, band_levels: Float32Array, *, grid: BeatGrid, duration_s: float
) -> tuple[Section, ...]:
    features = bar_features(band_power, band_levels, grid=grid, duration_s=duration_s)
    boundaries = section_boundaries(features)
    edges_s = [0.0, *(grid.bar_start_s(bar) for bar in boundaries), duration_s]
    spans = [
        range(start, end) for start, end in pairwise([0, *boundaries, features.loudness_db.size])
    ]
    loudness_db = [float(features.loudness_db[span].mean()) for span in spans]
    louds = loud_flags(loudness_db)
    return tuple(
        Section(
            name=section_name(index, louds, rising=rising(features.loudness_db[span])),
            start_s=start_s,
            end_s=end_s,
            loud=louds[index],
        )
        for index, (span, (start_s, end_s)) in enumerate(zip(spans, pairwise(edges_s), strict=True))
    )


def bar_features(
    band_power: Float32Array, band_levels: Float32Array, *, grid: BeatGrid, duration_s: float
) -> BarFeatures:
    bar_count = grid.bar_count(duration_s)
    bars = grid.bars_at(np.arange(band_power.shape[0]) / FRAME_RATE_HZ, bar_count=bar_count)
    frame_db = power_to_db(band_power.sum(axis=1), floor_db=LOUDNESS_FLOOR_DB)
    return BarFeatures(
        loudness_db=bar_means(frame_db[:, np.newaxis], bars, bar_count)[:, 0],
        profiles=bar_means(band_levels, bars, bar_count),
    )


def bar_means(values: Float32Array, bars: NDArray[np.int64], bar_count: int) -> Float64Array:
    sums = np.zeros((bar_count, values.shape[1]))
    np.add.at(sums, bars, values)
    counts = np.bincount(bars, minlength=bar_count).astype(np.float64)
    means = sums / np.maximum(counts, 1.0)[:, np.newaxis]
    filled = np.maximum.accumulate(np.where(counts > 0, np.arange(bar_count), 0))
    return means[filled]


def novelty(features: BarFeatures, *, window_bars: int) -> Float64Array:
    bar_count = features.loudness_db.size
    scores = np.zeros(bar_count)
    for bar in range(1, bar_count):
        before = slice(max(0, bar - window_bars), bar)
        after = slice(bar, min(bar_count, bar + window_bars))
        loudness_change = abs(
            features.loudness_db[before].mean() - features.loudness_db[after].mean()
        )
        timbre_change = cosine_distance(
            features.profiles[before].mean(axis=0), features.profiles[after].mean(axis=0)
        )
        scores[bar] = loudness_change / LOUDNESS_SCALE_DB + timbre_change / TIMBRE_SCALE
    return scores


def cosine_distance(first: Float64Array, second: Float64Array) -> float:
    norms = float(np.linalg.norm(first) * np.linalg.norm(second))
    if norms == 0.0:
        return 0.0 if not first.any() and not second.any() else 1.0
    return 1.0 - float(first @ second) / norms


def section_boundaries(features: BarFeatures) -> list[int]:
    sudden = novelty(features, window_bars=SUDDEN_WINDOW_BARS)
    sustained = novelty(features, window_bars=SUSTAINED_WINDOW_BARS)
    scores = sudden + sustained
    bar_count = scores.size
    candidates = [
        bar
        for bar in range(MIN_SECTION_BARS, bar_count - MIN_SECTION_BARS + 1)
        if sudden[bar] >= SUDDEN_THRESHOLD and sustained[bar] >= SUSTAINED_THRESHOLD
    ]
    chosen: list[int] = []
    for bar in sorted(candidates, key=lambda candidate: scores[candidate], reverse=True):
        if all(abs(bar - other) >= MIN_SECTION_BARS for other in chosen):
            chosen.append(bar)
    return sorted(chosen)


def loud_flags(loudness_db: Sequence[float]) -> list[bool]:
    loudest = max(loudness_db)
    return [level >= loudest - LOUD_MARGIN_DB for level in loudness_db]


def rising(loudness_db: Float64Array) -> bool:
    half = loudness_db.size // 2
    if half == 0:
        return False
    return float(loudness_db[-half:].mean() - loudness_db[:half].mean()) >= RISE_DB


def section_name(index: int, louds: Sequence[bool], *, rising: bool) -> SectionName:
    last = len(louds) - 1
    if louds[index]:
        return SectionName.DROP
    if index == 0:
        return SectionName.INTRO
    if index == last:
        return SectionName.OUTRO
    if louds[index + 1] and rising:
        return SectionName.BUILDUP
    return SectionName.BREAKDOWN
