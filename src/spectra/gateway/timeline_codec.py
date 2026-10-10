import struct
from typing import Final

import numpy as np
from numpy.typing import NDArray

from spectra.analysis.domain.bands import BAND_COUNT
from spectra.analysis.domain.bar_spectra import FOURIER_BIN_COUNT
from spectra.analysis.domain.frame_levels import LEVEL_COUNT
from spectra.analysis.domain.peaks import PEAK_COUNT, PEAK_FIELD_COUNT
from spectra.analysis.domain.ranges import Float32Array
from spectra.analysis.domain.track_analysis import TrackAnalysis
from spectra.gateway.protocol import PROTOCOL_VERSION

HEADER: Final = struct.Struct("<IfII")
UINT8_SCALE: Final = 255
WIRE_FLOAT32: Final = np.dtype("<f4")
WIRE_UINT8: Final = np.dtype(np.uint8)
PEAK_ROW_BYTES: Final = PEAK_COUNT * PEAK_FIELD_COUNT * WIRE_FLOAT32.itemsize
BAND_ROW_BYTES: Final = BAND_COUNT * WIRE_UINT8.itemsize
LEVEL_ROW_BYTES: Final = LEVEL_COUNT * WIRE_UINT8.itemsize
FOURIER_ROW_BYTES: Final = FOURIER_BIN_COUNT * WIRE_UINT8.itemsize


def timeline_length(*, frame_count: int, bar_count: int) -> int:
    frame_bytes = BAND_ROW_BYTES + LEVEL_ROW_BYTES
    bar_bytes = PEAK_ROW_BYTES + FOURIER_ROW_BYTES
    return HEADER.size + bar_bytes * bar_count + frame_bytes * frame_count


def quantise(values: Float32Array) -> NDArray[np.uint8]:
    scaled = np.clip(values.astype(np.float64), 0.0, 1.0) * UINT8_SCALE
    return np.floor(scaled + 0.5).astype(np.uint8)


def encode_timeline(analysis: TrackAnalysis) -> bytes:
    peaks = np.stack([bar.as_padded_array() for bar in analysis.bar_peaks]).astype(WIRE_FLOAT32)
    header = HEADER.pack(
        PROTOCOL_VERSION, analysis.frame_rate_hz, analysis.frame_count, analysis.bar_count
    )
    return b"".join(
        [
            header,
            peaks.tobytes(),
            quantise(analysis.bands).tobytes(),
            quantise(analysis.levels).tobytes(),
            quantise(analysis.bar_spectra).tobytes(),
        ]
    )
