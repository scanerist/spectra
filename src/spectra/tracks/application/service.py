from collections.abc import AsyncIterator

from spectra.analysis.application.ports import AudioDecoder
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.ports import AnalysisJob, JobQueue
from spectra.tracks.application.registry import TrackRegistry
from spectra.tracks.domain.errors import EmptyUploadError, FileTooLargeError
from spectra.tracks.domain.track import Analysing, Failed, TrackId, TrackStatus


class TrackService:
    def __init__(
        self,
        *,
        decoder: AudioDecoder,
        registry: TrackRegistry,
        jobs: JobQueue,
        max_upload_bytes: int,
    ) -> None:
        self._decoder = decoder
        self._registry = registry
        self._jobs = jobs
        self._max_upload_bytes = max_upload_bytes

    @property
    def max_upload_bytes(self) -> int:
        return self._max_upload_bytes

    def submit(self, data: bytes) -> TrackId:
        if not data:
            raise EmptyUploadError("the upload is empty")
        if len(data) > self._max_upload_bytes:
            raise FileTooLargeError(f"the upload is larger than {self._max_upload_bytes} bytes")
        self._decoder.probe(data)
        track_id = TrackId.of_content(data)
        known = self._registry.find(track_id)
        if known is not None and not isinstance(known, Failed):
            return track_id
        self._registry.put(track_id, Analysing.at(AnalysisStage.DECODING))
        self._jobs.enqueue(AnalysisJob(track_id=track_id, data=data))
        return track_id

    def status(self, track_id: TrackId) -> TrackStatus:
        return self._registry.status(track_id)

    def watch(self, track_id: TrackId) -> AsyncIterator[TrackStatus]:
        return self._registry.watch(track_id)
