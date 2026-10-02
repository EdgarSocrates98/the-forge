import socket

import pytest

import theforge


def test_version() -> None:
    assert theforge.__version__ == "0.1.0"


def test_network_is_blocked() -> None:
    with pytest.raises(OSError, match="network access disabled"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)
