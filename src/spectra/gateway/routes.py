import ipaddress
from collections.abc import Callable
from typing import Annotated, Final, Literal, override

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.requests import HTTPConnection
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.types import Receive, Scope, Send

from spectra.gateway.errors import (
    FAILURE_CODES,
    ApiError,
    ErrorCode,
    GatewayNotConfiguredError,
)
from spectra.gateway.events import (
    EVENT_STREAM_HEADERS,
    EVENT_STREAM_MEDIA_TYPE,
    EventStreams,
    holding,
    status_events,
    until_deadline,
)
from spectra.gateway.protocol import PROTOCOL_VERSION
from spectra.gateway.readiness import Readiness, readiness
from spectra.gateway.schemas import TrackCreated, TrackInfo, track_info
from spectra.gateway.slots import Slot, Slots
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.application.service import TrackService
from spectra.tracks.domain.errors import (
    AnalysisQueueFullError,
    EmptyUploadError,
    FileTooLargeError,
)
from spectra.tracks.domain.quota import UploadSource
from spectra.tracks.domain.track import Analysing, Failed, Ready, TrackId, TrackSummary

TRACK_SERVICE_STATE: Final = "track_service"
UPLOAD_ADMISSION_STATE: Final = "upload_admission"
EVENT_STREAMS_STATE: Final = "event_streams"
UPLOAD_SLOTS_STATE: Final = "upload_slots"
TIMELINE_SLOTS_STATE: Final = "timeline_slots"
TIMELINE_CACHE_CONTROL: Final = "private, max-age=3600"
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


def install_track_service(app: FastAPI, service: TrackService) -> None:
    setattr(app.state, TRACK_SERVICE_STATE, service)


def track_service(connection: HTTPConnection) -> TrackService:
    service = getattr(connection.app.state, TRACK_SERVICE_STATE, None)
    if not isinstance(service, TrackService):
        raise GatewayNotConfiguredError("the track service is not installed on the app")
    return service


def install_upload_admission(app: FastAPI, admission: UploadAdmission) -> None:
    setattr(app.state, UPLOAD_ADMISSION_STATE, admission)


def upload_admission(connection: HTTPConnection) -> UploadAdmission:
    admission = getattr(connection.app.state, UPLOAD_ADMISSION_STATE, None)
    if not isinstance(admission, UploadAdmission):
        raise GatewayNotConfiguredError("the upload admission is not installed on the app")
    return admission


def install_event_streams(app: FastAPI, streams: EventStreams) -> None:
    setattr(app.state, EVENT_STREAMS_STATE, streams)


def event_streams(connection: HTTPConnection) -> EventStreams:
    streams = getattr(connection.app.state, EVENT_STREAMS_STATE, None)
    if not isinstance(streams, EventStreams):
        raise GatewayNotConfiguredError("the event streams are not installed on the app")
    return streams


def install_upload_slots(app: FastAPI, slots: Slots) -> None:
    setattr(app.state, UPLOAD_SLOTS_STATE, slots)


def install_timeline_slots(app: FastAPI, slots: Slots) -> None:
    setattr(app.state, TIMELINE_SLOTS_STATE, slots)


def installed_slots(state: str) -> Callable[[HTTPConnection], Slots]:
    def slots(connection: HTTPConnection) -> Slots:
        found = getattr(connection.app.state, state, None)
        if not isinstance(found, Slots):
            raise GatewayNotConfiguredError(f"the {state} are not installed on the app")
        return found

    return slots


type Service = Annotated[TrackService, Depends(track_service)]
type Admission = Annotated[UploadAdmission, Depends(upload_admission)]
type Probes = Annotated[Readiness, Depends(readiness)]
type Streams = Annotated[EventStreams, Depends(event_streams)]
type UploadSlots = Annotated[Slots, Depends(installed_slots(UPLOAD_SLOTS_STATE))]
type TimelineSlots = Annotated[Slots, Depends(installed_slots(TIMELINE_SLOTS_STATE))]


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


class HeldResponse(Response):
    def __init__(
        self, slot: Slot, *, content: bytes, media_type: str, headers: dict[str, str]
    ) -> None:
        super().__init__(content=content, media_type=media_type, headers=headers)
        self._slot = slot

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._slot.release()


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
        return HeldResponse(
            slot,
            content=timeline,
            media_type=TIMELINE_MEDIA_TYPE,
            headers={"Cache-Control": TIMELINE_CACHE_CONTROL},
        )

    return router
