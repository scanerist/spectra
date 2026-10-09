from typing import Final

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from spectra.shared.clock import Clock
from spectra.tracks.domain.track import TrackId, TrackStatus, outcome_name

ANALYSIS_BUCKETS_S: Final = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0)


class PrometheusAnalysisObserver:
    def __init__(self, *, registry: CollectorRegistry, clock: Clock) -> None:
        self._clock = clock
        self._started_s: dict[TrackId, float] = {}
        self._finished = Counter(
            "spectra_analyses",
            "Analyses the worker settled, by outcome",
            ["outcome"],
            registry=registry,
        )
        self._duration = Histogram(
            "spectra_analysis_duration_seconds",
            "Time from taking a job to settling its track",
            buckets=ANALYSIS_BUCKETS_S,
            registry=registry,
        )
        self._running = Gauge(
            "spectra_analyses_running", "Analyses in progress in this process", registry=registry
        )

    def started(self, track_id: TrackId) -> None:
        self._started_s[track_id] = self._clock.now_s()
        self._running.inc()

    def finished(self, track_id: TrackId, outcome: TrackStatus) -> None:
        self._running.dec()
        self._finished.labels(outcome=outcome_name(outcome)).inc()
        started_s = self._started_s.pop(track_id, None)
        if started_s is not None:
            self._duration.observe(self._clock.now_s() - started_s)
