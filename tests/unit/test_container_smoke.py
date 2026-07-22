import pytest
from scripts.container_smoke import published_port


def test_published_port_parses_loopback_mapping() -> None:
    assert published_port("127.0.0.1:49152\n") == 49152


@pytest.mark.parametrize(
    "value",
    ["", "127.0.0.1", "127.0.0.1:0", "127.0.0.1:70000", "one:1\ntwo:2\n"],
)
def test_published_port_rejects_ambiguous_or_invalid_values(value: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        published_port(value)
