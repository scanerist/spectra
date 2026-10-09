from pydantic import BaseModel, ConfigDict

from spectra.analysis.domain.sections import Section
from spectra.analysis.domain.track_analysis import TrackAnalysis
from spectra.tracks.domain.track import TrackId


class ApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TrackCreated(ApiModel):
    track_id: str


class SectionBody(ApiModel):
    name: str
    start_s: float
    end_s: float
    loud: bool


class TrackInfo(ApiModel):
    track_id: str
    duration_s: float
    bpm: float
    beat_offset_s: float
    sections: list[SectionBody]


class ErrorBody(ApiModel):
    error: str
    message: str


def section_body(section: Section) -> SectionBody:
    return SectionBody(
        name=section.name.value,
        start_s=section.start_s,
        end_s=section.end_s,
        loud=section.loud,
    )


def track_info(track_id: TrackId, analysis: TrackAnalysis) -> TrackInfo:
    return TrackInfo(
        track_id=track_id.value,
        duration_s=analysis.duration_s,
        bpm=analysis.grid.tempo.bpm,
        beat_offset_s=analysis.grid.offset_s,
        sections=[section_body(section) for section in analysis.sections],
    )
