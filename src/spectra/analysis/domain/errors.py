class AnalysisError(Exception):
    pass


class InvalidTempoError(AnalysisError):
    pass


class InvalidTimeError(AnalysisError):
    pass


class InvalidBeatPositionError(AnalysisError):
    pass


class InvalidShapeError(AnalysisError):
    pass


class OutOfRangeError(AnalysisError):
    pass


class InvalidPeaksError(AnalysisError):
    pass


class InvalidSignalError(AnalysisError):
    pass
