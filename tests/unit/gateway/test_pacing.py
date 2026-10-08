import math
from typing import Final

import pytest

from spectra.gateway.errors import InvalidFrameRateError
from spectra.gateway.pacing import FramePacer

FRAME_RATE_HZ: Final = 60.0
PERIOD_S: Final = 1.0 / FRAME_RATE_HZ


def test_period_is_reciprocal_of_frame_rate() -> None:
    assert FramePacer(frame_rate_hz=FRAME_RATE_HZ, start_s=0.0).frame_period_s == PERIOD_S


@pytest.mark.parametrize(
    "frame_rate_hz", [0.0, -60.0, math.nan, math.inf], ids=["zero", "negative", "nan", "inf"]
)
def test_rejects_invalid_frame_rate(frame_rate_hz: float) -> None:
    with pytest.raises(InvalidFrameRateError):
        FramePacer(frame_rate_hz=frame_rate_hz, start_s=0.0)


def test_steady_rate_sleeps_one_period_per_frame() -> None:
    pacer = FramePacer(frame_rate_hz=FRAME_RATE_HZ, start_s=10.0)
    delays_s = [pacer.delay_s(10.0 + frame * PERIOD_S) for frame in range(5)]
    assert delays_s == pytest.approx([PERIOD_S] * 5)


def test_slow_frame_shortens_the_next_sleep() -> None:
    pacer = FramePacer(frame_rate_hz=FRAME_RATE_HZ, start_s=0.0)
    assert pacer.delay_s(0.01) == pytest.approx(PERIOD_S - 0.01)


def test_lateness_within_one_frame_is_caught_up_without_sleeping() -> None:
    pacer = FramePacer(frame_rate_hz=FRAME_RATE_HZ, start_s=0.0)
    assert pacer.delay_s(1.5 * PERIOD_S) == 0.0
    assert pacer.delay_s(1.5 * PERIOD_S) == pytest.approx(0.5 * PERIOD_S)


def test_resyncs_after_a_stall_without_bursting() -> None:
    pacer = FramePacer(frame_rate_hz=FRAME_RATE_HZ, start_s=0.0)
    stall_end_s = 10 * PERIOD_S
    assert pacer.delay_s(stall_end_s) == 0.0
    delays_s = [pacer.delay_s(stall_end_s + frame * PERIOD_S) for frame in range(3)]
    assert delays_s == pytest.approx([PERIOD_S] * 3)
