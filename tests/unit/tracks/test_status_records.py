import json

import pytest
from pydantic import ValidationError

from spectra.tracks.adapters.status_records import (
    StatusState,
    state_of,
    status_document,
    status_from_document,
    status_from_json,
    status_json,
)
from spectra.tracks.domain.track import TrackStatus
from tests.statuses import ANALYSING, EVERY_STATUS, FAILED, READY


@pytest.mark.parametrize("status", EVERY_STATUS)
def test_a_status_survives_a_round_trip_through_json(status: TrackStatus) -> None:
    document = json.loads(json.dumps(status_document(status)))
    assert status_from_document(document) == status


@pytest.mark.parametrize("status", EVERY_STATUS)
def test_a_status_survives_a_round_trip_through_json_bytes(status: TrackStatus) -> None:
    assert status_from_json(status_json(status)) == status


@pytest.mark.parametrize(
    ("status", "state"),
    [
        pytest.param(ANALYSING, StatusState.ANALYSING, id="analysing"),
        pytest.param(READY, StatusState.READY, id="ready"),
        pytest.param(FAILED, StatusState.FAILED, id="failed"),
    ],
)
def test_a_status_names_its_state(status: TrackStatus, state: StatusState) -> None:
    assert state_of(status) == state
    assert status_document(status)["state"] == state.value


def test_a_document_with_an_unknown_state_is_rejected() -> None:
    with pytest.raises(ValidationError):
        status_from_document({"state": "queued"})


def test_a_document_with_an_unknown_field_is_rejected() -> None:
    document = status_document(FAILED) | {"retry": True}
    with pytest.raises(ValidationError):
        status_from_document(document)
