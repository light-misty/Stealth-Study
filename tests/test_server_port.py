"""Server port auto-increment: dev-only fallback when the requested port is busy.

`resolve_server_port` applies only when the caller did NOT pass an explicit
`--port` (the production sidecar always does, so its port is never replaced).
"""

import socket

import pytest

from stealth_study.server.run import port_in_use, resolve_server_port


def bind_port(port: int, host: str = "127.0.0.1") -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(1)
    return server


def free_port() -> int:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.close()
    return port


def bind_consecutive(count: int) -> tuple[int, list[socket.socket]]:
    while True:
        base = free_port()
        servers = [bind_port(base)]
        try:
            for offset in range(1, count):
                servers.append(bind_port(base + offset))
            return base, servers
        except OSError:
            for server in servers:
                server.close()


def close_all(servers: list[socket.socket]) -> None:
    for server in servers:
        server.close()


def test_port_in_use_detects_bound_and_free_ports():
    port = free_port()
    server = bind_port(port)
    try:
        assert port_in_use(port) is True
    finally:
        server.close()
    assert port_in_use(port) is False


def test_free_requested_port_is_returned_unchanged():
    port = free_port()
    assert resolve_server_port(port, explicit=False) == port


def test_occupied_requested_port_increments_to_first_free():
    base, servers = bind_consecutive(2)
    try:
        assert resolve_server_port(base, explicit=False) == base + 2
    finally:
        close_all(servers)


def test_explicit_port_is_never_replaced_even_when_busy():
    port = free_port()
    server = bind_port(port)
    try:
        assert resolve_server_port(port, explicit=True) == port
    finally:
        server.close()


def test_exhaustion_raises_when_no_port_is_free():
    base, servers = bind_consecutive(1)
    try:
        with pytest.raises(RuntimeError):
            resolve_server_port(base, explicit=False, max_attempts=1)
    finally:
        close_all(servers)


def test_attempts_and_final_port_are_logged(caplog):
    base, servers = bind_consecutive(2)
    try:
        with caplog.at_level("INFO", logger="stealth_study.server.run"):
            resolved = resolve_server_port(base, explicit=False)
    finally:
        close_all(servers)
    messages = [record.getMessage() for record in caplog.records]
    assert resolved == base + 2
    assert any(str(base) in m and "in use" in m for m in messages)
    assert any(str(base + 2) in m and "using port" in m for m in messages)
