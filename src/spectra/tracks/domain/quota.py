import math
from dataclasses import dataclass

from spectra.tracks.domain.errors import InvalidQuotaError


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotaDecision:
    allowed: bool
    retry_after_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadQuotaPolicy:
    uploads: int
    window_s: float

    def __post_init__(self) -> None:
        if self.uploads < 1:
            raise InvalidQuotaError(f"a quota allows at least one upload, got {self.uploads}")
        if not (math.isfinite(self.window_s) and self.window_s > 0.0):
            raise InvalidQuotaError(f"a quota window must be positive, got {self.window_s}")

    def window_of(self, now_s: float) -> int:
        return math.floor(now_s / self.window_s)

    def decide(self, *, used: int, now_s: float) -> QuotaDecision:
        if used <= self.uploads:
            return QuotaDecision(allowed=True, retry_after_s=0.0)
        window_end_s = (self.window_of(now_s) + 1) * self.window_s
        return QuotaDecision(allowed=False, retry_after_s=window_end_s - now_s)
