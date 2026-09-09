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
# [ADDED v1.69.0] Output perfectly formed logic for standard triggers, retrieving native YAML dictionary if present via raw_trigger.
# [ADDED v3.5.0 | 2026-08-24] Purpose: A net now carries a level. automation compiles to the
#   automation schema exactly as before, script compiles to alias plus sequence, and scene
#   compiles to name plus entities. A net with no level is an automation.
# [ADDED v2.0.0 | 2026-08-17] Purpose: The rung is the logical unit.
#   1. Every rung compiles on its own. Rungs that share a group compile back into one choose, in order.
#   2. Triggers are collected once, get an id, and a rung that starts with a trigger references it with
#      condition: trigger, which is the exact mirror of what the importer draws.
#   3. Nothing is invented. An element that carries raw is emitted from raw with only the fields the
#      user actually edited patched into it, so templates, ids, titles and media_stream survive.
#   4. python_script.set_state is never written again.
import logging
import re

from .yaml_to_libi import (
    norm_service, norm_entity, norm_kind, domain_of, short,
    ON_STATES, SET_VALUE_SERVICES, element_sig, EVENT_TRIGGER_KEYS, target_spec,
    target_summary, hms_to_seconds,
)

_LOGGER = logging.getLogger(__name__)

CONDITION_TYPES = ("contact_", "cmp_", "schedule")
MATH_SYMBOL = {"math_add": "+", "math_sub": "-", "math_mul": "*", "math_div": "/"}


# ==========================================================================================
# [ADDED v3.5.0] EXECUTION LEVELS
# A net is one of three things and the level decides which schema it compiles to. A net with no
# level is an automation, which is what every net saved before this version is.
# ==========================================================================================

NET_LEVELS = ("automation", "script", "scene")

# The only coils a scene can hold. A scene assigns end states and nothing else.
SCENE_ON_TYPES = ("coil", "coil_s")
# A toggle has no fixed end state, so a scene, which is a snapshot of end states, cannot hold one.


def net_level(net):
    """The level of a net, normalised. Anything missing or unknown reads as automation."""
    lvl = str((net or {}).get("level") or "automation").strip().lower()
    return lvl if lvl in NET_LEVELS else "automation"


def slugify(text, fallback="libi_item"):
    """A script is stored under an object id and not in a list, so its name becomes a slug."""
    slug = re.sub(r"[^a-z0-9_]+", "_", str(text or "").strip().lower()).strip("_")
    return slug or fallback


def _without_triggers(rungs):
    """A script and a scene never listen to anything. Any leftover flag is cleared on a copy, so the
    compiler reads the element as an ordinary condition and the stored net is not touched."""
    import copy as _copy
    out = _copy.deepcopy(rungs or [])

    def walk(elements):
        for el in elements or []:
            if el.get("isTrigger"):
                el["isTrigger"] = False
            if el.get("type") == "parallel":
                for branch in el.get("branches", []):
                    walk(branch)
            elif el.get("type") == "repeat":
                walk(el.get("sequence", []))

    for rung in out:
        walk(rung.get("elements", []))
    return out



def _is_condition(el):
    t = el.get("type", "")
    if el.get("tplId") or el.get("timeId"):
        # every piece of a decomposed template or time window gates the rung, including its MATH block
        return True
    if t in ("parallel",):
        return all(_is_condition(x) for b in el.get("branches", []) for x in b) and \
               any(x for b in el.get("branches", []) for x in b)
    if t == "wait":
        return False
    return t.startswith("contact_") or t.startswith("cmp_") or t == "schedule"  # cmp_rng included


def _num(value):
    """Bounds go back as numbers, the way Home Assistant writes them."""
    txt = str(value if value is not None else "").strip()
    if txt == "":
        return value
    try:
        return int(txt) if re.fullmatch(r"-?\d+", txt) else float(txt)
    except (TypeError, ValueError):
        return value


def _norm_spec(spec):
    """A target block reduced to something comparable: every key a sorted list of strings."""
    if not isinstance(spec, dict):
        return {}
    out = {}
    for key, value in spec.items():
        items = value if isinstance(value, (list, tuple)) else [value]
        items = sorted(str(v) for v in items if v not in (None, ""))
        if items:
            out[key] = items
    return out


def spec_changed(el):
    """[ADDED v3.7.0] True when the user picked different targets than the ones that were imported."""
    spec = el.get("targetSpec")
    if not isinstance(spec, dict):
        return False
    return _norm_spec(spec) != _norm_spec(target_spec(el.get("raw") or {}))


def apply_target_spec(out, spec):
    """[ADDED v3.7.0] Writes what the native picker produced. The whole target block is replaced and
    the same keys are cleared wherever else the node was carrying them, so a node can never end up
    with two competing targets. A single item goes back as a plain string, the way HA writes it."""
    clean = _norm_spec(spec)
    out = dict(out)
    for key in TARGET_KEY_NAMES:
        out.pop(key, None)
        if isinstance(out.get("data"), dict) and key in out["data"]:
            data = dict(out["data"])
            data.pop(key, None)
            out["data"] = data
    block = {k: (v[0] if len(v) == 1 else v) for k, v in clean.items()}
    if block:
        out["target"] = block
    else:
        out.pop("target", None)
    return out


def _apply_continue_on_error(out, el):
    """[ADDED v3.24.0] The flag is a real field of the action, so the tick in the inspector writes it
    and clearing the tick takes it away rather than leaving a false behind."""
    out = dict(out)
    if el.get("continueOnError"):
        out["continue_on_error"] = True
    else:
        out.pop("continue_on_error", None)
    return out


def _untouched(el):
    """True when the element still describes its original node exactly, so that node is emitted
    verbatim and every field the ladder does not model survives the round trip."""
    if el.get("type") in ("repeat", "parallel"):
        return False
    # [ADDED v3.24.0] Neither of these is part of the text fingerprint, so they are checked here.
    raw = el.get("raw") if isinstance(el.get("raw"), dict) else None
    if raw is not None:
        if bool(el.get("continueOnError")) != (raw.get("continue_on_error") is True):
            return False
        picked = str(el.get("service") or "").strip()
        if picked and norm_service(raw) and picked != norm_service(raw):
            return False
    # [ADDED v3.7.0] The picked targets are not part of the text fingerprint, so they are checked
    # here. Without this a target chosen in the picker would be silently thrown away on save.
    if spec_changed(el):
        return False
    raw = el.get("raw")
    return isinstance(raw, dict) and el.get("sig") and el.get("sig") == element_sig(el)


# [ADDED v3.6.0] A pin may carry a count suffix such as light.porch +9, which is display only.
_COUNT_SUFFIX = re.compile(r"\s*\+\d+$")
_ENTITY_SHAPE = re.compile(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+")
_RESOLVED_KEYS = {"device": "device_id", "area": "area_id", "label": "label_id", "floor": "floor_id"}
TARGET_KEY_NAMES = ("entity_id", "device_id", "area_id", "label_id", "floor_id")


def clean_target(value):
    """The entity part of what a pin shows, without the count suffix the importer added."""
    return _COUNT_SUFFIX.sub("", str(value or "")).strip()


def _drop_resolved_key(out, target_kind):
    """The user replaced a resolved device, area or label with a real entity, so the key that was
    resolved goes away instead of sitting next to the new entity_id and doubling the target."""
    key = _RESOLVED_KEYS.get(target_kind)
    if not key:
        return out
    out = dict(out)
    out.pop(key, None)
    if isinstance(out.get("target"), dict):
        tgt = dict(out["target"])
        tgt.pop(key, None)
        out["target"] = tgt or {}
    return out


def target_updates(el):
    """[ADDED v3.6.0] What to write back for the target of this element, and which kind of target it
    started as. Returns None when there is nothing safe to write, which is the case whenever the pin
    still shows the name LIBI resolved for a device, an area or a label. Those names are a display of
    something that is not an entity, so writing them into entity_id would break the action."""
    # [ADDED v3.7.0] A target chosen in the native picker wins over everything else, because it says
    # precisely which entities, devices, areas and labels the user meant.
    if spec_changed(el):
        return {"__target_spec__": el.get("targetSpec")}, "spec"
    kind = str(el.get("targetKind") or "entity")
    label = clean_target(el.get("label") if el.get("label") is not None else el.get("target"))
    if kind == "entity":
        return {"entity_id": label}, kind
    if label == clean_target(el.get("targetLabel")):
        return None, kind
    if not _ENTITY_SHAPE.fullmatch(label):
        return None, kind
    return {"entity_id": label}, kind


def _patch(raw, updates, target_kind=""):
    """Emit the original node with only the edited fields replaced, so nothing unknown is lost."""
    out = dict(raw) if isinstance(raw, dict) else {}
    if isinstance(updates, dict) and "__target_spec__" in updates:
        return apply_target_spec(out, updates["__target_spec__"])
    if target_kind and target_kind != "entity" and "entity_id" in (updates or {}):
        out = _drop_resolved_key(out, target_kind)
    for key, val in updates.items():
        if val is None:
            continue
        if key == "entity_id":
            val = clean_target(val)
            if "entity_id" in out:
                out["entity_id"] = val
            elif isinstance(out.get("target"), dict):
                out["target"] = dict(out["target"])
                out["target"]["entity_id"] = val
            else:
                out["entity_id"] = val
        else:
            out[key] = val
    return out


# ==========================================================================================
# TRIGGERS
# ==========================================================================================

def _element_to_trigger(el, trig_id):
    # [ADDED v3.33.0] A group LIBI understood but did not invent goes back untouched. Editing the
    # members of one is not offered, so there is nothing here that could quietly rewrite it.
    if el.get("spookGroup") and isinstance(el.get("raw"), dict):
        out = dict(el["raw"])
        out.setdefault("id", trig_id)
        return out
    t = el.get("type", "")
    raw = el.get("raw")

    if _untouched(el) and (norm_kind(raw) or "platform" in raw or "trigger" in raw):
        out = dict(raw)
        if trig_id:
            out["id"] = trig_id
        return out

    if isinstance(raw, dict) and (norm_kind(raw) or "platform" in raw or "trigger" in raw):
        out = dict(raw)
        if t == "cmp_rng":
            out = _patch(out, {"entity_id": el.get("sourceA")})
            out["above"] = _num(el.get("sourceB"))
            out["below"] = _num(el.get("sourceC"))
        elif t in ("cmp_gt", "cmp_lt", "cmp_ge", "cmp_le"):
            out = _patch(out, {"entity_id": el.get("sourceA")})
            if t in ("cmp_gt", "cmp_ge"):
                out.pop("below", None)
                out["above"] = _num(el.get("sourceB"))
            else:
                out.pop("above", None)
                out["below"] = _num(el.get("sourceB"))
        elif t in ("cmp_eq", "cmp_ne") and norm_kind(raw) == "zone":
            out = _patch(out, {"entity_id": el.get("sourceA"), "zone": el.get("sourceB")})
            out["event"] = "leave" if t == "cmp_ne" else "enter"
        elif t in ("cmp_eq", "cmp_ne") and norm_kind(raw) == "time":
            out["at"] = el.get("sourceB")
        elif el.get("deviceNode") or norm_kind(out) == "device":
            # [ADDED v3.26.0] The inspector edits the node itself, so it already carries the device
            # and the trigger that were chosen. Patching an entity_id in would break it.
            pass
        elif t.startswith("contact_"):
            # [CHANGED v3.6.0] A pulse contact over a conversation, a webhook, an mqtt topic or a tag
            # has no entity at all. Its identity lives in that trigger's own key, and writing an
            # entity_id next to it would produce a trigger Home Assistant cannot load.
            kind = el.get("eventKind") or norm_kind(out)
            key = EVENT_TRIGGER_KEYS.get(kind)
            if key:
                label = clean_target(el.get("label"))
                ident = label.split(".", 1)[1] if label.startswith(f"{kind}.") else label
                if ident:
                    out[key] = ident
            else:
                updates, kind_t = target_updates(el)
                if updates:
                    out = _patch(out, updates, target_kind=kind_t)
        elif t == "cmp_tpl":
            out["value_template"] = el.get("sourceA")
        if trig_id:
            out["id"] = trig_id
        return out

    # Synthesised from the ladder alone. The right side decides the HA dialect.
    ent = el.get("sourceA") or el.get("label") or ""
    val = el.get("sourceB")
    out = None

    if t.startswith("contact_"):
        state = "off" if t in ("contact_nc", "contact_n") else "on"
        out = {"trigger": "state", "entity_id": ent, "to": state}
        if t in ("contact_p", "contact_n"):
            out.pop("to", None) if t == "contact_p" and not ent else None
    elif t in ("cmp_eq", "cmp_ne"):
        if str(ent).lower() == "time":
            out = {"trigger": "time", "at": val}
        elif str(ent).lower() == "sun":
            out = {"trigger": "sun", "event": val or "sunset"}
        elif domain_of(val) == "zone" or str(val).startswith("zone."):
            out = {"trigger": "zone", "entity_id": ent, "zone": val,
                   "event": "leave" if t == "cmp_ne" else "enter"}
        else:
            out = {"trigger": "state", "entity_id": ent, "to": val}
    elif t == "cmp_rng":
        out = {"trigger": "numeric_state", "entity_id": ent, "above": _num(el.get("sourceB")), "below": _num(el.get("sourceC"))}
    elif t == "cmp_gt":
        out = {"trigger": "numeric_state", "entity_id": ent, "above": _num(val)}
    elif t == "cmp_lt":
        out = {"trigger": "numeric_state", "entity_id": ent, "below": _num(val)}
    elif el.get("tplId"):
        math_map = {}
        _collect_math([el], math_map)
        out = {"trigger": "template", "value_template": "{{ " + _template_expr([el], math_map) + " }}"}
    elif t in ("native", "device") and isinstance(el.get("raw"), dict):  # legacy saves only
        out = dict(el["raw"])
    elif t == "schedule":
        out = {"trigger": "time", "at": el.get("sourceA", "")}

    if out is None:
        out = {"trigger": "state", "entity_id": ent}
    if trig_id:
        out["id"] = trig_id
    return out


def _trigger_key(el):
    """Two identical triggers on two rungs are one trigger in the automation."""
    if el.get("trigId"):
        return f"id:{el['trigId']}"
    return "|".join([
        el.get("type", ""),
        str(el.get("label", "")),
        str(el.get("sourceA", "")),
        str(el.get("sourceB", "")),
    ])


# ==========================================================================================
# CONDITIONS
# ==========================================================================================

def _element_to_condition(el):
    t = el.get("type", "")
    raw = el.get("raw")

    if t == "parallel":
        branches = []
        for b in el.get("branches", []):
            conds = [c for c in (_element_to_condition(x) for x in b) if c]
            if len(conds) == 1:
                branches.append(conds[0])
            elif conds:
                branches.append({"condition": "and", "conditions": conds})
        if not branches:
            return None
        if len(branches) == 1:
            return branches[0]
        return {"condition": "or", "conditions": branches}

    if _untouched(el) and isinstance(raw, dict) and raw.get("condition"):
        return dict(raw)

    if isinstance(raw, dict) and raw.get("condition"):
        out = dict(raw)
        if t.startswith("contact_"):
            out = _patch(out, {"entity_id": el.get("label")})
            if out.get("condition") == "state":
                out["state"] = "off" if t in ("contact_nc", "contact_n") else "on"
        elif t in ("cmp_eq", "cmp_ne"):
            out = _patch(out, {"entity_id": el.get("sourceA")})
            if out.get("condition") == "zone":
                out["zone"] = el.get("sourceB")
            elif out.get("condition") == "state":
                out["state"] = el.get("sourceB")
        elif t in ("cmp_gt", "cmp_lt"):
            out = _patch(out, {"entity_id": el.get("sourceA")})
            if t == "cmp_gt":
                out.pop("below", None)
                out["above"] = el.get("sourceB")
            else:
                out.pop("above", None)
                out["below"] = el.get("sourceB")
        elif t == "cmp_tpl":
            out["value_template"] = el.get("sourceA", "")
        elif t == "schedule":
            if el.get("sourceA"):
                out["after"] = el.get("sourceA")
            if el.get("sourceB"):
                out["before"] = el.get("sourceB")
            if el.get("weekdays"):
                out["weekday"] = el.get("weekdays")
        return out

    ent = el.get("sourceA") or el.get("label") or ""
    val = el.get("sourceB")

    if t.startswith("contact_"):
        return {"condition": "state", "entity_id": ent, "state": "off" if t in ("contact_nc", "contact_n") else "on"}
    if t == "cmp_eq" and str(ent) == "weekday":
        return {"condition": "time", "weekday": [d.strip() for d in str(val or "").split(",") if d.strip()]}
    if t == "cmp_eq":
        if domain_of(val) == "zone" or str(val).startswith("zone."):
            return {"condition": "zone", "entity_id": ent, "zone": val}
        return {"condition": "state", "entity_id": ent, "state": val}
    if t == "cmp_ne":
        return {"condition": "not", "conditions": [{"condition": "state", "entity_id": ent, "state": val}]}
    if t == "cmp_rng":
        if str(ent).lower() == "time" or el.get("kind") == "time":
            return {"condition": "time", "after": el.get("sourceB"), "before": el.get("sourceC")}
        return {"condition": "numeric_state", "entity_id": ent, "above": _num(el.get("sourceB")), "below": _num(el.get("sourceC"))}
    if t == "cmp_gt":
        return {"condition": "numeric_state", "entity_id": ent, "above": _num(val)}
    if t == "cmp_lt":
        return {"condition": "numeric_state", "entity_id": ent, "below": _num(val)}
    if t == "cmp_ge":
        if str(ent).lower() == "time":
            return {"condition": "time", "after": val}
        return {"condition": "not", "conditions": [{"condition": "numeric_state", "entity_id": ent, "below": val}]}
    if t == "cmp_le":
        if str(ent).lower() == "time":
            return {"condition": "time", "before": val}
        return {"condition": "not", "conditions": [{"condition": "numeric_state", "entity_id": ent, "above": val}]}
    if t == "cmp_tpl":
        return {"condition": "template", "value_template": el.get("sourceA", "")}
    if t == "schedule":
        out = {"condition": "time"}
        if el.get("sourceA"):
            out["after"] = el.get("sourceA")
        if el.get("sourceB"):
            out["before"] = el.get("sourceB")
        if el.get("weekdays"):
            out["weekday"] = el.get("weekdays")
        return out
    if t in ("native", "device") and isinstance(raw, dict):  # legacy saves only
        return dict(raw)
    return None


# ==========================================================================================
# ACTIONS
# ==========================================================================================

def _notify_actions(el):
    """One MOVE block, one or two HA actions, depending on the mode."""
    mode = el.get("mode", "notify")
    target = el.get("target", "")
    message = el.get("source", "")
    title = el.get("title", "")
    tts = el.get("tts", "") or message
    stream = el.get("stream", "") or "alarm_stream"
    raw = el.get("raw") if isinstance(el.get("raw"), dict) else None

    def notify_node():
        if raw and "tts_text" not in str(raw):
            out = dict(raw)
            data = dict(out.get("data") or {})
            data["message"] = message
            if title:
                data["title"] = title
            else:
                data.pop("title", None)
            out["data"] = data
            out.pop("service", None)
            out["action"] = target or norm_service(raw)
            return out
        data = {"message": message}
        if title:
            data["title"] = title
        return {"action": target, "data": data}

    def tts_node():
        if str(target).startswith("notify."):
            return {"action": target, "data": {"message": "TTS", "data": {"tts_text": tts, "media_stream": stream}}}
        return {"action": "tts.speak", "target": {"entity_id": target}, "data": {"message": tts}}

    if mode == "notify":
        return [notify_node()]
    if mode == "tts":
        return [tts_node()]
    if mode == "both":
        return [notify_node(), tts_node()]
    return []


def _move_action_node(el):
    """[ADDED v3.8.0] A MOVE ACTION is a wrapper, not an assignment. The node it holds is emitted as
    it is, with only the service from the IN pin and the targets from the picker applied. The OUT pin
    is a summary for the eye and is never read back."""
    raw = el.get("raw") if isinstance(el.get("raw"), dict) else {}
    out = dict(raw)
    out.pop("service", None)
    svc = str(el.get("source") or "").strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+", svc):
        svc = norm_service(raw) or svc
    if svc:
        out["action"] = svc
    updates, kind = target_updates(el)
    if updates and "__target_spec__" in updates:
        return _patch(out, updates)
    return out


def _move_value_action(el):
    target = el.get("target", "")
    value = el.get("source", "")
    raw = el.get("raw") if isinstance(el.get("raw"), dict) else None

    # [ADDED v3.8.0] A wrapper never turns into a value assignment, otherwise the service name on the
    # IN pin would be written into the data payload of the action.
    if el.get("moveKind") == "action":
        return _apply_continue_on_error(_move_action_node(el), el)

    # [ADDED v3.6.0] The reply a voice assistant speaks back is a key of its own, not a service call.
    # Without this branch an edited reply came back as an action named conversation.response.
    if el.get("service") == "set_conversation_response" or (
            isinstance(raw, dict) and "set_conversation_response" in raw):
        out = dict(raw) if isinstance(raw, dict) else {}
        out["set_conversation_response"] = value
        return out

    if raw and norm_service(raw):
        out = dict(raw)
        data = dict(out.get("data") or {})
        key = el.get("valueKey") or next((k for k in data.keys() if k != "entity_id"), None)
        if key:
            data[key] = value
        out["data"] = data
        out.pop("service", None)
        out["action"] = norm_service(raw)
        # [CHANGED v3.7.0] A MOVE follows the same target rule as a coil, so picking devices or an
        # area on a value assignment writes a proper target block.
        out = _apply_continue_on_error(out, el)
        updates, kind = target_updates(el)
        if updates and "__target_spec__" in updates:
            return _patch(out, updates)
        return _patch(out, {"entity_id": target})

    domain = domain_of(target)
    svc_map = {
        "input_datetime": ("input_datetime.set_datetime", "time"),
        "input_number": ("input_number.set_value", "value"),
        "input_text": ("input_text.set_value", "value"),
        "input_select": ("input_select.select_option", "option"),
        "number": ("number.set_value", "value"),
        "select": ("select.select_option", "option"),
        "text": ("text.set_value", "value"),
        "counter": ("counter.set_value", "value"),
    }
    svc, key = svc_map.get(domain, ("", ""))
    if not svc:
        return {"action": target, "data": {"value": value}} if target else None
    return {"action": svc, "target": {"entity_id": target}, "data": {key: value}}


def _math_action(el):
    t = el.get("type", "math_add")
    op = MATH_SYMBOL.get(t, "+")
    a = el.get("sourceA", "")
    b = el.get("sourceB", "")
    target = el.get("target", "")
    a_expr = f"(states('{a}') | float(0))" if "." in str(a) else f"({a})"
    b_expr = f"(states('{b}') | float(0))" if "." in str(b) else f"({b})"

    if t == "math_div":
        precision = el.get("precision", 2)
        fallback = el.get("fallback", 0)
        expr = ("{{ ((" + a_expr + " / " + b_expr + ") | round(" + str(precision) + "))"
                " if " + b_expr + " != 0 else " + str(fallback) + " }}")
    else:
        expr = "{{ " + a_expr + " " + op + " " + b_expr + " }}"

    domain = domain_of(target)
    svc = "input_number.set_value" if domain in ("input_number", "") else f"{domain}.set_value"
    return {"action": svc, "target": {"entity_id": target}, "data": {"value": expr}}


def _element_to_actions(el):
    """Always returns a list. An element that carries an unmapped node returns it untouched."""
    t = el.get("type", "")

    if t == "move" and el.get("mode") == "both" and _untouched(el) and isinstance(el.get("raw2"), dict):
        return [dict(el["raw"]), dict(el["raw2"])]

    if _untouched(el):
        # The shape of the original node decides, not the shape of the drawn element. A contact that
        # came from wait_for_trigger goes back as wait_for_trigger, and a coil that came from a device
        # action goes back as that device action, registry ids and all.
        raw = el.get("raw")
        if isinstance(raw, dict) and not raw.get("condition") and not norm_kind(raw):
            return [dict(raw)]

    if t in ("native", "device"):  # legacy saves only, the model has no opaque block any more
        raw = el.get("raw")
        return [dict(raw)] if isinstance(raw, dict) else []

    if t == "repeat":
        rep = {}
        loop = el.get("loopType", "count")
        val = el.get("value", "1")
        if loop == "count":
            try:
                rep["count"] = int(val)
            except (TypeError, ValueError):
                rep["count"] = val
        elif loop == "for_each":
            rep["for_each"] = [x.strip() for x in str(val).split(",")]
        elif loop == "while":
            rep["while"] = [{"condition": "template", "value_template": val}]
        elif loop == "until":
            rep["until"] = [{"condition": "template", "value_template": val}]
        seq = []
        for child in el.get("sequence", []) or []:
            seq.extend(_element_to_actions(child))
        rep["sequence"] = seq
        return [{"repeat": rep}]

    if t == "parallel":
        if _is_condition(el):
            cond = _element_to_condition(el)
            return [cond] if cond else []
        branches = []
        shapes = el.get("branchWrapped") or []
        for idx, b in enumerate(el.get("branches", [])):
            seq = []
            for child in b:
                seq.extend(_element_to_actions(child))
            if not seq:
                continue
            wrap = shapes[idx] if idx < len(shapes) else (len(seq) > 1)
            branches.append({"sequence": seq} if (wrap or len(seq) > 1) else seq[0])
        return [{"parallel": branches}] if branches else []

    if t == "timer_ton":
        return [{"delay": el.get("label", "00:00:01")}]
    if t == "timer_toff":
        return [{"delay": el.get("label", "00:00:01")}]

    if t == "wait":
        return [{"wait_for_trigger": [{"trigger": "state", "entity_id": el.get("label", "")}]}]

    if t == "move":
        mode = el.get("mode", "value")
        # [ADDED v3.8.0] The spoken reply is drawn as MOVE TTS but it is not a text to speech service
        # call, so it is caught before the notify compiler and goes back to its own key.
        if el.get("service") == "set_conversation_response" or (
                isinstance(el.get("raw"), dict) and "set_conversation_response" in el["raw"]):
            out = dict(el.get("raw") or {})
            out["set_conversation_response"] = el.get("tts") or el.get("source") or ""
            return [out]
        if mode in ("notify", "tts", "both"):
            return _notify_actions(el)
        node = _move_value_action(el)
        return [node] if node else []

    if t == "notify":  # legacy element, still compiles
        return [{"action": el.get("target", ""), "data": {"message": el.get("source", "")}}]

    if t == "ctu":
        return [{"action": "counter.increment", "target": {"entity_id": el.get("source", "")}}]

    if t.startswith("math_"):
        return [_math_action(el)]

    if t.startswith("coil"):
        raw = el.get("raw")
        if isinstance(raw, dict) and norm_service(raw):
            out = dict(raw)
            out.pop("service", None)
            # [CHANGED v3.24.0] The service chosen in the inspector wins, so switching a cover from
            # close to open or to stop comes back out as that service.
            picked = str(el.get("service") or "").strip()
            out["action"] = picked if re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", picked) else norm_service(raw)
            out = _apply_continue_on_error(out, el)
            # [CHANGED v3.6.0] A coil that came from a device, an area or a label target keeps that
            # target untouched unless the user typed a real entity id over it.
            updates, kind = target_updates(el)
            return [_patch(out, updates, target_kind=kind) if updates else out]
        # [CHANGED v3.30.0] A coil drawn from scratch, with no node behind it yet.
        svc = ("homeassistant.toggle" if t == "coil_t"
               else "homeassistant.turn_off" if t == "coil_r"
               else "homeassistant.turn_on")
        return [{"action": svc, "target": {"entity_id": clean_target(el.get("label", ""))}}]

    if _is_condition(el):
        cond = _element_to_condition(el)
        return [cond] if cond else []

    return []


# ==========================================================================================
# RUNG COMPILATION
# ==========================================================================================

def _split_rung(elements):
    """Leading conditions gate the rung, everything from the first action onwards is the body."""
    head = []
    body = []
    in_body = False
    for el in elements:
        # [CHANGED v3.27.0] An on delay timer that carries forOf is the for of the condition before
        # it, so it belongs to the head. Without this it started the body, and every condition drawn
        # after it was compiled as an action.
        if not in_body and not el.get("fromAction") and (
                el.get("isTrigger") or _is_condition(el)
                or _is_for_timer(el) or _is_recent_timer(el)):
            head.append(el)
        else:
            in_body = True
            body.append(el)
    return head, body


def _group_key(el):
    return el.get("tplId") or el.get("timeId")


def _spans(elements):
    """Consecutive elements that came from one template or one time window travel together."""
    out = []
    i = 0
    while i < len(elements):
        key = _group_key(elements[i])
        if key:
            j = i
            while j < len(elements) and _group_key(elements[j]) == key:
                j += 1
            out.append((key, elements[i:j]))
            i = j
        else:
            out.append((None, [elements[i]]))
            i += 1
    return out


def _looks_like_entity(value):
    v = str(value or "")
    return "." in v and " " not in v and not v.startswith("calc.") and not v.replace(".", "").isdigit()


def _side_expr(el, which, math_map):
    """The Jinja text for one side of a comparison, reusing the original text when untouched."""
    value = el.get("sourceA") if which == "A" else el.get("sourceB")
    disp = el.get("dispA") if which == "A" else el.get("dispB")
    orig = el.get("exprA") if which == "A" else el.get("exprB")
    if str(value).startswith("calc.") and value in math_map:
        return _math_expr(math_map[value], math_map)
    if orig and str(value) == str(disp):
        return orig
    if _looks_like_entity(value):
        return f"states('{value}') | float(0)"
    if str(value).replace(".", "").replace("-", "").isdigit():
        return str(value)
    return f"'{value}'"


def _math_expr(el, math_map):
    if el.get("expr") and el.get("sourceA") == el.get("dispA") and el.get("sourceB") == el.get("dispB"):
        return el["expr"]
    op = MATH_SYMBOL.get(el.get("type"), "+")
    return f"({_side_expr(el, 'A', math_map)} {op} {_side_expr(el, 'B', math_map)})"


TPL_OP = {"cmp_eq": "==", "cmp_ne": "!=", "cmp_gt": ">", "cmp_lt": "<", "cmp_ge": ">=", "cmp_le": "<="}


def _template_expr(elements, math_map):
    parts = []
    for el in elements:
        t = el.get("type", "")
        if t.startswith("math_"):
            continue  # inlined into the comparison that reads it
        if t == "parallel":
            branch_exprs = [_template_expr(b, math_map) for b in el.get("branches", [])]
            branch_exprs = [b for b in branch_exprs if b]
            if branch_exprs:
                parts.append("(" + " or ".join(branch_exprs) + ")")
            continue
        if t.startswith("contact_"):
            neg = t in ("contact_nc", "contact_n")
            parts.append(f"is_state('{el.get('label', '')}', '{'off' if neg else 'on'}')")
            continue
        op = TPL_OP.get(t, "==")
        if str(el.get("sourceB")) == "true" and el.get("expr") and el.get("sourceA") == el.get("dispA"):
            parts.append(el["expr"])
            continue
        parts.append(f"{_side_expr(el, 'A', math_map)} {op} {_side_expr(el, 'B', math_map)}")
    return " and ".join(p for p in parts if p)


def _collect_math(elements, math_map):
    for el in elements:
        if el.get("type", "").startswith("math_") and el.get("target"):
            math_map[el["target"]] = el
        if el.get("type") == "parallel":
            for b in el.get("branches", []):
                _collect_math(b, math_map)


def _time_condition(span):
    out = {"condition": "time"}
    for el in span:
        t = el.get("type")
        if t == "cmp_rng":
            out["after"] = el.get("sourceB")
            out["before"] = el.get("sourceC")
        elif t in ("cmp_ge", "cmp_gt"):
            out["after"] = el.get("sourceB")
        elif t in ("cmp_le", "cmp_lt"):
            out["before"] = el.get("sourceB")
        elif t == "cmp_eq" and str(el.get("sourceA")) == "weekday":
            days = str(el.get("sourceB") or "")
            out["weekday"] = [d.strip() for d in days.split(",") if d.strip()]
    return out


def _group_untouched(elements):
    """True when no part of the group was edited, nested branches included."""
    for el in elements:
        if el.get("sig") and el["sig"] != element_sig(el):
            return False
        if el.get("type") == "parallel":
            for b in el.get("branches", []):
                if not _group_untouched(b):
                    return False
    return True


def _group_condition(span):
    """One condition for the whole group, from the original node when nothing was touched."""
    root = span[0]
    if isinstance(root.get("raw"), dict) and _group_untouched(span):
        return dict(root["raw"])
    if root.get("timeId"):
        return _time_condition(span)
    math_map = {}
    _collect_math(span, math_map)
    expr = _template_expr(span, math_map)
    return {"condition": "template", "value_template": "{{ " + expr + " }}"} if expr else None


def hms_to_for(text):
    """[ADDED v3.27.0] hh:mm:ss back into the mapping Home Assistant writes for a for."""
    parts = str(text or "").split(":")
    try:
        h, m, s = [int(float(x)) for x in (parts + ["0", "0", "0"])[:3]]
    except (TypeError, ValueError):
        return None
    if h == m == s == 0:
        return None
    return {"hours": h, "minutes": m, "seconds": s}


def _is_for_timer(el):
    return el.get("type") == "timer_ton" and (el.get("isFor") or el.get("forOf"))


def _is_recent_timer(el):
    """[ADDED v3.33.0] An off delay timer drawn straight after a contact says that the contact only
    has to have been true lately, not right now."""
    return el.get("type") == "timer_tof" and el.get("isRecent")


def _recent_after(head, index):
    nxt = head[index + 1] if index + 1 < len(head) else None
    if nxt and _is_recent_timer(nxt):
        secs = hms_to_seconds(nxt.get("label"))
        return secs if secs > 0 else None
    return None


def _recent_condition(el, seconds):
    """The condition that says it holds now or held within the window. Every entity carries the
    moment it reached its present state, so this needs no helper and no timer of its own."""
    entity = clean_target(el.get("label"))
    if not entity or "." not in entity:
        return None
    state = el.get("recentState")
    if not state:
        state = "off" if el.get("type") == "contact_nc" else "on"
    return {
        "condition": "template",
        "value_template": (
            "{{ is_state('%s','%s') and "
            "(now() - states.%s.last_changed).total_seconds() < %d }}" % (entity, state, entity, seconds)
        ),
    }


def _for_after(head, index):
    """[ADDED v3.27.0] The on delay timer drawn straight after the element at this position, which is
    that condition's for. A timer with no marker is an ordinary delay and is not one of these."""
    nxt = head[index + 1] if index + 1 < len(head) else None
    if nxt and _is_for_timer(nxt):
        return hms_to_for(nxt.get("label"))
    return None


def _rung_conditions(head, trig_ids, use_trigger_refs):
    conds = []
    for key, span in _spans(head):
        if key:
            cond = _group_condition(span)
            if cond:
                conds.append(cond)
            continue
        el = span[0]
        if el.get("autoGate"):
            continue  # drawn only to show what starts the flow, the automation trigger already gates it
        if el.get("isTrigger"):
            if use_trigger_refs:
                tid = trig_ids.get(_trigger_key(el))
                if tid:
                    conds.append({"condition": "trigger", "id": tid})
            continue
        if el.get("type") == "parallel":
            if all(x.get("autoGate") for b in el.get("branches", []) for x in b):
                continue
            trig_branches = [b for b in el.get("branches", []) if any(x.get("isTrigger") for x in b)]
            if trig_branches and len(trig_branches) == len(el.get("branches", [])):
                if use_trigger_refs:
                    ors = []
                    for b in el.get("branches", []):
                        sub = []
                        for x in b:
                            if x.get("isTrigger"):
                                tid = trig_ids.get(_trigger_key(x))
                                if tid:
                                    sub.append({"condition": "trigger", "id": tid})
                            else:
                                c = _element_to_condition(x)
                                if c:
                                    sub.append(c)
                        if len(sub) == 1:
                            ors.append(sub[0])
                        elif sub:
                            ors.append({"condition": "and", "conditions": sub})
                    if len(ors) == 1:
                        conds.append(ors[0])
                    elif ors:
                        conds.append({"condition": "or", "conditions": ors})
                continue
        if _is_for_timer(el) or _is_recent_timer(el):
            continue   # it belongs to the condition before it, not a condition of its own
        # [ADDED v3.33.0] A contact with an off delay timer behind it asks whether the thing was
        # true lately rather than whether it is true now.
        recent = _recent_after(head, head.index(el)) if el in head else None
        if str(el.get("type", "")).startswith("contact_") and (recent or el.get("recentState")):
            if recent:
                built = _recent_condition(el, recent)
            else:
                # The timer was taken off the rung, so the question is no longer whether it happened
                # lately but simply whether it holds. The window goes with the timer.
                entity = clean_target(el.get("label"))
                state = el.get("recentState") or ("off" if el.get("type") == "contact_nc" else "on")
                built = {"condition": "state", "entity_id": entity, "state": state} if entity else None
            if built:
                conds.append(built)
                continue
        cond = _element_to_condition(el)
        if cond:
            # [ADDED v3.27.0] The timer drawn after this condition is its for. When there is none,
            # any for the node used to carry is gone, because the timer was taken off the rung.
            held = _for_after(head, head.index(el)) if el in head else None
            cond = dict(cond)
            if held:
                cond["for"] = held
            else:
                cond.pop("for", None)
            conds.append(cond)
    return conds


def _all_triggers(el):
    if el.get("type") != "parallel":
        return False
    return all(x.get("isTrigger") or _all_triggers(x) for b in el.get("branches", []) for x in b)


def _head_trigger_keys(head):
    keys = set()
    for el in head:
        if el.get("isTrigger"):
            keys.add(_trigger_key(el))
        elif el.get("type") == "parallel":
            for b in el.get("branches", []):
                keys |= _head_trigger_keys(b)
    return keys


def _rung_actions(body):
    out = []
    for key, span in _spans(body):
        if key:
            root = span[0]
            raw = root.get("raw")
            if isinstance(raw, dict) and "wait_template" in raw and _group_untouched(span):
                out.append(dict(raw))
                continue
            cond = _group_condition(span)
            if cond:
                if isinstance(raw, dict) and "wait_template" in raw:
                    out.append({"wait_template": cond.get("value_template", "")})
                else:
                    out.append(cond)
            continue
        out.extend(_element_to_actions(span[0]))
    return out


def _collect_triggers(net):
    """One entry per distinct trigger, in the order they appear."""
    order = []
    seen = {}
    for rung in net.get("rungs", []):
        for el in _walk(rung.get("elements", [])):
            if el.get("isTrigger"):
                key = _trigger_key(el)
                if key not in seen:
                    seen[key] = el
                    order.append(key)
    trig_ids = {}
    triggers = []
    for i, key in enumerate(order):
        el = seen[key]
        tid = el.get("trigId") or f"t{i + 1}"
        trig_ids[key] = tid
        triggers.append(_element_to_trigger(el, tid))
    return triggers, trig_ids


def _walk(elements):
    for el in elements:
        yield el
        if el.get("type") == "parallel":
            for b in el.get("branches", []):
                for x in _walk(b):
                    yield x
        elif el.get("type") == "repeat":
            for x in _walk(el.get("sequence", []) or []):
                yield x


def _path_steps(path):
    from .yaml_to_libi import norm_kind  # noqa: F401 - keeps the import list stable
    parts = str(path).split(".")
    steps = []
    for i in range(0, len(parts) - 1, 2):
        kind = "seq" if parts[i + 1] == "seq" else "b"
        steps.append({"idx": int(parts[i]), "kind": kind,
                      "bidx": -1 if kind == "seq" else int(str(parts[i + 1])[1:])})
    return steps, int(parts[-1])


def _arr_by_steps(elements, steps):
    cur = elements
    for st in steps:
        if st["idx"] >= len(cur):
            return None
        el = cur[st["idx"]]
        cur = el.get("sequence") if st["kind"] == "seq" else (el.get("branches") or [None] * 9)[st["bidx"]]
        if cur is None:
            return None
    return cur


def _merge_pair(upper, lower, up_path, lo_path):
    """[ADDED v3.0.0] A link is a column. What is before it on both rungs becomes an OR that closes
    there, what is after it stays open. This is the same shape the editor draws, turned into one
    circuit so the rest of the compiler sees exactly what it used to see."""
    up_steps, i = _path_steps(up_path)
    lo_steps, j = _path_steps(lo_path)
    up_arr = _arr_by_steps(upper["elements"], up_steps)
    lo_arr = _arr_by_steps(lower["elements"], lo_steps)
    if up_arr is None or lo_arr is None or i == 0:
        return False

    up_head, up_tail = up_arr[:i], up_arr[i:]
    lo_head, lo_tail = lo_arr[:j], lo_arr[j:]
    merged = []
    if lo_head:
        merged.append({"id": f"m{id(lower)}h", "type": "parallel", "closed": True,
                       "branches": [up_head, lo_head], "isTrigger": False})
    else:
        merged.extend(up_head)
    if lo_tail:
        merged.append({"id": f"m{id(lower)}t", "type": "parallel", "closed": False,
                       "branches": [up_tail, lo_tail], "isTrigger": False})
    else:
        merged.extend(up_tail)

    up_arr[:] = merged
    lo_arr[:] = []
    return True


def merge_linked_rungs(net):
    """Returns the rung list the compiler should read: every group of linked rungs collapsed into the
    single circuit they draw. The stored net is never touched."""
    links = net.get("links") or []
    if not links:
        return net.get("rungs", []) or []

    import copy as _copy
    rungs = _copy.deepcopy(net.get("rungs", []) or [])
    by_id = {r.get("id"): r for r in rungs}
    order = [r.get("id") for r in rungs]
    absorbed = set()

    # Lower rungs are folded into the rung above them, following the order they appear in the net.
    for link in sorted(links, key=lambda l: (order.index(l["bRung"]) if l["bRung"] in order else 0)):
        a, b = link.get("aRung"), link.get("bRung")
        if a not in by_id or b not in by_id:
            continue
        upper_id, lower_id = (a, b) if order.index(a) <= order.index(b) else (b, a)
        up_path = link.get("aPath") if upper_id == a else link.get("bPath")
        lo_path = link.get("bPath") if upper_id == a else link.get("aPath")
        while upper_id in absorbed:
            upper_id = absorbed[upper_id] if isinstance(absorbed, dict) else upper_id
            break
        if _merge_pair(by_id[upper_id], by_id[lower_id], up_path, lo_path):
            if by_id[upper_id].get("comment") and by_id[lower_id].get("comment"):
                by_id[upper_id]["comment"] += ", or " + by_id[lower_id]["comment"]
            absorbed.add(lower_id)

    return [r for r in rungs if r.get("id") not in absorbed or (r.get("elements") or [])]


def _group_rungs(rungs):
    """[ADDED v3.5.0] Splits the rung list into the grouped rungs, keyed by group id, and the plain
    ones. Lifted out of ast_to_yaml unchanged so a script builds its sequence with the same code."""
    groups = {}
    plain = []
    for rung in rungs:
        gid = rung.get("group")
        if gid:
            groups.setdefault(gid, []).append(rung)
        else:
            plain.append(rung)
    return groups, plain


def _rungs_to_actions(rungs, groups, trig_ids):
    """[ADDED v3.5.0] The per rung compilation that an automation with more than one rung already
    used, lifted out of ast_to_yaml unchanged. With an empty trig_ids it is exactly what a script
    sequence needs: every rung contributes its plain actions or an if / then that wraps them."""
    actions = []
    ordered = []
    for rung in rungs:
        gid = rung.get("group")
        if gid:
            if all(r is not rung for r in ordered if isinstance(r, dict) and r.get("__gid") == gid):
                pass
        ordered.append(rung)

    emitted_groups = set()
    for rung in rungs:
        gid = rung.get("group")
        if gid:
            if gid in emitted_groups:
                continue
            emitted_groups.add(gid)
            members = sorted(groups[gid], key=lambda r: r.get("groupIdx", 0))
            options = []
            default_seq = None
            for member in members:
                head, body = _split_rung(member.get("elements", []))
                conds = _rung_conditions(head, trig_ids, use_trigger_refs=True)
                seq = _rung_actions(body)
                if member.get("isDefault"):
                    default_seq = seq
                else:
                    options.append({"conditions": conds, "sequence": seq})
            kind = members[0].get("groupKind", "choose")
            if kind == "if" and len(options) <= 1:
                # A group that came from if / then / else goes back as if / then / else.
                block = {"if": options[0]["conditions"] if options else [],
                         "then": options[0]["sequence"] if options else []}
                if default_seq:
                    block["else"] = default_seq
            else:
                block = {"choose": options}
                if default_seq:
                    block["default"] = default_seq
            actions.append(block)
        else:
            head, body = _split_rung(rung.get("elements", []))
            conds = _rung_conditions(head, trig_ids, use_trigger_refs=True)
            seq = _rung_actions(body)
            only_triggers = all(el.get("isTrigger") or _all_triggers(el) for el in head) if head else True
            covers_all = only_triggers and len(_head_trigger_keys(head)) >= len(trig_ids)
            if conds and not covers_all:
                actions.append({"if": conds, "then": seq})
            else:
                actions.extend(seq)
    return actions


def ast_to_automation(hass, net_ast):
    """[CHANGED v3.5.0] The automation compiler, byte for byte what ast_to_yaml did before, with the
    per rung part moved into _rungs_to_actions so the script compiler can share it."""
    net = net_ast or {}
    rungs = merge_linked_rungs(net)

    triggers, trig_ids = _collect_triggers({"rungs": rungs})

    groups, plain = _group_rungs(rungs)

    # A single plain rung with no groups is the simple automation shape.
    simple = (len(rungs) == 1 and not groups)

    conditions = []
    actions = []

    if simple:
        head, body = _split_rung(rungs[0].get("elements", []))
        conditions = _rung_conditions(head, trig_ids, use_trigger_refs=False)
        actions = _rung_actions(body)
    else:
        actions = _rungs_to_actions(rungs, groups, trig_ids)

    out = {
        "id": net.get("ha_id") or net.get("id"),
        "alias": net.get("name"),
        "description": net.get("description", ""),
        "triggers": triggers,
        "conditions": conditions,
        "actions": actions,
    }
    if net.get("mode"):
        out["mode"] = net["mode"]
    if net.get("max") is not None:
        out["max"] = net["max"]
    if net.get("variables"):
        out["variables"] = net["variables"]
    for k, v in (net.get("extra") or {}).items():
        out.setdefault(k, v)
    return out


def ast_to_script(hass, net_ast):
    """[ADDED v3.5.0] A script is a sequence and nothing else. There is no trigger and no automation
    level condition block, so every rung goes through the same per rung compilation an automation
    with several rungs already used, only with no trigger ids to reference."""
    net = net_ast or {}
    rungs = _without_triggers(merge_linked_rungs(net))
    groups, plain = _group_rungs(rungs)

    out = {
        "alias": net.get("name"),
        "sequence": _rungs_to_actions(rungs, groups, {}),
    }
    if net.get("description"):
        out["description"] = net.get("description")
    if net.get("mode"):
        out["mode"] = net["mode"]
    if net.get("max") is not None:
        out["max"] = net["max"]
    if net.get("variables"):
        out["variables"] = net["variables"]
    for k, v in (net.get("extra") or {}).items():
        out.setdefault(k, v)
    return out


def _scene_entry(el):
    """[ADDED v3.5.0] One element of a scene as a pair of entity and the state it is put into, or
    None when the element assigns nothing. A scene has no order and no logic, only end states."""
    t = el.get("type", "")
    if t in SCENE_ON_TYPES or t == "coil_r":
        ent = str(el.get("label") or "").strip()
        if not ent:
            return None
        return ent, ("off" if t == "coil_r" else "on")
    if t == "move" and (el.get("mode") or "value") == "value":
        ent = str(el.get("target") or "").strip()
        if not ent:
            return None
        value = el.get("source", "")
        key = el.get("valueKey") or ""
        if key:
            return ent, {key: _num(value)}
        if str(value).strip() == "":
            return None
        return ent, _num(value)
    return None


def _scene_entities(rungs):
    """[ADDED v3.5.0] The entities map of a scene. Two elements that touch the same entity are merged
    rather than one overwriting the other, so a coil and a brightness assignment live together."""
    entities = {}

    def put(ent, state):
        current = entities.get(ent)
        if isinstance(state, dict):
            if isinstance(current, dict):
                merged = dict(current)
            elif current is not None:
                merged = {"state": current}
            else:
                merged = {}
            merged.update(state)
            entities[ent] = merged
        elif isinstance(current, dict):
            merged = dict(current)
            merged["state"] = state
            entities[ent] = merged
        else:
            entities[ent] = state

    def walk(elements):
        for el in elements or []:
            if el.get("type") == "parallel":
                for branch in el.get("branches", []):
                    walk(branch)
                continue
            if el.get("type") == "repeat":
                walk(el.get("sequence", []))
                continue
            entry = _scene_entry(el)
            if entry:
                put(entry[0], entry[1])

    for rung in rungs or []:
        walk(rung.get("elements", []))
    return entities


def ast_to_scene(hass, net_ast):
    """[ADDED v3.5.0] A scene is a snapshot. No triggers, no timing and no conditions, only the
    states the entities are asked to wear."""
    net = net_ast or {}
    rungs = _without_triggers(merge_linked_rungs(net))
    out = {
        "id": str(net.get("ha_id") or net.get("id") or ""),
        "name": net.get("name"),
        "entities": _scene_entities(rungs),
    }
    if net.get("description"):
        out["description"] = net.get("description")
    for k, v in (net.get("extra") or {}).items():
        out.setdefault(k, v)
    return out


def ast_to_yaml(hass, net_ast):
    """[CHANGED v3.5.0] The level of the net decides the schema. A net with no level is an
    automation, so every net saved before this version compiles exactly as it did."""
    level = net_level(net_ast)
    if level == "script":
        return ast_to_script(hass, net_ast)
    if level == "scene":
        return ast_to_scene(hass, net_ast)
    return ast_to_automation(hass, net_ast)


# ==========================================================================================
# ROUND TRIP CHECK - the safety gate
# ==========================================================================================

def _canon(node):
    """Compares meaning, not spelling: trigger/platform, action/service, plural keys, numbers as text,
    and the and/or/not shorthand against the long form."""
    if isinstance(node, dict):
        for word in ("and", "or", "not"):
            if word in node and "condition" not in node and isinstance(node.get(word), list):
                node = {"condition": word, "conditions": node[word]}
                break
        out = {}
        for k, v in node.items():
            key = k
            if k in ("platform",):
                key = "trigger"
            elif k in ("service",):
                key = "action"
            elif k == "triggers":
                key = "trigger"
            elif k == "conditions" and "condition" not in node:
                key = "condition"
            elif k == "actions":
                key = "action"
            val = _canon(v)
            if val in ({}, [], "", None):
                continue
            out[key] = val
        return out
    if isinstance(node, list):
        return [_canon(x) for x in node]
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        return str(node)
    return node


def verify_round_trip(hass, automation_dict):
    """Import then export then compare. Returns ok plus the parts that did not survive."""
    from .yaml_to_libi import yaml_to_ast
    try:
        net = yaml_to_ast(hass, automation_dict)
        back = ast_to_yaml(hass, net)
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "error": str(err), "issues": ["conversion crashed"]}

    src = _canon(automation_dict)
    dst = _canon(back)
    issues = []

    def compare(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a:
                if k in ("id", "alias", "description"):
                    continue
                if k not in b:
                    issues.append(f"missing {path}.{k}")
                else:
                    compare(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                issues.append(f"length {path}: {len(a)} to {len(b)}")
            for i, (x, y) in enumerate(zip(a, b)):
                compare(x, y, f"{path}[{i}]")
        elif a != b:
            issues.append(f"changed {path}: {short(a, 40)} to {short(b, 40)}")

    compare(src, dst, "")
    return {"ok": not issues, "issues": issues[:40], "count": len(issues)}