from typing import Final

import pytest

from spectra.analysis.domain.sections import Section, SectionName
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    Ready,
    TrackId,
    TrackSummary,
)

SUMMARY: Final = TrackSummary(
    duration_s=96.5,
    bpm=126.0,
    beat_offset_s=0.25,
    sections=(
        Section(name=SectionName.INTRO, start_s=0.0, end_s=30.7, loud=False),
        Section(name=SectionName.DROP, start_s=30.7, end_s=96.5, loud=True),
    ),
)
ANALYSING: Final = Analysing.at(AnalysisStage.TEMPO)
READY: Final = Ready(summary=SUMMARY)
FAILED: Final = Failed(code=FailureCode.UNDECODABLE, message="truncated mp3 frame")
EVERY_STATUS: Final = [
    pytest.param(ANALYSING, id="analysing"),
    pytest.param(READY, id="ready"),
    pytest.param(FAILED, id="failed"),
]


def track(name: str) -> TrackId:
    return TrackId.of_content(name.encode())
