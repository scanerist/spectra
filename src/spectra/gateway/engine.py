from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI
from fastapi.requests import HTTPConnection

from spectra.gateway.errors import GatewayNotConfiguredError
from spectra.gateway.events import EventStreams
from spectra.gateway.readiness import Readiness
from spectra.gateway.slots import Slots
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.application.service import TrackService

ENGINE_STATE: Final = "engine"


@dataclass(frozen=True, slots=True, kw_only=True)
class EngineState:
    track_service: TrackService
    upload_admission: UploadAdmission
    event_streams: EventStreams
    upload_slots: Slots
    timeline_slots: Slots
    readiness: Readiness


def install_engine(app: FastAPI, state: EngineState) -> None:
    setattr(app.state, ENGINE_STATE, state)


def installed_engine(connection: HTTPConnection) -> EngineState:
    state = getattr(connection.app.state, ENGINE_STATE, None)
    if not isinstance(state, EngineState):
        raise GatewayNotConfiguredError("the engine state is not installed on the app")
    return state
