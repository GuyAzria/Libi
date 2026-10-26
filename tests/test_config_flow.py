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
"""The config flow, exactly as it behaves today. The AI steps are kept as they are."""
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.libi.const import (
    AI_MODE_LOCAL,
    AI_MODE_NONE,
    CONF_AI_MODE,
    CONF_LOCAL_MODEL,
    CONF_LOCAL_URL,
    DOMAIN,
)


async def test_no_ai_creates_the_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AI_MODE: AI_MODE_NONE})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_AI_MODE: AI_MODE_NONE}


async def test_local_ai_requires_url_and_model(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AI_MODE: AI_MODE_LOCAL})
    assert result["step_id"] == "local"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_URL: " ", CONF_LOCAL_MODEL: ""})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOCAL_URL: "invalid_url", CONF_LOCAL_MODEL: "invalid_model"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_URL: "http://ollama:11434", CONF_LOCAL_MODEL: "llama3"})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_only_one_instance(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, data={CONF_AI_MODE: AI_MODE_NONE}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
