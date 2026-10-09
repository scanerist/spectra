from spectra.tracks.application.ports import UploadQuota
from spectra.tracks.domain.errors import UploadQuotaExceededError


class UploadAdmission:
    def __init__(self, *, quota: UploadQuota) -> None:
        self._quota = quota

    async def admit(self, client: str) -> None:
        decision = await self._quota.spend(client)
        if not decision.allowed:
            raise UploadQuotaExceededError(
                "too many uploads from this address", retry_after_s=decision.retry_after_s
            )

    async def refund(self, client: str) -> None:
        await self._quota.refund(client)
