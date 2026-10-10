import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.tracks.adapters.memory import InMemoryUploadQuota
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.domain.errors import InvalidQuotaError, UploadQuotaExceededError
from spectra.tracks.domain.quota import QuotaDecision, QuotaScope, UploadQuotaPolicy, UploadSource
from tests.fakes import ExhaustedQuota, FakeClock

HOUR_S = 3_600.0
POLICY = UploadQuotaPolicy(per_address=3, per_network=5, total=8, window_s=HOUR_S)
HOME = UploadSource(address="2001:db8:1:1::/64", network="2001:db8:1::/48")
NEIGHBOUR = UploadSource(address="2001:db8:1:2::/64", network="2001:db8:1::/48")


def source(index: int) -> UploadSource:
    return UploadSource(address=f"203.0.113.{index}", network=f"203.0.113.{index}")


def quota_at(start_s: float = 100.0) -> tuple[InMemoryUploadQuota, FakeClock]:
    clock = FakeClock(start_s=start_s)
    return InMemoryUploadQuota(policy=POLICY, clock=clock), clock


def test_a_source_counts_against_its_address_its_network_and_everyone() -> None:
    assert POLICY.scopes(HOME) == (
        QuotaScope(key="address:2001:db8:1:1::/64", limit=3),
        QuotaScope(key="network:2001:db8:1::/48", limit=5),
        QuotaScope(key="total", limit=8),
    )


def test_an_upload_with_no_full_scope_is_allowed() -> None:
    decision = POLICY.decide(blocking_uploads_s=[], now_s=10.0)
    assert decision == QuotaDecision(allowed=True, retry_after_s=0.0)


def test_a_refused_upload_waits_until_the_oldest_upload_of_every_full_scope_leaves() -> None:
    decision = POLICY.decide(blocking_uploads_s=[600.0, 900.0], now_s=1_000.0)
    assert decision == QuotaDecision(allowed=False, retry_after_s=3_500.0)


def test_a_refusal_always_asks_to_wait_a_little() -> None:
    oldest_s = 1_617.108553965816
    decision = POLICY.decide(blocking_uploads_s=[oldest_s], now_s=oldest_s + (HOUR_S - 1e-13))
    assert not decision.allowed
    assert decision.retry_after_s > 0.0


@given(
    oldest_s=st.floats(min_value=0.0, max_value=HOUR_S, allow_nan=False),
    elapsed_s=st.floats(min_value=0.0, max_value=HOUR_S, exclude_max=True, allow_nan=False),
)
def test_the_wait_never_exceeds_one_window(oldest_s: float, elapsed_s: float) -> None:
    decision = POLICY.decide(blocking_uploads_s=[oldest_s], now_s=oldest_s + elapsed_s)
    assert 0.0 < decision.retry_after_s <= HOUR_S


@pytest.mark.parametrize(
    ("per_address", "per_network", "total", "window_s"),
    [
        (0, 1, 1, HOUR_S),
        (1, 0, 1, HOUR_S),
        (1, 1, 0, HOUR_S),
        (1, 1, 1, 0.0),
        (1, 1, 1, float("inf")),
    ],
    ids=["no-address-uploads", "no-network-uploads", "no-uploads", "no-window", "endless-window"],
)
def test_a_quota_must_allow_something_within_a_finite_window(
    per_address: int, per_network: int, total: int, window_s: float
) -> None:
    with pytest.raises(InvalidQuotaError):
        UploadQuotaPolicy(
            per_address=per_address, per_network=per_network, total=total, window_s=window_s
        )


@pytest.mark.anyio
async def test_memory_quota_counts_each_address_separately() -> None:
    quota, _ = quota_at()
    first = [await quota.spend(source(1)) for _ in range(4)]
    assert [decision.allowed for decision in first] == [True, True, True, False]
    assert (await quota.spend(source(2))).allowed


@pytest.mark.anyio
async def test_addresses_of_one_network_share_its_quota() -> None:
    quota, _ = quota_at()
    homes = [await quota.spend(HOME) for _ in range(3)]
    neighbours = [await quota.spend(NEIGHBOUR) for _ in range(3)]
    assert [decision.allowed for decision in [*homes, *neighbours]] == [True] * 5 + [False]


@pytest.mark.anyio
async def test_everyone_shares_the_total_quota() -> None:
    quota, _ = quota_at()
    decisions = [await quota.spend(source(index)) for index in range(9)]
    assert [decision.allowed for decision in decisions] == [True] * 8 + [False]


@pytest.mark.anyio
async def test_the_window_slides_instead_of_starting_over() -> None:
    quota, clock = quota_at(start_s=HOUR_S - 1.0)
    for _ in range(3):
        await quota.spend(source(1))
    clock.advance(2.0)
    refused = await quota.spend(source(1))
    assert not refused.allowed
    assert refused.retry_after_s == pytest.approx(HOUR_S - 2.0)
    clock.advance(refused.retry_after_s)
    assert (await quota.spend(source(1))).allowed


@pytest.mark.anyio
async def test_a_refused_upload_does_not_use_up_the_quota() -> None:
    quota, clock = quota_at()
    for _ in range(5):
        await quota.spend(source(1))
    clock.advance(HOUR_S)
    decisions = [await quota.spend(source(1)) for _ in range(4)]
    assert [decision.allowed for decision in decisions] == [True, True, True, False]


@pytest.mark.anyio
async def test_admission_refuses_a_source_over_its_quota() -> None:
    admission = UploadAdmission(quota=ExhaustedQuota(retry_after_s=12.5))
    with pytest.raises(UploadQuotaExceededError) as refused:
        await admission.admit(source(1))
    assert refused.value.retry_after_s == 12.5


@pytest.mark.anyio
async def test_a_refunded_upload_frees_its_place_in_every_scope() -> None:
    quota, _ = quota_at()
    for _ in range(3):
        await quota.spend(HOME)
    for _ in range(2):
        await quota.spend(NEIGHBOUR)
    await quota.refund(NEIGHBOUR)
    assert (await quota.spend(NEIGHBOUR)).allowed
    assert not (await quota.spend(NEIGHBOUR)).allowed


@pytest.mark.anyio
async def test_a_refund_without_uploads_changes_nothing() -> None:
    quota, _ = quota_at()
    await quota.refund(source(1))
    decisions = [await quota.spend(source(1)) for _ in range(4)]
    assert [decision.allowed for decision in decisions] == [True, True, True, False]
