class TracksError(Exception):
    pass


class InvalidTrackIdError(TracksError):
    pass


class TrackNotFoundError(TracksError):
    pass


class EmptyUploadError(TracksError):
    pass


class FileTooLargeError(TracksError):
    pass


class TrackTooLongError(TracksError):
    pass


class AnalysisQueueFullError(TracksError):
    pass


class InvalidQuotaError(TracksError):
    pass


class UploadQuotaExceededError(TracksError):
    def __init__(self, message: str, *, retry_after_s: float) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s
