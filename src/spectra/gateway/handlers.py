import logging
from collections.abc import Sequence
from typing import Protocol

from spectra.analysis.application.ports import FeatureSource
from spectra.gateway.wire.messages import (
    ClientMessage,
    DirectorLog,
    FrameCapture,
    Prompt,
    ServerMessage,
    ShaderCompiled,
)

logger = logging.getLogger(__name__)


class ClientMessageHandler(Protocol):
    def handle(self, message: ClientMessage) -> Sequence[ServerMessage]: ...


class PromptEchoHandler:
    def __init__(self, *, source: FeatureSource) -> None:
        self._source = source

    def handle(self, message: ClientMessage) -> Sequence[ServerMessage]:
        match message:
            case ShaderCompiled(ok=False, id=shader_id, error=error):
                logger.info("shader %s failed to compile: %s", shader_id, error)
                return ()
            case ShaderCompiled(id=shader_id):
                logger.info("shader %s compiled", shader_id)
                return ()
            case Prompt(text=text):
                bar = self._source.latest().position.bar
                return (DirectorLog(bar=bar, text=f"prompt received: {text}"),)
            case FrameCapture(id=shader_id, state=state):
                logger.debug("frame capture of %s at %s is not handled yet", shader_id, state)
                return ()
