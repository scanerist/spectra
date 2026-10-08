import json

import pytest
from pydantic import BaseModel

from engine.protocol import (
    DecksState,
    DirectorLog,
    FrameCapture,
    Prompt,
    SceneParams,
    SceneSwitch,
    ShaderCompiled,
    ShaderLoad,
    StudioProgress,
    client_message_adapter,
)

type JsonObject = dict[str, object]


@pytest.mark.parametrize(
    ("model", "contract_json", "wire_json"),
    [
        (
            ShaderLoad,
            {"type": "shader.load", "id": "concrete_strobe", "code": "<glsl>"},
            {"type": "shader.load", "id": "concrete_strobe", "code": "<glsl>"},
        ),
        (
            SceneSwitch,
            {"type": "scene.switch", "id": "concrete_strobe", "transition_bars": 2},
            {"type": "scene.switch", "id": "concrete_strobe", "transition_bars": 2},
        ),
        (
            SceneParams,
            {
                "type": "scene.params",
                "intensity": 0.8,
                "palette": ["#0D0D0D", "#EC6D1C", "#EDEAE4"],
            },
            {
                "type": "scene.params",
                "intensity": 0.8,
                "palette": ["#0D0D0D", "#EC6D1C", "#EDEAE4"],
            },
        ),
        (
            SceneParams,
            {"type": "scene.params", "intensity": 0.5},
            {"type": "scene.params", "intensity": 0.5, "palette": None},
        ),
        (
            DirectorLog,
            {"type": "director.log", "bar": 80, "text": "дроп → кроссфейд в «бетон», 2 такта"},
            {"type": "director.log", "bar": 80, "text": "дроп → кроссфейд в «бетон», 2 такта"},
        ),
        (
            DecksState,
            {"type": "decks.state", "decks": [{"id": "A", "on_air": True}], "crossfader": 0.37},
            {"type": "decks.state", "decks": [{"id": "A", "on_air": True}], "crossfader": 0.37},
        ),
        (
            StudioProgress,
            {"type": "studio.progress", "order_id": "o-1", "for_deck": "B", "progress": 0.6},
            {"type": "studio.progress", "order_id": "o-1", "for_deck": "B", "progress": 0.6},
        ),
        (
            StudioProgress,
            {"type": "studio.progress", "order_id": "o-1", "progress": 0.6},
            {"type": "studio.progress", "order_id": "o-1", "for_deck": None, "progress": 0.6},
        ),
    ],
    ids=[
        "shader.load",
        "scene.switch",
        "scene.params",
        "scene.params-partial",
        "director.log",
        "decks.state",
        "studio.progress",
        "studio.progress-no-deck",
    ],
)
def test_server_message_json_shape(
    model: type[BaseModel], contract_json: JsonObject, wire_json: JsonObject
) -> None:
    message = model.model_validate(contract_json)
    assert json.loads(message.model_dump_json()) == wire_json


@pytest.mark.parametrize(
    ("model", "contract_json", "parsed"),
    [
        (
            ShaderCompiled,
            {"type": "shader.compiled", "id": "concrete_strobe", "ok": True},
            {"type": "shader.compiled", "id": "concrete_strobe", "ok": True, "error": None},
        ),
        (
            ShaderCompiled,
            {
                "type": "shader.compiled",
                "id": "concrete_strobe",
                "ok": False,
                "error": "ERROR: 0:14: ...",
            },
            {
                "type": "shader.compiled",
                "id": "concrete_strobe",
                "ok": False,
                "error": "ERROR: 0:14: ...",
            },
        ),
        (
            FrameCapture,
            {
                "type": "frame.capture",
                "id": "concrete_strobe",
                "state": "kick_peak",
                "png_b64": "...",
            },
            {
                "type": "frame.capture",
                "id": "concrete_strobe",
                "state": "kick_peak",
                "png_b64": "...",
            },
        ),
        (
            Prompt,
            {"type": "prompt", "text": "холодно, бетон, стробы на кик"},
            {"type": "prompt", "text": "холодно, бетон, стробы на кик"},
        ),
    ],
    ids=["shader.compiled-ok", "shader.compiled-error", "frame.capture", "prompt"],
)
def test_client_message_json_shape(
    model: type[BaseModel], contract_json: JsonObject, parsed: JsonObject
) -> None:
    message = client_message_adapter.validate_json(json.dumps(contract_json))
    assert isinstance(message, model)
    assert message.model_dump(mode="json") == parsed
