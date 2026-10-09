import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from spectra.analysis.domain.envelopes import (
    RELEASE_FLOOR,
    moving_average,
    normalise_db,
    power_to_db,
    release,
)

FRAME_RATE_HZ = 100.0


def test_release_attacks_instantly() -> None:
    values = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)
    assert release(values, release_s=0.1, frame_rate_hz=FRAME_RATE_HZ)[2] == pytest.approx(1.0)


def test_release_halves_after_release_time_times_ln_two() -> None:
    values = np.zeros(200, dtype=np.float32)
    values[0] = 1.0
    held = release(values, release_s=0.2, frame_rate_hz=FRAME_RATE_HZ)
    half_frame = round(0.2 * math.log(2.0) * FRAME_RATE_HZ)
    assert held[half_frame] == pytest.approx(0.5, abs=0.01)


def test_release_works_column_by_column() -> None:
    values = np.zeros((50, 2), dtype=np.float32)
    values[0, 0] = 1.0
    values[10, 1] = 0.5
    held = release(values, release_s=0.1, frame_rate_hz=FRAME_RATE_HZ)
    assert held[10, 1] == pytest.approx(0.5)
    assert held[5, 1] == pytest.approx(0.0, abs=1e-9)
    assert held[10, 0] == pytest.approx(math.exp(-1.0), rel=1e-4)


@given(values=arrays(np.float32, st.integers(1, 300), elements=st.floats(0.0, 1.0, width=32)))
def test_release_never_drops_below_input_or_rises_above_the_maximum(
    values: np.typing.NDArray[np.float32],
) -> None:
    held = release(values, release_s=0.05, frame_rate_hz=FRAME_RATE_HZ)
    assert np.all((held >= values * (1 - 1e-5)) | (values <= RELEASE_FLOOR * 1.001))
    assert np.all(held <= max(float(values.max()), 1e-30) * (1 + 1e-5))


def test_moving_average_keeps_length_and_constants() -> None:
    values = np.full(10, 0.25, dtype=np.float32)
    np.testing.assert_allclose(moving_average(values, width_frames=4), values)


def test_moving_average_smooths_a_step() -> None:
    values = np.concatenate([np.zeros(10), np.ones(10)]).astype(np.float32)
    smoothed = moving_average(values, width_frames=4)
    assert 0.0 < smoothed[10] < 1.0
    assert smoothed[0] == 0.0
    assert smoothed[-1] == 1.0


def test_power_to_db_clamps_at_the_floor() -> None:
    db = power_to_db(np.array([1.0, 0.01, 0.0], dtype=np.float32), floor_db=-100.0)
    np.testing.assert_allclose(db, [0.0, -20.0, -100.0], atol=1e-4)


def test_normalise_db_maps_reference_to_one_and_range_below_to_zero() -> None:
    db = np.array([0.0, -30.0, -60.0, -90.0], dtype=np.float32)
    scaled = normalise_db(db, range_db=60.0, percentile=100.0, min_reference_db=-200.0)
    np.testing.assert_allclose(scaled, [1.0, 0.5, 0.0, 0.0])


def test_normalise_db_keeps_quiet_material_quiet() -> None:
    db = np.full(8, -110.0, dtype=np.float32)
    scaled = normalise_db(db, range_db=60.0, percentile=100.0, min_reference_db=-40.0)
    assert not scaled.any()
