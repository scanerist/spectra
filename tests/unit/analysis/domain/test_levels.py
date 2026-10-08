import math

import pytest

from spectra.analysis.domain.errors import OutOfRangeError
from spectra.analysis.domain.levels import Levels

IN_RANGE: dict[str, float] = {"kick": 1.0, "bass": 0.0, "mid": 0.5, "high": 0.25}


def test_levels_accept_unit_interval_bounds() -> None:
    levels = Levels(kick=1.0, bass=0.0, mid=0.5, high=0.25)
    assert (levels.kick, levels.bass, levels.mid, levels.high) == (1.0, 0.0, 0.5, 0.25)


@pytest.mark.parametrize("field", ["kick", "bass", "mid", "high"], ids=str)
@pytest.mark.parametrize("value", [-0.01, 1.01, math.nan], ids=["negative", "above-one", "nan"])
def test_levels_reject_out_of_range(field: str, value: float) -> None:
    values = IN_RANGE | {field: value}
    with pytest.raises(OutOfRangeError):
        Levels(kick=values["kick"], bass=values["bass"], mid=values["mid"], high=values["high"])
