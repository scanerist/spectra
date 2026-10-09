import ipaddress
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.requests import HTTPConnection
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import UploadFile

from spectra.gateway.errors import (
    FAILURE_CODES,
    ApiError,
    ErrorCode,
    GatewayNotConfiguredError,
)
from spectra.gateway.events import EVENT_STREAM_HEADERS, EVENT_STREAM_MEDIA_TYPE, status_events
from spectra.gateway.protocol import PROTOCOL_VERSION
from spectra.gateway.readiness import Readiness, readiness
from spectra.gateway.schemas import TrackCreated, TrackInfo, track_info
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.application.service import TrackService
from spectra.tracks.domain.errors import (
    AnalysisQueueFullError,
    EmptyUploadError,
    FileTooLargeError,
)
from spectra.tracks.domain.track import Analysing, Failed, Ready, TrackId, TrackSummary

TRACK_SERVICE_STATE: Final = "track_service"
UPLOAD_ADMISSION_STATE: Final = "upload_admission"
UPLOAD_CHUNK_BYTES: Final = 1 << 20
TIMELINE_MEDIA_TYPE: Final = "application/octet-stream"
UNKNOWN_CLIENT: Final = "unknown"
IPV6_CLIENT_PREFIX: Final = 64


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


type Service = Annotated[TrackService, Depends(track_service)]
type Admission = Annotated[UploadAdmission, Depends(upload_admission)]
type Probes = Annotated[Readiness, Depends(readiness)]


def client_address(request: Request) -> str:
    if request.client is None:
        return UNKNOWN_CLIENT
    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return request.client.host
    match address:
        case ipaddress.IPv6Address(ipv4_mapped=ipaddress.IPv4Address() as ipv4):
            return str(ipv4)
        case ipaddress.IPv6Address():
            return str(ipaddress.ip_network(f"{address}/{IPV6_CLIENT_PREFIX}", strict=False))
    return str(address)


async def read_upload(upload: UploadFile | None, *, limit: int) -> bytes:
    if upload is None:
        raise EmptyUploadError("the request has no file part")
    chunks: list[bytes] = []
    received = 0
    while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
        received += len(chunk)
        if received > limit:
            raise FileTooLargeError(f"the upload is larger than {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def ready_summary(service: TrackService, track_id: str) -> tuple[TrackId, TrackSummary]:
    track = TrackId(track_id)
    match await service.status(track):
        case Ready(summary=summary):
            return track, summary
        case Analysing():
            raise ApiError(ErrorCode.NOT_READY, "the analysis of this track is still running")
        case Failed(code=code, message=message):
            raise ApiError(FAILURE_CODES[code], message)


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
        request: Request, service: Service, admission: Admission
    ) -> TrackCreated:
        client = client_address(request)
        await admission.admit(client)
        async with request.form(max_files=1, max_fields=0) as form:
            upload = form.get("file")
            data = await read_upload(
                upload if isinstance(upload, UploadFile) else None,
                limit=service.max_upload_bytes,
            )
        try:
            track_id = await service.submit(data)
        except AnalysisQueueFullError:
            await admission.refund(client)
            raise
        return TrackCreated(track_id=track_id.value)

    @router.get("/tracks/{track_id}")
    async def get_track(track_id: str, service: Service) -> TrackInfo:
        track, summary = await ready_summary(service, track_id)
        return track_info(track, summary)

    @router.get("/tracks/{track_id}/events")
    async def track_events(track_id: str, service: Service) -> StreamingResponse:
        track = TrackId(track_id)
        await service.status(track)
        return StreamingResponse(
            status_events(track, service.watch(track)),
            media_type=EVENT_STREAM_MEDIA_TYPE,
            headers=dict(EVENT_STREAM_HEADERS),
        )

    @router.get("/tracks/{track_id}/timeline")
    async def get_timeline(track_id: str, service: Service) -> Response:
        track, _ = await ready_summary(service, track_id)
        return Response(content=await service.timeline(track), media_type=TIMELINE_MEDIA_TYPE)

    return router
