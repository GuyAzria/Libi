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
# v3.89.0
# [ADDED v3.88.0 | 2026-11-05] Purpose: LIBI Global - the recipients of messages ("Guy", "Everyone"), each a script of
#   Home Assistant's that sends to the phones ticked for it in LIBI. A NET sends to the recipient, so a phone replaced is
#   changed in one place for every project (the user's request, 2026-11-05).
# [ADDED v3.89.0 | 2026-11-05] Purpose: move_entry - an automation or script that sends straight to the one phone of a
#   recipient sends through the recipient instead, only the action of those steps changed (the user's request, the
#   same day: replace it in every automation, once they confirm).
"""LIBI Global: the recipients of LIBI's messages.

A recipient is a script, kept in scripts.yaml under a key that starts with RECIPIENT_PREFIX. The panel sends it to Home
Assistant's own config API, as it sends every save since 3.85.0 - LIBI writes no file. A MOVE NOTIFY / TTS block calls the
script with the data it would give a phone's notify action - message, title, and the app's data (tts_text and
media_stream for a message read aloud) - and the script gives that to each of its phones: together when there are
several (one parallel step, so a phone that fails does not keep the message from the others, and the failure is still
in the script's trace). A phone that does not read a message aloud (iOS) gets the spoken text as its message instead of
the word TTS.

The phones are read back from the script itself: scripts.yaml is the only place they are kept (RULE 21). A script under
the prefix that is not exactly what LIBI writes for its name and phones was changed outside LIBI (edited): LIBI says so,
and writes it again only when the user saves it in LIBI Global.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from homeassistant.util import slugify

from .const import RECIPIENT_PREFIX
from .libi_to_yaml import same_config
from .yaml_to_libi import called_actions, iter_steps

ALIAS_PREFIX = "LIBI Global: "
MAX_NAME = 60
MAX_PHONES = 20
_KEY_RE = re.compile(re.escape(RECIPIENT_PREFIX) + r"[a-z0-9_]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# What a NET gives the script: what it would give a phone's notify action.
FIELDS = {
    "message": {"name": "Message", "description": "The text. TTS, with tts_text in data, is a message read aloud.",
                "selector": {"text": {"multiline": True}}},
    "title": {"name": "Title", "selector": {"text": {}}},
    "data": {"name": "Data", "description": "What the phone's app reads besides the text: tts_text and media_stream for "
                                            "a message read aloud.",
             "selector": {"object": {}}},
}

# The data of one phone's step: what the script was given, without an empty title or empty data - the phone gets what a
# notify action of its own would have given it. One template that renders a mapping; Home Assistant takes a template as
# the data of an action.
_REST = ("{% if title is defined and title %}{% set out = dict(out, title=title) %}{% endif %}"
         "{% if data is defined and data is mapping and data %}{% set out = dict(out, data=data) %}{% endif %}{{ out }}")
SPEAKS_DATA = "{% set out = {'message': message | default('')} %}" + _REST
# A phone that does not read a message aloud shows the spoken text, not the word TTS.
TEXT_DATA = ("{% set said = data.tts_text if data is defined and data is mapping and data.tts_text is defined else '' %}"
             "{% set text = message | default('') %}"
             "{% set out = {'message': said if said and text | upper == 'TTS' else text} %}" + _REST)


def is_recipient_key(key: Any) -> bool:
    """The key of a recipient's script in scripts.yaml."""
    return isinstance(key, str) and _KEY_RE.fullmatch(key) is not None


def clean_name(text: Any) -> str:
    """A recipient's name as the user typed it, on one line: no control characters, single spaces, MAX_NAME long."""
    return " ".join(_CONTROL.sub(" ", str(text or "")).split())[:MAX_NAME]


def new_key(name: str, taken: set[str]) -> str:
    """The key of a new recipient: its name as a slug (Home Assistant's, which spells out other alphabets), unique among
    the scripts there are. It never changes after: the NETs call the script by it, so a new name is a new alias only."""
    slug = re.sub(r"[^a-z0-9_]", "", slugify(name))[:40].strip("_")
    if not slug or (slug == "unknown" and "unknown" not in name.lower()):
        slug = "recipient"
    base = RECIPIENT_PREFIX + slug
    key, counter = base, 2
    while key in taken:
        key, counter = f"{base}_{counter}", counter + 1
    return key


def recipient_config(name: str, phones: list[tuple[str, bool]]) -> dict[str, Any]:
    """The script of a recipient: its name, and each phone's notify action with whether it reads a message aloud."""
    steps = [{"action": service, "data": SPEAKS_DATA if speaks else TEXT_DATA} for service, speaks in phones]
    return {
        "alias": ALIAS_PREFIX + name,
        "description": (f"Sends LIBI's messages to the phones of {name}. LIBI writes it: change the phones in LIBI ▸ "
                        f"Global, and every automation that sends to {name} follows."),
        "icon": "mdi:cellphone-message",
        "mode": "parallel",
        "max": 50,
        "fields": copy.deepcopy(FIELDS),
        "sequence": steps if len(steps) == 1 else [{"parallel": steps}],
    }


def read_recipient(key: str, config: dict) -> dict[str, Any]:
    """A recipient as scripts.yaml holds it: its name, the phones it sends to, and whether it is not what LIBI writes for
    that name and those phones (edited). Of an edited one, the phones are every notify action it calls."""
    alias = str(config.get("alias") or "").strip()
    name = clean_name(alias[len(ALIAS_PREFIX):] if alias.startswith(ALIAS_PREFIX) else alias)
    name = name or key[len(RECIPIENT_PREFIX):]
    sequence = config.get("sequence")
    steps = sequence
    if (isinstance(sequence, list) and len(sequence) == 1 and isinstance(sequence[0], dict)
            and list(sequence[0]) == ["parallel"] and isinstance(sequence[0]["parallel"], list)):
        steps = sequence[0]["parallel"]
    phones: list[tuple[str, bool]] = []
    for step in steps if isinstance(steps, list) else []:
        action = step.get("action") if isinstance(step, dict) else None
        if isinstance(action, str) and action.startswith("notify.") and step.get("data") in (SPEAKS_DATA, TEXT_DATA):
            phones.append((action, step["data"] == SPEAKS_DATA))
    edited = not phones or not same_config(config, recipient_config(name, phones))
    services = ([service for service, _speaks in phones] if not edited
                else list(dict.fromkeys(a for a in called_actions(sequence) if a.startswith("notify."))))
    return {"key": key, "action": f"script.{key}", "name": name, "phones": services, "edited": edited}


# [ADDED v3.89.0] A step that sends straight to a phone, sent through a recipient of that phone alone instead. Only a step
# the recipient passes on exactly as the phone got it is moved: the keys any step may have, and the data of a phone's
# notify action - a message, a title, the app's data. Anything else (a target, a response, no message) stays as it is.
_MOVE_STEP_KEYS = frozenset(("action", "service", "data", "metadata", "alias", "enabled", "continue_on_error"))
_MOVE_DATA_KEYS = frozenset(("message", "title", "data"))


def movable_step(step: dict) -> bool:
    """Whether a step that sends to a phone gives the recipient nothing it would not pass on to the phone."""
    data = step.get("data")
    return set(step) <= _MOVE_STEP_KEYS and isinstance(data, dict) and "message" in data and set(data) <= _MOVE_DATA_KEYS


def steps_key(domain: str, config: dict) -> str:
    """Where an automation or a script keeps its steps."""
    if domain == "script":
        return "sequence"
    return "actions" if "actions" in config else "action"


def move_entry(domain: str, config: dict, phone: str, action: str) -> tuple[dict, int, int]:
    """A copy of an automation or a script in which each step that sends straight to phone and can be moved calls action
    instead - its key kept, action or service, and nothing else changed. With how many steps were moved, and how many
    that send to phone stay as they are."""
    out = copy.deepcopy(config)
    moved = kept = 0
    for step in iter_steps(out.get(steps_key(domain, out))):
        for key in ("action", "service"):
            if isinstance(step.get(key), str) and step[key].strip() == phone:
                if movable_step(step):
                    step[key] = action
                    moved += 1
                else:
                    kept += 1
    return out, moved, kept
