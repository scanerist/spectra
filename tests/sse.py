import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ServerSentEvent:
    name: str
    data: dict[str, object]


def parse_events(stream: str) -> list[ServerSentEvent]:
    events: list[ServerSentEvent] = []
    for block in stream.replace("\r\n", "\n").split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.split("\n") if line and not line.startswith(":")
        )
        if fields:
            events.append(ServerSentEvent(name=fields["event"], data=json.loads(fields["data"])))
    return events
