from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from spectra.gateway.errors import ApiError, ErrorCode, GatewayError


class InvalidSlotLimitsError(GatewayError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class SlotLimits:
    total: int
    per_client: int
    retry_after_s: float

    def __post_init__(self) -> None:
        if not 0 < self.per_client <= self.total:
            raise InvalidSlotLimitsError(
                f"slot limits need 0 < per client <= total, got {self.per_client} of {self.total}"
            )
        if self.retry_after_s <= 0.0:
            raise InvalidSlotLimitsError(
                f"slot retry delay must be positive, got {self.retry_after_s}"
            )


class Slot:
    def __init__(self, release: Callable[[], None]) -> None:
        self._release = release
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._release()


class Slots:
    def __init__(self, *, limits: SlotLimits, name: str) -> None:
        self._limits = limits
        self._name = name
        self._held: Counter[str] = Counter()

    @property
    def held(self) -> int:
        return self._held.total()

    def take(self, client: str) -> Slot:
        if self.held >= self._limits.total:
            raise ApiError(ErrorCode.BUSY, f"the server already serves too many {self._name}")
        if self._held[client] >= self._limits.per_client:
            raise ApiError(
                ErrorCode.RATE_LIMITED,
                f"too many {self._name} from this address",
                retry_after_s=self._limits.retry_after_s,
            )
        self._held[client] += 1
        return Slot(lambda: self._free(client))

    def _free(self, client: str) -> None:
        self._held[client] -= 1
        if self._held[client] <= 0:
            del self._held[client]
