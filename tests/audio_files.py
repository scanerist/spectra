import io
import math

import numpy as np
import soundfile

from spectra.analysis.domain.ranges import Float32Array


def tone(freq_hz: float, duration_s: float, sample_rate_hz: int) -> Float32Array:
    times_s = np.arange(round(duration_s * sample_rate_hz)) / sample_rate_hz
    return (0.5 * np.sin(2.0 * math.pi * freq_hz * times_s)).astype(np.float32)


def encoded(frames: Float32Array, sample_rate_hz: int, container: str) -> bytes:
    buffer = io.BytesIO()
    soundfile.write(buffer, frames, sample_rate_hz, format=container)
    return buffer.getvalue()
