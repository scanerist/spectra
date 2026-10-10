import asyncio
from collections.abc import Iterator
from dataclasses import replace
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.analysis.domain.errors import UnsupportedFormatError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.gateway.engine import install_engine
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.routes import create_router
from spectra.gateway.slots import SlotLimits, Slots
from spectra.gateway.timeline_codec import encode_timeline
from spectra.gateway.upload_limit import MULTIPART_OVERHEAD_BYTES, install_upload_limit
from spectra.tracks.adapters.memory import InMemoryBlobStore
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.application.ports import UploadQuota
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.domain.blobs import timeline_key
from spectra.tracks.domain.quota import UploadSource
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    Ready,
    TrackId,
    TrackSummary,
)
from tests.contract.timeline_fixture import golden_analysis
from tests.fakes import (
    RELAXED_PACE,
    ExhaustedQuota,
    FakeClock,
    FakeDecoder,
    FakeJobQueue,
    UnlimitedQuota,
    fake_engine,
    memory_board,
    probe_of,
    record_now,
)

DATA: Final = b"RIFF pretend this is audio"
LIMIT_BYTES: Final = 1_000
TESTCLIENT: Final = UploadSource(address="testclient", network="testclient")
ELSEWHERE: Final = UploadSource(address="203.0.113.1", network="203.0.113.1")
FARTHER: Final = UploadSource(address="203.0.113.2", network="203.0.113.2")


class Api:
    def __init__(
        self, *, decoder: FakeDecoder | None = None, quota: UploadQuota | None = None
    ) -> None:
        self.board = memory_board()
        self.jobs = FakeJobQueue()
        self.blobs = InMemoryBlobStore()
        self.clients = UnlimitedQuota()
        self.uploads = Slots(
            limits=SlotLimits(total=2, per_address=1, per_network=1, retry_after_s=5.0),
            name="uploads",
        )
        service = TrackService(
            decoder=decoder or FakeDecoder(),
            board=self.board,
            blobs=self.blobs,
            jobs=self.jobs,
            limits=UploadLimits(
                max_upload_bytes=LIMIT_BYTES,
                max_duration_s=600.0,
                max_pending=1,
                max_decoded_samples=10**9,
            ),
        )
        app = FastAPI()
        app.include_router(create_router())
        install_error_handlers(app)
        self.timelines = Slots(
            limits=SlotLimits(total=1, per_address=1, per_network=1, retry_after_s=5.0),
            name="timelines",
        )
        install_engine(
            app,
            replace(
                fake_engine(),
                track_service=service,
                upload_admission=UploadAdmission(quota=quota or self.clients),
                upload_slots=self.uploads,
                timeline_slots=self.timelines,
            ),
        )
        install_upload_limit(
            app, max_upload_bytes=LIMIT_BYTES, pace=RELAXED_PACE, clock=FakeClock()
        )
        self.client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api() -> Api:
    return Api()


def test_upload_answers_202_with_the_track_id(api: Api) -> None:
    response = api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert response.status_code == 202
    assert response.json() == {"track_id": TrackId.of_content(DATA).value}
    assert len(api.jobs.jobs) == 1


def test_uploads_are_counted_per_client_address(api: Api) -> None:
    api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert api.clients.clients == [TESTCLIENT]


def test_an_exhausted_quota_is_rate_limited_with_retry_after() -> None:
    api = Api(quota=ExhaustedQuota(retry_after_s=41.2))
    response = api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
    assert response.headers["retry-after"] == "42"
    assert api.jobs.jobs == []


def test_a_rate_limited_upload_is_refused_before_its_body_is_read() -> None:
    api = Api(quota=ExhaustedQuota(retry_after_s=1.0))
    body = b"--b\r\ngarbage without headers"
    headers = {"content-type": "multipart/form-data; boundary=b"}
    response = api.client.post("/tracks", content=body, headers=headers)
    assert response.status_code == 429


def test_an_upload_while_every_upload_slot_is_taken_is_busy_and_not_counted(api: Api) -> None:
    held = [api.uploads.take(source) for source in (ELSEWHERE, FARTHER)]
    response = api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert response.status_code == 503
    assert response.json()["error"] == "busy"
    assert api.clients.clients == []
    held[0].release()
    assert (
        api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")}).status_code == 202
    )


def test_a_second_upload_at_once_from_one_address_is_rate_limited_and_not_counted(
    api: Api,
) -> None:
    api.uploads.take(TESTCLIENT)
    response = api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
    assert response.headers["retry-after"] == "5"
    assert api.clients.clients == []


@pytest.mark.parametrize(
    ("data", "status_code"),
    [(DATA, 202), (b"", 400), (b"x" * (LIMIT_BYTES + 1), 413)],
    ids=["accepted", "empty", "too-large"],
)
def test_an_upload_gives_its_slot_back(api: Api, data: bytes, status_code: int) -> None:
    response = api.client.post("/tracks", files={"file": ("t.wav", data, "audio/wav")})
    assert response.status_code == status_code
    assert api.uploads.held == 0


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


def test_a_chunked_upload_over_the_limit_is_file_too_large(api: Api) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="t.wav"\r\n\r\n'
        for _ in range(200):
            yield b"x" * 1_000

    headers = {"content-type": "multipart/form-data; boundary=b"}
    response = api.client.post("/tracks", content=chunks(), headers=headers)
    assert response.status_code == 413
    assert response.json()["error"] == "file_too_large"


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
    assert api.clients.refunds == [TESTCLIENT]


def test_an_accepted_upload_keeps_its_place_in_the_quota(api: Api) -> None:
    api.client.post("/tracks", files={"file": ("t.wav", DATA, "audio/wav")})
    assert api.clients.refunds == []


def test_track_over_the_duration_limit_is_file_too_large() -> None:
    api = Api(decoder=FakeDecoder(probe_result=probe_of(duration_s=601.0)))
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
    record_now(api.board, track, Ready(summary=TrackSummary.of_analysis(analysis)))
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
    asyncio.run(api.blobs.put(timeline_key(track), encode_timeline(analysis)))
    record_now(api.board, track, Ready(summary=TrackSummary.of_analysis(analysis)))
    response = api.client.get(f"/tracks/{track.value}/timeline")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.content == encode_timeline(analysis)
    assert api.timelines.held == 0


def test_a_timeline_while_every_timeline_slot_is_taken_is_busy(api: Api) -> None:
    track = TrackId.of_content(DATA)
    analysis = golden_analysis()
    asyncio.run(api.blobs.put(timeline_key(track), encode_timeline(analysis)))
    record_now(api.board, track, Ready(summary=TrackSummary.of_analysis(analysis)))
    held = api.timelines.take(ELSEWHERE)
    response = api.client.get(f"/tracks/{track.value}/timeline")
    assert response.status_code == 503
    assert response.json()["error"] == "busy"
    held.release()
    assert api.client.get(f"/tracks/{track.value}/timeline").status_code == 200


def test_a_missing_timeline_gives_its_slot_back(api: Api) -> None:
    track = TrackId.of_content(DATA)
    record_now(api.board, track, Ready(summary=TrackSummary.of_analysis(golden_analysis())))
    assert api.client.get(f"/tracks/{track.value}/timeline").status_code == 404
    assert api.timelines.held == 0


def test_ready_track_without_a_timeline_is_forgotten(api: Api) -> None:
    track = TrackId.of_content(DATA)
    record_now(api.board, track, Ready(summary=TrackSummary.of_analysis(golden_analysis())))
    response = api.client.get(f"/tracks/{track.value}/timeline")
    assert response.status_code == 404
    assert response.json()["error"] == "track_not_found"
    assert api.client.get(f"/tracks/{track.value}").status_code == 404
