from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from spectra.gateway.protocol import PROTOCOL_VERSION


class HealthReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: Literal[True] = True
    protocol: int = PROTOCOL_VERSION


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> HealthReport:
        return HealthReport()

    return router
