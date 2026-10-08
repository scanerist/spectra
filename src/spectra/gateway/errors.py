class GatewayError(Exception):
    pass


class WireFormatError(GatewayError):
    pass


class InvalidFrameRateError(GatewayError):
    pass
