import asyncio
from dataclasses import replace
from typing import Final

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.gateway.engine import install_engine
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.events import EventStreams, status_event
from spectra.gateway.routes import create_router
from spectra.gateway.slots import SlotLimits, Slots
from spectra.tracks.adapters.memory import InMemoryBlobStore
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, Ready, TrackId, TrackSummary
from tests.contract.timeline_fixture import golden_analysis
from tests.fakes import FakeDecoder, FakeJobQueue, fake_engine, memory_board, record_now
from tests.sse import parse_events

TRACK = TrackId.of_content(b"track")
LIFETIME_S: Final = 0.5
WAIT_S: Final = 5.0


@pytest.fixture
def board() -> StatusBoard:
    return memory_board()


def event_streams(*, total: int, per_address: int) -> EventStreams:
    limits = SlotLimits(
        total=total, per_address=per_address, per_network=per_address, retry_after_s=5.0
    )
    return EventStreams(slots=Slots(limits=limits, name="event streams"), lifetime_s=LIFETIME_S)


def events_app(board: StatusBoard, streams: EventStreams) -> FastAPI:
    service = TrackService(
        decoder=FakeDecoder(),
        board=board,
        blobs=InMemoryBlobStore(),
        jobs=FakeJobQueue(),
        limits=UploadLimits(
            max_upload_bytes=100, max_duration_s=600.0, max_pending=4, max_decoded_samples=10**9
        ),
    )
    app = FastAPI()
    app.include_router(create_router())
    install_error_handlers(app)
    install_engine(app, replace(fake_engine(), track_service=service, event_streams=streams))
    return app


@pytest.fixture
def client(board: StatusBoard) -> TestClient:
    return TestClient(events_app(board, event_streams(total=4, per_address=2)))


def signalling_start(app: ASGIApp, started: asyncio.Event) -> ASGIApp:
    async def signalled(scope: Scope, receive: Receive, send: Send) -> None:
        async def send_and_signal(message: Message) -> None:
            await send(message)
            if message["type"] == "http.response.start":
                started.set()

        await app(scope, receive, send_and_signal)

    return signalled


async def second_stream_while_one_is_open(
    board: StatusBoard, streams: EventStreams
) -> tuple[httpx.Response, httpx.Response]:
    started = asyncio.Event()
    transport = httpx.ASGITransport(app=signalling_start(events_app(board, streams), started))
    url = f"/tracks/{TRACK.value}/events"
    async with httpx.AsyncClient(transport=transport, base_url="http://spectra") as client:
        first = asyncio.create_task(client.get(url))
        async with asyncio.timeout(WAIT_S):
            await started.wait()
        second = await client.get(url)
        return await first, second


def test_progress_event_carries_stage_and_progress() -> None:
    event = status_event(TRACK, Analysing.at(AnalysisStage.TEMPO))
    assert event == 'event: progress\ndata: {"stage":"tempo","progress":0.55}\n\n'


def test_ready_track_streams_one_ready_event_with_its_metadata(
    client: TestClient, board: StatusBoard
) -> None:
    record_now(board, TRACK, Ready(summary=TrackSummary.of_analysis(golden_analysis())))
    response = client.get(f"/tracks/{TRACK.value}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert [event.name for event in events] == ["ready"]
    assert events[0].data == client.get(f"/tracks/{TRACK.value}").json()


def test_failed_track_streams_one_failed_event(client: TestClient, board: StatusBoard) -> None:
    record_now(board, TRACK, Failed(code=FailureCode.UNDECODABLE, message="lost sync"))
    events = parse_events(client.get(f"/tracks/{TRACK.value}/events").text)
    assert [(event.name, event.data) for event in events] == [
        ("failed", {"error": "undecodable", "message": "lost sync"})
    ]


def test_unknown_track_events_are_track_not_found_json(client: TestClient) -> None:
    response = client.get("/tracks/0123456789abcdef/events")
    assert response.status_code == 404
    assert response.json()["error"] == "track_not_found"


def test_a_stream_ends_without_a_verdict_once_its_lifetime_is_over(
    client: TestClient, board: StatusBoard
) -> None:
    record_now(board, TRACK, Analysing.at(AnalysisStage.TEMPO))
    events = parse_events(client.get(f"/tracks/{TRACK.value}/events").text)
    assert [event.name for event in events] == ["progress"]


@pytest.mark.anyio
async def test_a_second_stream_from_the_same_address_is_rate_limited(board: StatusBoard) -> None:
    await board.record(TRACK, Analysing.at(AnalysisStage.TEMPO))
    streams = event_streams(total=4, per_address=1)
    first, second = await second_stream_while_one_is_open(board, streams)
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"
    assert second.headers["Retry-After"] == "5"
    assert first.status_code == 200
    assert streams.slots.held == 0


@pytest.mark.anyio
async def test_a_stream_beyond_the_server_limit_is_busy(board: StatusBoard) -> None:
    await board.record(TRACK, Analysing.at(AnalysisStage.TEMPO))
    streams = event_streams(total=1, per_address=1)
    _, second = await second_stream_while_one_is_open(board, streams)
    assert second.status_code == 503
    assert second.json()["error"] == "busy"
    assert streams.slots.held == 0
