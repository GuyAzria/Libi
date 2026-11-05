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
# v3.90.0
# [ADDED v3.34.0 | 2026-10-26] Purpose: The static path and the websocket commands are registered once
#   in async_setup, so reloading the config entry no longer fails on a route that already exists. The
#   panel is admin only and is removed through the frontend API on unload, the entry data lives on
#   entry.runtime_data, and CONFIG_SCHEMA declares that LIBI is set up from the UI only.
# [ADDED v3.89.0 | 2026-11-05] Purpose: LIBI_VERSION 3.89.0 (the phone replaced with its global variable in the
#   automations that send straight to it, once confirmed); 3.88.1 is on the user's Home Assistant.
# [CHANGED v3.90.0 | 2026-11-05] Purpose: LIBI_VERSION 3.90.0 (the HACS review of 2026-11-05: a save asks before it
#   deletes, and deletes only what LIBI made); the browser must load the new panel, not keep 3.89.0.
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
# [ADDED v3.76.0] The row of LIBI's dashboard card that shows the days of an 8-bit helper as seven checkboxes
# ([CHANGED v3.79.0] round buttons).
_DAYS_ROW_JS = "libi-days-row.js"
# One version number for the whole integration. The panel and every module it imports are served
# with this string, so the browser can never mix an old file with a new one.
LIBI_VERSION = "3.90.0"

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
    # [ADDED v3.76.0] On every dashboard, so the card LIBI writes (custom:libi-days-row) shows wherever it is pasted;
    # from LIBI's own folder, like the panel - nothing comes from the internet.
    # [CHANGED v3.85.0] And by the legacy build Home Assistant serves to browsers it does not count as modern (Samsung
    # Internet up to 27, a Chrome or a WebView older than 131, Safari older than 18.1), which loads only the scripts
    # registered for it: there the row was unknown, and the user's card said "Configuration error".
    days_row = f"{_STATIC_URL}/{_DAYS_ROW_JS}?v={LIBI_VERSION}"
    frontend.add_extra_js_url(hass, days_row)
    frontend.add_extra_js_url(hass, days_row, es5=True)
    ws_module.async_register_websockets(hass)
    # [ADDED v3.85.0] The file LIBI wrote before 3.5.0 is left alone; the log says when it still holds automations.
    await hass.async_add_executor_job(ws_module.legacy_file_note_sync, hass)
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
        # saves automations, scripts and scenes ([CHANGED v3.85.0] through that editor's config API).
        require_admin=True,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LibiConfigEntry) -> bool:
    """Unload a config entry: remove the panel. The files LIBI wrote stay where they are."""
    frontend.async_remove_panel(hass, PANEL_URL)
    return True
