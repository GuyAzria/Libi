# -*- coding: utf-8 -*-
# LIBI for Home Assistant
# Copyright (C) 2026 Guy Azria
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details. <https://www.gnu.org/licenses/>.
"""Windows-only: the Proactor event loop opens a socketpair at startup, which pytest-socket blocks.
pytest-homeassistant-custom-component calls pytest_socket.disable_socket() before every test, so it
is made a no-op here. Never used in CI, where tests run on Linux with sockets blocked as intended."""
import pytest_socket

pytest_socket.disable_socket = lambda *a, **k: None
