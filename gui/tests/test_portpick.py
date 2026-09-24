import socket

from app.portpick import pick_free_port


def test_returns_free_port_not_conflicting():
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    port = blocker.getsockname()[1]
    free = pick_free_port(start=port, tries=5)
    assert free != port
    s = socket.socket()
    s.bind(("127.0.0.1", free))
    s.close()
    blocker.close()
