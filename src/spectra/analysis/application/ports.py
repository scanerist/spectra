from typing import Protocol

from spectra.analysis.domain.feature_frame import FeatureFrame


class FeatureSource(Protocol):
    def latest(self) -> FeatureFrame: ...
