

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, cast

import msgpack
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTOCOL_VERSION = 0

N_BANDS = 64
N_WAVEFORM = 512
N_PEAKS = 8
BANDS_FMIN_HZ = 30.0
BANDS_FMAX_HZ = 16_000.0

F32 = NDArray[np.float32]


# --------------------------------------------------------------------------- #
# 1. FeatureFrame (server -> client, 60 Hz, binary)
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class FeatureFrame:
    t: float  # engine time, s
    bands: F32  # (N_BANDS,) log bands 30 Hz-16 kHz, 0..1, smoothed
    waveform: F32  # (N_WAVEFORM,) -1..1
    peaks: F32  # (N_PEAKS, 3): freq_hz, amp 0..1, phase rad; sorted by amp desc, zero-padded
    kick: float  # 0..1, instant attack, exp decay
    bass: float  # 0..1
    mid: float  # 0..1
    high: float  # 0..1
    bpm: float
    beat_phase: float  # 0..1 within beat
    bar: int
    beat_in_bar: int  # 0..3
    energy: float  # slow (~4 bars), 0..1

    def __post_init__(self) -> None:
        _check_shape("bands", self.bands, (N_BANDS,))
        _check_shape("waveform", self.waveform, (N_WAVEFORM,))
        _check_shape("peaks", self.peaks, (N_PEAKS, 3))

    def pack(self) -> bytes:
        """Serialize to msgpack. Arrays go as little-endian float32 `bin` fields,
        so the client can view them as Float32Array without per-element decoding."""
        payload: dict[str, Any] = {
            "v": PROTOCOL_VERSION,
            "t": self.t,
            "bands": _f32le(self.bands),
            "waveform": _f32le(self.waveform),
            "peaks": _f32le(self.peaks),
            "kick": self.kick,
            "bass": self.bass,
            "mid": self.mid,
            "high": self.high,
            "bpm": self.bpm,
            "beat_phase": self.beat_phase,
            "bar": self.bar,
            "beat_in_bar": self.beat_in_bar,
            "energy": self.energy,
        }
        return cast(bytes, msgpack.packb(payload, use_bin_type=True))

    @classmethod
    def unpack(cls, data: bytes) -> FeatureFrame:
        """Inverse of pack(). Used in tests and for recording/replaying sessions."""
        d: dict[str, Any] = msgpack.unpackb(data, raw=False)
        if d.get("v") != PROTOCOL_VERSION:
            raise ValueError(f"protocol version mismatch: {d.get('v')} != {PROTOCOL_VERSION}")
        return cls(
            t=float(d["t"]),
            bands=_from_f32le(d["bands"]),
            waveform=_from_f32le(d["waveform"]),
            peaks=_from_f32le(d["peaks"]).reshape(N_PEAKS, 3),
            kick=float(d["kick"]),
            bass=float(d["bass"]),
            mid=float(d["mid"]),
            high=float(d["high"]),
            bpm=float(d["bpm"]),
            beat_phase=float(d["beat_phase"]),
            bar=int(d["bar"]),
            beat_in_bar=int(d["beat_in_bar"]),
            energy=float(d["energy"]),
        )


def _f32le(a: F32) -> bytes:
    return np.ascontiguousarray(a, dtype="<f4").tobytes()


def _from_f32le(b: bytes) -> F32:
    return np.frombuffer(b, dtype="<f4").astype(np.float32)  # copy -> native, writable


def _check_shape(name: str, a: F32, shape: tuple[int, ...]) -> None:
    if a.shape != shape:
        raise ValueError(f"FeatureFrame.{name}: expected shape {shape}, got {a.shape}")


# --------------------------------------------------------------------------- #
# Control messages (JSON text frames)
# --------------------------------------------------------------------------- #


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]


# --- 3. server -> client ---------------------------------------------------- #


class ShaderLoad(_Msg):
    type: Literal["shader.load"] = "shader.load"
    id: str
    code: str


class SceneSwitch(_Msg):
    type: Literal["scene.switch"] = "scene.switch"
    id: str
    transition_bars: int = Field(ge=0, le=64)


class SceneParams(_Msg):
    type: Literal["scene.params"] = "scene.params"
    intensity: Unit | None = None
    palette: tuple[HexColor, HexColor, HexColor] | None = None


class DirectorLog(_Msg):
    type: Literal["director.log"] = "director.log"
    bar: int
    text: str


class DecksState(_Msg):
    type: Literal["decks.state"] = "decks.state"
    decks: list[dict[str, Any]]  # TODO(stage 6): typed DeckState from 04_dj_integration
    crossfader: Unit


class StudioProgress(_Msg):
    type: Literal["studio.progress"] = "studio.progress"
    order_id: str
    for_deck: str | None = None
    progress: Unit


ServerMessage = ShaderLoad | SceneSwitch | SceneParams | DirectorLog | DecksState | StudioProgress


# --- 4. client -> server ---------------------------------------------------- #


class ShaderCompiled(_Msg):
    type: Literal["shader.compiled"] = "shader.compiled"
    id: str
    ok: bool
    error: str | None = None


class FrameCapture(_Msg):
    type: Literal["frame.capture"] = "frame.capture"
    id: str
    state: Literal["silence", "kick_peak", "high_energy", "breakdown"]
    png_b64: str


class Prompt(_Msg):
    type: Literal["prompt"] = "prompt"
    text: str = Field(min_length=1, max_length=500)


ClientMessage = ShaderCompiled | FrameCapture | Prompt

client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(
    Annotated[ClientMessage, Field(discriminator="type")]
)
