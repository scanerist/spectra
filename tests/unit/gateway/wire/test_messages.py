import json
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from spectra.gateway.wire.messages import (
    CLIENT_MESSAGE_ADAPTER,
    MAX_PROMPT_LENGTH,
    MAX_TRANSITION_BARS,
    CaptureState,
    DecksState,
    DirectorLog,
    FrameCapture,
    Prompt,
    SceneParams,
    SceneSwitch,
    ShaderCompiled,
    StudioProgress,
)


def parse(payload: dict[str, object]) -> object:
    return CLIENT_MESSAGE_ADAPTER.validate_json(json.dumps(payload))


def test_server_messages_default_their_type() -> None:
    assert DirectorLog(bar=4, text="drop").type == "director.log"


def test_messages_are_hashable_values() -> None:
    assert hash(DirectorLog(bar=4, text="drop")) == hash(DirectorLog(bar=4, text="drop"))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"type": "shader.compiled", "id": "s", "ok": True}, ShaderCompiled),
        ({"type": "frame.capture", "id": "s", "state": "silence", "png_b64": ""}, FrameCapture),
        ({"type": "prompt", "text": "cold"}, Prompt),
    ],
    ids=["shader.compiled", "frame.capture", "prompt"],
)
def test_client_message_dispatches_on_type(payload: dict[str, object], expected: type) -> None:
    assert isinstance(parse(payload), expected)


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "nope"},
        {"text": "no type"},
        {"type": "director.log", "bar": 1, "text": "server only"},
        {"type": "prompt", "text": "x", "extra": 1},
    ],
    ids=["unknown-type", "missing-type", "server-message", "extra-field"],
)
def test_client_message_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("length", [1, MAX_PROMPT_LENGTH], ids=["one-char", "max-length"])
def test_prompt_accepts_lengths_within_limits(length: int) -> None:
    assert Prompt(text="x" * length).text == "x" * length


@pytest.mark.parametrize("length", [0, MAX_PROMPT_LENGTH + 1], ids=["empty", "too-long"])
def test_prompt_rejects_lengths_outside_limits(length: int) -> None:
    with pytest.raises(ValidationError):
        Prompt(text="x" * length)


@pytest.mark.parametrize("state", list(CaptureState), ids=str)
def test_frame_capture_accepts_every_capture_state(state: CaptureState) -> None:
    message = parse({"type": "frame.capture", "id": "s", "state": state.value, "png_b64": ""})
    assert isinstance(message, FrameCapture)
    assert message.state is state


def test_frame_capture_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        parse({"type": "frame.capture", "id": "s", "state": "drop", "png_b64": ""})


@pytest.mark.parametrize(
    "palette",
    [("#0D0D0D", "#EC6D1C"), ("#0D0D0D", "#EC6D1C", "#GGGGGG"), ("0D0D0D", "#EC6D1C", "#EDEAE4")],
    ids=["two-colors", "not-hex", "no-hash"],
)
def test_scene_params_palette_requires_three_hex_colors(palette: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        SceneParams.model_validate({"palette": palette})


@pytest.mark.parametrize(
    "build",
    [
        lambda: SceneParams(intensity=1.5),
        lambda: SceneParams(intensity=-0.1),
        lambda: DecksState(decks=[], crossfader=1.01),
        lambda: StudioProgress(order_id="o", progress=-0.5),
    ],
    ids=["intensity-high", "intensity-negative", "crossfader", "progress"],
)
def test_unit_fields_reject_out_of_range(build: Callable[[], object]) -> None:
    with pytest.raises(ValidationError):
        build()


@pytest.mark.parametrize(
    "transition_bars", [-1, MAX_TRANSITION_BARS + 1], ids=["negative", "too-long"]
)
def test_scene_switch_rejects_transition_bars_out_of_range(transition_bars: int) -> None:
    with pytest.raises(ValidationError):
        SceneSwitch(id="s", transition_bars=transition_bars)
