"""Setup, unload and reload of the config entry."""
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


async def test_unload_removes_the_panel(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert PANEL_URL not in hass.data.get("frontend_panels", {})


async def test_reload_does_not_fail(hass: HomeAssistant) -> None:
    """The static path is registered once, so a reload no longer hits an existing route."""
    entry = await _setup(hass)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert PANEL_URL in hass.data["frontend_panels"]
