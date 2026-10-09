import http.client
import sys
from http import HTTPStatus
from typing import Final

from spectra.bootstrap.settings import Settings

PROBE_HOST: Final = "127.0.0.1"
PROBE_PATH: Final = "/ready"
METRICS_PATH: Final = "/metrics"
PROBE_TIMEOUT_S: Final = 4.0


def is_healthy(*, port: int, path: str) -> bool:
    connection = http.client.HTTPConnection(PROBE_HOST, port, timeout=PROBE_TIMEOUT_S)
    try:
        connection.request("GET", path)
        return connection.getresponse().status == HTTPStatus.OK
    except OSError:
        return False
    finally:
        connection.close()


def main() -> None:
    sys.exit(0 if is_healthy(port=Settings().port, path=PROBE_PATH) else 1)


def worker_main() -> None:
    port = Settings().metrics_port
    sys.exit(0 if port is not None and is_healthy(port=port, path=METRICS_PATH) else 1)
