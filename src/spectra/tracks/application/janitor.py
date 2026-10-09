import logging
from typing import Final

from spectra.tracks.application.ports import BlobStore, TrackExpiry
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.blobs import timeline_key, upload_key

logger = logging.getLogger(__name__)

SWEEP_BATCH_SIZE: Final = 500


class Janitor:
    def __init__(
        self,
        *,
        expiry: TrackExpiry,
        board: StatusBoard,
        blobs: BlobStore,
        retention_s: float,
    ) -> None:
        self._expiry = expiry
        self._board = board
        self._blobs = blobs
        self._retention_s = retention_s

    async def sweep(self) -> int:
        removed = 0
        while stale := await self._expiry.stale_tracks(
            unseen_for_s=self._retention_s, limit=SWEEP_BATCH_SIZE
        ):
            for track_id in stale:
                await self._blobs.delete(upload_key(track_id))
                await self._blobs.delete(timeline_key(track_id))
                await self._board.forget(track_id)
            removed += len(stale)
        if removed:
            logger.info("removed %s tracks unseen for %s s", removed, self._retention_s)
        return removed
