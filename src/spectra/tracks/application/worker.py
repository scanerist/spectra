import asyncio
import logging
from typing import Final

from spectra.analysis.application.ports import AudioDecoder
from spectra.analysis.domain.errors import (
    AnalysisError,
    UndecodableAudioError,
    UnsupportedFormatError,
)
from spectra.analysis.domain.track_analysis import AnalysisStage, StageListener, analyse_signal
from spectra.tracks.application.ports import AnalysisJob, BlobStore, JobQueue
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.blobs import upload_key
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, Ready, TrackStatus

logger = logging.getLogger(__name__)

SHUT_DOWN: Final = Failed(
    code=FailureCode.INTERNAL, message="the server shut down before analysing the track"
)
UPLOAD_GONE: Final = Failed(code=FailureCode.INTERNAL, message="the upload is no longer stored")

type StageQueue = asyncio.Queue[AnalysisStage | None]


class AnalysisWorker:
    def __init__(
        self, *, decoder: AudioDecoder, board: StatusBoard, blobs: BlobStore, jobs: JobQueue
    ) -> None:
        self._decoder = decoder
        self._board = board
        self._blobs = blobs
        self._jobs = jobs

    async def close(self) -> None:
        for job in await self._jobs.close():
            await self._blobs.delete(upload_key(job.track_id))
            await self._board.record(job.track_id, SHUT_DOWN)

    async def run(self) -> None:
        while (job := await self._jobs.take()) is not None:
            await self._board.record(job.track_id, await self._process(job))
            await self._jobs.done(job)

    async def _process(self, job: AnalysisJob) -> TrackStatus:
        key = upload_key(job.track_id)
        data = await self._blobs.get(key)
        if data is None:
            return UPLOAD_GONE
        try:
            return await self._analyse(job, data)
        finally:
            await self._blobs.delete(key)

    async def _analyse(self, job: AnalysisJob, data: bytes) -> TrackStatus:
        loop = asyncio.get_running_loop()
        stages: StageQueue = asyncio.Queue()

        def report(stage: AnalysisStage) -> None:
            loop.call_soon_threadsafe(stages.put_nowait, stage)

        async with asyncio.TaskGroup() as group:
            outcome = group.create_task(self._analyse_in_thread(job, data, report, stages))
            while (stage := await stages.get()) is not None:
                await self._board.record(job.track_id, Analysing.at(stage))
        return outcome.result()

    async def _analyse_in_thread(
        self, job: AnalysisJob, data: bytes, report: StageListener, stages: StageQueue
    ) -> TrackStatus:
        try:
            return await asyncio.to_thread(self._analyse_blocking, data, report)
        except (UndecodableAudioError, UnsupportedFormatError) as error:
            return Failed(code=FailureCode.UNDECODABLE, message=str(error))
        except AnalysisError as error:
            return Failed(code=FailureCode.ANALYSIS_FAILED, message=str(error))
        except Exception:
            logger.exception("analysis of track %s crashed", job.track_id.value)
            return Failed(code=FailureCode.INTERNAL, message="the analysis crashed")
        finally:
            stages.put_nowait(None)

    def _analyse_blocking(self, data: bytes, report: StageListener) -> Ready:
        signal = self._decoder.decode(data)
        return Ready(analysis=analyse_signal(signal, on_stage=report))
