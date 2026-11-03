"""Use SDL's off-screen drivers before test modules import or initialize Pygame."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import socket
import pytest


@pytest.fixture(autouse=True)
def prohibit_test_network(monkeypatch):
    """Even a caught connection error must fail an offline test."""
    attempts = []

    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Network access is prohibited in the offline test suite")

    for target, name in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                         (socket.socket, "sendto"), (socket, "create_connection"),
                         (socket, "getaddrinfo")):
        monkeypatch.setattr(target, name, deny)
    yield
    assert not attempts, "An offline test attempted networking"
