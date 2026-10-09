import pytest

from spectra.analysis.domain.errors import UnsupportedFormatError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.registry import TrackRegistry
from spectra.tracks.application.service import TrackService
from spectra.tracks.domain.errors import (
    EmptyUploadError,
    FileTooLargeError,
    TrackNotFoundError,
    TrackTooLongError,
)
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, TrackId
from tests.fakes import FakeDecoder, FakeJobQueue

DATA = b"RIFF fake wav bytes"
MAX_DURATION_S = 600.0


def service_with(
    decoder: FakeDecoder | None = None, *, max_upload_bytes: int = 1_000
) -> tuple[TrackService, TrackRegistry, FakeJobQueue]:
    registry = TrackRegistry(capacity=8)
    jobs = FakeJobQueue()
    service = TrackService(
        decoder=decoder or FakeDecoder(),
        registry=registry,
        jobs=jobs,
        max_upload_bytes=max_upload_bytes,
        max_duration_s=MAX_DURATION_S,
    )
    return service, registry, jobs


def test_submit_registers_decoding_and_queues_one_job() -> None:
    service, _, jobs = service_with()
    track_id = service.submit(DATA)
    assert track_id == TrackId.of_content(DATA)
    assert service.status(track_id) == Analysing.at(AnalysisStage.DECODING)
    assert [(job.track_id, job.data) for job in jobs.jobs] == [(track_id, DATA)]


def test_same_file_reuses_the_track_without_a_second_job() -> None:
    service, _, jobs = service_with()
    assert service.submit(DATA) == service.submit(DATA)
    assert len(jobs.jobs) == 1


def test_failed_track_is_analysed_again_on_upload() -> None:
    service, registry, jobs = service_with()
    track_id = service.submit(DATA)
    registry.put(track_id, Failed(code=FailureCode.UNDECODABLE, message="bad"))
    service.submit(DATA)
    assert len(jobs.jobs) == 2
    assert service.status(track_id) == Analysing.at(AnalysisStage.DECODING)


def test_empty_upload_is_rejected() -> None:
    service, _, jobs = service_with()
    with pytest.raises(EmptyUploadError):
        service.submit(b"")
    assert jobs.jobs == []


def test_upload_over_the_limit_is_rejected() -> None:
    service, _, jobs = service_with(max_upload_bytes=4)
    with pytest.raises(FileTooLargeError):
        service.submit(b"12345")
    assert jobs.jobs == []


def test_track_longer_than_the_limit_is_rejected() -> None:
    service, _, jobs = service_with(FakeDecoder(duration_s=MAX_DURATION_S + 1.0))
    with pytest.raises(TrackTooLongError):
        service.submit(DATA)
    assert jobs.jobs == []


def test_unsupported_format_is_rejected_before_registering() -> None:
    decoder = FakeDecoder(probe_error=UnsupportedFormatError("aiff"))
    service, _, jobs = service_with(decoder)
    with pytest.raises(UnsupportedFormatError):
        service.submit(DATA)
    assert jobs.jobs == []
    with pytest.raises(TrackNotFoundError):
        service.status(TrackId.of_content(DATA))
