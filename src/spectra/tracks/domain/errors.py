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
