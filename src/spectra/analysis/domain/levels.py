from dataclasses import dataclass

from spectra.analysis.domain.ranges import require_unit_interval


@dataclass(frozen=True, slots=True, kw_only=True)
class Levels:
    kick: float
    bass: float
    mid: float
    high: float

    def __post_init__(self) -> None:
        require_unit_interval("kick level", self.kick)
        require_unit_interval("bass level", self.bass)
        require_unit_interval("mid level", self.mid)
        require_unit_interval("high level", self.high)
