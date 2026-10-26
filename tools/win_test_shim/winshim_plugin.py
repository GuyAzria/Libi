"""Windows-only: the Proactor event loop opens a socketpair at startup, which pytest-socket blocks.
pytest-homeassistant-custom-component calls pytest_socket.disable_socket() before every test, so it
is made a no-op here. Never used in CI, where tests run on Linux with sockets blocked as intended."""
import pytest_socket

pytest_socket.disable_socket = lambda *a, **k: None
