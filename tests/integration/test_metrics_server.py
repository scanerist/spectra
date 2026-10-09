import urllib.request

from prometheus_client import CollectorRegistry, Counter

from spectra.bootstrap.metrics import serving_metrics


def test_metrics_are_served_on_the_configured_port() -> None:
    registry = CollectorRegistry()
    Counter("spectra_test_events", "Events seen by the test", registry=registry).inc(3)
    with serving_metrics(registry, port=0) as port:
        assert port is not None
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as response:
            body = response.read().decode()
    assert "spectra_test_events_total 3.0" in body


def test_no_port_serves_nothing() -> None:
    with serving_metrics(CollectorRegistry(), port=None) as port:
        assert port is None
