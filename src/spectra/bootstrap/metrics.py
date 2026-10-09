from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, start_http_server


@contextmanager
def serving_metrics(registry: CollectorRegistry, *, port: int | None) -> Iterator[int | None]:
    if port is None:
        yield None
        return
    server, thread = start_http_server(port, registry=registry)
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
