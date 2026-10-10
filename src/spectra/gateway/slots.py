from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from spectra.gateway.errors import ApiError, ErrorCode, GatewayError
from spectra.tracks.domain.quota import UploadSource


class InvalidSlotLimitsError(GatewayError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class SlotLimits:
    total: int
    per_address: int
    per_network: int
    retry_after_s: float

    def __post_init__(self) -> None:
        if not 0 < self.per_address <= self.per_network <= self.total:
            raise InvalidSlotLimitsError(
                "slot limits need 0 < per address <= per network <= total, got "
                f"{self.per_address}, {self.per_network} and {self.total}"
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
        self._by_address: Counter[str] = Counter()
        self._by_network: Counter[str] = Counter()

    @property
    def held(self) -> int:
        return self._by_address.total()

    def take(self, source: UploadSource) -> Slot:
        if self.held >= self._limits.total:
            raise ApiError(ErrorCode.BUSY, f"the server already serves too many {self._name}")
        if (
            self._by_address[source.address] >= self._limits.per_address
            or self._by_network[source.network] >= self._limits.per_network
        ):
            raise ApiError(
                ErrorCode.RATE_LIMITED,
                f"too many {self._name} from this address or its network",
                retry_after_s=self._limits.retry_after_s,
            )
        self._by_address[source.address] += 1
        self._by_network[source.network] += 1
        return Slot(lambda: self._free(source))

    def _free(self, source: UploadSource) -> None:
        self._by_address -= Counter({source.address: 1})
        self._by_network -= Counter({source.network: 1})
