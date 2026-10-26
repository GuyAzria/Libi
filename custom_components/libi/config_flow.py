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
# v3.37.0
# [ADDED v3.36.0 | 2026-10-26] Purpose: The AI settings for the chat. The cloud step chooses a
#   provider (Gemini, OpenAI or any OpenAI-compatible address), secrets use the password selector,
#   and the options flow can switch the AI mode and actually takes effect: its result is stored in
#   the entry's options, which the AI reads on top of the data, so no reload is needed.
# [ADDED v3.37.0 | 2026-10-26] Purpose: The AI settings are tested before they are saved: the server
#   must answer, accept the key and list the model (test-before-configure).
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .ai import async_test_connection
from .const import (
    DOMAIN,
    CONF_AI_MODE,
    AI_MODES,
    AI_MODE_NONE,
    AI_MODE_LOCAL,
    CLOUD_PROVIDER_CUSTOM,
    CLOUD_PROVIDER_GEMINI,
    CLOUD_PROVIDERS,
    CONF_CLOUD_BASE_URL,
    CONF_CLOUD_PROVIDER,
    CONF_LOCAL_API_KEY,
    CONF_LOCAL_URL,
    CONF_LOCAL_MODEL,
    CONF_CLOUD_API_KEY,
    CONF_CLOUD_MODEL,
)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
_TEXT = TextSelector()
_PROVIDER = SelectSelector(SelectSelectorConfig(
    options=CLOUD_PROVIDERS, mode=SelectSelectorMode.DROPDOWN, translation_key="cloud_provider"))


def _mode_schema(current: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_AI_MODE, default=current): vol.In(AI_MODES)})


def _local_schema(cur: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_LOCAL_URL, default=cur.get(CONF_LOCAL_URL, "http://localhost:11434")): _URL,
        vol.Required(CONF_LOCAL_MODEL, default=cur.get(CONF_LOCAL_MODEL, "llama3")): _TEXT,
        vol.Optional(CONF_LOCAL_API_KEY): _PASSWORD,
    })


def _cloud_schema(cur: dict, key_required: bool) -> vol.Schema:
    key = vol.Required(CONF_CLOUD_API_KEY) if key_required else vol.Optional(CONF_CLOUD_API_KEY)
    return vol.Schema({
        vol.Required(CONF_CLOUD_PROVIDER, default=cur.get(CONF_CLOUD_PROVIDER, CLOUD_PROVIDER_GEMINI)): _PROVIDER,
        key: _PASSWORD,
        vol.Required(CONF_CLOUD_MODEL, default=cur.get(CONF_CLOUD_MODEL, "")): _TEXT,
        vol.Optional(CONF_CLOUD_BASE_URL, default=cur.get(CONF_CLOUD_BASE_URL, "")): _TEXT,
    })


def _local_errors(user_input: dict) -> dict:
    errors = {}
    if not str(user_input.get(CONF_LOCAL_URL, "")).strip():
        errors[CONF_LOCAL_URL] = "invalid_url"
    if not str(user_input.get(CONF_LOCAL_MODEL, "")).strip():
        errors[CONF_LOCAL_MODEL] = "invalid_model"
    return errors


def _cloud_errors(user_input: dict, have_key: bool) -> dict:
    errors = {}
    if not have_key and not str(user_input.get(CONF_CLOUD_API_KEY, "")).strip():
        errors[CONF_CLOUD_API_KEY] = "invalid_key"
    if not str(user_input.get(CONF_CLOUD_MODEL, "")).strip():
        errors[CONF_CLOUD_MODEL] = "invalid_model"
    if (user_input.get(CONF_CLOUD_PROVIDER) == CLOUD_PROVIDER_CUSTOM
            and not str(user_input.get(CONF_CLOUD_BASE_URL, "")).strip()):
        errors[CONF_CLOUD_BASE_URL] = "invalid_url"
    return errors


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
                return self.async_create_entry(title="LIBI", data=self._user_input)
            if user_input[CONF_AI_MODE] == AI_MODE_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()

        return self.async_show_form(step_id="user", data_schema=_mode_schema(AI_MODE_LOCAL), errors={})

    # [ADDED v1.5.1 | 2026-08-10] Purpose: Collect local Ollama/LLM server URL and model name.
    async def async_step_local(self, user_input=None):
        """Handle the Local AI configuration step."""
        errors = {}
        if user_input is not None:
            errors = _local_errors(user_input)
            if not errors:
                errors = await self._test({**self._user_input, **user_input})
            if not errors:
                self._user_input.update(user_input)
                return self.async_create_entry(title="LIBI (Local AI)", data=self._user_input)
        return self.async_show_form(step_id="local", data_schema=_local_schema({}), errors=errors)

    # [ADDED v1.5.1 | 2026-08-10] Purpose: Collect Cloud API key and cloud model name.
    async def async_step_cloud(self, user_input=None):
        """Handle the Cloud API configuration step."""
        errors = {}
        if user_input is not None:
            errors = _cloud_errors(user_input, have_key=False)
            if not errors:
                errors = await self._test({**self._user_input, **user_input})
            if not errors:
                self._user_input.update(user_input)
                return self.async_create_entry(title="LIBI (Cloud API)", data=self._user_input)
        return self.async_show_form(step_id="cloud", data_schema=_cloud_schema({}, True), errors=errors)

    async def _test(self, settings: dict) -> dict:
        """[ADDED v3.37.0] test-before-configure: the server answers, the key works, the model exists."""
        problem = await async_test_connection(self.hass, settings)
        return {"base": problem} if problem else {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the Options Flow handler."""
        return LibiOptionsFlow()


class LibiOptionsFlow(config_entries.OptionsFlow):
    """Change the AI mode and its settings after setup.

    [CHANGED v3.36.0] The flow can now switch the mode itself, and what it stores is read: the AI
    takes the entry's options on top of its data. A secret left empty keeps the one already stored.
    """

    def __init__(self):
        """Initialise the options flow."""
        self._new: dict = {}

    def _current(self) -> dict:
        return {**self.config_entry.data, **self.config_entry.options}

    async def _test(self, settings: dict) -> dict:
        problem = await async_test_connection(self.hass, settings)
        return {"base": problem} if problem else {}

    async def async_step_init(self, user_input=None):
        """Choose the AI mode."""
        if user_input is not None:
            self._new = {CONF_AI_MODE: user_input[CONF_AI_MODE]}
            if user_input[CONF_AI_MODE] == AI_MODE_NONE:
                return self.async_create_entry(title="", data=self._new)
            if user_input[CONF_AI_MODE] == AI_MODE_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()
        return self.async_show_form(
            step_id="init", data_schema=_mode_schema(self._current().get(CONF_AI_MODE, AI_MODE_NONE)))

    async def async_step_local(self, user_input=None):
        """Local AI settings."""
        cur = self._current()
        errors = {}
        if user_input is not None:
            errors = _local_errors(user_input)
            if not errors:
                if not user_input.get(CONF_LOCAL_API_KEY) and cur.get(CONF_LOCAL_API_KEY):
                    user_input[CONF_LOCAL_API_KEY] = cur[CONF_LOCAL_API_KEY]
                errors = await self._test({**self._new, **user_input})
            if not errors:
                return self.async_create_entry(title="", data={**self._new, **user_input})
        return self.async_show_form(step_id="local", data_schema=_local_schema(cur), errors=errors)

    async def async_step_cloud(self, user_input=None):
        """Cloud AI settings."""
        cur = self._current()
        have_key = bool(cur.get(CONF_CLOUD_API_KEY))
        errors = {}
        if user_input is not None:
            errors = _cloud_errors(user_input, have_key)
            if not errors:
                if not user_input.get(CONF_CLOUD_API_KEY) and have_key:
                    user_input[CONF_CLOUD_API_KEY] = cur[CONF_CLOUD_API_KEY]
                errors = await self._test({**self._new, **user_input})
            if not errors:
                return self.async_create_entry(title="", data={**self._new, **user_input})
        return self.async_show_form(step_id="cloud", data_schema=_cloud_schema(cur, not have_key),
                                    errors=errors)
