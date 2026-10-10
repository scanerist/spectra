import io
import tracemalloc
from typing import Final

import numpy as np
import pytest
import soundfile

from spectra.analysis.adapters.soundfile_decoder import (
    MAX_CHANNELS,
    MAX_SAMPLE_RATE_HZ,
    SoundfileDecoder,
)
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


def multichannel(channels: int, sample_rate_hz: int, duration_s: float = 0.25) -> bytes:
    frames = tone(1_000.0, duration_s, sample_rate_hz)
    return encoded(np.tile(frames[:, np.newaxis], (1, channels)), sample_rate_hz, "WAV")


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


def test_probe_reports_the_sample_rate_and_channel_count(decoder: AudioDecoder) -> None:
    probe = decoder.probe(multichannel(6, 96_000))
    assert probe.sample_rate_hz == 96_000
    assert probe.channel_count == 6


def test_the_largest_supported_audio_parameters_are_accepted(decoder: AudioDecoder) -> None:
    probe = decoder.probe(multichannel(MAX_CHANNELS, MAX_SAMPLE_RATE_HZ))
    assert probe.channel_count == MAX_CHANNELS


@pytest.mark.parametrize(
    ("channels", "sample_rate_hz"),
    [(MAX_CHANNELS + 1, 48_000), (2, 2 * MAX_SAMPLE_RATE_HZ)],
    ids=["too-many-channels", "too-high-sample-rate"],
)
def test_audio_beyond_the_supported_parameters_is_rejected(
    decoder: AudioDecoder, channels: int, sample_rate_hz: int
) -> None:
    data = multichannel(channels, sample_rate_hz)
    with pytest.raises(UnsupportedFormatError):
        decoder.probe(data)
    with pytest.raises(UnsupportedFormatError):
        decoder.decode(data)


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


def test_decoding_many_channels_never_holds_them_all_in_memory(decoder: AudioDecoder) -> None:
    duration_s = 4.0
    data = multichannel(MAX_CHANNELS, MAX_SAMPLE_RATE_HZ, duration_s)
    all_channels_bytes = int(duration_s * MAX_SAMPLE_RATE_HZ) * MAX_CHANNELS * 4
    tracemalloc.start()
    try:
        signal = decoder.decode(data)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert signal.duration_s == pytest.approx(duration_s, abs=0.01)
    assert peak_bytes < all_channels_bytes / 2


def test_decoding_in_blocks_keeps_the_tone_and_its_level(decoder: AudioDecoder) -> None:
    signal = decoder.decode(multichannel(MAX_CHANNELS, 96_000, duration_s=3.0))
    middle = signal.samples[ANALYSIS_SAMPLE_RATE_HZ : 2 * ANALYSIS_SAMPLE_RATE_HZ]
    expected = tone(1_000.0, 1.0, ANALYSIS_SAMPLE_RATE_HZ)
    assert np.sqrt(np.mean(middle**2)) == pytest.approx(np.sqrt(np.mean(expected**2)), rel=0.02)


@pytest.mark.parametrize("kept", [0.1, 0.55], ids=["tenth", "half"])
def test_a_truncated_mp3_decodes_only_the_audio_it_holds(
    decoder: AudioDecoder, kept: float
) -> None:
    data = encoded(tone(440.0, 6.0, ANALYSIS_SAMPLE_RATE_HZ), ANALYSIS_SAMPLE_RATE_HZ, "MP3")
    truncated = data[: int(len(data) * kept)]
    frames, _ = soundfile.read(io.BytesIO(truncated), dtype="float32")
    signal = decoder.decode(truncated)
    assert signal.sample_count == len(frames)
    assert np.abs(signal.samples).max() <= 1.0
