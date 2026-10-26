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
"""The LIBI integration: a ladder editor panel for Home Assistant automations."""
# v3.38.0
# [ADDED v3.34.0 | 2026-10-26] Purpose: The static path and the websocket commands are registered once
#   in async_setup, so reloading the config entry no longer fails on a route that already exists. The
#   panel is admin only and is removed through the frontend API on unload, the entry data lives on
#   entry.runtime_data, and CONFIG_SCHEMA declares that LIBI is set up from the UI only.
# [ADDED v3.38.0 | 2026-10-26] Purpose: LIBI_VERSION 3.38.0 (an XSS fix in the panel).
import logging
import os

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PANEL_URL, PANEL_TITLE, PANEL_ICON
from . import websocket as ws_module

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_PANEL_JS = "libi-panel.js"
_PANEL_ELEMENT = "libi-panel"
# One version number for the whole integration. The panel and every module it imports are served
# with this string, so the browser can never mix an old file with a new one.
LIBI_VERSION = "3.38.0"

# [CHANGED v3.15.2] The frontend used to be served from /local/libi. /local is Home Assistant's own
# alias for the config/www folder and it is registered before any custom integration, so if a folder
# called libi ever existed under config/www, Home Assistant served those files instead of ours and
# no update could ever reach the browser. A private prefix cannot collide with anything.
_STATIC_URL = f"/{DOMAIN}_static"

LibiConfigEntry = ConfigEntry[dict]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register what lives for the whole run: the static files and the websocket commands.

    aiohttp refuses a route that is already registered, so doing this per config entry made every
    reload of the entry fail."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            url_path=_STATIC_URL,
            path=os.path.join(os.path.dirname(__file__), "frontend"),
            cache_headers=False,
        )
    ])
    ws_module.async_register_websockets(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LibiConfigEntry) -> bool:
    """Set up LIBI from a config entry: show the panel."""
    entry.runtime_data = dict(entry.data)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=_PANEL_ELEMENT,
        frontend_url_path=PANEL_URL,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{_STATIC_URL}/{_PANEL_JS}?v={LIBI_VERSION}",
        # [CHANGED v3.34.0] Admin only, like Home Assistant's own automation editor: the panel
        # writes automations.yaml, scripts.yaml and scenes.yaml.
        require_admin=True,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LibiConfigEntry) -> bool:
    """Unload a config entry: remove the panel. The files LIBI wrote stay where they are."""
    frontend.async_remove_panel(hass, PANEL_URL)
    return True
