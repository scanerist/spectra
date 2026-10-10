import logging
from typing import Final

from spectra.tracks.application.ports import BlobStore, ProgressFeed, TrackExpiry
from spectra.tracks.domain.blobs import timeline_key, upload_key
from spectra.tracks.domain.track import Failed, FailureCode

logger = logging.getLogger(__name__)

SWEEP_BATCH_SIZE: Final = 500
ABANDONED: Final = Failed(
    code=FailureCode.INTERNAL, message="the analysis stopped without news, upload the file again"
)


class Janitor:
    def __init__(
        self,
        *,
        expiry: TrackExpiry,
        feed: ProgressFeed,
        blobs: BlobStore,
        retention_s: float,
        stalled_after_s: float,
    ) -> None:
        self._expiry = expiry
        self._feed = feed
        self._blobs = blobs
        self._retention_s = retention_s
        self._stalled_after_s = stalled_after_s

    async def abandon(self) -> int:
        abandoned = await self._expiry.abandon_stalled(
            stalled_for_s=self._stalled_after_s, status=ABANDONED
        )
        for track_id in abandoned:
            await self._feed.publish(track_id, ABANDONED)
            await self._blobs.delete(upload_key(track_id))
        if abandoned:
            logger.warning(
                "abandoned %s analyses without news for %s s", len(abandoned), self._stalled_after_s
            )
        return len(abandoned)

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
