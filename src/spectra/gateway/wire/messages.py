from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

MAX_PROMPT_LENGTH: Final = 500
MAX_TRANSITION_BARS: Final = 64

type HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
type UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]


class CaptureState(StrEnum):
    SILENCE = "silence"
    KICK_PEAK = "kick_peak"
    HIGH_ENERGY = "high_energy"
    BREAKDOWN = "breakdown"


class WireMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ShaderLoad(WireMessage):
    type: Literal["shader.load"] = "shader.load"
    id: str
    code: str


class SceneSwitch(WireMessage):
    type: Literal["scene.switch"] = "scene.switch"
    id: str
    transition_bars: int = Field(ge=0, le=MAX_TRANSITION_BARS)


class SceneParams(WireMessage):
    type: Literal["scene.params"] = "scene.params"
    intensity: UnitInterval | None = None
    palette: tuple[HexColor, HexColor, HexColor] | None = None


class DirectorLog(WireMessage):
    type: Literal["director.log"] = "director.log"
    bar: int
    text: str


class DecksState(WireMessage):
    type: Literal["decks.state"] = "decks.state"
    decks: list[dict[str, JsonValue]]
    crossfader: UnitInterval


class StudioProgress(WireMessage):
    type: Literal["studio.progress"] = "studio.progress"
    order_id: str
    for_deck: str | None = None
    progress: UnitInterval


class ShaderCompiled(WireMessage):
    type: Literal["shader.compiled"] = "shader.compiled"
    id: str
    ok: bool
    error: str | None = None


class FrameCapture(WireMessage):
    type: Literal["frame.capture"] = "frame.capture"
    id: str
    state: CaptureState
    png_b64: str


class Prompt(WireMessage):
    type: Literal["prompt"] = "prompt"
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)


type ServerMessage = Annotated[
    ShaderLoad | SceneSwitch | SceneParams | DirectorLog | DecksState | StudioProgress,
    Field(discriminator="type"),
]

type ClientMessage = Annotated[
    ShaderCompiled | FrameCapture | Prompt,
    Field(discriminator="type"),
]

CLIENT_MESSAGE_ADAPTER: Final[TypeAdapter[ClientMessage]] = TypeAdapter(ClientMessage)
