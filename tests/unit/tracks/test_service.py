import pytest

from spectra.analysis.domain.errors import UnsupportedFormatError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.adapters.memory import InMemoryBlobStore
from spectra.tracks.application.service import NOT_QUEUED, TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.blobs import upload_key
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
    decoder: FakeDecoder | None = None,
    *,
    max_upload_bytes: int = 1_000,
    jobs: FakeJobQueue | None = None,
) -> tuple[TrackService, StatusBoard, FakeJobQueue, InMemoryBlobStore]:
    board = memory_board()
    jobs = jobs or FakeJobQueue()
    blobs = InMemoryBlobStore()
    service = TrackService(
        decoder=decoder or FakeDecoder(),
        board=board,
        blobs=blobs,
        jobs=jobs,
        limits=UploadLimits(
            max_upload_bytes=max_upload_bytes,
            max_duration_s=MAX_DURATION_S,
            max_pending=MAX_PENDING,
        ),
    )
    return service, board, jobs, blobs


@pytest.mark.anyio
async def test_submit_registers_decoding_and_queues_one_job() -> None:
    service, _, jobs, blobs = service_with()
    track_id = await service.submit(DATA)
    assert track_id == TrackId.of_content(DATA)
    assert await service.status(track_id) == Analysing.at(AnalysisStage.DECODING)
    assert [job.track_id for job in jobs.jobs] == [track_id]
    assert await blobs.get(upload_key(track_id)) == DATA


@pytest.mark.anyio
async def test_same_file_reuses_the_track_without_a_second_job() -> None:
    service, _, jobs, _ = service_with()
    assert await service.submit(DATA) == await service.submit(DATA)
    assert len(jobs.jobs) == 1


@pytest.mark.anyio
async def test_failed_track_is_analysed_again_on_upload() -> None:
    service, board, jobs, _ = service_with()
    track_id = await service.submit(DATA)
    await board.record(track_id, Failed(code=FailureCode.UNDECODABLE, message="bad"))
    await service.submit(DATA)
    assert len(jobs.jobs) == 2
    assert await service.status(track_id) == Analysing.at(AnalysisStage.DECODING)


@pytest.mark.anyio
async def test_empty_upload_is_rejected() -> None:
    service, _, jobs, blobs = service_with()
    with pytest.raises(EmptyUploadError):
        await service.submit(b"")
    assert jobs.jobs == []
    assert await blobs.get(upload_key(TrackId.of_content(b""))) is None


@pytest.mark.anyio
async def test_upload_over_the_limit_is_rejected() -> None:
    service, _, jobs, _ = service_with(max_upload_bytes=4)
    with pytest.raises(FileTooLargeError):
        await service.submit(b"12345")
    assert jobs.jobs == []


@pytest.mark.anyio
async def test_upload_is_refused_while_the_queue_is_full() -> None:
    service, _, jobs, _ = service_with()
    await service.submit(b"first")
    await service.submit(b"second")
    with pytest.raises(AnalysisQueueFullError):
        await service.submit(b"third")
    assert len(jobs.jobs) == MAX_PENDING
    assert await service.submit(b"first") == TrackId.of_content(b"first")


@pytest.mark.anyio
async def test_track_longer_than_the_limit_is_rejected() -> None:
    service, _, jobs, _ = service_with(FakeDecoder(duration_s=MAX_DURATION_S + 1.0))
    with pytest.raises(TrackTooLongError):
        await service.submit(DATA)
    assert jobs.jobs == []


@pytest.mark.anyio
async def test_unsupported_format_is_rejected_before_registering() -> None:
    decoder = FakeDecoder(probe_error=UnsupportedFormatError("aiff"))
    service, _, jobs, blobs = service_with(decoder)
    with pytest.raises(UnsupportedFormatError):
        await service.submit(DATA)
    assert jobs.jobs == []
    assert await blobs.get(upload_key(TrackId.of_content(DATA))) is None
    with pytest.raises(TrackNotFoundError):
        await service.status(TrackId.of_content(DATA))


@pytest.mark.anyio
async def test_a_track_whose_job_was_not_queued_fails_and_can_be_retried() -> None:
    refusing = FakeJobQueue(enqueue_error=ConnectionError("redis went away"))
    service, _, jobs, blobs = service_with(jobs=refusing)
    with pytest.raises(ConnectionError):
        await service.submit(DATA)
    track_id = TrackId.of_content(DATA)
    assert await service.status(track_id) == NOT_QUEUED
    assert await blobs.get(upload_key(track_id)) is None
    jobs.enqueue_error = None
    assert await service.submit(DATA) == track_id
    assert [job.track_id for job in jobs.jobs] == [track_id]
