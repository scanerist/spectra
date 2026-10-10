import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Final

from spectra.analysis.application.ports import AudioDecoder
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.ports import AnalysisJob, BlobStore, JobQueue
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.blobs import timeline_key, upload_key
from spectra.tracks.domain.errors import (
    AnalysisQueueFullError,
    EmptyUploadError,
    FileTooLargeError,
    TrackNotFoundError,
    TrackTooLongError,
)
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, TrackId, TrackStatus

NOT_QUEUED: Final = Failed(code=FailureCode.INTERNAL, message="the analysis could not be queued")


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadLimits:
    max_upload_bytes: int
    max_duration_s: float
    max_pending: int
    max_decoded_samples: int


class TrackService:
    def __init__(
        self,
        *,
        decoder: AudioDecoder,
        board: StatusBoard,
        blobs: BlobStore,
        jobs: JobQueue,
        limits: UploadLimits,
    ) -> None:
        self._decoder = decoder
        self._board = board
        self._blobs = blobs
        self._jobs = jobs
        self._limits = limits

    @property
    def max_upload_bytes(self) -> int:
        return self._limits.max_upload_bytes

    async def submit(self, data: bytes) -> TrackId:
        if not data:
            raise EmptyUploadError("the upload is empty")
        if len(data) > self._limits.max_upload_bytes:
            raise FileTooLargeError(
                f"the upload is larger than {self._limits.max_upload_bytes} bytes"
            )
        track_id = await asyncio.to_thread(self._inspect, data)
        known = await self._board.find(track_id)
        if known is not None and not isinstance(known, Failed):
            return track_id
        if await self._board.analysing_count() >= self._limits.max_pending:
            raise AnalysisQueueFullError(f"{self._limits.max_pending} analyses are already queued")
        await self._blobs.put(upload_key(track_id), data)
        await self._board.record(track_id, Analysing.at(AnalysisStage.DECODING))
        try:
            await self._jobs.enqueue(AnalysisJob(track_id=track_id))
        except Exception:
            await self._board.record(track_id, NOT_QUEUED)
            await self._blobs.delete(upload_key(track_id))
            raise
        return track_id

    def _inspect(self, data: bytes) -> TrackId:
        probe = self._decoder.probe(data)
        if probe.duration_s > self._limits.max_duration_s:
            limit_s = self._limits.max_duration_s
            raise TrackTooLongError(
                f"the track lasts {probe.duration_s:.0f} s, over {limit_s:.0f} s"
            )
        decoded_samples = probe.duration_s * probe.sample_rate_hz * probe.channel_count
        if decoded_samples > self._limits.max_decoded_samples:
            limit = self._limits.max_decoded_samples
            raise TrackTooLongError(
                f"the track decodes to {decoded_samples:.0f} samples, over {limit}"
            )
        return TrackId.of_content(data)

    async def status(self, track_id: TrackId) -> TrackStatus:
        return await self._board.current(track_id)

    async def timeline(self, track_id: TrackId) -> bytes:
        timeline = await self._blobs.get(timeline_key(track_id))
        if timeline is None:
            await self._board.forget(track_id)
            raise TrackNotFoundError(f"the timeline of track {track_id.value} is gone")
        return timeline

    def watch(self, track_id: TrackId) -> AsyncIterator[TrackStatus]:
        return self._board.watch(track_id)
