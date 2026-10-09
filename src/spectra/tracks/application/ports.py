from dataclasses import dataclass
from typing import Protocol

from spectra.tracks.domain.track import TrackId


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class AnalysisJob:
    track_id: TrackId
    data: bytes


class JobQueue(Protocol):
    def enqueue(self, job: AnalysisJob) -> None: ...
