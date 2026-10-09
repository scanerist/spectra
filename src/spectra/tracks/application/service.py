from collections.abc import AsyncIterator
from dataclasses import dataclass

from spectra.analysis.application.ports import AudioDecoder
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.ports import AnalysisJob, JobQueue
from spectra.tracks.application.registry import TrackRegistry
from spectra.tracks.domain.errors import (
    AnalysisQueueFullError,
    EmptyUploadError,
    FileTooLargeError,
    TrackTooLongError,
)
from spectra.tracks.domain.track import Analysing, Failed, TrackId, TrackStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadLimits:
    max_upload_bytes: int
    max_duration_s: float
    max_pending: int


class TrackService:
    def __init__(
        self,
        *,
        decoder: AudioDecoder,
        registry: TrackRegistry,
        jobs: JobQueue,
        limits: UploadLimits,
    ) -> None:
        self._decoder = decoder
        self._registry = registry
        self._jobs = jobs
        self._limits = limits

    @property
    def max_upload_bytes(self) -> int:
        return self._limits.max_upload_bytes

    def submit(self, data: bytes) -> TrackId:
        if not data:
            raise EmptyUploadError("the upload is empty")
        if len(data) > self._limits.max_upload_bytes:
            raise FileTooLargeError(
                f"the upload is larger than {self._limits.max_upload_bytes} bytes"
            )
        probe = self._decoder.probe(data)
        if probe.duration_s > self._limits.max_duration_s:
            limit_s = self._limits.max_duration_s
            raise TrackTooLongError(
                f"the track lasts {probe.duration_s:.0f} s, over {limit_s:.0f} s"
            )
        track_id = TrackId.of_content(data)
        known = self._registry.find(track_id)
        if known is not None and not isinstance(known, Failed):
            return track_id
        if self._registry.analysing_count() >= self._limits.max_pending:
            raise AnalysisQueueFullError(f"{self._limits.max_pending} analyses are already queued")
        self._registry.put(track_id, Analysing.at(AnalysisStage.DECODING))
        self._jobs.enqueue(AnalysisJob(track_id=track_id, data=data))
        return track_id

    def status(self, track_id: TrackId) -> TrackStatus:
        return self._registry.status(track_id)

    def watch(self, track_id: TrackId) -> AsyncIterator[TrackStatus]:
        return self._registry.watch(track_id)
