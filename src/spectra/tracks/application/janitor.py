import logging
from typing import Final

from spectra.tracks.application.ports import BlobStore, TrackExpiry
from spectra.tracks.domain.blobs import timeline_key, upload_key

logger = logging.getLogger(__name__)

SWEEP_BATCH_SIZE: Final = 500


class Janitor:
    def __init__(
        self,
        *,
        expiry: TrackExpiry,
        blobs: BlobStore,
        retention_s: float,
    ) -> None:
        self._expiry = expiry
        self._blobs = blobs
        self._retention_s = retention_s

    async def sweep(self) -> int:
        removed = 0
        while expired := await self._expiry.expire_unseen(
            unseen_for_s=self._retention_s, limit=SWEEP_BATCH_SIZE
        ):
            for track_id in expired:
                await self._blobs.delete(upload_key(track_id))
                await self._blobs.delete(timeline_key(track_id))
            removed += len(expired)
        if removed:
            logger.info("removed %s tracks unseen for %s s", removed, self._retention_s)
        return removed
