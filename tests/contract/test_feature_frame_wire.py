from pathlib import Path
from typing import Final

import msgpack
import numpy as np
import pytest
from numpy.typing import NDArray

from engine.protocol import FeatureFrame

GOLDEN_PATH: Final = Path(__file__).parent / "golden" / "feature_frame_v0.bin"

CONTRACT_KEYS: Final = (
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
)

GOLDEN_PEAK_ROWS: Final = (
    (55.0, 0.75, 0.5),
    (440.0, 0.5, 1.25),
    (8_000.0, 0.25, 3.0),
)


def golden_bands() -> NDArray[np.float32]:
    return (np.arange(64) / 64).astype(np.float32)


def golden_waveform() -> NDArray[np.float32]:
    return np.linspace(-1.0, 1.0, 512, endpoint=False).astype(np.float32)


def golden_peaks() -> NDArray[np.float32]:
    padded = np.zeros((8, 3), dtype=np.float32)
    padded[: len(GOLDEN_PEAK_ROWS)] = GOLDEN_PEAK_ROWS
    return padded


def golden_frame() -> FeatureFrame:
    return FeatureFrame(
        t=1.5,
        bands=golden_bands(),
        waveform=golden_waveform(),
        peaks=golden_peaks(),
        kick=0.75,
        bass=0.5,
        mid=0.25,
        high=0.125,
        bpm=128.0,
        beat_phase=0.25,
        bar=3,
        beat_in_bar=2,
        energy=0.625,
    )


@pytest.fixture
def golden_bytes() -> bytes:
    return GOLDEN_PATH.read_bytes()


@pytest.fixture
def golden_map(golden_bytes: bytes) -> dict[str, object]:
    unpacked: dict[str, object] = msgpack.unpackb(golden_bytes, raw=False)
    return unpacked


def test_golden_has_exactly_contract_keys_in_order(golden_map: dict[str, object]) -> None:
    assert tuple(golden_map) == CONTRACT_KEYS


def test_golden_protocol_version_is_zero(golden_map: dict[str, object]) -> None:
    assert golden_map["v"] == 0


@pytest.mark.parametrize(
    ("key", "byte_length"),
    [("bands", 256), ("waveform", 2048), ("peaks", 96)],
    ids=["bands", "waveform", "peaks"],
)
def test_golden_array_byte_lengths(
    golden_map: dict[str, object], key: str, byte_length: int
) -> None:
    value = golden_map[key]
    assert isinstance(value, bytes)
    assert len(value) == byte_length


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("bands", golden_bands().ravel()),
        ("waveform", golden_waveform().ravel()),
        ("peaks", golden_peaks().ravel()),
    ],
    ids=["bands", "waveform", "peaks"],
)
def test_golden_arrays_are_little_endian_float32_row_major(
    golden_map: dict[str, object], key: str, expected: NDArray[np.float32]
) -> None:
    value = golden_map[key]
    assert isinstance(value, bytes)
    np.testing.assert_array_equal(np.frombuffer(value, dtype="<f4"), expected)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("t", 1.5),
        ("kick", 0.75),
        ("bass", 0.5),
        ("mid", 0.25),
        ("high", 0.125),
        ("bpm", 128.0),
        ("beat_phase", 0.25),
        ("energy", 0.625),
    ],
    ids=["t", "kick", "bass", "mid", "high", "bpm", "beat_phase", "energy"],
)
def test_golden_scalars_are_floats(
    golden_map: dict[str, object], key: str, expected: float
) -> None:
    value = golden_map[key]
    assert type(value) is float
    assert value == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [("bar", 3), ("beat_in_bar", 2)],
    ids=["bar", "beat_in_bar"],
)
def test_golden_counters_are_ints(golden_map: dict[str, object], key: str, expected: int) -> None:
    value = golden_map[key]
    assert type(value) is int
    assert value == expected


def test_encoder_reproduces_golden_bytes(golden_bytes: bytes) -> None:
    assert golden_frame().pack() == golden_bytes
