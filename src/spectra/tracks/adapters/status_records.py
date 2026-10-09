from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from spectra.analysis.domain.sections import Section, SectionName
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    Ready,
    TrackStatus,
    TrackSummary,
)


class StatusState(StrEnum):
    ANALYSING = "analysing"
    READY = "ready"
    FAILED = "failed"


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SectionRecord(Record):
    name: SectionName
    start_s: float
    end_s: float
    loud: bool


class SummaryRecord(Record):
    duration_s: float
    bpm: float
    beat_offset_s: float
    sections: tuple[SectionRecord, ...]


class AnalysingRecord(Record):
    state: Literal[StatusState.ANALYSING] = StatusState.ANALYSING
    stage: AnalysisStage
    progress: float


class ReadyRecord(Record):
    state: Literal[StatusState.READY] = StatusState.READY
    summary: SummaryRecord


class FailedRecord(Record):
    state: Literal[StatusState.FAILED] = StatusState.FAILED
    code: FailureCode
    message: str


type StatusRecord = AnalysingRecord | ReadyRecord | FailedRecord

STATUS_RECORDS: Final = TypeAdapter[StatusRecord](
    Annotated[StatusRecord, Field(discriminator="state")]
)


def state_of(status: TrackStatus) -> StatusState:
    return record_of(status).state


def status_document(status: TrackStatus) -> dict[str, object]:
    return record_of(status).model_dump(mode="json")


def status_from_document(document: object) -> TrackStatus:
    return status_of(STATUS_RECORDS.validate_python(document))


def record_of(status: TrackStatus) -> StatusRecord:
    match status:
        case Analysing(stage=stage, progress=progress):
            return AnalysingRecord(stage=stage, progress=progress)
        case Ready(summary=summary):
            return ReadyRecord(summary=summary_record(summary))
        case Failed(code=code, message=message):
            return FailedRecord(code=code, message=message)


def status_of(record: StatusRecord) -> TrackStatus:
    match record:
        case AnalysingRecord(stage=stage, progress=progress):
            return Analysing(stage=stage, progress=progress)
        case ReadyRecord(summary=summary):
            return Ready(summary=summary_of(summary))
        case FailedRecord(code=code, message=message):
            return Failed(code=code, message=message)


def summary_record(summary: TrackSummary) -> SummaryRecord:
    return SummaryRecord(
        duration_s=summary.duration_s,
        bpm=summary.bpm,
        beat_offset_s=summary.beat_offset_s,
        sections=tuple(
            SectionRecord(
                name=section.name,
                start_s=section.start_s,
                end_s=section.end_s,
                loud=section.loud,
            )
            for section in summary.sections
        ),
    )


def summary_of(record: SummaryRecord) -> TrackSummary:
    return TrackSummary(
        duration_s=record.duration_s,
        bpm=record.bpm,
        beat_offset_s=record.beat_offset_s,
        sections=tuple(
            Section(
                name=section.name,
                start_s=section.start_s,
                end_s=section.end_s,
                loud=section.loud,
            )
            for section in record.sections
        ),
    )
