from enum import StrEnum
from typing import Protocol

from spectra.analysis.domain.signal import AudioSignal


class AudioFormat(StrEnum):
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"
    OGG = "ogg"


class AudioDecoder(Protocol):
    def probe(self, data: bytes) -> AudioFormat: ...

    def decode(self, data: bytes) -> AudioSignal: ...
