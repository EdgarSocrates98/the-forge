import socket

import pytest

import theforge


def test_version() -> None:
    assert theforge.__version__ == "0.2.0"


def test_network_is_blocked() -> None:
    with pytest.raises(OSError, match="network access disabled"):
        socket.create_connection(("192.0.2.1", 9), timeout=1)
