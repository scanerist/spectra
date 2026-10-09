from spectra.tracks.domain.track import TrackId


def upload_key(track_id: TrackId) -> str:
    return f"uploads/{track_id.value}"
