import http.client
import sys
from http import HTTPStatus
from typing import Final

from spectra.bootstrap.settings import Settings

PROBE_HOST: Final = "127.0.0.1"
PROBE_PATH: Final = "/health"
PROBE_TIMEOUT_S: Final = 2.0


def is_healthy(*, port: int) -> bool:
    connection = http.client.HTTPConnection(PROBE_HOST, port, timeout=PROBE_TIMEOUT_S)
    try:
        connection.request("GET", PROBE_PATH)
        return connection.getresponse().status == HTTPStatus.OK
    except OSError:
        return False
    finally:
        connection.close()


def main() -> None:
    sys.exit(0 if is_healthy(port=Settings().port) else 1)
