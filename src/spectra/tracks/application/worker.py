import asyncio
import logging
from typing import Final

from spectra.analysis.domain.errors import (
    AnalysisError,
    UndecodableAudioError,
    UnsupportedFormatError,
)
from spectra.analysis.domain.track_analysis import AnalysisStage, StageListener
from spectra.tracks.application.pipeline import AnalysisPipeline
from spectra.tracks.application.ports import AnalysisJob, AnalysisObserver, BlobStore, JobQueue
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.blobs import timeline_key, upload_key
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    Ready,
    TrackId,
    TrackStatus,
    TrackSummary,
    is_final,
    outcome_name,
)

logger = logging.getLogger(__name__)

SHUT_DOWN: Final = Failed(
    code=FailureCode.INTERNAL, message="the server shut down before analysing the track"
)
UPLOAD_GONE: Final = Failed(code=FailureCode.INTERNAL, message="the upload is no longer stored")
KEEPS_CRASHING: Final = Failed(
    code=FailureCode.INTERNAL, message="the analysis kept stopping the worker"
)
MAX_ATTEMPTS: Final = 3

type StageQueue = asyncio.Queue[AnalysisStage | None]
type Outcome = tuple[TrackSummary, bytes] | Failed


class AnalysisWorker:
    def __init__(
        self,
        *,
        pipeline: AnalysisPipeline,
        board: StatusBoard,
        blobs: BlobStore,
        jobs: JobQueue,
        observer: AnalysisObserver,
    ) -> None:
        self._pipeline = pipeline
        self._observer = observer
        self._board = board
        self._blobs = blobs
        self._jobs = jobs

    async def close(self) -> None:
        for job in await self._jobs.close():
            await self._blobs.delete(upload_key(job.track_id))
            await self._board.record(job.track_id, SHUT_DOWN)

    async def run(self) -> None:
        while (job := await self._jobs.take()) is not None:
            if await self._is_pending(job.track_id):
                self._observer.started(job.track_id)
                outcome = KEEPS_CRASHING if job.attempt > MAX_ATTEMPTS else await self._process(job)
                await self._board.record(job.track_id, outcome)
                self._observer.finished(job.track_id, outcome)
                logger.info(
                    "track %s settled as %s",
                    job.track_id.value,
                    outcome_name(outcome),
                    extra={"track_id": job.track_id.value, "outcome": outcome_name(outcome)},
                )
                await self._evict(keep=job.track_id)
            await self._blobs.delete(upload_key(job.track_id))
            await self._jobs.done(job)

    async def _is_pending(self, track_id: TrackId) -> bool:
        status = await self._board.find(track_id)
        return status is not None and not is_final(status)

    async def _evict(self, *, keep: TrackId) -> None:
        for track_id in await self._board.evict_settled(keep=keep):
            await self._blobs.delete(timeline_key(track_id))

    async def _process(self, job: AnalysisJob) -> TrackStatus:
        data = await self._blobs.get(upload_key(job.track_id))
        if data is None:
            return UPLOAD_GONE
        outcome = await self._analyse(job, data)
        if isinstance(outcome, Failed):
            return outcome
        summary, timeline = outcome
        await self._blobs.put(timeline_key(job.track_id), timeline)
        return Ready(summary=summary)

    async def _analyse(self, job: AnalysisJob, data: bytes) -> Outcome:
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
    ) -> Outcome:
        try:
            return await asyncio.to_thread(self._pipeline.run, data, report)
        except (UndecodableAudioError, UnsupportedFormatError) as error:
            return Failed(code=FailureCode.UNDECODABLE, message=str(error))
        except AnalysisError as error:
            return Failed(code=FailureCode.ANALYSIS_FAILED, message=str(error))
        except Exception:
            logger.exception("analysis of track %s crashed", job.track_id.value)
            return Failed(code=FailureCode.INTERNAL, message="the analysis crashed")
        finally:
            stages.put_nowait(None)
