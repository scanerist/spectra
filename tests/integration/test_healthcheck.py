import threading
from collections.abc import Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from spectra.bootstrap import healthcheck


def serving(status: HTTPStatus) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status if self.path == "/ready" else HTTPStatus.NOT_FOUND)
            self.end_headers()

    return Handler


@pytest.fixture
def server_port(request: pytest.FixtureRequest) -> Iterator[int]:
    status: HTTPStatus = request.param
    server = ThreadingHTTPServer(("127.0.0.1", 0), serving(status))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("server_port", [HTTPStatus.OK], indirect=True, ids=["ok"])
def test_healthy_server_passes(server_port: int) -> None:
    assert healthcheck.is_healthy(port=server_port)


@pytest.mark.parametrize(
    "server_port", [HTTPStatus.SERVICE_UNAVAILABLE], indirect=True, ids=["unavailable"]
)
def test_unhealthy_answer_fails(server_port: int) -> None:
    assert not healthcheck.is_healthy(port=server_port)


def test_nothing_listening_fails() -> None:
    probe = ThreadingHTTPServer(("127.0.0.1", 0), serving(HTTPStatus.OK))
    free_port = probe.server_address[1]
    probe.server_close()
    assert not healthcheck.is_healthy(port=free_port)


@pytest.mark.parametrize(
    ("server_port", "exit_code"),
    [(HTTPStatus.OK, 0), (HTTPStatus.SERVICE_UNAVAILABLE, 1)],
    indirect=["server_port"],
    ids=["healthy", "unhealthy"],
)
def test_main_exits_with_the_probe_result(
    server_port: int, exit_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECTRA_PORT", str(server_port))
    with pytest.raises(SystemExit) as exited:
        healthcheck.main()
    assert exited.value.code == exit_code
