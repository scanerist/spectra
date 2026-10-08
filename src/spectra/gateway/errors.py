class GatewayError(Exception):
    pass


class WireFormatError(GatewayError):
    pass


class InvalidFrameRateError(GatewayError):
    pass


class ClientDisconnectedError(GatewayError):
    pass


class UnreadableClientFrameError(GatewayError):
    pass
