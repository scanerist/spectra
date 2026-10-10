from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from spectra.analysis.domain.signal import AudioSignal


class AudioFormat(StrEnum):
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"
    OGG = "ogg"


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioProbe:
    audio_format: AudioFormat
    duration_s: float
    sample_rate_hz: int
    channel_count: int


class AudioDecoder(Protocol):
    def probe(self, data: bytes) -> AudioProbe: ...

    def decode(self, data: bytes) -> AudioSignal: ...
