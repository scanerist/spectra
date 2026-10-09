import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from spectra.bootstrap import smoke
from spectra.bootstrap.app import create_app
from spectra.bootstrap.settings import Settings

STARTUP_LIMIT_S = 10.0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def live_url() -> Iterator[str]:
    port = free_port()
    config = uvicorn.Config(
        create_app(Settings()), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + STARTUP_LIMIT_S
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(STARTUP_LIMIT_S)


def test_smoke_test_passes_against_a_live_server(live_url: str) -> None:
    report = smoke.run_smoke_test(live_url)
    assert report.bpm == pytest.approx(smoke.SMOKE_BPM, abs=smoke.BPM_TOLERANCE)
    assert report.frame_count > 0
    assert report.bar_count > 0


def test_main_exits_zero_when_the_service_works(
    live_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["spectra-smoke", live_url])
    smoke.main()


def test_main_exits_with_the_error_when_nothing_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["spectra-smoke", f"http://127.0.0.1:{free_port()}"])
    with pytest.raises(SystemExit, match=r"smoke test against .* failed"):
        smoke.main()


def test_non_http_base_url_is_rejected() -> None:
    with pytest.raises(smoke.SmokeTestError):
        smoke.Client("ftp://example.org")
