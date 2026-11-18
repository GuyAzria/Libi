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
# [CHANGED v3.96.1 | 2026-11-18] Purpose: ADD, SUB, MUL and DIV take IN3, IN4 ... (more): A + B + C, A / B / C - each
#   divisor not 0 - written and read back the same way (calc_template, calc_block, _pins_of, _math_of), fingerprinted
#   only where a block has them (SIG_EXTRA), and said in the rung's sentence (_calc_words).
# [CHANGED v3.96.2 | 2026-11-18] Purpose: The review of the release (RULE 41): a value that is the words of an
#   entity id - an option media_player.living_room of a list of speakers - is that value (literal), not the
#   variable: edited, it was written as {{ states('media_player.living_room') }}; a MUX input of such words keeps
#   its quotes (_mux_item, calc_block), and a rung's sentence names the words, not a variable (_move_words). A check
#   of both bounds - Home Assistant's "between" - is a RANGE: it was CMP > of the lower one, the upper out of sight.
# [ADDED v1.69.0] Backend parser updated to correctly map native device/state triggers into isTrigger=True Contacts and CMPs without using proprietary blocks.
# [ADDED v3.6.0 | 2026-08-24] Purpose: Three rules that the import now keeps without exception.
#   1. No pin is ever left empty and no registry id is ever shown. Every target is resolved through
#      target_label, which walks entity_id, device_id, area_id, label_id and floor_id in turn.
#   2. A trigger is a boolean contact or a comparison, never a MOVE. Any trigger kind the ladder has
#      no specific drawing for becomes a pulse contact carrying the identity of the event.
#   3. A service that switches something is a coil, not a MOVE. That covers the whole verb family:
#      open and close a cover, lock and unlock, start and stop, play and pause.
# [ADDED v2.0.0 | 2026-08-17] Purpose: Structural importer.
#   1. One normalisation layer for both HA syntaxes (trigger/platform, action/service, plural keys).
#   2. Triggers are OR, so they become parallel branches, never a series of contacts.
#   3. choose / if / parallel become real ladder structure. A choose option becomes its own RUNG whose
#      first element is the trigger of that option, exactly like a PLC programmer would write it.
#   4. and / or / not become series / parallel branches / inverted contacts.
#   5. Nothing is ever dumped as JSON into an element. Anything the ladder cannot express becomes a
#      NATIVE block that shows a service name and a target only, and keeps its original node in raw.
import copy
import json
import logging
import re

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import label_registry as lr

from .const import RECIPIENT_PREFIX
from .tpl_part import parse_template, label_of, text_of, CMP_OPS, MATH_OPS as TPL_MATH_OPS

# [ADDED v3.88.0] The action of a recipient of LIBI Global: script.libi_send_to_<name> (recipients.py).
_RECIPIENT_ACTION_RE = re.compile(r"script\." + re.escape(RECIPIENT_PREFIX) + r"[a-z0-9_]+")


def is_recipient_action(action) -> bool:
    """[ADDED v3.88.0] A recipient of LIBI Global's script, called as an action. It takes the data a phone's notify action
    takes, so its MOVE NOTIFY / TTS block is the one of a phone."""
    return isinstance(action, str) and _RECIPIENT_ACTION_RE.fullmatch(action.strip()) is not None


# [ADDED v3.87.0] The keys of a step that hold more steps. A notification's own data (its buttons are "actions" too) and
# the event data of a trigger are never walked.
_NESTED_STEPS = frozenset(("sequence", "then", "else", "default", "choose", "parallel", "repeat"))


def iter_steps(node):
    """[ADDED v3.89.0] Every step of a list of steps, the nested ones too, in the order they are written - each the dict
    the list holds, so a step changed is changed in the list. called_actions reads with it; LIBI Global replaces a phone
    with its recipient with it (recipients.move_steps)."""
    if isinstance(node, list):
        for one in node:
            yield from iter_steps(one)
    elif isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key in _NESTED_STEPS:
                yield from iter_steps(value)


def called_actions(node) -> list[str]:
    """[ADDED v3.87.0] Every action a list of steps calls, the nested ones too, in the order they are written.
    [CHANGED v3.88.0] Here, from ai.py: LIBI Global reads with it which entries send to a recipient or to a phone."""
    return [step[key].strip() for step in iter_steps(node) for key in ("action", "service")
            if isinstance(step.get(key), str)]

# [ADDED v3.76.0] The days of the week an 8-bit helper holds - the user's design (2026-10-31): bit 1 (1) is Sunday, bit 2
# (2) Monday ... bit 7 (64) Saturday. A CMP DAY that reads a helper is this one template, written exactly so; the card
# shows the bits as checkboxes (frontend/libi-days-row.js). Home Assistant's time condition takes fixed days only.
DAY_BITS_DOMAINS = ("input_number", "number")
DAY_BITS_TEMPLATE = "{{{{ states('{entity}') | int(0) | bitwise_and(2 ** ((now().weekday() + 1) % 7)) > 0 }}}}"
_DAY_BITS_RE = re.compile(r"\{\{ states\('((?:input_number|number)\.[a-z0-9_]+)'\) \| int\(0\) \| bitwise_and\(2 \*\* "
                          r"\(\(now\(\)\.weekday\(\) \+ 1\) % 7\)\) > 0 \}\}")


def day_bits_template(entity: str) -> str:
    """[ADDED v3.76.0] The condition template of CMP DAY = an 8-bit helper."""
    return DAY_BITS_TEMPLATE.format(entity=entity)


def day_bits_entity(template) -> str:
    """[ADDED v3.76.0] The helper a template reads the days of the week from, as DAY_BITS_TEMPLATE writes it; ''
    for any other template, which stays a template block."""
    m = _DAY_BITS_RE.fullmatch(str(template or "").strip())
    return m.group(1) if m else ""

_LOGGER = logging.getLogger(__name__)

# Domains whose state is boolean, so they are drawn as a contact instead of a comparison block.
BOOLEAN_DOMAINS = {
    "binary_sensor", "input_boolean", "switch", "light", "fan", "automation", "script",
    "remote", "siren", "lock", "cover", "person_home", "group", "media_player_bool",
}
# [CHANGED v3.70.0] Domains that are on or off by the clock, drawn as a comparison block and never as a contact. A
# schedule is a weekly calendar: the user's ladder compares times and days with CMP blocks (CMP TIME, CMP DAY), so a
# schedule is CMP DATETIME - the date and time = schedule.x while it is on (_clock_element) - and never a block of
# its own.
COMPARED_DOMAINS = {"schedule"}
BOOL_STATES = {"on", "off", "true", "false", "home", "not_home", "open", "closed", "locked", "unlocked"}
ON_STATES = {"on", "true", "home", "open", "unlocked"}
# [ADDED v3.96.0] Domains whose state is a value - a number, a choice, a text, a date or a time, the moment a button
# was pressed or an event came - and not on or off. A P contact on one is the moment its value changes (libi_to_yaml
# _change_trigger): drawn by hand it was to: "on", which they never reach - "when I pick a colour on the dashboard"
# never ran. The panel has the same lists (libi-panel.js VALUE_DOMAINS, NEVER_ON_DOMAINS).
VALUE_DOMAINS = frozenset((
    "input_number", "number", "counter", "input_select", "select", "input_text", "text", "input_datetime", "date",
    "time", "datetime", "input_button", "button", "event", "timer", "sensor"))
# Those of them no entity of which is ever on or off, whatever it holds - a choice, a text or a sensor can hold the word
# on. A contact that waits for on or off on one never holds: the compiler refuses it.
NEVER_ON_DOMAINS = frozenset((
    "input_number", "number", "counter", "input_datetime", "date", "time", "datetime", "input_button", "button",
    "event", "timer"))
# Not a value: the device dropped off, or has not said yet. The moment a value changes is from one value to another.
NOT_A_VALUE = ("unavailable", "unknown")
# [ADDED v3.96.0] EVERY, a time pattern as its block holds it: "seconds=/10", "hours=* minutes=0" - as the importer
# draws one. Each part a key of Home Assistant's time_pattern trigger, its value *, /N or N.
PATTERN_KEYS = ("hours", "minutes", "seconds")
_PATTERN_PART_RE = re.compile(r"(hours|minutes|seconds)=(\*|/\d+|\d+)")


def pattern_parts(text):
    """[ADDED v3.96.0] The parts of a time pattern its block holds, as the trigger takes them - {"seconds": "/10"},
    a whole number as a number - or None when it is not one."""
    words = str(text if text is not None else "").split()
    parts = {}
    for word in words:
        m = _PATTERN_PART_RE.fullmatch(word)
        if not m or m.group(1) in parts:
            return None
        parts[m.group(1)] = int(m.group(2)) if m.group(2).isdigit() else m.group(2)
    return parts or None


def pattern_words(text):
    """[ADDED v3.96.0] How often a time pattern fires, in words: every 10 seconds, every minute, at minute 0 of every
    hour - or the pattern itself."""
    parts = pattern_parts(text) or {}
    every = [(k, v) for k, v in parts.items() if isinstance(v, str) and v.startswith("/")]
    if len(parts) == 1 and every:
        key, value = every[0]
        n = int(value[1:] or 0)
        unit = key[:-1]
        return f"every {unit}" if n == 1 else f"every {n} {key}"
    return f"on the time pattern {text}"

TURN_ON_SERVICES = ("turn_on", "toggle")
TURN_OFF_SERVICES = ("turn_off",)

# [ADDED v3.6.0] A coil is the ladder symbol for a service that puts something into one of two
# states, so the whole verb family belongs here and not in a MOVE. () energises, (R) de-energises,
# and homeassistant.turn_on stays (S) because it is the latching form.
# [CHANGED v3.24.0] A reset coil means the rung switches something off. Closing a cover is not that.
# A cover has open and closed, not on and off, and close_cover drives a motor exactly as open_cover
# does, so both are commands that make something happen and both latch, which is (S). Only a service
# that genuinely takes something out of service is (R): turning off, stopping, pausing, disarming.
# [CHANGED v3.29.0] A plain coil ( ) is a momentary output: in a scanning controller it is energised
# only while the rung is true and drops the moment it is not. Home Assistant does not scan. An
# automation fires on a trigger, runs once and stops, and the light it turned on stays on. That is a
# latch, so turning something on is (S). The only genuinely momentary thing left is a button press,
# which is an impulse and latches nothing.
COIL_PLAIN_SERVICES = ("press",)

# [ADDED v3.30.0] A toggle is neither a set nor a reset. It flips whatever state the thing is in, so
# it drives the output to the opposite of what it was and gets a symbol of its own, (T).
COIL_TOGGLE_SERVICES = ("toggle",)
COIL_RESET_SERVICES = ("turn_off", "stop", "stop_cover", "stop_valve", "media_pause", "media_stop",
                       "cancel", "disable", "disarm", "alarm_disarm", "close", "turn_off_all")
COIL_SET_SERVICES = ("turn_on", "open_cover", "close_cover", "lock", "unlock",
                     "open_valve", "close_valve", "open", "media_play", "start", "enable",
                     "arm_home", "arm_away", "arm_night",
                     "alarm_arm_home", "alarm_arm_away", "alarm_arm_night", "alarm_arm_vacation")

# Every service that is drawn as a coil at all.
COIL_ALL_SERVICES = (COIL_PLAIN_SERVICES + COIL_RESET_SERVICES
                     + COIL_SET_SERVICES + COIL_TOGGLE_SERVICES)


def coil_for_service(svc):
    """[ADDED v3.24.0] Which coil draws this service, or an empty string when none of them does."""
    name = str(svc or "").split(".")[-1]
    if svc in ("homeassistant.turn_on", "homeassistant.turn_off"):
        return "coil_r" if name == "turn_off" else "coil_s"
    if name in COIL_RESET_SERVICES:
        return "coil_r"
    if name in COIL_TOGGLE_SERVICES:
        return "coil_t"
    if name in COIL_PLAIN_SERVICES:
        return "coil"
    if name in COIL_SET_SERVICES:
        return "coil_s"
    return ""

# [ADDED v3.6.0] Every place Home Assistant can name a target, in the order it resolves them.
TARGET_KEYS = ("entity_id", "device_id", "area_id", "label_id", "floor_id")

# [ADDED v3.6.0] Trigger kinds that carry no entity at all. The ladder draws them as a pulse contact
# and this table says which field holds the identity that goes on the contact and back into the YAML.
EVENT_TRIGGER_KEYS = {
    "conversation": "command",
    "event": "event_type",
    "webhook": "webhook_id",
    "mqtt": "topic",
    "tag": "tag_id",
    "homeassistant": "event",
    "persistent_notification": "update_type",
}

# Services that assign a value to a helper, drawn as MOVE in value mode.
SET_VALUE_SERVICES = {
    "input_datetime.set_datetime": ("time", "date", "timestamp", "datetime"),
    "input_number.set_value": ("value",),
    "input_text.set_value": ("value",),
    "input_select.select_option": ("option",),
    "number.set_value": ("value",),
    "select.select_option": ("option",),
    "text.set_value": ("value",),
    "counter.set_value": ("value",),
}

# [ADDED v3.96.0] The value a MOVE gives each kind of device: the action that sets it and the keys of its data that
# are that value. A light takes several - its brightness, colour, colour temperature or effect, the block says which
# (valueKey); every other kind one. The helpers have their own (SET_VALUE_SERVICES).
LIGHT_VALUE_KEYS = ("brightness_pct", "brightness", "brightness_step_pct", "brightness_step", "rgb_color",
                    "color_name", "hs_color", "xy_color", "rgbw_color", "rgbww_color", "color_temp_kelvin", "effect")
LIST_VALUE_KEYS = ("rgb_color", "hs_color", "xy_color", "rgbw_color", "rgbww_color")
DEVICE_VALUE_SERVICES = {
    "light.turn_on": LIGHT_VALUE_KEYS,
    "fan.set_percentage": ("percentage",),
    "cover.set_cover_position": ("position",),
    "valve.set_valve_position": ("position",),
    "climate.set_temperature": ("temperature",),
    "water_heater.set_temperature": ("temperature",),
    "humidifier.set_humidity": ("humidity",),
    "media_player.volume_set": ("volume_level",),
}
DEVICE_VALUE_DOMAINS = frozenset(svc.split(".")[0] for svc in DEVICE_VALUE_SERVICES)
# A call with one of these besides its value does more than set it: a thermostat's mode, or its two set points.
_MORE_THAN_A_VALUE = ("target_temp_high", "target_temp_low", "hvac_mode", "entity_id")
# [ADDED v3.96.0] The kinds of entity whose state a MOVE can read: an entity id of one of these on its IN pin is a
# variable - the value it holds when the action runs - and never the words of its id.
STATE_DOMAINS = frozenset((
    "air_quality", "alarm_control_panel", "automation", "binary_sensor", "button", "calendar", "camera", "climate",
    "counter", "cover", "date", "datetime", "device_tracker", "event", "fan", "group", "humidifier", "image",
    "input_boolean", "input_button", "input_datetime", "input_number", "input_select", "input_text", "lawn_mower",
    "light", "lock", "media_player", "number", "person", "plant", "remote", "scene", "schedule", "script", "select",
    "sensor", "siren", "sun", "switch", "text", "time", "timer", "todo", "update", "vacuum", "valve", "water_heater",
    "weather", "zone"))
_ENTITY_ID_RE = re.compile(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+")
_LIGHT_ATTRS = ("brightness", "rgb_color", "hs_color", "xy_color", "rgbw_color", "rgbww_color", "color_temp_kelvin",
                "effect")
_HEX_READ = ("{% set c = states('ENTITY') | replace('#', '') %}"
             "{{ [c[0:2] | int(0, 16), c[2:4] | int(0, 16), c[4:6] | int(0, 16)] }}")
_STATES_READ_RE = re.compile(r"\{\{\s*states\(\s*(['\"])([a-z_][a-z0-9_]*\.[a-z0-9_]+)\1\s*\)\s*"
                             r"(?:\|\s*(?:int|float)\s*(?:\(\s*(?:0|0\.0)?\s*\))?\s*)?\}\}")
_READ_ENTITY_RE = re.compile(r"(?:states|state_attr)\(\s*['\"]([a-z_][a-z0-9_]*\.[a-z0-9_]+)['\"]")


def is_entity_ref(text):
    """[ADDED v3.96.0] An entity id of a kind that has a state, as a variable on a pin: input_number.dim, light.desk."""
    s = str(text if text is not None else "").strip()
    return bool(_ENTITY_ID_RE.fullmatch(s)) and s.split(".", 1)[0] in STATE_DOMAINS


def read_template(entity, key=""):
    """[ADDED v3.96.0] The template a MOVE writes for a variable on its IN pin: the value it holds when the action runs.
    A light gives its attribute - a MOVE from one light to another copies its brightness or its colour; a text helper
    a colour written #rrggbb, turned into the list a light takes; anything else its state."""
    ent = str(entity).strip()
    domain = domain_of(ent)
    if domain == "light":
        if key == "brightness_pct":
            return "{{ ((state_attr('" + ent + "', 'brightness') | int(0)) / 2.55) | round(0) }}"
        attr = "rgb_color" if key == "color_name" else key
        if attr in _LIGHT_ATTRS:
            return "{{ state_attr('" + ent + "', '" + attr + "') }}"
    if domain in ("input_text", "text") and key == "rgb_color":
        return _HEX_READ.replace("ENTITY", ent)
    return "{{ states('" + ent + "') }}"


def template_entity(text, key=""):
    """[ADDED v3.96.0] The variable a template reads, when it is one LIBI writes (read_template) or the common way of
    writing one by hand - {{ states('input_number.x') | int }} - or "". So a MOVE of a helper to a light comes back
    with that helper on its IN pin, not as a template."""
    s = str(text if text is not None else "").strip()
    m = _STATES_READ_RE.fullmatch(s)
    if m:
        return m.group(2)
    m = _READ_ENTITY_RE.search(s)
    if m and s == read_template(m.group(1), key):
        return m.group(1)
    return ""


def move_text(value, key=""):
    """[ADDED v3.96.0] A value as the IN pin of a MOVE shows it: a variable read by a template is that variable; a list,
    a colour, is its JSON - [255, 136, 0]; anything else as it is."""
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value))
    if isinstance(value, str):
        return template_entity(value, key) or value
    return value


MATH_OPS = {"+": "math_add", "-": "math_sub", "*": "math_mul", "/": "math_div", "%": "math_mod"}

# [ADDED v3.96.0] The blocks of the Math group as Home Assistant templates - one text both ways: the compiler writes it
# (libi_to_yaml), the importer reads it back as the block (calc_block), so a NET saved and opened again shows the same
# blocks. The user (2026-11-18): "RAND - a random whole number between IN1 and IN2; MOD - the remainder; MUX - input
# number K", each IN a number or a variable, the result into a variable. A variable on a pin is the value it holds when
# the action runs. MATH ADD with a constant on a pin was read back as a MOVE of a long template; now it is MATH again.
CALC_SIGN = {"math_add": "+", "math_sub": "-", "math_mul": "*", "math_div": "/", "math_mod": "%"}
CALC_WORDS = {"math_add": "plus", "math_sub": "minus", "math_mul": "times", "math_div": "divided by", "math_mod": "mod"}
# What a RAND or a MOD sets: a number kept in a helper. A counter is the one the card does not show (ai.CARD_DOMAINS).
NUMBER_OUT_DOMAINS = ("input_number", "number", "counter", "input_text", "text")
_INT_RE = re.compile(r"-?\d+")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_NUM_LIST_RE = re.compile(r"\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*\s*\]")
_ENT = r"([a-z_][a-z0-9_]*\.[a-z0-9_]+)"
# A pin as the compiler writes it, or as one is commonly written by hand: states('x') | int, a whole number, (anything).
_FLOAT_PIN = r"(?:\(states\('" + _ENT + r"'\) \| float\(0\)\)|\(([^()]*)\))"
_INT_PIN = (r"(?:\(states\(\s*'" + _ENT + r"'\s*\)\s*\|\s*int(?:\(\s*0?\s*\))?\s*\)|states\(\s*'" + _ENT
            + r"'\s*\)\s*\|\s*int(?:\(\s*0?\s*\))?|(-?\d+)|\(([^()]*)\))")
_FLOAT_PINS = r"(?:\(states\('[a-z_][a-z0-9_]*\.[a-z0-9_]+'\) \| float\(0\)\)|\([^()]*\))"
_MATH_TPL = re.compile(r"\{\{\s*(" + _FLOAT_PINS + r"(?:\s*[+\-*]\s*" + _FLOAT_PINS + r")+)\s*\}\}")
_DIV_TPL = re.compile(r"\{\{\s*\(\((" + _FLOAT_PINS + r"(?: / " + _FLOAT_PINS + r")+)\) \| round\((\d+)\)\) if ("
                      + _FLOAT_PINS + r" != 0(?: and " + _FLOAT_PINS + r" != 0)*) else ([^ {}]+)\s*\}\}")
_MOD_TPL = re.compile(r"\{\{\s*" + _INT_PIN + r"\s*%\s*" + _INT_PIN + r"\s*\}\}")
_RAND_TPL = re.compile(r"\{\{\s*range\(\s*" + _INT_PIN + r"\s*,\s*" + _INT_PIN + r"\s*\+\s*1\s*\)"
                       r"(\s*\|\s*reject\(\s*'eq'\s*,\s*states\(\s*'" + _ENT + r"'\s*\)\s*\|\s*int\(\s*None\s*\)\s*\)"
                       r"\s*\|\s*list)?\s*\|\s*random\s*\}\}")
_MUX_TPL = re.compile(r"\{\{\s*\[(.*)\]\s*\[\s*" + _INT_PIN + r"\s*\]\s*\}\}", re.S)
_MUX_ITEM = re.compile(r"states\(\s*'" + _ENT + r"'\s*\)|(-?\d+(?:\.\d+)?)|'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|"
                       r"(\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*\s*\])")


def calc_pin(value, cast="float"):
    """[ADDED v3.96.0] A pin of a block of the Math group in its template: a variable is read (an entity id, as MATH
    always read one), a whole number of RAND, MOD or MUX is written as it is, anything else - a number of MATH, an
    expression - in brackets, as MATH always wrote it."""
    s = str(value if value is not None else "").strip()
    if _ENTITY_ID_RE.fullmatch(s):
        return f"(states('{s}') | {cast}(0))"
    if cast == "int" and _INT_RE.fullmatch(s):
        return s
    return f"({s})"


def _mux_item(value):
    """[ADDED v3.96.0] An input of a MUX in its list: a variable read, a number, a colour [r, g, b], or a word quoted."""
    s = str(value if value is not None else "").strip()
    if _ENTITY_ID_RE.fullmatch(s):
        return f"states('{s}')"
    if _NUM_RE.fullmatch(s) or _NUM_LIST_RE.fullmatch(s):
        return s
    if re.fullmatch(r"'[^'\\]*'", s):
        return s  # [ADDED v3.96.2] quoted: words as they are, an entity id's too
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def calc_template(el):
    """[ADDED v3.96.0] The template a block of the Math group writes into the value it sets, or None for any other block.
    MATH as before: (states('a') | float(0)) + (5). MOD: (states('counter.step') | int(0)) % 4. RAND: range(0, 9 + 1) |
    random - with "never the value OUT holds now", the value OUT holds left out of the range. MUX: ['red', 'blue',
    states('input_select.c')][(states('counter.k') | int(0))] - input number K, from 0."""
    t = str(el.get("type") or "")
    a, b = el.get("sourceA", ""), el.get("sourceB", "")
    # [CHANGED v3.96.0] ADD, SUB, MUL and DIV take IN3, IN4 ... (more): A + B + C, A / B / C, each divisor not 0.
    pins = [calc_pin(p) for p in [a, b, *(el.get("more") or [])]]
    if t in ("math_add", "math_sub", "math_mul"):
        return "{{ " + f" {CALC_SIGN[t]} ".join(pins) + " }}"
    if t == "math_div":
        precision, fallback = el.get("precision", 2), el.get("fallback", 0)
        return ("{{ ((" + " / ".join(pins) + ") | round(" + str(precision) + "))"
                " if " + " and ".join(f"{p} != 0" for p in pins[1:]) + " else " + str(fallback) + " }}")
    if t == "math_mod":
        return "{{ " + calc_pin(a, "int") + " % " + calc_pin(b, "int") + " }}"
    if t == "math_rand":
        out = str(el.get("target") or "").strip()
        values = "range(" + calc_pin(a, "int") + ", " + calc_pin(b, "int") + " + 1)"
        if el.get("notSame") and _ENTITY_ID_RE.fullmatch(out):
            values += " | reject('eq', states('" + out + "') | int(None)) | list"
        return "{{ " + values + " | random }}"
    if t == "mux":
        items = ", ".join(_mux_item(v) for v in (el.get("inputs") or []))
        return "{{ [" + items + "][" + calc_pin(el.get("sourceA", ""), "int") + "] }}"
    return None


def _pin_read(groups):
    """[ADDED v3.96.0] What a pin read by the patterns above holds: the entity, the number, or the expression - its last
    group. None for an expression shaped like an entity id, (trigger.idx): written again it would read that "entity"."""
    *named, expr = groups
    value = next((g for g in named if g is not None), None)
    if value is not None:
        return value
    if expr is None or _ENTITY_ID_RE.fullmatch(expr.strip()):
        return None
    return expr.strip()


_FLOAT_PIN_RE = re.compile(_FLOAT_PIN)


def _pins_of(body):
    """[ADDED v3.96.0] The pins of a MATH template in order, and the signs between them - (None, []) when a pin is not
    one LIBI reads (an expression shaped like an entity id)."""
    found = list(_FLOAT_PIN_RE.finditer(body))
    pins = [_pin_read(x.groups()) for x in found]
    ops = [body[x.end():y.start()].strip() for x, y in zip(found, found[1:], strict=False)]
    if not pins or not all(pins) or not all(op in ("+", "-", "*", "/") for op in ops):
        return None, []
    return pins, ops


def _math_of(kind, pins):
    """[ADDED v3.96.0] A MATH block of these pins: IN1, IN2, and IN3 ... in more when there are more."""
    block = {"type": kind, "sourceA": pins[0], "sourceB": pins[1]}
    if len(pins) > 2:
        block["more"] = pins[2:]
    return block


def _split_items(text):
    """[ADDED v3.96.0] The inputs of a MUX's list, split at its own commas - not those inside a quote or a [r, g, b]."""
    items, depth, quote, start, i = [], 0, "", 0, 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append(text[start:i].strip())
            start = i + 1
        i += 1
    items.append(text[start:].strip())
    return items


def calc_block(value, target=""):
    """[ADDED v3.96.0] The block of the Math group a template written into a value is - {"type": ..., "sourceA": ...}
    with the fields the block shows - or None. Only the forms calc_template writes and a few common ones by hand are
    read: anything else stays the MOVE it was, its template as it is."""
    s = str(value if value is not None else "").strip()
    if not s.startswith("{{"):
        return None
    m = _MATH_TPL.fullmatch(s)
    if m:
        pins, ops = _pins_of(m.group(1))
        if pins is None or len(set(ops)) != 1:
            return None
        return _math_of(MATH_OPS[ops[0]], pins)
    m = _DIV_TPL.fullmatch(s)
    if m:
        pins, _ops = _pins_of(m.group(1))
        guards = [_pin_read(x.groups()) for x in _FLOAT_PIN_RE.finditer(m.group(3))]
        if pins is None or guards != pins[1:]:
            return None
        fallback = m.group(4)
        return {**_math_of("math_div", pins), "precision": int(m.group(2)),
                "fallback": int(fallback) if _INT_RE.fullmatch(fallback) else fallback}
    m = _MOD_TPL.fullmatch(s)
    if m:
        g = m.groups()
        a, b = _pin_read(g[0:4]), _pin_read(g[4:8])
        return {"type": "math_mod", "sourceA": a, "sourceB": b} if a and b else None
    m = _RAND_TPL.fullmatch(s)
    if m:
        g = m.groups()
        a, b, not_same, own = _pin_read(g[0:4]), _pin_read(g[4:8]), g[8], g[9]
        if not a or not b or (not_same and own != str(target or "").strip()):
            return None
        return {"type": "math_rand", "sourceA": a, "sourceB": b, "notSame": bool(not_same)}
    m = _MUX_TPL.fullmatch(s)
    if m:
        k = _pin_read(m.groups()[1:5])
        inputs = []
        for item in _split_items(m.group(1)):
            im = _MUX_ITEM.fullmatch(item)
            if not im:
                return None
            ent, num, single, double, listed = im.groups()
            if single is not None or double is not None:
                word = re.sub(r"\\(.)", r"\1", single if single is not None else double)
                # [ADDED v3.96.2] The words of an entity id keep their quotes: they are those words, not the variable.
                inputs.append(f"'{word}'" if _ENTITY_ID_RE.fullmatch(word) else word)
            else:
                inputs.append(ent or num or listed)
        return {"type": "mux", "sourceA": k, "inputs": inputs} if k and len(inputs) >= 2 else None
    return None

# [ADDED v2.1.0] Device triggers, conditions and actions are ordinary ladder elements. The only thing
# that made them look foreign was the registry id, so it is resolved to a real entity id first.
DEVICE_ON_TYPES = {"turned_on", "opened", "unlocked", "home", "detected", "motion", "occupied",
                   "connected", "plugged_in", "present", "running", "hot", "wet", "gas", "smoke",
                   "moist", "light", "sound", "problem", "tampered", "unsafe", "on"}
DEVICE_OFF_TYPES = {"turned_off", "closed", "locked", "not_home", "no_motion", "not_occupied",
                    "disconnected", "unplugged", "not_present", "not_running", "cold", "dry",
                    "no_gas", "no_smoke", "not_moist", "no_light", "no_sound", "no_problem",
                    "not_tampered", "safe", "off"}
DEVICE_PRESS_TYPES = {"pressed", "released", "single", "double", "triple", "long_press", "changed"}


def resolve_entity(ids, value):
    """A device node points at the entity registry, not at an entity id. Turn it into the entity id
    the user actually knows, and fall back to whatever was there if the registry has nothing."""
    val = str(value or "")
    if not val or "." in val:
        return value
    hass = getattr(ids, "hass", None)
    if hass is None:
        return value
    try:
        reg = er.async_get(hass)
        try:
            resolved = er.async_resolve_entity_id(reg, val)
            if resolved:
                return resolved
        except Exception:  # noqa: BLE001
            pass
        getter = getattr(reg.entities, "get_entry_by_id", None)
        if getter:
            entry = getter(val)
            if entry:
                return entry.entity_id
        for entry in reg.entities.values():
            if getattr(entry, "id", None) == val:
                return entry.entity_id
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("[ladder_ha] could not resolve %s: %s", val, err)
    return value


def _slug(text):
    """A readable name turned into something that reads like an entity id on a pin."""
    return re.sub(r"[^a-z0-9_]+", "_", str(text or "").strip().lower()).strip("_")


def _registry_name(ids, kind, value):
    """[ADDED v3.6.0] The readable name behind an area, a label or a floor id."""
    hass = getattr(ids, "hass", None)
    if hass is None or not value:
        return ""
    try:
        if kind == "area":
            entry = ar.async_get(hass).async_get_area(value)
        elif kind == "label":
            entry = lr.async_get(hass).async_get_label(value)
        elif kind == "floor":
            entry = fr.async_get(hass).async_get_floor(value)
        else:
            return ""
        if entry:
            return getattr(entry, "name", "") or ""
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("[libi] could not resolve %s %s: %s", kind, value, err)
    return ""


def entity_of_device(ids, device_id, domain_hint=""):
    """[ADDED v3.6.0] The entity a device action really acts on. When the service says light.turn_off
    the light entity of that device is the one to show, not the first entity the registry returns."""
    hass = getattr(ids, "hass", None)
    if hass is None or not device_id:
        return ""
    try:
        reg = er.async_get(hass)
        entries = [e for e in er.async_entries_for_device(reg, device_id, include_disabled_entities=True)]
        if not entries:
            return ""
        if domain_hint:
            for entry in entries:
                if entry.entity_id.split(".")[0] == domain_hint:
                    return entry.entity_id
        for entry in entries:
            if not getattr(entry, "entity_category", None):
                return entry.entity_id
        return entries[0].entity_id
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("[libi] no entity for device %s: %s", device_id, err)
    return ""


def _first_and_count(value):
    """A target may be a list. Returns the first item and how many more there are."""
    if isinstance(value, (list, tuple)):
        items = [v for v in value if v not in (None, "")]
        return (items[0] if items else ""), max(0, len(items) - 1)
    return value, 0


def target_spec(node):
    """[ADDED v3.7.0] The Home Assistant target block of a node, normalised to lists. This is exactly
    the shape the native target selector reads and writes, so it travels on the element untouched and
    the user can pick entities, devices, areas, labels and floors the same way HA lets them."""
    if not isinstance(node, dict):
        return {}
    holders = [node]
    for key in ("target", "data"):
        if isinstance(node.get(key), dict):
            holders.append(node[key])
    spec = {}
    for kind_key in TARGET_KEYS:
        for holder in holders:
            if kind_key not in holder:
                continue
            value = holder.get(kind_key)
            items = value if isinstance(value, (list, tuple)) else [value]
            for item in items:
                if item in (None, ""):
                    continue
                spec.setdefault(kind_key, [])
                if str(item) not in spec[kind_key]:
                    spec[kind_key].append(str(item))
    return spec


def spec_total(spec):
    """[ADDED v3.8.0] How many things a target block names, across all of its keys."""
    total = 0
    for value in (spec or {}).values():
        total += len(value) if isinstance(value, (list, tuple)) else 1
    return total


def target_summary(label, kind, spec):
    """[ADDED v3.8.0] The OUT pin of a MOVE ACTION. A short readable summary and nothing else, since
    the real target lives in the node itself. Several targets read as a count, a single group reads
    as the kind and its name, and a single entity reads as the entity."""
    total = spec_total(spec)
    if total > 1:
        return f"{total} targets"
    clean = re.sub(r"\s*\+\d+$", "", str(label or "")).strip()
    if not clean:
        return "no target"
    if kind == "entity":
        return clean
    name = clean.split(".", 1)[1] if "." in clean else clean
    return f"{kind.capitalize()}: {name}"


def _move_action(ids, node, svc, label, kind, src):
    """[ADDED v3.8.0] The uniform wrapper for an action the ladder does not draw as a single coil.
    IN carries the Home Assistant service name exactly as it is written there, OUT carries the
    summary, and the node itself travels untouched in raw so nothing is ever lost or invented."""
    el = _el(ids, "move", mode="value", source=svc,
             target=target_summary(label, kind, target_spec(node)),
             service=svc, moveKind="action", raw=node, src=src)
    if isinstance(node, dict) and node.get("continue_on_error") is True:
        el["continueOnError"] = True
    return _attach_target(el, ids, node, label, kind)


def _attach_target(el, ids, node, label, kind):
    """[ADDED v3.7.0] Everything a block needs to know about what it points at: the readable name for
    the pin, which kind of target produced it, and the target block itself for the native picker."""
    spec = target_spec(node)
    if spec:
        el["targetSpec"] = spec
    if kind != "entity":
        el["targetKind"] = kind
        el["targetLabel"] = label
    return el


def target_label(ids, node, domain_hint=""):
    """[ADDED v3.6.0] A readable name for whatever a node points at, plus which kind of target it
    came from. This is the one place that decides what a pin says, and it never returns a registry
    id and never returns an empty string when the node names anything at all."""
    if not isinstance(node, dict):
        return "", "entity"
    holders = [node]
    for key in ("target", "data"):
        if isinstance(node.get(key), dict):
            holders.append(node[key])

    for kind_key in TARGET_KEYS:
        for holder in holders:
            if kind_key not in holder:
                continue
            value, extra = _first_and_count(holder.get(kind_key))
            if value in (None, ""):
                continue
            suffix = f" +{extra}" if extra else ""

            if kind_key == "entity_id":
                ent = resolve_entity(ids, value)
                if ent and not is_registry_id(ent):
                    return f"{ent}{suffix}", "entity"
                value = ent or value
                kind_key = "device_id"  # a registry id in entity_id is really a device row

            if kind_key == "device_id":
                ent = entity_of_device(ids, value, domain_hint)
                if ent:
                    # The name shown is a real entity, but the node still targets the device. The kind
                    # stays device so that replacing the name replaces device_id instead of sitting
                    # next to it and doubling the target.
                    return f"{ent}{suffix}", "device"
                name = resolve_device(ids, value)
                base = _slug(name) if name and not is_registry_id(name) else ""
                return f"{domain_hint or 'device'}.{base or 'device'}{suffix}", "device"

            if kind_key in ("area_id", "label_id", "floor_id"):
                kind = kind_key[:-3]
                name = _registry_name(ids, kind, value)
                base = _slug(name) or _slug(value) or kind
                return f"{kind}.{base}{suffix}", kind

    return "", "entity"


def is_registry_id(value):
    """A 32 character hex string is an entity registry row, not something a person should ever read."""
    return bool(re.fullmatch(r"[0-9a-fA-F]{32}", str(value or "")))


def resolve_device(ids, device_id):
    """A readable device name for the rare node that has no entity at all."""
    hass = getattr(ids, "hass", None)
    if hass is None or not device_id:
        return str(device_id or "")
    try:
        reg = dr.async_get(hass)
        dev = reg.async_get(device_id)
        if dev:
            return dev.name_by_user or dev.name or str(device_id)
    except Exception:  # noqa: BLE001
        pass
    return str(device_id)


def _params_line(data):
    """Service parameters as one readable line. Never a JSON dump."""
    if not isinstance(data, dict):
        return short(data, 60)
    parts = []
    for k, v in data.items():
        if k == "entity_id":
            continue
        if isinstance(v, (dict, list)):
            parts.append(f"{k}=…")
        else:
            parts.append(f"{k}={v}")
    return short(" ".join(parts), 60)


# ==========================================================================================
# NORMALISATION - the single place that knows about the two HA syntaxes
# ==========================================================================================

def norm_kind(node):
    """Trigger kind, old and new syntax."""
    if not isinstance(node, dict):
        return ""
    return str(node.get("trigger") or node.get("platform") or "")


def norm_service(node):
    """Service / action name, old and new syntax."""
    if not isinstance(node, dict):
        return ""
    val = node.get("action") or node.get("service") or ""
    return val if isinstance(val, str) else ""


def norm_list(automation, singular, plural):
    """Trigger / triggers, condition / conditions, action / actions."""
    val = automation.get(plural)
    if val is None:
        val = automation.get(singular)
    if val is None:
        return []
    if isinstance(val, dict):
        return [val]
    if isinstance(val, list):
        return list(val)
    return []


def norm_entity(node):
    """The entity a node acts on, wherever HA decided to put it this year."""
    if not isinstance(node, dict):
        return ""
    ent = node.get("entity_id")
    if not ent and isinstance(node.get("target"), dict):
        ent = node["target"].get("entity_id")
    if not ent and isinstance(node.get("data"), dict):
        ent = node["data"].get("entity_id")
    if isinstance(ent, list):
        ent = ent[0] if ent else ""
    return ent or ""


def domain_of(entity_id):
    s = str(entity_id or "")
    return s.split(".", maxsplit=1)[0] if "." in s else ""


def is_boolean_state(entity_id, state):
    """A contact is only used for a real boolean, everything else is a comparison block."""
    if isinstance(state, (list, tuple)):
        return False
    st = str(state).lower()
    if st not in BOOL_STATES or domain_of(entity_id) in COMPARED_DOMAINS:
        return False
    return domain_of(entity_id) in BOOLEAN_DOMAINS or st in ("on", "off")


def _clock_element(ids, ent, state):
    """[ADDED v3.70.0] A schedule on is CMP DATETIME = schedule, off is CMP DATETIME with cmp_ne: the clock is inside
    the spans the user marked in it, or outside them. None for any other entity or state, so the caller draws it."""
    st = state.lower() if isinstance(state, str) else ""
    if domain_of(ent) not in COMPARED_DOMAINS or st not in ("on", "off"):
        return None
    return _el(ids, "cmp_eq" if st == "on" else "cmp_ne", sourceA="datetime", sourceB=ent)


SIG_FIELDS = ("type", "label", "sourceA", "sourceB", "sourceC", "target", "source", "mode", "title",
              "tts", "stream", "value", "valueKey", "loopType", "weekdays", "precision", "fallback", "kind")
# [ADDED v3.96.0] The fields of RAND (notSame), MUX (inputs) and the IN3, IN4 ... of MATH (more), fingerprinted only
# where a block has them.
SIG_EXTRA = ("inputs", "notSame", "more")


def element_sig(el):
    """Fingerprint of everything the user can edit. Equal fingerprint means the original node is
    still an exact description of this element, so it can be emitted untouched.
    [CHANGED v3.96.0] And the inputs of a MUX and the tick of a RAND (SIG_EXTRA), only on a block that has them: the
    fingerprint of every other block is what it was, so a NET saved before reads as untouched."""
    sig = "|".join(f"{k}={el.get(k, '')}" for k in SIG_FIELDS)
    extra = [f"{k}={json.dumps(el[k]) if isinstance(el[k], (list, dict)) else el[k]}" for k in SIG_EXTRA if k in el]
    return sig + "".join("|" + x for x in extra)


def stamp_sigs(elements):
    for el in elements or []:
        if el.get("type") == "parallel":
            for b in el.get("branches", []):
                stamp_sigs(b)
        elif el.get("type") == "repeat":
            stamp_sigs(el.get("sequence", []))
        # Every piece of a decomposed template or time window is fingerprinted too, so the group can
        # tell whether the user edited any part of it before deciding to reuse the original text.
        # [CHANGED v3.68.0] So is the TON of a wait's time limit, which has no node of its own.
        if isinstance(el.get("raw"), dict) or el.get("tplId") or el.get("timeId") or el.get("waitTimeout"):
            el["sig"] = element_sig(el)


def short(text, limit=60):
    """Never let a payload reach the canvas. One line, capped."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ==========================================================================================
# ELEMENT FACTORY
# ==========================================================================================

class _Ids:
    def __init__(self, prefix="e", hass=None):
        self.n = 0
        self.prefix = prefix
        self.hass = hass

    def next(self):
        self.n += 1
        return f"{self.prefix}{self.n}"


def _el(ids, el_type, **kw):
    el = {"id": ids.next(), "type": el_type, "isTrigger": False}
    el.update(kw)
    return el


def _fallback_move(ids, node, src="", service="", entity="", value=""):
    """[CHANGED v2.1.0] There is no opaque block any more. Anything that is not a contact, a coil, a
    comparison or a timer is a MOVE: these parameters go to this service or entity. Readable, editable
    and standard, and the original node still travels in raw so nothing is lost."""
    svc = service or norm_service(node)
    kind = "entity"
    if entity:
        ent = entity
    else:
        ent, kind = target_label(ids, node, domain_hint=svc.split(".")[0] if svc else "")
        if not ent:
            ent = resolve_entity(ids, norm_entity(node))
    data = node.get("data") if isinstance(node, dict) and isinstance(node.get("data"), dict) else {}
    val = value if value != "" else _params_line(data)
    # [ADDED v3.6.0] A pin is never left blank. With no parameters to show, the verb of the service
    # is what the block is doing, so that is what goes in.
    if str(val).strip() == "":
        val = svc.split(".")[-1].replace("_", " ") if svc else "run"
    el = _el(ids, "move", mode="value", source=val, target=ent or svc or "action", raw=node, src=src)
    if svc and ent:
        el["service"] = svc
    return _attach_target(el, ids, node, ent, kind)


def _dummy_keep_symbols():
    """Kept so target_summary and spec_total are importable from this module by name."""
    return target_summary, spec_total


# ==========================================================================================
# TRIGGERS
# ==========================================================================================

def _numeric_element(ids, ent, above, below, src, node=None, kind=None):
    """[CHANGED v2.3.0] A pair of bounds is a range, full stop. above: 0 is a real limit, not a
    default to be thrown away, so 0 to 500 is drawn as CMP RANGE and never as a plain less than."""
    has_above = above is not None and str(above) != ""
    has_below = below is not None and str(below) != ""
    if has_above and has_below:
        el = _el(ids, "cmp_rng", sourceA=ent, sourceB=above, sourceC=below, src=src)
    elif has_below:
        el = _el(ids, "cmp_lt", sourceA=ent, sourceB=below, src=src)
    elif has_above:
        el = _el(ids, "cmp_gt", sourceA=ent, sourceB=above, src=src)
    else:
        return None
    if kind:
        el["kind"] = kind
    if node is not None:
        el["raw"] = node
    return el


def _device_element(node, ids, src, as_action=False):
    """[ADDED v2.1.0] A device node is drawn with the very same elements as everything else:
    a contact when it is boolean, a comparison when it is numeric, a coil when it switches."""
    ent = resolve_entity(ids, norm_entity(node))
    dtype = str(node.get("type", "")).lower()
    if is_registry_id(ent):
        # The registry could not resolve it, so show the device name rather than a hex string.
        name = resolve_device(ids, node.get("device_id"))
        domain = node.get("domain") or "device"
        ent = f"{domain}.{re.sub(r'[^a-z0-9_]+', '_', str(name).lower()).strip('_')}" if name and not is_registry_id(name) else ent
    label = ent or resolve_device(ids, node.get("device_id"))
    if (not ent or is_registry_id(ent)) and dtype and not as_action:
        dev = resolve_device(ids, node.get("device_id"))
        unnamed = (not dev) or is_registry_id(dev) or str(dev) == str(node.get("device_id"))
        base = (node.get("domain") or "device") if unnamed else re.sub(r"[^a-z0-9_]+", "_", str(dev).lower()).strip("_")
        label = f"{base}.{dtype}"

    # [ADDED v3.26.0] A device node points at a device and a kind of event, never at an entity. The
    # element says so, so the inspector can offer the two fields that really apply and the compiler
    # knows not to write an entity_id into something that has no entity.
    def _mark(el):
        el["deviceNode"] = "action" if as_action else "trigger"
        el["deviceId"] = str(node.get("device_id") or "")
        return el

    if as_action:
        if dtype == "toggle":
            return _mark(_el(ids, "coil_t", label=label, raw=node, src=src))
        if dtype == "turn_on":
            # Same reasoning: a device action that switches something on latches, so it is (S).
            return _mark(_el(ids, "coil_s", label=label, raw=node, src=src))
        if dtype == "turn_off":
            return _mark(_el(ids, "coil_r", label=label, raw=node, src=src))
        return _mark(_fallback_move(ids, node, src=src, service=f"device.{dtype}" if dtype else "device",
                                    entity=label, value=_params_line(node)))

    numeric = _numeric_element(ids, label, node.get("above"), node.get("below"), src, node)
    if numeric is not None:
        return numeric

    # [CHANGED v2.2.0] A device event carries no number, so by the standard it is a boolean and it is
    # drawn as a contact. The device id, the domain and the event type all stay in raw for the way back.
    if dtype in DEVICE_OFF_TYPES:
        return _mark(_el(ids, "contact_nc", label=label, raw=node, src=src))
    if dtype in DEVICE_PRESS_TYPES:
        return _mark(_el(ids, "contact_p", label=label, raw=node, src=src))
    return _mark(_el(ids, "contact_no", label=label, raw=node, src=src))


def _is_trigger_shape(el):
    """[ADDED v3.6.0] Only these three shapes may start a rung: a contact, a comparison, or a group
    of them in parallel. Everything else is an output and has no business carrying isTrigger."""
    kind = str((el or {}).get("type", ""))
    return kind.startswith("contact_") or kind.startswith("cmp_") or kind == "parallel"


def _event_trigger_label(ids, kind, t, ent):
    """[ADDED v3.6.0] What a pulse contact says for a trigger that has no entity. A conversation
    trigger reads conversation.<the sentence>, a webhook reads webhook.<id>, and so on. When the
    trigger does name a real entity that entity wins, because it is the thing the user knows."""
    if ent and "." in str(ent) and not is_registry_id(ent):
        return str(ent)
    resolved, _kind = target_label(ids, t)
    if resolved:
        return resolved
    key = EVENT_TRIGGER_KEYS.get(kind)
    if key:
        value, extra = _first_and_count(t.get(key))
        if value not in (None, ""):
            return f"{kind}.{short(value, 40)}" + (f" +{extra}" if extra else "")
    for fallback in ("event_type", "topic", "command", "webhook_id", "tag_id", "event", "source"):
        value, extra = _first_and_count(t.get(fallback))
        if value not in (None, ""):
            return f"{kind or 'trigger'}.{short(value, 40)}"
    return f"{kind or 'trigger'}.any"


def _trigger_to_element(t, ids, src):
    """A trigger is the same thing as a condition, plus the checkbox that says it starts the flow."""
    kind = norm_kind(t)
    ent = resolve_entity(ids, norm_entity(t))
    el = None

    if kind == "device" or ("device_id" in t and not kind):
        el = _device_element(t, ids, src)

    if kind == "zone":
        op = "cmp_ne" if str(t.get("event", "enter")).lower() == "leave" else "cmp_eq"
        el = _el(ids, op, sourceA=ent, sourceB=t.get("zone", ""))

    elif kind == "state":
        to_state = t.get("to")
        from_state = t.get("from")
        # [CHANGED v3.70.0] A list of one state is that state, as in a condition (v3.28.0): to [on] is a contact.
        if isinstance(to_state, list) and len(to_state) == 1:
            to_state = to_state[0]
        if to_state is None and from_state is None:
            el = _el(ids, "contact_p", label=ent)
        elif isinstance(to_state, list):
            el = _el(ids, "cmp_eq", sourceA=ent, sourceB=", ".join(str(x) for x in to_state))
        elif is_boolean_state(ent, to_state):
            el = _el(ids, "contact_no" if str(to_state).lower() in ON_STATES else "contact_nc", label=ent)
        else:
            el = _clock_element(ids, ent, to_state) or _el(ids, "cmp_eq", sourceA=ent, sourceB=to_state)

    elif kind == "numeric_state":
        el = _numeric_element(ids, ent, t.get("above"), t.get("below"), src)

    elif kind == "time":
        at = t.get("at")
        if isinstance(at, list):
            at = at[0] if at else ""
        if isinstance(at, dict):
            at = at.get("entity_id", "")
        el = _el(ids, "cmp_eq", sourceA="time", sourceB=at)

    elif kind == "template":
        els = template_to_elements(t.get("value_template", ""), ids, src, t)
        el = els[0] if len(els) == 1 else _el(ids, "parallel", branches=[els, []], closed=True)

    elif kind == "sun":
        el = _el(ids, "cmp_eq", sourceA="sun", sourceB=t.get("event", "sunset"))

    elif kind == "time_pattern":
        parts = [f"{k}={v}" for k, v in t.items() if k in ("hours", "minutes", "seconds")]
        el = _el(ids, "cmp_eq", sourceA="time pattern", sourceB=" ".join(parts))

    # [ADDED v3.33.0] Spook adds an all of trigger: several triggers that must all have happened
    # inside a window, in any order. LIBI does not invent it and does not depend on it. It is simply
    # understood on the way in and handed back exactly as it came, so an installation that has Spook
    # sees its logic drawn, and one that does not is never handed a trigger it cannot run.
    if kind in ("spook.all_of", "spook.sequence", "spook.any_of"):
        opts = t.get("options") if isinstance(t.get("options"), dict) else t
        window = opts.get("within") or opts.get("window") or ""
        members = opts.get("triggers") or []
        branches = []
        for i, member in enumerate(members if isinstance(members, list) else []):
            sub = _trigger_to_element(member, ids, f"{src}.all_of[{i}]")
            sub["isTrigger"] = False       # the group as a whole is the trigger, not each member
            branches.append([sub])
        if not branches:
            branches = [[_el(ids, "contact_p", label=f"{kind}.empty", src=src)]]
        group = _el(ids, "parallel", branches=branches, src=src)
        group["raw"] = t
        group["spookGroup"] = kind
        group["spookWindow"] = str(window)
        group["isTrigger"] = True
        return group

    # [ADDED v3.6.0] The rule, enforced in one place: a trigger is a boolean contact or a comparison.
    # A kind with no specific drawing becomes a pulse contact that carries the identity of the event,
    # and the guard below catches any kind nobody has thought of yet, so a MOVE can never be a trigger.
    if el is None:
        el = _el(ids, "contact_p", label=_event_trigger_label(ids, kind, t, ent), src=src)
        key = EVENT_TRIGGER_KEYS.get(kind)
        if key:
            el["eventKind"] = kind

    if not _is_trigger_shape(el):
        el = _el(ids, "contact_p", label=_event_trigger_label(ids, kind, t, ent), src=src)
        if EVENT_TRIGGER_KEYS.get(kind):
            el["eventKind"] = kind

    el["isTrigger"] = True
    el["raw"] = t
    el["src"] = src
    if t.get("id"):
        el["trigId"] = str(t.get("id"))
    return el


# ==========================================================================================
# [ADDED v2.2.0] TEMPLATE DECOMPOSITION
# A Jinja condition is drawn with ordinary elements. or becomes parallel branches, and becomes a
# series, every comparison becomes a CMP block and the arithmetic inside one becomes a MATH block
# that feeds it. The original text travels in raw so an untouched condition compiles back to itself.
# ==========================================================================================

def _tpl_side(node, ids, src, tpl_id, pre):
    """Returns the name to show on the comparison pin, creating MATH blocks for any arithmetic."""
    if isinstance(node, dict) and node.get("kind") == "truth":
        node = node["expr"]
    if isinstance(node, dict) and node.get("kind") == "math":
        a = _tpl_side(node["left"], ids, src, tpl_id, pre)
        b = _tpl_side(node["right"], ids, src, tpl_id, pre)
        el = _el(ids, TPL_MATH_OPS.get(node["op"], "math_add"), sourceA=a, sourceB=b, src=src)
        el["target"] = f"calc.{el['id']}"
        el["tplId"] = tpl_id
        el["expr"] = text_of(node)
        el["dispA"] = a
        el["dispB"] = b
        pre.append(el)
        return el["target"]
    return label_of(node)


def _tpl_truth_element(expr, ids, src, tpl_id):
    """A bare truth test. is_state is a contact, anything else is a comparison against true."""
    if isinstance(expr, dict) and expr.get("kind") == "call" and expr.get("name") == "is_state":
        args = expr.get("args") or []
        if len(args) >= 2:
            ent = label_of(args[0])
            state = str(label_of(args[1])).lower()
            if state in ON_STATES:
                el = _el(ids, "contact_no", label=ent, src=src)
            elif state in BOOL_STATES:
                el = _el(ids, "contact_nc", label=ent, src=src)
            else:
                el = _el(ids, "cmp_eq", sourceA=ent, sourceB=label_of(args[1]), src=src)
            el["tplId"] = tpl_id
            el["expr"] = text_of(expr)
            return el
    name = label_of(expr)
    if isinstance(name, str) and "." in name and " " not in name and not name.startswith("calc."):
        el = _el(ids, "contact_no", label=name, src=src)
    else:
        el = _el(ids, "cmp_eq", sourceA=short(name, 40), sourceB="true", src=src)
        el["dispA"] = short(name, 40)
    el["tplId"] = tpl_id
    el["expr"] = text_of(expr)
    return el


def _tree_to_elements(node, ids, src, tpl_id):
    kind = node.get("kind")

    if kind == "or":
        branches = []
        for part in node["parts"]:
            sub = _tree_to_elements(part, ids, src, tpl_id)
            if sub is None:
                return None
            branches.append(sub)
        par = _el(ids, "parallel", branches=branches, closed=True, src=src)
        par.pop("isTrigger", None)
        par["tplId"] = tpl_id
        return [par]

    if kind == "and":
        out = []
        for part in node["parts"]:
            sub = _tree_to_elements(part, ids, src, tpl_id)
            if sub is None:
                return None
            out.extend(sub)
        return out

    if kind == "not":
        sub = _tree_to_elements(node["part"], ids, src, tpl_id)
        if sub and len(sub) == 1:
            flipped = _invert(sub[0])
            if flipped:
                flipped["id"] = sub[0]["id"]
                flipped["tplId"] = tpl_id
                flipped["expr"] = sub[0].get("expr", "")
                flipped["negated"] = True
                return [flipped]
        return None

    if kind == "cmp":
        pre = []
        a = _tpl_side(node["left"], ids, src, tpl_id, pre)
        b = _tpl_side(node["right"], ids, src, tpl_id, pre)
        el_type = CMP_OPS.get(node["op"], "cmp_eq")
        el = _el(ids, el_type, sourceA=a, sourceB=b, src=src)
        el["tplId"] = tpl_id
        el["exprA"] = text_of(node["left"])
        el["exprB"] = text_of(node["right"])
        el["dispA"] = a
        el["dispB"] = b
        return pre + [el]

    if kind == "truth":
        return [_tpl_truth_element(node["expr"], ids, src, tpl_id)]

    return None


# [ADDED v3.33.0] "It happened lately" written as a template. Home Assistant has no AND over time
# in its triggers, but every entity carries the moment it reached its present state, so the question
# is expressible as an ordinary condition. In ladder that shape is an off delay timer: the contact
# holds for a while after the thing stopped being true, and two of those in series is an AND over
# time without a helper entity anywhere.
_RECENT_RE = re.compile(
    r"^\s*\{\{\s*is_state\(\s*['\"]([a-z_][a-z0-9_]*\.[a-z0-9_]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)"
    r"\s+and\s+\(\s*now\(\)\s*-\s*states\.\1\.last_changed\s*\)\.total_seconds\(\)\s*<\s*(\d+)\s*\}\}\s*$"
)


def seconds_to_hms(total):
    total = int(total)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def hms_to_seconds(text):
    parts = str(text or "").split(":")
    try:
        h, m, s = [int(float(x)) for x in (parts + ["0", "0", "0"])[:3]]
    except (TypeError, ValueError):
        return 0
    return h * 3600 + m * 60 + s


def _recent_to_elements(tpl_text, ids, src, raw_node):
    """A contact followed by an off delay timer, when the template says exactly that and nothing
    more. Anything else falls through to the ordinary template importer."""
    m = _RECENT_RE.match(str(tpl_text or ""))
    if not m:
        return None
    entity, state, seconds = m.group(1), m.group(2), int(m.group(3))
    kind = "contact_no" if str(state).lower() in ON_STATES else "contact_nc"
    contact = _el(ids, kind, label=entity, raw=raw_node, src=src)
    contact["recentState"] = state
    # [CHANGED v3.68.0] timer_toff, the TOF of the palette. timer_tof was a type of its own that the palette did
    # not know, so picking TOF on it turned the window into a state check and a delay.
    tof = _el(ids, "timer_toff", label=seconds_to_hms(seconds), src=src)
    tof["isRecent"] = True
    return [contact, tof]


def template_to_elements(tpl_text, ids, src, raw_node):
    """Never returns None. If the expression cannot be broken down it becomes a single comparison
    against true, which is still a standard block and still compiles back to the original text."""
    tpl_id = f"tpl{ids.next()}"
    tree = parse_template(tpl_text)
    els = _tree_to_elements(tree, ids, src, tpl_id) if tree else None
    if not els:
        el = _el(ids, "cmp_eq", sourceA=short(str(tpl_text).replace("{{", "").replace("}}", "").strip(), 46),
                 sourceB="true", src=src)
        el["tplId"] = tpl_id
        el["expr"] = str(tpl_text)
        el["dispA"] = el["sourceA"]
        els = [el]
    els[0]["raw"] = raw_node
    els[0]["tplRoot"] = True
    els[0]["tplText"] = str(tpl_text)
    return els


# ==========================================================================================
# CONDITIONS
# ==========================================================================================

def _invert(el):
    """not X, done on the element itself whenever the ladder can express it."""
    flip = {
        "contact_no": "contact_nc", "contact_nc": "contact_no",
        "cmp_eq": "cmp_ne", "cmp_ne": "cmp_eq",
        "cmp_gt": "cmp_le", "cmp_le": "cmp_gt",
        "cmp_lt": "cmp_ge", "cmp_ge": "cmp_lt",
    }
    if el.get("type") in flip:
        out = dict(el)
        out["type"] = flip[el["type"]]
        out.pop("raw", None)  # the raw node no longer describes this element
        return out
    return None


def is_template_duration(value):
    """[ADDED v3.58.0] A duration Home Assistant works out when the automation runs: a template, or a
    mapping with a template in one of its parts ({"minutes": "{{ states('input_number.x') }}"})."""
    if isinstance(value, dict):
        return any(is_template_duration(v) for v in value.values())
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def for_to_hms(value):
    """[ADDED v3.27.0] The for of a condition or a trigger, as hh:mm:ss. It arrives either as a
    mapping of hours, minutes and seconds or already as a string.
    [CHANGED v3.58.0] Also the duration of a delay. A part that is no number (a template) used to stop
    the whole import; it is shown as written instead, since there is no fixed time to draw."""
    if isinstance(value, dict):
        try:
            h = int(value.get("hours") or 0)
            m = int(value.get("minutes") or 0)
            s = int(value.get("seconds") or 0)
            if value.get("milliseconds"):
                s += int(int(value["milliseconds"]) / 1000)
        except (TypeError, ValueError):
            return short(", ".join(f"{k} {v}" for k, v in value.items()), 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) == 3:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(float(parts[2])):02d}"
        except (TypeError, ValueError):
            return short(text, 60)
    return short(text, 60)


def duration_label(value):
    """[ADDED v3.68.0] What a TON shows for a delay or for a wait's time limit: hh:mm:ss for a mapping,
    otherwise the value as it was written (a time, a number of seconds or a template)."""
    return for_to_hms(value) if isinstance(value, dict) else str(value)


def _for_seconds(value):
    """Zero means there is nothing to draw, so a for of all zeros is left alone."""
    hms = for_to_hms(value)
    try:
        h, m, s = [int(float(x)) for x in hms.split(":")]
        return h * 3600 + m * 60 + s
    except (TypeError, ValueError):
        return 0


def _attach_for_timer(els, ids, node, src):
    """[ADDED v3.27.0] A condition that has to hold for a while is a contact followed by an on delay
    timer, which is exactly how a ladder says it. The timer carries the id of the contact it belongs
    to, so the way back knows it is that condition's for and not a delay of its own."""
    if not els:
        return els
    value = (node or {}).get("for")
    # [CHANGED v3.58.0] A template has no seconds to count, and was left undrawn - so the way back,
    # which writes no for when there is no timer, dropped it.
    if _for_seconds(value) <= 0 and not is_template_duration(value):
        return els
    ton = _el(ids, "timer_ton", label=for_to_hms(value), src=src)
    # The element ids are handed out again when the net is assembled, so the link is the position:
    # this timer belongs to whatever sits immediately before it. isFor is what says so.
    ton["isFor"] = True
    # [ADDED v3.58.0] The for as it was written: the label is only hh:mm:ss (or a shortened template), so
    # the way back takes this while the label is unchanged, and the user's YAML keeps its shape.
    ton["forValue"] = copy.deepcopy(value)
    return els + [ton]


def _condition_to_elements(c, ids, trig_map, src, parallel_ids=None):
    """[CHANGED v3.27.0] A thin wrapper so every caller gets the for drawn without knowing about it.
    The timer is attached only to a leaf condition, since and, or and not carry no for of their own
    and their children are handled by the recursion inside."""
    els = _condition_to_elements_inner(c, ids, trig_map, src, parallel_ids)
    if isinstance(c, dict) and not any(k in c for k in ("and", "or", "not", "conditions")):
        els = _attach_for_timer(els, ids, c, src)
    return els


def _opaque_condition(ids, c, src):
    """[ADDED v3.96.0] A condition the ladder has no drawing for, as one block that says what it is and is kept exactly
    as it is (RULE 5): the compiler writes its node back whatever the block shows, and the panel does not edit it. A not
    of several checks was drawn without its not, and a condition of a new kind as an action."""
    kind = str(c.get("condition") or next((k for k in ("and", "or", "not") if k in c), "condition"))
    rest = _params_line({k: v for k, v in c.items() if k != "condition"})
    return _el(ids, "cmp_eq", sourceA=short(f"{kind}: {rest}" if rest else kind, 44), sourceB="true", raw=c, src=src,
               opaque=True)


def _condition_to_elements_inner(c, ids, trig_map, src, parallel_ids=None):
    """Returns a LIST of elements in series. or becomes one closed parallel block."""
    # [ADDED v3.96.0] A template written as a bare string - "{{ ... }}" - is a template condition: it was dropped.
    if isinstance(c, str) and c.strip():
        c = {"condition": "template", "value_template": c}
    if not isinstance(c, dict):
        return []

    ctype = str(c.get("condition") or "").lower()

    # [ADDED v3.96.0] An and or an or with a key of its own that changes what it does - turned off (enabled), or
    # anything the ladder does not know - is one block kept as it is: drawn as its checks, the save turned it on.
    # Its alias alone is only a name: it is still drawn (and the round trip check says the name would go). A not
    # keeps its own keys on the block it is drawn as (below).
    if (ctype in ("and", "or") or (not ctype and any(k in c for k in ("and", "or")))) \
            and set(c) - {"condition", "conditions", "and", "or", "alias"}:
        return [_opaque_condition(ids, c, src)]

    # and / or / not, including the shorthand forms {"and": [...]} and {"or": [...]}
    inner = None
    if ctype == "and" or "and" in c:
        inner = c.get("conditions") if ctype == "and" else c.get("and")
        out = []
        for i, sub in enumerate(inner or []):
            out.extend(_condition_to_elements(sub, ids, trig_map, f"{src}.and[{i}]"))
        return out

    if ctype == "or" or "or" in c:
        inner = c.get("conditions") if ctype == "or" else c.get("or")
        branches = []
        for i, sub in enumerate(inner or []):
            branches.append(_condition_to_elements(sub, ids, trig_map, f"{src}.or[{i}]"))
        if not branches:
            return []
        if len(branches) == 1:
            return branches[0]
        par = _el(ids, "parallel", branches=branches, closed=True, src=src)
        par.pop("isTrigger", None)
        return [par]

    if ctype == "not" or "not" in c:
        inner = c.get("conditions") if ctype == "not" else c.get("not")
        inner = inner if isinstance(inner, list) else ([inner] if inner else [])
        # [CHANGED v3.96.0] Each check of a not is drawn as its opposite - not [a, b] is "not a" and "not b". One the
        # ladder cannot turn round (a check held for a time, a time window, an or ...) makes the whole not one block
        # kept as it is: it was drawn WITHOUT its not, the logic the other way round.
        flipped = []
        for i, sub in enumerate(inner):
            els = _condition_to_elements(sub, ids, trig_map, f"{src}.not[{i}]")
            turned = _invert(els[0]) if len(els) == 1 else None
            if not turned:
                flipped = None
                break
            turned["id"] = els[0]["id"]
            flipped.append((turned, sub))
        if not inner:
            return []
        if flipped and len(flipped) == 1:
            flipped[0][0]["raw"] = c
            flipped[0][0]["src"] = src
            return [flipped[0][0]]
        if flipped and set(c) <= {"condition", "conditions", "not"}:
            for i, (turned, sub) in enumerate(flipped):
                turned["raw"] = {"condition": "not", "conditions": [sub]}
                turned["src"] = f"{src}.not[{i}]"
            return [turned for turned, _sub in flipped]
        return [_opaque_condition(ids, c, src)]

    ent = resolve_entity(ids, norm_entity(c))

    if ctype == "trigger":
        # The reference to a trigger is drawn as the trigger itself, marked as a trigger.
        ids_ref = c.get("id")
        ref_list = ids_ref if isinstance(ids_ref, list) else [ids_ref]
        out = []
        for rid in ref_list:
            # [CHANGED v3.96.0] Every trigger of that id: Home Assistant lets several share one.
            for src_el in trig_map.get(str(rid)) or []:
                copy = dict(src_el)
                copy["id"] = ids.next()
                copy["isTrigger"] = True
                copy["src"] = src
                out.append(copy)
        if out:
            return out
        return [_el(ids, "cmp_eq", sourceA="trigger", sourceB=short(ids_ref, 24), raw=c, src=src, isTrigger=True)]

    if ctype == "state":
        st = c.get("state")
        # [CHANGED v3.28.0] A list holding one state means the same thing as that state written
        # plainly, and the Home Assistant editor writes it either way. It was drawn as a comparison
        # while the plain form was drawn as a contact, so the same condition looked like two
        # different things depending on which editor last touched it. One item unwraps.
        if isinstance(st, list) and len(st) == 1:
            st = st[0]
        if isinstance(st, list):
            el = _el(ids, "cmp_eq", sourceA=ent, sourceB=", ".join(str(x) for x in st))
        elif is_boolean_state(ent, st):
            el = _el(ids, "contact_no" if str(st).lower() in ON_STATES else "contact_nc", label=ent)
        else:
            el = _clock_element(ids, ent, st) or _el(ids, "cmp_eq", sourceA=ent, sourceB=st)
        el["raw"] = c
        el["src"] = src
        return [el]

    if ctype == "numeric_state":
        # [CHANGED v3.96.2] Both bounds - what Home Assistant's editor writes for "between" - are one RANGE, as a
        # trigger's and a device check's are (_numeric_element). Drawn as CMP > of the lower one, the upper one was out
        # of sight, and gone from the file once the block was edited. A not of one is one block kept as it is (_invert).
        if c.get("above") is not None and c.get("below") is not None:
            el = _el(ids, "cmp_rng", sourceA=ent, sourceB=c.get("above"), sourceC=c.get("below"))
        elif c.get("above") is not None:
            el = _el(ids, "cmp_gt", sourceA=ent, sourceB=c.get("above"))
        elif c.get("below") is not None:
            el = _el(ids, "cmp_lt", sourceA=ent, sourceB=c.get("below"))
        else:
            return [_el(ids, "cmp_eq", sourceA=ent, sourceB="?", raw=c, src=src)]
        el["raw"] = c
        el["src"] = src
        return [el]

    if ctype == "template":
        # [ADDED v3.76.0] The days an 8-bit helper holds: CMP DAY = that helper.
        bits = day_bits_entity(c.get("value_template"))
        if bits:
            return [_el(ids, "cmp_eq", sourceA="weekday", sourceB=bits, kind="date", raw=c, src=src)]
        recent = _recent_to_elements(c.get("value_template", ""), ids, src, c)
        if recent:
            return recent
        return template_to_elements(c.get("value_template", ""), ids, src, c)

    if ctype == "zone":
        el = _el(ids, "cmp_eq", sourceA=ent, sourceB=c.get("zone", ""), raw=c, src=src)
        return [el]

    if ctype == "time":
        # [CHANGED v2.2.0] No TIME WINDOW block. A time window is a range comparison on the clock and
        # the weekday list is a comparison of its own, both standard blocks.
        out = []
        after, before = c.get("after", ""), c.get("before", "")
        if after and before:
            el = _el(ids, "cmp_rng", sourceA="time", sourceB=after, sourceC=before, kind="time", src=src)
        elif after:
            el = _el(ids, "cmp_ge", sourceA="time", sourceB=after, kind="time", src=src)
        elif before:
            el = _el(ids, "cmp_le", sourceA="time", sourceB=before, kind="time", src=src)
        else:
            el = None
        if el is not None:
            out.append(el)
        days = c.get("weekday")
        if days:
            out.append(_el(ids, "cmp_eq", sourceA="weekday",
                           sourceB=", ".join(days) if isinstance(days, list) else str(days),
                           kind="date", src=src))
        if not out:
            out.append(_el(ids, "cmp_eq", sourceA="time", sourceB="", kind="time", src=src))
        out[0]["raw"] = c
        out[0]["timeRoot"] = True
        for e in out:
            e["timeId"] = out[0]["id"]
        return out

    if ctype == "sun":
        el = _el(ids, "cmp_eq", sourceA="sun", sourceB=c.get("after") or c.get("before") or "", raw=c, src=src)
        return [el]

    if ctype == "device" or "device_id" in c:
        el = _device_element(c, ids, src)
        return [el]

    # [CHANGED v3.96.0] A kind the ladder has no drawing for is one block kept as it is. It was drawn as a MOVE, which
    # the compiler wrote as an action: the condition gone, and a call of a service that does not exist in its place.
    return [_opaque_condition(ids, c, src)]


# ==========================================================================================
# ACTIONS
# ==========================================================================================

def _device_value(ids, a, svc, ent, target_kind, data, src):
    """[ADDED v3.96.0] A device given one value - a light's brightness or colour, a fan's speed, a cover's position, a
    thermostat's temperature, a player's volume - as a MOVE of that value to it, as a helper is set: the user sees and
    edits 50 %, and a colour is a colour. None for anything else - several values, several targets, an entity in the
    data - which keeps the drawing it had: a coil, or the MOVE ACTION."""
    keys = DEVICE_VALUE_SERVICES.get(svc)
    if not keys or target_kind != "entity" or domain_of(ent) != svc.split(".")[0]:
        return None
    if spec_total(target_spec(a)) != 1 or any(k in data for k in _MORE_THAN_A_VALUE):
        return None
    present = [k for k in keys if k in data]
    if len(present) != 1:
        return None
    key = present[0]
    # [ADDED v3.96.0] A device given input number K of a list - the colours, one after another - is a MUX.
    block = calc_block(data[key], ent)
    if block and block["type"] == "mux":
        el = _el(ids, "mux", sourceA=block["sourceA"], inputs=block["inputs"], target=ent, valueKey=key, raw=a, src=src)
    else:
        el = _el(ids, "move", mode="value", source=move_text(data[key], key), target=ent, valueKey=key, raw=a,
                 src=src)
    if a.get("continue_on_error") is True:
        el["continueOnError"] = True
    return el


def _detect_math(template):
    """Pulls a + b, a - b, a * b or a / b out of a value template."""
    s = str(template or "")
    ents = re.findall(r"states\(\s*['\"]([^'\"]+)['\"]\s*\)", s)
    if len(ents) < 2:
        return None
    stripped = re.sub(r"states\(\s*['\"][^'\"]+['\"]\s*\)", "@", s)
    stripped = re.sub(r"\|\s*float\([^)]*\)", "", stripped)
    m = re.search(r"@\s*\)?\s*([\+\-\*/])\s*\(?\s*@", stripped)
    if not m:
        return None
    return MATH_OPS.get(m.group(1)), ents[0], ents[1]


def _notify_payload(node):
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    message = data.get("message", "")
    title = data.get("title", "")
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    tts = nested.get("tts_text", "")
    stream = nested.get("media_stream", "")
    is_tts = bool(tts) or str(message).strip().upper() == "TTS"
    return message, title, tts, stream, is_tts, data


# [ADDED v3.68.0] A wait for trigger goes on at the moment the thing changes, so a contact drawn for it is the
# edge contact of the same kind: |P| for a change to on, |N| for a change to off.
WAIT_EDGE = {"contact_no": "contact_p", "contact_nc": "contact_n"}


def wait_parts(el):
    """[ADDED v3.68.0] The branches of a wait as they are drawn: what it waits for, one block each, and the TON
    of its time limit. A wait for one thing is that one block."""
    return [[el]] if el.get("waitOne") else list(el.get("branches") or [])


def _wait_to_element(a, ids, src):
    """[ADDED v3.68.0] A wait for trigger, drawn with the user's own blocks. Each trigger it waits for is the
    contact or CMP it is at the head of a rung; several are a closed PARALLEL, one branch each, since any one of
    them lets the run go on; a time limit is one more branch, a TON with the limit as its preset. The block that
    stands for the wait carries the node (waitFor) and the shape it was drawn in (waitShape), so the way back
    can tell an untouched wait from an edited one."""
    wt = a.get("wait_for_trigger")
    branches = []
    for i, t in enumerate(wt if isinstance(wt, list) else [wt]):
        if not isinstance(t, dict):
            continue
        el = _trigger_to_element(t, ids, f"{src}.wait_for_trigger[{i}]")
        el["isTrigger"] = False  # it lets the run go on, it does not start the automation
        el.pop("trigId", None)
        el["type"] = WAIT_EDGE.get(el["type"], el["type"])
        branches.append([el])
    if a.get("timeout") not in (None, ""):
        ton = _el(ids, "timer_ton", label=duration_label(a["timeout"]), src=src)
        ton["waitTimeout"] = True
        branches.append([ton])
    if len(branches) == 1:
        root = branches[0][0]
        root["waitOne"] = True
    else:
        root = _el(ids, "parallel", branches=branches or [[], []], closed=True, src=src)
        root.pop("isTrigger", None)
    root["waitFor"] = a
    root["waitShape"] = [len(b) for b in wait_parts(root)]
    return root


def _action_to_elements(a, ids, trig_map, src):
    """Returns a list of elements. Structural actions expand into ladder structure, never into JSON."""
    if not isinstance(a, dict):
        return [_fallback_move(ids, {"raw": a}, src=src, service="action", value=short(a, 60))]

    # --- structure -------------------------------------------------------------------
    if "repeat" in a:
        rep = a["repeat"] or {}
        el = _el(ids, "repeat", sequence=[], raw=a, src=src)
        el["loopType"], el["value"] = repeat_loop(rep)
        seq = []
        for i, child in enumerate(rep.get("sequence", []) or []):
            seq.extend(_action_to_elements(child, ids, trig_map, f"{src}.repeat[{i}]"))
        el["sequence"] = seq
        return [el]

    if "parallel" in a:
        branches = []
        wrapped = []
        for i, child in enumerate(a.get("parallel") or []):
            wrapped.append(isinstance(child, dict) and "sequence" in child)
            if isinstance(child, dict) and "sequence" in child:
                branch = []
                for j, sub in enumerate(child.get("sequence") or []):
                    branch.extend(_action_to_elements(sub, ids, trig_map, f"{src}.parallel[{i}][{j}]"))
            else:
                branch = _action_to_elements(child, ids, trig_map, f"{src}.parallel[{i}]")
            branches.append(branch)
        if not branches:
            return []
        while len(branches) < 2:
            branches.append([])
        par = _el(ids, "parallel", branches=branches, closed=True, raw=a, src=src)
        par["branchWrapped"] = wrapped
        par.pop("isTrigger", None)
        return [par]

    if "delay" in a:
        d = a["delay"]
        # [CHANGED v3.58.0] for_to_hms, which also takes a template: int() of one stopped the import.
        return [_el(ids, "timer_ton", label=duration_label(d), raw=a, src=src)]

    if "wait_for_trigger" in a:
        # [CHANGED v3.68.0] Drawn with what it waits for. There is no WAIT block in the ladder.
        return [_wait_to_element(a, ids, src)]

    if "wait_template" in a:
        return template_to_elements(a.get("wait_template", ""), ids, src, a)

    if "condition" in a and not norm_service(a):
        return _condition_to_elements(a, ids, trig_map, src)

    # --- services --------------------------------------------------------------------
    svc = norm_service(a)
    if svc:
        domain = svc.split(".")[0]
        # [CHANGED v3.6.0] One resolution for every action, so a device, an area or a label target
        # shows a real name instead of leaving the pin empty.
        ent, target_kind = target_label(ids, a, domain_hint=domain)
        if not ent:
            ent = resolve_entity(ids, norm_entity(a))
            target_kind = "entity"
        data = a.get("data") if isinstance(a.get("data"), dict) else {}

        # [CHANGED v3.88.0] A recipient of LIBI Global takes what a phone takes: the same block, sending to it.
        if domain == "notify" or svc.startswith("notify.") or is_recipient_action(svc):
            message, title, tts, stream, is_tts, _d = _notify_payload(a)
            mode = "tts" if is_tts else "notify"
            el = _el(ids, "move", mode=mode, target=svc,
                     source="" if is_tts else message,
                     title=title, tts=tts, stream=stream, raw=a, src=src)
            return [el]

        if svc in ("tts.speak", "tts.cloud_say", "tts.google_translate_say") or domain == "tts":
            el = _el(ids, "move", mode="tts", target=ent or svc,
                     tts=data.get("message", data.get("cache", "")), raw=a, src=src)
            return [el]

        if svc == "counter.increment":
            # [CHANGED v3.6.0] A counter with no step given steps by one. That is a real value and it
            # goes on the pin, where a question mark used to be written into the file itself.
            return [_el(ids, "ctu", source=ent, value=str(data.get("value", "")) or "1", raw=a, src=src)]

        if svc in SET_VALUE_SERVICES:
            keys = SET_VALUE_SERVICES[svc]
            val = ""
            key_used = ""
            for k in keys:
                if k in data:
                    val = data.get(k)
                    key_used = k
                    break
            # [ADDED v3.96.0] A block of the Math group - MATH, MOD, RAND, MUX - as LIBI writes it (calc_block).
            block = calc_block(val, ent)
            if block:
                if block["type"] == "mux":
                    block["valueKey"] = key_used  # as a MOVE: an input_datetime is set by its time or its date
                el = _el(ids, block.pop("type"), **block, target=ent, raw=a, src=src)
                if a.get("continue_on_error") is True:
                    el["continueOnError"] = True
                return [el]
            math = _detect_math(val)
            if math and math[0]:
                op_type, a_ent, b_ent = math
                return [_el(ids, op_type, sourceA=a_ent, sourceB=b_ent, target=ent, raw=a, src=src)]
            # [CHANGED v3.96.0] A helper read by a template is that helper on the IN pin (move_text); continue_on_error
            # is the block's own tick - without it the node was not the block's any more, and was compiled again.
            el = _el(ids, "move", mode="value", source=move_text(val, key_used), target=ent, valueKey=key_used, raw=a,
                     src=src)
            # [ADDED v3.96.2] The words of an entity id given as the value - an option of a list of speakers - are
            # those words, never the variable: written again they stay words (libi_to_yaml._move_input).
            if isinstance(val, str) and is_entity_ref(val):
                el["literal"] = True
            if a.get("continue_on_error") is True:
                el["continueOnError"] = True
            return [el]

        moved = _device_value(ids, a, svc, ent, target_kind, data, src)
        if moved:
            return [moved]

        # [CHANGED v3.6.0] Any service that switches something between two states is a coil. Closing
        # a cover, locking a lock and stopping a player are resets, opening and unlocking and playing
        # are sets, and only homeassistant.turn_on and turn_off keep the latching (S) form.
        # [CHANGED v3.8.0] A coil is the drawing for one switch. It stays a coil only when the action
        # names exactly one thing that resolves to an entity. The moment an action points at several
        # targets, or at a group such as a label, an area or a floor, it is a MOVE ACTION instead:
        # the ladder cannot honestly draw seventeen lights as one contact on a rung.
        coil = coil_for_service(svc)
        if coil:
            spec = target_spec(a)
            single_entity = spec_total(spec) <= 1 and target_kind in ("entity", "device")
            if single_entity:
                # [CHANGED v3.24.0] The coil now carries the service it came from and whether the
                # rung is allowed to carry on when it fails. Without the service the block could say
                # cover but never close cover, and there was nothing for the inspector to edit.
                el = _el(ids, coil, label=ent, service=svc, raw=a, src=src)
                if a.get("continue_on_error") is True:
                    el["continueOnError"] = True
                return [_attach_target(el, ids, a, ent, target_kind)]
            return [_move_action(ids, a, svc, ent, target_kind, src)]

        return [_move_action(ids, a, svc, ent, target_kind, src)]

    if "device_id" in a:
        return [_device_element(a, ids, src, as_action=True)]

    if "variables" in a and isinstance(a["variables"], dict):
        out = []
        for k, v in a["variables"].items():
            out.append(_el(ids, "move", mode="value", source=short(v, 60), target=k,
                           service="variables", raw=a, src=src))
        return out or [_fallback_move(ids, a, src=src, service="variables")]

    if "stop" in a:
        return [_el(ids, "move", mode="value", source=short(a.get("stop", ""), 40), target="stop",
                    service="stop", raw=a, src=src)]

    if "event" in a:
        return [_el(ids, "move", mode="value", source=_params_line(a.get("event_data") or {}) or "fire",
                    target=str(a.get("event", "")), service="event", raw=a, src=src)]

    # [CHANGED v3.8.0] The reply a voice assistant speaks back is spoken text, so it is the MOVE TTS
    # block that already exists. No new kind of block is invented for it.
    if "set_conversation_response" in a:
        return [_el(ids, "move", mode="tts", tts=short(a.get("set_conversation_response", ""), 60),
                    target="conversation.response", service="set_conversation_response",
                    raw=a, src=src)]

    # [CHANGED v3.6.0] The last resort still never shows a payload. The first key of the node names
    # what it is and its value fills the pin, so no element ever displays braces.
    if isinstance(a, dict) and a:
        key = next(iter(a))
        value = a.get(key)
        text = _params_line(value) if isinstance(value, dict) else short(value, 60)
        return [_el(ids, "move", mode="value", source=text or str(key).replace("_", " "),
                    target=str(key), service=str(key), raw=a, src=src)]

    return [_fallback_move(ids, a, src=src, value=short(a, 60))]


def fold_notify_pairs(elements):
    """A notification followed by its spoken twin is one MOVE block in NOTIFY/TTS mode.
    Both original nodes are kept, so compiling back produces exactly the same two actions."""
    out = []
    i = 0
    while i < len(elements):
        el = elements[i]
        nxt = elements[i + 1] if i + 1 < len(elements) else None
        if (el.get("type") == "move" and el.get("mode") == "notify" and
                nxt and nxt.get("type") == "move" and nxt.get("mode") == "tts" and
                el.get("target") and el.get("target") == nxt.get("target")):
            merged = dict(el)
            merged["mode"] = "both"
            merged["tts"] = nxt.get("tts", "")
            merged["stream"] = nxt.get("stream", "")
            merged["raw2"] = nxt.get("raw")
            out.append(merged)
            i += 2
            continue
        if el.get("type") == "parallel":
            el = dict(el)
            el["branches"] = [fold_notify_pairs(b) for b in el.get("branches", [])]
        elif el.get("type") == "repeat":
            el = dict(el)
            el["sequence"] = fold_notify_pairs(el.get("sequence", []))
        out.append(el)
        i += 1
    return out


def _mark_from_action(elements):
    """A block that sits in the action sequence keeps its place there. A condition written inside a
    sequence is a series contact in the middle of the rung, not part of the rung gate."""
    for el in elements or []:
        el["fromAction"] = True
    return elements


def repeat_loop(rep):
    """[ADDED v3.57.0] (loopType, value) a REPEAT block shows for a repeat node. The value is a summary for
    the eye (a while template is shortened), so the compiler compares against it and keeps the node's own
    loop when the user did not change it."""
    rep = rep if isinstance(rep, dict) else {}
    if "count" in rep:
        return "count", str(rep.get("count"))
    if "for_each" in rep:
        fe = rep.get("for_each")
        return "for_each", ", ".join(str(x) for x in fe) if isinstance(fe, list) else str(fe)
    if "while" in rep:
        return "while", short(_first_template(rep.get("while")), 40)
    if "until" in rep:
        return "until", short(_first_template(rep.get("until")), 40)
    return "count", "1"


def _first_template(cond_list):
    if isinstance(cond_list, list):
        for c in cond_list:
            if isinstance(c, dict) and c.get("value_template"):
                return c["value_template"]
    if isinstance(cond_list, dict):
        return cond_list.get("value_template", "")
    return str(cond_list or "")


# ==========================================================================================
# [ADDED v2.3.0] PLAIN ENGLISH RUNG DESCRIPTION
# The comment line above each rung is filled in on import, so an imported automation reads like a
# sentence before the user has written a single note.
# ==========================================================================================

def friendly(value):
    """sensor.valve_garden_summation_delivered becomes valve garden summation delivered."""
    text = str(value or "").strip()
    if not text:
        return "it"
    # [ADDED v3.88.0] A recipient of LIBI Global is said by its name: script.libi_send_to_guy is guy.
    if is_recipient_action(text):
        text = text.split(".", 1)[1][len(RECIPIENT_PREFIX):]
    elif "." in text and " " not in text:
        text = text.split(".", 1)[1]
    return text.replace("_", " ").strip() or "it"


def _describe_wait(el, calc):
    """[ADDED v3.68.0] wait until the meter is above the litres or the valve switches off, for at most 00:30:00"""
    parts, limit = [], ""
    for branch in wait_parts(el):
        for x in branch:
            if x.get("waitTimeout"):
                limit = str(x.get("label", ""))
                continue
            text = _describe_el({k: v for k, v in x.items() if k != "waitFor"}, False, calc)
            if text:
                parts.append(text)
    text = "wait until " + " or ".join(parts) if parts else "wait"
    if limit:
        stops = el["waitFor"].get("continue_on_timeout") is False
        text += f", stopping after {limit}" if stops else f", for at most {limit}"
    return text


def _describe_el(el, as_trigger=False, calc=None):
    calc = calc if calc is not None else {}
    t = el.get("type", "")
    if isinstance(el.get("waitFor"), dict):
        return _describe_wait(el, calc)
    if t == "parallel":
        parts = []
        for b in el.get("branches", []):
            inner = " and ".join(x for x in (_describe_el(e, as_trigger, calc) for e in b) if x)
            if inner:
                parts.append(inner)
        if not parts:
            return ""
        return "either " + " or ".join(parts) if len(parts) > 1 else parts[0]

    a = calc.get(str(el.get("sourceA")), friendly(el.get("sourceA")))
    b = el.get("sourceB")
    raw = el.get("raw") if isinstance(el.get("raw"), dict) else {}
    lbl = friendly(el.get("label"))
    if raw.get("device_id"):
        # a device event reads better as a whole name than as a domain and a state
        if is_registry_id(el.get("label")):
            lbl = f"the {raw.get('domain', 'device')}"
        else:
            lbl = str(el.get("label") or "").replace(".", " ").replace("_", " ").strip() or lbl
        if not (raw.get("above") is not None or raw.get("below") is not None):
            if t.startswith("contact"):
                return f"{lbl} happens" if as_trigger else f"{lbl} is active"

    if t == "contact_no":
        return f"{lbl} turns on" if as_trigger else f"{lbl} is on"
    if t == "contact_nc":
        return f"{lbl} turns off" if as_trigger else f"{lbl} is off"
    if t == "cmp_eq" and str(el.get("sourceA")) == "time pattern":
        return pattern_words(el.get("sourceB"))  # [ADDED v3.96.0] EVERY
    if t == "contact_p" and as_trigger and domain_of(el.get("label")) in VALUE_DOMAINS:
        # [ADDED v3.96.0] the moment a value changes, as the compiler writes a P contact on one
        return f"{lbl} is pressed" if domain_of(el.get("label")) in ("input_button", "button") else f"{lbl} changes"
    if t == "contact_p":
        return f"{lbl} is triggered" if as_trigger else f"{lbl} switches on"
    if t == "contact_n":
        return f"{lbl} switches off"
    if t == "cmp_rng":
        if str(el.get("sourceA")) == "time":
            return f"the time is between {b} and {el.get('sourceC')}"
        return f"{a} is between {b} and {el.get('sourceC')}"
    if t in ("cmp_gt", "cmp_ge"):
        return f"{a} is above {b}" if str(el.get("sourceA")) != "time" else f"the time is after {b}"
    if t in ("cmp_lt", "cmp_le"):
        return f"{a} is below {b}" if str(el.get("sourceA")) != "time" else f"the time is before {b}"
    if t in ("cmp_eq", "cmp_ne") and str(el.get("sourceA")) == "datetime" and domain_of(b) in COMPARED_DOMAINS:
        # [ADDED v3.70.0] CMP DATETIME against a schedule: it starts and ends by the clock.
        if as_trigger:
            return f"the schedule {friendly(b)} {'starts' if t == 'cmp_eq' else 'ends'}"
        return f"the time is {'inside' if t == 'cmp_eq' else 'outside'} the schedule {friendly(b)}"
    if t == "cmp_eq":
        src = str(el.get("sourceA"))
        if src == "time":
            return f"the time is {friendly(b)}"
        if src == "weekday":
            # [ADDED v3.76.0] The days an 8-bit helper holds.
            if domain_of(b) in DAY_BITS_DOMAINS:
                return f"the day is ticked in {friendly(b)}"
            return f"the day is {b}"
        if src == "datetime":
            return f"the date and time is {friendly(b)}"
        if src == "sun":
            return f"the sun is at {b}"
        if str(b).startswith("zone."):
            return f"{a} arrives at {friendly(b)}" if as_trigger else f"{a} is at {friendly(b)}"
        return f"{a} is {b}"
    if t == "cmp_ne":
        if str(b).startswith("zone."):
            return f"{a} leaves {friendly(b)}"
        return f"{a} is not {b}"
    if t.startswith("math_") or t == "mux":
        return _calc_words(el)
    if t == "coil_r":
        return f"turn off {lbl}"
    if t == "coil_t":
        return f"toggle {lbl}"
    if t in ("coil", "coil_s"):
        return f"turn on {lbl}"
    if t == "move":
        mode = el.get("mode", "value")
        target = friendly(el.get("target"))
        if mode == "value" and el.get("service"):
            return f"call {friendly(el['service'])} on {target}"
        if mode == "notify":
            return f"send a notification to {target}"
        if mode == "tts":
            return f"speak on {target}"
        if mode == "both":
            return f"notify and speak on {target}"
        # [CHANGED v3.96.0] And what it sets, to what (_move_words).
        words = _move_words(el)
        return f"set {target} {words}" if words else f"set {target}"
    if t == "notify":
        return f"send a notification to {friendly(el.get('target'))}"
    if t == "ctu":
        return f"count up {friendly(el.get('source'))}"
    if t in ("timer_ton", "timer_toff") and not el.get("isRecent"):
        return f"wait {el.get('label', '')}"
    if t == "repeat":
        inner = ", ".join(x for x in (_describe_el(e, False, calc) for e in el.get("sequence", [])) if x)
        return f"repeat {el.get('value', '')} times ({inner})" if inner else f"repeat {el.get('value', '')} times"
    return ""


# [ADDED v3.96.0] What a MOVE sets, in words, and the unit of its value.
_KEY_WORDS = {"brightness_pct": "brightness", "brightness_step_pct": "brightness by", "brightness_step": "brightness by",
              "rgb_color": "color", "color_name": "color", "color_temp_kelvin": "color temperature", "percentage": "speed",
              "volume_level": "volume", "value": "", "option": "", "time": "", "date": "", "datetime": "", "timestamp": ""}
_KEY_UNITS = {"brightness_pct": " %", "brightness_step_pct": " %", "percentage": " %", "position": " %", "humidity": " %",
              "color_temp_kelvin": " K"}


def _sets_value(el):
    """[ADDED v3.96.0] The target of a MOVE that sets a value (not a call of something else, not a message), or ""."""
    if el.get("type") != "move" or el.get("mode", "value") != "value" or el.get("service") or el.get("moveKind") == "action":
        return ""
    return str(el.get("target") or "")


def _calc_words(el):
    """[ADDED v3.96.0] What a block of the Math group sets, in words: "set colour step to colour step mod 4", "set index
    to a random number from 0 to 9, never the one it holds", "set strip color to input index of red, blue, lime". A
    MATH block of a template a comparison reads (a calc. target) is said where the comparison is: here nothing."""
    target = str(el.get("target") or "")
    if target.startswith("calc."):
        return ""
    t = str(el.get("type") or "")

    def pin(value):
        text = str(value if value is not None else "").strip()
        return friendly(text) if is_entity_ref(text) else short(text or "?", 20)

    a, b, out = pin(el.get("sourceA")), pin(el.get("sourceB")), friendly(target) if target else "?"
    if t == "math_rand":
        return f"set {out} to a random number from {a} to {b}" + (", never the one it holds" if el.get("notSame") else "")
    if t == "mux":
        inputs = list(el.get("inputs") or [])
        listed = ", ".join(pin(v) for v in inputs[:4]) + (" ..." if len(inputs) > 4 else "")
        key = _KEY_WORDS.get(str(el.get("valueKey") or ""), str(el.get("valueKey") or "").replace("_", " "))
        return f"set {out}{' ' + key if key else ''} to input {a} of {listed}"
    rest = "".join(f" {CALC_WORDS.get(t, 'plus')} {pin(x)}" for x in el.get("more") or [])
    return f"set {out} to {a} {CALC_WORDS.get(t, 'plus')} {b}{rest}"


def _move_words(el):
    """[ADDED v3.96.0] What a MOVE sets, in words - brightness to 50 %, color to [255, 136, 0], from dim - so a rung that
    sets several values on one thing says each."""
    key = str(el.get("valueKey") or "")
    words = _KEY_WORDS.get(key, key.replace("_", " "))
    value = el.get("source")
    text = str(value if value is not None else "").strip()
    if is_entity_ref(text) and not el.get("literal"):
        shown = f"from {friendly(text)}"
    elif text:
        shown = f"to {short(text, 28)}{_KEY_UNITS.get(key, '')}"
    else:
        shown = ""
    return " ".join(x for x in (words, shown) if x)


def describe_rung(elements):
    """When the trigger fires, if the conditions hold, do the actions. In one plain sentence."""
    triggers, conditions, actions = [], [], []
    in_actions = False

    # A MATH block inside a decomposed template feeds a comparison, so its result is described in
    # words wherever that comparison refers to it.
    calc = {}

    def collect_calc(els):
        for el in els:
            if el.get("type", "").startswith("math_") and str(el.get("target", "")).startswith("calc."):
                calc[el["target"]] = (f"{calc.get(str(el.get('sourceA')), friendly(el.get('sourceA')))} "
                                      f"{CALC_WORDS.get(el['type'], 'plus')} "
                                      f"{calc.get(str(el.get('sourceB')), friendly(el.get('sourceB')))}")
            if el.get("type") == "parallel":
                for b in el.get("branches", []):
                    collect_calc(b)
    collect_calc(elements)

    said = None
    last_set = ""
    for el in elements:
        t = el.get("type", "")
        # [CHANGED v3.68.0] A wait is drawn with contacts and CMP blocks too, but it is a step, not a condition.
        is_cond = not el.get("waitFor") and (t.startswith("contact_") or t.startswith("cmp_") or (
            t == "parallel" and all(x.get("type", "").startswith(("contact_", "cmp_", "math_"))
                                    for b in el.get("branches", []) for x in b)))
        if not in_actions and (el.get("isTrigger") or is_cond):
            text = _describe_el(el, bool(el.get("isTrigger")), calc)
            if not text:
                continue
            said = triggers if el.get("isTrigger") or _has_trigger([el]) else conditions
            said.append(text)
        elif not in_actions and el.get("isFor") and said:
            # [ADDED v3.72.0] The TON of a for belongs to the trigger or the check right before it.
            said[-1] += f" for {el.get('label', '')}"
        else:
            in_actions = True
            # [ADDED v3.96.0] Several values set on one thing are one "set": brightness to 80, color to [255, 0, 0].
            target = _sets_value(el)
            if target and target == last_set and actions and _move_words(el):
                actions[-1] += ", " + _move_words(el)
                continue
            last_set = target
            text = _describe_el(el, False, calc)
            if text:
                actions.append(text)

    parts = []
    if triggers:
        # [ADDED v3.96.0] "Every 10 seconds, if ..." - not "When every 10 seconds".
        alone = len(triggers) == 1 and triggers[0].startswith(("every ", "on the time pattern "))
        parts.append(triggers[0] if alone else "When " + " or ".join(triggers))
    if conditions:
        parts.append(("if " if triggers else "If ") + " and ".join(conditions))
    if actions:
        parts.append(("then " if parts else "") + " and ".join(actions))
    if not parts:
        return ""
    sentence = ", ".join(parts)
    sentence = sentence[0].upper() + sentence[1:]
    return sentence if len(sentence) <= 160 else sentence[:157] + "..."


# ==========================================================================================
# RUNG ASSEMBLY
# ==========================================================================================

def _has_trigger(elements):
    for el in elements or []:
        if el.get("isTrigger"):
            return True
        if el.get("type") == "parallel" and any(_has_trigger(b) for b in el.get("branches", [])):
            return True
    return False


def _trigger_unit(el, ids):
    """[ADDED v3.72.0] A trigger as it starts a rung: the trigger, and the TON of its for right after it when it has to
    hold for a while - how a ladder says "on for 30 minutes". forTimer on the trigger says the TON is its for, so
    the compiler writes the for the TON says, and none when the TON was taken away."""
    unit = _attach_for_timer([el], ids, el.get("raw") if isinstance(el.get("raw"), dict) else {}, el.get("src", ""))
    if len(unit) > 1:
        el["forTimer"] = True
    return unit


def _trigger_group(elements, ids):
    """Triggers are an OR, so more than one becomes a closed parallel block, never a series.
    [CHANGED v3.72.0] Each trigger with the TON of its for."""
    if not elements:
        return []
    units = [_trigger_unit(e, ids) for e in elements]
    if len(units) == 1:
        return units[0]
    par = _el(ids, "parallel", branches=units, closed=True)
    par.pop("isTrigger", None)
    return [par]


def _clone_group(elements, ids, auto=False, base=False):
    """Fresh ids for a trigger group reused on another rung. auto marks a trigger that is drawn only
    to show what starts the flow, so the compiler does not turn it into a condition of its own.
    [ADDED v3.40.0] base marks a copy of an automation-level condition, so the compiler can put the
    conditions back under conditions: when every rung still carries the same ones."""
    out = []
    for el in elements:
        copy = dict(el)
        copy["id"] = ids.next()
        if auto:
            copy["autoGate"] = True
        if base:
            copy["baseCond"] = True
        if copy.get("type") == "parallel":
            copy["branches"] = [_clone_group(b, ids, auto, base) for b in el.get("branches", [])]
        out.append(copy)
    return out


def _split_options(block):
    """choose / if-then-else, returned as a list of (conditions, sequence, is_default)."""
    options = []
    if "choose" in block:
        for opt in block.get("choose") or []:
            if not isinstance(opt, dict):
                continue
            conds = opt.get("conditions")
            if conds is None:
                conds = opt.get("condition", [])
            if isinstance(conds, dict):
                conds = [conds]
            options.append((conds or [], opt.get("sequence") or [], False))
        default = block.get("default")
        if default:
            options.append(([], default, True))
    elif "if" in block:
        conds = block.get("if")
        if isinstance(conds, dict):
            conds = [conds]
        options.append((conds or [], block.get("then") or [], False))
        if block.get("else"):
            options.append(([], block.get("else"), True))
    return options


def split_leading_or(rungs, r_ids):
    """A rung whose first element is a closed OR block becomes one rung per branch, tied together by
    links at the column where the block closed. The logic is identical, only the drawing changes, and
    the compiler folds them back into exactly the same block."""
    links = []
    out = []
    link_no = 0
    for rung in rungs:
        els = rung.get("elements") or []
        first = els[0] if els else None
        if not (first and first.get("type") == "parallel" and first.get("closed")
                and len(first.get("branches") or []) > 1
                and all(b and b[0].get("isTrigger") for b in first["branches"])):
            out.append(rung)
            continue

        branches = first["branches"]
        rest = els[1:]
        rung["elements"] = list(branches[0]) + rest
        out.append(rung)

        for extra_branch in branches[1:]:
            link_no += 1
            side = {"id": r_ids.next(), "comment": "", "elements": list(extra_branch)}
            for key in ("group", "groupIdx", "groupTotal", "groupKind", "isDefault", "src"):
                if key in rung:
                    side[key] = rung[key]
            out.append(side)
            links.append({
                "id": f"k{link_no}",
                "aRung": rung["id"], "aPath": str(len(branches[0])),
                "bRung": side["id"], "bPath": str(len(extra_branch)),
            })
    rungs[:] = out
    return links


# [ADDED v3.96.0] What a script holds that a net has a field of its own for; anything else travels in extra.
_SCRIPT_NET_KEYS = ("alias", "description", "mode", "max", "variables", "sequence")
_SCENE_NET_KEYS = ("id", "name", "entities")


def script_to_ast(hass, key, script_dict):
    """[ADDED v3.96.0] A script of scripts.yaml as a net at the script level: its sequence drawn as an automation's
    actions are - a rung for each plain run of steps, a rung for each option of a choose or an if - with no trigger. Its
    key in the file is the net's ha_id; what the ladder does not draw (icon, fields, trace ...) travels in extra."""
    script = script_dict if isinstance(script_dict, dict) else {}
    net = yaml_to_ast(hass, {"id": key, "alias": script.get("alias"), "description": script.get("description", ""),
                             "mode": script.get("mode"), "max": script.get("max"),
                             "variables": script.get("variables"), "actions": script.get("sequence")})
    net.update(id=f"n_{key}", ha_id=str(key), name=str(script.get("alias") or key), level="script",
               extra={k: v for k, v in script.items() if k not in _SCRIPT_NET_KEYS})
    if not script.get("alias"):
        # A script with no alias is shown by its key; the compiler writes no alias while the name is still the key.
        net["aliasFromKey"] = True
    return net


def _scene_text(value):
    """[ADDED v3.96.0] A scene's value as the block shows it: a list or a mapping as JSON, anything else as its text."""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "on" if value else "off"
    return "" if value is None else str(value)


def scene_to_ast(hass, scene_dict):
    """[ADDED v3.96.0] A scene of scenes.yaml as a net at the scene level: a rung for each entity - a set coil for on, a
    reset coil for off, a MOVE for any other state and for each attribute (brightness, temperature ...). Each block
    carries the value as the file has it (raw), which the compiler writes back while the block is not changed - on
    written without quotes, a colour as a list. What a scene holds besides its entities (icon, metadata) travels in
    extra."""
    scene = scene_dict if isinstance(scene_dict, dict) else {}
    ids = _Ids("e", hass=hass)
    r_ids = _Ids("r")
    rungs = []
    entities = scene.get("entities")
    for ent, value in (entities.items() if isinstance(entities, dict) else []):
        ent = str(ent)
        if isinstance(value, dict) and value:
            parts = ([(None, value["state"])] if "state" in value else []) + [(k, v) for k, v in value.items() if k != "state"]
        else:
            parts = [(None, value)]
        elements = []
        for key, part in parts:
            raw = {"scene": {"entity": ent, "key": key, "value": part, "dict": isinstance(value, dict) and bool(value)}}
            word = part.strip().lower() if isinstance(part, str) else part
            if key is None and (word is True or word == "on"):
                el = _el(ids, "coil_s", label=ent, raw=raw)
            elif key is None and (word is False or word == "off"):
                el = _el(ids, "coil_r", label=ent, raw=raw)
            else:
                el = _el(ids, "move", mode="value", target=ent, source=_scene_text(part), raw=raw)
                if key is not None:
                    el["valueKey"] = str(key)
            elements.append(el)
        stamp_sigs(elements)
        rungs.append({"id": r_ids.next(), "comment": describe_rung(elements), "elements": elements})
    if not rungs:
        rungs.append({"id": r_ids.next(), "comment": "", "elements": []})
    return {
        "id": f"n_{scene.get('id', 'imported')}",
        "ha_id": scene.get("id"),
        "name": scene.get("name", "Imported Scene"),
        "description": "",
        "collapsed": False,
        "level": "scene",
        "mode": None,
        "max": None,
        "variables": None,
        "extra": {k: v for k, v in scene.items() if k not in _SCENE_NET_KEYS},
        "rungs": rungs,
        "links": [],
    }


def entry_to_ast(hass, domain, key, config):
    """[ADDED v3.96.0] An entry of Home Assistant's files as a net, by its kind: an automation, a script (its key is not
    in its config) or a scene."""
    if domain == "script":
        return script_to_ast(hass, key, config)
    if domain == "scene":
        return scene_to_ast(hass, config)
    return yaml_to_ast(hass, config)


def yaml_to_ast(hass, automation_dict):
    """Builds a net. One rung per logical path, exactly the way a ladder program is written."""
    ids = _Ids("e", hass=hass)
    auto = automation_dict or {}

    raw_triggers = norm_list(auto, "trigger", "triggers")
    raw_conditions = norm_list(auto, "condition", "conditions")
    raw_actions = norm_list(auto, "action", "actions")

    # 1. triggers
    trigger_elements = []
    trig_map = {}
    for i, t in enumerate(raw_triggers):
        el = _trigger_to_element(t, ids, f"triggers[{i}]")
        # [ADDED v3.96.0] Its place among the triggers: a choose may draw them in another order, and the compiler
        # writes them back in this one (_collect_triggers).
        el["trigIdx"] = i
        trigger_elements.append(el)
        if el.get("trigId"):
            # [CHANGED v3.96.0] Several triggers may share one id (Home Assistant allows it): each is kept - the second
            # replaced the first, and a save wrote one trigger less. trigDup tells them apart for the compiler.
            same = trig_map.setdefault(el["trigId"], [])
            if same:
                el["trigDup"] = len(same)
            same.append(el)

    # 2. automation level conditions, shared by every rung
    base_conditions = []
    for i, c in enumerate(raw_conditions):
        base_conditions.extend(_condition_to_elements(c, ids, trig_map, f"conditions[{i}]"))

    # 3. actions, split into plain segments and branch blocks
    rungs = []
    r_ids = _Ids("r")
    segment = []
    segment_src = []
    group_no = 0

    def auto_head():
        """[ADDED v3.71.0] The automation's triggers at the head of a rung that names none of its own, and whether the
        rung hangs from them instead: right below a rung that starts with them, or hangs from them, they are not
        drawn again (sharesHead). The compiler gives a hanging rung the trigger back (expand_shared_heads)."""
        above = rungs[-1] if rungs else None
        if above and (above.get("sharesHead") or (above["elements"] and above["elements"][0].get("autoGate"))):
            return [], True
        return _clone_group(_trigger_group(trigger_elements, ids), ids, auto=True), False

    def flush_segment():
        if not segment:
            return
        elements, hang = auto_head()
        elements += _clone_group(base_conditions, ids, base=True)
        elements += segment
        rungs.append({"id": r_ids.next(), "comment": "", "elements": elements})
        if hang:
            rungs[-1]["sharesHead"] = True

    for i, a in enumerate(raw_actions):
        options = _split_options(a) if isinstance(a, dict) else []
        if options:
            flush_segment()
            segment = []
            segment_src = []
            group_no += 1
            gid = f"g{group_no}"
            total = len(options)
            for k, (conds, seq, is_default) in enumerate(options):
                cond_elements = []
                for j, c in enumerate(conds):
                    cond_elements.extend(_condition_to_elements(c, ids, trig_map, f"actions[{i}].opt[{k}].cond[{j}]"))
                rest = []
                hang = False

                # The first element of the rung is the trigger of this option. If the option did not
                # name one, the whole trigger group gates it.
                if _has_trigger(cond_elements):
                    # The option names its own trigger, so the rung already starts with it and the
                    # global trigger group must not be prepended on top of it.
                    lead = [e for e in cond_elements if e.get("isTrigger")]
                    nested = [e for e in cond_elements if not e.get("isTrigger")]
                    if lead:
                        head = _trigger_group(lead, ids)  # [CHANGED v3.72.0] one lead too, with the TON of its for
                        rest = nested
                    else:
                        head = cond_elements
                        rest = []
                else:
                    head, hang = auto_head()
                    rest = cond_elements

                act_elements = []
                for j, s in enumerate(seq):
                    act_elements.extend(_mark_from_action(_action_to_elements(s, ids, trig_map, f"actions[{i}].opt[{k}].seq[{j}]")))

                elements = head + _clone_group(base_conditions, ids, base=True) + rest + act_elements
                rungs.append({
                    "id": r_ids.next(),
                    "comment": "",
                    "elements": elements,
                    "group": gid,
                    "groupIdx": k,
                    "groupTotal": total,
                    "groupKind": "choose" if "choose" in a else "if",
                    "isDefault": bool(is_default),
                    "src": f"actions[{i}]",
                })
                if hang:
                    rungs[-1]["sharesHead"] = True
        else:
            segment.extend(_mark_from_action(_action_to_elements(a, ids, trig_map, f"actions[{i}]")))
            segment_src.append(i)

    flush_segment()

    if not rungs:
        elements = _clone_group(_trigger_group(trigger_elements, ids), ids, auto=True) + _clone_group(base_conditions, ids, base=True)
        rungs.append({"id": r_ids.next(), "comment": "", "elements": elements})

    for rung in rungs:
        rung["elements"] = fold_notify_pairs(rung["elements"])
        stamp_sigs(rung["elements"])
        if not rung.get("comment"):
            rung["comment"] = describe_rung(rung["elements"])

    # [ADDED v3.0.0] A rung never opens with a split. An OR of triggers at the head of a rung is drawn
    # the way a PLC editor draws it, as separate rungs wired together by a vertical link.
    links = split_leading_or(rungs, r_ids)

    known = {"id", "alias", "description", "trigger", "triggers", "condition", "conditions",
             "action", "actions", "mode", "max", "variables"}
    extra = {k: v for k, v in auto.items() if k not in known}

    net = {
        "id": f"n_{auto.get('id', 'imported')}",
        "ha_id": auto.get("id"),
        "name": auto.get("alias", "Imported Automation"),
        "description": auto.get("description", ""),
        "collapsed": False,
        # [ADDED v3.5.0] Import reads automations, so the net it builds is an automation. The
        # level is written explicitly rather than left to the default, so a net that came from
        # Home Assistant always says what it is.
        "level": "automation",
        "mode": auto.get("mode"),
        "max": auto.get("max"),
        "variables": auto.get("variables"),
        "extra": extra,
        "rungs": rungs,
        "links": links,
    }
    return net
