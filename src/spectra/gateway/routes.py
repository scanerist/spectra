import ipaddress
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from spectra.gateway.engine import EngineState, installed_engine
from spectra.gateway.errors import FAILURE_CODES, ApiError, ErrorCode
from spectra.gateway.events import (
    EVENT_STREAM_HEADERS,
    EVENT_STREAM_MEDIA_TYPE,
    EventStreams,
    holding,
    status_events,
    until_deadline,
)
from spectra.gateway.held_response import HeldStreamingResponse
from spectra.gateway.protocol import PROTOCOL_VERSION
from spectra.gateway.readiness import Readiness
from spectra.gateway.schemas import TrackCreated, TrackInfo, track_info
from spectra.gateway.slots import Slots
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.application.service import TrackService
from spectra.tracks.domain.errors import (
    AnalysisQueueFullError,
    EmptyUploadError,
    FileTooLargeError,
)
from spectra.tracks.domain.quota import UploadSource
from spectra.tracks.domain.track import Analysing, Failed, Ready, TrackId, TrackSummary

TIMELINE_CACHE_CONTROL: Final = "private, max-age=3600"
TIMELINE_SEND_DEADLINE_S: Final = 300.0
TIMELINE_MEDIA_TYPE: Final = "application/octet-stream"
UNKNOWN_CLIENT: Final = "unknown"
IPV6_CLIENT_PREFIX: Final = 64
IPV6_NETWORK_PREFIX: Final = 48

type PeerAddress = ipaddress.IPv4Address | ipaddress.IPv6Address | str


class HealthReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: Literal[True] = True
    protocol: int = PROTOCOL_VERSION


class ReadinessReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: Literal[True] = True


type Engine = Annotated[EngineState, Depends(installed_engine)]


def track_service(engine: Engine) -> TrackService:
    return engine.track_service


def upload_admission(engine: Engine) -> UploadAdmission:
    return engine.upload_admission


def event_streams(engine: Engine) -> EventStreams:
    return engine.event_streams


def upload_slots(engine: Engine) -> Slots:
    return engine.upload_slots


def timeline_slots(engine: Engine) -> Slots:
    return engine.timeline_slots


def readiness(engine: Engine) -> Readiness:
    return engine.readiness


type Service = Annotated[TrackService, Depends(track_service)]
type Admission = Annotated[UploadAdmission, Depends(upload_admission)]
type Probes = Annotated[Readiness, Depends(readiness)]
type Streams = Annotated[EventStreams, Depends(event_streams)]
type UploadSlots = Annotated[Slots, Depends(upload_slots)]
type TimelineSlots = Annotated[Slots, Depends(timeline_slots)]


def peer_address(request: Request) -> PeerAddress:
    if request.client is None:
        return UNKNOWN_CLIENT
    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return request.client.host
    match address:
        case ipaddress.IPv6Address(ipv4_mapped=ipaddress.IPv4Address() as ipv4):
            return ipv4
    return address


def network_of(address: ipaddress.IPv6Address, prefix: int) -> str:
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def upload_source(request: Request) -> UploadSource:
    match peer_address(request):
        case ipaddress.IPv6Address() as ipv6:
            return UploadSource(
                address=network_of(ipv6, IPV6_CLIENT_PREFIX),
                network=network_of(ipv6, IPV6_NETWORK_PREFIX),
            )
        case peer:
            return UploadSource(address=str(peer), network=str(peer))


async def read_upload(upload: UploadFile | None, *, limit: int) -> bytes:
    if upload is None:
        raise EmptyUploadError("the request has no file part")
    if upload.size is not None and upload.size > limit:
        raise FileTooLargeError(f"the upload is larger than {limit} bytes")
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise FileTooLargeError(f"the upload is larger than {limit} bytes")
    return data


async def ready_summary(service: TrackService, track_id: str) -> tuple[TrackId, TrackSummary]:
    track = TrackId(track_id)
    match await service.status(track):
        case Ready(summary=summary):
            return track, summary
        case Analysing():
            raise ApiError(ErrorCode.NOT_READY, "the analysis of this track is still running")
        case Failed(code=code, message=message):
            raise ApiError(FAILURE_CODES[code], message)


async def accept_upload(
    request: Request, service: TrackService, admission: UploadAdmission
) -> TrackCreated:
    source = upload_source(request)
    await admission.admit(source)
    async with request.form(max_files=1, max_fields=0) as form:
        upload = form.get("file")
        data = await read_upload(
            upload if isinstance(upload, UploadFile) else None,
            limit=service.max_upload_bytes,
        )
    try:
        track_id = await service.submit(data)
    except AnalysisQueueFullError:
        await admission.refund(source)
        raise
    return TrackCreated(track_id=track_id.value)


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> HealthReport:
        return HealthReport()

    @router.get("/ready")
    async def ready(probes: Probes) -> ReadinessReport:
        if silent := await probes.silent():
            raise ApiError(ErrorCode.UNAVAILABLE, f"not responding: {', '.join(silent)}")
        return ReadinessReport()

    @router.post("/tracks", status_code=status.HTTP_202_ACCEPTED)
    async def upload_track(
        request: Request, service: Service, admission: Admission, uploads: UploadSlots
    ) -> TrackCreated:
        slot = uploads.take(upload_source(request))
        try:
            return await accept_upload(request, service, admission)
        finally:
            slot.release()

    @router.get("/tracks/{track_id}")
    async def get_track(track_id: str, service: Service) -> TrackInfo:
        track, summary = await ready_summary(service, track_id)
        return track_info(track, summary)

    @router.get("/tracks/{track_id}/events")
    async def track_events(
        track_id: str, request: Request, service: Service, streams: Streams
    ) -> StreamingResponse:
        track = TrackId(track_id)
        await service.status(track)
        slot = streams.slots.take(upload_source(request))
        statuses = until_deadline(service.watch(track), lifetime_s=streams.lifetime_s)
        return StreamingResponse(
            holding(slot, status_events(track, statuses)),
            media_type=EVENT_STREAM_MEDIA_TYPE,
            headers=dict(EVENT_STREAM_HEADERS),
            background=BackgroundTask(slot.release),
        )

    @router.get("/tracks/{track_id}/timeline")
    async def get_timeline(
        track_id: str, request: Request, service: Service, timelines: TimelineSlots
    ) -> Response:
        track, _ = await ready_summary(service, track_id)
        slot = timelines.take(upload_source(request))
        try:
            timeline = await service.timeline(track)
        except BaseException:
            slot.release()
            raise
        return HeldStreamingResponse(
            slot,
            content=timeline,
            media_type=TIMELINE_MEDIA_TYPE,
            headers={"Cache-Control": TIMELINE_CACHE_CONTROL},
            deadline_s=TIMELINE_SEND_DEADLINE_S,
        )

    return router
