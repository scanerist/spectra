from prometheus_client import CollectorRegistry

from spectra.tracks.adapters.prometheus import PrometheusAnalysisObserver
from spectra.tracks.domain.track import Failed, FailureCode
from tests.fakes import FakeClock
from tests.statuses import READY, track


def test_a_settled_analysis_is_counted_by_outcome_and_timed() -> None:
    registry = CollectorRegistry()
    clock = FakeClock(start_s=10.0)
    observer = PrometheusAnalysisObserver(registry=registry, clock=clock)
    observer.started(track("a"))
    assert registry.get_sample_value("spectra_analyses_running") == 1.0
    clock.advance(2.5)
    observer.finished(track("a"), READY)
    assert registry.get_sample_value("spectra_analyses_total", {"outcome": "ready"}) == 1.0
    assert registry.get_sample_value("spectra_analysis_duration_seconds_sum") == 2.5
    assert registry.get_sample_value("spectra_analyses_running") == 0.0


def test_failures_are_counted_by_their_code() -> None:
    registry = CollectorRegistry()
    observer = PrometheusAnalysisObserver(registry=registry, clock=FakeClock())
    observer.started(track("a"))
    observer.finished(track("a"), Failed(code=FailureCode.UNDECODABLE, message="lost sync"))
    labels = {"outcome": "undecodable"}
    assert registry.get_sample_value("spectra_analyses_total", labels) == 1.0
