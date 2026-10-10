import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from spectra.tracks.domain.errors import InvalidQuotaError

TOTAL_SCOPE_KEY: Final = "total"
MIN_WAIT_S: Final = 0.001


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotaDecision:
    allowed: bool
    retry_after_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadSource:
    address: str
    network: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotaScope:
    key: str
    limit: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadQuotaPolicy:
    per_address: int
    per_network: int
    total: int
    window_s: float

    def __post_init__(self) -> None:
        if min(self.per_address, self.per_network, self.total) < 1:
            raise InvalidQuotaError(
                "a quota allows at least one upload per address, network and in total, got "
                f"{self.per_address}, {self.per_network} and {self.total}"
            )
        if not (math.isfinite(self.window_s) and self.window_s > 0.0):
            raise InvalidQuotaError(f"a quota window must be positive, got {self.window_s}")

    def scopes(self, source: UploadSource) -> tuple[QuotaScope, ...]:
        return (
            QuotaScope(key=f"address:{source.address}", limit=self.per_address),
            QuotaScope(key=f"network:{source.network}", limit=self.per_network),
            QuotaScope(key=TOTAL_SCOPE_KEY, limit=self.total),
        )

    def decide(self, *, blocking_uploads_s: Sequence[float], now_s: float) -> QuotaDecision:
        if not blocking_uploads_s:
            return QuotaDecision(allowed=True, retry_after_s=0.0)
        free_at_s = max(blocking_uploads_s) + self.window_s
        wait_s = min(max(free_at_s - now_s, MIN_WAIT_S), self.window_s)
        return QuotaDecision(allowed=False, retry_after_s=wait_s)
