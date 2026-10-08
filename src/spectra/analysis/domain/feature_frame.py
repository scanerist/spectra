from dataclasses import dataclass

from spectra.analysis.domain.levels import Levels
from spectra.analysis.domain.peaks import Peaks
from spectra.analysis.domain.ranges import require_time, require_unit_interval
from spectra.analysis.domain.spectrum import Spectrum
from spectra.analysis.domain.tempo import BeatPosition, Tempo
from spectra.analysis.domain.waveform import Waveform


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureFrame:
    time_s: float
    spectrum: Spectrum
    waveform: Waveform
    peaks: Peaks
    levels: Levels
    tempo: Tempo
    position: BeatPosition
    energy: float

    def __post_init__(self) -> None:
        require_time(self.time_s)
        require_unit_interval("energy", self.energy)
