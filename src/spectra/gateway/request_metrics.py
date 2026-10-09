from typing import Final

from fastapi import FastAPI
from fastapi.routing import APIRoute
from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from spectra.shared.clock import Clock

UNMATCHED_ROUTE: Final = "unmatched"
OTHER_METHOD: Final = "OTHER"
KNOWN_METHODS: Final = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
REQUEST_BUCKETS_S: Final = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class RequestMetrics:
    def __init__(self, app: ASGIApp, *, registry: CollectorRegistry, clock: Clock) -> None:
        self._app = app
        self._clock = clock
        self._requests = Counter(
            "spectra_http_requests",
            "HTTP requests by method, route template and status",
            ["method", "route", "status"],
            registry=registry,
        )
        self._duration = Histogram(
            "spectra_http_request_duration_seconds",
            "Time to answer an HTTP request, streams included",
            ["method", "route"],
            buckets=REQUEST_BUCKETS_S,
            registry=registry,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started_s = self._clock.now_s()
        response = ResponseStatus(send)
        try:
            await self._app(scope, receive, response.send)
        finally:
            method, route = method_of(scope), route_of(scope)
            self._requests.labels(method=method, route=route, status=str(response.status)).inc()
            self._duration.labels(method=method, route=route).observe(
                self._clock.now_s() - started_s
            )


class ResponseStatus:
    def __init__(self, send: Send) -> None:
        self._send = send
        self.status = 500

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        await self._send(message)


def method_of(scope: Scope) -> str:
    method: str = scope["method"]
    return method if method in KNOWN_METHODS else OTHER_METHOD


def route_of(scope: Scope) -> str:
    route = scope.get("route")
    return route.path if isinstance(route, APIRoute) else UNMATCHED_ROUTE


def install_request_metrics(app: FastAPI, *, registry: CollectorRegistry, clock: Clock) -> None:
    app.add_middleware(RequestMetrics, registry=registry, clock=clock)
