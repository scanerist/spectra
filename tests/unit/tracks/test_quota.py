import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.tracks.adapters.memory import InMemoryUploadQuota
from spectra.tracks.application.admission import UploadAdmission
from spectra.tracks.domain.errors import InvalidQuotaError, UploadQuotaExceededError
from spectra.tracks.domain.quota import QuotaDecision, UploadQuotaPolicy
from tests.fakes import ExhaustedQuota, FakeClock

HOUR_S = 3_600.0
POLICY = UploadQuotaPolicy(uploads=3, window_s=HOUR_S)


def test_uploads_within_the_quota_are_allowed() -> None:
    assert POLICY.decide(used=3, now_s=10.0) == QuotaDecision(allowed=True, retry_after_s=0.0)


def test_an_upload_over_the_quota_waits_for_the_next_window() -> None:
    assert POLICY.decide(used=4, now_s=HOUR_S + 600.0) == QuotaDecision(
        allowed=False, retry_after_s=3_000.0
    )


@given(now_s=st.floats(min_value=0.0, max_value=1e9, allow_nan=False))
def test_the_wait_never_exceeds_one_window(now_s: float) -> None:
    decision = POLICY.decide(used=4, now_s=now_s)
    assert 0.0 < decision.retry_after_s <= HOUR_S


@pytest.mark.parametrize(
    ("uploads", "window_s"),
    [(0, HOUR_S), (1, 0.0), (1, float("inf"))],
    ids=["no-uploads", "no-window", "endless-window"],
)
def test_a_quota_must_allow_something_within_a_finite_window(uploads: int, window_s: float) -> None:
    with pytest.raises(InvalidQuotaError):
        UploadQuotaPolicy(uploads=uploads, window_s=window_s)


@pytest.mark.anyio
async def test_memory_quota_counts_each_client_separately() -> None:
    quota = InMemoryUploadQuota(policy=POLICY, clock=FakeClock(start_s=100.0))
    first = [await quota.spend("1.2.3.4") for _ in range(4)]
    assert [decision.allowed for decision in first] == [True, True, True, False]
    assert (await quota.spend("5.6.7.8")).allowed


@pytest.mark.anyio
async def test_memory_quota_starts_over_in_the_next_window() -> None:
    clock = FakeClock(start_s=100.0)
    quota = InMemoryUploadQuota(policy=POLICY, clock=clock)
    for _ in range(4):
        await quota.spend("1.2.3.4")
    clock.advance(HOUR_S)
    assert (await quota.spend("1.2.3.4")).allowed


@pytest.mark.anyio
async def test_admission_refuses_a_client_over_its_quota() -> None:
    admission = UploadAdmission(quota=ExhaustedQuota(retry_after_s=12.5))
    with pytest.raises(UploadQuotaExceededError) as refused:
        await admission.admit("1.2.3.4")
    assert refused.value.retry_after_s == 12.5


@pytest.mark.anyio
async def test_a_refunded_upload_frees_its_place() -> None:
    quota = InMemoryUploadQuota(policy=POLICY, clock=FakeClock(start_s=100.0))
    for _ in range(3):
        await quota.spend("1.2.3.4")
    await quota.refund("1.2.3.4")
    assert (await quota.spend("1.2.3.4")).allowed
    assert not (await quota.spend("1.2.3.4")).allowed


@pytest.mark.anyio
async def test_a_refund_without_uploads_changes_nothing() -> None:
    quota = InMemoryUploadQuota(policy=POLICY, clock=FakeClock(start_s=100.0))
    await quota.refund("1.2.3.4")
    decisions = [await quota.spend("1.2.3.4") for _ in range(4)]
    assert [decision.allowed for decision in decisions] == [True, True, True, False]
