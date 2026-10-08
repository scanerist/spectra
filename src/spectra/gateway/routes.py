from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, FastAPI, WebSocket
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict

from spectra.gateway.connection import WebSocketConnection
from spectra.gateway.errors import GatewayNotConfiguredError
from spectra.gateway.session import ClientSession, SessionDependencies
from spectra.gateway.wire.frame_codec import PROTOCOL_VERSION

SESSION_DEPENDENCIES_STATE: Final = "session_dependencies"


class HealthReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: Literal[True] = True
    protocol: int = PROTOCOL_VERSION


def install_session_dependencies(app: FastAPI, dependencies: SessionDependencies) -> None:
    setattr(app.state, SESSION_DEPENDENCIES_STATE, dependencies)


def session_dependencies(connection: HTTPConnection) -> SessionDependencies:
    dependencies = getattr(connection.app.state, SESSION_DEPENDENCIES_STATE, None)
    if not isinstance(dependencies, SessionDependencies):
        raise GatewayNotConfiguredError("session dependencies are not installed on the app")
    return dependencies


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> HealthReport:
        return HealthReport()

    @router.websocket("/ws")
    async def stream(
        websocket: WebSocket,
        dependencies: Annotated[SessionDependencies, Depends(session_dependencies)],
    ) -> None:
        await websocket.accept()
        session = ClientSession(
            connection=WebSocketConnection(websocket), dependencies=dependencies
        )
        await session.run()

    return router
