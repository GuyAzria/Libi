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
"""Config flow for LIBI integration."""
# v3.3.0
# [ADDED v3.3.0 | 2026-08-20] Purpose: Renamed config flow classes from LadderHA to HaLibi to match the domain.
# [ADDED v3.11.0 | 2026-08-25] Purpose: Domain is now libi, so the classes drop the ha prefix.
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_AI_MODE,
    AI_MODES,
    AI_MODE_NONE,
    AI_MODE_LOCAL,
    AI_MODE_CLOUD,
    CONF_LOCAL_URL,
    CONF_LOCAL_MODEL,
    CONF_CLOUD_API_KEY,
    CONF_CLOUD_MODEL,
)


class LibiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LIBI."""

    VERSION = 1

    def __init__(self):
        """Initialise the config flow internal state."""
        self._user_input = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step – choose AI mode."""
        # [ADDED v1.5.1 | 2026-08-10] Purpose: Gate to a single integration instance.
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._user_input[CONF_AI_MODE] = user_input[CONF_AI_MODE]
            # [ADDED v1.5.1 | 2026-08-10] Purpose: Route to correct branch; No AI skips all extra steps.
            if user_input[CONF_AI_MODE] == AI_MODE_NONE:
                return self.async_create_entry(
                    title="LIBI",
                    data=self._user_input,
                )
            if user_input[CONF_AI_MODE] == AI_MODE_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_AI_MODE, default=AI_MODE_LOCAL): vol.In(AI_MODES),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors={},
        )

    # [ADDED v1.5.1 | 2026-08-10] Purpose: Collect local Ollama/LLM server URL and model name.
    async def async_step_local(self, user_input=None):
        """Handle the Local AI configuration step."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_LOCAL_URL, "").strip():
                errors[CONF_LOCAL_URL] = "invalid_url"
            if not user_input.get(CONF_LOCAL_MODEL, "").strip():
                errors[CONF_LOCAL_MODEL] = "invalid_model"

            if not errors:
                self._user_input.update(user_input)
                return self.async_create_entry(
                    title="LIBI (Local AI)",
                    data=self._user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_LOCAL_URL, default="http://localhost:11434"): str,
                vol.Required(CONF_LOCAL_MODEL, default="llama3"): str,
            }
        )

        return self.async_show_form(
            step_id="local",
            data_schema=data_schema,
            errors=errors,
        )

    # [ADDED v1.5.1 | 2026-08-10] Purpose: Collect Cloud API key and cloud model name.
    async def async_step_cloud(self, user_input=None):
        """Handle the Cloud API configuration step."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_CLOUD_API_KEY, "").strip():
                errors[CONF_CLOUD_API_KEY] = "invalid_key"
            if not user_input.get(CONF_CLOUD_MODEL, "").strip():
                errors[CONF_CLOUD_MODEL] = "invalid_model"

            if not errors:
                self._user_input.update(user_input)
                return self.async_create_entry(
                    title="LIBI (Cloud API)",
                    data=self._user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CLOUD_API_KEY): str,
                vol.Required(CONF_CLOUD_MODEL, default="gpt-4o"): str,
            }
        )

        return self.async_show_form(
            step_id="cloud",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the Options Flow handler."""
        # [ADDED v1.5.1 | 2026-08-10] Purpose: Allow users to reconfigure settings post-setup via Integrations UI.
        return LibiOptionsFlow(config_entry)


class LibiOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for LIBI."""

    def __init__(self, config_entry):
        """Initialise the options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options – reconfigure AI mode or credentials."""
        # [ADDED v1.5.1 | 2026-08-10] Purpose: Clean options schema with only relevant fields, no stray artifacts.
        errors = {}
        current_mode = self._config_entry.data.get(CONF_AI_MODE, AI_MODE_NONE)

        if user_input is not None:
            return self.async_create_entry(title="LIBI", data=user_input)

        # [ADDED v1.5.1 | 2026-08-10] Purpose: Show empty options form when No AI mode is selected.
        if current_mode == AI_MODE_NONE:
            if user_input is not None:
                return self.async_create_entry(title="LIBI", data={})
            return self.async_show_form(step_id="init", data_schema=vol.Schema({}))

        if current_mode == AI_MODE_LOCAL:
            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_LOCAL_URL,
                        default=self._config_entry.data.get(CONF_LOCAL_URL, "http://localhost:11434"),
                    ): str,
                    vol.Required(
                        CONF_LOCAL_MODEL,
                        default=self._config_entry.data.get(CONF_LOCAL_MODEL, "llama3"),
                    ): str,
                }
            )
        else:
            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_CLOUD_API_KEY,
                        default=self._config_entry.data.get(CONF_CLOUD_API_KEY, ""),
                    ): str,
                    vol.Required(
                        CONF_CLOUD_MODEL,
                        default=self._config_entry.data.get(CONF_CLOUD_MODEL, "gpt-4o"),
                    ): str,
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )