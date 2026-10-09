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
from spectra.tracks.application.registry import TrackRegistry
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, Ready, TrackStatus

logger = logging.getLogger(__name__)

SHUT_DOWN: Final = Failed(
    code=FailureCode.INTERNAL, message="the server shut down before analysing the track"
)


class AnalysisWorker:
    def __init__(self, *, decoder: AudioDecoder, registry: TrackRegistry) -> None:
        self._decoder = decoder
        self._registry = registry
        self._jobs: asyncio.Queue[AnalysisJob | None] = asyncio.Queue()

    def enqueue(self, job: AnalysisJob) -> None:
        self._jobs.put_nowait(job)

    def close(self) -> None:
        while not self._jobs.empty():
            job = self._jobs.get_nowait()
            if job is not None:
                self._registry.put(job.track_id, SHUT_DOWN)
        self._jobs.put_nowait(None)

    async def run(self) -> None:
        while (job := await self._jobs.get()) is not None:
            self._registry.put(job.track_id, await self._analyse(job))

    async def _analyse(self, job: AnalysisJob) -> TrackStatus:
        loop = asyncio.get_running_loop()

        def report(stage: AnalysisStage) -> None:
            loop.call_soon_threadsafe(self._registry.put, job.track_id, Analysing.at(stage))

        try:
            return await asyncio.to_thread(self._analyse_blocking, job, report)
        except (UndecodableAudioError, UnsupportedFormatError) as error:
            return Failed(code=FailureCode.UNDECODABLE, message=str(error))
        except AnalysisError as error:
            return Failed(code=FailureCode.ANALYSIS_FAILED, message=str(error))
        except Exception:
            logger.exception("analysis of track %s crashed", job.track_id.value)
            return Failed(code=FailureCode.INTERNAL, message="the analysis crashed")

    def _analyse_blocking(self, job: AnalysisJob, report: StageListener) -> Ready:
        signal = self._decoder.decode(job.data)
        return Ready(analysis=analyse_signal(signal, on_stage=report))
