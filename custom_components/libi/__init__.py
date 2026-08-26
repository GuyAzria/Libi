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
# [ADDED v1.0.0 | 2026-08-09] Purpose: Register ladder_ha integration and set up panel/API routes.
# v3.3.0
import logging
import os
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PANEL_URL, PANEL_TITLE, PANEL_ICON
from . import websocket as ws_module

_LOGGER = logging.getLogger(__name__)

# [ADDED v1.5.1 | 2026-08-10] Purpose: Filename of the custom panel JS served to the browser.
# [ADDED v3.2.0 | 2026-08-20] Purpose: Updated filenames to reflect LIBI rebranding.
_PANEL_JS = "libi-panel.js"
_PANEL_ELEMENT = "libi-panel"
# [ADDED v2.0.0 | 2026-08-17] One version number for the whole integration. The panel and every module
# it imports are served with this string, so the browser can never mix an old file with a new one.
# [ADDED v3.3.0 | 2026-08-20] Purpose: Renamed LADDER_VERSION to LIBI_VERSION.
LIBI_VERSION = "3.11.0"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the LIBI for HA component."""
    _LOGGER.info("Setting up LIBI for HA")
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LIBI for HA from a config entry."""
    _LOGGER.info("Setting up LIBI for HA entry: %s", entry.entry_id)

    hass.data[DOMAIN][entry.entry_id] = entry.data
    frontend_path = os.path.join(os.path.dirname(__file__), "frontend")
    
    from homeassistant.components.http import StaticPathConfig
    await hass.http.async_register_static_paths(
        [StaticPathConfig(
            url_path=f"/local/{DOMAIN}",
            path=frontend_path,
            cache_headers=False,
        )]
    )

    from homeassistant.components import panel_custom
    # [ADDED v3.2.0 | 2026-08-20] Purpose: Replaced PANEL_TITLE with "LIBI" to reflect the new brand in the HA sidebar.
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=_PANEL_ELEMENT,
        frontend_url_path=PANEL_URL,
        sidebar_title="LIBI",
        sidebar_icon=PANEL_ICON,
        module_url=f"/local/{DOMAIN}/{_PANEL_JS}?v={LIBI_VERSION}",
        require_admin=False,
    )

    ws_module.async_register_websockets(hass)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading LIBI for HA entry: %s", entry.entry_id)

    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)

    hass.data.get("frontend_panels", {}).pop(PANEL_URL, None)
    return True