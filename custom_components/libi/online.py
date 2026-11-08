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
# v1.0.0
# [ADDED v1.0.0 | 2026-11-07] Purpose: Online's Real - the user's request (2026-11-07): FORCE TRUE on a trigger runs the
#   automation in Home Assistant as if that trigger fired now, and its result is drawn on the blocks from Home
#   Assistant's own trace. Home Assistant's automation.trigger starts a run with no trigger at all, so a rung that runs
#   for its own trigger (trigger id) never ran.
"""Online's Real: a run of an automation in Home Assistant, as if one of its triggers fired.

What a run can reach is read from what Home Assistant has loaded - the automation, every script it calls and every
automation it runs, and the scripts and automations those call - never from LIBI's drawing (RULE 11). A run is refused
(RULE 9, the user's choice of 2026-11-06) when it can reach a lock, an alarm or a cover: named anywhere in those configs,
in an area, a floor, a device or a label they target, or in a scene or a group they name. What cannot be told - a script
or an automation that is not loaded, a target written as a template - is refused too (RULE 31).

Nothing runs unless the panel asks with fire set, after the user confirmed in the panel, and the automation is still the
one the user was shown (before): the plan is made again just before the run, and a change in between refuses it.

The run is Home Assistant's own: the automation entity's async_trigger, as its automation.trigger service calls it, with
the trigger variables a trigger of that place gives (id, idx, platform) and a description that says LIBI started it. Home
Assistant checks the automation's conditions (unless the user chose to skip them), runs its actions, honours its mode,
and keeps the trace, in which the panel finds the result.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .libi_to_yaml import same_config, trigger_place

_LOGGER = logging.getLogger(__name__)

# The domains a real run from LIBI never drives (RULE 9).
NEVER_RUN_REAL = ("lock", "alarm_control_panel", "cover")
# Every domain.object written in a config, overlapping: "states.cover.gate" names cover.gate too.
_NAME = re.compile(r"(?=\b([a-z_]+)\.([a-z0-9_]+)\b)")
# script.turn_on and its kin are actions, not scripts.
_SCRIPT_SERVICES = frozenset({"turn_on", "turn_off", "toggle", "reload"})
_TARGET_KEYS = ("entity_id", "device_id", "area_id", "floor_id", "label_id")
_REFERENCES = ("referenced_entities", "referenced_devices", "referenced_areas", "referenced_floors",
               "referenced_labels")
DESCRIPTION = "LIBI: FORCE TRUE"
DESCRIPTION_NONE = "LIBI: run without a trigger"


def _templated(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _walk_calls(node: Any, driven: set[str], templated: set[str]) -> None:
    """The actions in a config: what each targets by name (driven), and each target written as a template."""
    if isinstance(node, list):
        for item in node:
            _walk_calls(item, driven, templated)
        return
    if not isinstance(node, dict):
        return
    call = node.get("action", node.get("service"))
    if isinstance(call, str):
        if _templated(call):
            templated.add(call)
        elif "." in call:
            for where in (node.get("target"), node, node.get("data")):
                if not isinstance(where, dict):
                    continue
                for key in _TARGET_KEYS:
                    for value in _as_list(where.get(key)):
                        if _templated(value):
                            templated.add(f"{call} {key}")
                        elif key == "entity_id" and isinstance(value, str):
                            driven.update(part.strip() for part in value.split(",") if part.strip())
    for value in node.values():
        if isinstance(value, (dict, list)):
            _walk_calls(value, driven, templated)


def _component(hass: HomeAssistant, domain: str):
    """The entity component of automation or script: where Home Assistant keeps what it loaded."""
    component = hass.data.get(domain)
    return component if component is not None and hasattr(component, "get_entity") else None


@callback
def real_run_reach(hass: HomeAssistant, automation) -> dict[str, list[str]]:
    """What a real run of an automation can reach: risky (a lock, an alarm or a cover), drives (the entities its actions
    name), unread (a script or an automation it calls that Home Assistant has not loaded), templated (a target that is a
    template). Every script and automation on the way is followed, each once."""
    scripts = _component(hass, "script")
    automations = _component(hass, "automation")
    names: set[str] = set()
    found: dict[str, set[str]] = {attr: set() for attr in _REFERENCES}
    driven: set[str] = set()
    templated: set[str] = set()
    unread: list[str] = []
    queue: list[tuple[str, Any]] = [(automation.entity_id, automation)]
    seen: set[str] = set()
    while queue:
        entity_id, obj = queue.pop(0)
        if entity_id in seen:
            continue
        seen.add(entity_id)
        raw = getattr(obj, "raw_config", None) if obj is not None else None
        if not isinstance(raw, dict) or getattr(obj, "available", True) is False:
            unread.append(entity_id)
            continue
        named = {f"{d}.{o}" for d, o in _NAME.findall(json.dumps(raw, default=str))}
        names |= named
        for attr in _REFERENCES:
            try:
                found[attr] |= set(getattr(obj, attr, None) or ())
            except Exception:  # noqa: BLE001 - what cannot be read is not known to be safe
                unread.append(entity_id)
        steps = raw.get("sequence") if entity_id.startswith("script.") else raw.get("actions", raw.get("action"))
        calls: set[str] = set()
        _walk_calls(steps, calls, templated)
        driven |= calls
        # A script named anywhere (script.x as an action, or script.turn_on's target), an automation an action runs.
        for name in sorted(named):
            domain, object_id = name.split(".", 1)
            if domain == "script" and object_id not in _SCRIPT_SERVICES:
                queue.append((name, scripts.get_entity(name) if scripts else None))
        for name in sorted(calls):
            if name.startswith("automation."):
                queue.append((name, automations.get_entity(name) if automations else None))

    entities = set(names) | found["referenced_entities"]
    devices = set(found["referenced_devices"])
    areas = set(found["referenced_areas"])
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    all_areas = list(ar.async_get(hass).async_list_areas())
    for floor in found["referenced_floors"]:
        areas |= {a.id for a in all_areas if getattr(a, "floor_id", None) == floor}
    for label in found["referenced_labels"]:
        entities |= {e.entity_id for e in er.async_entries_for_label(ent_reg, label)}
        devices |= {d.id for d in dr.async_entries_for_label(dev_reg, label)}
        areas |= {a.id for a in all_areas if label in (getattr(a, "labels", None) or ())}
    for area in areas:
        entities |= {e.entity_id for e in er.async_entries_for_area(ent_reg, area)}
        devices |= {d.id for d in dr.async_entries_for_area(dev_reg, area)}
    for device in devices:
        entities |= {e.entity_id for e in er.async_entries_for_device(ent_reg, device, include_disabled_entities=True)}
    # A scene or a group turned on reaches what it holds: Home Assistant lists that in its entity_id attribute.
    pending = list(entities)
    while pending:
        state = hass.states.get(pending.pop())
        members = state.attributes.get("entity_id") if state is not None else None
        for member in members if isinstance(members, (list, tuple)) else ():
            if isinstance(member, str) and member not in entities:
                entities.add(member)
                pending.append(member)
    risky = sorted(n for n in entities if n.split(".", 1)[0] in NEVER_RUN_REAL)
    drives = sorted(n for n in driven if n != automation.entity_id and hass.states.get(n) is not None)
    return {"risky": risky, "drives": drives, "unread": sorted(set(unread)), "templated": sorted(templated)}


def _fingerprint(raw: Any) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _triggers_of(raw: dict) -> list:
    triggers = raw.get("triggers", raw.get("trigger", []))
    if isinstance(triggers, dict):
        return [triggers]
    return triggers if isinstance(triggers, list) else []


def _conditions_of(raw: dict) -> list:
    conditions = raw.get("conditions", raw.get("condition", []))
    if isinstance(conditions, dict):
        return [conditions]
    return conditions if isinstance(conditions, list) else []


def _without_id(trigger: Any) -> Any:
    return {k: v for k, v in trigger.items() if k != "id"} if isinstance(trigger, dict) else trigger


def _refused(reason: str, **extra) -> dict[str, Any]:
    return {"ok": False, "reason": reason, **extra}


@callback
def fire_plan(hass: HomeAssistant, entity_id: str, trigger: int | None = None, trigger_id: str | None = None,
              net: dict | None = None, element_id: str | None = None) -> tuple[dict[str, Any], Any, dict | None]:
    """What a real run of entity_id, as if its trigger fired, would be: (the answer for the panel, the automation entity,
    the run variables). The answer says why not (reason) or what it is (name, trigger, conditions, drives, before).
    The trigger is found by its place (trigger), by its id (trigger_id), or by the element of a NET drawn in LIBI
    (net, element_id) - the place the compiler gives it, which must be what Home Assistant has there."""
    automations = _component(hass, "automation")
    entity = automations.get_entity(entity_id) if automations else None
    state = hass.states.get(entity_id)
    if entity is None or state is None:
        return _refused("This NET is not in Home Assistant yet: press SAVE & COMPILE first, or try it in Simulate."), None, None
    raw = getattr(entity, "raw_config", None)
    if state.state == "unavailable" or not isinstance(raw, dict) or not hasattr(entity, "async_trigger"):
        return _refused("Home Assistant could not load this automation, so it does not run: see Settings ▸ "
                        "System ▸ Logs."), None, None
    if state.state != "on":
        return _refused("It is turned off in Home Assistant, so it does not run. Turn it on first."), None, None

    triggers = _triggers_of(raw)
    idx: int | None = None
    if net is not None and element_id:
        try:
            place = trigger_place(net, element_id)
        except Exception:  # noqa: BLE001 - a NET the compiler cannot read names no trigger
            place = None
        if place is None:
            return _refused("This block is not a trigger of the NET."), None, None
        idx, compiled = place
        if idx >= len(triggers) or not same_config(_without_id(compiled), _without_id(triggers[idx])):
            return _refused("Home Assistant's automation has another trigger there: press SAVE & COMPILE, then try "
                            "again."), None, None
    elif trigger is not None:
        idx = trigger
        if idx >= len(triggers) or not isinstance(triggers[idx], dict) or (
                trigger_id is not None and str(triggers[idx].get("id", idx)) != trigger_id):
            return _refused("Home Assistant's automation has another trigger there: open the NET again, or press "
                            "SAVE & COMPILE, then try again."), None, None
    elif trigger_id is not None:
        found = [i for i, t in enumerate(triggers) if isinstance(t, dict) and str(t.get("id", i)) == trigger_id]
        if not found:
            return _refused(f"Home Assistant's automation has no trigger {trigger_id}: press SAVE & COMPILE, then try "
                            "again."), None, None
        idx = found[0]

    reach = real_run_reach(hass, entity)
    if reach["unread"]:
        return _refused(f"Home Assistant has not loaded {', '.join(reach['unread'])}, so LIBI cannot tell what a real run "
                        "would do, and does not run it. Try it in Simulate."), None, None
    if reach["risky"]:
        return _refused(f"LIBI does not run this automation for real: it can reach {', '.join(reach['risky'])}. Try it "
                        "in Simulate, or run it from Home Assistant's own editor.", risky=reach["risky"]), None, None
    if reach["templated"]:
        return _refused("LIBI does not run this automation for real: it picks what it switches with a template "
                        f"({', '.join(reach['templated'])}), so LIBI cannot tell whether that is a lock, an alarm or a "
                        "cover. Try it in Simulate."), None, None

    if idx is None:
        described: dict[str, Any] | None = None
        variables = {"trigger": {"platform": None, "description": DESCRIPTION_NONE}}
    else:
        trig = triggers[idx]
        kind = trig.get("trigger", trig.get("platform"))
        described = {"idx": idx, "id": str(trig.get("id", idx)), "kind": str(kind or ""), "alias": trig.get("alias") or ""}
        variables = {"trigger": {"id": described["id"], "idx": str(idx), "alias": trig.get("alias"), "platform": kind,
                                 "description": f"{DESCRIPTION} (trigger {idx + 1})"}}
    answer = {
        "ok": True,
        "entity_id": entity_id,
        "name": str(state.attributes.get("friendly_name") or raw.get("alias") or entity_id),
        "trigger": described,
        "conditions": len(_conditions_of(raw)),
        "drives": reach["drives"],
        "before": _fingerprint(raw),
    }
    return answer, entity, variables


@callback
def fire(hass: HomeAssistant, entity, variables: dict, skip_condition: bool, context: Context) -> None:
    """The run itself, as Home Assistant's automation.trigger starts it - not waited for: a run with a TON lasts as long
    as the TON. What it does, and an error, are in its trace."""

    async def _run() -> None:
        try:
            await entity.async_trigger(variables, context=context, skip_condition=skip_condition)
        except Exception as err:  # noqa: BLE001 - Home Assistant keeps the error in the trace; this is the log
            _LOGGER.warning("[libi] the run of %s could not start: %s", entity.entity_id, err)

    hass.async_create_task(_run(), f"libi_online_fire_{entity.entity_id}")
