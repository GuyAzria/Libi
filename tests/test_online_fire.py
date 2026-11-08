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
# [ADDED v1.0.0 | 2026-11-07] Purpose: Online's Real against a real Home Assistant - FORCE TRUE on a trigger runs the
#   automation as if that trigger fired, so the rung of that trigger id runs and Home Assistant's trace says so (the
#   user's request, 2026-11-07: automation.trigger starts a run with no trigger, and no rung of theirs ran). Never
#   without fire, never over a changed automation, never one that can reach a lock, an alarm or a cover - named, in an
#   area, on a device, in a script it calls - or whose target is a template; never for a user who is not an
#   administrator.
"""libi/online_fire, as the panel's Online calls it: without fire, what a run would be; with fire, the run."""
import copy

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.libi.libi_to_yaml import trigger_place
from custom_components.libi.yaml_to_libi import yaml_to_ast

from .save_helpers import home_assistant_files, send
from .test_websocket import libi  # noqa: F401 - fixture

# The automation waits for 06:00 with a timer of Home Assistant's, still set when a test ends: what a time trigger is.
pytestmark = pytest.mark.parametrize("expected_lingering_timers", [True])

ENTITY = "automation.train_reminder"
TRAIN = {
    "id": "train", "alias": "Train reminder", "description": "", "mode": "single",
    "triggers": [
        {"trigger": "time", "at": "06:00:00", "id": "morning"},
        {"trigger": "state", "entity_id": "input_boolean.evening", "to": "on", "id": "evening"},
    ],
    "conditions": [],
    "actions": [{"choose": [
        {"conditions": [{"condition": "trigger", "id": "morning"}], "sequence": [{"action": "test.morning"}]},
        {"conditions": [{"condition": "trigger", "id": "evening"}], "sequence": [{"action": "test.evening"}]},
    ]}],
}


def _with(**changes) -> dict:
    auto = copy.deepcopy(TRAIN)
    auto.update(changes)
    return auto


def _calls(hass) -> dict:
    return {name: async_mock_service(hass, "test", name) for name in ("morning", "evening", "always")}


async def _setup(hass, libi, automations=None, scripts=None):  # noqa: F811 - the fixture's folder
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"evening": None, "allowed": None}})
    await home_assistant_files(hass, libi, automations=automations or [copy.deepcopy(TRAIN)], scripts=scripts)


async def _fire(client, hass, **msg) -> dict:
    """As the panel does it: asked, then - the user confirmed - fired with what it was shown (before)."""
    asked = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, **msg})
    assert asked["success"], asked
    if not asked["result"]["ok"]:
        return asked["result"]
    fired = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, **msg, "fire": True,
                                "before": asked["result"]["before"]})
    assert fired["success"], fired
    await hass.async_block_till_done()
    return fired["result"]


async def _runs(client) -> list:
    res = await send(client, {"type": "trace/list", "domain": "automation", "item_id": "train"})
    assert res["success"], res
    return res["result"]


async def test_asking_runs_nothing(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "trigger": 0})
    assert res["success"], res
    plan = res["result"]
    assert plan["ok"] and plan["trigger"] == {"idx": 0, "id": "morning", "kind": "time", "alias": ""}, plan
    assert plan["conditions"] == 0 and plan["before"] and plan["name"] == "Train reminder", plan
    await hass.async_block_till_done()
    assert not any(calls.values()) and await _runs(client) == []


async def test_force_true_runs_the_rung_of_that_trigger(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    done = await _fire(client, hass, trigger=0)
    assert done["ok"] and done["fired"], done
    assert len(calls["morning"]) == 1 and not calls["evening"], calls
    runs = await _runs(client)
    assert len(runs) == 1 and runs[0]["trigger"] == "LIBI: FORCE TRUE (trigger 1)", runs
    got = await send(client, {"type": "trace/get", "domain": "automation", "item_id": "train", "run_id": runs[0]["run_id"]})
    assert "trigger/0" in got["result"]["trace"], list(got["result"]["trace"])
    assert got["result"]["script_execution"] == "finished", got["result"]
    # The other trigger, by its id: its own rung.
    done = await _fire(client, hass, trigger_id="evening")
    assert done["ok"] and len(calls["evening"]) == 1 and len(calls["morning"]) == 1, calls


async def test_a_run_with_no_trigger_is_what_home_assistants_run_is(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    done = await _fire(client, hass)
    assert done["ok"] and done["trigger"] is None, done
    assert not any(calls.values()), calls  # no rung of its own trigger runs - why FORCE TRUE fires one
    assert (await _runs(client))[0]["trigger"] == "LIBI: run without a trigger"


async def test_the_automations_conditions_are_checked_unless_skipped(hass, libi, hass_ws_client):  # noqa: F811
    guarded = _with(conditions=[{"condition": "state", "entity_id": "input_boolean.allowed", "state": "on"}])
    await _setup(hass, libi, automations=[guarded])
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    done = await _fire(client, hass, trigger=0)
    assert done["ok"] and done["conditions"] == 1 and not calls["morning"], calls
    assert (await _runs(client))[0]["script_execution"] == "failed_conditions"
    done = await _fire(client, hass, trigger=0, skip_condition=True)
    assert done["ok"] and len(calls["morning"]) == 1, calls


async def test_without_fire_or_with_a_changed_automation_nothing_runs(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "trigger": 0, "before": "x"})
    assert res["result"]["ok"] and "fired" not in res["result"], res
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "trigger": 0, "fire": True,
                              "before": "not what the user was shown"})
    assert res["result"]["ok"] is False and res["result"]["stale"], res
    await hass.async_block_till_done()
    assert not any(calls.values()) and await _runs(client) == []


async def test_a_trigger_that_is_not_there_is_refused(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    for msg in ({"trigger": 5}, {"trigger_id": "noon"}, {"trigger": 0, "trigger_id": "evening"}):
        res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "fire": True, **msg})
        reason = res["result"].get("reason", "")
        assert res["result"]["ok"] is False and ("another trigger" in reason or "no trigger" in reason), res
    await hass.async_block_till_done()
    assert not any(calls.values())


async def test_off_or_not_in_home_assistant_is_refused(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    await hass.services.async_call("automation", "turn_off", {"entity_id": ENTITY}, blocking=True)
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "trigger": 0, "fire": True})
    assert res["result"]["ok"] is False and res["result"]["reason"].startswith("It is turned off"), res
    res = await send(client, {"type": "libi/online_fire", "entity_id": "automation.nothing", "fire": True})
    assert res["result"]["ok"] is False and res["result"]["reason"].startswith("This NET is not in Home Assistant"), res
    await hass.async_block_till_done()
    assert not any(calls.values())


async def test_a_lock_an_alarm_or_a_cover_is_never_run_for_real(hass, libi, hass_ws_client):  # noqa: F811
    owner = MockConfigEntry(domain="test")
    owner.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Garage")
    device = dr.async_get(hass).async_get_or_create(config_entry_id=owner.entry_id, identifiers={("test", "door")})
    reg = er.async_get(hass)
    reg.async_get_or_create("cover", "test", "door", suggested_object_id="garage_door", device_id=device.id)
    reg.async_get_or_create("cover", "test", "gate", suggested_object_id="side_gate")
    reg.async_update_entity("cover.side_gate", area_id=area.id)
    risky = {
        "named": [{"action": "lock.unlock", "target": {"entity_id": "lock.front_door"}}],
        "in a condition of its own": [{"if": [{"condition": "state", "entity_id": "alarm_control_panel.home",
                                               "state": "disarmed"}], "then": [{"action": "test.always"}]}],
        "an area": [{"action": "homeassistant.turn_on", "target": {"area_id": area.id}}],
        "a device": [{"action": "homeassistant.turn_on", "target": {"device_id": device.id}}],
        "a script it calls": [{"action": "script.open_gate"}],
        "a script that calls a script": [{"action": "script.outer"}],
        "three scripts deep": [{"action": "script.first"}],
        "script.turn_on of a script": [{"action": "script.turn_on", "target": {"entity_id": "script.open_gate"}}],
        "a scene that holds a cover": [{"action": "scene.turn_on", "target": {"entity_id": "scene.gate_open"}}],
        "another automation it runs": [{"action": "automation.trigger", "target": {"entity_id": "automation.unlock"}}],
    }
    scripts = {"open_gate": {"sequence": [{"action": "cover.open_cover", "target": {"entity_id": "cover.gate"}}]},
               "outer": {"sequence": [{"action": "script.open_gate"}]},
               "first": {"sequence": [{"action": "script.second"}]},
               "second": {"sequence": [{"action": "script.outer"}]}}
    autos = [_with(id=f"r{i}", alias=f"Risky {i}", actions=steps) for i, steps in enumerate(risky.values())]
    autos.append(_with(id="unlock", alias="Unlock", actions=[{"action": "lock.unlock", "target": {"entity_id": "lock.front_door"}}]))
    await _setup(hass, libi, automations=autos, scripts=scripts)
    assert await async_setup_component(hass, "scene", {})
    hass.states.async_set("scene.gate_open", "2026-11-07T08:00:00+00:00", {"entity_id": ["cover.side_gate"]})
    await hass.async_block_till_done()
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    for i, why in enumerate(risky):
        res = await send(client, {"type": "libi/online_fire", "entity_id": f"automation.risky_{i}", "fire": True})
        assert res["success"], res
        assert res["result"]["ok"] is False and res["result"]["reason"].startswith(
            "LIBI does not run this automation for real: it can reach"), (why, res)
    await hass.async_block_till_done()
    assert not any(calls.values())


async def test_what_cannot_be_told_is_not_run(hass, libi, hass_ws_client):  # noqa: F811
    unknown = {
        "a script Home Assistant has not loaded": ([{"action": "script.not_there"}], "has not loaded script.not_there"),
        "a target that is a template": ([{"action": "homeassistant.turn_on",
                                          "target": {"entity_id": "{{ states('input_text.which') }}"}}], "with a template"),
        "an action that is a template": ([{"action": "{{ 'cover.open_cover' }}"}], ""),
    }
    autos = [_with(id=f"u{i}", alias=f"Unknown {i}", actions=steps) for i, (steps, _t) in enumerate(unknown.values())]
    await _setup(hass, libi, automations=autos)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    for i, (why, (_steps, text)) in enumerate(unknown.items()):
        res = await send(client, {"type": "libi/online_fire", "entity_id": f"automation.unknown_{i}", "fire": True})
        assert res["result"]["ok"] is False and text in res["result"]["reason"], (why, res)
    await hass.async_block_till_done()
    assert not any(calls.values())


async def test_a_net_drawn_in_libi_fires_the_trigger_at_its_place(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass)
    net = yaml_to_ast(hass, copy.deepcopy(TRAIN))
    triggers = []

    def walk(els):
        for el in els or []:
            if el.get("isTrigger"):
                triggers.append(el)
            for branch in el.get("branches") or []:
                walk(branch)

    for rung in net["rungs"]:
        walk(rung["elements"])
    evening = next(el for el in triggers if el.get("trigId") == "evening")
    # Drawn in LIBI: no place in the YAML, no id of its own.
    for el in triggers:
        el.pop("src", None)
    assert trigger_place(net, evening["id"])[0] == 1
    done = await _fire(client, hass, net=net, element_id=evening["id"])
    assert done["ok"] and done["trigger"]["id"] == "evening" and len(calls["evening"]) == 1 and not calls["morning"], done
    # The NET without its first rung: the evening trigger would be first, and Home Assistant has the time there.
    alone = copy.deepcopy(net)
    alone["rungs"] = [r for r in alone["rungs"] if any(e.get("id") == evening["id"] for e in r["elements"])]
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "net": alone, "element_id": evening["id"],
                              "fire": True})
    assert res["result"]["ok"] is False and "another trigger there" in res["result"]["reason"], res
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "net": net, "element_id": "nothing",
                              "fire": True})
    assert res["result"]["ok"] is False and res["result"]["reason"] == "This block is not a trigger of the NET.", res
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "net": {"rungs": [{"elements": "not a list"}]},
                              "element_id": evening["id"], "fire": True})
    assert res["success"] and res["result"]["ok"] is False and res["result"]["reason"] == "This block is not a trigger of the NET.", res
    await hass.async_block_till_done()
    assert len(calls["evening"]) == 1


async def test_only_an_administrator_runs_one(hass, libi, hass_ws_client, hass_read_only_access_token):  # noqa: F811
    await _setup(hass, libi)
    calls = _calls(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    res = await send(client, {"type": "libi/online_fire", "entity_id": ENTITY, "trigger": 0, "fire": True})
    assert res["success"] is False and res["error"]["code"] == "unauthorized", res
    await hass.async_block_till_done()
    assert not any(calls.values())


async def test_an_entity_id_that_is_not_an_automation_is_refused(hass, libi, hass_ws_client):  # noqa: F811
    await _setup(hass, libi)
    client = await hass_ws_client(hass)
    for entity_id in ("script.open_gate", "automation.Train", "automation.x; rm"):
        res = await send(client, {"type": "libi/online_fire", "entity_id": entity_id, "fire": True})
        assert res["success"] is False and res["error"]["code"] == "invalid_format", res
