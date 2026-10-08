class AnalysisError(Exception):
    pass


class InvalidTempoError(AnalysisError):
    pass


class InvalidTimeError(AnalysisError):
    pass


class InvalidBeatPositionError(AnalysisError):
    pass
