import struct
from pathlib import Path
from typing import Final

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from spectra.analysis.domain.ranges import Float32Array
from spectra.gateway.timeline_codec import encode_timeline, quantise, timeline_length
from tests.contract.timeline_fixture import GOLDEN_BARS, GOLDEN_FRAMES, golden_analysis

GOLDEN_PATH: Final = Path(__file__).parent / "golden" / "timeline_v1.bin"
F: Final = GOLDEN_FRAMES
B: Final = GOLDEN_BARS
PEAKS_AT: Final = 16
BANDS_AT: Final = 16 + 64 * B
LEVELS_AT: Final = 16 + 64 * B + 64 * F
FOURIER_AT: Final = 16 + 64 * B + 69 * F


@pytest.fixture
def golden() -> bytes:
    return GOLDEN_PATH.read_bytes()


def test_encoding_matches_the_golden_bytes(golden: bytes) -> None:
    assert encode_timeline(golden_analysis()) == golden


def test_header_carries_version_frame_rate_and_counts(golden: bytes) -> None:
    assert struct.unpack_from("<IfII", golden, 0) == (1, 44_100 / 512, F, B)


def test_length_is_16_plus_264_per_bar_plus_69_per_frame(golden: bytes) -> None:
    assert len(golden) == 16 + 264 * B + 69 * F == timeline_length(frame_count=F, bar_count=B)


def test_peaks_come_first_as_aligned_float32_rows(golden: bytes) -> None:
    assert PEAKS_AT % 4 == 0
    peaks = np.frombuffer(golden, dtype="<f4", count=B * 8 * 2, offset=PEAKS_AT).reshape(B, 8, 2)
    np.testing.assert_array_equal(peaks[0, :2], [[55.0, 1.0], [110.0, 0.5]])
    assert not peaks[0, 2:].any()
    assert not peaks[1].any()


def test_bands_follow_the_peaks_one_byte_per_band(golden: bytes) -> None:
    bands = np.frombuffer(golden, dtype=np.uint8, count=F * 64, offset=BANDS_AT).reshape(F, 64)
    np.testing.assert_array_equal(bands.ravel()[:300], np.arange(300) % 256)


def test_levels_follow_the_bands_as_kick_bass_mid_high_energy(golden: bytes) -> None:
    levels = np.frombuffer(golden, dtype=np.uint8, count=F * 5, offset=LEVELS_AT).reshape(F, 5)
    np.testing.assert_array_equal(levels[0], [0, 64, 128, 191, 255])
    np.testing.assert_array_equal(levels[1], [255, 0, 1, 254, 128])


def test_fourier_closes_the_timeline(golden: bytes) -> None:
    fourier = np.frombuffer(golden, dtype=np.uint8, count=B * 200, offset=FOURIER_AT)
    assert len(golden) == FOURIER_AT + B * 200
    np.testing.assert_array_equal(fourier.reshape(B, 200)[:, [0, -1]], [[0, 255], [255, 0]])


@given(values=arrays(np.float32, st.integers(1, 64), elements=st.floats(-2.0, 2.0, width=32)))
def test_quantisation_stays_within_half_a_step(values: Float32Array) -> None:
    decoded = quantise(values).astype(np.float64) / 255.0
    expected = np.clip(values.astype(np.float64), 0.0, 1.0)
    assert np.all(np.abs(decoded - expected) <= 1 / 510 + 1e-12)


def test_quantisation_maps_the_ends_exactly() -> None:
    values = np.array([0.0, 1.0, -0.5, 1.5], dtype=np.float32)
    np.testing.assert_array_equal(quantise(values), [0, 255, 0, 255])
