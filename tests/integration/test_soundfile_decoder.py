from typing import Final

import numpy as np
import pytest

from spectra.analysis.adapters.soundfile_decoder import SoundfileDecoder
from spectra.analysis.application.ports import AudioDecoder, AudioFormat
from spectra.analysis.domain.errors import UndecodableAudioError, UnsupportedFormatError
from spectra.analysis.domain.signal import ANALYSIS_SAMPLE_RATE_HZ
from spectra.analysis.domain.stft import bin_freqs_hz, stft_magnitudes
from tests.audio_files import encoded, tone

CONTAINERS: Final = [
    ("WAV", AudioFormat.WAV),
    ("FLAC", AudioFormat.FLAC),
    ("OGG", AudioFormat.OGG),
    ("MP3", AudioFormat.MP3),
]
CONTAINER_IDS: Final = ["wav", "flac", "ogg", "mp3"]


@pytest.fixture
def decoder() -> AudioDecoder:
    return SoundfileDecoder()


def stereo_tone(sample_rate_hz: int) -> bytes:
    left = tone(1_000.0, 3.0, sample_rate_hz)
    return encoded(np.stack([left, left], axis=1), sample_rate_hz, "WAV")


@pytest.mark.parametrize(("container", "audio_format"), CONTAINERS, ids=CONTAINER_IDS)
def test_probe_recognises_supported_containers(
    decoder: AudioDecoder, container: str, audio_format: AudioFormat
) -> None:
    data = encoded(tone(1_000.0, 1.0, 48_000), 48_000, container)
    probe = decoder.probe(data)
    assert probe.audio_format is audio_format
    assert probe.duration_s == pytest.approx(1.0, abs=0.1)


@pytest.mark.parametrize(("container", "audio_format"), CONTAINERS, ids=CONTAINER_IDS)
def test_decode_gives_mono_at_the_analysis_rate(
    decoder: AudioDecoder, container: str, audio_format: AudioFormat
) -> None:
    frames = tone(1_000.0, 3.0, 48_000)
    signal = decoder.decode(encoded(np.stack([frames, frames], axis=1), 48_000, container))
    assert signal.duration_s == pytest.approx(3.0, abs=0.1)
    peak_hz = bin_freqs_hz()[np.argmax(stft_magnitudes(signal)[20:-20].mean(axis=0))]
    assert peak_hz == pytest.approx(1_000.0, abs=11.0)
    assert audio_format in AudioFormat


def test_decode_keeps_analysis_rate_audio_sample_for_sample(decoder: AudioDecoder) -> None:
    frames = tone(440.0, 1.0, ANALYSIS_SAMPLE_RATE_HZ)
    signal = decoder.decode(encoded(frames, ANALYSIS_SAMPLE_RATE_HZ, "FLAC"))
    np.testing.assert_allclose(signal.samples, frames, atol=1e-4)


def test_decode_averages_channels(decoder: AudioDecoder) -> None:
    left = tone(440.0, 1.0, ANALYSIS_SAMPLE_RATE_HZ)
    signal = decoder.decode(
        encoded(np.stack([left, -left], axis=1), ANALYSIS_SAMPLE_RATE_HZ, "WAV")
    )
    assert np.abs(signal.samples).max() < 1e-4


@pytest.mark.parametrize(
    "data",
    [b"", b"definitely not audio" * 64, encoded(tone(440.0, 1.0, 48_000), 48_000, "AIFF")],
    ids=["empty", "text", "aiff"],
)
def test_unsupported_content_is_rejected_by_probe_and_decode(
    decoder: AudioDecoder, data: bytes
) -> None:
    with pytest.raises(UnsupportedFormatError):
        decoder.probe(data)
    with pytest.raises(UnsupportedFormatError):
        decoder.decode(data)


def test_truncated_flac_is_recognised_but_undecodable(decoder: AudioDecoder) -> None:
    data = encoded(tone(440.0, 3.0, 48_000), 48_000, "FLAC")
    truncated = data[: len(data) // 2]
    assert decoder.probe(truncated).audio_format is AudioFormat.FLAC
    with pytest.raises(UndecodableAudioError):
        decoder.decode(truncated)


def test_ogg_without_audio_frames_is_undecodable(decoder: AudioDecoder) -> None:
    data = encoded(tone(440.0, 3.0, 48_000), 48_000, "OGG")
    with pytest.raises(UndecodableAudioError):
        decoder.decode(data[: len(data) // 2])
