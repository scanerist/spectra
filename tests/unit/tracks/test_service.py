import pytest

from spectra.analysis.domain.errors import UnsupportedFormatError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.errors import (
    AnalysisQueueFullError,
    EmptyUploadError,
    FileTooLargeError,
    TrackNotFoundError,
    TrackTooLongError,
)
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, TrackId
from tests.fakes import FakeDecoder, FakeJobQueue, memory_board

DATA = b"RIFF fake wav bytes"
MAX_DURATION_S = 600.0
MAX_PENDING = 2


def service_with(
    decoder: FakeDecoder | None = None, *, max_upload_bytes: int = 1_000
) -> tuple[TrackService, StatusBoard, FakeJobQueue]:
    board = memory_board()
    jobs = FakeJobQueue()
    service = TrackService(
        decoder=decoder or FakeDecoder(),
        board=board,
        jobs=jobs,
        limits=UploadLimits(
            max_upload_bytes=max_upload_bytes,
            max_duration_s=MAX_DURATION_S,
            max_pending=MAX_PENDING,
        ),
    )
    return service, board, jobs


@pytest.mark.anyio
async def test_submit_registers_decoding_and_queues_one_job() -> None:
    service, _, jobs = service_with()
    track_id = await service.submit(DATA)
    assert track_id == TrackId.of_content(DATA)
    assert await service.status(track_id) == Analysing.at(AnalysisStage.DECODING)
    assert [(job.track_id, job.data) for job in jobs.jobs] == [(track_id, DATA)]


@pytest.mark.anyio
async def test_same_file_reuses_the_track_without_a_second_job() -> None:
    service, _, jobs = service_with()
    assert await service.submit(DATA) == await service.submit(DATA)
    assert len(jobs.jobs) == 1


@pytest.mark.anyio
async def test_failed_track_is_analysed_again_on_upload() -> None:
    service, board, jobs = service_with()
    track_id = await service.submit(DATA)
    await board.record(track_id, Failed(code=FailureCode.UNDECODABLE, message="bad"))
    await service.submit(DATA)
    assert len(jobs.jobs) == 2
    assert await service.status(track_id) == Analysing.at(AnalysisStage.DECODING)


@pytest.mark.anyio
async def test_empty_upload_is_rejected() -> None:
    service, _, jobs = service_with()
    with pytest.raises(EmptyUploadError):
        await service.submit(b"")
    assert jobs.jobs == []


@pytest.mark.anyio
async def test_upload_over_the_limit_is_rejected() -> None:
    service, _, jobs = service_with(max_upload_bytes=4)
    with pytest.raises(FileTooLargeError):
        await service.submit(b"12345")
    assert jobs.jobs == []


@pytest.mark.anyio
async def test_upload_is_refused_while_the_queue_is_full() -> None:
    service, _, jobs = service_with()
    await service.submit(b"first")
    await service.submit(b"second")
    with pytest.raises(AnalysisQueueFullError):
        await service.submit(b"third")
    assert len(jobs.jobs) == MAX_PENDING
    assert await service.submit(b"first") == TrackId.of_content(b"first")


@pytest.mark.anyio
async def test_track_longer_than_the_limit_is_rejected() -> None:
    service, _, jobs = service_with(FakeDecoder(duration_s=MAX_DURATION_S + 1.0))
    with pytest.raises(TrackTooLongError):
        await service.submit(DATA)
    assert jobs.jobs == []


@pytest.mark.anyio
async def test_unsupported_format_is_rejected_before_registering() -> None:
    decoder = FakeDecoder(probe_error=UnsupportedFormatError("aiff"))
    service, _, jobs = service_with(decoder)
    with pytest.raises(UnsupportedFormatError):
        await service.submit(DATA)
    assert jobs.jobs == []
    with pytest.raises(TrackNotFoundError):
        await service.status(TrackId.of_content(DATA))
