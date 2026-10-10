from dataclasses import dataclass
from typing import Final

from prometheus_client import CollectorRegistry

from spectra.analysis.adapters.soundfile_decoder import SoundfileDecoder
from spectra.bootstrap.hosted import HostedAdapters
from spectra.bootstrap.settings import Settings
from spectra.gateway.events import EventStreams
from spectra.gateway.slots import SlotLimits, Slots
from spectra.gateway.timeline_codec import encode_timeline
from spectra.gateway.upload_limit import UploadPace
from spectra.shared.clock import MonotonicClock
from spectra.tracks.adapters.memory import (
    InMemoryBlobStore,
    InMemoryJobQueue,
    InMemoryProgressFeed,
    InMemoryTrackStore,
    InMemoryUploadQuota,
)
from spectra.tracks.adapters.prometheus import PrometheusAnalysisObserver
from spectra.tracks.adapters.redis_quota import RedisUploadQuota
from spectra.tracks.application.pipeline import AnalysisPipeline
from spectra.tracks.application.ports import AnalysisObserver, BlobStore, JobQueue, UploadQuota
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.application.worker import AnalysisWorker
from spectra.tracks.domain.quota import UploadQuotaPolicy

HOUR_S: Final = 3_600.0
EVENT_STREAM_RETRY_AFTER_S: Final = 10.0
UPLOAD_RETRY_AFTER_S: Final = 5.0
TIMELINE_RETRY_AFTER_S: Final = 5.0
UPLOADS_PER_NETWORK: Final = 1
TIMELINES_PER_ADDRESS: Final = 2
TIMELINES_PER_NETWORK: Final = 4
UPLOAD_GRACE_S: Final = 30.0
UPLOAD_IDLE_S: Final = 30.0


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackParts:
    board: StatusBoard
    blobs: BlobStore
    jobs: JobQueue
    quota: UploadQuota


def upload_quota_policy(settings: Settings) -> UploadQuotaPolicy:
    return UploadQuotaPolicy(
        per_address=settings.uploads_per_hour,
        per_network=settings.network_uploads_per_hour,
        total=settings.total_uploads_per_hour,
        window_s=HOUR_S,
    )


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
            max_decoded_samples=settings.max_decoded_samples,
        ),
    )


def event_streams(settings: Settings) -> EventStreams:
    limits = SlotLimits(
        total=settings.max_event_streams,
        per_address=settings.max_event_streams_per_address,
        per_network=settings.max_event_streams_per_network,
        retry_after_s=EVENT_STREAM_RETRY_AFTER_S,
    )
    return EventStreams(
        slots=Slots(limits=limits, name="event streams"),
        lifetime_s=settings.event_stream_lifetime_s,
    )


def upload_slots(settings: Settings) -> Slots:
    limits = SlotLimits(
        total=settings.max_concurrent_uploads,
        per_address=UPLOADS_PER_NETWORK,
        per_network=UPLOADS_PER_NETWORK,
        retry_after_s=UPLOAD_RETRY_AFTER_S,
    )
    return Slots(limits=limits, name="uploads")


def timeline_slots(settings: Settings) -> Slots:
    limits = SlotLimits(
        total=settings.max_timeline_downloads,
        per_address=TIMELINES_PER_ADDRESS,
        per_network=TIMELINES_PER_NETWORK,
        retry_after_s=TIMELINE_RETRY_AFTER_S,
    )
    return Slots(limits=limits, name="timelines")


def upload_pace(settings: Settings) -> UploadPace:
    return UploadPace(
        min_bytes_per_s=settings.min_upload_bytes_per_s,
        grace_s=UPLOAD_GRACE_S,
        idle_s=UPLOAD_IDLE_S,
        max_s=settings.max_upload_s,
    )


def analysis_observer(registry: CollectorRegistry) -> AnalysisObserver:
    return PrometheusAnalysisObserver(registry=registry, clock=MonotonicClock())


def analysis_worker(parts: TrackParts, observer: AnalysisObserver) -> AnalysisWorker:
    return AnalysisWorker(
        pipeline=AnalysisPipeline(decoder=SoundfileDecoder(), encoder=encode_timeline),
        board=parts.board,
        blobs=parts.blobs,
        jobs=parts.jobs,
        observer=observer,
    )
