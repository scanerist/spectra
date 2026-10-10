import io
from collections.abc import Mapping
from typing import Final

import numpy as np
import soundfile
import soxr

from spectra.analysis.application.ports import AudioFormat, AudioProbe
from spectra.analysis.domain.errors import UndecodableAudioError, UnsupportedFormatError
from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ, AudioSignal

CONTAINER_FORMATS: Final[Mapping[str, AudioFormat]] = {
    "WAV": AudioFormat.WAV,
    "WAVEX": AudioFormat.WAV,
    "RF64": AudioFormat.WAV,
    "FLAC": AudioFormat.FLAC,
    "OGG": AudioFormat.OGG,
    "MP3": AudioFormat.MP3,
}
RESAMPLE_QUALITY: Final = "HQ"
MAX_SAMPLE_RATE_HZ: Final = 192_000
MAX_CHANNELS: Final = 8


class SoundfileDecoder:
    def probe(self, data: bytes) -> AudioProbe:
        try:
            info = soundfile.info(io.BytesIO(data))
        except soundfile.SoundFileError as error:
            raise UnsupportedFormatError("expected mp3, wav, flac or ogg") from error
        container = str(info.format)
        audio_format = CONTAINER_FORMATS.get(container)
        if audio_format is None:
            raise UnsupportedFormatError(f"expected mp3, wav, flac or ogg, got {container.lower()}")
        if info.samplerate > MAX_SAMPLE_RATE_HZ:
            limit = f"sample rates above {MAX_SAMPLE_RATE_HZ} Hz are not supported"
            raise UnsupportedFormatError(f"{limit}, got {info.samplerate}")
        if info.channels > MAX_CHANNELS:
            raise UnsupportedFormatError(
                f"more than {MAX_CHANNELS} channels are not supported, got {info.channels}"
            )
        return AudioProbe(
            audio_format=audio_format,
            duration_s=float(info.duration),
            sample_rate_hz=int(info.samplerate),
            channel_count=int(info.channels),
        )

    def decode(self, data: bytes) -> AudioSignal:
        self.probe(data)
        try:
            frames, sample_rate_hz = soundfile.read(
                io.BytesIO(data), dtype="float32", always_2d=True
            )
        except soundfile.SoundFileError as error:
            raise UndecodableAudioError(f"the file cannot be decoded: {error}") from error
        if frames.shape[0] == 0:
            raise UndecodableAudioError("the file holds no audio frames")
        mono = np.asarray(frames.mean(axis=1), dtype=np.float32)
        if sample_rate_hz != ANALYSIS_SAMPLE_RATE_HZ:
            mono = np.asarray(
                soxr.resample(
                    mono, sample_rate_hz, ANALYSIS_SAMPLE_RATE_HZ, quality=RESAMPLE_QUALITY
                ),
                dtype=np.float32,
            )
        return AudioSignal(samples=mono)
