from dataclasses import dataclass
from typing import Final

from spectra.analysis.adapters.soundfile_decoder import SoundfileDecoder
from spectra.bootstrap.hosted import HostedAdapters
from spectra.bootstrap.settings import Settings
from spectra.gateway.timeline_codec import encode_timeline
from spectra.shared.clock import MonotonicClock
from spectra.tracks.adapters.memory import (
    InMemoryBlobStore,
    InMemoryJobQueue,
    InMemoryProgressFeed,
    InMemoryTrackStore,
    InMemoryUploadQuota,
)
from spectra.tracks.adapters.redis_quota import RedisUploadQuota
from spectra.tracks.application.ports import BlobStore, JobQueue, UploadQuota
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.application.worker import AnalysisWorker
from spectra.tracks.domain.quota import UploadQuotaPolicy

HOUR_S: Final = 3_600.0


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackParts:
    board: StatusBoard
    blobs: BlobStore
    jobs: JobQueue
    quota: UploadQuota


def upload_quota_policy(settings: Settings) -> UploadQuotaPolicy:
    return UploadQuotaPolicy(uploads=settings.uploads_per_hour, window_s=HOUR_S)


def memory_quota(settings: Settings) -> InMemoryUploadQuota:
    return InMemoryUploadQuota(policy=upload_quota_policy(settings), clock=MonotonicClock())


def local_parts(settings: Settings) -> TrackParts:
    return TrackParts(
        board=StatusBoard(
            store=InMemoryTrackStore(capacity=settings.max_tracks), feed=InMemoryProgressFeed()
        ),
        blobs=InMemoryBlobStore(),
        jobs=InMemoryJobQueue(),
        quota=memory_quota(settings),
    )


def hosted_parts(adapters: HostedAdapters, settings: Settings) -> TrackParts:
    return TrackParts(
        board=StatusBoard(store=adapters.store, feed=adapters.feed),
        blobs=adapters.blobs,
        jobs=adapters.jobs,
        quota=RedisUploadQuota(client=adapters.redis, policy=upload_quota_policy(settings)),
    )


def track_service(parts: TrackParts, settings: Settings) -> TrackService:
    return TrackService(
        decoder=SoundfileDecoder(),
        board=parts.board,
        blobs=parts.blobs,
        jobs=parts.jobs,
        limits=UploadLimits(
            max_upload_bytes=settings.max_upload_bytes,
            max_duration_s=settings.max_duration_s,
            max_pending=settings.max_pending_analyses,
        ),
    )


def analysis_worker(parts: TrackParts) -> AnalysisWorker:
    return AnalysisWorker(
        decoder=SoundfileDecoder(),
        board=parts.board,
        blobs=parts.blobs,
        jobs=parts.jobs,
        encoder=encode_timeline,
    )
