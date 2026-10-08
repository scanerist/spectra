from collections.abc import Mapping
from typing import Final

import msgpack
import numpy as np

from spectra.analysis.domain.errors import AnalysisError
from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import PEAK_COUNT, PEAK_FIELD_COUNT, Peaks
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.spectrum import BAND_COUNT, Spectrum
from spectra.analysis.domain.tempo import BeatPosition, Tempo
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform
from spectra.gateway.errors import WireFormatError

PROTOCOL_VERSION: Final = 0
WIRE_FLOAT32: Final = np.dtype("<f4")
FRAME_KEYS: Final = frozenset(
    {
        "v",
        "t",
        "bands",
        "waveform",
        "peaks",
        "kick",
        "bass",
        "mid",
        "high",
        "bpm",
        "beat_phase",
        "bar",
        "beat_in_bar",
        "energy",
    }
)

type WireMap = Mapping[object, object]


def encode_frame(frame: FeatureFrame) -> bytes:
    payload = {
        "v": PROTOCOL_VERSION,
        "t": float(frame.time_s),
        "bands": to_wire_array(frame.spectrum.bands),
        "waveform": to_wire_array(frame.waveform.samples),
        "peaks": to_wire_array(frame.peaks.as_padded_array()),
        "kick": float(frame.levels.kick),
        "bass": float(frame.levels.bass),
        "mid": float(frame.levels.mid),
        "high": float(frame.levels.high),
        "bpm": float(frame.tempo.bpm),
        "beat_phase": float(frame.position.phase),
        "bar": int(frame.position.bar),
        "beat_in_bar": int(frame.position.beat_in_bar),
        "energy": float(frame.energy),
    }
    packed: bytes = msgpack.packb(payload, use_bin_type=True)
    return packed


def decode_frame(data: bytes) -> FeatureFrame:
    payload = unpack_map(data)
    require_frame_keys(payload)
    version = read_int(payload, "v")
    if version != PROTOCOL_VERSION:
        raise WireFormatError(
            f"unsupported protocol version {version}, expected {PROTOCOL_VERSION}"
        )
    try:
        return FeatureFrame(
            time_s=read_float(payload, "t"),
            spectrum=Spectrum(bands=read_array(payload, "bands", BAND_COUNT)),
            waveform=Waveform(samples=read_array(payload, "waveform", WAVEFORM_LENGTH)),
            peaks=Peaks.from_padded_array(
                read_array(payload, "peaks", PEAK_COUNT * PEAK_FIELD_COUNT).reshape(
                    PEAK_COUNT, PEAK_FIELD_COUNT
                )
            ),
            levels=Levels(
                kick=read_float(payload, "kick"),
                bass=read_float(payload, "bass"),
                mid=read_float(payload, "mid"),
                high=read_float(payload, "high"),
            ),
            tempo=Tempo(bpm=read_float(payload, "bpm")),
            position=BeatPosition(
                bar=read_int(payload, "bar"),
                beat_in_bar=read_int(payload, "beat_in_bar"),
                phase=read_float(payload, "beat_phase"),
            ),
            energy=read_float(payload, "energy"),
        )
    except AnalysisError as error:
        raise WireFormatError(f"frame violates domain invariants: {error}") from error


def to_wire_array(array: Float32Array) -> bytes:
    return np.ascontiguousarray(array, dtype=WIRE_FLOAT32).tobytes()


def unpack_map(data: bytes) -> WireMap:
    try:
        payload: object = msgpack.unpackb(data, raw=False)
    except ValueError as error:
        raise WireFormatError(f"frame is not valid msgpack: {error}") from error
    if not isinstance(payload, dict):
        raise WireFormatError(f"frame must be a msgpack map, got {type(payload).__name__}")
    return payload


def require_frame_keys(payload: WireMap) -> None:
    keys = set(payload)
    missing = sorted(FRAME_KEYS - keys)
    unexpected = sorted(str(key) for key in keys - FRAME_KEYS)
    if missing or unexpected:
        raise WireFormatError(f"frame keys mismatch: missing {missing}, unexpected {unexpected}")


def read_float(payload: WireMap, key: str) -> float:
    value = payload[key]
    if not isinstance(value, float):
        raise WireFormatError(f"{key} must be a float, got {type(value).__name__}")
    return value


def read_int(payload: WireMap, key: str) -> int:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise WireFormatError(f"{key} must be an int, got {type(value).__name__}")
    return value


def read_array(payload: WireMap, key: str, length: int) -> Float32Array:
    value = payload[key]
    expected_bytes = length * WIRE_FLOAT32.itemsize
    if not isinstance(value, bytes) or len(value) != expected_bytes:
        raise WireFormatError(f"{key} must be {expected_bytes} bytes of little-endian float32")
    return np.frombuffer(value, dtype=WIRE_FLOAT32).astype(np.float32)
