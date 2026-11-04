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
"""Setup, unload and reload of the config entry."""
import logging
import re
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.libi.const import AI_MODE_NONE, CONF_AI_MODE, DOMAIN, PANEL_URL


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_AI_MODE: AI_MODE_NONE})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_registers_an_admin_only_panel(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    panel = hass.data["frontend_panels"][PANEL_URL]
    assert panel.require_admin is True
    assert entry.runtime_data == {CONF_AI_MODE: AI_MODE_NONE}


async def test_setup_says_when_the_old_libi_file_still_holds_automations(hass: HomeAssistant, tmp_path, caplog) -> None:
    """[ADDED 2026-11-04, v3.85.0] The HACS review: LIBI leaves libi_automations.yaml alone and tells the user in the log."""
    hass.config.config_dir = str(tmp_path)
    legacy = "- id: old\n  alias: Old\n"
    (tmp_path / "libi_automations.yaml").write_text(legacy, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        await _setup(hass)
    assert "libi_automations.yaml, from LIBI before 3.5.0, still holds 1 automation(s)" in caplog.text
    assert (tmp_path / "libi_automations.yaml").read_text(encoding="utf-8") == legacy


async def test_unload_removes_the_panel(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert PANEL_URL not in hass.data.get("frontend_panels", {})


async def test_the_days_row_of_the_card_is_loaded_on_every_dashboard(hass: HomeAssistant) -> None:
    """[ADDED 2026-10-31, v3.76.0] LIBI's card shows the days of an 8-bit helper with a row of its own, which every
    dashboard loads from LIBI's own folder, with the version, and only once - a reload adds no second one."""
    from custom_components.libi import LIBI_VERSION

    entry = await _setup(hass)

    def days_rows(key="frontend_extra_module_url"):
        return [url for url in hass.data[key].urls if "libi-days-row.js" in url]
    assert days_rows() == [f"/libi_static/libi-days-row.js?v={LIBI_VERSION}"]
    # [ADDED 2026-11-04, v3.85.0] And for the legacy build, which loads only its own list: the user's card said
    # "Configuration error" in a browser Home Assistant does not count as modern.
    assert days_rows("frontend_extra_js_url_es5") == [f"/libi_static/libi-days-row.js?v={LIBI_VERSION}"]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(days_rows()) == 1 and len(days_rows("frontend_extra_js_url_es5")) == 1


async def test_reload_does_not_fail(hass: HomeAssistant) -> None:
    """The static path is registered once, so a reload no longer hits an existing route."""
    entry = await _setup(hass)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert PANEL_URL in hass.data["frontend_panels"]


async def test_the_panel_and_every_module_it_imports_carry_one_version(hass: HomeAssistant) -> None:
    """[ADDED 2026-11-04, v3.86.1] The browser keeps a file by its address, ?v= and all. The panel is registered with
    LIBI_VERSION, it imports every module with it, and it prints it: one number everywhere, or a browser mixes an old
    module with a new panel - the panel stayed blank when libi-core.js was a copy from an earlier 3.86.0."""
    from custom_components.libi import LIBI_VERSION

    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    module_url = hass.data["frontend_panels"][PANEL_URL].config["_panel_custom"]["module_url"]
    assert module_url.endswith(f"/libi-panel.js?v={LIBI_VERSION}")
    frontend = Path(__file__).resolve().parent.parent / "custom_components" / "libi" / "frontend"
    panel = (frontend / "libi-panel.js").read_text(encoding="utf-8")
    imports = re.findall(r"^import [^;]* from '\./([a-z0-9-]+\.js)\?v=([^']*)';", panel, re.M)
    assert {name for name, _ in imports} == {"libi-core.js", "libi-css.js", "libi-svg.js", "libi-online.js", "libi-ai.js"}
    assert all(v == LIBI_VERSION for _, v in imports), imports
    assert all((frontend / name).is_file() for name, _ in imports)
    assert re.findall(r"^export const LIBI_BUILD = '([^']*)';", panel, re.M) == [LIBI_VERSION]
    # Every other ?v= a module writes out, in any frontend file, is the same number.
    for js in frontend.glob("*.js"):
        for v in re.findall(r"\?v=([0-9][0-9.]*)", js.read_text(encoding="utf-8")):
            assert v == LIBI_VERSION, (js.name, v)
