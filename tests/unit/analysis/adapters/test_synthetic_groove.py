import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from spectra.analysis.adapters.synthetic_groove import ENERGY_CYCLE_BARS, SyntheticGroove
from spectra.analysis.application.ports import FeatureSource
from spectra.analysis.domain.feature_frame import FeatureFrame
from spectra.analysis.domain.tempo import BEATS_PER_BAR, Tempo
from tests.fakes import FakeClock

TEMPO = Tempo(bpm=128.0)


def frame_at(time_s: float, *, seed: int = 0) -> FeatureFrame:
    clock = FakeClock()
    groove = SyntheticGroove(clock=clock, tempo=TEMPO, seed=seed)
    clock.advance(time_s)
    return groove.latest()


def beat_time_s(beats: float) -> float:
    return beats * TEMPO.beat_duration_s


def test_groove_is_a_feature_source() -> None:
    source: FeatureSource = SyntheticGroove(clock=FakeClock(), tempo=TEMPO, seed=0)
    assert source.latest().tempo == TEMPO


def test_time_is_measured_from_construction() -> None:
    clock = FakeClock(start_s=100.0)
    groove = SyntheticGroove(clock=clock, tempo=TEMPO, seed=0)
    clock.advance(1.5)
    frame = groove.latest()
    assert frame.time_s == pytest.approx(1.5)
    assert frame.position == TEMPO.position_at(frame.time_s)


@pytest.mark.parametrize("beat", [0, 1, 7, 33], ids=["first", "second", "eighth", "later-bar"])
def test_kick_is_one_at_beat_start_and_decays(beat: int) -> None:
    kicks = [frame_at(beat_time_s(beat + phase)).levels.kick for phase in (0.0, 0.1, 0.3, 0.6)]
    assert kicks[0] == pytest.approx(1.0)
    assert kicks == sorted(kicks, reverse=True)
    assert kicks[-1] < 0.1


def test_hat_peaks_on_offbeat() -> None:
    phases = np.linspace(0.0, 1.0, 40, endpoint=False)
    highs = [frame_at(beat_time_s(8 + float(phase))).levels.high for phase in phases]
    assert phases[int(np.argmax(highs))] == pytest.approx(0.5)


def test_bass_ducks_under_the_kick() -> None:
    on_kick = frame_at(beat_time_s(4.0)).levels.bass
    between_kicks = frame_at(beat_time_s(4.5)).levels.bass
    assert on_kick < between_kicks


@pytest.mark.parametrize(
    ("bars", "energy"),
    [(0, 0.0), (ENERGY_CYCLE_BARS // 2, 1.0), (ENERGY_CYCLE_BARS, 0.0)],
    ids=["start", "half-cycle", "full-cycle"],
)
def test_energy_cycles_over_energy_cycle_bars(bars: int, energy: float) -> None:
    frame = frame_at(beat_time_s(bars * BEATS_PER_BAR))
    assert frame.energy == pytest.approx(energy, abs=1e-9)


def test_kick_drives_the_strongest_peak_on_the_beat() -> None:
    strongest = frame_at(beat_time_s(2.0)).peaks.items[0]
    assert strongest.freq_hz == 55.0
    assert strongest.amplitude == pytest.approx(1.0)


@given(time_s=st.floats(min_value=0.0, max_value=1e5))
def test_every_value_stays_in_range_for_any_time(time_s: float) -> None:
    frame = frame_at(time_s)
    levels = frame.levels
    assert all(0.0 <= level <= 1.0 for level in (levels.kick, levels.bass, levels.mid, levels.high))
    assert 0.0 <= frame.energy <= 1.0
    assert 0.0 <= frame.position.phase < 1.0
    assert np.all((frame.spectrum.bands >= 0.0) & (frame.spectrum.bands <= 1.0))
    assert np.all(np.abs(frame.waveform.samples) <= 1.0)


def frames_over(times_s: list[float], *, seed: int) -> list[FeatureFrame]:
    clock = FakeClock()
    groove = SyntheticGroove(clock=clock, tempo=TEMPO, seed=seed)
    return [read_at(clock, groove, time_s) for time_s in times_s]


def read_at(clock: FakeClock, groove: SyntheticGroove, time_s: float) -> FeatureFrame:
    clock.set_now_s(time_s)
    return groove.latest()


def test_same_seed_gives_same_frames() -> None:
    times_s = [0.0, 0.37, 0.37, 1.5, 12.345]
    assert frames_over(times_s, seed=7) == frames_over(times_s, seed=7)


def test_different_seeds_give_different_noise() -> None:
    assert frame_at(1.0, seed=1).spectrum != frame_at(1.0, seed=2).spectrum
