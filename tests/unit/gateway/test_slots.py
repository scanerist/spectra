import pytest

from spectra.gateway.errors import ApiError, ErrorCode
from spectra.gateway.slots import InvalidSlotLimitsError, SlotLimits, Slots

LIMITS = SlotLimits(total=3, per_client=2, retry_after_s=5.0)


def refusal(slots: Slots, client: str) -> ApiError:
    with pytest.raises(ApiError) as caught:
        slots.take(client)
    return caught.value


def test_a_client_holding_its_share_is_rate_limited_with_a_retry_delay() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    slots.take("a")
    slots.take("a")
    error = refusal(slots, "a")
    assert error.code is ErrorCode.RATE_LIMITED
    assert error.retry_after_s == 5.0
    slots.take("b")


def test_the_server_is_busy_once_every_slot_is_held() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    slots.take("a")
    slots.take("b")
    slots.take("c")
    assert refusal(slots, "d").code is ErrorCode.BUSY


def test_a_released_slot_can_be_taken_again() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    first = slots.take("a")
    slots.take("a")
    first.release()
    slots.take("a")
    assert slots.held == 2


def test_releasing_a_slot_twice_frees_it_once() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    slot = slots.take("a")
    slots.take("a")
    slot.release()
    slot.release()
    assert slots.held == 1
    slots.take("a")
    assert refusal(slots, "a").code is ErrorCode.RATE_LIMITED


@pytest.mark.parametrize(
    ("total", "per_client", "retry_after_s"),
    [(0, 1, 1.0), (1, 0, 1.0), (1, 2, 1.0), (1, 1, 0.0)],
    ids=["no-total", "no-share", "share-above-total", "no-retry"],
)
def test_limits_must_be_positive_and_consistent(
    total: int, per_client: int, retry_after_s: float
) -> None:
    with pytest.raises(InvalidSlotLimitsError):
        SlotLimits(total=total, per_client=per_client, retry_after_s=retry_after_s)
