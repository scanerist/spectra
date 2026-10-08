import math

import msgpack
import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import PEAK_COUNT, Peak, Peaks
from spectra.analysis.domain.spectrum import BAND_COUNT, Spectrum
from spectra.analysis.domain.tempo import BEATS_PER_BAR, MAX_BPM, MIN_BPM, BeatPosition, Tempo
from spectra.analysis.domain.waveform import WAVEFORM_LENGTH, Waveform
from spectra.gateway.errors import WireFormatError
from spectra.gateway.wire.frame_codec import PROTOCOL_VERSION, decode_frame, encode_frame

unit = st.floats(min_value=0.0, max_value=1.0)


def float32_arrays(length: int, *, low: float, high: float) -> st.SearchStrategy[np.ndarray]:
    elements = st.floats(min_value=low, max_value=high, width=32)
    return arrays(np.float32, length, elements=elements)


frames = st.builds(
    FeatureFrame,
    time_s=st.floats(min_value=0.0, max_value=1e7),
    spectrum=st.builds(Spectrum, bands=float32_arrays(BAND_COUNT, low=0.0, high=1.0)),
    waveform=st.builds(Waveform, samples=float32_arrays(WAVEFORM_LENGTH, low=-1.0, high=1.0)),
    peaks=st.lists(
        st.builds(
            Peak,
            freq_hz=st.floats(min_value=1.0, max_value=24_000.0),
            amplitude=unit,
            phase_rad=st.floats(min_value=-2 * math.pi, max_value=2 * math.pi),
        ),
        max_size=PEAK_COUNT,
    ).map(Peaks.ranked),
    levels=st.builds(Levels, kick=unit, bass=unit, mid=unit, high=unit),
    tempo=st.builds(Tempo, bpm=st.floats(min_value=MIN_BPM, max_value=MAX_BPM)),
    position=st.builds(
        BeatPosition,
        bar=st.integers(min_value=0, max_value=2**31),
        beat_in_bar=st.integers(min_value=0, max_value=BEATS_PER_BAR - 1),
        phase=st.floats(min_value=0.0, max_value=1.0, exclude_max=True),
    ),
    energy=unit,
)


def make_frame() -> FeatureFrame:
    return FeatureFrame(
        time_s=2.0,
        spectrum=Spectrum(bands=np.full(BAND_COUNT, 0.5, dtype=np.float32)),
        waveform=Waveform(samples=np.zeros(WAVEFORM_LENGTH, dtype=np.float32)),
        peaks=Peaks(items=(Peak(freq_hz=55.0, amplitude=1.0, phase_rad=0.0),)),
        levels=Levels(kick=1.0, bass=0.5, mid=0.25, high=0.0),
        tempo=Tempo(bpm=128.0),
        position=BeatPosition(bar=1, beat_in_bar=0, phase=0.0),
        energy=0.5,
    )


def wire_map(frame: FeatureFrame) -> dict[str, object]:
    unpacked: dict[str, object] = msgpack.unpackb(encode_frame(frame), raw=False)
    return unpacked


def pack(payload: dict[str, object]) -> bytes:
    packed: bytes = msgpack.packb(payload, use_bin_type=True)
    return packed


@given(frame=frames)
def test_decode_encode_round_trip_is_identity(frame: FeatureFrame) -> None:
    data = encode_frame(frame)
    assert encode_frame(decode_frame(data)) == data


@given(frame=frames)
def test_decoded_frame_matches_the_encoded_one(frame: FeatureFrame) -> None:
    decoded = decode_frame(encode_frame(frame))
    assert decoded.time_s == frame.time_s
    assert decoded.spectrum == frame.spectrum
    assert decoded.waveform == frame.waveform
    assert decoded.levels == frame.levels
    assert decoded.tempo == frame.tempo
    assert decoded.position == frame.position
    assert decoded.energy == frame.energy
    np.testing.assert_array_equal(decoded.peaks.as_padded_array(), frame.peaks.as_padded_array())


def test_integer_bpm_is_still_encoded_as_a_float() -> None:
    frame = make_frame()
    integral = FeatureFrame(
        time_s=frame.time_s,
        spectrum=frame.spectrum,
        waveform=frame.waveform,
        peaks=frame.peaks,
        levels=frame.levels,
        tempo=Tempo(bpm=128),
        position=frame.position,
        energy=frame.energy,
    )
    assert type(wire_map(integral)["bpm"]) is float


def test_frame_is_under_three_kilobytes() -> None:
    assert len(encode_frame(make_frame())) < 3_000


def test_decode_rejects_wrong_version() -> None:
    payload = wire_map(make_frame()) | {"v": PROTOCOL_VERSION + 1}
    with pytest.raises(WireFormatError, match="version"):
        decode_frame(pack(payload))


def test_decode_rejects_missing_key() -> None:
    payload = wire_map(make_frame())
    del payload["energy"]
    with pytest.raises(WireFormatError, match="energy"):
        decode_frame(pack(payload))


def test_decode_rejects_unexpected_key() -> None:
    payload = wire_map(make_frame()) | {"extra": 1}
    with pytest.raises(WireFormatError, match="extra"):
        decode_frame(pack(payload))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("bands", b"\x00" * 252),
        ("waveform", [0.0] * WAVEFORM_LENGTH),
        ("kick", "loud"),
        ("bar", 1.0),
        ("beat_in_bar", True),
        ("t", 1),
    ],
    ids=["short-bands", "waveform-not-bin", "kick-not-number", "bar-float", "beat-bool", "t-int"],
)
def test_decode_rejects_wrong_field_types(key: str, value: object) -> None:
    payload = wire_map(make_frame()) | {key: value}
    with pytest.raises(WireFormatError, match=key):
        decode_frame(pack(payload))


def test_decode_rejects_domain_invariant_violations() -> None:
    payload = wire_map(make_frame()) | {"energy": 1.5}
    with pytest.raises(WireFormatError):
        decode_frame(pack(payload))


def test_decode_rejects_non_map_payload() -> None:
    with pytest.raises(WireFormatError):
        decode_frame(pack_list())


def pack_list() -> bytes:
    packed: bytes = msgpack.packb([1, 2, 3])
    return packed


@given(data=st.binary(max_size=4_096))
def test_decode_rejects_garbage_with_wire_format_error(data: bytes) -> None:
    with pytest.raises(WireFormatError):
        decode_frame(data)
