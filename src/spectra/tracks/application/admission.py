from spectra.tracks.application.ports import UploadQuota
from spectra.tracks.domain.errors import UploadQuotaExceededError
from spectra.tracks.domain.quota import UploadSource


class UploadAdmission:
    def __init__(self, *, quota: UploadQuota) -> None:
        self._quota = quota

    async def admit(self, source: UploadSource) -> None:
        decision = await self._quota.spend(source)
        if not decision.allowed:
            raise UploadQuotaExceededError(
                "too many uploads from this address, its network or everyone",
                retry_after_s=decision.retry_after_s,
            )

    async def refund(self, source: UploadSource) -> None:
        await self._quota.refund(source)
