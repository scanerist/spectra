import pytest

from spectra.analysis.domain.errors import OutOfRangeError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.domain.errors import InvalidTrackIdError
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    TrackId,
    is_final,
)


def test_same_content_gets_the_same_sixteen_hex_digit_id() -> None:
    first = TrackId.of_content(b"track bytes")
    assert first == TrackId.of_content(b"track bytes")
    assert len(first.value) == 16
    assert int(first.value, 16) >= 0
    assert first != TrackId.of_content(b"other bytes")


@pytest.mark.parametrize(
    "value", ["", "9F2C41D07A3B55E1", "9f2c41d07a3b55e", "../../etc/passwd"], ids=str
)
def test_track_id_rejects_anything_but_sixteen_lowercase_hex_digits(value: str) -> None:
    with pytest.raises(InvalidTrackIdError):
        TrackId(value)


def test_analysing_progress_follows_the_stage_order() -> None:
    stages = [AnalysisStage.DECODING, AnalysisStage.SPECTRUM, AnalysisStage.TEMPO]
    progress = [Analysing.at(stage).progress for stage in [*stages, AnalysisStage.STRUCTURE]]
    assert progress == sorted(progress)
    assert progress[0] == 0.0
    assert progress[-1] < 1.0


def test_analysing_rejects_progress_outside_unit_interval() -> None:
    with pytest.raises(OutOfRangeError):
        Analysing(stage=AnalysisStage.TEMPO, progress=1.5)


def test_only_ready_and_failed_are_final() -> None:
    assert not is_final(Analysing.at(AnalysisStage.TEMPO))
    assert is_final(Failed(code=FailureCode.INTERNAL, message="boom"))


def test_failure_codes_are_the_contract_strings() -> None:
    assert [code.value for code in FailureCode] == ["undecodable", "analysis_failed", "internal"]
