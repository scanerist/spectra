import pytest

from spectra.gateway.errors import ApiError, ErrorCode
from spectra.gateway.slots import InvalidSlotLimitsError, SlotLimits, Slots
from spectra.tracks.domain.quota import UploadSource

LIMITS = SlotLimits(total=4, per_address=2, per_network=3, retry_after_s=5.0)
HOME = UploadSource(address="2001:db8:1:1::/64", network="2001:db8:1::/48")
NEIGHBOUR = UploadSource(address="2001:db8:1:2::/64", network="2001:db8:1::/48")


def source(index: int) -> UploadSource:
    return UploadSource(address=f"203.0.113.{index}", network=f"203.0.113.{index}")


def refusal(slots: Slots, requester: UploadSource) -> ApiError:
    with pytest.raises(ApiError) as caught:
        slots.take(requester)
    return caught.value


def test_an_address_holding_its_share_is_rate_limited_with_a_retry_delay() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    slots.take(source(1))
    slots.take(source(1))
    error = refusal(slots, source(1))
    assert error.code is ErrorCode.RATE_LIMITED
    assert error.retry_after_s == 5.0
    slots.take(source(2))


def test_addresses_of_one_network_share_its_slots() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    slots.take(HOME)
    slots.take(HOME)
    slots.take(NEIGHBOUR)
    assert refusal(slots, NEIGHBOUR).code is ErrorCode.RATE_LIMITED
    slots.take(source(1))


def test_the_server_is_busy_once_every_slot_is_held() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    for index in range(4):
        slots.take(source(index))
    assert refusal(slots, source(9)).code is ErrorCode.BUSY


def test_a_released_slot_can_be_taken_again() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    first = slots.take(HOME)
    slots.take(NEIGHBOUR)
    slots.take(NEIGHBOUR)
    first.release()
    slots.take(HOME)
    assert slots.held == 3


def test_releasing_a_slot_twice_frees_it_once() -> None:
    slots = Slots(limits=LIMITS, name="event streams")
    slot = slots.take(source(1))
    slots.take(source(1))
    slot.release()
    slot.release()
    assert slots.held == 1
    slots.take(source(1))
    assert refusal(slots, source(1)).code is ErrorCode.RATE_LIMITED


@pytest.mark.parametrize(
    ("total", "per_address", "per_network", "retry_after_s"),
    [(0, 1, 1, 1.0), (1, 0, 1, 1.0), (2, 2, 1, 1.0), (1, 1, 2, 1.0), (1, 1, 1, 0.0)],
    ids=["no-total", "no-share", "address-above-network", "network-above-total", "no-retry"],
)
def test_limits_must_be_positive_and_nested(
    total: int, per_address: int, per_network: int, retry_after_s: float
) -> None:
    with pytest.raises(InvalidSlotLimitsError):
        SlotLimits(
            total=total,
            per_address=per_address,
            per_network=per_network,
            retry_after_s=retry_after_s,
        )
