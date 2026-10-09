import pytest
from starlette.requests import Request

from spectra.gateway.routes import client_address


def request_from(client: tuple[str, int] | None) -> Request:
    return Request(
        {"type": "http", "method": "POST", "path": "/tracks", "headers": [], "client": client}
    )


@pytest.mark.parametrize(
    ("host", "address"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("testclient", "testclient"),
    ],
    ids=["ipv4", "ipv6-host", "ipv6-same-network", "ipv4-mapped", "not-an-address"],
)
def test_clients_are_counted_by_address_and_ipv6_by_network(host: str, address: str) -> None:
    assert client_address(request_from((host, 51_000))) == address


def test_a_request_without_a_peer_counts_as_unknown() -> None:
    assert client_address(request_from(None)) == "unknown"
