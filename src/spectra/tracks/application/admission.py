from spectra.tracks.application.ports import UploadQuota
from spectra.tracks.domain.errors import UploadQuotaExceededError
from spectra.tracks.domain.quota import UploadCharge


class UploadAdmission:
    def __init__(self, *, quota: UploadQuota) -> None:
        self._quota = quota

    async def admit(self, client: str) -> UploadCharge:
        decision = await self._quota.spend(client)
        if not decision.allowed:
            raise UploadQuotaExceededError(
                "too many uploads from this address", retry_after_s=decision.retry_after_s
            )
        return UploadCharge(client=client, window=decision.window)

    async def refund(self, charge: UploadCharge) -> None:
        await self._quota.refund(charge.client, window=charge.window)
