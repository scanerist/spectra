from dataclasses import dataclass

from spectra.analysis.application.ports import AudioDecoder
from spectra.analysis.domain.track_analysis import StageListener, analyse_signal
from spectra.tracks.application.ports import TimelineEncoder
from spectra.tracks.domain.track import TrackSummary


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPipeline:
    decoder: AudioDecoder
    encoder: TimelineEncoder

    def run(self, data: bytes, on_stage: StageListener) -> tuple[TrackSummary, bytes]:
        analysis = analyse_signal(self.decoder.decode(data), on_stage=on_stage)
        return TrackSummary.of_analysis(analysis), self.encoder(analysis)
