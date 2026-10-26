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
MAX_ROLES = 8
MAX_CANDIDATES = 80
LLM_TIMEOUT = aiohttp.ClientTimeout(total=120)


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
            async with session.post(url, json=body, headers=headers, timeout=LLM_TIMEOUT) as resp:
                if resp.status >= 400:
                    raise AiError(f"The local AI server answered {resp.status}.")
                data = await resp.json(content_type=None)
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
            async with session.post(base + "/chat/completions", json=body, headers=headers,
                                    timeout=LLM_TIMEOUT) as resp:
                if resp.status == 400:
                    # Some OpenAI-compatible servers know only the plain JSON mode. A new body, so
                    # the request already sent is never changed after the fact.
                    plain = {**body, "response_format": {"type": "json_object"}}
                    async with session.post(base + "/chat/completions", json=plain, headers=headers,
                                            timeout=LLM_TIMEOUT) as retry:
                        if retry.status >= 400:
                            raise AiError(f"The AI service answered {retry.status}.")
                        data = await retry.json(content_type=None)
                elif resp.status >= 400:
                    raise AiError(f"The AI service answered {resp.status}.")
                else:
                    data = await resp.json(content_type=None)
            choices = (data or {}).get("choices") or [{}]
            return _parse_json(((choices[0] or {}).get("message") or {}).get("content", ""))
    except AiError:
        raise
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.warning("[libi] AI request failed: %s", _sanitize(err))
        raise AiError("The AI could not be reached. Check the address in the LIBI settings.") from err
    raise AiError("AI is not set up. Choose a model in Settings > Devices & services > LIBI > Configure.")


# ---------------------------------------------------------------------------------------- prompts

PLAN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
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
    },
    "required": ["reply", "level", "name", "roles", "questions"],
}

PLAN_SYSTEM = """You help a Home Assistant user describe an automation, script or scene that LIBI will build.
You do NOT know the user's devices and you must NOT name any entity_id, device_id or area_id.
Instead, describe every device the logic needs as a ROLE with search criteria. LIBI searches the
user's Home Assistant with them and the user picks the entities from a list.

Answer with JSON only, matching the schema:
- reply: one or two short sentences IN THE USER'S LANGUAGE: what you understood and what to pick.
- level: "automation" if something must start it (a button, a sensor, a time); "script" if the user
  starts it by hand; "scene" for a set of fixed states.
- name: a short name for it, in the user's language.
- roles: every device the logic touches. For each:
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
    e.g. ["button","remote","switch","כפתור","לחצן"].
  - area_keywords: area names the user mentioned, in English AND in the user's language, e.g.
    ["living room","salon","סלון"]; [] when no area was said.
  Do not invent a specific device; when the user did not say which one, the role asks them to pick.
- questions: what you must know before building that is not a device: durations, times, days,
  thresholds, whether a dashboard card is wanted and on which dashboard. Each with an English
  snake_case id, the text in the user's language, and choices (or [] for a free answer). Ask only
  what you really need; use sensible defaults otherwise and say so in the reply.
"""

BUILD_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "level": {"type": "string", "enum": list(LEVELS)},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "config": {"type": "object"},
        "ui_card": {"type": "object"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["reply", "level", "name", "description", "config", "ui_card", "notes"],
}

BUILD_SYSTEM = """You write a Home Assistant configuration that LIBI turns into a ladder diagram.
Answer with JSON only, matching the schema.

Devices: you never write an entity_id. Every device is written as "role:<role id>" from the ROLES
list, e.g. "entity_id": "role:trigger_buttons". A role may hold several entities; LIBI fills them in.
Never write device_id, area_id, floor_id or label_id, and no device triggers or device actions.

config, by level:
- automation: {"mode": "single"|"restart"|"queued"|"parallel", "triggers": [...], "conditions": [...],
  "actions": [...]}
- script: {"mode": ..., "sequence": [...]}
- scene: {"actions": [...]} where every action switches one role on or off, e.g.
  {"action": "light.turn_on", "target": {"entity_id": "role:lights"}}
Use the current syntax: "trigger:" (not platform), "action:" (not service).
Allowed triggers: state, numeric_state, time, time_pattern, sun, template, homeassistant, zone.
  A press of a button/input_button/event entity is {"trigger": "state", "entity_id": "role:..."}
  with no "to". A remote's action sensor uses "to" with the action value only if the user said it.
Allowed conditions: state, numeric_state, time, sun, template, and, or, not, trigger, zone.
Allowed actions: a service of the target's own domain (light.turn_on, switch.turn_off, valve.open_valve,
  cover.close_cover, climate.set_temperature, media_player.volume_set, input_number.set_value ...),
  homeassistant.turn_on/turn_off/toggle, notify.*, tts.speak, persistent_notification.create,
  delay, wait_for_trigger, wait_template, choose, if/then/else, repeat, parallel, sequence, stop.
  Every service that acts on devices must have target.entity_id with role references.
Durations: "delay": {"minutes": 10} or "for": {"minutes": 2}.

ui_card: when the user asked for a dashboard card, a Lovelace card config (built-in card types only,
e.g. "entities", "tile", "glance", "vertical-stack"), with entities as role references; otherwise {}.
reply: one or two sentences IN THE USER'S LANGUAGE describing what you built.
description: one sentence in the user's language. notes: anything the user should check, in the
user's language, or [].
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
def clean_plan(hass: HomeAssistant, raw: dict) -> dict:
    """The plan reduced to what LIBI understands. A domain that does not exist in this Home
    Assistant is dropped, ids become safe snake_case, and every list is capped."""
    domains_here = present_domains(hass)
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
            "domains": [d for d in _str_list(r.get("domains"), 8, 30) if d in domains_here],
            "device_classes": [_clean_id(d, "") for d in _str_list(r.get("device_classes"), 8, 30)],
            "keywords": _str_list(r.get("keywords")),
            "area_keywords": _str_list(r.get("area_keywords")),
        })
    questions, qseen = [], set()
    for i, q in enumerate(raw.get("questions") or []):
        if not isinstance(q, dict) or len(questions) >= 6:
            continue
        qid = _clean_id(q.get("id"), f"q{i + 1}")
        if qid in qseen:
            continue
        qseen.add(qid)
        questions.append({"id": qid, "text": str(q.get("text") or "")[:300],
                          "choices": _str_list(q.get("choices"), 8, 80)})
    return {"reply": str(raw.get("reply") or "")[:1200], "level": level,
            "name": str(raw.get("name") or "")[:80] or "AI automation",
            "roles": roles, "questions": questions}


def _norm(text: Any) -> str:
    return re.sub(r"[\s_\-.]+", " ", str(text or "").lower()).strip()


@callback
def find_candidates(hass: HomeAssistant, role: dict) -> dict:
    """[RULE 8] The entities a role can be, found in the registries without the model. Entities that
    match a keyword or an area come first and are marked exact; when nothing matches, the closest
    entities of the right domain are offered and marked so."""
    domains = role.get("domains") or []
    if not domains:
        return {"items": [], "exact": False}
    ent_reg, dev_reg, area_reg = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    keywords = [_norm(k) for k in role.get("keywords") or [] if _norm(k)]
    areas = [_norm(k) for k in role.get("area_keywords") or [] if _norm(k)]
    classes = set(role.get("device_classes") or [])

    scored = []
    for state in hass.states.async_all(domains):
        entry = ent_reg.async_get(state.entity_id)
        device = dev_reg.async_get(entry.device_id) if entry and entry.device_id else None
        area_id = (entry.area_id if entry else None) or (device.area_id if device else None)
        area = area_reg.async_get_area(area_id) if area_id else None
        area_name = area.name if area else ""
        device_name = (device.name_by_user or device.name) if device else ""
        dclass = state.attributes.get("device_class") or (entry.original_device_class if entry else None) or ""
        text = _norm(f"{state.entity_id} {state.name} {device_name}")
        area_text = _norm(area_name)

        score = 0
        score += sum(3 for k in keywords if k in text)
        score += sum(5 for a in areas if a and (a in area_text or a in text))
        class_ok = not classes or dclass in classes
        if classes and class_ok:
            score += 2
        scored.append((score, class_ok, {
            "entity_id": state.entity_id, "name": state.name, "area": area_name,
            "device_class": dclass, "state": state.state,
        }))

    wanted_area = bool(areas)
    exact = [s for s in scored if s[1] and s[0] > (4 if wanted_area else 0)]
    pool = exact or [s for s in scored if s[1]] or scored
    pool.sort(key=lambda s: (-s[0], s[2]["name"].lower()))
    return {"items": [s[2] for s in pool[:MAX_CANDIDATES]], "exact": bool(exact),
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
}

_ROLE_RE = re.compile(r"role:([a-z0-9_]+)")
_ENTITY_RE = re.compile(r"(?<![\w.])([a-z_][a-z0-9_]*)\.([a-z0-9_]+)(?![\w(])")


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
        if domain not in ENTITY_SERVICE_DOMAINS or (domain in RESTRICTED and name not in RESTRICTED[domain]):
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
        if rid not in out:
            errors.append(f"Pick at least one entity for '{role['label']}'.")
    return out, errors


async def _validate_with_home_assistant(hass: HomeAssistant, level: str, config: dict) -> str | None:
    """Home Assistant's own schema has the last word. Returns an error text or None."""
    try:
        if level == "script":
            from homeassistant.components.script.config import async_validate_config_item  # noqa: PLC0415
            result = await async_validate_config_item(hass, "libi_ai_check", config)
        elif level == "automation":
            from homeassistant.components.automation.config import async_validate_config_item  # noqa: PLC0415
            result = await async_validate_config_item(hass, "libi_ai_check", config)
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


async def async_build_draft(hass: HomeAssistant, plan: dict, selections: dict, raw: dict) -> dict:
    """The model's build answer, validated and turned into an automation, script or scene dict
    that the importer can draw. Returns errors instead when anything does not hold."""
    level = raw.get("level") if raw.get("level") in LEVELS else plan.get("level", "automation")
    config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    draft = _Draft(hass, selections)
    body = draft.walk(copy.deepcopy(config))

    name = str(raw.get("name") or plan.get("name") or "AI automation")[:80]
    description = str(raw.get("description") or "")[:300]
    if level == "automation":
        auto = {"id": f"libi_ai_{int(time.time() * 1000)}", "alias": name, "description": description,
                "mode": body.get("mode", "single"), "triggers": body.get("triggers") or [],
                "conditions": body.get("conditions") or [], "actions": body.get("actions") or []}
        if not auto["triggers"]:
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
    if not auto["actions"]:
        draft.err("The draft does nothing: it has no actions.")

    card = raw.get("ui_card") if isinstance(raw.get("ui_card"), dict) else {}
    card_yaml = ""
    if card:
        card_draft = _Draft(hass, selections)
        card_body = _clean_card(card_draft, card)
        draft.errors.extend(e for e in card_draft.errors if e not in draft.errors)
        draft.used |= card_draft.used
        card_yaml = yaml.dump(card_body, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if not draft.errors and ha_config is not None:
        problem = await _validate_with_home_assistant(hass, level, ha_config)
        if problem:
            draft.err(f"Home Assistant rejected the draft: {problem}")

    sensitive = sorted(e for e in draft.used if e.split(".")[0] in SENSITIVE_DOMAINS)
    preview = yaml.dump(ha_config if ha_config is not None else {"name": name, "actions": auto["actions"]},
                        default_flow_style=False, allow_unicode=True, sort_keys=False)
    return {"ok": not draft.errors, "errors": draft.errors, "level": level, "auto": auto,
            "yaml": preview, "card_yaml": card_yaml, "sensitive": sensitive,
            "reply": str(raw.get("reply") or "")[:1200],
            "notes": _str_list(raw.get("notes"), 8, 300)}


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
            if k == "type" and isinstance(v, str) and v.startswith("custom:"):
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


# ---------------------------------------------------------------------------------------- messages

def clean_messages(raw: Any) -> list[dict]:
    """The conversation as the model may see it: user and assistant turns, capped."""
    out = []
    for m in (raw or [])[-MAX_MESSAGES:] if isinstance(raw, list) else []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            text = str(m.get("content") or "").strip()[:MAX_MESSAGE_CHARS]
            if text:
                out.append({"role": m["role"], "content": text})
    return out


def build_context(plan: dict, selections: dict, answers: dict, hass: HomeAssistant) -> str:
    """What the model is told for the build: the roles and what the user picked, by NAME and
    domain only, so it can choose fitting services; entity ids are filled in by LIBI."""
    lines = [f"LEVEL: {plan['level']}", f"NAME: {plan['name']}", "ROLES:"]
    for role in plan["roles"]:
        picked = selections.get(role["id"]) or []
        kinds = sorted({e.split(".")[0] for e in picked})
        names = [hass.states.get(e).name for e in picked if hass.states.get(e)][:12]
        lines.append(f"- role:{role['id']} ({role['purpose']}) = {len(picked)} entity(ies) of domain "
                     f"{', '.join(kinds)}: {', '.join(names)}")
    if answers:
        lines.append("ANSWERS:")
        for q in plan.get("questions") or []:
            if q["id"] in answers:
                lines.append(f"- {q['text']} -> {str(answers[q['id']])[:200]}")
    return "\n".join(lines)
