import pytest

from spectra.shared.clock import Clock, MonotonicClock
from tests.fakes import FakeClock


def test_monotonic_clock_never_goes_back() -> None:
    clock: Clock = MonotonicClock()
    readings_s = [clock.now_s() for _ in range(1_000)]
    assert readings_s == sorted(readings_s)


@pytest.mark.anyio
async def test_monotonic_clock_sleep_waits_at_least_the_duration() -> None:
    clock: Clock = MonotonicClock()
    before_s = clock.now_s()
    await clock.sleep(0.02)
    assert clock.now_s() - before_s >= 0.015


@pytest.mark.anyio
async def test_fake_clock_sleep_advances_time_and_records_it() -> None:
    clock = FakeClock(start_s=10.0)
    fake: Clock = clock
    await fake.sleep(0.25)
    assert fake.now_s() == 10.25
    assert clock.sleeps_s == [0.25]
