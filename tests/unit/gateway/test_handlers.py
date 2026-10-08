import logging

import pytest

from spectra.gateway.handlers import ClientMessageHandler, PromptEchoHandler
from spectra.gateway.wire.messages import (
    CaptureState,
    DirectorLog,
    FrameCapture,
    Prompt,
    ShaderCompiled,
)
from tests.fakes import StaticFeatureSource, frame_at_bar


@pytest.fixture
def handler() -> ClientMessageHandler:
    return PromptEchoHandler(source=StaticFeatureSource(frame_at_bar(17)))


def test_prompt_is_echoed_as_director_log_at_the_current_bar(
    handler: ClientMessageHandler,
) -> None:
    replies = handler.handle(Prompt(text="cold concrete"))
    assert replies == (DirectorLog(bar=17, text="prompt received: cold concrete"),)


@pytest.mark.parametrize(
    ("message", "logged"),
    [
        (ShaderCompiled(id="strobe", ok=True), "shader strobe compiled"),
        (
            ShaderCompiled(id="strobe", ok=False, error="ERROR: 0:14"),
            "shader strobe failed to compile: ERROR: 0:14",
        ),
    ],
    ids=["compiled", "failed"],
)
def test_shader_compile_results_are_logged_without_reply(
    handler: ClientMessageHandler,
    caplog: pytest.LogCaptureFixture,
    message: ShaderCompiled,
    logged: str,
) -> None:
    with caplog.at_level(logging.INFO, logger="spectra.gateway.handlers"):
        assert handler.handle(message) == ()
    assert logged in caplog.messages


def test_frame_capture_gets_no_reply(handler: ClientMessageHandler) -> None:
    capture = FrameCapture(id="strobe", state=CaptureState.KICK_PEAK, png_b64="")
    assert handler.handle(capture) == ()
