import math

from spectra.gateway.errors import InvalidFrameRateError


class FramePacer:
    def __init__(self, *, frame_rate_hz: float, start_s: float) -> None:
        if not (math.isfinite(frame_rate_hz) and frame_rate_hz > 0.0):
            raise InvalidFrameRateError(f"frame rate must be finite and > 0, got {frame_rate_hz}")
        self._frame_period_s = 1.0 / frame_rate_hz
        self._next_tick_s = start_s

    @property
    def frame_period_s(self) -> float:
        return self._frame_period_s

    def delay_s(self, now_s: float) -> float:
        self._next_tick_s += self._frame_period_s
        delay_s = self._next_tick_s - now_s
        if delay_s < -self._frame_period_s:
            self._next_tick_s = now_s
            return 0.0
        return max(delay_s, 0.0)
