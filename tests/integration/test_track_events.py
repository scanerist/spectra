import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.events import status_event
from spectra.gateway.routes import create_router, install_track_service
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, Ready, TrackId
from tests.contract.timeline_fixture import golden_analysis
from tests.fakes import FakeDecoder, FakeJobQueue, memory_board, record_now
from tests.sse import parse_events

TRACK = TrackId.of_content(b"track")


@pytest.fixture
def board() -> StatusBoard:
    return memory_board()


@pytest.fixture
def client(board: StatusBoard) -> TestClient:
    service = TrackService(
        decoder=FakeDecoder(),
        board=board,
        jobs=FakeJobQueue(),
        limits=UploadLimits(max_upload_bytes=100, max_duration_s=600.0, max_pending=4),
    )
    app = FastAPI()
    app.include_router(create_router())
    install_error_handlers(app)
    install_track_service(app, service)
    return TestClient(app)


def test_progress_event_carries_stage_and_progress() -> None:
    event = status_event(TRACK, Analysing.at(AnalysisStage.TEMPO))
    assert event == 'event: progress\ndata: {"stage":"tempo","progress":0.55}\n\n'


def test_ready_track_streams_one_ready_event_with_its_metadata(
    client: TestClient, board: StatusBoard
) -> None:
    record_now(board, TRACK, Ready(analysis=golden_analysis()))
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
