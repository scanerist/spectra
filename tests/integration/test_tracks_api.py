from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.analysis.domain.errors import UnsupportedFormatError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.routes import create_router, install_track_service
from spectra.gateway.timeline_codec import encode_timeline
from spectra.gateway.upload_limit import MULTIPART_OVERHEAD_BYTES, install_upload_limit
from spectra.tracks.adapters.memory import InMemoryBlobStore
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, Ready, TrackId
from tests.contract.timeline_fixture import golden_analysis
from tests.fakes import FakeDecoder, FakeJobQueue, memory_board, record_now

DATA: Final = b"RIFF pretend this is audio"
LIMIT_BYTES: Final = 1_000


class Api:
    def __init__(self, *, decoder: FakeDecoder | None = None) -> None:
        self.board = memory_board()
        self.jobs = FakeJobQueue()
        service = TrackService(
            decoder=decoder or FakeDecoder(),
            board=self.board,
            blobs=InMemoryBlobStore(),
            jobs=self.jobs,
            limits=UploadLimits(max_upload_bytes=LIMIT_BYTES, max_duration_s=600.0, max_pending=1),
        )
        app = FastAPI()
        app.include_router(create_router())
        install_error_handlers(app)
        install_track_service(app, service)
        install_upload_limit(app, max_upload_bytes=LIMIT_BYTES)
        self.client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api() -> Api:
    return Api()


def test_upload_answers_202_with_the_track_id(api: Api) -> None:
    response = api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert response.status_code == 202
    assert response.json() == {"track_id": TrackId.of_content(DATA).value}
    assert len(api.jobs.jobs) == 1


def test_upload_without_a_file_part_is_no_file(api: Api) -> None:
    response = api.client.post("/tracks", data={"other": "field"})
    assert response.status_code == 400
    assert response.json()["error"] == "no_file"


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b'--b\r\nContent-Disposition: form-data; name="file"\r\n\r\nRIFF\r\n--b--\r\n', "b"),
        (b"--b\r\ngarbage without headers", "b"),
        (b"file=RIFF", None),
    ],
    ids=["part-without-filename", "broken-multipart", "missing-boundary"],
)
def test_unreadable_upload_is_no_file_in_the_contract_body(
    api: Api, body: bytes, content_type: str | None
) -> None:
    header = "multipart/form-data" + (f"; boundary={content_type}" if content_type else "")
    response = api.client.post("/tracks", content=body, headers={"content-type": header})
    assert response.status_code == 400
    assert response.json()["error"] == "no_file"
    assert set(response.json()) == {"error", "message"}


def test_empty_upload_is_no_file(api: Api) -> None:
    response = api.client.post("/tracks", files={"file": ("t.wav", b"", "audio/wav")})
    assert response.status_code == 400
    assert response.json()["error"] == "no_file"


def test_upload_over_the_limit_is_file_too_large(api: Api) -> None:
    big = b"x" * (LIMIT_BYTES + 1)
    response = api.client.post("/tracks", files={"file": ("t.wav", big, "audio/wav")})
    assert response.status_code == 413
    assert response.json()["error"] == "file_too_large"


def test_declared_oversized_body_is_refused_before_the_app_reads_it(api: Api) -> None:
    big = b"x" * (LIMIT_BYTES + MULTIPART_OVERHEAD_BYTES + 1)
    response = api.client.post("/tracks", files={"file": ("t.wav", big, "audio/wav")})
    assert response.status_code == 413
    assert response.json()["error"] == "file_too_large"
    assert api.jobs.jobs == []


def test_upload_while_the_queue_is_full_is_busy(api: Api) -> None:
    api.client.post("/tracks", files={"file": ("a.wav", b"first", "audio/wav")})
    response = api.client.post("/tracks", files={"file": ("b.wav", DATA, "audio/wav")})
    assert response.status_code == 503
    assert response.json()["error"] == "busy"


def test_track_over_the_duration_limit_is_file_too_large() -> None:
    api = Api(decoder=FakeDecoder(duration_s=601.0))
    response = api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert response.status_code == 413
    assert response.json()["error"] == "file_too_large"
    assert api.jobs.jobs == []


def test_unsupported_content_is_unsupported_format() -> None:
    api = Api(decoder=FakeDecoder(probe_error=UnsupportedFormatError("expected mp3")))
    response = api.client.post("/tracks", files={"file": ("t.aiff", DATA, "audio/aiff")})
    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_format", "message": "expected mp3"}


@pytest.mark.parametrize(
    "path", ["/tracks/{id}", "/tracks/{id}/timeline"], ids=["metadata", "timeline"]
)
@pytest.mark.parametrize(
    "track_id", ["0123456789abcdef", "not-a-track-id"], ids=["unknown", "malformed"]
)
def test_unknown_track_is_track_not_found(api: Api, path: str, track_id: str) -> None:
    response = api.client.get(path.format(id=track_id))
    assert response.status_code == 404
    assert response.json()["error"] == "track_not_found"


@pytest.mark.parametrize(
    "path", ["/tracks/{id}", "/tracks/{id}/timeline"], ids=["metadata", "timeline"]
)
def test_running_analysis_is_not_ready(api: Api, path: str) -> None:
    track = TrackId.of_content(DATA)
    record_now(api.board, track, Analysing.at(AnalysisStage.TEMPO))
    response = api.client.get(path.format(id=track.value))
    assert response.status_code == 409
    assert response.json()["error"] == "not_ready"


@pytest.mark.parametrize(
    ("code", "http_status"),
    [
        (FailureCode.UNDECODABLE, 422),
        (FailureCode.ANALYSIS_FAILED, 422),
        (FailureCode.INTERNAL, 500),
    ],
    ids=["undecodable", "analysis-failed", "internal"],
)
def test_failed_analysis_returns_its_error(api: Api, code: FailureCode, http_status: int) -> None:
    track = TrackId.of_content(DATA)
    record_now(api.board, track, Failed(code=code, message="why"))
    response = api.client.get(f"/tracks/{track.value}")
    assert response.status_code == http_status
    assert response.json() == {"error": code.value, "message": "why"}


def test_ready_track_metadata_matches_the_contract(api: Api) -> None:
    track = TrackId.of_content(DATA)
    analysis = golden_analysis()
    record_now(api.board, track, Ready(analysis=analysis))
    response = api.client.get(f"/tracks/{track.value}")
    assert response.status_code == 200
    assert response.json() == {
        "track_id": track.value,
        "duration_s": analysis.duration_s,
        "bpm": 300.0,
        "beat_offset_s": 0.0,
        "sections": [{"name": "drop", "start_s": 0.0, "end_s": analysis.duration_s, "loud": True}],
    }


def test_ready_track_timeline_is_the_encoded_analysis(api: Api) -> None:
    track = TrackId.of_content(DATA)
    analysis = golden_analysis()
    record_now(api.board, track, Ready(analysis=analysis))
    response = api.client.get(f"/tracks/{track.value}/timeline")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == encode_timeline(analysis)
