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
"""The AI chat: an LLM drafts, Home Assistant decides.

[ADDED v3.87.0 | 2026-11-04] Purpose: The phones for the panel's MOVE NOTIFY / TTS block, each with the action that sends to
it (phone_list), and the notify actions an entry calls that Home Assistant does not have (notify_action_problems): the
user's train reminder had a phone's notify entity as its action, was saved, and said nothing at its time.
[ADDED v3.88.0 | 2026-11-05] Purpose: notify_action_problems also stops an entry that sends to a recipient of LIBI Global
no longer in Home Assistant; the walk over an entry's steps is yaml_to_libi.called_actions, shared with LIBI Global.

[ADDED v3.36.0 | 2026-10-26] Purpose: Turn a request written in any language into a ladder net.

The model is never trusted with anything that executes (CLAUDE.md RULES 7-11):

1. PLAN. The model reads the request and returns roles - "the button that starts it", "the lights
   to switch" - as search criteria: domains, device classes, keywords and areas. It names no
   entity.
2. SEARCH. LIBI looks the roles up in this Home Assistant's own registries, deterministically, and
   the user picks the entities, several per role if they like.
3. BUILD. The model writes the automation, script or scene and refers to every device only as
   "role:<id>". LIBI substitutes the entities the USER picked, and rejects the draft when it names
   any entity the user did not pick, any device, area, floor or label id, a service outside the
   allow list, a service whose target is of another domain, or a trigger or condition type LIBI
   does not allow. Home Assistant's own automation or script validator then has the last word.
4. The result is a draft net on the canvas. Nothing is written to Home Assistant until the user
   presses SAVE & COMPILE. Locks, alarms, covers, valves and sirens are flagged.

The internal language is English (RULE 20): the prompts and every field LIBI acts on are English;
only the texts shown to the user are in the user's language, and they are never interpreted.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import time
from typing import Any

import aiohttp
import yaml

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from .libi_to_yaml import ast_to_yaml, net_level
from .yaml_to_libi import DAY_BITS_DOMAINS, called_actions, day_bits_entity, day_bits_template, is_recipient_action
from .const import (
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    AI_MODE_NONE,
    CLOUD_BASE_URLS,
    CLOUD_PROVIDER_OPENAI,
    CONF_AI_MODE,
    CONF_CLOUD_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_CLOUD_MODEL,
    CONF_CLOUD_PROVIDER,
    CONF_LOCAL_API_KEY,
    CONF_LOCAL_MODEL,
    CONF_LOCAL_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

LEVELS = ("automation", "script", "scene")
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 4000
# [CHANGED v3.44.0] 8 was too few: watering on days the user picks needs a role per day, plus the
# valve, the meter, the weather, the time and the amount. A longer plan was cut without a word.
MAX_ROLES = 20
MAX_CANDIDATES = 80
LLM_TIMEOUT = aiohttp.ClientTimeout(total=120)
# [ADDED v3.48.0] The answers that mean "busy, try again": rate limited, overloaded, a gateway that timed
# out. A new model in preview answers 503 often. Each is asked again after these waits, in seconds.
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_DELAYS = (2, 6)


class AiError(Exception):
    """A failure that is shown to the user as it is. It never carries a key or a URL."""


# ---------------------------------------------------------------------------------------- settings

def ai_settings(hass: HomeAssistant) -> dict:
    """The AI settings of the LIBI entry: what the config flow stored, with the options on top."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return {CONF_AI_MODE: AI_MODE_NONE}
    entry = entries[0]
    return {**entry.data, **entry.options}


def ai_status(settings: dict) -> dict:
    """What the panel may know about the AI setup. Never the key, never the URL."""
    mode = settings.get(CONF_AI_MODE, AI_MODE_NONE)
    if mode == AI_MODE_LOCAL:
        return {"configured": bool(settings.get(CONF_LOCAL_URL) and settings.get(CONF_LOCAL_MODEL)),
                "mode": "local", "provider": "ollama", "model": settings.get(CONF_LOCAL_MODEL, "")}
    if mode == AI_MODE_CLOUD:
        return {"configured": bool(settings.get(CONF_CLOUD_API_KEY) and settings.get(CONF_CLOUD_MODEL)),
                "mode": "cloud", "provider": settings.get(CONF_CLOUD_PROVIDER, CLOUD_PROVIDER_OPENAI),
                "model": settings.get(CONF_CLOUD_MODEL, "")}
    return {"configured": False, "mode": "none", "provider": "", "model": ""}


TEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _model_listed(model: str, names: list[str]) -> bool:
    """Ollama lists "llama3:latest" for "llama3"; Gemini lists "models/gemini-x" for "gemini-x"."""
    model = model.strip()
    for name in names:
        name = str(name or "")
        if name in (model, f"{model}:latest") or name.endswith(f"/{model}") or name.split(":", 1)[0] == model:
            return True
    return False


async def async_test_connection(hass: HomeAssistant, settings: dict) -> str | None:
    """[ADDED v3.37.0] Asks the model server whether it answers, accepts the key and has the model.
    Returns a config flow error key, or None when everything checks out. A server that offers no
    model list is not an error, because that does not prove the model is wrong."""
    session = async_get_clientsession(hass)
    mode = settings.get(CONF_AI_MODE, AI_MODE_NONE)
    if mode == AI_MODE_LOCAL:
        url = str(settings.get(CONF_LOCAL_URL, "")).rstrip("/") + "/api/tags"
        headers = ({"Authorization": f"Bearer {settings[CONF_LOCAL_API_KEY]}"}
                   if settings.get(CONF_LOCAL_API_KEY) else {})
        model = str(settings.get(CONF_LOCAL_MODEL, ""))
    elif mode == AI_MODE_CLOUD:
        provider = settings.get(CONF_CLOUD_PROVIDER, CLOUD_PROVIDER_OPENAI)
        base = (settings.get(CONF_CLOUD_BASE_URL) or CLOUD_BASE_URLS.get(provider) or "").rstrip("/")
        url = base + "/models"
        headers = {"Authorization": f"Bearer {settings.get(CONF_CLOUD_API_KEY, '')}"}
        model = str(settings.get(CONF_CLOUD_MODEL, ""))
    else:
        return None
    try:
        async with session.get(url, headers=headers, timeout=TEST_TIMEOUT) as resp:
            if resp.status in (401, 403):
                return "invalid_auth"
            if resp.status in (404, 405, 501):
                return None  # no model list on this server; the chat will tell if the model is wrong
            if resp.status >= 400:
                return "cannot_connect"
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("[libi] AI connection test failed: %s", _sanitize(err))
        return "cannot_connect"
    data = data if isinstance(data, dict) else {}
    if mode == AI_MODE_LOCAL:
        names = [m.get("name") or m.get("model") for m in data.get("models") or [] if isinstance(m, dict)]
    else:
        names = [m.get("id") for m in data.get("data") or data.get("models") or [] if isinstance(m, dict)]
        names += [m.get("name") for m in data.get("models") or [] if isinstance(m, dict)]
    names = [n for n in names if n]
    if names and not _model_listed(model, names):
        return "model_not_found"
    return None


# ---------------------------------------------------------------------------------------- the LLM

def _sanitize(text: str) -> str:
    """Error text with anything that looks like a credential or a URL removed."""
    text = re.sub(r"https?://\S+", "<url>", str(text))
    text = re.sub(r"(?i)(key|token|bearer|authorization)[=: ]+\S+", r"\1=<hidden>", text)
    return text[:300]


def _parse_json(content: str) -> dict:
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    try:
        data = json.loads(content)
    except ValueError as err:
        raise AiError("The AI did not answer in the expected format. Try again.") from err
    if not isinstance(data, dict):
        raise AiError("The AI did not answer in the expected format. Try again.")
    return data


def _error_detail(text: str) -> str:
    """The reason the server gave, from an OpenAI, Gemini or Ollama error body, sanitised."""
    try:
        data = json.loads(text or "")
    except ValueError:
        return ""
    if isinstance(data, list) and data:
        data = data[0]
    err = data.get("error") if isinstance(data, dict) else None
    message = err.get("message") if isinstance(err, dict) else err
    return _sanitize(message)[:200] if isinstance(message, str) and message.strip() else ""


def _status_error(status: int, detail: str, local: bool) -> AiError:
    """The words for an error status. The model's own reason is added, never a key or a URL."""
    who = "The local AI server" if local else "The AI service"
    if status in (401, 403):
        text = f"{who} refused the API key ({status}). Check the key in the LIBI settings."
    elif status == 404:
        text = f"{who} does not know this model ({status}). Check the model name in the LIBI settings."
    elif status == 429:
        text = (f"{who} is limiting requests for this key ({status}), even after waiting. Wait a minute "
                "and try again, or check the quota of the key.")
    elif status in RETRY_STATUSES:
        text = (f"{who} is busy or unavailable right now ({status}), even after asking again. Try again "
                "in a minute, or choose another model in the LIBI settings.")
    else:
        text = f"{who} answered {status}."
    return AiError(f"{text} Reason: {detail}" if detail else text)


async def _post_json(session, url: str, body: dict, headers: dict) -> tuple[int, Any, str]:
    """[ADDED v3.48.0] One POST, asked again after a short wait while the server says it is busy.
    Returns the status, the JSON answer (None on an error) and the server's reason for an error."""
    delays = list(RETRY_DELAYS)
    while True:
        async with session.post(url, json=body, headers=headers, timeout=LLM_TIMEOUT) as resp:
            status = resp.status
            if status < 400:
                return status, await resp.json(content_type=None), ""
            detail = _error_detail(await resp.text())
        if status not in RETRY_STATUSES or not delays:
            return status, None, detail
        delay = delays.pop(0)
        _LOGGER.info("[libi] the AI server answered %s, asking again in %s s", status, delay)
        await asyncio.sleep(delay)


async def async_llm_json(hass: HomeAssistant, settings: dict, system: str,
                         messages: list[dict], schema: dict) -> dict:
    """One structured call to the configured model. Returns the parsed JSON object."""
    mode = settings.get(CONF_AI_MODE, AI_MODE_NONE)
    session = async_get_clientsession(hass)
    chat = [{"role": "system", "content": system}] + messages
    try:
        if mode == AI_MODE_LOCAL:
            url = str(settings.get(CONF_LOCAL_URL, "")).rstrip("/") + "/api/chat"
            headers = {}
            if settings.get(CONF_LOCAL_API_KEY):
                headers["Authorization"] = f"Bearer {settings[CONF_LOCAL_API_KEY]}"
            body = {"model": settings.get(CONF_LOCAL_MODEL), "messages": chat, "stream": False,
                    "format": schema, "options": {"temperature": 0.2}}
            status, data, detail = await _post_json(session, url, body, headers)
            if status >= 400:
                raise _status_error(status, detail, local=True)
            return _parse_json(((data or {}).get("message") or {}).get("content", ""))

        if mode == AI_MODE_CLOUD:
            provider = settings.get(CONF_CLOUD_PROVIDER, CLOUD_PROVIDER_OPENAI)
            base = (settings.get(CONF_CLOUD_BASE_URL) or CLOUD_BASE_URLS.get(provider) or "").rstrip("/")
            if not base:
                raise AiError("No API address is set for this AI provider.")
            headers = {"Authorization": f"Bearer {settings.get(CONF_CLOUD_API_KEY, '')}"}
            body = {"model": settings.get(CONF_CLOUD_MODEL), "messages": chat, "temperature": 0.2,
                    "response_format": {"type": "json_schema",
                                        "json_schema": {"name": "libi", "schema": schema}}}
            status, data, detail = await _post_json(session, base + "/chat/completions", body, headers)
            if status == 400:
                # Some OpenAI-compatible servers know only the plain JSON mode. A new body, so the
                # request already sent is never changed after the fact.
                plain = {**body, "response_format": {"type": "json_object"}}
                status, data, detail = await _post_json(session, base + "/chat/completions", plain, headers)
            if status >= 400:
                raise _status_error(status, detail, local=False)
            choices = (data or {}).get("choices") or [{}]
            return _parse_json(((choices[0] or {}).get("message") or {}).get("content", ""))
    except AiError:
        raise
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.warning("[libi] AI request failed: %s", _sanitize(err))
        raise AiError("The AI could not be reached. Check the address in the LIBI settings.") from err
    raise AiError("AI is not set up. Choose a model in Settings > Devices & services > LIBI > Configure.")


# ---------------------------------------------------------------------------------------- prompts

# [ADDED v3.50.0] Every setting a proposed helper may carry, so a structured-output model can fill them:
# Gemini answers {} for an object schema without properties. "initial" is text because it is a number
# for input_number and text for input_select; clean_new_helpers converts it per domain.
HELPER_SETTINGS_SCHEMA: dict = {"type": "object", "properties": {
    "icon": {"type": "string"}, "min": {"type": "number"}, "max": {"type": "number"},
    "step": {"type": "number"}, "initial": {"type": "string"}, "mode": {"type": "string"},
    "unit_of_measurement": {"type": "string"}, "has_date": {"type": "boolean"},
    "has_time": {"type": "boolean"}, "options": {"type": "array", "items": {"type": "string"}},
    "minimum": {"type": "number"}, "maximum": {"type": "number"}, "duration": {"type": "string"},
    "restore": {"type": "boolean"},
    # [ADDED v3.53.0] schedule: the days and the span of time it is on.
    "days": {"type": "array", "items": {"type": "string"}}, "from": {"type": "string"},
    "to": {"type": "string"},
}}

# [ADDED v3.73.0] The kinds of line a request is split into: each one LIBI can see in the logic itself
# (requirement_report), and "other" for the rest, which only the model's own word places.
REQUIREMENT_KINDS = ("time", "days", "weather_now", "forecast", "amount", "time_limit", "message", "card", "other")
MAX_REQUIREMENTS = 16

PLAN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        # [ADDED v3.73.0] What the user asked for, one line each, of a kind LIBI checks in the logic.
        "requirements": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                           "kind": {"type": "string", "enum": list(REQUIREMENT_KINDS)}},
            "required": ["id", "text", "kind"],
        }},
        "reply": {"type": "string"},
        "intent": {"type": "string", "enum": ["answer", "create", "modify"]},
        "target_net": {"type": "string"},
        "level": {"type": "string", "enum": list(LEVELS)},
        "name": {"type": "string"},
        "roles": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "label": {"type": "string"},
                "purpose": {"type": "string", "enum": ["trigger", "condition", "target", "measure"]},
                "domains": {"type": "array", "items": {"type": "string"}},
                "device_classes": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "area_keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "label", "purpose", "domains", "device_classes", "keywords", "area_keywords"],
        }},
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                           "choices": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "text", "choices"],
        }},
        "new_helpers": {"type": "array", "items": {
            "type": "object",
            "properties": {"role": {"type": "string"}, "domain": {"type": "string"},
                           "name": {"type": "string"}, "settings": HELPER_SETTINGS_SCHEMA},
            "required": ["role", "domain", "name", "settings"],
        }},
    },
    "required": ["reply", "intent", "target_net", "level", "name", "roles", "questions", "new_helpers", "requirements"],
}

PLAN_SYSTEM_TEMPLATE = """You help a Home Assistant user describe an automation, script or scene that LIBI will build.
You do NOT know the user's devices and you must NOT name any entity_id, device_id or area_id.
Instead, describe every device the logic needs as a ROLE with search criteria. LIBI searches the
user's Home Assistant with them and the user picks the entities from a list.

The message may end with NETS ON THE CANVAS: the automations, scripts and scenes the user has open
in LIBI, as YAML, each with its NET number (as the canvas shows it) and its net id - and only those; other automations are not shown to you. Use
them to answer questions about them and to change them. When the user asks for new logic "with the
devices of NET 1", give a role for every device of that net the new logic needs (its valve AND its water
meter, for example), with the words of those entity_ids as keywords. It may also list the user's HELPERS. A
helper the logic reads or sets is a role, like a device: when the user names one ("I already have a helper
...", "use my helper ...") or one fits (a schedule, a timer, a number for the litres), give it a role with
its domain and the words of its name as keywords - not a new helper, not a new device. It may also list
NAMED, NOT FOUND: names the user's message quotes that nothing in this Home Assistant has. A helper the user says
they have that is listed there is gone: propose it in new_helpers under that very name, with its settings, in its
role - and days and hours the user sets on the screen are the alarm clock below, not a schedule.

Answer with JSON only, matching the schema:
- intent: "answer" when the user only asks a question (about a net, or in general) - then give the
  answer in reply and leave roles and questions empty; "modify" ONLY when the user names the net to
  change by its NET number and asks to change it ("update NET 3", "add a timer to NET 2"); "create" for
  everything else - also when the request uses the devices of a net or does what a net already does,
  and whenever the user asks for a new net. LIBI adds new logic as a new net after the last one, and
  saves a change as a new version of the net, so the user can go back to the one before.
- target_net: for "modify", the net id of the net the user named, exactly as listed; otherwise "".
- reply: IN THE USER'S LANGUAGE. For "answer", the answer itself (it may be several sentences). For
  "create" and "modify", one or two short sentences: what you understood and what to pick.
- For "modify", the roles describe every device the NEW version needs, including the devices the net
  already uses (LIBI ticks those for the user) and any new ones (for example a weather entity).
- level: "automation" if something must start it (a button, a sensor, a time); "script" if the user
  starts it by hand; "scene" for a set of fixed states.
- name: a short name for it, in the user's language.
- roles: every device and every helper the logic touches. For each:
  - id: snake_case English, e.g. "trigger_buttons", "living_room_lights", "garden_valves".
  - label: what the user picks here, in the user's language.
  - purpose: trigger | condition | target | measure.
  - domains: Home Assistant entity domains to search. Physical buttons are often "event",
    "sensor" (an action sensor of a remote), "binary_sensor", "button" or "input_button" - list all
    that apply. Lights: "light", and "switch" when lights may be relays. Irrigation outputs:
    "valve", "switch". Water measurement: "sensor".
  - device_classes: Home Assistant device classes that fit (e.g. "water", "moisture",
    "volume_flow_rate", "motion", "door"), or [] when any fits.
  - keywords: words to match in entity and device names, in English AND in the user's language,
    e.g. ["button","remote","switch"] and the same words as the user writes them. When the user points at a
    device a net on the canvas uses ("the valve in NET 1"), add the words of that entity_id too, e.g.
    ["valve","garden"].
  - area_keywords: area names the user mentioned, in English AND in the user's language, e.g.
    ["living room","salon"] and the name as the user writes it; [] when no area was said.
  Do not invent a specific device; when the user did not say which one, the role asks them to pick.
  Being at a place is a zone: a role with domains ["zone"] for the place AND a role with domains ["person",
  "device_tracker"] for who must be there - two roles, never one for both, and never a question for either: LIBI
  lists all the user's zones and people to pick from. A place the user chooses on the screen is no zone role but a
  helper (new_helpers, below), with the role for who must be there.
  A message to a phone is not a device: when the user names the notify services to use (for example
  notify.mobile_app_phone), give no role for them; the build writes them as they are.
- new_helpers: when the user wants to set something from the screen (days, a time, an amount, an
  on/off choice) and no existing HELPER fits, propose new helpers here - LIBI creates them only after
  the user approves. Each: role (the role id it fills; also list that role in roles with the helper's
  domain), domain, name (in the user's language), settings. {HELPER_RULES}
  Propose one helper for EVERY value the user said they set from the screen, each with its own role
  id - not only the first one. Days and a time the user picks are set as on an alarm clock: ONE time
  helper (input_datetime, settings {"has_time": true, "has_date": false}, role "start_time") and ONE
  days helper, a number of 8 bits whose bits are the days - bit 1 (value 1) Sunday, bit 2 (2) Monday,
  bit 3 (4) Tuesday ... bit 7 (64) Saturday (input_number, settings {"min": 0, "max": 255, "step": 1,
  "mode": "box"}, role "days", named "<what it is> - days" in the user's language). The user sets the
  time and ticks the days as checkboxes on the card - never a switch for each day. So
  also when the user names a schedule helper of their own for the days and hours they choose on the
  screen: a schedule's days and hours are set only in its own settings, never on a dashboard card -
  propose the alarm clock, give the schedule no role, and say so in the reply. A schedule helper (a
  weekly calendar; settings days, from, to, e.g. {"days": ["mon","tue","thu"], "from": "06:00",
  "to": "06:30"}) only when the user asks for a schedule that is not set from the screen.
  For an amount, an input_number with min, max, step and unit_of_measurement, which the card shows next to
  the value (e.g. litres: min 0, max 500, step 5, unit_of_measurement "L"; minutes: unit_of_measurement
  "min"). So "days and times chosen in the UI, and the amount from a variable" is a time helper,
  a days helper and an amount helper. A value the user sets from the screen is a helper, never a
  question. A zone the user chooses on the screen is an input_select in role "zone_choice", settings {}: LIBI puts
  the user's zones in it, as a person's state names them.
  [] when nothing new is needed.
- questions: what you must know before building that is not a device: durations, times, days,
  thresholds, whether a dashboard card is wanted and on which dashboard. Each with an English
  snake_case id, the text in the user's language, and choices (or [] for a free answer). Ask only
  what you really need; use sensible defaults otherwise and say so in the reply. LIBI itself asks
  whether to add an on/off switch for the whole automation, whether to send a message when it starts
  and when it ends (a notification or spoken), what to do when a device it switches is offline, and
  whether to send a message when a battery is low, and adds what the user answers: never ask those,
  and plan no role or helper for such a switch. Do ask what else could go wrong in this
  logic that the user must decide - a sensor it reads that stops reporting, a value out of range -
  when it matters here.
- requirements: what the user asked for, ONE line per point, so LIBI can check the logic against it
  and show the user where each one is. Each: id ("r1", "r2", ...), text (the point, short, in the
  user's language), kind - how LIBI can see it in the logic: "time" (it starts at a time of day, by a
  schedule or by the sun), "days" (only on certain days), "weather_now" (the weather now, e.g. it is
  raining), "forecast" (the weather forecast, e.g. rain expected today), "amount" (a number reached,
  e.g. litres), "time_limit" (a maximum time, or how long something stays on), "message" (a
  notification or spoken text), "card" (a dashboard card), "other" (anything else). A point that asks
  two of these is two lines: "rain now or rain expected today" is a weather_now line and a forecast
  line. [] for a question.
"""

BUILD_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "level": {"type": "string", "enum": list(LEVELS)},
        "name": {"type": "string"},
        "description": {"type": "string"},
        # [CHANGED v3.55.0] JSON text, not an object: a structured-output model (Gemini) answers {} for an
        # object schema without properties, and a configuration cannot be described property by property.
        "config": {"type": "string"},
        "ui_card": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
        # [ADDED v3.73.0] Where the logic does each line of the request: the trigger id of its option, and how.
        "covers": {"type": "array", "items": {
            "type": "object",
            "properties": {"requirement": {"type": "string"}, "trigger_id": {"type": "string"},
                           "how": {"type": "string"}},
            "required": ["requirement", "trigger_id", "how"],
        }},
    },
    "required": ["reply", "level", "name", "description", "config", "ui_card", "notes", "covers"],
}

BUILD_SYSTEM_TEMPLATE = """You write a Home Assistant configuration that LIBI turns into a ladder diagram.
Answer with JSON only, matching the schema.

Devices: you never write an entity_id. Every device is written as "role:<role id>" from the ROLES
list, e.g. "entity_id": "role:trigger_buttons". A role may hold several entities; LIBI fills them in.
Never write device_id, area_id, floor_id or label_id, and no device triggers or device actions.

config and ui_card are JSON TEXT in a string: the JSON of the object described below, e.g.
"config": "{\\"mode\\": \\"single\\", \\"triggers\\": [...], ...}". An empty ui_card is "".
config, by level:
- automation: {"mode": "single"|"restart"|"queued"|"parallel", "triggers": [...], "conditions": [...],
  "actions": [...]}
- script: {"mode": ..., "sequence": [...]}
- scene: {"actions": [...]} where every action switches one role on or off, e.g.
  {"action": "light.turn_on", "target": {"entity_id": "role:lights"}}
{RULES}
  A press of a button/input_button/event entity is {"trigger": "state", "entity_id": "role:..."}
  with no "to". A remote's action sensor uses "to" with the action value only if the user said it.
Days of the week: a "time" condition with "weekday": ["sun", "tue", "thu", "sat"]. When the ROLES hold a
  days helper (role "days": its 8 bits are the days the user ticks on the screen, bit 1 Sunday ... bit 7
  Saturday), the days are ONE condition, written exactly so - LIBI draws it as one CMP DAY block:
  {"condition": "template", "value_template": "{DAY_BITS}"}. The time the user sets (an input_datetime role,
  e.g. start_time) is the trigger {"trigger": "time", "at": "role:<time role>", "id": "start"}, and the days
  are checked right after it.
A zone the user chooses on the card (ZONE CHOICE in the message): who must be there is in it when their state is the
  zone chosen - {"condition": "state", "entity_id": "role:<who>", "state": "role:<zone choice role>"}, which Home
  Assistant compares with the state of that dropdown, and LIBI draws as one CMP EQ. No zone condition and no template
  for it.
A schedule role is on during the days and hours the user marked in it: start with {"trigger": "state",
  "entity_id": "role:<schedule role>", "to": "on"}, and no other day or time check - unless the message has an
  ALARM CLOCK: then the logic starts at its time and runs on its days, and no schedule starts it.
Weather: read the forecast with {"action": "weather.get_forecasts", "target": {"entity_id": "role:<weather
  role>"}, "data": {"type": "daily"}, "response_variable": "forecast"}. The weather role's state is the weather
  NOW and forecast[0] is TODAY, so "rain now or rain expected today" checks both, e.g. "{{ states('role:<weather
  role>') not in ['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail'] and forecast['role:<weather
  role>'].forecast[0].condition not in ['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail'] }}".
  The weather role must have exactly one entity.
  The weather NOW is checked for rain, never for fair weather: before sunrise it is clear-night, and a cloudy morning
  is no rain, so a check that it is sunny would hold the logic back on a dry day. Written so: {"condition": "not",
  "conditions": [{"condition": "state", "entity_id": "role:<weather role>", "state": ["rainy", "pouring",
  "lightning-rainy", "snowy-rainy", "hail"]}]}, or as the template above.
Watering by an amount, with a time limit - the ladder way, nothing waits inside a run:
  - start (id "start"): the trigger of the time (or of the schedule) the user set. Its option is
    {"conditions": [{"condition": "trigger", "id": "start"}, <the days, when the user ticks them>, <the rain NOW:
    not raining, as Weather says>], "sequence": [<weather.get_forecasts, as above>, {"condition":
    "template", "value_template": "{{ forecast['role:<weather role>'].forecast[0].condition not in [...] }}"},
    <the valve on>]}. Skipping on "rain now or rain expected today" checks both: the weather now AND today's
    forecast.
  - the amount reached (id "amount_reached"): a meter that counts from 0 again each time the valve opens is
    {"trigger": "numeric_state", "entity_id": "role:<meter>", "above": "role:<amount helper>", "id":
    "amount_reached"}, and its option turns the valve off when it is on. numeric_state fires only when the count
    crosses the amount, so the count of the run before, which the meter shows until it reports its reset, does
    not fire it. A meter that keeps counting (a total) needs its reading at the start kept in a helper.
  - the time limit (id "time_limit"): {"trigger": "state", "entity_id": "role:<valve>", "to": "on", "for":
    {"minutes": "{{ states('role:<minutes helper>') | int(30) }}"}, "id": "time_limit"}; its option turns the
    valve off and sends the messages.
  - closed by hand: nothing to write - with the valve off, neither of the two fires.
  - a restart: a "for" does not outlive one, so {"trigger": "homeassistant", "event": "start", "id":
    "restarted"}, whose option turns the valve off when it is on.
Messages to a phone: one {"action": "notify.mobile_app_<phone>", "data": {"message": "..."}} per phone - when the
  message lists PHONES, exactly the services listed there, each once; otherwise the notify services the user
  named, as written. A service listed as MISSING under MESSAGE SERVICES does not exist: leave it out and say so
  in notes. A message spoken aloud is the phone reading it - the Home Assistant app on Android: {"action":
  "notify.mobile_app_<phone>", "data": {"message": "TTS", "data": {"tts_text": "..."}}}, one per phone; with a
  notification as well, the notification and right after it its spoken twin, phone by phone. tts.speak is for a
  speaker only (a media_player role).
When the request changes an existing net (CURRENT NET below), write the WHOLE new version of it.
THE LADDER LIBI DRAWS - write the logic the way a ladder works, like the user's own automations: every rung is
"when THIS happens, if THESE hold, do THAT", and no rung waits for another.
- One trigger for every event the logic reacts to - a time, a schedule starting, a button, an amount reached, a
  time limit, a restart - each with an "id" (short snake_case: start, amount_reached, time_limit).
- With more than one trigger, "actions" is ONE "choose" with one option per trigger id, in the order of the
  triggers: its "conditions" start with {"condition": "trigger", "id": "<id>"}, then the checks of that option;
  its "sequence" is what happens then. With one trigger, "actions" is its steps. Home Assistant runs only the
  first option that holds, so never two options for one trigger id: every check of an event is in its option.
- Never wait inside a run: no wait_for_trigger, no wait_template, no stop, and no "wait." in a template. What it
  would wait for is a trigger with an option of its own; how long a thing may stay on is that trigger's "for".
- The steps of an option run in order, and a condition step stops them when it fails: that is how "skip when
  ..." is written inside an option (the rain of today's forecast, read just before it, for example). Never put
  an if or a choose inside another step (if, choose, repeat, parallel).
- The elements: a check of a state or a number is a contact or a CMP block (CMP TIME for a time of day, CMP DAY
  for weekdays, CMP DATETIME for a schedule); turning one device on or off is a coil; setting a helper
  (input_number.set_value, input_datetime.set_datetime, input_select.select_option) is a MOVE; a message is a
  MOVE NOTIFY; spoken text (tts.speak) is a MOVE TTS; a delay, and the "for" of a trigger, is a TON;
  counter.increment is a CTU.

ui_card: "" when the logic reads helpers the user sets (days, a time, an amount, an on/off choice): LIBI
builds that card itself, the same every time - every setting, the days as one row of buttons, the
devices. When the logic reads none and the user asked for a card: a Lovelace card config (built-in card
types only, e.g. "entities", "tile", "glance", "vertical-stack"), with entities as role references.
Otherwise "".
reply: one or two sentences IN THE USER'S LANGUAGE describing what you built.
description: one sentence in the user's language. notes: anything the user should check, in the
user's language, or [].
REQUIREMENTS in the message are the user's request, one line each: the logic must do every one of them, and LIBI
checks it. covers: for each one, its id as "requirement", the trigger id of the option that does it as
"trigger_id" ("" when no one option does, e.g. the card), and "how": one short sentence in the user's language.
The message may also carry the user's HELPERS and, per role, the DEVICES LIBI found. Use them to reuse a
helper that already exists instead of inventing one, and to read units (litres, %, W). The rules above still hold:
devices only as "role:<id>", never an entity_id copied from that context.
"""


# ---------------------------------------------------------------------------------------- plan

_ID_RE = re.compile(r"[^a-z0-9_]+")


def _clean_id(value: Any, fallback: str) -> str:
    out = _ID_RE.sub("_", str(value or "").strip().lower()).strip("_")[:40]
    return out or fallback


def _str_list(value: Any, limit: int = 12, size: int = 60) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v)[:size] for v in value if isinstance(v, (str, int, float)) and str(v).strip()][:limit]


@callback
def present_domains(hass: HomeAssistant) -> set[str]:
    return {s.domain for s in hass.states.async_all()}


@callback
def clean_plan(hass: HomeAssistant, raw: dict, net_ids: set[str] | None = None) -> dict:
    """The plan reduced to what LIBI understands. A domain that does not exist in this Home
    Assistant is dropped, ids become safe snake_case, and every list is capped. [v3.40.0] A target
    net is kept only when it is one of the nets on the canvas; otherwise a change becomes new logic."""
    domains_here = present_domains(hass)
    intent = raw.get("intent") if raw.get("intent") in ("answer", "create", "modify") else "create"
    target = str(raw.get("target_net") or "")
    if intent != "modify" or not net_ids or target not in net_ids:
        target = ""
        if intent == "modify":
            intent = "create"
    level = raw.get("level") if raw.get("level") in LEVELS else "automation"
    roles, seen = [], set()
    for i, r in enumerate(raw.get("roles") or []):
        if not isinstance(r, dict) or len(roles) >= MAX_ROLES:
            continue
        rid = _clean_id(r.get("id"), f"role_{i + 1}")
        while rid in seen:
            rid += "_x"
        seen.add(rid)
        purpose = r.get("purpose") if r.get("purpose") in ("trigger", "condition", "target", "measure") else "target"
        roles.append({
            "id": rid,
            "label": str(r.get("label") or rid)[:80],
            "purpose": purpose,
            # [CHANGED v3.51.0] A helper domain stays even when no helper of it exists yet: LIBI can create one.
            # [CHANGED v3.62.0] A message domain too: a phone role is made optional (optional_message_roles)
            # instead of losing its domain and asking for a pick that cannot be made.
            "domains": [d for d in _str_list(r.get("domains"), 8, 30)
                        if d in domains_here or d in HELPER_SPEC or d in MESSAGE_DOMAINS],
            "device_classes": [_clean_id(d, "") for d in _str_list(r.get("device_classes"), 8, 30)],
            "keywords": _str_list(r.get("keywords")),
            "area_keywords": _str_list(r.get("area_keywords")),
            # [ADDED v3.54.0] Set by LIBI for a device of a named NET (roles_for_named_nets); the build
            # leaves an optional role out when nothing was picked for it.
            "optional": r.get("optional") is True,
            # [ADDED v3.60.0] Set by LIBI for a helper the user's message names (roles_for_named_helpers): the
            # chat says so. It changes no check.
            "named": r.get("named") is True,
        })
        # [ADDED v3.74.0] Set by LIBI for a schedule the user named that gave way to the alarm clock: the chat says why.
        # Only where it is set, so a role comes back from the browser as LIBI made it.
        if r.get("replaced") is True:
            roles[-1]["replaced"] = True
        # [ADDED v3.78.0] Set by LIBI for a helper the user's message names that this Home Assistant does not have
        # (roles_for_missing_helpers): the name, which the chat shows and the new helper is given.
        if isinstance(r.get("missing"), str) and r["missing"].strip():
            roles[-1]["missing"] = r["missing"].strip()[:60]
        # [ADDED v3.84.0] Set by LIBI for the zone chosen on the card (zone_choices): the build is told how it is read.
        if r.get("zone_choice") is True and roles[-1]["domains"] == ["input_select"]:
            roles[-1]["zone_choice"] = True
    questions, qseen, theirs = [], set(), 0
    for i, q in enumerate(raw.get("questions") or []):
        if not isinstance(q, dict):
            continue
        qid = _clean_id(q.get("id"), f"q{i + 1}")
        # [CHANGED v3.80.0] Six of the model's, and LIBI's own (SAFETY_QUESTIONS), which come back from the browser.
        mine = qid in SAFETY_QUESTIONS
        if qid in qseen or (not mine and theirs >= 6):
            continue
        qseen.add(qid)
        theirs += not mine
        questions.append({"id": qid, "text": str(q.get("text") or "")[:300],
                          "choices": _str_list(q.get("choices"), 8, 80)})
    # [ADDED v3.73.0] The lines of the request, each of a kind LIBI checks in the logic. The text is only shown.
    requirements, rseen = [], set()
    given = raw.get("requirements") if isinstance(raw.get("requirements"), list) else []
    for i, item in enumerate(given):
        if not isinstance(item, dict) or len(requirements) >= MAX_REQUIREMENTS:
            continue
        rid, text = _clean_id(item.get("id"), f"r{i + 1}"), str(item.get("text") or "").strip()[:200]
        if not text or rid in rseen:
            continue
        rseen.add(rid)
        requirements.append({"id": rid, "text": text,
                             "kind": item.get("kind") if item.get("kind") in REQUIREMENT_KINDS else "other"})
    new_helpers = []
    if intent != "answer":
        new_helpers, roles = clean_new_helpers(raw.get("new_helpers"), roles)
    if intent == "answer":
        roles, questions, requirements = [], [], []
    return {"requirements": requirements,
            "reply": str(raw.get("reply") or "")[:4000 if intent == "answer" else 1200],
            "intent": intent, "target_net": target, "level": level,
            "name": str(raw.get("name") or "")[:80] or "AI automation",
            "roles": roles, "questions": questions, "new_helpers": new_helpers}


def _norm(text: Any) -> str:
    return re.sub(r"[\s_\-.]+", " ", str(text or "").lower()).strip()


def canvas_entities(hass: HomeAssistant, nets: Any, by_id: dict[str, str]) -> dict[str, str]:
    """[ADDED v3.49.0] Every entity the nets on the page use, with where: "NET 2 · Garden". Read from
    the YAML LIBI compiles for those nets (canvas_context), so only what the page shows is used."""
    out: dict[str, str] = {}
    for index, net in enumerate(nets if isinstance(nets, list) else []):
        if not isinstance(net, dict):
            continue
        text = by_id.get(str(net.get("id") or "")[:40], "")
        where = f"NET {index + 1} · {str(net.get('name') or '')[:40]}".rstrip(" ·")
        for m in _ENTITY_RE.finditer(text):
            eid = m.group(0)
            if eid not in out and hass.states.get(eid):
                out[eid] = where
    return out


# [ADDED v3.60.0] Device classes of one kind of quantity. The user's garden "flow meter" role asked for water and
# volume_flow_rate, and the meter that counts the litres - the one NET 1 uses - is of class volume, so it was not
# listed at all. A related class passes the class filter; only a class the role asked for earns the bonus.
RELATED_CLASSES = ({"water", "volume", "volume_storage", "volume_flow_rate"},)
# [ADDED v3.83.0] The domains whose every entity a role lists: a few, each known by name. [CHANGED v3.84.0] And the
# trackers: who must be there is a person or a phone, all of them listed.
LIST_ALL_DOMAINS = {"zone", "person", "device_tracker"}
# [ADDED v3.83.0] Who can be at a place: a person, or the tracker of a phone.
PRESENCE_DOMAINS = ("person", "device_tracker")
# [ADDED v3.84.0] The zone a card chooses: a setting whose role says zone - or location, place, area or region, or whose
# helper has a map icon, in a plan about who or where - held in a dropdown of the user's zones (zone_choices).
_ZONE_CHOICE_RE = re.compile(r"(?:^|_)(?:zones?|geofences?)(?:_|$)")
_PLACE_CHOICE_RE = re.compile(r"(?:^|_)(?:locations?|places?|areas?|regions?)(?:_|$)")
ZONE_CHOICE_DOMAINS = {"input_select", "input_text", "select", "text"}


def _related_classes(classes: set[str]) -> set[str]:
    out = set(classes)
    for family in RELATED_CLASSES:
        if classes & family:
            out |= family
    return out


@callback
def find_candidates(hass: HomeAssistant, role: dict, on_canvas: dict[str, str] | None = None) -> dict:
    """[RULE 8] The entities a role can be, found in the registries without the model. Entities that
    match a keyword or an area come first and are marked exact; when nothing matches, the closest
    entities of the right domain are offered and marked so.

    [CHANGED v3.49.0] An entity a net on the page already uses ranks above everything else and says
    which net, because "the valve in NET 1" is how a user names a device. It is offered, not ticked:
    the user still picks."""
    on_canvas = on_canvas or {}
    domains = role.get("domains") or []
    if not domains:
        return {"items": [], "exact": False}
    ent_reg, dev_reg, area_reg = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    keywords = [_norm(k) for k in role.get("keywords") or [] if _norm(k)]
    areas = [_norm(k) for k in role.get("area_keywords") or [] if _norm(k)]
    classes = set(role.get("device_classes") or [])
    related = _related_classes(classes)

    scored = []
    for state in hass.states.async_all(domains):
        entry = ent_reg.async_get(state.entity_id)
        device = dev_reg.async_get(entry.device_id) if entry and entry.device_id else None
        area_id = (entry.area_id if entry else None) or (device.area_id if device else None)
        area = area_reg.async_get_area(area_id) if area_id else None
        area_name = area.name if area else ""
        device_name = (device.name_by_user or device.name) if device else ""
        dclass = state.attributes.get("device_class") or (entry.original_device_class if entry else None) or ""
        # [CHANGED v3.78.0] A setting is matched by its own name, not by its kind: "schedule" or "number" is in the
        # entity_id of every schedule and every input_number, so the model's word for the kind made each of the user's
        # helpers of that kind an exact match, and LIBI proposed no helper of its own (the user's chat of 2026-11-01).
        own = state.entity_id.split(".", 1)[1] if state.domain in SETTING_DOMAINS else state.entity_id
        text = _norm(f"{own} {state.name} {device_name}")
        area_text = _norm(area_name)

        score = 0
        score += sum(3 for k in keywords if k in text)
        score += sum(5 for a in areas if a and (a in area_text or a in text))
        # [CHANGED v3.54.0] An entity with no device class is not hidden by a class filter (a weather entity
        # has none, and "weather or rain sensor" listed only the moisture sensors); it only gets no bonus.
        # A device a net on the page uses must fit the class too: the water meter of NET 1 (volume) is not a
        # rain sensor, however near it is.
        class_ok = not classes or dclass in related or not dclass
        # [CHANGED v3.69.0] A related class is a match as well, ranked below the class asked for. The user's garden
        # meter (volume, in litres) had none of the model's words for a water meter, so the house meter and the
        # kitchen filter (water), which had, filled the list and it was not offered at all.
        if classes and dclass in related:
            score += 2 if dclass in classes else 1
        item = {"entity_id": state.entity_id, "name": state.name, "area": area_name,
                "device_class": dclass, "state": state.state}
        if state.entity_id in on_canvas and class_ok:
            score += 10
            item["on_canvas"] = on_canvas[state.entity_id]
        scored.append((score, class_ok, item))

    wanted_area = bool(areas)
    exact = [s for s in scored if s[1] and (s[0] > (4 if wanted_area else 0) or "on_canvas" in s[2])]
    pool = exact or [s for s in scored if s[1]] or scored
    # [ADDED v3.83.0] A zone or a person is one of a few the user knows by name: all of them, the ones the words match
    # first - the user's zone "Yulia in Lod" was not offered for a reminder "at work", only the zones named with it.
    # [CHANGED v3.84.0] The whole list is no fallback, so the chat does not call it the closest; the people come before
    # the trackers of their phones.
    listed = set(domains) <= LIST_ALL_DOMAINS
    if listed:
        pool = [s for s in scored if s[1]] or scored
    people_first = "person" if {"person", "device_tracker"} <= set(domains) else ""
    pool.sort(key=lambda s: (-s[0], s[2]["entity_id"].split(".")[0] != people_first, s[2]["name"].lower()))
    return {"items": [s[2] for s in pool[:MAX_CANDIDATES]], "exact": bool(exact) or (listed and bool(pool)),
            "total": len(pool)}


# ---------------------------------------------------------------------------------------- build

# Where a service is allowed at all. A domain listed here may only act on its own entities.
ENTITY_SERVICE_DOMAINS = {
    "light", "switch", "fan", "cover", "climate", "media_player", "valve", "lock",
    "alarm_control_panel", "input_boolean", "input_number", "input_select", "input_text",
    "input_datetime", "input_button", "button", "number", "select", "scene", "script", "siren",
    "humidifier", "water_heater", "vacuum", "lawn_mower", "timer", "counter", "automation",
    "remote", "text", "date", "time", "datetime",
}
# Services that send a message or speak and need no device of their own domain.
MESSAGE_DOMAINS = {"notify", "persistent_notification"}
MESSAGE_SERVICES = {"tts.speak"}
# [ADDED v3.40.0] Services that only READ and answer into a response_variable. Each one acts on
# entities of its own domain, which the user picked, like any entity service.
READ_SERVICES = {"weather.get_forecasts"}
GENERIC_SERVICES = {"homeassistant.turn_on", "homeassistant.turn_off", "homeassistant.toggle"}
# Within scene and script only switching is allowed, never creating or applying ad hoc ones.
RESTRICTED = {"scene": {"turn_on"}, "script": {"turn_on", "turn_off", "toggle"},
              "automation": {"turn_on", "turn_off", "toggle", "trigger"}}
SENSITIVE_DOMAINS = {"lock", "alarm_control_panel", "cover", "valve", "siren"}

TRIGGERS = {"state", "numeric_state", "time", "time_pattern", "sun", "template", "homeassistant", "zone"}
CONDITIONS = {"state", "numeric_state", "time", "sun", "template", "and", "or", "not", "trigger", "zone"}
FORBIDDEN_KEYS = {"device_id", "area_id", "floor_id", "label_id", "device", "domain", "type"}
# Dicts whose keys are free: service data, variables, durations.
FREE_KEYS = {"data", "variables", "for", "delay", "timeout", "offset"}
KNOWN_KEYS = {
    "mode", "max", "max_exceeded", "triggers", "trigger", "platform", "conditions", "condition",
    "actions", "action", "service", "sequence", "target", "entity_id", "to", "from", "for", "above",
    "below", "attribute", "value_template", "at", "event", "offset", "hours", "minutes", "seconds",
    "milliseconds", "days", "id", "zone", "weekday", "after", "before", "state", "enabled", "alias",
    "continue_on_error", "delay", "wait_template", "wait_for_trigger", "timeout",
    "continue_on_timeout", "choose", "default", "if", "then", "else", "repeat", "count", "while",
    "until", "for_each", "parallel", "stop", "error", "variables", "response_variable", "data",
    "message", "title", "media_player_entity_id", "description", "match",
    # [ADDED v3.41.0] Valid in Home Assistant, and rejected before: state trigger and sun condition keys.
    "not_from", "not_to", "after_offset", "before_offset",
}

LEGACY_KEYS = {"platform", "service"}


# [ADDED v3.43.0] The helpers the AI may propose and the settings each takes - the same kinds and fields
# the Helper tab of the panel creates, through the same <domain>/create call of Home Assistant.
HELPER_SPEC: dict[str, dict[str, str]] = {
    "input_boolean": {"icon": "text"},
    "input_button": {"icon": "text"},
    "input_number": {"icon": "text", "min": "number", "max": "number", "step": "number", "initial": "number",
                     "mode": "box|slider", "unit_of_measurement": "text"},
    "input_datetime": {"icon": "text", "has_date": "bool", "has_time": "bool"},
    "input_select": {"icon": "text", "options": "list", "initial": "text"},
    "input_text": {"icon": "text", "min": "number", "max": "number", "initial": "text", "mode": "text|password"},
    "counter": {"icon": "text", "initial": "number", "minimum": "number", "maximum": "number", "step": "number",
                "restore": "bool"},
    "timer": {"icon": "text", "duration": "text", "restore": "bool"},
    # [ADDED v3.53.0] A weekly calendar: on during the spans the user marks. See _clean_schedule.
    "schedule": {"icon": "text", "days": "days", "from": "time", "to": "time"},
}
# [CHANGED v3.73.0] 12 left no room: an alarm clock alone is a time helper and seven day switches.
MAX_NEW_HELPERS = 16


def helper_rules() -> str:
    kinds = "; ".join(f"{d}: {', '.join(f'{k} ({t})' for k, t in f.items())}" for d, f in HELPER_SPEC.items())
    return (f"Helper domains and their settings: {kinds}. input_datetime needs has_time and/or has_date; "
            "input_number needs max above min, and initial between them; schedule days are mon ... sun, "
            "from and to are HH:MM with to after from.")


_WEEK = {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday", "fri": "friday",
         "sat": "saturday", "sun": "sunday"}
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(:00)?$")


def _clean_schedule(given: dict) -> dict:
    """[ADDED v3.53.0] A schedule helper's week as Home Assistant's schedule/create takes it - the same
    shape the panel's Helper tab sends: {"monday": [{"from": "06:00:00", "to": "06:30:00"}], ...}, every day
    present. From the model's {"days", "from", "to"}, or from that shape itself (the plan comes back from
    the browser and is cleaned again). Anything that does not hold leaves the week empty for the user to
    mark - a schedule never runs on days nobody chose."""
    week: dict[str, list] = {day: [] for day in _WEEK.values()}
    if any(day in given for day in week):
        for day in week:
            ranges = given.get(day) if isinstance(given.get(day), list) else []
            for r in ranges[:4]:
                frm, to = (r.get("from"), r.get("to")) if isinstance(r, dict) else (None, None)
                if _HHMM_RE.match(str(frm or "")) and _HHMM_RE.match(str(to or "")) and str(frm)[:5] < str(to)[:5]:
                    week[day].append({"from": f"{str(frm)[:5]}:00", "to": f"{str(to)[:5]}:00"})
            week[day] = sorted(week[day], key=lambda r: r["from"])
            if any(a["to"] > b["from"] for a, b in zip(week[day], week[day][1:], strict=False)):
                week[day] = []
        return week
    frm, to = str(given.get("from") or ""), str(given.get("to") or "")
    days = given.get("days") if isinstance(given.get("days"), list) else []
    if _HHMM_RE.match(frm) and _HHMM_RE.match(to) and frm[:5] < to[:5]:
        for day in days:
            full = _WEEK.get(str(day).strip().lower()[:3])
            if full:
                week[full] = [{"from": f"{frm[:5]}:00", "to": f"{to[:5]}:00"}]
    return week


def clean_new_helpers(raw: Any, roles: list[dict]) -> tuple[list[dict], list[dict]]:
    """[ADDED v3.43.0] The helpers the model proposed, reduced to what Home Assistant's <domain>/create
    accepts: known domains, known settings of the right type, ranges that make sense. Anything else is
    dropped. Each kept helper fills a role; a role it names that the plan lacks is added. Nothing is
    created here - the user creates the ones they keep, with a click in the chat."""
    out, seen = [], set()
    by_id = {r["id"]: r for r in roles}
    for item in (raw if isinstance(raw, list) else [])[:MAX_NEW_HELPERS]:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "")
        spec = HELPER_SPEC.get(domain)
        name = str(item.get("name") or "").strip()[:60]
        rid = _clean_id(item.get("role"), "")
        if not spec or not name or not rid:
            continue
        if rid in seen:
            # [CHANGED v3.50.0] A second helper for the same role used to be dropped without a word, so a
            # plan for "days, a time and an amount" could keep one of them. Each helper fills one role
            # (the chat puts the created entity into it), so the next one gets a role of its own.
            base, n = rid[:36], 2
            while f"{base}_{n}" in seen or f"{base}_{n}" in by_id:
                n += 1
            rid = f"{base}_{n}"
        settings = {}
        given = item.get("settings") if isinstance(item.get("settings"), dict) else {}
        if domain == "schedule":
            settings, spec = _clean_schedule(given), {"icon": "text"}
        for key, kind in spec.items():
            if key not in given:
                continue
            value = given[key]
            if kind == "number":
                try:
                    settings[key] = float(value)
                except (TypeError, ValueError):
                    continue
                if settings[key].is_integer():
                    settings[key] = int(settings[key])
            elif kind == "bool":
                settings[key] = bool(value)
            elif kind == "list":
                opts = [str(v)[:60] for v in value if str(v).strip()][:30] if isinstance(value, list) else []
                if opts:
                    settings[key] = opts
            elif "|" in kind:
                if str(value) in kind.split("|"):
                    settings[key] = str(value)
            else:
                text = str(value).strip()[:100]
                if text:
                    settings[key] = text
        if domain == "input_number":
            lo, hi = settings.get("min", 0), settings.get("max", 100)
            if not hi > lo:
                continue
            # [CHANGED v3.49.0] Home Assistant's input_number/create requires both; the chat shows
            # 0-100 when the model gave none, so that is what is created.
            settings["min"], settings["max"] = lo, hi
            if "initial" in settings and not lo <= settings["initial"] <= hi:
                settings.pop("initial")
        if domain == "input_datetime" and not (settings.get("has_time") or settings.get("has_date")):
            settings["has_time"] = True
        if domain == "input_select":
            # [CHANGED v3.84.0] Save the zone chosen on the card: LIBI gives it the user's zones (zone_choices).
            if not settings.get("options") and not _ZONE_CHOICE_RE.search(rid):
                continue
            if settings.get("initial") not in (settings.get("options") or []):
                settings.pop("initial", None)
        if domain == "counter" and "maximum" in settings and "minimum" in settings \
                and not settings["maximum"] > settings["minimum"]:
            continue
        seen.add(rid)
        out.append({"role": rid, "domain": domain, "name": name, "settings": settings})
        role = by_id.get(rid)
        if role is None:
            role = {"id": rid, "label": name, "purpose": "condition", "domains": [domain],
                    "device_classes": [], "keywords": [], "area_keywords": []}
            roles.append(role)
            by_id[rid] = role
        elif domain not in role["domains"]:
            role["domains"].append(domain)
    return out, roles


_DAY_ORDER = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

# [ADDED v3.51.0] The entity domains a role holds a SETTING in, rather than a device: the helper kinds and the
# number, select, text and time entities of integrations.
SETTING_DOMAINS = set(HELPER_SPEC) | {"number", "select", "text", "time", "date", "datetime"}


def helpers_for_open_roles(plan: dict, candidates: dict, named: dict | None = None) -> None:
    """[ADDED v3.51.0] A role that holds a setting (only setting domains), that no proposed helper fills
    and that found no exact match gets a new helper proposed by LIBI: the user asked to set it from the
    screen and nothing fits. The model forgets some of them; the closest entities it would show instead
    are someone else's settings. Same checks as the model's own proposals, and nothing is created here.
    [CHANGED v3.73.0] named: the helpers the user's message names, per role (roles_for_named_helpers).
    [CHANGED v3.78.0] A helper the message names that is gone is proposed under the user's name for it; a schedule role
    nothing of the user's fills gives way to the alarm clock as a named schedule does (_open_schedule)."""
    if plan.get("intent") == "answer":
        return
    filled = {h["role"] for h in plan["new_helpers"]}
    extra = []
    for role in plan["roles"]:
        domains = role.get("domains") or []
        if role["id"] in filled or not domains or not set(domains) <= SETTING_DOMAINS:
            continue
        if (candidates.get(role["id"]) or {}).get("exact"):
            continue
        domain = next((d for d in domains if d in HELPER_SPEC and d not in ("input_select", "input_button")), "")
        if domain:
            extra.append({"role": role["id"], "domain": domain, "name": role.get("missing") or role["label"],
                          "settings": {}})
    room = MAX_NEW_HELPERS - len(plan["new_helpers"])
    if extra and room > 0:
        kept, plan["roles"] = clean_new_helpers(extra[:room], plan["roles"])
        plan["new_helpers"].extend(kept)
    # [CHANGED v3.73.0] Days and a time set from the screen are an alarm clock (the user's choice, 2026-10-31): a time
    # helper and a switch for every day, set and ticked on the card. v3.53.0 made them one schedule, whose days and
    # hours are changed only in its own settings, never on a card - "it does not let me choose the days of the week
    # and the hours".
    # [CHANGED v3.74.0] A schedule the user names gives way as well when its days and hours are to be chosen on the
    # screen - the model proposed the alarm clock for them, or the request asks for a card. In 3.73.0 it held them and
    # the user got the same card again: "still no way in the UI to choose the days of the week and the start time".
    # [CHANGED v3.76.0] The days are ONE 8-bit helper, ticked as checkboxes on the card - the user: "a variable for each
    # day was not needed" (_days_as_bits).
    schedules = [(rid, eid) for rid, ids in (named or {}).items() for eid in ids if eid.split(".")[0] == "schedule"]
    # [CHANGED v3.78.0] And a schedule role nothing of the user's fills: one the message names that is gone (the user's
    # chat of 2026-11-01, after NET 3 was deleted with its helpers), or one the model planned that found no schedule -
    # LIBI would have proposed a new schedule for it, and a card cannot set one either.
    left = [r["id"] for r in plan["roles"] if _open_schedule(r, candidates, filled, named)]
    if ((schedules and named is not None) or left) and (_alarm_proposed(plan) or _set_on_a_card(plan)):
        _alarm_clock_for(plan, named if named is not None else {}, schedules, left)
    _days_as_bits(plan)


def _open_schedule(role: dict, candidates: dict, filled: set[str], named: dict | None) -> bool:
    """[ADDED v3.78.0] A role for a schedule that nothing of the user's fills: one the user's message names that this Home
    Assistant does not have, or one the model planned whose search found no schedule and for which it proposed none - the
    one LIBI proposes would be a new schedule. A schedule the model proposes stays its own (fixed days in the request)."""
    if set(role.get("domains") or []) != {"schedule"} or role.get("replaced") or role["id"] in (named or {}):
        return False
    return bool(role.get("missing")) or (role["id"] not in filled and not (candidates.get(role["id"]) or {}).get("exact"))


# [ADDED v3.73.0] The role of a day switch, as LIBI and the models name it: day_mon, monday, water_mon.
_DAY_RE = re.compile(r"(?:^|_)(sun|mon|tue|wed|thu|fri|sat)(?:day|sday|nesday|rsday|urday)?$")


def _day_of(role_id: Any) -> str:
    """[ADDED v3.73.0] sun ... sat for the role of a day switch, "" for any other role."""
    m = _DAY_RE.search(str(role_id or ""))
    return m.group(1) if m else ""


def _is_day_switch(helper: dict) -> bool:
    return helper["domain"] == "input_boolean" and bool(_day_of(helper["role"]))


def _is_clock_time(helper: dict) -> bool:
    """[ADDED v3.74.0] A time of day the user sets: an input_datetime with a time and no date."""
    settings = helper.get("settings") or {}
    return helper["domain"] == "input_datetime" and bool(settings.get("has_time")) and not settings.get("has_date")


def _alarm_proposed(plan: dict) -> bool:
    """[ADDED v3.74.0] The plan proposes an alarm clock: a day switch, or the start time.
    [CHANGED v3.75.0] Or has one: the role of a day's switch, as a change of a net with an alarm clock has.
    [CHANGED v3.76.0] Or the days helper, or its role."""
    return any(_is_day_switch(h) or _is_days_bits(h) or (_is_clock_time(h) and h["role"] == "start_time")
               for h in plan["new_helpers"]) or any(_is_day_role(r) or _is_days_role(r) for r in plan["roles"])


# [ADDED v3.76.0] The settings of the days helper: the 8 bits of the days, set from the card's checkboxes.
DAY_BITS_SETTINGS = {"min": 0, "max": 255, "step": 1, "mode": "box"}
# [ADDED v3.76.0] LIBI's own row of a dashboard card: the days of that helper as seven checkboxes ([CHANGED v3.79.0]
# seven round buttons, as on an alarm clock).
DAYS_ROW_TYPE = "custom:libi-days-row"


def _is_days_role(role: dict) -> bool:
    """[ADDED v3.76.0] The role of the days helper: "days" (or "<something>_days"), holding a number."""
    rid = str(role.get("id") or "")
    return (rid == "days" or rid.endswith("_days")) and bool(set(role.get("domains") or []) & set(DAY_BITS_DOMAINS))


def _is_days_bits(helper: dict) -> bool:
    """[ADDED v3.76.0] A proposed days helper: a number in the days role."""
    return helper["domain"] in DAY_BITS_DOMAINS and (helper["role"] == "days" or helper["role"].endswith("_days"))


def _is_day_role(role: dict) -> bool:
    """[ADDED v3.75.0] The role of a day's switch: named for a day (day_mon, monday), holding an input_boolean."""
    return bool(_day_of(role["id"])) and "input_boolean" in (role.get("domains") or [])


def _set_on_a_card(plan: dict) -> bool:
    """[ADDED v3.74.0] The request asks for a card, and for days or a time: what the card has to set."""
    kinds = {line["kind"] for line in plan.get("requirements") or []}
    return "card" in kinds and bool(kinds & {"days", "time"})


def _alarm_clock_for(plan: dict, named: dict, schedules: list[tuple[str, str]], left: list[str] | None = None) -> None:
    """[ADDED v3.74.0] A schedule the user names cannot be set from a dashboard card - its days and hours are changed only
    in its own settings - so the days and the time chosen on the screen are an alarm clock: the start time and the days,
    proposed here when the model did not (named after the plan, for the user to rename). The schedule is no longer
    ticked; its role stays, optional and marked replaced, so the chat says why.
    [CHANGED v3.76.0] The days are the one 8-bit helper (role days), no longer a switch for each day.
    [CHANGED v3.78.0] left: the schedule roles nothing of the user's fills (_open_schedule) - replaced as well, and no
    schedule is proposed for them."""
    gone = set(left or [])
    plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] not in gone]
    base = str(plan.get("name") or "").strip()[:50] or "Watering"
    ids = {r["id"] for r in plan["roles"]}
    extra = []
    if not any(_is_clock_time(h) for h in plan["new_helpers"]) and "start_time" not in ids:
        extra.append({"role": "start_time", "domain": "input_datetime", "name": base,
                      "settings": {"has_time": True, "has_date": False}})
    # Not over the switches or day roles the model planned: _days_as_bits makes them the days helper, where they stood.
    if not any(_is_days_bits(h) or _is_day_switch(h) for h in plan["new_helpers"]) \
            and not any(_is_days_role(r) or _is_day_role(r) for r in plan["roles"]):
        extra.append({"role": "days", "domain": "input_number", "name": f"{base} - days"[:60],
                      "settings": dict(DAY_BITS_SETTINGS)})
    if extra and len(plan["new_helpers"]) + len(extra) <= MAX_NEW_HELPERS and len(plan["roles"]) + len(extra) <= MAX_ROLES:
        kept, plan["roles"] = clean_new_helpers(extra, plan["roles"])
        plan["new_helpers"].extend(kept)
        for role in plan["roles"]:
            if role["id"] == "start_time" and "start_time" not in ids:
                role["purpose"] = "trigger"
    for rid, eid in schedules:
        rest = [e for e in named.get(rid, []) if e != eid]
        if rest:
            named[rid] = rest
        else:
            named.pop(rid, None)
    replaced = {rid for rid, _eid in schedules} | gone
    for role in plan["roles"]:
        if role["id"] in replaced:
            role["optional"], role["replaced"] = True, True


def _days_as_bits(plan: dict) -> None:
    """[ADDED v3.76.0, in place of _complete_days] The days of an alarm clock are ONE 8-bit helper, ticked as checkboxes
    on the card - the user's design (2026-10-31): "a variable for each day was not needed". A switch the model still
    proposes for a day, or a role it plans for one that the user did not name, goes; the days helper takes their place,
    named as the switches were ("<what it is> - days"), else after the plan, for the user to rename. Every days helper
    gets the 8 bits' settings, so all seven days can be ticked, and starts at 0: nothing runs on a day nobody ticked."""
    switches = [h for h in plan["new_helpers"] if _is_day_switch(h)]
    gone = {h["role"] for h in switches} | {r["id"] for r in plan["roles"] if _is_day_role(r) and not r.get("named")}
    if gone:
        first = next((h for d in _DAY_ORDER for h in switches if _day_of(h["role"]) == d), None)
        base, sep, _day = (first["name"] if first else "").rpartition(" - ")
        base = base.strip() if sep and base.strip() else (str(plan.get("name") or "").strip()[:50] or "Days")
        # Where the switches stood in the list - after the time, as the card shows them.
        at = next((i for i, h in enumerate(plan["new_helpers"]) if h["role"] in gone), len(plan["new_helpers"]))
        plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] not in gone]
        plan["roles"] = [r for r in plan["roles"] if r["id"] not in gone]
        if not any(_is_days_role(r) for r in plan["roles"]) and len(plan["new_helpers"]) < MAX_NEW_HELPERS:
            kept, plan["roles"] = clean_new_helpers([{"role": "days", "domain": "input_number", "name": f"{base} - days"[:60],
                                                      "settings": dict(DAY_BITS_SETTINGS)}], plan["roles"])
            plan["new_helpers"][at:at] = kept
    for helper in plan["new_helpers"]:
        if _is_days_bits(helper):
            helper["settings"] = {**{k: v for k, v in helper["settings"].items() if k == "icon"}, **DAY_BITS_SETTINGS}
            helper["days_bits"] = True


def _is_clock_entity(hass: HomeAssistant, entity_id: str) -> bool:
    """[ADDED v3.75.0] An input_datetime that holds a time of day and no date: the time of an alarm clock."""
    state = hass.states.get(entity_id) if str(entity_id).split(".")[0] == "input_datetime" else None
    return state is not None and bool(state.attributes.get("has_time")) and not state.attributes.get("has_date")


@callback
def picked_alarm_clock(hass: HomeAssistant, plan: dict, selections: dict) -> dict:
    """[ADDED v3.75.0] The alarm clock the user picked: its days and the start time, the time of day the user sets - the
    one of the role start_time, else the only one picked. The user's NET 3 of 2026-10-31 had the days of an alarm clock
    and started when the schedule the user had named turned on, so the time set on the card was in no rung, and not
    on the card either.
    [CHANGED v3.76.0] The days are the one 8-bit helper of the days role. {} without it."""
    days = ("", "")
    times: list[tuple[str, str]] = []
    for role in plan.get("roles") or []:
        picks = selections.get(role["id"]) or []
        if _is_days_role(role) and len(picks) == 1 and picks[0].split(".")[0] in DAY_BITS_DOMAINS and not days[1]:
            days = (role["id"], picks[0])
        times += [(role["id"], eid) for eid in picks if _is_clock_entity(hass, eid)]
    if not days[1]:
        return {}
    start = next((t for t in times if t[0] == "start_time"), None) or (times[0] if len(times) == 1 else ("", ""))
    return {"time_role": start[0], "time": start[1], "days_role": days[0], "days": days[1]}


def _yaml_mapping(text: str) -> dict:
    """[ADDED v3.75.0] A net's YAML as LIBI compiles it for the model (canvas_context), read back; {} when it is not
    one mapping."""
    try:
        data = yaml.safe_load(text or "")
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


@callback
def net_alarm_clock(hass: HomeAssistant, config: Any) -> dict:
    """[ADDED v3.75.0] The alarm clock a net has: its days and its time - the input_datetime its time trigger is at, else
    the time of day named as its days are: LIBI names the time "<name>" and the days "<name> - days" (and in 3.73.0 -
    3.75.0 "<name> - Sun" ... "<name> - Sat"), and the user's NET 3 had the days only.
    [CHANGED v3.76.0] days: the 8-bit helper its CMP DAY reads; switches: the switch it checks on each day, as a net of
    3.73.0 - 3.75.0 does. {} when the net has neither."""
    bits = next((e for e in config_day_bits(config) if hass.states.get(e) is not None), "")
    switches: dict[str, str] = {}
    for eid, index in config_days(config).items():
        if hass.states.get(eid) is not None:
            switches.setdefault(_DAY_ORDER[index], eid)
    if not bits and not switches:
        return {}
    time = ""
    for node in _walk_nodes(config):
        at = node.get("at") if node.get("trigger") == "time" else None
        time = time or next((v for v in (at if isinstance(at, list) else [at])
                             if isinstance(v, str) and _is_clock_entity(hass, v)), "")
    base = _base_name(hass, [bits] if bits else list(switches.values()))
    if not time and base:
        time = next((s.entity_id for s in hass.states.async_all("input_datetime")
                     if _norm(s.name) == _norm(base) and _is_clock_entity(hass, s.entity_id)), "")
    return {"time": time, "days": bits, "switches": switches, "base": base}


def _base_name(hass: HomeAssistant, entity_ids: list[str]) -> str:
    """[ADDED v3.76.0] What the names of LIBI's helpers of one alarm clock share: "<name>" of "<name> - days" or of "<name>
    - Sun" ... ; "" when they share nothing so named."""
    bases = set()
    for eid in entity_ids:
        head, sep, _tail = str(hass.states.get(eid).name).rpartition(" - ")
        bases.add(head.strip() if sep else "")
    return bases.pop() if len(bases) == 1 else ""


@callback
def keep_net_alarm_clock(hass: HomeAssistant, plan: dict, net_yaml: str) -> dict[str, list[str]]:
    """[ADDED v3.75.0] A change of a net with an alarm clock keeps that alarm clock: its time in the role start_time - the
    role added when the plan has none - and no helper proposed for it: a proposal of the model for the start time (a
    time of day in a trigger's role) goes, with the role it made for it. The model plans a change from the request,
    which seldom names them, and the chat hid the net's own helpers - the net itself uses them - and offered a second
    alarm clock. Returns the picks to tick.
    [CHANGED v3.76.0] Its days helper likewise, in the role days. A net of 3.73.0 - 3.75.0 checks a switch for each day:
    the change gets the days helper proposed in their place - the user's design, one 8-bit helper - and the switches,
    and any role or proposal for a day's switch, go out of the logic."""
    clock = net_alarm_clock(hass, _yaml_mapping(net_yaml))
    if not clock:
        return {}
    picks: dict[str, list[str]] = {}
    wanted = ([("start_time", clock["time"], "trigger")] if clock["time"] else []) + (
        [("days", clock["days"], "condition")] if clock["days"] else [])
    for rid, eid, purpose in wanted:
        role = next((r for r in plan["roles"] if r["id"] == rid or (rid == "days" and _is_days_role(r))), None)
        domain = eid.split(".")[0]
        if role is None:
            if len(plan["roles"]) >= MAX_ROLES:
                continue
            role = {"id": rid, "label": _sanitize(hass.states.get(eid).name)[:80], "purpose": purpose,
                    "domains": [domain], "device_classes": [], "keywords": [], "area_keywords": []}
            plan["roles"].append(role)
        elif domain not in role["domains"]:
            role["domains"].append(domain)
        picks[role["id"]] = [eid]
    purpose = {r["id"]: r["purpose"] for r in plan["roles"]}
    gone = {h["role"] for h in plan["new_helpers"] if h["role"] not in picks and (
        (clock["time"] and _is_clock_time(h) and (purpose.get(h["role"]) == "trigger" or "start" in h["role"]))
        or (clock["days"] and _is_days_bits(h)) or _is_day_switch(h))}
    gone |= {r["id"] for r in plan["roles"] if _is_day_role(r) and not r.get("named")}
    plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] not in picks and h["role"] not in gone]
    plan["roles"] = [r for r in plan["roles"] if r["id"] not in gone or r.get("named")]
    if clock["switches"] and not clock["days"] and not any(_is_days_role(r) for r in plan["roles"]) \
            and len(plan["new_helpers"]) < MAX_NEW_HELPERS and len(plan["roles"]) < MAX_ROLES:
        base = clock["base"] or str(plan.get("name") or "").strip()[:50] or "Days"
        kept, plan["roles"] = clean_new_helpers([{"role": "days", "domain": "input_number", "name": f"{base} - days"[:60],
                                                  "settings": dict(DAY_BITS_SETTINGS)}], plan["roles"])
        plan["new_helpers"].extend(kept)
    return picks


@callback
def offer_current(hass: HomeAssistant, candidates: dict, picks: dict[str, list[str]]) -> None:
    """[ADDED v3.40.0 in the plan command, here since v3.75.0] A change starts from what the net uses: each pick first in
    its role's list when the search did not find it, marked current, and the list exact - so no helper is proposed for
    that role (helpers_for_open_roles), and drop_used_helpers is told to keep them."""
    for rid, ids in picks.items():
        cand = candidates.setdefault(rid, {"items": [], "exact": True})
        items = cand.setdefault("items", [])
        listed = {i["entity_id"] for i in items}
        for eid in reversed(ids):
            state = hass.states.get(eid)
            if eid not in listed and state is not None:
                items.insert(0, {"entity_id": eid, "name": state.name, "area": "",
                                 "device_class": state.attributes.get("device_class") or "", "state": state.state})
        for item in items:
            if item["entity_id"] in ids:
                item["current"] = True
        cand["exact"] = True


def mentions(entity_id: str, text: str) -> bool:
    """[ADDED v3.77.0] Whether a text names an entity: its entity_id as a whole word, `states.<entity_id>.state` of a
    template too. It tells whether something else uses a helper, so in doubt it says yes."""
    return bool(re.search(rf"(?<!\w){re.escape(entity_id)}(?!\w)", text or ""))


def helper_users(hass: HomeAssistant, entity_id: str, config_text: str) -> list[str]:
    """[ADDED v3.56.0] Who uses a helper: the names of the automations and scripts that reference it, from
    Home Assistant's own index, and - when that index knows none - a mention of its entity_id anywhere in
    automations.yaml or scripts.yaml (a template, which the index does not see)."""
    from homeassistant.components.automation import automations_with_entity  # noqa: PLC0415
    from homeassistant.components.script import scripts_with_entity  # noqa: PLC0415

    users = []
    for eid in automations_with_entity(hass, entity_id) + scripts_with_entity(hass, entity_id):
        state = hass.states.get(eid)
        users.append(_sanitize(state.name if state else eid)[:60])
    if not users and mentions(entity_id, config_text):
        users.append("a template in automations.yaml or scripts.yaml")
    return users


def drop_used_helpers(hass: HomeAssistant, candidates: dict, config_text: str, keep: set[str] | None = None) -> None:
    """[ADDED v3.56.0] A setting role offers only settings nothing else uses: picking a helper another
    automation reads would let the new card change that automation too. Devices are not filtered - a valve
    is meant to be switched by more than one automation. How many were left out is told to the user.
    [CHANGED v3.75.0] keep: what a change of a net starts from - the net's own helpers, which only the net itself may use
    (net_entities), and its picks (offer_current)."""
    keep = keep or set()
    for cand in candidates.values():
        kept, hidden = [], 0
        for item in cand.get("items") or []:
            # [ADDED v3.60.0] Not a helper the user named: "use my helper X" is the user's own choice, and the
            # chat says who else uses it (roles_for_named_helpers).
            eid = item["entity_id"]
            if not item.get("named") and eid not in keep and eid.split(".")[0] in SETTING_DOMAINS \
                    and helper_users(hass, eid, config_text):
                hidden += 1
            else:
                kept.append(item)
        if hidden:
            cand["items"], cand["hidden_used"] = kept, hidden
            if not kept:
                cand["exact"] = False


def dedupe_new_helpers(hass: HomeAssistant, plan: dict, candidates: dict, config_text: str) -> None:
    """[ADDED v3.56.0] A proposed helper whose kind and name already exist is not created a second time. If
    the existing one is unused (for example made in an earlier chat whose logic was never built), it is
    offered first in its role, marked "exists", and the proposal goes. If something uses it, the new one
    gets a name of its own, so the two cannot be mistaken for each other."""
    existing: dict[tuple[str, str], str] = {}
    for state in hass.states.async_all(list(HELPER_SPEC)):
        existing.setdefault((state.domain, _norm(state.name)), state.entity_id)
    kept = []
    for helper in plan["new_helpers"]:
        eid = existing.get((helper["domain"], _norm(helper["name"])))
        if eid is None:
            kept.append(helper)
            continue
        if not helper_users(hass, eid, config_text):
            state = hass.states.get(eid)
            cand = candidates.setdefault(helper["role"], {"items": [], "exact": True})
            cand["items"] = [i for i in cand["items"] if i["entity_id"] != eid]
            cand["items"].insert(0, {"entity_id": eid, "name": state.name, "area": "", "device_class": "",
                                     "state": state.state, "exists": True})
            cand["exact"] = True
            continue
        base, n = helper["name"][:54], 2
        while (helper["domain"], _norm(f"{base} ({n})")) in existing:
            n += 1
        helper["name"] = f"{base} ({n})"
        kept.append(helper)
    plan["new_helpers"] = kept


# [ADDED v3.82.0] The local variables of a NET in one place - the user (2026-11-02): "all the local variables should be at
# the start in the same window, always with the option to create all of them new; and if there is a free variable, choose
# it instead of creating a new one". In 3.81 a setting was a list to pick from where a helper of the user's fitted, and a
# helper to create where none did - and the on/off switch was both at once.
_CREATABLE_DOMAINS = ("input_number", "input_datetime", "input_boolean", "input_text", "input_select", "counter", "timer",
                      "schedule")


@callback
def _unique_name(hass: HomeAssistant, domain: str, name: str) -> str:
    """[ADDED v3.82.0] A name no helper of the domain has yet: the name itself, else "<name> (2)", "<name> (3)" ..."""
    taken = {_norm(s.name) for s in hass.states.async_all(domain)}
    base, out, n = str(name).strip()[:54], str(name).strip()[:60], 2
    while _norm(out) in taken:
        out, n = f"{base} ({n})", n + 1
    return out


def _fitting(role: dict, cand: dict, preselect: dict, taken: set[str]) -> str:
    """[ADDED v3.82.0] The helper of the user's a variable starts with: the one ticked for it (a change of a NET, a helper
    the message names), else one that exists under the name proposed for it, one the net being changed uses or one made
    in this chat, else the best of the exact matches - never one another variable starts with, nor one of the closest only.
    A helper listed is free: drop_used_helpers left out the ones something else uses, save those the user named."""
    items = [i for i in cand.get("items") or [] if i["entity_id"] not in taken]
    ids = {i["entity_id"] for i in items}
    for eid in preselect.get(role["id"]) or []:
        if eid in ids:
            return eid
    for item in items:
        if item.get("named") or item.get("exists") or item.get("current") or item.get("created"):
            return item["entity_id"]
    return items[0]["entity_id"] if items and cand.get("exact") else ""


@callback
def local_variables(hass: HomeAssistant, plan: dict, candidates: dict, preselect: dict) -> None:
    """[ADDED v3.82.0] Every setting the logic reads is a local variable of the NET (role "variable"), and each one can be
    made new. Where a free helper of the user's fits, it is the one the chat starts with ("pick"), and the helper LIBI would
    make in its place - set up like that one, under a name of its own - is its alternative (plan["alternatives"]); where
    none fits, the helper to create is in new_helpers, as before. A schedule that gave way is a variable that is not used.
    Nothing is created here."""
    if plan.get("intent") == "answer":
        return
    # [ADDED v3.84.0] The zone chosen on the card: only a dropdown of the user's zones fits, and a free one is chosen
    # instead of a new one.
    zones = set(zone_states(hass))
    for role in plan["roles"]:
        if role.get("zone_choice"):
            cand = candidates.setdefault(role["id"], {"items": [], "exact": False})
            cand["items"] = [i for i in cand.get("items") or [] if _lists_zones(hass.states.get(i["entity_id"]), zones)]
            cand["exact"] = bool(cand["items"])
            if cand["items"]:
                plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] != role["id"]]
    proposed = {h["role"] for h in plan["new_helpers"]}
    taken: set[str] = set()
    alternatives: list[dict] = []
    for role in list(plan["roles"]):
        domains = role.get("domains") or []
        # A role a helper is proposed for is a variable too, whatever else it may hold.
        if not domains or not (set(domains) <= SETTING_DOMAINS or role["id"] in proposed):
            continue
        role["variable"] = True
        if role.get("replaced") or role["id"] in proposed:
            continue
        pick = _fitting(role, candidates.get(role["id"]) or {}, preselect, taken)
        domain = next((d for d in domains if d in _CREATABLE_DOMAINS), "")
        if not domain:
            continue
        like = hass.states.get(pick) if pick else None
        settings = {k: v for k, v in (like.attributes if like else {}).items() if k in HELPER_SPEC[domain]}
        if role.get("zone_choice"):
            settings = zone_choice_settings(hass, settings.get("icon"))
        name = like.name if like else (role.get("missing") or role["label"])
        kept, plan["roles"] = clean_new_helpers([{"role": role["id"], "domain": domain, "settings": settings,
                                                  "name": _unique_name(hass, domain, name)}], plan["roles"])
        if not kept:
            continue
        helper = kept[0]
        if _is_days_role(role) and helper["domain"] in DAY_BITS_DOMAINS:
            helper["settings"] = {**{k: v for k, v in helper["settings"].items() if k == "icon"}, **DAY_BITS_SETTINGS}
            helper["days_bits"] = True
        if pick:
            taken.add(pick)
            alternatives.append({**helper, "pick": pick})
        elif len(plan["new_helpers"]) < MAX_NEW_HELPERS:
            plan["new_helpers"].append(helper)
    plan["alternatives"] = alternatives[:MAX_NEW_HELPERS]


# [ADDED v3.60.0] The quote marks a one-word helper name has to stand between to count as named: ASCII and
# typographic quotes, guillemets, and the gershayim and geresh of Hebrew script.
_QUOTES = "\"'`\u2018\u2019\u201c\u201d\u201e\u00ab\u00bb\u05f3\u05f4"
MAX_NAMED_HELPERS = 8


@callback
def helpers_named(hass: HomeAssistant, request: str) -> list[str]:
    """[ADDED v3.60.0] The helpers the user's own text names by their whole name ("I already have a helper
    Garden schedule, use it"), in the order named. A name of one word counts only between quotes, so a test
    in a sentence is not the helper called test; where one name holds another, the longer one is meant. Before
    the name may stand a letter of another alphabet (a one-letter prefix of the user's language), not a Latin
    letter or a digit. Read from the user's words and this Home Assistant's helpers, never from the model."""
    text = _norm(request)
    if not text:
        return []
    quote = re.escape(_QUOTES)
    hits = []
    for state in hass.states.async_all(list(HELPER_DOMAINS)):
        name = _norm(state.name)
        if len(name) < 3:
            continue
        if " " in name:
            pattern = rf"(?<![a-z0-9]){re.escape(name)}(?!\w)"
        else:
            pattern = rf"(?<=[{quote}]){re.escape(name)}(?=[{quote}])"
        hits += [(m.start(), m.end(), state.entity_id) for m in re.finditer(pattern, text)]
    first: dict[str, int] = {}
    for start, end, eid in hits:
        inside = any(s <= start and end <= e and e - s > end - start for s, e, _x in hits)
        if not inside and start < first.get(eid, len(text)):
            first[eid] = start
    return sorted(first, key=lambda eid: first[eid])[:MAX_NAMED_HELPERS]


def _offer_named(cand: dict, state: Any, users: list[str]) -> None:
    """[ADDED v3.60.0] A helper the user named, first in a role's list and tagged; with who else uses it."""
    items = cand.get("items") or []
    item = next((i for i in items if i["entity_id"] == state.entity_id), None) or {
        "entity_id": state.entity_id, "name": state.name, "area": "", "device_class": "", "state": state.state}
    item["named"] = True
    if users:
        item["used_by"] = users[:3]
    cand["items"] = [item] + [i for i in items if i["entity_id"] != state.entity_id]


def roles_for_named_helpers(hass: HomeAssistant, plan: dict, named: list[str], candidates: dict,
                            config_text: str) -> dict[str, list[str]]:
    """[ADDED v3.60.0] Every helper the user's message names is offered and ticked. In the user's test the
    model planned the valve, the meter and the weather only, although the message said which schedule and
    which litres helper to use, so neither could be picked. The helper goes into the role meant for it: the
    one whose proposed new helper has its very name (that one is then not created), else the one whose
    search found it best - a match of the role's own words before a role that found nothing better. When two
    roles found it equally, it is offered first in both and ticked in neither: the user picks. With no role
    for it, it gets an optional role of its own. A role the user's helper fills gets no new helper. Returns
    the picks to tick. Nothing here comes from the model; the names were matched in the user's own text."""
    if plan.get("intent") == "answer" or not named:
        return {}
    picks: dict[str, list[str]] = {}
    ids = {r["id"] for r in plan["roles"]}
    for eid in named:
        state = hass.states.get(eid)
        if state is None:
            continue
        domain = eid.split(".")[0]
        users = helper_users(hass, eid, config_text)
        proposed = {h["role"] for h in plan["new_helpers"]}
        same = next((h for h in plan["new_helpers"]
                     if h["domain"] == domain and _norm(h["name"]) == _norm(state.name)), None)
        rid = same["role"] if same else ""
        if not rid:
            found = []
            for role in plan["roles"]:
                cand = candidates.get(role["id"]) or {}
                pos = next((i for i, it in enumerate(cand.get("items") or []) if it["entity_id"] == eid), None)
                # A role holding a proposal is meant for a new helper unless its own words found this one.
                if pos is None or role["id"] in picks or (role["id"] in proposed and not cand.get("exact")):
                    continue
                found.append((0 if cand.get("exact") else 1, pos, role["id"]))
            found.sort()
            if len(found) > 1 and found[0][:2] == found[1][:2]:
                for tier, pos, other in found:
                    if (tier, pos) == found[0][:2]:
                        _offer_named(candidates[other], state, users)
                continue
            rid = found[0][2] if found else ""
        if not rid:
            if len(plan["roles"]) >= MAX_ROLES:
                continue
            rid = _clean_id(f"{domain}_{eid.split('.', 1)[1]}", domain)[:40]
            while rid in ids:
                rid = rid[:37] + "_x"
            plan["roles"].append({"id": rid, "label": _sanitize(state.name)[:80] or eid,
                                  "purpose": "trigger" if domain in ("schedule", "input_button") else "condition",
                                  "domains": [domain], "device_classes": [], "keywords": [], "area_keywords": [],
                                  "optional": True, "named": True})
            ids.add(rid)
        cand = candidates.setdefault(rid, {"items": [], "exact": True})
        _offer_named(cand, state, users)
        cand["exact"] = True
        plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] != rid]
        picks.setdefault(rid, []).append(eid)
    return picks


# [ADDED v3.78.0] A text between double quotes on one line of the user's text: ASCII and typographic quotes,
# guillemets, and the gershayim of Hebrew script. Every pair is taken, short or long, so the next pair is read as the
# user wrote it, and only then is the text weighed as a name.
_QUOTED_RE = re.compile("[\"\u201c\u201e\u00ab\u05f4]([^\"\u201c\u201d\u201e\u00ab\u00bb\u05f4\n]*)[\"\u201c\u201d\u00bb\u05f4]")


@callback
def helpers_missing(hass: HomeAssistant, request: str) -> list[str]:
    """[ADDED v3.78.0] The names the user's text puts between double quotes that nothing in this Home Assistant has, as
    written and in the order named. In the user's chat of 2026-11-01 the request still said "I already have a helper
    "<name>", use it" of two helpers deleted with NET 3, so neither could be found (helpers_named). Read from the user's
    words and this Home Assistant's entities, never from the model; what a name is for, the role that holds it says
    (roles_for_missing_helpers)."""
    known: set[str] = set()
    for state in hass.states.async_all():
        known.update((_norm(state.name), _norm(state.entity_id), _norm(state.object_id)))
    out: list[str] = []
    for match in _QUOTED_RE.finditer(request or ""):
        name = " ".join(match.group(1).split()).strip(" .,;:!?")
        key = _norm(name)
        if len(key) >= 3 and len(name) <= 60 and key not in known and all(_norm(n) != key for n in out):
            out.append(name)
    return out[:MAX_NAMED_HELPERS]


def missing_context(names: list[str]) -> str:
    """[ADDED v3.78.0] The model is told the names the user's message quotes that nothing in this Home Assistant has."""
    lines = [f'- "{name}"' for name in names]
    return ("NAMED, NOT FOUND (nothing in this Home Assistant has these names):\n" + "\n".join(lines)) if lines else ""


def _holds_name(role: dict, key: str) -> bool:
    """[ADDED v3.78.0] Whether a role's label or one of its keywords holds a name, as whole words."""
    pattern = rf"(?<!\w){re.escape(key)}(?!\w)"
    return any(re.search(pattern, _norm(text)) for text in [role.get("label") or "", *(role.get("keywords") or [])])


def roles_for_missing_helpers(plan: dict, missing: list[str], candidates: dict, taken: set[str]) -> None:
    """[ADDED v3.78.0] A helper the user's message names that this Home Assistant does not have is proposed again, under
    that very name. The setting role whose label or words hold the name is marked missing - the chat says so - and what
    its search found is no match: found by the words of the name or of its kind, it is not the user's helper, so
    helpers_for_open_roles proposes it. The model's proposal for that role takes the user's name; one it made under that
    name in a role of its own is that helper, and a second role for it goes. taken: the roles already filled with the
    user's own helpers (a named one, or one a changed net uses). The names are the user's words, never the model's."""
    if plan.get("intent") == "answer":
        return
    for name in missing:
        key = _norm(name)
        holders = [r for r in plan["roles"] if r["id"] not in taken and not r.get("missing") and r.get("domains")
                   and set(r["domains"]) <= SETTING_DOMAINS and _holds_name(r, key)]
        proposal = next((h for h in plan["new_helpers"] if _norm(h["name"]) == key and h["role"] not in taken), None)
        if proposal is not None:
            twins = {r["id"] for r in holders if r["id"] != proposal["role"]}
            plan["roles"] = [r for r in plan["roles"] if r["id"] not in twins]
            for rid in twins:
                candidates.pop(rid, None)
            holders = [r for r in plan["roles"] if r["id"] == proposal["role"]]
        if not holders:
            continue
        role = next((r for r in holders if _norm(r["label"]) == key), holders[0])
        role["missing"] = name
        candidates.setdefault(role["id"], {"items": []})["exact"] = False
        for helper in plan["new_helpers"]:
            if helper["role"] == role["id"]:
                helper["name"] = name[:60]


# [CHANGED v3.59.0] The word NET as the canvas shows it, also right after a letter of another alphabet
# (a one-letter prefix of the user's language); after a Latin letter or a digit it is part of another word
# (INTERNET 3).
_NET_REF_RE = re.compile(r"(?<![A-Za-z0-9_])NET\s*-?\s*(\d{1,3})(?!\d)", re.IGNORECASE)


def nets_named(request: str, nets: Any) -> list[str]:
    """[ADDED v3.59.0] The ids of the nets the user's own text names by number - NET 3 is the third net on
    the page, as the canvas numbers them - in the order named. Read from the user's words, never from
    the model."""
    if not isinstance(nets, list):
        return []
    out: list[str] = []
    for number in _NET_REF_RE.findall(request or ""):
        index = int(number) - 1
        if 0 <= index < len(nets) and isinstance(nets[index], dict):
            nid = str(nets[index].get("id") or "")[:40]
            if nid and nid not in out:
                out.append(nid)
    return out


def only_named_changes(plan: dict, request: str, nets: Any) -> None:
    """[ADDED v3.59.0] The user's rule: an existing net is changed only when the request names it by its
    number ("update NET 3"); every other request is new logic, which the chat adds as a new net after the
    last one. The model only proposes; this decides, from the user's own words. When the request names one
    net, that is the net changed, whichever the model picked. forced_new tells the chat why it is new."""
    if plan.get("intent") != "modify":
        return
    named = nets_named(request, nets)
    if plan.get("target_net") in named:
        return
    if len(named) == 1:
        plan["target_net"] = named[0]
        return
    plan["intent"], plan["target_net"], plan["forced_new"] = "create", "", True


def roles_for_named_nets(hass: HomeAssistant, plan: dict, request: str, nets: Any, by_id: dict[str, str],
                         candidates: dict, on_canvas: dict[str, str]) -> None:
    """[ADDED v3.54.0] "Use the devices of NET 1": every entity that net uses which no role offers becomes
    an OPTIONAL role of its own, so the water meter of NET 1 can be picked even when the model forgot to ask
    for it. Read from the user's own text and the nets on the page, never from the model. Optional: nothing
    has to be picked, and the build leaves an unpicked one out."""
    if plan.get("intent") != "create" or not isinstance(nets, list):
        return
    wanted = {int(n) for n in _NET_REF_RE.findall(request or "")}
    offered = {i["entity_id"] for c in candidates.values() for i in (c.get("items") or [])}
    ids = {r["id"] for r in plan["roles"]}
    for index, net in enumerate(nets):
        if index + 1 not in wanted or not isinstance(net, dict):
            continue
        text = by_id.get(str(net.get("id") or "")[:40], "")
        for m in _ENTITY_RE.finditer(text):
            eid = m.group(0)
            state = hass.states.get(eid)
            if state is None or eid in offered or eid.split(".")[0] in SETTING_DOMAINS or len(plan["roles"]) >= MAX_ROLES:
                continue
            rid = _clean_id(f"net{index + 1}_{eid.split('.', 1)[1]}", f"net{index + 1}")[:40]
            while rid in ids:
                rid = rid[:37] + "_x"
            domain = eid.split(".")[0]
            role = {"id": rid, "label": _sanitize(state.name)[:80] or eid, "domains": [domain],
                    "purpose": "measure" if domain in ("sensor", "binary_sensor") else "target",
                    "device_classes": [], "keywords": [], "area_keywords": [], "optional": True}
            plan["roles"].append(role)
            ids.add(rid)
            offered.add(eid)
            candidates[rid] = find_candidates(hass, role, on_canvas)


def validator_rules() -> str:
    """[ADDED v3.41.0] The rules the model is told, made from the very lists the validator checks, so
    the prompt can never allow what LIBI rejects or keep quiet about what it accepts."""
    restricted = "; ".join(f"{d}: only {', '.join(sorted(v))}" for d, v in sorted(RESTRICTED.items()))
    return "\n".join([
        "HOME ASSISTANT SYNTAX (current, 2024.10 and later):",
        "- Plural top-level keys: triggers, conditions, actions (a script: sequence).",
        "- A trigger is {\"trigger\": <type>, ...} - never \"platform\". A service call is",
        "  {\"action\": \"<domain>.<service>\", \"target\": {\"entity_id\": ...}, \"data\": {...}} - never",
        "  \"service\", \"service_data\" or \"data_template\".",
        "- Times are strings \"HH:MM:SS\" (\"05:00:00\"). Durations are {\"hours\": h, \"minutes\": m,",
        "  \"seconds\": s} or \"HH:MM:SS\"; from a helper {\"minutes\": \"{{ states('role:x') | int(0) }}\"}.",
        "  Weekdays: mon tue wed thu fri sat sun.",
        "- numeric_state needs above and/or below: a number, or a role holding one input_number, number or",
        "  sensor (\"above\": \"role:x\") - never a template. State values are strings: \"on\", \"off\", \"home\".",
        "- A condition is a dict with \"condition\": <type>; and / or / not take \"conditions\": [...].",
        "- Templates are Jinja: {{ states('role:x') }}, {{ is_state('role:x', 'on') }}, {{ now() }}.",
        "  Use | float(0) or | int(0) before comparing numbers. A role inside a template must hold one entity.",
        "- mode: single (ignore new runs while running), restart, queued or parallel.",
        "- How each trigger is written: time {\"trigger\": \"time\", \"at\": \"05:00:00\"};",
        "  time_pattern {\"trigger\": \"time_pattern\", \"minutes\": \"/5\"}; sun {\"trigger\": \"sun\",",
        "  \"event\": \"sunset\", \"offset\": \"-00:30:00\"}; state {\"trigger\": \"state\", \"entity_id\": ..., \"to\": \"on\",",
        "  \"for\": {\"minutes\": 2}}; numeric_state {..., \"above\": 25}; zone {\"trigger\": \"zone\", \"entity_id\": <person>,",
        "  \"zone\": <zone>, \"event\": \"enter\"}; template {\"trigger\": \"template\", \"value_template\": \"{{ ... }}\"}.",
        "- A state CONDITION uses \"state\": \"on\" (not \"to\"). A time condition: \"after\", \"before\", \"weekday\".",
        "- Give a trigger an \"id\" only when a {\"condition\": \"trigger\", \"id\": ...} refers to it.",
        "- No !secret, !include, !input or any other YAML tag. No device triggers, conditions or actions.",
        "",
        "WHAT LIBI ACCEPTS (anything else and the draft is rejected):",
        f"- Trigger types: {', '.join(sorted(TRIGGERS))}.",
        f"- Condition types: {', '.join(sorted(CONDITIONS))}.",
        "- Services on devices: any existing service of these domains, acting only on entities of the same",
        f"  domain: {', '.join(sorted(ENTITY_SERVICE_DOMAINS))}.",
        f"  Restricted domains: {restricted}. To run a script: script.turn_on with the script as target.",
        f"- Services that act on any device: {', '.join(sorted(GENERIC_SERVICES))}.",
        f"- Messages: {', '.join(d + '.*' for d in sorted(MESSAGE_DOMAINS))} and {', '.join(sorted(MESSAGE_SERVICES))}.",
        f"- Read-only services (with response_variable): {', '.join(sorted(READ_SERVICES))}.",
        "- Every service that acts on devices has target.entity_id with role references; never \"all\".",
        f"- Never write these keys: {', '.join(sorted(FORBIDDEN_KEYS))} (inside \"data\" they are allowed).",
        # platform and service are accepted so old automations load, but the model must not write them.
        f"- Allowed keys outside data and variables: {', '.join(sorted(KNOWN_KEYS - LEGACY_KEYS))}.",
        "- Building blocks: delay, choose/default, if/then/else, repeat (count, while, until, for_each), parallel,",
        "  sequence, variables, an inline condition step, continue_on_error. wait_template, wait_for_trigger and stop",
        "  are accepted as well, but the ladder way below never needs them.",
    ])


BUILD_SYSTEM = BUILD_SYSTEM_TEMPLATE.replace("{RULES}", validator_rules()).replace(
    "{DAY_BITS}", day_bits_template("role:days"))
PLAN_SYSTEM = PLAN_SYSTEM_TEMPLATE.replace("{HELPER_RULES}", helper_rules())

_ROLE_RE = re.compile(r"role:([a-z0-9_]+)")
_ENTITY_RE = re.compile(r"(?<![\w.])([a-z_][a-z0-9_]*)\.([a-z0-9_]+)(?![\w(])")
# [ADDED v3.62.0] A template that only reads one entity's state, maybe as a number: "{{ states('x.y') | float(0) }}".
_THRESHOLD_RE = re.compile(r"^\{\{\s*(?:states\(\s*['\"]([a-z_]+\.[a-z0-9_]+)['\"]\s*\)|states\.([a-z_]+\.[a-z0-9_]+)\.state)"
                           r"\s*(?:\|\s*(?:float|int)(?:\(\s*-?[0-9.]*\s*\))?\s*)?\}\}$")
THRESHOLD_DOMAINS = ("input_number", "number", "sensor")


def _threshold(value: str) -> str:
    """[ADDED v3.62.0] numeric_state takes above and below as a number or as the entity_id of an input_number,
    number or sensor, never as a template. A template that only reads such an entity's state is that entity."""
    m = _THRESHOLD_RE.match(value.strip())
    eid = (m.group(1) or m.group(2)) if m else ""
    return eid if eid.split(".")[0] in THRESHOLD_DOMAINS else value


class _Draft:
    """Walks the model's config, substitutes the user's picks and collects every problem."""

    def __init__(self, hass: HomeAssistant, selections: dict[str, list[str]]):
        self.hass = hass
        self.sel = selections
        self.allowed = {e for ids in selections.values() for e in ids}
        self.domains_here = present_domains(hass)
        self.errors: list[str] = []
        self.used: set[str] = set()
        self.services: set[str] = set()

    def err(self, msg: str) -> None:
        if msg not in self.errors:
            self.errors.append(msg)

    # -- strings
    def _expand(self, value: str) -> list[str]:
        m = _ROLE_RE.fullmatch(value.strip())
        if m:
            ids = self.sel.get(m.group(1))
            if not ids:
                self.err(f"The draft refers to '{m.group(1)}', which has no entity picked.")
                return []
            return list(ids)
        return [value]

    def _text(self, value: str) -> str:
        """A string that is not an entity list: one-entity roles may be used inside it."""
        def sub(m):
            ids = self.sel.get(m.group(1)) or []
            if len(ids) != 1:
                self.err(f"'{m.group(1)}' is used inside a text or template, so it needs exactly one entity.")
                return m.group(0)
            return ids[0]
        out = _ROLE_RE.sub(sub, value)
        for m in _ENTITY_RE.finditer(out):
            if m.group(1) in self.domains_here:
                self._check_entity(m.group(0))
        return out

    def _check_entity(self, eid: str) -> None:
        if eid not in self.allowed:
            self.err(f"The draft names {eid}, which you did not pick. It was not used.")
        else:
            self.used.add(eid)

    def entity_list(self, value: Any) -> list[str]:
        items = value if isinstance(value, list) else [value]
        out = []
        for item in items:
            if not isinstance(item, str):
                self.err("An entity reference is not text.")
                continue
            for eid in self._expand(item):
                if eid.strip().lower() in ("all", "none"):
                    self.err("'all' is not allowed as a target. Pick the entities instead.")
                    continue
                self._check_entity(eid)
                out.append(eid)
        return out

    # -- structure
    def walk(self, node: Any, key: str = "", free: bool = False) -> Any:
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                k = str(k)
                if not free:
                    if k in FORBIDDEN_KEYS:
                        self.err(f"'{k}' is not allowed in an AI draft; devices are picked by you.")
                        continue
                    if k not in KNOWN_KEYS:
                        self.err(f"'{k}' is not something LIBI lets the AI write.")
                        continue
                if k in ("entity_id", "media_player_entity_id"):
                    ids = self.entity_list(v)
                    out[k] = ids[0] if len(ids) == 1 else ids
                elif k in ("action", "service") and isinstance(v, str) and not free:
                    out[k] = self.service(v, node)
                elif k in ("trigger", "platform") and not free and key in ("triggers", "trigger", "wait_for_trigger"):
                    if v not in TRIGGERS:
                        self.err(f"The trigger type '{v}' is not allowed.")
                    out[k] = v
                elif k == "condition" and isinstance(v, str) and not free:
                    if v not in CONDITIONS:
                        self.err(f"The condition type '{v}' is not allowed.")
                    out[k] = v
                else:
                    out[k] = self.walk(v, k, free or k in FREE_KEYS)
                    # [ADDED v3.62.0] A threshold written as a template of one entity's state is that entity, which
                    # is how Home Assistant takes it: a template there was rejected ("expected float at 'above'").
                    if k in ("above", "below") and not free and isinstance(out[k], str):
                        out[k] = _threshold(out[k])
            return out
        if isinstance(node, list):
            return [self.walk(v, key, free) for v in node]
        if isinstance(node, str):
            return self._text(node)
        return node

    def service(self, value: str, step: dict) -> str:
        value = value.strip()
        if "." not in value:
            self.err(f"'{value}' is not a service.")
            return value
        domain, name = value.split(".", 1)
        if not self.hass.services.has_service(domain, name):
            self.err(f"The service {value} does not exist in this Home Assistant.")
            return value
        self.services.add(value)
        if domain in MESSAGE_DOMAINS or value in MESSAGE_SERVICES:
            return value
        if value in GENERIC_SERVICES:
            if not _targets(step):
                self.err(f"{value} needs a target.")
            return value
        if value not in READ_SERVICES and (
                domain not in ENTITY_SERVICE_DOMAINS or (domain in RESTRICTED and name not in RESTRICTED[domain])):
            self.err(f"The service {value} is not allowed in an AI draft.")
            return value
        targets = _targets(step)
        if not targets:
            self.err(f"{value} must name the entities it acts on.")
        for t in targets:
            for eid in (self._expand(t) if isinstance(t, str) else []):
                if eid.split(".")[0] != domain:
                    self.err(f"{value} cannot act on {eid}, which is not a {domain}.")
        return value


def _targets(step: dict) -> list:
    target = step.get("target") if isinstance(step.get("target"), dict) else {}
    found = target.get("entity_id", step.get("entity_id"))
    if found is None and isinstance(step.get("data"), dict):
        found = step["data"].get("entity_id")
    if found is None:
        return []
    return found if isinstance(found, list) else [found]


@callback
def clean_selections(hass: HomeAssistant, plan: dict, raw: Any) -> tuple[dict, list[str]]:
    """The user's picks, kept only when the entity exists and fits the role's domains."""
    errors: list[str] = []
    roles = {r["id"]: r for r in plan.get("roles") or []}
    out: dict[str, list[str]] = {}
    for rid, ids in (raw or {}).items() if isinstance(raw, dict) else []:
        role = roles.get(rid)
        if role is None or not isinstance(ids, list):
            continue
        keep = []
        for eid in ids[:100]:
            eid = str(eid)
            if hass.states.get(eid) is None:
                errors.append(f"{eid} does not exist.")
            elif eid.split(".")[0] not in role["domains"]:
                errors.append(f"{eid} does not fit '{role['label']}'.")
            else:
                keep.append(eid)
        if keep:
            out[rid] = keep
    for rid, role in roles.items():
        if rid not in out and not role.get("optional"):
            errors.append(f"Pick at least one entity for '{role['label']}'.")
    return out, errors


# [ADDED v3.62.0] A message service as the user writes it: notify.mobile_app_phone.
_MESSAGE_SERVICE_RE = re.compile(rf"(?<![\w.])({'|'.join(sorted(MESSAGE_DOMAINS))})\.([a-z0-9_]+)(?![\w(])")


@callback
def services_named(hass: HomeAssistant, texts: list[str]) -> tuple[list[str], list[str]]:
    """[ADDED v3.62.0] The message services the user's own words name: the ones this Home Assistant has, and the
    ones it does not. In the user's test the second phone was no longer in the Companion app, so every draft
    that sent to it was rejected. A notify entity the user names is neither: a role holds it."""
    found: list[str] = []
    missing: list[str] = []
    for text in texts:
        for m in _MESSAGE_SERVICE_RE.finditer(str(text or "").lower()):
            name = m.group(0)
            if name in found or name in missing or hass.states.get(name) is not None:
                continue
            (found if hass.services.has_service(m.group(1), m.group(2)) else missing).append(name)
    return found[:12], missing[:12]


# [ADDED v3.64.0] The role LIBI makes for the phones a message goes to (phones_role).
PHONES_ROLE = "phones_to_notify"


@callback
def phone_services(hass: HomeAssistant) -> dict[str, str]:
    """[ADDED v3.64.0] Each phone's notify entity with the notify service of the same phone. The Companion app
    registers both from the device name of its config entry: notify.<phone> and notify.mobile_app_<phone>."""
    ent_reg = er.async_get(hass)
    out: dict[str, str] = {}
    for state in hass.states.async_all("notify"):
        entry = ent_reg.async_get(state.entity_id)
        if entry is None or entry.platform != "mobile_app" or not entry.config_entry_id:
            continue
        config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
        name = str((config_entry.data if config_entry else {}).get("device_name") or "")
        service = slugify(f"mobile_app_{name}") if name else ""
        if service and hass.services.has_service("notify", service):
            out[state.entity_id] = f"notify.{service}"
    return out


@callback
def phone_owners(hass: HomeAssistant) -> dict[str, dict[str, str]]:
    """[ADDED v3.66.0] Whose each phone is and what it is, for the list the user picks from: the person whose user
    registered the Companion app on it, and the maker and model the app reported ("Guy", "samsung SM-N985F"). Read
    from the app's config entry - never its webhook or secret - and shown to the user only: the model never gets it."""
    people = {s.attributes.get("user_id"): s.name for s in hass.states.async_all("person") if s.attributes.get("user_id")}
    ent_reg = er.async_get(hass)
    out: dict[str, dict[str, str]] = {}
    for state in hass.states.async_all("notify"):
        entry = ent_reg.async_get(state.entity_id)
        if entry is None or entry.platform != "mobile_app" or not entry.config_entry_id:
            continue
        config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
        data = config_entry.data if config_entry else {}
        device = " ".join(str(data.get(key) or "").strip() for key in ("manufacturer", "model")).strip()
        out[state.entity_id] = {"owner": _sanitize(people.get(data.get("user_id"), ""))[:40],
                                "device": _sanitize(device)[:60]}
    return out


@callback
def phones_role(hass: HomeAssistant, plan: dict, found: list[str], candidates: dict) -> list[str] | None:
    """[ADDED v3.64.0] The user's message names notify services ("send it to notify.mobile_app_x and ..."): LIBI
    offers the phones itself, the same list every run - in the user's tests the model planned two phone roles in
    one run and none in the next, the same request. The phones the user named are ticked, and another phone can
    take the place of one that no longer exists. The model's own phone roles go. Returns the phones to tick, or
    None when there is no notify entity to offer (then the services named are used as written)."""
    if plan.get("intent") == "answer":
        return None
    services = phone_services(hass)
    # [CHANGED v3.65.0] Only phones with a notify service of their own: the message goes to each by that service,
    # one MOVE NOTIFY per phone, as the user's other automations send it.
    items = [i for i in find_candidates(hass, {"domains": ["notify"], "keywords": [], "area_keywords": [],
                                               "device_classes": []})["items"] if i["entity_id"] in services]
    if not items:
        return None
    by_service = {service: eid for eid, service in services.items()}
    ticked = list(dict.fromkeys(by_service[name] for name in found if name in by_service))
    for rid in [r["id"] for r in plan["roles"] if r["domains"] and set(r["domains"]) <= MESSAGE_DOMAINS]:
        candidates.pop(rid, None)
    plan["roles"] = [r for r in plan["roles"] if not (r["domains"] and set(r["domains"]) <= MESSAGE_DOMAINS)
                     and r["id"] != PHONES_ROLE]
    if len(plan["roles"]) >= MAX_ROLES:
        return None
    # [CHANGED v3.66.0] First in the plan, where the note about a named phone that does not exist is: at the end of
    # a long plan the user did not find it. Each phone says whose it is and what it is.
    plan["roles"].insert(0, {"id": PHONES_ROLE, "label": "Phones to notify", "purpose": "target", "domains": ["notify"],
                             "device_classes": [], "keywords": [], "area_keywords": [], "optional": False,
                             "named": False, "phones": True})
    owners = phone_owners(hass)
    items = [dict(i, **owners.get(i["entity_id"], {})) for i in items]
    first = [dict(i, named=True) for i in items if i["entity_id"] in ticked]
    candidates[PHONES_ROLE] = {"items": first + [i for i in items if i["entity_id"] not in ticked], "exact": True}
    return ticked


@callback
def presence_roles(hass: HomeAssistant, plan: dict, candidates: dict) -> None:
    """[ADDED v3.83.0] Who is where: a zone holds no one and a person is somewhere - being at a place takes both. The
    user's train reminder ("when I am at a zone I choose"): one plan gave a zone and no one to be in it, the next a
    person and no zone, and asked for the zone in words. A zone gets the role of who must be there; a person or a tracker
    gets a zone, optional - the logic may read home or away from the person alone.
    [CHANGED v3.84.0] One role for both - the user's train reminder had "location tracking / zone", the people, the
    trackers and the zones in one list - is the two: it keeps who must be there, and the zone is added, not optional, as
    the plan asked for one, ranked by the words of that role. The zone chosen on the card (zone_choices) is where: then
    no zone is picked here."""
    if plan.get("intent") == "answer":
        return
    split, words = False, []
    for role in plan["roles"]:
        domains = role.get("domains") or []
        if "zone" in domains and set(domains) & set(PRESENCE_DOMAINS):
            role.update(domains=[d for d in domains if d != "zone"], label="Who must be there")
            candidates[role["id"]] = find_candidates(hass, role)
            split, words = True, words + (role.get("keywords") or [])
    zones = any(r.get("zone_choice") or "zone" in (r.get("domains") or []) for r in plan["roles"])
    people = any(set(r.get("domains") or []) & set(PRESENCE_DOMAINS) for r in plan["roles"])
    if zones == people or len(plan["roles"]) >= MAX_ROLES:
        return
    ids = {r["id"] for r in plan["roles"]}
    rid = "who_is_there" if zones else "the_zone"
    while rid in ids:
        rid += "_x"
    role = ({"id": rid, "label": "Who must be there", "purpose": "condition", "domains": list(PRESENCE_DOMAINS)} if zones
            else {"id": rid, "label": "The zone", "purpose": "condition", "domains": ["zone"], "optional": not split,
                  "keywords": list(dict.fromkeys(words))[:12]})
    role.update(device_classes=[], keywords=role.get("keywords", []), area_keywords=[], named=False,
                optional=role.get("optional", False))
    plan["roles"].append(role)
    candidates[rid] = find_candidates(hass, role)


@callback
def message_phones(hass: HomeAssistant, plan: dict, candidates: dict) -> None:
    """[ADDED v3.83.0] A request whose point is a message - a reminder, spoken or not - gets LIBI's list of phones when the
    plan has none: the user's train reminder had a zone and a time, and nowhere to say it. A phone must be ticked, and
    the app on it reads a spoken message aloud."""
    if plan.get("intent") == "answer" or not any(r.get("kind") == "message" for r in plan.get("requirements") or []):
        return
    if any(r["id"] == PHONES_ROLE or (r.get("domains") and set(r["domains"]) <= MESSAGE_DOMAINS) for r in plan["roles"]):
        return
    if offer_phones(hass, plan, candidates):
        plan["roles"][0].update(optional=False, offered=False, for_message=True)


# [ADDED v3.84.0] The options of the zone chosen on the card: as many as a helper LIBI proposes may have (clean_new_helpers).
MAX_ZONE_OPTIONS = 30


@callback
def zone_states(hass: HomeAssistant) -> list[str]:
    """[ADDED v3.84.0] What a person's state is in each of the user's zones - "home" in the Home zone, the zone's name in
    any other - Home first, the others by name. A passive zone is never anyone's state, nor is a name longer than an
    option of a dropdown LIBI proposes."""
    out = ["home"] if hass.states.get("zone.home") else []
    for state in sorted(hass.states.async_all("zone"), key=lambda s: s.name.casefold()):
        name = str(state.name or "")
        if state.entity_id != "zone.home" and not state.attributes.get("passive") and 0 < len(name) <= 60 \
                and name not in out:
            out.append(name)
    return out[:MAX_ZONE_OPTIONS]


@callback
def zone_choice_settings(hass: HomeAssistant, icon: Any = None) -> dict:
    """[ADDED v3.84.0] The helper of the zone chosen on the card: a dropdown of the user's zones (zone_states)."""
    return {"icon": str(icon or "").strip()[:100] or "mdi:map-marker", "options": zone_states(hass)}


def _lists_zones(state: Any, zones: set[str]) -> bool:
    """[ADDED v3.84.0] A dropdown whose every option is one of the user's zones: one a card can choose the zone with."""
    options = state.attributes.get("options") if state is not None and state.domain == "input_select" else None
    return isinstance(options, list) and bool(options) and all(str(o) in zones for o in options)


@callback
def zone_choices(hass: HomeAssistant, plan: dict, candidates: dict) -> None:
    """[ADDED v3.84.0] The zone the user chooses on the card. The user's train reminder - "if I am at a zone I choose from
    the UI" - got a text helper for it, with a map icon, in which no zone can be chosen. A setting whose role says zone (or
    location, place, area or region, or whose helper has a map icon, in a plan about who or where), or LIBI's role
    "zone_choice", is a dropdown of the user's zones as a person's state names them: the helper proposed for it has them
    as its options, and the list to pick from holds only dropdowns of the user's zones. The zone is then not picked in
    the chat, so a role for a fixed zone goes. Nothing is created here."""
    if plan.get("intent") == "answer":
        return
    zones = zone_states(hass)
    if not zones:
        return
    presence = any(set(r.get("domains") or []) & {"zone", *PRESENCE_DOMAINS} for r in plan["roles"])
    helpers = {h["role"]: h for h in plan["new_helpers"]}
    lists = sorted((s for s in hass.states.async_all("input_select") if _lists_zones(s, set(zones))),
                   key=lambda s: s.name.casefold())
    chosen = False
    for role in plan["roles"]:
        rid = str(role["id"])
        setting = set(role.get("domains") or []) - {"zone"}
        icon = str(((helpers.get(rid) or {}).get("settings") or {}).get("icon") or "")
        says = bool(_ZONE_CHOICE_RE.search(rid) or (presence and (_PLACE_CHOICE_RE.search(rid) or icon.startswith("mdi:map"))))
        if not (role.get("zone_choice") or rid == "zone_choice" or (says and setting and setting <= ZONE_CHOICE_DOMAINS)):
            continue
        chosen = True
        role.update(domains=["input_select"], zone_choice=True)
        if rid in helpers:
            helpers[rid].update(domain="input_select",
                                settings=zone_choice_settings(hass, helpers[rid]["settings"].get("icon")))
        items = [{"entity_id": s.entity_id, "name": s.name, "area": "", "device_class": "", "state": s.state}
                 for s in lists]
        candidates[rid] = {"items": items[:MAX_CANDIDATES], "exact": bool(items), "total": len(items)}
    if chosen:
        fixed = {r["id"] for r in plan["roles"] if (r.get("domains") or []) == ["zone"]}
        plan["roles"] = [r for r in plan["roles"] if r["id"] not in fixed]
        for rid in fixed:
            candidates.pop(rid, None)


def zone_choice_context(plan: dict, selections: dict) -> list[str]:
    """[ADDED v3.84.0] How the logic reads the zone chosen on the card: who must be there is in it when their state is the
    zone chosen. Home Assistant's state condition takes an input_select as the state and compares with the state of that
    dropdown - one CMP EQ."""
    who = next((r["id"] for r in plan["roles"] if selections.get(r["id"])
                and set(r.get("domains") or []) & set(PRESENCE_DOMAINS)), "")
    out = []
    for role in plan["roles"]:
        if who and role.get("zone_choice") and selections.get(role["id"]):
            check = json.dumps({"condition": "state", "entity_id": f"role:{who}", "state": f"role:{role['id']}"})
            out.append(f"ZONE CHOICE (the user chooses the zone on the card): role:{role['id']} holds the zone chosen, as "
                       "a person's state names it. Who must be there is in it when their state is that one - checked "
                       f"right after the trigger that starts the logic, exactly so: {check}.")
    return out


def optional_message_roles(plan: dict, services: list[str]) -> None:
    """[ADDED v3.62.0] When the user's message names notify services that exist, a role for a phone is optional:
    the build writes those services. In the user's test two required phone roles listed notify entities only,
    and the second phone was among none of them. The chat says why the role is optional."""
    if not services:
        return
    for role in plan.get("roles") or []:
        if role["domains"] and set(role["domains"]) <= MESSAGE_DOMAINS:
            role["optional"], role["message"] = True, True


async def validate_with_home_assistant(hass: HomeAssistant, level: str, config: dict) -> str | None:
    """Home Assistant's own schema has the last word. Returns an error text or None.
    [CHANGED v3.85.0] Public: SAVE & COMPILE checks with it what it sends to Home Assistant's config API; and a scene is
    checked as that API checks one, by the scene integration's schema. Home Assistant's validators rename keys in the
    dict they are given (trigger becomes triggers), so each gets a copy: what is checked is never changed."""
    try:
        if level == "script":
            from homeassistant.components.script.config import async_validate_config_item  # noqa: PLC0415
            result = await async_validate_config_item(hass, "libi_ai_check", copy.deepcopy(config))
        elif level == "automation":
            from homeassistant.components.automation.config import async_validate_config_item  # noqa: PLC0415
            result = await async_validate_config_item(hass, "libi_ai_check", copy.deepcopy(config))
        elif level == "scene":
            from homeassistant.components.scene import PLATFORM_SCHEMA  # noqa: PLC0415
            PLATFORM_SCHEMA(copy.deepcopy(config))
            return None
        else:
            return None
    except Exception as err:  # noqa: BLE001
        return _sanitize(err)
    if result is None:
        return "Home Assistant rejected the draft."
    status = getattr(result, "validation_status", "ok")
    if str(getattr(status, "value", status)) != "ok":
        return _sanitize(getattr(result, "validation_error", None) or "Home Assistant rejected the draft.")
    return None


def _json_object(value: Any) -> dict | None:
    """[ADDED v3.55.0] A field the model writes as JSON text (or, from a model that ignores the schema, as
    the object itself). {} when it is empty, None when it is text that is not a JSON object."""
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    if not text:
        return {}
    # [CHANGED v3.57.0] What models get wrong in JSON text: \' for the single quotes of a Jinja template
    # (not a JSON escape), a sentence after the object, or YAML written instead. The result is only
    # data: every key and entity in it is still validated by _Draft.
    for attempt in (text, text.replace("\\'", "'")):
        try:
            data, _end = json.JSONDecoder().raw_decode(attempt)
        except ValueError:
            continue
        return data if isinstance(data, dict) else None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        _LOGGER.warning("[libi] The AI's configuration is neither JSON nor YAML: %s", _sanitize(str(err))[:200])
        return None
    return data if isinstance(data, dict) else None


async def async_build_draft(hass: HomeAssistant, plan: dict, selections: dict, raw: dict) -> dict:
    """The model's build answer, validated and turned into an automation, script or scene dict
    that the importer can draw. Returns errors instead when anything does not hold."""
    level = raw.get("level") if raw.get("level") in LEVELS else plan.get("level", "automation")
    config = _json_object(raw.get("config"))
    draft = _Draft(hass, selections)
    unreadable = config is None
    if unreadable:
        draft.err("The AI's configuration could not be read. Try Build again.")
        config = {}
    body = draft.walk(copy.deepcopy(config))

    name = str(raw.get("name") or plan.get("name") or "AI automation")[:80]
    description = str(raw.get("description") or "")[:300]
    if level == "automation":
        auto = {"id": f"libi_ai_{int(time.time() * 1000)}", "alias": name, "description": description,
                "mode": body.get("mode", "single"), "triggers": body.get("triggers") or [],
                "conditions": body.get("conditions") or [], "actions": body.get("actions") or []}
        # [CHANGED v3.57.0] Not when nothing could be read: that is the one error, the rest follows from it.
        if not auto["triggers"] and not unreadable:
            draft.err("An automation needs at least one trigger.")
        ha_config = {k: v for k, v in auto.items() if k != "id"}
    elif level == "script":
        sequence = body.get("sequence") or body.get("actions") or []
        auto = {"id": f"libi_ai_{int(time.time() * 1000)}", "alias": name, "description": description,
                "mode": body.get("mode", "single"), "triggers": [], "conditions": [], "actions": sequence}
        ha_config = {"alias": name, "description": description, "mode": auto["mode"], "sequence": sequence}
    else:
        actions = body.get("actions") or []
        auto = {"id": f"libi_ai_{int(time.time() * 1000)}", "alias": name, "description": description,
                "triggers": [], "conditions": [], "actions": actions}
        ha_config = None
    if not auto["actions"] and not unreadable:
        draft.err("The draft does nothing: it has no actions.")
    # [CHANGED v3.65.0] The message goes to every phone the user ticked, each by its own notify service - one MOVE
    # NOTIFY per phone, which the ladder shows with the phone - and to no phone the user did not tick.
    phones = selections.get(PHONES_ROLE) or []
    if phones and not unreadable:
        known = phone_services(hass)
        wanted = {known[eid] for eid in phones if eid in known}
        missed = sorted(wanted - draft.services)
        if missed:
            draft.err(f"The message does not go to {', '.join(missed)}, which the user ticked.")
        extra = sorted(name for name in draft.services if name in set(known.values()) - wanted)
        if extra:
            draft.err(f"{', '.join(extra)} is a phone the user did not tick.")
        if "notify.send_message" in draft.services:
            draft.err("notify.send_message hides the phone on the ladder: send with each phone's own service.")

    # [CHANGED v3.73.0] The settings the logic reads come on LIBI's own card, the same every run - the time, the days
    # as one row of buttons, the other settings, the devices (the user: "it does not let me choose the days and the
    # hours"). The model's card only when the logic reads no setting.
    card = settings_card(hass, plan, selections, name, auto, draft.used) or _json_object(raw.get("ui_card")) or {}
    card_yaml = ""
    if card:
        card_draft = _Draft(hass, selections)
        card_body = _clean_card(card_draft, card)
        draft.errors.extend(e for e in card_draft.errors if e not in draft.errors)
        draft.used |= card_draft.used
        card_yaml = yaml.dump(card_body, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if not draft.errors and ha_config is not None:
        problem = await validate_with_home_assistant(hass, level, ha_config)
        if problem:
            draft.err(f"Home Assistant rejected the draft: {problem}")

    sensitive = sorted(e for e in draft.used if e.split(".")[0] in SENSITIVE_DOMAINS)
    preview = yaml.dump(ha_config if ha_config is not None else {"name": name, "actions": auto["actions"]},
                        default_flow_style=False, allow_unicode=True, sort_keys=False)
    return {"ok": not draft.errors, "errors": draft.errors, "level": level, "auto": auto,
            "yaml": preview, "card_yaml": card_yaml, "sensitive": sensitive,
            "reply": str(raw.get("reply") or "")[:1200],
            "notes": _str_list(raw.get("notes"), 8, 300)}


# [ADDED v3.62.0] How many answers the build asks for at most: the first one, and two corrections.
MAX_BUILD_TRIES = 3

# [ADDED v3.62.0] What to do about the problems models make most, said with the problem when it goes back.
_REPAIR_HINTS = (
    # [ADDED v3.80.0]
    (re.compile(r"The user answered", re.I),
     "Write it exactly as the ON/OFF SWITCH, START MESSAGE, END MESSAGE, OFFLINE and LOW BATTERY lines of the message "
     "say: a check or a message in the start option, and a trigger with an option of its own."),
    # [ADDED v3.81.0]
    (re.compile(r"only in fair weather", re.I),
     'Check the weather now so, in the start option: {"condition": "not", "conditions": [{"condition": "state", '
     '"entity_id": "role:<weather role>", "state": ["rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail"]}]} - '
     "never that it is sunny."),
    # [ADDED v3.75.0]
    (re.compile(r"start with trigger id", re.I),
     "One option per trigger id: its conditions, then its steps in order. A check that must hold before a step is a "
     "condition step among them - today's forecast, read just before it, is checked in the start option before the "
     "valve turns on."),
    (re.compile(r"set on the card|ticked on the card", re.I),
     "It is an alarm clock (ALARM CLOCK in the message): start with the time trigger written there, check the day roles "
     "right after it in the start option, as Days of the week says, and let no schedule start it."),
    # [ADDED v3.73.0]
    (re.compile(r"and the logic does not do it", re.I),
     "Keep everything else and add it the ladder way: in the option it belongs to (today's forecast is read and "
     "checked in the start option, before the valve turns on), or as an option of its own with its trigger."),
    # [ADDED v3.72.0]
    (re.compile(r"does not wait inside a run", re.I),
     "One trigger with an id for every event the logic reacts to, and actions as ONE choose with an option per "
     "trigger id; a time limit is the for of a trigger, an amount a numeric_state trigger. Nothing waits or stops."),
    (re.compile(r"expected (float|a number)", re.I),
     "numeric_state above and below take a number, or a role holding one input_number, number or sensor "
     "(\"above\": \"role:<id>\") - never a template. For a computed threshold use a template trigger or condition."),
    (re.compile(r"service \S+ does not exist", re.I),
     "Use only services that exist in this Home Assistant; leave the others out and say so in notes."),
    (re.compile(r"could not be read", re.I),
     "config is ONE JSON object written as text: double quotes, no comments, no trailing commas."),
    (re.compile(r"which the user ticked|the user did not tick|hides the phone", re.I),
     "Send each message with one {\"action\": \"notify.mobile_app_<phone>\", \"data\": {\"message\": \"...\"}} "
     "per phone, to exactly the services under PHONES."),
    (re.compile(r"sits inside another step", re.I),
     "Branch only at the top of the actions: make it a top-level if after the step it depends on, and join the "
     "conditions with and/or when it was inside another if."),
    (re.compile(r"needs exactly one entity", re.I),
     "Inside a template a role must hold one entity: use the role as the entity_id of a step instead."),
    (re.compile(r"did not pick|has no entity picked|is not something LIBI lets|is not allowed", re.I),
     "Write every device as role:<id> from ROLES, and only the keys, triggers, conditions and services the rules list."),
    (re.compile(r"could not keep this part|could not be drawn", re.I),
     "Keep the logic, but write that part in a plainer form: one step per action, conditions as steps of their own."),
)


def _as_roles(text: str, selections: dict) -> str:
    """[ADDED v3.62.0] The user's entities in a problem, as the role references the model wrote."""
    for rid, ids in selections.items():
        for eid in ids:
            text = re.sub(rf"(?<![\w.]){re.escape(eid)}(?![\w])", f"role:{rid}", text)
    return text


def nested_branches(actions: Any, path: str = "actions", top: bool = True) -> list[str]:
    """[ADDED v3.65.0] Where an if or a choose sits inside another step (if, choose, repeat, parallel, sequence).
    The ladder draws a branch only at the top of the actions, one rung per option, and keeps anything deeper as
    one block - in the user's NET 3 the if after the wait was a MOVE ACTION showing "if"."""
    found: list[str] = []
    for i, step in enumerate(actions if isinstance(actions, list) else []):
        if not isinstance(step, dict):
            continue
        here = f"{path}[{i}]"
        if not top and ("if" in step or "choose" in step):
            found.append(here)
        inner = [(step.get("then"), f"{here}.then"), (step.get("else"), f"{here}.else")]
        inner += [(opt.get("sequence"), f"{here}.choose[{k}]") for k, opt in enumerate(step.get("choose") or [])
                  if isinstance(opt, dict)]
        inner += [(step.get("default"), f"{here}.default"), (step.get("sequence"), f"{here}.sequence")]
        if isinstance(step.get("repeat"), dict):
            inner.append((step["repeat"].get("sequence"), f"{here}.repeat"))
        for k, branch in enumerate(step.get("parallel") or [] if isinstance(step.get("parallel"), list) else []):
            inner.append((branch.get("sequence") if isinstance(branch, dict) and "sequence" in branch else [branch],
                          f"{here}.parallel[{k}]"))
        for seq, where in inner:
            if seq:
                found += nested_branches(seq if isinstance(seq, list) else [seq], where, top=False)
    return found


_WAIT_READ = re.compile(r"\bwait\.(?:trigger|completed|remaining)\b")
WAIT_STEPS = ("wait_for_trigger", "wait_template", "stop")


def waits_in(actions: Any, path: str = "actions") -> list[str]:
    """[ADDED v3.72.0] Where an automation waits inside a run - a wait_for_trigger, a wait_template, a stop, or a
    template that reads wait. - which a ladder does not do: every rung reacts to a trigger of its own, and none waits
    for another. The user's NET 4 read wait.trigger in the rungs after its wait, and on a day of rain had none."""
    found: list[str] = []

    def walk(node: Any, here: str) -> None:
        if isinstance(node, dict):
            found.extend(f"{here} has {key}" for key in WAIT_STEPS if key in node)
            for key, value in node.items():
                walk(value, f"{here}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{here}[{i}]")
        elif isinstance(node, str) and _WAIT_READ.search(node):
            found.append(f"{here} reads wait.")

    walk(actions, path)
    return found


def shared_options(actions: Any) -> list[tuple[str, list[int]]]:
    """[ADDED v3.75.0] The trigger ids that start more than one option of a top-level choose, each with the numbers of
    those options (1 first). The ladder draws every option as a rung of its own, but Home Assistant runs only the
    FIRST option that holds: of two options of one trigger, the second runs only when the first does not. The user's
    NET 3 read today's forecast in its first `start` option and checked it in a second one, which was never reached
    on a morning it watered; on a day nobody ticked, it would have opened the valve without the day."""
    found: list[tuple[str, list[int]]] = []
    for step in actions if isinstance(actions, list) else []:
        options = step.get("choose") if isinstance(step, dict) else None
        by_id: dict[str, list[int]] = {}
        for number, option in enumerate(options if isinstance(options, list) else [], start=1):
            conds = option.get("conditions") if isinstance(option, dict) else None
            first = (conds if isinstance(conds, list) else [conds])[0] if conds else None
            if isinstance(first, dict) and first.get("condition") == "trigger":
                for tid in first.get("id") if isinstance(first.get("id"), list) else [first.get("id")]:
                    by_id.setdefault(str(tid), []).append(number)
        found += [(tid, numbers) for tid, numbers in by_id.items() if len(numbers) > 1]
    return found


def draft_problems(draft: dict, drawn: dict) -> list[str]:
    """[ADDED v3.62.0] Why a build answer is not ready: LIBI's or Home Assistant's checks, the drawing, or what the
    ladder could not keep as written. [] when it is ready.
    [CHANGED v3.65.0] And a branch inside another step, which the ladder can only show as one block.
    [CHANGED v3.72.0] And a wait inside a run, which the ladder way never needs.
    [CHANGED v3.75.0] And two options of one trigger id, which do not run as the ladder shows them (shared_options)."""
    if not draft["ok"]:
        return list(draft["errors"])
    if drawn.get("error"):
        return [drawn["error"]]
    problems = [f"LIBI's ladder could not keep this part as written: {issue}"
                for issue in (drawn.get("round_trip") or {}).get("issues", [])[:5]]
    problems += [f"LIBI's ladder draws an if or a choose only at the top of the actions: {where} sits inside "
                 "another step." for where in nested_branches(draft["auto"].get("actions"))[:5]]
    problems += [f"LIBI's ladder does not wait inside a run: {where}."
                 for where in waits_in(draft["auto"].get("actions"))[:5]]
    return problems + [f"LIBI's ladder draws every option of the choose as a rung of its own, but Home Assistant runs only "
                       f"the first option that holds: options {', '.join(map(str, numbers[:-1]))} and {numbers[-1]} start "
                       f'with trigger id "{tid}", so a later one runs only when the ones before it do not.'
                       for tid, numbers in shared_options(draft["auto"].get("actions"))[:3]]


def draft_rank(draft: dict, drawn: dict, problems: list[str] | None = None) -> int:
    """[ADDED v3.62.0] 0 ready, 1 valid but not drawn as written (the ladder changes it, or a branch is one block),
    2 not valid: the build keeps the best answer. [CHANGED v3.73.0] problems: what was found already, with the lines
    of the request the draft misses."""
    if not draft["ok"] or drawn.get("error"):
        return 2
    return 1 if (draft_problems(draft, drawn) if problems is None else problems) else 0


# [ADDED v3.73.0] ---------------------------------------------------------------- the request, line by line
_WEATHER_NOW_RE = re.compile(r"(?:is_state|states)\(\s*['\"]weather\.|states\.weather\.")


def _walk_nodes(value: Any):
    """Every dict in a configuration, depth first."""
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_nodes(item)


def _ids_in(node: dict) -> list[str]:
    found = node.get("entity_id")
    return [str(x) for x in (found if isinstance(found, list) else [found]) if x]


def _on_schedule(node: dict) -> bool:
    return (node.get("trigger") == "state" or node.get("condition") == "state") and any(
        e.startswith("schedule.") for e in _ids_in(node))


def _reads_weather_now(node: dict) -> bool:
    """The weather as it is now, a check of a weather entity's state - not today's forecast, which only
    weather.get_forecasts reads."""
    if node.get("condition") == "state" and any(e.startswith("weather.") for e in _ids_in(node)):
        return True
    return any(isinstance(v, str) and _WEATHER_NOW_RE.search(v) for v in node.values())


# [ADDED v3.81.0] The weather when it rains, and the fair weather a check of the rain now must let through. The user's
# draft of 2026-11-01 watered at 05:00 only when the weather now was sunny: before sunrise it is clear-night, so it would
# never have watered - and LIBI ticked the line of the rain now, as it only looked for a read of the weather.
RAIN_STATES = ("rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail")
_FAIR_STATES = {"sunny", "clear-night", "partlycloudy", "cloudy"}
_SKIPS_RAIN_RE = re.compile(r"not\s+in\s*\[[^\]]*['\"]rainy['\"]|!=\s*['\"]rainy['\"]|not\s+is_state\([^)]*['\"]rainy['\"]")
_ASKS_FAIR_RE = re.compile(r"(?<!not )is_state\([^)]*['\"](?:sunny|clear-night|partlycloudy|cloudy)['\"]"
                           r"|==\s*['\"](?:sunny|clear-night|partlycloudy|cloudy)['\"]|(?<!not )\bin\s*\[[^\]]*['\"]sunny['\"]")
_WEATHER_NOW_FAIR = ("it lets the start through only in fair weather (sunny), so it does not run on a clear night "
                     "(clear-night, before sunrise) or a cloudy morning - check that it is not raining instead: a not "
                     f"of the state {', '.join(RAIN_STATES)}")
_WEATHER_NOW_UNCHECKED = "it reads the weather now, but no check before the start skips on rain"


def _weather_check(node: dict) -> str:
    """[ADDED v3.81.0] What a check of the weather now does: "skips" on rain, "fair" when it asks for fair weather (or
    for rain), "" when it is no such check."""
    if node.get("condition") == "not" or "not" in node:
        inner = node.get("conditions") if node.get("condition") == "not" else node.get("not")
        states = {str(s) for n in _leaves(inner) if n.get("condition") == "state"
                  and any(e.startswith("weather.") for e in _ids_in(n))
                  for s in (n.get("state") if isinstance(n.get("state"), list) else [n.get("state")])}
        if not states:
            return ""
        return "skips" if states & set(RAIN_STATES) and not states & _FAIR_STATES else "fair"
    if node.get("condition") == "state" and any(e.startswith("weather.") for e in _ids_in(node)):
        state = node.get("state")
        states = {str(s) for s in (state if isinstance(state, list) else [state])}
        return "skips" if states >= _FAIR_STATES and not states & set(RAIN_STATES) else "fair"
    text = node.get("value_template") if node.get("condition") == "template" else None
    if isinstance(text, str) and _WEATHER_NOW_RE.search(text):
        if _ASKS_FAIR_RE.search(text):
            return "fair"
        return "skips" if _SKIPS_RAIN_RE.search(text) else ""
    return ""


def _weather_now_checks(config: Any) -> tuple[bool, bool]:
    """[ADDED v3.81.0] Of the checks before a step that turns something on - where a check holds the start back - whether
    one skips on rain, and whether one asks for fair weather. Without such a step, the checks of every option."""
    auto = config if isinstance(config, dict) else {}
    options = _options(auto)
    checks = [c for o in options for i, s in enumerate(o["steps"])
              if isinstance(s, dict) and str(s.get("action") or s.get("service") or "").split(".")[-1] in _ON_SERVICES
              for c in _checks_before(auto, o, i)]
    if not checks:
        checks = [c for o in options for c in _checks_before(auto, o, len(o["steps"]))]
    kinds = {_weather_check(c) for c in checks}
    return "skips" in kinds, "fair" in kinds


# How a line of each kind shows in a configuration: a test of one node - a trigger, a condition or a step.
_KIND_TESTS = {
    "time": lambda n: n.get("trigger") in ("time", "time_pattern", "sun") or _on_schedule(n) or (
        n.get("condition") == "time" and ("after" in n or "before" in n)),
    "days": lambda n: "weekday" in n or _on_schedule(n) or bool(day_bits_entity(n.get("value_template"))),
    "weather_now": _reads_weather_now,
    "forecast": lambda n: n.get("action") == "weather.get_forecasts",
    "amount": lambda n: "numeric_state" in (n.get("trigger"), n.get("condition")),
    "time_limit": lambda n: "delay" in n or (bool(n.get("for")) and ("trigger" in n or "condition" in n)),
    "message": lambda n: (str(n.get("action") or "").split(".")[0] in MESSAGE_DOMAINS
                          or n.get("action") in MESSAGE_SERVICES),
}
# What the logic lacks when a line of that kind is not in it: said to the model, and to the user.
_KIND_MISSING = {
    "time": "nothing starts it at a time or by a schedule",
    "days": "no check of the days",
    "weather_now": "it never reads the weather now",
    "forecast": "it never reads the forecast (weather.get_forecasts)",
    "amount": "no numeric_state trigger or condition for the amount",
    "time_limit": "no time limit (a for of a trigger, or a delay)",
    "message": "it sends no message",
    "card": "there is no dashboard card",
}
# [ADDED v3.75.0] With an alarm clock: the lines LIBI checks when the plan has none for them, and what the logic lacks.
_ALARM_LINES = {"time": "It starts at the time set on the card", "days": "Only on the days ticked on the card"}
_ALARM_MISSING = {
    "time": "it does not start at the time set on the card",
    "schedule": "a schedule starts it - only the time set on the card may",
    "days": "it does not check the days ticked on the card (CMP DAY of the days helper)",
}
# [ADDED v3.75.0]
_FORECAST_UNCHECKED = ("it reads the forecast, but no step checks it before the next action - a condition right after "
                       "weather.get_forecasts, in the same option")


def _forecast_checked(config: Any) -> bool:
    """[ADDED v3.75.0] Today's forecast is read AND checked: in one list of steps, weather.get_forecasts answering into a
    variable, then a condition step reading that variable before any other action. The user's NET 3 read it in the
    start option and checked it in a second option of the same trigger, which a choose never reaches once the first
    one runs - so it watered when rain was expected."""
    for node in _walk_nodes(config):
        for key in ("actions", "sequence", "then", "else", "default"):
            steps = node.get(key)
            for i, step in enumerate(steps if isinstance(steps, list) else []):
                if not (isinstance(step, dict) and step.get("action") == "weather.get_forecasts"
                        and step.get("response_variable")):
                    continue
                read = re.compile(rf"(?<![\w.]){re.escape(str(step['response_variable']))}(?![\w])")
                for later in steps[i + 1:]:
                    if isinstance(later, dict) and "condition" in later and read.search(json.dumps(later)):
                        return True
                    if isinstance(later, dict) and "action" in later:
                        break
    return False


def _rung_nodes(rung: dict) -> list[dict]:
    """The YAML nodes the elements of a drawn rung came from, and every node inside them."""
    out: list[dict] = []

    def walk(elements: Any) -> None:
        for el in elements if isinstance(elements, list) else []:
            if not isinstance(el, dict):
                continue
            if isinstance(el.get("raw"), dict):
                out.extend(_walk_nodes(el["raw"]))
            for branch in el.get("branches") or []:
                walk(branch)
            walk(el.get("sequence"))
    walk(rung.get("elements"))
    return out


def requirement_report(plan: dict, draft: dict, drawn: dict, raw: dict, alarm: dict | None = None,
                       safety: dict | None = None) -> list[dict]:
    """[ADDED v3.73.0] Each line of the user's request, checked in the logic itself where its kind shows there: ok True
    or False, and the rung of the drawing that does it. A line of another kind is placed only by the model's own word
    (covers), and is never shown as checked (ok None). The texts are shown, never acted on. [] when the plan has no
    lines or the draft does not hold.
    [CHANGED v3.75.0] alarm: the alarm clock the user picked (picked_alarm_clock). Its time is the time line - a time
    trigger at it, and no schedule starting the logic - and its switches are the days line, each checked on its own
    day; LIBI checks both also when the plan has no line for them, with a line of its own. In the user's NET 3 a
    schedule started the logic and passed for the time. The forecast line holds only when a step checks the forecast
    right after reading it (_forecast_checked).
    [CHANGED v3.76.0] The days line of an alarm clock is the CMP DAY of its days helper (DAY_BITS_TEMPLATE).
    [CHANGED v3.80.0] safety: the user's answers to LIBI's own questions (safety_answers), checked after the lines of
    the request (safety_report) - also when the request has none."""
    alarm = alarm or {}
    lines = list(plan.get("requirements") or [])
    kinds = {line["kind"] for line in lines}
    lines += [{"id": f"alarm_{kind}", "text": text, "kind": kind} for kind, text in _ALARM_LINES.items()
              if kind not in kinds and alarm.get(kind)]
    asked = bool(safety and (safety.get("enable") or safety.get("offline") or safety.get("battery")))
    if not (lines or asked) or not draft.get("ok"):
        return []
    auto = draft.get("auto") or {}
    tests, missing = dict(_KIND_TESTS), dict(_KIND_MISSING)
    if alarm.get("time"):
        tests["time"] = lambda n: n.get("trigger") == "time" and alarm["time"] in (
            n["at"] if isinstance(n.get("at"), list) else [n.get("at")])
        missing["time"] = _ALARM_MISSING["time"]
    if alarm.get("days"):
        missing["days"] = _ALARM_MISSING["days"]
    by_schedule = bool(alarm.get("time")) and any(
        node.get("trigger") == "state" and any(e.startswith("schedule.") for e in _ids_in(node))
        for node in _walk_nodes(auto.get("triggers")))
    bits_checked = config_day_bits(auto)
    forecast_checked = _forecast_checked(auto)
    rungs = [_rung_nodes(r) for r in ((drawn or {}).get("net") or {}).get("rungs") or []]
    by_trigger: dict[str, int] = {}
    for number, nodes in enumerate(rungs, start=1):
        for node in nodes:
            if "trigger" in node and node.get("id") is not None:
                by_trigger.setdefault(str(node["id"]), number)
    covers: dict[str, dict] = {}
    for item in raw.get("covers") if isinstance(raw.get("covers"), list) else []:
        if isinstance(item, dict):
            covers.setdefault(str(item.get("requirement") or ""), item)
    report = []
    for line in lines:
        cover = covers.get(line["id"]) or {}
        item = {"id": line["id"], "text": line["text"], "kind": line["kind"], "ok": None, "rung": 0,
                "how": _sanitize(str(cover.get("how") or ""))[:200], "missing": ""}
        test = tests.get(line["kind"])
        if line["kind"] == "card":
            item["ok"] = bool(draft.get("card_yaml"))
        elif test is not None:
            item["ok"] = any(test(node) for node in _walk_nodes(auto))
            item["rung"] = next((n for n, nodes in enumerate(rungs, start=1) if any(test(x) for x in nodes)), 0)
        if line["kind"] == "days" and alarm.get("days"):
            item["ok"] = alarm["days"] in bits_checked
        if line["kind"] != "card" and not item["rung"]:
            item["rung"] = by_trigger.get(str(cover.get("trigger_id") or ""), 0)
        if item["ok"] is False:
            item["missing"] = missing.get(line["kind"], "")
        if line["kind"] == "time" and by_schedule:
            item["ok"], item["missing"] = False, _ALARM_MISSING["schedule"]
        if line["kind"] == "forecast" and item["ok"] and not forecast_checked:
            item["ok"], item["missing"] = False, _FORECAST_UNCHECKED
        # [ADDED v3.81.0] The rain now holds the start back on rain only - never a check that asks for fair weather.
        if line["kind"] == "weather_now" and item["ok"]:
            skips, fair = _weather_now_checks(auto)
            if fair or not skips:
                item["ok"], item["missing"] = False, _WEATHER_NOW_FAIR if fair else _WEATHER_NOW_UNCHECKED
        report.append(item)
    return report + safety_report(safety, auto, by_trigger)


def requirement_problems(report: list[dict]) -> list[str]:
    """[ADDED v3.73.0] The lines of the request the logic does not do, as problems the model corrects."""
    # [CHANGED v3.80.0] A line of LIBI's own is what the user answered to LIBI's questions.
    return [(f'The user answered "{item["text"]}"' if str(item.get("id", "")).startswith("libi_")
             else f'The request asks "{item["text"]}" ({item["kind"]})') + f', and the logic does not do it: {item["missing"]}.'
            for item in report if item["ok"] is False][:6]


def repair_request(raw: dict, problems: list[str], selections: dict) -> list[dict]:
    """[ADDED v3.62.0] The conversation goes on with the model's own answer and what LIBI found wrong in it, so the
    next answer corrects it instead of starting over. A problem names the user's entities by the role references
    the model wrote: the model never gets an entity_id LIBI filled in. The model's answer is data it wrote."""
    lines = []
    for problem in problems[:12]:
        text = _as_roles(_sanitize(str(problem)), selections)[:500]
        lines.append(f"- {text}")
        hint = next((h for rx, h in _REPAIR_HINTS if rx.search(text)), "")
        if hint:
            lines.append(f"  How: {hint}")
    return [{"role": "assistant", "content": json.dumps(raw, ensure_ascii=False, default=str)[:16000]},
            {"role": "user", "content": "LIBI checked your answer, and this does not hold yet:\n" + "\n".join(lines)
             + "\nAnswer again with the whole answer corrected, in the same JSON. Keep everything else as it was."}]


# Values the user SETS. A button is pressed and a counter or timer runs; they are not settings.
CARD_DOMAINS = ("input_boolean", "input_number", "input_datetime", "input_select", "input_text", "schedule")
# [ADDED v3.63.0] What a card also lets the user switch: the devices the logic turns on and off - the user's
# watering card asked for the valve. Locks, alarms and sirens are left for the user to add by hand.
CARD_DEVICE_DOMAINS = ("switch", "valve", "light", "fan", "cover", "climate", "media_player", "humidifier",
                       "water_heater")
# [ADDED v3.79.0] What the logic reads and the user only looks at, under the devices: the litres the valve delivered
# next to the valve, as the user's own garden card has them; the weather the logic checks. At most MAX_CARD_READINGS.
CARD_READING_DOMAINS = ("sensor", "binary_sensor", "weather")
MAX_CARD_READINGS = 4


def _card(hass: HomeAssistant, entities: list[str], title: str, days: dict[str, int] | None = None,
          need_settings: bool = True, day_bits: set[str] | None = None, enable: set[str] | None = None) -> dict:
    """[ADDED v3.63.0] An entities card of the given entities that exist, after a divider the devices. With
    need_settings there is no card without a setting - a button and a light need no dashboard. {} when there is
    nothing for a card. [CHANGED v3.73.0] Read as an alarm clock is: the time first, then the days as ONE row of
    buttons in week order - each tapped to tick or untick it, its colour saying which - then the other settings.
    [CHANGED v3.76.0] A days helper (day_bits) is LIBI's own row of seven checkboxes, right after the time; the row of
    buttons stays for the switches of a net of 3.73.0 - 3.75.0.
    [CHANGED v3.79.0] Laid out for the dashboard - the user, of the card of 2026-11-01: "the design should be nicer and
    easier to use". Three groups, a divider between them: the alarm clock (the time, the days), the other settings, the
    devices with what the logic reads (CARD_READING_DOMAINS). No row says the card's title again (_row_name), and no
    toggle in the header: with two switches on the card it would switch the valve together with a setting.
    [CHANGED v3.80.0] enable: the on/off switch of the logic (the user's enable), first, as on an alarm clock - the
    switch of "<name> - enabled" reads "Enabled"."""
    days, day_bits, enable = days or {}, set(day_bits or ()), set(enable or ())
    title = str(title or "Settings")[:60]
    times, bits_rows, settings, day_rows, devices, readings, switches = [], [], [], [], [], [], []
    for eid in dict.fromkeys(entities):
        state = hass.states.get(eid)
        domain = eid.split(".")[0]
        if state is None:
            continue
        row = {"entity": eid, "name": str(state.name or eid)[:60]}
        if eid in enable and domain == "input_boolean":
            switches.append(row)
        elif eid in day_bits and domain in DAY_BITS_DOMAINS:
            bits_rows.append({"type": DAYS_ROW_TYPE, **row})
        elif domain in CARD_DOMAINS and eid in days:
            day_rows.append((days[eid], row))
        elif domain in ("input_datetime", "schedule"):
            times.append(row)
        elif domain in CARD_DOMAINS:
            settings.append(row)
        elif domain in CARD_DEVICE_DOMAINS:
            devices.append(row)
        elif domain in CARD_READING_DOMAINS and len(readings) < MAX_CARD_READINGS:
            readings.append(row)
    if not (times or bits_rows or settings or day_rows or switches) and (need_settings or not devices):
        return {}
    # LIBI names an alarm clock after its net: the time "<name>", the days "<name> - days" (and each day's switch
    # "<name> - Sun" in 3.73.0 - 3.75.0). Under the title of that net the rows said it again. What the days are named
    # after is left out of the alarm clock's own rows only.
    clock_heads = [title] + [row["name"].rpartition(" - ")[0] for row in bits_rows + [r for _i, r in day_rows]
                             if " - " in row["name"]]

    def named(row: dict, default: str | None = None, heads: tuple[str, ...] = (title,)) -> dict:
        return {**row, "name": _row_name(row["name"], list(heads), default or row["name"])}

    clock = [named(row, "Enabled", (title, row["name"].rpartition(" - ")[0] or title)) for row in switches]
    clock += [named(row, "Start time" if _is_clock_entity(hass, row["entity"]) else None, tuple(clock_heads))
              for row in times]
    clock += [named(row, "Days", tuple(clock_heads)) for row in bits_rows]
    if day_rows:
        # A tap of a button in this row opens the details unless it says toggle (hui-buttons-base sets no default).
        clock.append({"type": "buttons", "entities": [
            {"entity": row["entity"], "name": _day_label(row["name"]), "tap_action": {"action": "toggle"}}
            for _i, row in sorted(day_rows, key=lambda x: x[0])]})
    rows: list[dict] = []
    for group in (clock, [named(row) for row in settings], [named(row) for row in devices + readings]):
        if group and rows:
            rows.append({"type": "divider"})
        rows += group
    return {"type": "entities", "title": title, "show_header_toggle": False, "state_color": True, "entities": rows}


def _row_name(name: str, heads: list[str], default: str) -> str:
    """[ADDED v3.79.0] A row's name without the words the card already shows: a name that is one of the heads is the
    default; one that starts with "<head> - " is what follows it ("days" is "Days"); any other name stays as it is."""
    text = str(name or "").strip()
    for head in (str(h or "").strip() for h in heads):
        if text.casefold() == head.casefold():
            return default[:60]
        lead = f"{head} - "
        tail = text[len(lead):].strip() if text[:len(lead)].casefold() == lead.casefold() else ""
        if tail:
            return (tail[:1].upper() + tail[1:] if tail.islower() else tail)[:60]
    return text[:60]


def _day_label(name: str) -> str:
    """[ADDED v3.73.0] A day switch's label on its button: what its name says after the last " - " ("Watering - Sun" is
    Sun), or the whole name."""
    _head, sep, tail = str(name or "").rpartition(" - ")
    return (tail if sep and tail.strip() else str(name or "")).strip()[:20]


def settings_card(hass: HomeAssistant, plan: dict, selections: dict, title: str, config: Any = None,
                  used: set[str] | None = None) -> dict:
    """[ADDED v3.44.0] An entities card with every helper the logic reads, so the user sets the days,
    the time, the amount and the on/off choices from a dashboard. Built by LIBI from the user's own
    picks - never from the model - and only of entities that exist. {} when no helper is used.
    [CHANGED v3.63.0] With the devices the user picked to switch at the end (the user's watering card asked for
    the valve). The card is _card, which the NET menu's card uses as well.
    [CHANGED v3.73.0] Only what the logic uses (used), and each day switch known by its role or by the day the
    configuration checks it on (config_days).
    [CHANGED v3.76.0] And the days helper by its role or by the CMP DAY that reads it (config_day_bits).
    [CHANGED v3.80.0] And the on/off switch by its role or by how the configuration uses it (config_enable)."""
    entities, days, day_bits = [], {}, set()
    for role in plan.get("roles") or []:
        day = _day_of(role["id"])
        for eid in selections.get(role["id"]) or []:
            if used is not None and eid not in used:
                continue
            entities.append(eid)
            if day and eid.split(".")[0] == "input_boolean":
                days[eid] = _DAY_ORDER.index(day)
            if _is_days_role(role):
                day_bits.add(eid)
    days.update(config_days(config))
    return _card(hass, entities, title, days, day_bits=day_bits | config_day_bits(config),
                 enable=set(selections.get(ENABLE_ROLE) or []) | config_enable(config))


def config_days(config: Any) -> dict[str, int]:
    """[ADDED v3.73.0] The day switches a configuration checks, each with its place in the week (Sunday first): an "and"
    of a time condition for one weekday and that switch being on, as the build writes the days the user ticks."""
    out: dict[str, int] = {}
    for node in _walk_nodes(config):
        parts = node.get("conditions") if node.get("condition") == "and" else None
        if not isinstance(parts, list) or len(parts) != 2 or not all(isinstance(p, dict) for p in parts):
            continue
        clock = next((p for p in parts if p.get("condition") == "time"), {})
        switch = next((p for p in parts if p.get("condition") == "state"), {})
        day = clock.get("weekday")
        day = day[0] if isinstance(day, list) and len(day) == 1 else day
        ids = _ids_in(switch)
        if isinstance(day, str) and day in _DAY_ORDER and len(ids) == 1 and ids[0].startswith("input_boolean.") \
                and str(switch.get("state")) == "on":
            out.setdefault(ids[0], _DAY_ORDER.index(day))
    return out


def config_day_bits(config: Any) -> set[str]:
    """[ADDED v3.76.0] The 8-bit helpers a configuration reads the days of the week from: its CMP DAY of a helper
    (DAY_BITS_TEMPLATE)."""
    return {eid for node in _walk_nodes(config) if node.get("condition") == "template"
            for eid in [day_bits_entity(node.get("value_template"))] if eid}


def config_entities(hass: HomeAssistant, config: Any) -> list[str]:
    """[ADDED v3.63.0] The entities a configuration uses, in the order they appear: entity_ids anywhere in it,
    templates included, and the ones a device trigger or action names by registry id."""
    text = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    found = [m.group(0) for m in _ENTITY_RE.finditer(text) if hass.states.get(m.group(0))]
    found += [eid for eid, _name in registry_entities(hass, text)]
    return list(dict.fromkeys(found))


def card_for_config(hass: HomeAssistant, config: Any, title: str) -> dict:
    """[ADDED v3.63.0] A dashboard card for any net, from what LIBI compiles for it: the settings it reads and the
    devices it switches. The card from the AI chat was gone once the chat was, and a net built by hand never had
    one. Read only; the user pastes it into a dashboard."""
    return _card(hass, config_entities(hass, config), title, config_days(config), need_settings=False,
                 day_bits=config_day_bits(config), enable=config_enable(config))


_CARD_SERVICE_KEYS = ("perform_action", "service")


def _clean_card(draft: _Draft, card: Any, depth: int = 0) -> Any:
    """A Lovelace card: built-in types only, entities as the user's picks, and any service a tap
    would call held to the same rules as the automation."""
    if depth > 8:
        draft.err("The card is nested too deeply.")
        return {}
    if isinstance(card, dict):
        out = {}
        for k, v in card.items():
            k = str(k)
            if k in ("device_id", "area_id"):
                draft.err(f"'{k}' is not allowed in an AI card.")
                continue
            if k in ("label", "name", "title", "icon") and isinstance(v, str):
                out[k] = v[:80]
                continue
            # [CHANGED v3.76.0] Except LIBI's own row of the days, which LIBI loads on every dashboard.
            if k == "type" and isinstance(v, str) and v.startswith("custom:") and v != DAYS_ROW_TYPE:
                draft.err(f"The card type {v} is a custom card, which may not be installed.")
            if k in ("entity", "entities", "entity_id") and not isinstance(v, dict):
                if isinstance(v, list):
                    out[k] = [(_clean_card(draft, item, depth + 1) if isinstance(item, dict)
                               else draft.entity_list(item)) for item in v]
                    out[k] = [x[0] if isinstance(x, list) and len(x) == 1 else x for x in out[k]]
                    flat = []
                    for x in out[k]:
                        flat.extend(x if isinstance(x, list) else [x])
                    out[k] = flat
                else:
                    ids = draft.entity_list(v)
                    out[k] = ids[0] if len(ids) == 1 else ids
            elif k in _CARD_SERVICE_KEYS and isinstance(v, str):
                out[k] = draft.service(v, (card.get("target") and {"target": card["target"]}) or card)
            else:
                out[k] = _clean_card(draft, v, depth + 1)
        return out
    if isinstance(card, list):
        return [_clean_card(draft, v, depth + 1) for v in card]
    if isinstance(card, str):
        return draft._text(card)
    return card


# [ADDED v3.80.0] ------------------------------------------------------------- the questions LIBI asks itself
# The user (2026-11-01), of a watering the chat built without asking: "things I would expect it to ask me - whether to add
# an enable button for the whole automation, what to do when the valve's battery runs out and it is offline, and a
# message when the battery is almost empty". The plan told the model to ask only what it really needs, and it asked none
# of them. LIBI asks them itself whenever an automation switches a device - in its own words, in English and the same
# every time (the user's choice) - and reads the answer by its own choices, never by the model's. The build is told what
# each answer means, written exactly so (safety_context), and LIBI checks the draft for it (safety_report).
ENABLE_QUESTION = "libi_enable"
# [ADDED v3.81.0] A message when the process starts and when it ends - the user: "always ask whether you want a message
# at the end or the start of the process, spoken or a notification".
START_QUESTION = "libi_start_message"
END_QUESTION = "libi_end_message"
OFFLINE_QUESTION = "libi_offline"
BATTERY_QUESTION = "libi_battery"
SAFETY_QUESTIONS = (ENABLE_QUESTION, START_QUESTION, END_QUESTION, OFFLINE_QUESTION, BATTERY_QUESTION)
_MESSAGE_CHOICES = {"notify": "A notification", "speak": "Spoken", "both": "Notification and spoken", "no": "No"}
SAFETY_CHOICES: dict[str, dict[str, str]] = {
    ENABLE_QUESTION: {"yes": "Yes", "no": "No"},
    START_QUESTION: dict(_MESSAGE_CHOICES),
    END_QUESTION: dict(_MESSAGE_CHOICES),
    OFFLINE_QUESTION: {"tell": "Tell me, and do not start", "skip": "Do not start, no message", "nothing": "Nothing"},
    BATTERY_QUESTION: {"20": "Yes, below 20%", "10": "Yes, below 10%", "no": "No"},
}
# [ADDED v3.81.0] The state a device is in once the process is over: off - or closed, or locked.
_OFF_STATE = {"valve": "closed", "cover": "closed", "lock": "locked"}
# The role of the switch, and the one of the batteries LIBI finds on the devices the user picked.
ENABLE_ROLE = "enabled"
BATTERY_ROLE = "batteries"
MAX_BATTERIES = 8
# How long a device is unavailable before the message says it is offline: not the moment of a reload or a restart.
OFFLINE_MINUTES = 10
# A device the logic switches - what may be offline when it is to be switched; and what else may run on a battery that
# matters to the logic: the button that starts it, the sensor it reads.
SWITCHED_DOMAINS = set(CARD_DEVICE_DOMAINS) | SENSITIVE_DOMAINS
BATTERY_DEVICE_DOMAINS = SWITCHED_DOMAINS | {"sensor", "binary_sensor", "event", "button"}
_ON_SERVICES = ("turn_on", "open_valve", "open_cover")
_OFF_SERVICES = ("turn_off", "close_valve", "close_cover")


def _switched_roles(plan: dict) -> list[dict]:
    """[ADDED v3.80.0] The roles of the devices the logic switches: its targets of a device domain."""
    return [r for r in plan.get("roles") or [] if r.get("purpose") == "target" and r["id"] != PHONES_ROLE
            and set(r.get("domains") or []) & SWITCHED_DOMAINS]


def _battery_roles(plan: dict) -> list[dict]:
    """[ADDED v3.80.0] The roles whose devices may run on a battery that matters to the logic: what it switches, what
    starts it, what it reads - not a setting, a phone or the weather."""
    return [r for r in plan.get("roles") or [] if r["id"] not in (PHONES_ROLE, BATTERY_ROLE)
            and set(r.get("domains") or []) & BATTERY_DEVICE_DOMAINS]


def _likely_picks(roles: list[dict], candidates: dict, preselect: dict) -> list[str]:
    """[ADDED v3.80.0] What the user will most likely pick in these roles before they pick: what is ticked for them, or
    else the exact matches LIBI found (the first five of each)."""
    out: list[str] = []
    for role in roles:
        picks = list(preselect.get(role["id"]) or [])
        cand = candidates.get(role["id"]) or {}
        if not picks and cand.get("exact"):
            picks = [i["entity_id"] for i in cand.get("items") or []][:5]
        out += picks
    return list(dict.fromkeys(out))


@callback
def battery_sensors(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """[ADDED v3.80.0] [RULE 8] The batteries of the devices these entities belong to, found in the registries and never
    named by the model: a sensor in % of the device class battery on the same device, not disabled. A phone's battery
    is the Companion app's, not the logic's."""
    ent_reg = er.async_get(hass)
    devices: list[str] = []
    for eid in entity_ids:
        entry = ent_reg.async_get(eid)
        if entry is not None and entry.device_id and entry.platform != "mobile_app" and entry.device_id not in devices:
            devices.append(entry.device_id)
    found: list[str] = []
    for device_id in devices:
        for entry in er.async_entries_for_device(ent_reg, device_id):
            state = hass.states.get(entry.entity_id)
            if entry.domain != "sensor" or state is None:
                continue
            dclass = state.attributes.get("device_class") or entry.device_class or entry.original_device_class
            if dclass == "battery" and state.attributes.get("unit_of_measurement") == "%":
                found.append(entry.entity_id)
    return list(dict.fromkeys(found))[:MAX_BATTERIES]


def _join(names: list[str], limit: int = 3) -> str:
    """[ADDED v3.80.0] Names as a question says them: "A", "A and B", "A, B and C", "A, B, C and 2 more"."""
    shown, rest = names[:limit], len(names) - limit
    if rest > 0:
        return f"{', '.join(shown)} and {rest} more"
    return " and ".join([", ".join(shown[:-1]), shown[-1]]) if len(shown) > 1 else (shown[0] if shown else "")


@callback
def _device_names(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """[ADDED v3.80.0] The devices of these entities, each once, by the name the user gave it - else the entity's."""
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    names: list[str] = []
    for eid in entity_ids:
        entry = ent_reg.async_get(eid)
        device = dev_reg.async_get(entry.device_id) if entry is not None and entry.device_id else None
        state = hass.states.get(eid)
        name = _sanitize(str((device.name_by_user or device.name) if device else (state.name if state else eid)))[:40]
        if name and name not in names:
            names.append(name)
    return names


@callback
def _switched_names(hass: HomeAssistant, plan: dict, candidates: dict, preselect: dict) -> list[str]:
    """[ADDED v3.80.0] What the offline question names, before the user picks: the device of each switched role - what is
    ticked, or the one device all its exact matches belong to (the user's valve has two switches) - else the role's own
    label, rather than devices the user may not pick."""
    ent_reg = er.async_get(hass)
    names: list[str] = []
    for role in _switched_roles(plan):
        picks = list(preselect.get(role["id"]) or [])
        if not picks:
            cand = candidates.get(role["id"]) or {}
            found = [i["entity_id"] for i in cand.get("items") or []] if cand.get("exact") else []
            owners = {getattr(ent_reg.async_get(e), "device_id", None) or e for e in found}
            picks = found if len(owners) == 1 else []
        for name in _device_names(hass, picks) if picks else [_sanitize(str(role.get("label") or role["id"]))[:40]]:
            if name and name not in names:
                names.append(name)
    return names


def _one(value: Any) -> Any:
    """[ADDED v3.80.0] A list of one value is that value, as Home Assistant takes it in a state's to or state."""
    return value[0] if isinstance(value, list) and len(value) == 1 else value


def _state_is(value: Any, state: str) -> bool:
    """[ADDED v3.80.0] A state written as on / off, in quotes or as the boolean YAML reads an unquoted on as."""
    value = _one(value)
    if isinstance(value, bool):
        return value is (state == "on") and state in ("on", "off")
    return str(value).lower() == state


def config_enable(config: Any) -> set[str]:
    """[ADDED v3.80.0] The on/off switch of a configuration, as LIBI writes the user's enable (safety_context): an
    input_boolean that a condition checks to be on, with a trigger of it turning off."""
    checked: set[str] = set()
    off: set[str] = set()
    for node in _walk_nodes(config):
        ids = [e for e in _ids_in(node) if e.startswith("input_boolean.")]
        if node.get("condition") == "state" and _state_is(node.get("state"), "on"):
            checked.update(ids)
        if node.get("trigger") == "state" and _state_is(node.get("to"), "off"):
            off.update(ids)
    return checked & off


def config_offline(config: Any, entity_ids: list[str]) -> bool:
    """[ADDED v3.80.0] A configuration that already reacts to one of these devices going offline."""
    wanted = set(entity_ids)
    return any(node.get("trigger") == "state" and _state_is(node.get("to"), "unavailable") and wanted & set(_ids_in(node))
               for node in _walk_nodes(config))


def config_battery(config: Any, sensors: list[str]) -> bool:
    """[ADDED v3.80.0] A configuration that already reacts to one of these batteries running low."""
    wanted = set(sensors)
    return any(node.get("trigger") == "numeric_state" and node.get("below") is not None and wanted & set(_ids_in(node))
               for node in _walk_nodes(config))


def _off_state(entity_id: str) -> str:
    """[ADDED v3.81.0] The state of a device once the process is over."""
    return _OFF_STATE.get(str(entity_id).split(".")[0], "off")


def _end_triggers(auto: dict, entity_id: str) -> set[str]:
    """[ADDED v3.81.0] The ids of the triggers of a device turning off (closed, locked)."""
    off = _off_state(entity_id)
    return _triggers_of(auto, entity_id, "state", lambda t: _state_is(t.get("to"), off))


def config_start_message(config: Any, entity_ids: list[str]) -> bool:
    """[ADDED v3.81.0] A configuration that already sends a message after it turns one of these devices on."""
    auto = config if isinstance(config, dict) else {}
    return any(_switches(s, entity_ids, _ON_SERVICES) and _sends(o["steps"][i + 1:])
               for o in _options(auto) for i, s in enumerate(o["steps"]))


def config_end_message(config: Any, entity_ids: list[str]) -> bool:
    """[ADDED v3.81.0] A configuration that already sends a message when one of these devices turns off."""
    auto = config if isinstance(config, dict) else {}
    ids = set().union(*(_end_triggers(auto, e) for e in entity_ids)) if entity_ids else set()
    return any(o["ids"] & ids and _sends(o["steps"]) for o in _options(auto))


@callback
def phones_that_speak(hass: HomeAssistant) -> set[str]:
    """[ADDED v3.81.0] The notify services of the phones that read a message aloud: the Home Assistant app on Android
    speaks a message "TTS" (its data.tts_text); on an iPhone it would show the word. Read from the app's config entry, as
    phone_owners reads it - never its webhook or secret."""
    ent_reg = er.async_get(hass)
    out: set[str] = set()
    for eid, service in phone_services(hass).items():
        entry = ent_reg.async_get(eid)
        config_entry = hass.config_entries.async_get_entry(entry.config_entry_id) if entry and entry.config_entry_id else None
        if str((config_entry.data if config_entry else {}).get("os_name") or "").lower().startswith("android"):
            out.add(service)
    return out


@callback
def phone_list(hass: HomeAssistant) -> list[dict[str, Any]]:
    """[ADDED v3.87.0] The phones for the panel's MOVE NOTIFY / TTS block: each phone's notify entity, the action that
    sends to it, its name in Home Assistant, whose it is and what it is (phone_owners), and whether it reads a message
    aloud. Picking a phone writes its action. The entity picker the block had listed each phone by its notify entity,
    which went into the automation as its action, and Home Assistant could not call it: the user's train reminder said
    nothing at its time (2026-11-04). Two phones the Companion app registered under one device name share one action,
    and it reaches only one of them: both are marked shared, and the panel picks neither. Read from the app's config
    entries in memory, as phone_owners reads them - never a webhook id or a secret."""
    services = phone_services(hass)
    owners = phone_owners(hass)
    speak = phones_that_speak(hass)
    uses: dict[str, int] = {}
    for service in services.values():
        uses[service] = uses.get(service, 0) + 1
    out: list[dict[str, Any]] = []
    for eid, service in services.items():
        state = hass.states.get(eid)
        owner = owners.get(eid, {})
        out.append({"entity_id": eid, "service": service, "name": str(state.name if state else eid)[:100],
                    "owner": owner.get("owner", ""), "device": owner.get("device", ""),
                    "speaks": service in speak, "shared": uses[service] > 1})
    return sorted(out, key=lambda p: (p["name"].lower(), p["entity_id"]))


_NOTIFY_ACTION_RE = re.compile(r"notify\.([a-z0-9_]+)")


@callback
def notify_action_problems(hass: HomeAssistant, domain: str, config: dict) -> list[str]:
    """[ADDED v3.87.0] The notify actions of an automation or a script that Home Assistant does not have. Home Assistant
    saves such an action and fails only when it runs: the user's train reminder had a phone's notify entity
    (notify.sm_s918b) as its action, was saved without a word, and said nothing at its time (2026-11-04). SAVE & COMPILE
    sends no entry that has one. Only notify: a phone's notify entity and its action share that domain, and a phone that
    leaves the Companion app takes its action with it.
    [CHANGED v3.88.0] And a recipient of LIBI Global that is not in Home Assistant: deleted, or not loaded."""
    if domain == "automation":
        steps = config.get("actions", config.get("action"))
    elif domain == "script":
        steps = config.get("sequence")
    else:
        return []
    found = called_actions(steps)
    phones = phone_services(hass)
    problems: list[str] = []
    for name in dict.fromkeys(found):
        if is_recipient_action(name):
            if not hass.services.has_service("script", name.split(".", 1)[1]):
                problems.append(f"{name} is a recipient of LIBI Global that Home Assistant does not have: nothing would "
                                "be sent. Pick another one in the MOVE block, or make it again in LIBI ▸ Global.")
            continue
        m = _NOTIFY_ACTION_RE.fullmatch(name)
        if not m or hass.services.has_service("notify", m.group(1)):
            continue
        service = phones.get(name)
        if service and list(phones.values()).count(service) == 1:
            state = hass.states.get(name)
            problems.append(f"{name} is the notify entity of the phone {state.name if state else name}, not an action: "
                            f"Home Assistant cannot send with it. The phone's action is {service} - pick the phone "
                            "again in the MOVE block.")
        elif service:
            problems.append(f"{name} is the notify entity of a phone, not an action, and another phone is registered "
                            f"under the same name in the Companion app: their one action, {service}, reaches only one "
                            "of them. Give one of the phones another name in the app.")
        else:
            problems.append(f"{name} is not an action in this Home Assistant - a phone no longer registered in the "
                            "Companion app? Nothing would be sent.")
    return problems


@callback
def offer_phones(hass: HomeAssistant, plan: dict, candidates: dict) -> bool:
    """[ADDED v3.81.0] LIBI's list of phones for its own messages, when the plan has none - as phones_role offers it, but
    optional: with none ticked a message goes to Home Assistant's notifications. False when there is no phone to offer."""
    if len(plan["roles"]) >= MAX_ROLES:
        return False
    services = phone_services(hass)
    items = [i for i in find_candidates(hass, {"domains": ["notify"], "keywords": [], "area_keywords": [],
                                               "device_classes": []})["items"] if i["entity_id"] in services]
    if not items:
        return False
    owners = phone_owners(hass)
    plan["roles"].insert(0, {"id": PHONES_ROLE, "label": "Phones to notify", "purpose": "target", "domains": ["notify"],
                             "device_classes": [], "keywords": [], "area_keywords": [], "optional": True,
                             "named": False, "phones": True, "offered": True})
    candidates[PHONES_ROLE] = {"items": [dict(i, **owners.get(i["entity_id"], {})) for i in items], "exact": True}
    return True


def _question(qid: str, text: str, note: str, adds: dict | None = None) -> dict:
    """[ADDED v3.80.0] One of LIBI's questions as the chat shows it: LIBI's own choices only, no answer of the user's own
    words (libi), and what a yes adds to the plan."""
    question = {"id": qid, "text": text[:300], "choices": list(SAFETY_CHOICES[qid].values()), "libi": True,
                "note": note[:400]}
    if adds:
        question["adds"], question["yes"] = adds, [SAFETY_CHOICES[qid]["yes"]]
    return question


@callback
def _enable_question(hass: HomeAssistant, plan: dict, config_text: str, keep: set[str] | None) -> dict:
    """[ADDED v3.80.0] The on/off switch, offered with what a yes adds: its role, and a helper named after the logic
    ("<name> - enabled") - or, when one of that name exists that nothing uses, that one, offered first in the role. The
    user's other switches that nothing else uses can be picked instead.
    [CHANGED v3.82.0] A local variable like the others: the helper to make always comes with it, under a name of its own,
    and a free switch LIBI made for an automation before ("<name> - enabled", nothing uses it) is the one it starts with
    ("pick") - the user: "if a variable is free, choose it instead of creating a new one"."""
    base = str(plan.get("name") or "").strip()[:48] or "Automation"
    role = {"id": ENABLE_ROLE, "label": "On/off switch", "purpose": "condition", "domains": ["input_boolean"],
            "device_classes": [], "keywords": [], "area_keywords": [], "optional": False, "named": False,
            "variable": True}
    found = find_candidates(hass, {"domains": ["input_boolean"], "keywords": [base], "area_keywords": [],
                                   "device_classes": []})
    drop_used_helpers(hass, {ENABLE_ROLE: found}, config_text, keep)
    fits = [i for i in found["items"] if str(i.get("name") or "").endswith(" - enabled")]
    for item in fits:
        item["exists"] = True
    if fits:
        found["items"] = fits + [i for i in found["items"] if i not in fits]
        found["exact"] = True
    own = next((i for i in fits if _norm(i.get("name")) == _norm(f"{base} - enabled")), fits[0] if fits else None)
    helper = {"role": ENABLE_ROLE, "domain": "input_boolean", "settings": {"icon": "mdi:power"},
              "name": _unique_name(hass, "input_boolean", f"{base} - enabled")}
    if own:
        helper["pick"] = own["entity_id"]
    return _question(ENABLE_QUESTION, "An on/off switch for the whole automation, on the card?",
                     "Off stops it at once - what it turned on is turned off - and nothing starts until it is on again. "
                     "What turns things off never waits for it. A new switch starts off: turn it on on the card. It is "
                     "one of the local variables above.",
                     {"role": role, "helper": helper, "candidates": found})


@callback
def safety_questions(hass: HomeAssistant, plan: dict, candidates: dict, preselect: dict, net_yaml: str = "",
                     config_text: str = "", keep: set[str] | None = None) -> None:
    """[ADDED v3.80.0] LIBI's own questions, after the model's: an on/off switch for the whole automation, what to do
    when a device it switches is offline, and a message when a battery of its devices runs low - asked whenever an
    automation switches a device, and not for what the net being changed does already. A question of the model's under
    one of LIBI's ids goes, and so does a switch the model planned itself: LIBI asks for it. A yes to the switch adds
    its role and its helper in the chat (adds); the batteries are found again at the build, on the devices the user
    picked (safety_answers)."""
    plan["questions"] = [q for q in plan.get("questions") or [] if q.get("id") not in SAFETY_QUESTIONS]
    if plan.get("intent") == "answer" or plan.get("level") != "automation":
        return
    switched = _likely_picks(_switched_roles(plan), candidates, preselect)
    if not switched:
        return
    current = _yaml_mapping(net_yaml) if net_yaml else {}
    # Not when the model planned a battery itself: the user asked for one.
    planned = any("battery" in (r.get("device_classes") or []) for r in plan["roles"])
    batteries = [] if planned else battery_sensors(hass, _likely_picks(_battery_roles(plan), candidates, preselect))
    on_battery = bool(battery_sensors(hass, switched))
    asked: list[dict] = []
    if not config_enable(current):
        if any(r["id"] == ENABLE_ROLE for r in plan["roles"]):
            plan["roles"] = [r for r in plan["roles"] if r["id"] != ENABLE_ROLE]
            plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] != ENABLE_ROLE]
            candidates.pop(ENABLE_ROLE, None)
        if len(plan["roles"]) < MAX_ROLES:
            asked.append(_enable_question(hass, plan, config_text, keep))
    names = _switched_names(hass, plan, candidates, preselect)
    # [ADDED v3.81.0] A message when it starts and when it ends, always asked. The phones they go to: the plan's, or
    # LIBI's list of them, optional.
    phones = any(r["id"] == PHONES_ROLE or (r.get("domains") and set(r["domains"]) <= MESSAGE_DOMAINS)
                 for r in plan["roles"]) or offer_phones(hass, plan, candidates)
    where = ("It goes to the phones picked in this plan. Spoken: the phone reads it aloud - the Home Assistant app on "
             "Android." if phones else "No phone with the Home Assistant app is set up here: a notification goes to Home "
             "Assistant's notifications, and nothing can be spoken.")
    if not config_start_message(current, switched):
        asked.append(_question(START_QUESTION, f"A message when it starts - when it turns {_join(names)} on?", where))
    if not config_end_message(current, switched):
        asked.append(_question(END_QUESTION, f"A message when it ends - when {_join(names)} "
                                             f"{'turns' if len(names) == 1 else 'turn'} off, whatever turned it off?",
                               where))
    if not config_offline(current, switched):
        asked.append(_question(
            OFFLINE_QUESTION, f"What if {_join(names)} {'is' if len(names) == 1 else 'are'} offline (unavailable) - "
                              f"{'its battery ran out' if on_battery else 'no power or no network'}, for example?",
            "Home Assistant skips a device that is offline - it only writes a warning in its log - so the logic would go "
            "on as if it had switched it."
            + (" A device on a battery is marked offline only when it has not been heard from for a while - with ZHA "
               "6 hours by default - so a low battery is usually told first." if on_battery else "")))
    if batteries and not config_battery(current, batteries):
        levels = ", ".join(f"{_join(_device_names(hass, [s]))} {_level(hass, s)}" for s in batteries[:3])
        asked.append(_question(BATTERY_QUESTION, f"A message when a battery is low? Now: {levels}.",
                               "LIBI found the battery on the device itself; the message names the battery and its level."))
    plan["questions"] += asked


def _level(hass: HomeAssistant, entity_id: str) -> str:
    """[ADDED v3.80.0] A battery's level as a question shows it: "87%", or "?" while it has none."""
    state = hass.states.get(entity_id)
    try:
        return f"{float(state.state):g}%"
    except (AttributeError, TypeError, ValueError):
        return "?"


def drop_declined(plan: dict, answers: dict) -> None:
    """[ADDED v3.80.0] The switch the user did not say yes to is no role of the logic, and no pick is asked for it: the
    chat takes it out on a no, and LIBI does when the plan comes back with it all the same."""
    asked = {q["id"] for q in plan.get("questions") or []}
    if ENABLE_QUESTION in asked and answers.get(ENABLE_QUESTION) != SAFETY_CHOICES[ENABLE_QUESTION]["yes"]:
        plan["roles"] = [r for r in plan["roles"] if r["id"] != ENABLE_ROLE]


@callback
def safety_answers(hass: HomeAssistant, plan: dict, selections: dict, answers: dict,
                   services: list[str] | None = None) -> dict:
    """[ADDED v3.80.0] What the user answered to LIBI's own questions, read by LIBI's own choices: the switch picked for
    its role, the devices the logic switches with what to do when one is offline, and the batteries of the devices
    picked with the level a message is sent below. A switch the user said no to goes out of the logic; the batteries
    become a role LIBI fills itself, from the registries (RULE 8) - the model is told only of them. Each part is empty
    when it was not asked or not answered; notes say why a yes could not be kept.
    [CHANGED v3.81.0] And the messages when it starts and when it ends, with the phones they go to - the ones ticked and
    the notify services the user named (services) - and the ones of them that speak."""
    asked = {q["id"] for q in plan.get("questions") or []}
    choice = {qid: next((key for key, text in SAFETY_CHOICES[qid].items() if answers.get(qid) == text), "")
              for qid in SAFETY_QUESTIONS}
    out: dict[str, Any] = {"enable": "", "start": "", "end": "", "phones": [], "speakers": [], "offline": "",
                           "switched": {}, "names": "", "battery": 0, "batteries": [], "notes": []}
    picks = [e for e in selections.get(ENABLE_ROLE) or [] if e.split(".")[0] == "input_boolean"]
    if choice[ENABLE_QUESTION] == "yes" and len(picks) == 1:
        out["enable"] = picks[0]
    elif ENABLE_QUESTION in asked:
        if choice[ENABLE_QUESTION] == "yes":
            out["notes"].append("The on/off switch needs exactly one helper, so it was left out.")
        selections.pop(ENABLE_ROLE, None)
        plan["roles"] = [r for r in plan["roles"] if r["id"] != ENABLE_ROLE]
    switched = {r["id"]: [e for e in selections.get(r["id"]) or [] if e.split(".")[0] in SWITCHED_DOMAINS]
                for r in _switched_roles(plan)}
    out["switched"] = {rid: ids for rid, ids in switched.items() if ids}
    out["names"] = ", ".join(dict.fromkeys(_sanitize(hass.states.get(e).name)[:40] for ids in out["switched"].values()
                                           for e in ids if hass.states.get(e)))[:120]
    if choice[OFFLINE_QUESTION] in ("tell", "skip") and out["switched"]:
        out["offline"] = choice[OFFLINE_QUESTION]
    known = phone_services(hass)
    ticked = [known[e] for e in selections.get(PHONES_ROLE) or [] if e in known]
    # [CHANGED v3.81.1] With phones ticked, a phone the message names is a phone only when it is ticked: the user's ticks
    # win (build_context says so). A named service that is no phone (a group) still gets the message.
    named = [s for s in services or [] if not (ticked and s in set(known.values()))]
    out["phones"] = list(dict.fromkeys(ticked + named))
    speak = phones_that_speak(hass)
    out["speakers"] = [s for s in out["phones"] if s in speak]
    for qid, key in ((START_QUESTION, "start"), (END_QUESTION, "end")):
        kind = choice[qid] if choice[qid] in ("notify", "speak", "both") and out["switched"] else ""
        if kind in ("speak", "both") and not out["speakers"]:
            out["notes"].append(f"No phone picked reads a message aloud (the Home Assistant app on Android), so the "
                                f"message when it {'starts' if key == 'start' else 'ends'} is a notification.")
            kind = "notify"
        out[key] = kind
    if choice[BATTERY_QUESTION] in ("20", "10"):
        sensors = battery_sensors(hass, [e for r in _battery_roles(plan) for e in selections.get(r["id"]) or []])
        if not sensors:
            out["notes"].append("No battery was found on the devices you picked, so no message tells of a low battery.")
        elif not any(r["id"] == BATTERY_ROLE for r in plan["roles"]) and len(plan["roles"]) < MAX_ROLES:
            plan["roles"].append({"id": BATTERY_ROLE, "label": "Batteries", "purpose": "measure", "domains": ["sensor"],
                                  "device_classes": ["battery"], "keywords": [], "area_keywords": [],
                                  "optional": False, "named": False, "filled": True})
            selections[BATTERY_ROLE] = sensors
            out["battery"], out["batteries"] = int(choice[BATTERY_QUESTION]), sensors
    return out


@callback
def filled_candidates(hass: HomeAssistant, entity_ids: list[str]) -> dict:
    """[ADDED v3.80.0] A role LIBI fills itself, as the build's list of devices shows it: only what LIBI put in it - not
    every battery of the house."""
    items = []
    for eid in entity_ids:
        state = hass.states.get(eid)
        if state is not None:
            items.append({"entity_id": eid, "name": state.name, "area": "",
                          "device_class": state.attributes.get("device_class") or "", "state": state.state})
    return {"items": items, "exact": True}


def safety_context(safety: dict | None) -> list[str]:
    """[ADDED v3.80.0] What the user's answers to LIBI's own questions mean for the logic, each written exactly so - as
    the alarm clock is. Every one is a rung of its own or a check in the start option, of the palette's blocks only."""
    safety = safety or {}
    lines: list[str] = []
    if safety.get("enable"):
        lines.append(
            f'ON/OFF SWITCH (role:{ENABLE_ROLE}, set on the card) - an enable: the start option checks it right after its '
            f'trigger, exactly so: {{"condition": "state", "entity_id": "role:{ENABLE_ROLE}", "state": "on"}}. Turning it '
            f'off stops a run at once: a trigger {{"trigger": "state", "entity_id": "role:{ENABLE_ROLE}", "to": "off", '
            '"id": "switched_off"} with an option of its own that turns off what the start turns on. No other option '
            "checks it - the amount reached, the time limit and a restart turn things off whatever it is - and it is "
            "never in the conditions of the automation itself, which hold for every trigger.")
    switched = safety.get("switched") or {}
    if safety.get("start") and switched:
        lines.append(f"START MESSAGE (the user's answer): in the start option, right after the step that turns "
                     f"{', '.join(f'role:{rid}' for rid in switched)} on - "
                     f"{_message_how(safety['start'], safety.get('phones') or [], safety.get('speakers') or [])}.")
    if safety.get("end"):
        for rid, ids in switched.items():
            ended = json.dumps({"trigger": "state", "entity_id": f"role:{rid}", "not_from": ["unavailable", "unknown"],
                                "to": _off_state(ids[0]), "id": f"{rid[:30]}_ended"})
            lines.append(f"END MESSAGE (role:{rid}): a trigger {ended} with an option of its own - "
                         f"{_message_how(safety['end'], safety.get('phones') or [], safety.get('speakers') or [])}. "
                         'The automation\'s mode is then "queued": the option that turns it off is still running when it '
                         "turns off, and in mode single Home Assistant would drop the message.")
    if safety.get("offline"):
        for rid, ids in (safety.get("switched") or {}).items():
            match = ', "match": "any"' if len(ids) > 1 else ""
            line = (f'OFFLINE (role:{rid}): while it is offline the start option does not switch it - it checks right after '
                    f'its trigger, exactly so: {{"condition": "not", "conditions": [{{"condition": "state", "entity_id": '
                    f'"role:{rid}", "state": "unavailable"{match}}}]}}.')
            if safety["offline"] == "tell":
                line += (f' And a trigger {{"trigger": "state", "entity_id": "role:{rid}", "to": "unavailable", "for": '
                         f'{{"minutes": {OFFLINE_MINUTES}}}, "id": "{rid[:30]}_offline"}} with an option of its own that '
                         "sends a message: it is offline, and its battery may be empty.")
            lines.append(line)
    if safety.get("battery"):
        lines.append(
            f'LOW BATTERY (role:{BATTERY_ROLE}, found by LIBI on the devices picked): a trigger {{"trigger": '
            f'"numeric_state", "entity_id": "role:{BATTERY_ROLE}", "below": {int(safety["battery"])}, "id": "battery_low"}} '
            "with an option of its own that sends a message with the battery and its level, e.g. "
            '"{{ trigger.to_state.name }}: {{ trigger.to_state.state }}%".')
    if lines:
        lines.append("These messages go where the other messages of this logic go: to every phone under PHONES, or to "
                     "the notify services the user named - and when there are none, with persistent_notification.create.")
    return lines


def _message_how(kind: str, phones: list[str], speakers: list[str]) -> str:
    """[ADDED v3.81.0] How a message of LIBI's questions is written: a notification to every phone, its text spoken by the
    phones that speak (the others get the notification), or both - a notification and right after it its spoken twin,
    which the ladder draws as one MOVE NOTIFY/TTS. Without a phone, Home Assistant's own notification."""
    notice = '{"action": "<service>", "data": {"message": "<the text>"}}'
    spoken = '{"action": "<service>", "data": {"message": "TTS", "data": {"tts_text": "<the text>"}}}'
    quiet = [p for p in phones if p not in speakers]
    if not phones:
        return 'a notification: {"action": "persistent_notification.create", "data": {"message": "<the text>"}}'
    if kind == "speak":
        return (f"the text spoken by each of {', '.join(speakers)}: {spoken}"
                + (f"; to {', '.join(quiet)}, which cannot speak, a notification: {notice}" if quiet else ""))
    if kind == "both" and speakers:
        return (f"to each of {', '.join(phones)} a notification, {notice}, and right after it, to each of "
                f"{', '.join(speakers)}, the same text spoken: {spoken} - one phone after the other")
    return f"a notification to each of {', '.join(phones)}: {notice}"


def _is_spoken(step: dict) -> bool:
    """[ADDED v3.81.0] A message the phone reads aloud: "TTS", with its text in data.tts_text."""
    data = step.get("data") if isinstance(step.get("data"), dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    return str(data.get("message", "")).strip().upper() == "TTS" or bool(inner.get("tts_text"))


def _wanted_messages(kind: str, phones: list[str], speakers: list[str]) -> list[tuple[str, bool]]:
    """[ADDED v3.81.0] The messages an answer asks for: (service, spoken) - as _message_how writes them."""
    if not phones:
        return [("persistent_notification.create", False)]
    out = []
    for phone in phones:
        if kind in ("notify", "both") or phone not in speakers:
            out.append((phone, False))
        if kind in ("speak", "both") and phone in speakers:
            out.append((phone, True))
    return out


def _unsent(steps: list, wanted: list[tuple[str, bool]]) -> list[str]:
    """[ADDED v3.81.0] The messages of wanted that these steps do not send."""
    return [f"{'the spoken message to ' if spoken else ''}{service}" for service, spoken in wanted
            if not any(isinstance(s, dict) and s.get("action") == service and _is_spoken(s) == spoken for s in steps)]


def _options(auto: dict) -> list[dict]:
    """[ADDED v3.80.0] The rungs of an automation as Home Assistant runs them: each option of a top-level choose, with
    the trigger ids its first condition names, its other conditions and its steps; the other top-level steps run for
    every trigger. A trigger with no id is "" here."""
    ids = {str(t.get("id")) if t.get("id") is not None else "" for t in auto.get("triggers") or [] if isinstance(t, dict)}
    ids = ids or {""}
    out: list[dict] = []
    plain: list = []
    for step in auto.get("actions") or []:
        options = step.get("choose") if isinstance(step, dict) else None
        if not isinstance(options, list):
            plain.append(step)
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            conds = option.get("conditions")
            conds = conds if isinstance(conds, list) else ([conds] if conds else [])
            first = conds[0] if conds else None
            steps = option.get("sequence") if isinstance(option.get("sequence"), list) else []
            if isinstance(first, dict) and first.get("condition") == "trigger":
                named = first.get("id") if isinstance(first.get("id"), list) else [first.get("id")]
                out.append({"ids": {str(i) for i in named}, "conditions": conds[1:], "steps": steps})
            else:
                out.append({"ids": set(ids), "conditions": conds, "steps": steps})
    if plain:
        out.append({"ids": set(ids), "conditions": [], "steps": plain})
    return out


def _leaves(conditions: Any):
    """[ADDED v3.80.0] The checks that must all hold: the conditions given and those of an and among them - never what is
    inside an or or a not."""
    for cond in conditions if isinstance(conditions, list) else [conditions]:
        if not isinstance(cond, dict):
            continue
        if cond.get("condition") == "and" or "and" in cond:
            yield from _leaves(cond.get("conditions") if cond.get("condition") == "and" else cond.get("and"))
        else:
            yield cond


def _checks_before(auto: dict, option: dict, index: int) -> list[dict]:
    """[ADDED v3.80.0] What must hold before the step at index of an option runs: the automation's conditions, the
    option's, and the condition steps before it."""
    steps = [s for s in option["steps"][:index] if isinstance(s, dict) and "condition" in s]
    return list(_leaves(list(auto.get("conditions") or []) + list(option["conditions"]) + steps))


def _switches(step: Any, entities: list[str], services: tuple[str, ...]) -> bool:
    """[ADDED v3.80.0] A step that switches one of these entities with one of these services (turn_on, open_valve ...)."""
    if not isinstance(step, dict):
        return False
    action = str(step.get("action") or step.get("service") or "")
    return action.split(".")[-1] in services and bool(set(map(str, _targets(step))) & set(entities))


def _sends(steps: list) -> bool:
    """[ADDED v3.80.0] Steps that send a message or speak."""
    return any(isinstance(s, dict) and (str(s.get("action") or "").split(".")[0] in MESSAGE_DOMAINS
                                         or s.get("action") in MESSAGE_SERVICES) for s in steps)


def _triggers_of(auto: dict, entity: str, kind: str, test) -> set[str]:
    """[ADDED v3.80.0] The ids of the triggers of a kind on an entity that pass the test ("" for one with no id)."""
    return {str(t.get("id")) if t.get("id") is not None else "" for t in auto.get("triggers") or []
            if isinstance(t, dict) and t.get("trigger") == kind and entity in _ids_in(t) and test(t)}


def _is_on_check(cond: dict, entity: str) -> bool:
    return cond.get("condition") == "state" and entity in _ids_in(cond) and _state_is(cond.get("state"), "on")


def _is_online_check(cond: dict, entity: str) -> bool:
    """[ADDED v3.80.0] A check that a device is online: not unavailable (as safety_context writes it), or off."""
    if cond.get("condition") == "not" or "not" in cond:
        inner = cond.get("conditions") if cond.get("condition") == "not" else cond.get("not")
        return any(n.get("condition") == "state" and entity in _ids_in(n) and _state_is(n.get("state"), "unavailable")
                   for n in _leaves(inner))
    return cond.get("condition") == "state" and entity in _ids_in(cond) and _state_is(cond.get("state"), "off")


def _below(trigger: dict, level: int) -> bool:
    try:
        return float(trigger.get("below")) == float(level)
    except (TypeError, ValueError):
        return False


def safety_report(safety: dict | None, auto: dict, by_trigger: dict[str, int]) -> list[dict]:
    """[ADDED v3.80.0] The user's answers to LIBI's own questions, each checked in the logic as the build was told to
    write it (safety_context): shown with the lines of the request, and a miss goes back to the model like one of them."""
    safety = safety or {}
    options = _options(auto)
    switched = [e for ids in (safety.get("switched") or {}).values() for e in ids]
    starts = [(o, i) for o in options for i, s in enumerate(o["steps"]) if _switches(s, switched, _ON_SERVICES)]

    def rung(ids: set[str]) -> int:
        return next((by_trigger[i] for i in sorted(ids) if i in by_trigger), 0)

    def item(iid: str, text: str, kind: str, missing: str, ids: set[str]) -> dict:
        return {"id": iid, "text": text, "kind": kind, "ok": not missing, "rung": rung(ids), "how": "",
                "missing": missing}

    report: list[dict] = []
    enable = safety.get("enable")
    if enable:
        off_ids = _triggers_of(auto, enable, "state", lambda t: _state_is(t.get("to"), "off"))
        stops = [o for o in options if o["ids"] & off_ids and any(_switches(s, switched, _OFF_SERVICES) for s in o["steps"])]
        blocking = [o for o in options if not any(_switches(s, switched, _ON_SERVICES) for s in o["steps"])
                    and any(_switches(s, switched, _OFF_SERVICES) for s in o["steps"])
                    and any(_is_on_check(c, enable) for c in _leaves(o["conditions"]))]
        # With nothing picked to switch, the switch is checked at all; else before every step that switches on.
        gated = (bool(starts) and all(any(_is_on_check(c, enable) for c in _checks_before(auto, o, i)) for o, i in starts)
                 if switched else any(_is_on_check(c, enable) for o in options for c in _leaves(o["conditions"])))
        missing = ("the switch is in the conditions of the automation, which hold for every trigger - off, it also keeps "
                   "what turns things off from running"
                   if any(_is_on_check(c, enable) for c in _leaves(auto.get("conditions") or [])) else
                   "the start does not check that the on/off switch is on before it switches" if not gated else
                   "turning the switch off does not stop it: no trigger of the switch turning off with an option that "
                   "turns off what the start turns on" if switched and not stops else
                   "an option that turns things off checks the switch - off, it would leave them on" if blocking else "")
        report.append(item("libi_enable", "The switch on the card: off stops it at once, and nothing starts until it is on",
                           "enable", missing, {i for o in stops for i in o["ids"]} or {i for o, _x in starts for i in o["ids"]}))
    # [ADDED v3.81.0] The messages when it starts and when it ends, each to every phone it is for.
    kinds = {"notify": "a notification", "speak": "spoken", "both": "a notification and spoken"}
    phones, speakers = safety.get("phones") or [], safety.get("speakers") or []
    if safety.get("start") and switched:
        wanted = _wanted_messages(safety["start"], phones, speakers)
        unsent = sorted({m for o, i in starts for m in _unsent(o["steps"][i + 1:], wanted)})
        report.append(item("libi_start", f"It tells you when it starts ({kinds[safety['start']]})", "message",
                           "nothing turns them on to tell of" if not starts else
                           f"after it turns them on, it does not send {', '.join(unsent)}" if unsent else "",
                           {i for o, _x in starts for i in o["ids"]}))
    if safety.get("end") and switched:
        wanted = _wanted_messages(safety["end"], phones, speakers)
        missing, told = "", set()
        for eid in switched:
            off = _off_state(eid)
            ids = _end_triggers(auto, eid)
            clean = {str(t.get("id")) if t.get("id") is not None else "" for t in auto.get("triggers") or []
                     if isinstance(t, dict) and t.get("trigger") == "state" and eid in _ids_in(t)
                     and _state_is(t.get("to"), off)
                     and ("unavailable" in (t.get("not_from") if isinstance(t.get("not_from"), list) else [t.get("not_from")])
                          or (t.get("from") is not None and not _state_is(t.get("from"), "unavailable")))}
            ends = [o for o in options if o["ids"] & clean]
            unsent = sorted({m for o in ends for m in _unsent(o["steps"], wanted)})
            missing = missing or (
                f"nothing tells you when {eid} turns {off}: no trigger of it turning {off} with an option that sends the "
                "message" if not ids else
                f'the trigger of {eid} turning {off} also fires when it comes back from unavailable - give it "not_from": '
                '["unavailable", "unknown"]' if not clean else
                f"when {eid} turns {off}, it does not send {', '.join(unsent)}" if unsent else "")
            told |= clean
        if not missing and str(auto.get("mode") or "single") not in ("queued", "parallel"):
            missing = (f"in mode {auto.get('mode') or 'single'} Home Assistant drops the message: the option that turns it "
                       'off is still running when it turns off - the mode is "queued"')
        report.append(item("libi_end", f"It tells you when it ends ({kinds[safety['end']]})", "message", missing, told))
    if safety.get("offline") and switched:
        names = safety.get("names") or "the device"
        unchecked = [e for e in switched if any(_switches(o["steps"][i], [e], _ON_SERVICES)
                                                and not any(_is_online_check(c, e) for c in _checks_before(auto, o, i))
                                                for o, i in starts)]
        report.append(item("libi_online", f"It does not start while {names} is offline", "offline",
                           f"it switches {', '.join(unchecked)} without checking that it is online" if unchecked else "",
                           {i for o, _x in starts for i in o["ids"]}))
        if safety["offline"] == "tell":
            told: set[str] = set()
            silent = []
            for eid in switched:
                ids = _triggers_of(auto, eid, "state", lambda t: _state_is(t.get("to"), "unavailable"))
                if any(o["ids"] & ids and _sends(o["steps"]) for o in options):
                    told |= ids
                else:
                    silent.append(eid)
            report.append(item("libi_offline", f"It tells you when {names} is offline", "offline",
                               f"nothing tells you when {', '.join(silent)} is offline: no trigger of it turning "
                               "unavailable with an option that sends a message" if silent else "", told))
    level = int(safety.get("battery") or 0)
    if level:
        told, quiet = set(), []
        for sensor in safety.get("batteries") or []:
            ids = _triggers_of(auto, sensor, "numeric_state", lambda t: _below(t, level))
            if any(o["ids"] & ids and _sends(o["steps"]) for o in options):
                told |= ids
            else:
                quiet.append(sensor)
        report.append(item("libi_battery", f"It tells you when a battery is below {level}%", "battery",
                           f"no message when {', '.join(quiet)} is below {level}%: no numeric_state trigger below {level} "
                           "with an option that sends a message" if quiet else "", told))
    return report


# ---------------------------------------------------------------------------------------- messages

MAX_HELPERS = 150
HELPER_DOMAINS = ("input_boolean", "input_number", "input_select", "input_text", "input_datetime",
                  "input_button", "timer", "counter", "schedule")


@callback
def helpers_context(hass: HomeAssistant) -> str:
    """[ADDED v3.41.0] The user's helpers, which an automation often reads or sets."""
    lines = []
    for state in hass.states.async_all(HELPER_DOMAINS)[:MAX_HELPERS]:
        a = state.attributes
        extra = []
        for key in ("unit_of_measurement", "min", "max", "step", "options", "has_date", "has_time", "duration"):
            if key in a:
                value = a[key]
                extra.append(f"{key}={value if not isinstance(value, list) else '|'.join(map(str, value[:12]))}")
        lines.append(f"- {state.entity_id} \"{state.name}\" = {state.state}" + (f" ({', '.join(extra)})" if extra else ""))
    return ("HELPERS:\n" + "\n".join(lines)) if lines else ""


@callback
def candidates_context(hass: HomeAssistant, plan: dict, candidates: dict, selections: dict) -> str:
    """[ADDED v3.41.0] Per role, the devices LIBI found, with state, unit and class, and which ones the
    user picked - so the model knows a meter counts litres. It still writes only role references."""
    lines = ["DEVICES (per role; * = picked by the user; write only the role reference):"]
    for role in plan.get("roles") or []:
        picked = set(selections.get(role["id"]) or [])
        items = (candidates.get(role["id"]) or {}).get("items") or []
        lines.append(f"role:{role['id']}:")
        for it in items[:25]:
            state = hass.states.get(it.get("entity_id", ""))
            unit = state.attributes.get("unit_of_measurement", "") if state else ""
            mark = "*" if it.get("entity_id") in picked else " "
            lines.append(f" {mark} {it.get('entity_id')} \"{it.get('name', '')}\" = {state.state if state else ''}"
                         f"{(' ' + unit) if unit else ''}{(' [' + it['device_class'] + ']') if it.get('device_class') else ''}")
    return "\n".join(lines)


MAX_CANVAS_NETS = 20
MAX_CANVAS_CHARS = 16000


_REGISTRY_ID_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")


def registry_entities(hass: HomeAssistant, text: str) -> list[tuple[str, str]]:
    """[ADDED v3.53.0] The entities a YAML text names by registry id (the Home Assistant editor writes
    device triggers and actions that way): (entity_id, name) of each that exists. A device id looks the
    same and is not an entity; the registry does not know it as one, so it is skipped."""
    reg, out, seen = er.async_get(hass), [], set()
    for m in _REGISTRY_ID_RE.finditer(text or ""):
        entry = reg.async_get(m.group(0))
        if entry is None or entry.entity_id in seen:
            continue
        state = hass.states.get(entry.entity_id)
        if state is None:
            continue
        seen.add(entry.entity_id)
        out.append((entry.entity_id, _sanitize(state.name)[:60]))
    return out


_FULL_ENTITY_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")
_ELEMENT_SKIP = {"raw", "sig", "comment", "structuralError"}


def element_entities(hass: HomeAssistant, net: Any) -> list[tuple[str, str]]:
    """[ADDED v3.54.0] The entities the ladder elements of a net show (label, sourceA, target, ...):
    (entity_id, name) of each that exists, in order. The importer resolved them when it drew the net."""
    out: dict[str, str] = {}

    def walk(value: Any, depth: int) -> None:
        if depth > 12 or len(out) >= MAX_CANDIDATES:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key not in _ELEMENT_SKIP:
                    walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, str) and _FULL_ENTITY_RE.match(value) and value not in out:
            state = hass.states.get(value)
            if state is not None:
                out[value] = _sanitize(state.name)[:60]

    walk((net or {}).get("rungs") if isinstance(net, dict) else None, 0)
    return list(out.items())


def canvas_context(hass: HomeAssistant, nets: Any) -> tuple[str, dict[str, str]]:
    """[ADDED v3.40.0] The nets on the canvas as the YAML LIBI would save, for the model to read.
    Returns the text block and each net's YAML by its net id. [CHANGED v3.42.0] This is the ONLY YAML
    the model gets: the nets open in the LIBI page, while the chat's share switch is on. The user's
    automations.yaml, scripts.yaml and scenes.yaml are never read for the model."""
    blocks, by_id, total = [], {}, 0
    for position, net in enumerate((nets if isinstance(nets, list) else [])[:MAX_CANVAS_NETS], start=1):
        if not isinstance(net, dict) or not net.get("id"):
            continue
        try:
            text = yaml.dump(ast_to_yaml(hass, net), default_flow_style=False, allow_unicode=True,
                             sort_keys=False)
        except Exception as err:  # noqa: BLE001
            text = f"# could not be compiled: {_sanitize(err)}\n"
        # [ADDED v3.53.0] Device triggers and actions name their entity by registry id; say which it is.
        # [CHANGED v3.54.0] And the entities on the ladder elements: a registry id can be stale (a device
        # paired again) while the element still shows the entity the user sees.
        resolved = [(e, n) for e, n in registry_entities(hass, text) + element_entities(hass, net) if e not in text]
        resolved = list(dict(resolved).items())
        if resolved:
            text += "# entities this net uses: " + ", ".join(f"{eid} ({name})" for eid, name in resolved) + "\n"
        nid = str(net["id"])[:40]
        by_id[nid] = text
        # [CHANGED v3.59.0] With the number the canvas shows: "update NET 3" names a net by it.
        block = f"--- NET {position} | net id {nid} | {net_level(net)} | {str(net.get('name') or '')[:80]}\n{text}"
        if total + len(block) > MAX_CANVAS_CHARS:
            blocks.append(f"--- NET {position} | net id {nid} | {str(net.get('name') or '')[:80]} (too long to include)")
            continue
        total += len(block)
        blocks.append(block)
    if not blocks:
        return "", by_id
    return "NETS ON THE CANVAS:\n" + "\n".join(blocks), by_id


@callback
def net_entities(hass: HomeAssistant, net_yaml: str) -> set[str]:
    """[ADDED v3.75.0] The entities a net's YAML names that exist (preselect; drop_used_helpers keeps them for a change:
    a helper the net itself uses is not used by another automation)."""
    return {m.group(0) for m in _ENTITY_RE.finditer(net_yaml or "") if hass.states.get(m.group(0))}


@callback
def preselect(hass: HomeAssistant, plan: dict, net_yaml: str, taken: set[str] | None = None,
              filled: set[str] | None = None) -> dict[str, list[str]]:
    """[ADDED v3.40.0] For a change to a net: the entities that net already uses, per role, so the
    user starts from what is there. Only entities that exist and fit the role's domains.
    [CHANGED v3.75.0] Not an entity taken already, nor a role filled already (taken, filled: the helpers the message
    names, and the net's alarm clock, which keep_net_alarm_clock puts in the roles of its days and its time), nothing in
    a day's role, and a setting only when it is the one that fits the role and the role the one it fits; a net with an
    alarm clock starts at its time, so its schedule is not ticked again. In a change of the user's NET 3 every day's
    role got all seven day switches, and the role of the most minutes the litres too."""
    used = net_entities(hass, net_yaml) - set(taken or ())
    config = _yaml_mapping(net_yaml)
    if net_alarm_clock(hass, config):
        used = {e for e in used if e.split(".")[0] != "schedule"}
    # [ADDED v3.76.0] A switch for each day, of a net of 3.73.0 - 3.75.0: its days are one helper now.
    used -= set(config_days(config))
    filled = set(filled or ())
    out, settings = {}, []
    for role in plan.get("roles") or []:
        # [ADDED v3.60.0] The role of a helper the user named holds that helper, not one of the net's.
        # [CHANGED v3.74.0] Nor does a schedule that gave way to the alarm clock: a card cannot set it.
        if role["id"] in filled or role.get("named") or role.get("replaced") or _is_day_role(role) or _is_days_role(role):
            continue
        ids = sorted(e for e in used if e.split(".")[0] in role["domains"])
        if not set(role["domains"]) <= SETTING_DOMAINS:
            if ids:
                out[role["id"]] = ids
        elif len(ids) == 1:
            settings.append((role["id"], ids[0]))
    # A setting that fits more than one role is the user's to place.
    fits = [eid for _rid, eid in settings]
    out.update({rid: [eid] for rid, eid in settings if fits.count(eid) == 1})
    return out


def clean_messages(raw: Any) -> list[dict]:
    """The conversation as the model may see it: user and assistant turns, capped."""
    out = []
    for m in (raw or [])[-MAX_MESSAGES:] if isinstance(raw, list) else []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            text = str(m.get("content") or "").strip()[:MAX_MESSAGE_CHARS]
            if text:
                out.append({"role": m["role"], "content": text})
    return out


def build_context(plan: dict, selections: dict, answers: dict, hass: HomeAssistant,
                  current_net: str = "", services: tuple[list[str], list[str]] | None = None,
                  safety: dict | None = None) -> str:
    """What the model is told for the build: the roles and what the user picked, by NAME and
    domain only, so it can choose fitting services; entity ids are filled in by LIBI. For a change,
    the current version of the net comes along, so the model rewrites it instead of starting over."""
    lines = [f"LEVEL: {plan['level']}", f"NAME: {plan['name']}"]
    if current_net:
        lines += ["CURRENT NET (write the whole new version of it, devices as role references):", current_net]
    lines.append("ROLES:")
    for role in plan["roles"]:
        picked = selections.get(role["id"]) or []
        kinds = sorted({e.split(".")[0] for e in picked})
        names = [hass.states.get(e).name for e in picked if hass.states.get(e)][:12]
        lines.append(f"- role:{role['id']} ({role['purpose']}) = {len(picked)} entity(ies) of domain "
                     f"{', '.join(kinds)}: {', '.join(names)}")
    # [CHANGED v3.80.0] Not the answers to LIBI's own questions: what they mean is said below (safety_context).
    theirs = [q for q in plan.get("questions") or [] if q["id"] in answers and q["id"] not in SAFETY_QUESTIONS]
    if theirs:
        lines.append("ANSWERS:")
        for q in theirs:
            lines.append(f"- {q['text']} -> {str(answers[q['id']])[:200]}")
    # [ADDED v3.73.0] The lines of the request the logic must do, which LIBI checks in the logic.
    if plan.get("requirements"):
        lines.append("REQUIREMENTS (the logic must do every one, and LIBI checks it; say in covers which trigger id "
                     "does each):")
        lines += [f"- {r['id']} ({r['kind']}): {r['text']}" for r in plan["requirements"]]
    # [ADDED v3.75.0] The alarm clock the user picked: its time starts the logic, and its days are checked right after.
    alarm = picked_alarm_clock(hass, plan, selections)
    if alarm:
        start = "ALARM CLOCK (the user sets it on the card): "
        if alarm["time"]:
            start += (f'it starts with {{"trigger": "time", "at": "role:{alarm["time_role"]}", "id": "start"}}, never '
                      "by a schedule; ")
        # [CHANGED v3.76.0] The days: the CMP DAY of the days helper, written exactly so.
        days = json.dumps({"condition": "template", "value_template": day_bits_template(f"role:{alarm['days_role']}")})
        lines.append(start + f"the start option checks the days right after it, exactly so: {days}.")
    # [ADDED v3.84.0] The zone chosen on the card, and how it is read.
    lines += zone_choice_context(plan, selections)
    # [ADDED v3.80.0] What the user answered to LIBI's own questions: an on/off switch, a device offline, a low battery.
    lines += safety_context(safety)
    # [ADDED v3.62.0] The message services the user named, checked: the build sends only to the ones that exist.
    found, missing = services or ([], [])
    unticked: list[str] = []
    # [CHANGED v3.65.0] The phones the user ticked, by the notify service each one is sent to.
    if selections.get(PHONES_ROLE):
        known = phone_services(hass)
        reached = [known[eid] for eid in selections[PHONES_ROLE] if eid in known]
        # [CHANGED v3.81.1] The ticks win over the message: a phone it names that the user left unticked is left out. It
        # was told "exists, use it as written", the draft sent to it, and the check of the ticks sent it back.
        unticked = [name for name in found if name in set(known.values()) and name not in reached]
        found = [name for name in found if name not in set(known.values())]
        lines.append("PHONES (send each message to every one of these, one action each): " + ", ".join(reached))
    if found or missing or unticked:
        lines.append("MESSAGE SERVICES THE USER NAMED:")
        lines += [f"- {name}: exists, use it as written" for name in found]
        lines += [f"- {name}: a phone the user left unticked in the list - leave it out" for name in unticked]
        lines += [f"- {name}: MISSING - it does not exist in this Home Assistant, leave it out" for name in missing]
    return "\n".join(lines)
