import pytest
from starlette.requests import Request

from spectra.gateway.routes import upload_source
from spectra.tracks.domain.quota import UploadSource


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
    assert upload_source(request_from((host, 51_000))).address == address


def test_a_request_without_a_peer_counts_as_unknown() -> None:
    assert upload_source(request_from(None)).address == "unknown"


@pytest.mark.parametrize(
    ("host", "network"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1::/48"),
        ("2001:db8:1:ffff::1", "2001:db8:1::/48"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("testclient", "testclient"),
    ],
    ids=["ipv4", "ipv6-host", "ipv6-other-subnet", "ipv4-mapped", "not-an-address"],
)
def test_ipv6_uploads_also_count_against_their_48_network(host: str, network: str) -> None:
    source = upload_source(request_from((host, 51_000)))
    assert source == UploadSource(
        address=upload_source(request_from((host, 51_000))).address, network=network
    )
