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
import logging
import re

from .tpl_part import parse_template, label_of, text_of, CMP_OPS, MATH_OPS as TPL_MATH_OPS

_LOGGER = logging.getLogger(__name__)

# Domains whose state is boolean, so they are drawn as a contact instead of a comparison block.
BOOLEAN_DOMAINS = {
    "binary_sensor", "input_boolean", "switch", "light", "fan", "automation", "script",
    "schedule", "remote", "siren", "lock", "cover", "person_home", "group", "media_player_bool",
}
BOOL_STATES = {"on", "off", "true", "false", "home", "not_home", "open", "closed", "locked", "unlocked"}
ON_STATES = {"on", "true", "home", "open", "unlocked"}

TURN_ON_SERVICES = ("turn_on", "toggle")
TURN_OFF_SERVICES = ("turn_off",)

# [ADDED v3.6.0] A coil is the ladder symbol for a service that puts something into one of two
# states, so the whole verb family belongs here and not in a MOVE. () energises, (R) de-energises,
# and homeassistant.turn_on stays (S) because it is the latching form.
# [CHANGED v3.24.0] A reset coil means the rung switches something off. Closing a cover is not that.
# A cover has open and closed, not on and off, and close_cover drives a motor exactly as open_cover
# does, so both are commands that make something happen and both latch, which is (S). Only a service
# that genuinely takes something out of service is (R): turning off, stopping, pausing, disarming.
# A plain turn_on stays the plain coil ( ), the ordinary energised output of a ladder.
COIL_PLAIN_SERVICES = ("turn_on",)
COIL_RESET_SERVICES = ("turn_off", "stop", "stop_cover", "stop_valve", "media_pause", "media_stop",
                       "cancel", "disable", "disarm", "alarm_disarm", "close", "turn_off_all")
COIL_SET_SERVICES = ("toggle", "open_cover", "close_cover", "lock", "unlock", "open_valve",
                     "close_valve", "open", "media_play", "start", "enable", "press",
                     "arm_home", "arm_away", "arm_night",
                     "alarm_arm_home", "alarm_arm_away", "alarm_arm_night", "alarm_arm_vacation")

# Every service that is drawn as a coil at all.
COIL_ALL_SERVICES = COIL_PLAIN_SERVICES + COIL_RESET_SERVICES + COIL_SET_SERVICES


def coil_for_service(svc):
    """[ADDED v3.24.0] Which coil draws this service, or an empty string when none of them does."""
    name = str(svc or "").split(".")[-1]
    if svc in ("homeassistant.turn_on", "homeassistant.turn_off"):
        return "coil_r" if name == "turn_off" else "coil_s"
    if name in COIL_RESET_SERVICES:
        return "coil_r"
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

MATH_OPS = {"+": "math_add", "-": "math_sub", "*": "math_mul", "/": "math_div"}

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
        from homeassistant.helpers import entity_registry as er
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
            from homeassistant.helpers import area_registry as reg_mod
            entry = reg_mod.async_get(hass).async_get_area(value)
        elif kind == "label":
            from homeassistant.helpers import label_registry as reg_mod
            entry = reg_mod.async_get(hass).async_get_label(value)
        elif kind == "floor":
            from homeassistant.helpers import floor_registry as reg_mod
            entry = reg_mod.async_get(hass).async_get_floor(value)
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
        from homeassistant.helpers import entity_registry as er
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
        from homeassistant.helpers import device_registry as dr
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
    return s.split(".")[0] if "." in s else ""


def is_boolean_state(entity_id, state):
    """A contact is only used for a real boolean, everything else is a comparison block."""
    if isinstance(state, (list, tuple)):
        return False
    st = str(state).lower()
    if st not in BOOL_STATES:
        return False
    return domain_of(entity_id) in BOOLEAN_DOMAINS or st in ("on", "off")


SIG_FIELDS = ("type", "label", "sourceA", "sourceB", "sourceC", "target", "source", "mode", "title",
              "tts", "stream", "value", "valueKey", "loopType", "weekdays", "precision", "fallback", "kind")


def element_sig(el):
    """Fingerprint of everything the user can edit. Equal fingerprint means the original node is
    still an exact description of this element, so it can be emitted untouched."""
    return "|".join(f"{k}={el.get(k, '')}" for k in SIG_FIELDS)


def stamp_sigs(elements):
    for el in elements or []:
        if el.get("type") == "parallel":
            for b in el.get("branches", []):
                stamp_sigs(b)
        elif el.get("type") == "repeat":
            stamp_sigs(el.get("sequence", []))
        # Every piece of a decomposed template or time window is fingerprinted too, so the group can
        # tell whether the user edited any part of it before deciding to reuse the original text.
        if isinstance(el.get("raw"), dict) or el.get("tplId") or el.get("timeId"):
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

    if as_action:
        if dtype in ("turn_on", "toggle"):
            return _el(ids, "coil", label=label, raw=node, src=src)
        if dtype == "turn_off":
            return _el(ids, "coil_r", label=label, raw=node, src=src)
        return _fallback_move(ids, node, src=src, service=f"device.{dtype}" if dtype else "device",
                              entity=label, value=_params_line(node))

    numeric = _numeric_element(ids, label, node.get("above"), node.get("below"), src, node)
    if numeric is not None:
        return numeric

    # [CHANGED v2.2.0] A device event carries no number, so by the standard it is a boolean and it is
    # drawn as a contact. The device id, the domain and the event type all stay in raw for the way back.
    if dtype in DEVICE_OFF_TYPES:
        return _el(ids, "contact_nc", label=label, raw=node, src=src)
    if dtype in DEVICE_PRESS_TYPES:
        return _el(ids, "contact_p", label=label, raw=node, src=src)
    return _el(ids, "contact_no", label=label, raw=node, src=src)


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
        if to_state is None and from_state is None:
            el = _el(ids, "contact_p", label=ent)
        elif isinstance(to_state, list):
            el = _el(ids, "cmp_eq", sourceA=ent, sourceB=", ".join(str(x) for x in to_state))
        elif is_boolean_state(ent, to_state):
            el = _el(ids, "contact_no" if str(to_state).lower() in ON_STATES else "contact_nc", label=ent)
        else:
            el = _el(ids, "cmp_eq", sourceA=ent, sourceB=to_state)

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


def _condition_to_elements(c, ids, trig_map, src, parallel_ids=None):
    """Returns a LIST of elements in series. or becomes one closed parallel block."""
    if not isinstance(c, dict):
        return []

    ctype = str(c.get("condition") or "").lower()

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
        subs = []
        for i, sub in enumerate(inner or []):
            subs.extend(_condition_to_elements(sub, ids, trig_map, f"{src}.not[{i}]"))
        if len(subs) == 1:
            flipped = _invert(subs[0])
            if flipped:
                flipped["id"] = subs[0]["id"]
                flipped["raw"] = c
                flipped["src"] = src
                return [flipped]
        return subs or []

    ent = resolve_entity(ids, norm_entity(c))

    if ctype == "trigger":
        # The reference to a trigger is drawn as the trigger itself, marked as a trigger.
        ids_ref = c.get("id")
        ref_list = ids_ref if isinstance(ids_ref, list) else [ids_ref]
        out = []
        for rid in ref_list:
            src_el = trig_map.get(str(rid))
            if src_el:
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
        if isinstance(st, list):
            el = _el(ids, "cmp_eq", sourceA=ent, sourceB=", ".join(str(x) for x in st))
        elif is_boolean_state(ent, st):
            el = _el(ids, "contact_no" if str(st).lower() in ON_STATES else "contact_nc", label=ent)
        else:
            el = _el(ids, "cmp_eq", sourceA=ent, sourceB=st)
        el["raw"] = c
        el["src"] = src
        return [el]

    if ctype == "numeric_state":
        if c.get("above") is not None:
            el = _el(ids, "cmp_gt", sourceA=ent, sourceB=c.get("above"))
        elif c.get("below") is not None:
            el = _el(ids, "cmp_lt", sourceA=ent, sourceB=c.get("below"))
        else:
            return [_el(ids, "cmp_eq", sourceA=ent, sourceB="?", raw=c, src=src)]
        el["raw"] = c
        el["src"] = src
        return [el]

    if ctype == "template":
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

    return [_fallback_move(ids, c, src=src, service=(ctype or "condition"), entity=ent,
                           value=_params_line({k: v for k, v in c.items() if k != "condition"}))]


# ==========================================================================================
# ACTIONS
# ==========================================================================================

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


def _action_to_elements(a, ids, trig_map, src):
    """Returns a list of elements. Structural actions expand into ladder structure, never into JSON."""
    if not isinstance(a, dict):
        return [_fallback_move(ids, {"raw": a}, src=src, service="action", value=short(a, 60))]

    # --- structure -------------------------------------------------------------------
    if "repeat" in a:
        rep = a["repeat"] or {}
        el = _el(ids, "repeat", sequence=[], raw=a, src=src)
        if "count" in rep:
            el["loopType"] = "count"
            el["value"] = str(rep.get("count"))
        elif "for_each" in rep:
            el["loopType"] = "for_each"
            fe = rep.get("for_each")
            el["value"] = ", ".join(str(x) for x in fe) if isinstance(fe, list) else str(fe)
        elif "while" in rep:
            el["loopType"] = "while"
            el["value"] = short(_first_template(rep.get("while")), 40)
        elif "until" in rep:
            el["loopType"] = "until"
            el["value"] = short(_first_template(rep.get("until")), 40)
        else:
            el["loopType"] = "count"
            el["value"] = "1"
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
        if isinstance(d, dict):
            label = "%02d:%02d:%02d" % (int(d.get("hours", 0)), int(d.get("minutes", 0)), int(d.get("seconds", 0)))
        else:
            label = str(d)
        return [_el(ids, "timer_ton", label=label, raw=a, src=src)]

    if "wait_for_trigger" in a:
        wt = a["wait_for_trigger"]
        first = wt[0] if isinstance(wt, list) and wt else wt
        if isinstance(first, dict) and norm_kind(first) == "state":
            ent = norm_entity(first)
            to_state = str(first.get("to", "")).lower()
            if to_state in ON_STATES:
                return [_el(ids, "contact_p", label=ent, raw=a, src=src)]
            if to_state:
                return [_el(ids, "contact_n", label=ent, raw=a, src=src)]
            return [_el(ids, "wait", label=ent, raw=a, src=src)]
        return [_el(ids, "wait", label=short(norm_entity(first) or "trigger", 30), raw=a, src=src)]

    if "wait_template" in a:
        return template_to_elements(a.get("wait_template", ""), ids, src, a)

    if "condition" in a and not norm_service(a):
        return _condition_to_elements(a, ids, trig_map, src)

    # --- services --------------------------------------------------------------------
    svc = norm_service(a)
    if svc:
        domain = svc.split(".")[0]
        name = svc.split(".")[-1]
        # [CHANGED v3.6.0] One resolution for every action, so a device, an area or a label target
        # shows a real name instead of leaving the pin empty.
        ent, target_kind = target_label(ids, a, domain_hint=domain)
        if not ent:
            ent = resolve_entity(ids, norm_entity(a))
            target_kind = "entity"
        data = a.get("data") if isinstance(a.get("data"), dict) else {}

        if domain == "notify" or svc.startswith("notify."):
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
            math = _detect_math(val)
            if math and math[0]:
                op_type, a_ent, b_ent = math
                return [_el(ids, op_type, sourceA=a_ent, sourceB=b_ent, target=ent, raw=a, src=src)]
            return [_el(ids, "move", mode="value", source=val, target=ent, valueKey=key_used, raw=a, src=src)]

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
    if "." in text and " " not in text:
        text = text.split(".", 1)[1]
    return text.replace("_", " ").strip() or "it"


def _describe_el(el, as_trigger=False, calc=None):
    calc = calc if calc is not None else {}
    t = el.get("type", "")
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
    if t == "cmp_eq":
        src = str(el.get("sourceA"))
        if src == "time":
            return f"the time is {friendly(b)}"
        if src == "weekday":
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
    if t.startswith("math_"):
        return ""
    if t == "coil_r":
        return f"turn off {lbl}"
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
        return f"set {target}"
    if t == "notify":
        return f"send a notification to {friendly(el.get('target'))}"
    if t == "ctu":
        return f"count up {friendly(el.get('source'))}"
    if t in ("timer_ton", "timer_toff"):
        return f"wait {el.get('label', '')}"
    if t == "wait":
        return f"wait for {lbl}"
    if t == "repeat":
        inner = ", ".join(x for x in (_describe_el(e, False, calc) for e in el.get("sequence", [])) if x)
        return f"repeat {el.get('value', '')} times ({inner})" if inner else f"repeat {el.get('value', '')} times"
    return ""


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
                sym = {"math_add": "plus", "math_sub": "minus", "math_mul": "times", "math_div": "divided by"}
                calc[el["target"]] = (f"{calc.get(str(el.get('sourceA')), friendly(el.get('sourceA')))} "
                                      f"{sym.get(el['type'], 'plus')} "
                                      f"{calc.get(str(el.get('sourceB')), friendly(el.get('sourceB')))}")
            if el.get("type") == "parallel":
                for b in el.get("branches", []):
                    collect_calc(b)
    collect_calc(elements)

    for el in elements:
        t = el.get("type", "")
        is_cond = t.startswith("contact_") or t.startswith("cmp_") or (
            t == "parallel" and all(x.get("type", "").startswith(("contact_", "cmp_", "math_"))
                                    for b in el.get("branches", []) for x in b))
        if not in_actions and (el.get("isTrigger") or is_cond):
            text = _describe_el(el, bool(el.get("isTrigger")), calc)
            if not text:
                continue
            (triggers if el.get("isTrigger") or _has_trigger([el]) else conditions).append(text)
        else:
            in_actions = True
            text = _describe_el(el, False, calc)
            if text:
                actions.append(text)

    parts = []
    if triggers:
        parts.append("When " + " or ".join(triggers))
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


def _trigger_group(elements, ids):
    """Triggers are an OR, so more than one becomes a closed parallel block, never a series."""
    if not elements:
        return []
    if len(elements) == 1:
        return [elements[0]]
    branches = [[e] for e in elements]
    par = _el(ids, "parallel", branches=branches, closed=True)
    par.pop("isTrigger", None)
    return [par]


def _clone_group(elements, ids, auto=False):
    """Fresh ids for a trigger group reused on another rung. auto marks a trigger that is drawn only
    to show what starts the flow, so the compiler does not turn it into a condition of its own."""
    out = []
    for el in elements:
        copy = dict(el)
        copy["id"] = ids.next()
        if auto:
            copy["autoGate"] = True
        if copy.get("type") == "parallel":
            copy["branches"] = [_clone_group(b, ids, auto) for b in el.get("branches", [])]
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
        trigger_elements.append(el)
        if el.get("trigId"):
            trig_map[el["trigId"]] = el

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

    def flush_segment():
        if not segment:
            return
        elements = _clone_group(_trigger_group(trigger_elements, ids), ids, auto=True)
        elements += _clone_group(base_conditions, ids)
        elements += segment
        rungs.append({"id": r_ids.next(), "comment": "", "elements": elements})

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

                # The first element of the rung is the trigger of this option. If the option did not
                # name one, the whole trigger group gates it.
                if _has_trigger(cond_elements):
                    # The option names its own trigger, so the rung already starts with it and the
                    # global trigger group must not be prepended on top of it.
                    lead = [e for e in cond_elements if e.get("isTrigger")]
                    nested = [e for e in cond_elements if not e.get("isTrigger")]
                    if lead:
                        head = (_trigger_group(lead, ids) if len(lead) > 1 else lead)
                        rest = nested
                    else:
                        head = cond_elements
                        rest = []
                else:
                    head = _clone_group(_trigger_group(trigger_elements, ids), ids, auto=True)
                    rest = cond_elements

                act_elements = []
                for j, s in enumerate(seq):
                    act_elements.extend(_mark_from_action(_action_to_elements(s, ids, trig_map, f"actions[{i}].opt[{k}].seq[{j}]")))

                elements = head + _clone_group(base_conditions, ids) + rest + act_elements
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
        else:
            segment.extend(_mark_from_action(_action_to_elements(a, ids, trig_map, f"actions[{i}]")))
            segment_src.append(i)

    flush_segment()

    if not rungs:
        elements = _clone_group(_trigger_group(trigger_elements, ids), ids, auto=True) + _clone_group(base_conditions, ids)
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