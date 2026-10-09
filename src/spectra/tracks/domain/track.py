import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Self

from spectra.analysis.domain.ranges import require_unit_interval
from spectra.analysis.domain.sections import Section
from spectra.analysis.domain.track_analysis import AnalysisStage, TrackAnalysis
from spectra.tracks.domain.errors import InvalidTrackIdError

TRACK_ID_LENGTH: Final = 16
TRACK_ID_PATTERN: Final = re.compile(rf"[0-9a-f]{{{TRACK_ID_LENGTH}}}")
STAGE_PROGRESS: Final[Mapping[AnalysisStage, float]] = {
    AnalysisStage.DECODING: 0.0,
    AnalysisStage.SPECTRUM: 0.25,
    AnalysisStage.TEMPO: 0.55,
    AnalysisStage.STRUCTURE: 0.75,
}


@dataclass(frozen=True, slots=True)
class TrackId:
    value: str

    def __post_init__(self) -> None:
        if not TRACK_ID_PATTERN.fullmatch(self.value):
            raise InvalidTrackIdError(f"track id must be {TRACK_ID_LENGTH} hex digits")

    @classmethod
    def of_content(cls, data: bytes) -> Self:
        return cls(hashlib.sha256(data).hexdigest()[:TRACK_ID_LENGTH])


class FailureCode(StrEnum):
    UNDECODABLE = "undecodable"
    ANALYSIS_FAILED = "analysis_failed"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True, kw_only=True)
class Analysing:
    stage: AnalysisStage
    progress: float

    def __post_init__(self) -> None:
        require_unit_interval("progress", self.progress)

    @classmethod
    def at(cls, stage: AnalysisStage) -> Self:
        return cls(stage=stage, progress=STAGE_PROGRESS[stage])


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackSummary:
    duration_s: float
    bpm: float
    beat_offset_s: float
    sections: tuple[Section, ...]

    @classmethod
    def of_analysis(cls, analysis: TrackAnalysis) -> Self:
        return cls(
            duration_s=analysis.duration_s,
            bpm=analysis.grid.tempo.bpm,
            beat_offset_s=analysis.grid.offset_s,
            sections=analysis.sections,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Ready:
    summary: TrackSummary


@dataclass(frozen=True, slots=True, kw_only=True)
class Failed:
    code: FailureCode
    message: str


type TrackStatus = Analysing | Ready | Failed


def is_final(status: TrackStatus) -> bool:
    return not isinstance(status, Analysing)


def outcome_name(status: TrackStatus) -> str:
    match status:
        case Analysing():
            return "analysing"
        case Ready():
            return "ready"
        case Failed(code=code):
            return code.value
