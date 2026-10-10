import io
from collections.abc import Iterator, Mapping
from typing import Final

import numpy as np
import soundfile
import soxr

from spectra.analysis.application.ports import AudioFormat, AudioProbe
from spectra.analysis.domain.errors import UndecodableAudioError, UnsupportedFormatError
from spectra.analysis.domain.ranges import Float32Array
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
BLOCK_FRAMES: Final = 65_536
EMPTY_BLOCK: Final[Float32Array] = np.zeros(0, dtype=np.float32)


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
        probe = self.probe(data)
        try:
            mono = decoded_mono(data, probe.sample_rate_hz)
        except soundfile.SoundFileError as error:
            raise UndecodableAudioError(f"the file cannot be decoded: {error}") from error
        if mono.size == 0:
            raise UndecodableAudioError("the file holds no audio frames")
        mono.flags.writeable = False
        return AudioSignal(samples=mono)


def decoded_mono(data: bytes, sample_rate_hz: int) -> Float32Array:
    with soundfile.SoundFile(io.BytesIO(data)) as audio:
        blocks = audio.blocks(BLOCK_FRAMES, dtype="float32", always_2d=True)
        mono_blocks = (np.mean(block, axis=1, dtype=np.float32) for block in blocks)
        return np.concatenate([*resampled(mono_blocks, sample_rate_hz), EMPTY_BLOCK])


def resampled(blocks: Iterator[Float32Array], sample_rate_hz: int) -> Iterator[Float32Array]:
    if sample_rate_hz == ANALYSIS_SAMPLE_RATE_HZ:
        yield from blocks
        return
    stream = soxr.ResampleStream(
        sample_rate_hz, ANALYSIS_SAMPLE_RATE_HZ, 1, dtype="float32", quality=RESAMPLE_QUALITY
    )
    yield from (stream.resample_chunk(block) for block in blocks)
    yield stream.resample_chunk(EMPTY_BLOCK, last=True)
