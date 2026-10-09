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
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, Ready, TrackStatus

logger = logging.getLogger(__name__)

SHUT_DOWN: Final = Failed(
    code=FailureCode.INTERNAL, message="the server shut down before analysing the track"
)

type StageQueue = asyncio.Queue[AnalysisStage | None]


class AnalysisWorker:
    def __init__(self, *, decoder: AudioDecoder, board: StatusBoard) -> None:
        self._decoder = decoder
        self._board = board
        self._jobs: asyncio.Queue[AnalysisJob | None] = asyncio.Queue()

    def enqueue(self, job: AnalysisJob) -> None:
        self._jobs.put_nowait(job)

    async def close(self) -> None:
        while not self._jobs.empty():
            job = self._jobs.get_nowait()
            if job is not None:
                await self._board.record(job.track_id, SHUT_DOWN)
        self._jobs.put_nowait(None)

    async def run(self) -> None:
        while (job := await self._jobs.get()) is not None:
            await self._board.record(job.track_id, await self._analyse(job))

    async def _analyse(self, job: AnalysisJob) -> TrackStatus:
        loop = asyncio.get_running_loop()
        stages: StageQueue = asyncio.Queue()

        def report(stage: AnalysisStage) -> None:
            loop.call_soon_threadsafe(stages.put_nowait, stage)

        async with asyncio.TaskGroup() as group:
            outcome = group.create_task(self._analyse_in_thread(job, report, stages))
            while (stage := await stages.get()) is not None:
                await self._board.record(job.track_id, Analysing.at(stage))
        return outcome.result()

    async def _analyse_in_thread(
        self, job: AnalysisJob, report: StageListener, stages: StageQueue
    ) -> TrackStatus:
        try:
            return await asyncio.to_thread(self._analyse_blocking, job, report)
        except (UndecodableAudioError, UnsupportedFormatError) as error:
            return Failed(code=FailureCode.UNDECODABLE, message=str(error))
        except AnalysisError as error:
            return Failed(code=FailureCode.ANALYSIS_FAILED, message=str(error))
        except Exception:
            logger.exception("analysis of track %s crashed", job.track_id.value)
            return Failed(code=FailureCode.INTERNAL, message="the analysis crashed")
        finally:
            stages.put_nowait(None)

    def _analyse_blocking(self, job: AnalysisJob, report: StageListener) -> Ready:
        signal = self._decoder.decode(job.data)
        return Ready(analysis=analyse_signal(signal, on_stage=report))
