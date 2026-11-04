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
"""YAML -> ladder -> YAML must give back an equivalent automation (CLAUDE.md RULE 5).

verify_round_trip compares both ways and skips only the automation's own id, alias and description,
so an id added to a trigger or a trigger written into the conditions fails here."""
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.libi import libi_to_yaml
from custom_components.libi.libi_to_yaml import verify_round_trip
from custom_components.libi.yaml_to_libi import day_bits_template

L = "light.hall"

CORPUS = [
    {"id": "simple", "alias": "Door light", "description": "", "mode": "single",
     "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
     "conditions": [],
     "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.hall"}}]},
    {"id": "legacy_keys", "alias": "Old syntax",
     "trigger": [{"platform": "state", "entity_id": "binary_sensor.door", "to": "off"}],
     "condition": [],
     "action": [{"service": "light.turn_off", "target": {"entity_id": "light.hall"}}]},
    {"id": "with_condition", "alias": "Only at night", "description": "keep",
     "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
     "conditions": [{"condition": "state", "entity_id": "sun.sun", "state": "below_horizon"}],
     "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.porch"}},
                 {"delay": {"seconds": 30}},
                 {"action": "light.turn_off", "target": {"entity_id": "light.porch"}}]},
    {"id": "template", "alias": "Hot", "mode": "restart", "max_exceeded": "silent",
     "triggers": [{"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 28}],
     "conditions": [{"condition": "template", "value_template": "{{ states('sensor.temp') | float > 28 }}"}],
     "actions": [{"action": "notify.notify", "data": {"message": "It is <hot> & humid"}}]},
    {"id": "multi_trigger_ids", "alias": "x", "triggers": [
        {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "id": "open"},
        {"trigger": "state", "entity_id": "binary_sensor.door", "to": "off", "id": "close"}],
     "conditions": [], "actions": [{"choose": [
         {"conditions": [{"condition": "trigger", "id": "open"}], "sequence": [{"action": "light.turn_on", "target": {"entity_id": L}}]},
         {"conditions": [{"condition": "trigger", "id": "close"}], "sequence": [{"action": "light.turn_off", "target": {"entity_id": L}}]}]}]},
    {"id": "numeric_for", "alias": "x",
     "triggers": [{"trigger": "numeric_state", "entity_id": "sensor.t", "above": 25, "for": {"minutes": 5}}],
     "conditions": [], "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.fan"}}]},
    {"id": "time_weekday", "alias": "x", "triggers": [{"trigger": "time", "at": "07:00:00"}],
     "conditions": [{"condition": "time", "weekday": ["mon", "tue", "wed", "thu", "fri"]}],
     "actions": [{"action": "light.turn_on", "target": {"entity_id": L}, "data": {"brightness_pct": 60}}]},
    {"id": "sun_offset", "alias": "x", "triggers": [{"trigger": "sun", "event": "sunset", "offset": "-00:30:00"}],
     "conditions": [], "actions": [{"action": "light.turn_on", "target": {"entity_id": L}}]},
    # Regression: the template trigger was also written into the conditions.
    {"id": "template_trigger", "alias": "x",
     "triggers": [{"trigger": "template", "value_template": "{{ states('sensor.t') | float > 30 }}"}],
     "conditions": [], "actions": [{"action": "notify.notify", "data": {"message": "hot"}}]},
    {"id": "template_math_trigger", "alias": "x", "triggers": [{"trigger": "template",
        "value_template": "{{ (states('sensor.a') | float + states('sensor.b') | float) > 30 }}"}],
     "conditions": [], "actions": [{"action": "light.turn_on", "target": {"entity_id": L}}]},
    {"id": "template_trigger_with_choose", "alias": "x", "triggers": [{"trigger": "template",
        "value_template": "{{ states('sensor.t') | float > 30 }}"}], "conditions": [],
     "actions": [{"choose": [{"conditions": [{"condition": "state", "entity_id": "input_boolean.away", "state": "on"}],
                              "sequence": [{"action": "notify.notify", "data": {"message": "hot, away"}}]}],
                  "default": [{"action": "switch.turn_on", "target": {"entity_id": "switch.fan"}}]}]},
    # Regression: an id was added to every trigger, so a save rewrote untouched automations.
    {"id": "two_triggers_no_ids", "alias": "x", "triggers": [
        {"trigger": "state", "entity_id": "input_button.a"}, {"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"action": "light.toggle", "target": {"entity_id": L}}]},
    {"id": "user_id_unreferenced", "alias": "x",
     "triggers": [{"trigger": "state", "entity_id": "input_button.a", "id": "my_button"}],
     "conditions": [], "actions": [{"action": "light.toggle", "target": {"entity_id": L}}]},
    {"id": "if_then_else", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"if": [{"condition": "state", "entity_id": L, "state": "on"}],
                                    "then": [{"action": "light.turn_off", "target": {"entity_id": L}}],
                                    "else": [{"action": "light.turn_on", "target": {"entity_id": L}}]}]},
    {"id": "repeat_count", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"repeat": {"count": 3, "sequence": [
         {"action": "light.toggle", "target": {"entity_id": L}}, {"delay": {"seconds": 1}}]}}]},
    {"id": "wait_for_trigger", "alias": "x", "mode": "restart",
     "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}], "conditions": [],
     "actions": [{"action": "light.turn_on", "target": {"entity_id": L}},
                 {"wait_for_trigger": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "off",
                                        "for": {"minutes": 2}}]},
                 {"action": "light.turn_off", "target": {"entity_id": L}}]},
    {"id": "set_value", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"action": "input_number.set_value",
                                    "target": {"entity_id": "input_number.level"}, "data": {"value": 5}}]},
    {"id": "or_condition", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
     "conditions": [{"condition": "or", "conditions": [{"condition": "state", "entity_id": "input_boolean.away", "state": "on"},
                                                        {"condition": "sun", "after": "sunset"}]}],
     "actions": [{"action": "notify.notify", "data": {"message": "door"}}]},
    {"id": "variables_and_max", "alias": "x", "mode": "queued", "max": 5, "variables": {"level": 40},
     "triggers": [{"trigger": "state", "entity_id": "input_button.b"}], "conditions": [],
     "actions": [{"action": "light.turn_on", "target": {"entity_id": L}, "data": {"brightness_pct": "{{ level }}"}}]},
    {"id": "continue_on_error", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"action": "light.turn_on", "target": {"entity_id": L}, "continue_on_error": True},
                                   {"action": "switch.turn_on", "target": {"entity_id": "switch.fan"}}]},
]


@pytest.mark.parametrize("automation", CORPUS, ids=[a["id"] for a in CORPUS])
async def test_round_trip_is_lossless(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("issues")


@pytest.mark.parametrize("change, expect", [
    (lambda out: out["triggers"][0].__setitem__("id", "t1"), "added"),
    (lambda out: out["actions"][0].pop("target"), "missing"),
])
async def test_the_gate_sees_added_and_lost_keys(hass: HomeAssistant, change, expect) -> None:
    """The check itself: an export that adds or drops a key must not pass."""
    real = libi_to_yaml.ast_to_yaml

    def lossy(h, net):
        out = real(h, net)
        change(out)
        return out

    with patch.object(libi_to_yaml, "ast_to_yaml", lossy):
        report = verify_round_trip(hass, CORPUS[0])
    assert report["ok"] is False
    assert any(i.startswith(expect) for i in report["issues"]), report["issues"]


# [ADDED 2026-10-27] Automation-level conditions next to an if or choose. The compiler used to write
# them into every rung as an if, so a save reshaped such an automation.
_V = "switch.garden_valve"
_ON = {"action": "switch.turn_on", "target": {"entity_id": _V}}
_OFF = {"action": "switch.turn_off", "target": {"entity_id": _V}}
_WK = [{"condition": "time", "weekday": ["sun", "tue", "thu", "sat"]}]
_IF_SHORT = {"if": [{"condition": "template", "value_template": "{{ not wait.completed }}"}],
             "then": [{"action": "notify.notify", "data": {"message": "short"}}]}
HOISTED = [
    {"id": "conditions_and_if", "alias": "x", "triggers": [{"trigger": "time", "at": "05:00:00"}],
     "conditions": _WK, "actions": [_ON, _IF_SHORT]},
    {"id": "conditions_segment_if_segment", "alias": "x", "triggers": [{"trigger": "time", "at": "05:00:00"}],
     "conditions": _WK, "actions": [_ON, _IF_SHORT, _OFF]},
    {"id": "two_conditions_and_choose", "alias": "x", "triggers": [{"trigger": "time", "at": "05:00:00"}],
     "conditions": _WK + [{"condition": "state", "entity_id": "input_boolean.away", "state": "off"}],
     "actions": [{"choose": [{"conditions": [{"condition": "state", "entity_id": _V, "state": "on"}],
                              "sequence": [_OFF]}], "default": [_ON]}]},
    {"id": "garden_four_mornings", "alias": "Garden watering", "mode": "single",
     "triggers": [{"trigger": "time", "at": "05:00:00"}], "conditions": _WK,
     "actions": [
         {"action": "weather.get_forecasts", "target": {"entity_id": "weather.home"},
          "data": {"type": "daily"}, "response_variable": "forecast"},
         {"condition": "template",
          "value_template": "{{ forecast['weather.home'].forecast[0].condition not in ['rainy', 'pouring'] }}"},
         {"variables": {"start": "{{ states('sensor.water_meter') | float(0) }}"}},
         _ON,
         {"wait_template": "{{ states('sensor.water_meter') | float(0) - start >= 200 }}",
          "timeout": "01:00:00", "continue_on_timeout": True},
         _OFF, _IF_SHORT]},
]


@pytest.mark.parametrize("automation", HOISTED, ids=[a["id"] for a in HOISTED])
async def test_conditions_next_to_if_keep_their_shape(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("issues")


async def test_a_condition_edited_in_one_rung_stays_in_that_rung(hass: HomeAssistant) -> None:
    """When the user changes the copy in one rung, the copies differ: nothing is hoisted, and each
    rung keeps its own condition, so the automation still does what the drawing says."""
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, HOISTED[0])
    edited = False
    for rung in net["rungs"]:
        for el in rung["elements"]:
            if el.get("baseCond") and not edited and rung.get("group"):
                el["weekday"] = ["mon"]
                if isinstance(el.get("raw"), dict):
                    el["raw"] = {**el["raw"], "weekday": ["mon"]}
                edited = True
    assert edited
    out = ast_to_yaml(hass, net)
    assert not out.get("conditions"), out.get("conditions")
    text = str(out["actions"])
    assert "'mon'" in text and "'sun'" in text


# [ADDED 2026-10-28] A variables step with two values is drawn as two MOVE blocks, and each wrote the whole
# step back: the AI's garden watering draft could not be added because its step came out twice.
_TWO = {"variables": {"start_water": "{{ states('sensor.water_meter') | float(0) }}",
                      "litres": "{{ states('input_number.garden_litres') | float(0) }}"}}
VARIABLES = [
    {"id": "variables_top", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [_TWO, _ON, _OFF]},
    {"id": "variables_in_if", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "schedule.garden", "to": "on"}],
     "conditions": [], "actions": [{"if": [{"condition": "state", "entity_id": "input_boolean.away", "state": "off"}],
                                    "then": [_TWO, _ON,
                                             {"wait_template": "{{ states('sensor.water_meter') | float(0) - start_water >= litres }}",
                                              "timeout": "01:00:00", "continue_on_timeout": True}, _OFF]}]},
    {"id": "variables_in_repeat", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"repeat": {"count": 2, "sequence": [_TWO, {"variables": {"one": 1}}, _ON]}}]},
]


@pytest.mark.parametrize("automation", VARIABLES, ids=[a["id"] for a in VARIABLES])
async def test_a_variables_step_with_two_values_stays_one_step(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("issues")


async def test_an_edited_variable_is_written_and_a_deleted_one_is_gone(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, VARIABLES[0])
    elements = net["rungs"][0]["elements"]
    moves = [el for el in elements if el.get("service") == "variables"]
    assert [el["target"] for el in moves] == ["start_water", "litres"]
    moves[1]["source"] = "25"
    out = ast_to_yaml(hass, net)
    assert out["actions"][0] == {"variables": {"start_water": _TWO["variables"]["start_water"], "litres": "25"}}
    elements.remove(moves[0])
    out = ast_to_yaml(hass, net)
    assert out["actions"][0] == {"variables": {"litres": "25"}}
    assert len(out["actions"]) == 3


# [ADDED 2026-10-28] A repeat was written back from what its block shows: the while template, shown shortened,
# was saved shortened, and continue_on_error was dropped. This is the AI's garden watering draft.
_LONG_WHILE = ("{{ (states('sensor.valve_garden_summation_delivered') | float(0) - start_water)"
               " < target_amount }}")
REPEATS = [
    {"id": "garden_watering_draft", "alias": "x", "mode": "single",
     "triggers": [{"trigger": "state", "entity_id": "schedule.garden", "to": "on"}],
     "conditions": [{"condition": "not", "conditions": [{"condition": "state", "entity_id": "weather.home",
                                                         "attribute": "condition", "state": s}]}
                    for s in ("rainy", "pouring", "lightning-rainy")],
     "actions": [{"variables": {"start_water": "{{ states('sensor.water_meter') | float(0) }}",
                                "target_amount": "{{ states('input_number.garden_litres') | float(0) }}"}},
                 _ON,
                 {"repeat": {"while": [{"condition": "template", "value_template": _LONG_WHILE}],
                             "sequence": [{"delay": {"seconds": 5}}]}, "continue_on_error": True},
                 _OFF]},
    {"id": "repeat_until_enabled", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.b"}],
     "conditions": [], "actions": [{"repeat": {"until": [{"condition": "template", "value_template": _LONG_WHILE},
                                                         {"condition": "state", "entity_id": _V, "state": "off"}],
                                               "sequence": [_ON, {"delay": {"seconds": 1}}]},
                                    "enabled": True, "alias": "fill"}]},
]


@pytest.mark.parametrize("automation", REPEATS, ids=[a["id"] for a in REPEATS])
async def test_a_repeat_keeps_its_own_loop_and_keys(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("issues")


async def test_an_edited_loop_is_written_and_the_other_keys_stay(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, REPEATS[0])
    rep = next(el for rung in net["rungs"] for el in rung["elements"] if el["type"] == "repeat")
    assert rep["value"].endswith("…")
    rep["value"] = "{{ states('sensor.water_meter') | float(0) < 5 }}"
    out = next(a for a in ast_to_yaml(hass, net)["actions"] if "repeat" in a)
    assert out["continue_on_error"] is True
    assert out["repeat"]["while"] == [{"condition": "template", "value_template": rep["value"]}]
    rep["loopType"], rep["value"] = "count", "3"
    out = next(a for a in ast_to_yaml(hass, net)["actions"] if "repeat" in a)
    assert out["repeat"]["count"] == 3 and "while" not in out["repeat"]


# [ADDED 2026-10-29] A duration given by a template stopped the import (int() of the template), so the AI's
# watering draft with a time limit set from the screen could not be drawn. A condition's for written as a
# template was dropped, and {minutes: 5} came back with hours and seconds added.
_T_MIN = "{{ states('input_number.max_minutes') | int(0) }}"
_T_BASE = {"alias": "x", "triggers": [{"trigger": "state", "entity_id": "schedule.garden", "to": "on"}], "conditions": []}
DURATIONS = [
    {**_T_BASE, "id": "delay_template", "actions": [_ON, {"delay": {"minutes": _T_MIN}}, _OFF]},
    {**_T_BASE, "id": "condition_for_template",
     "conditions": [{"condition": "state", "entity_id": _V, "state": "on", "for": {"minutes": _T_MIN}}], "actions": [_OFF]},
    {**_T_BASE, "id": "condition_for_template_text",
     "conditions": [{"condition": "state", "entity_id": _V, "state": "on", "for": _T_MIN}], "actions": [_OFF]},
    {**_T_BASE, "id": "if_condition_for_template",
     "actions": [{"if": [{"condition": "state", "entity_id": _V, "state": "on", "for": {"minutes": _T_MIN}}], "then": [_OFF]}]},
    {**_T_BASE, "id": "trigger_for_template",
     "triggers": [{"trigger": "state", "entity_id": _V, "to": "on", "for": {"minutes": _T_MIN}}], "actions": [_OFF]},
    {**_T_BASE, "id": "wait_timeout_template",
     "actions": [_ON, {"wait_template": "{{ is_state('switch.garden_valve', 'off') }}", "timeout": {"minutes": _T_MIN},
                       "continue_on_timeout": True}, _OFF]},
    {**_T_BASE, "id": "condition_for_keeps_its_shape",
     "conditions": [{"condition": "state", "entity_id": _V, "state": "on", "for": {"minutes": 5}}],
     "actions": [{"delay": {"minutes": 2}}, _OFF]},
]


@pytest.mark.parametrize("automation", DURATIONS, ids=[a["id"] for a in DURATIONS])
async def test_a_duration_given_by_a_template_is_drawn_and_kept(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("error") or report.get("issues")


async def test_a_template_delay_shows_its_template(hass: HomeAssistant) -> None:
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, DURATIONS[0])
    timer = next(el for rung in net["rungs"] for el in rung["elements"] if el["type"] == "timer_ton")
    assert timer["label"].startswith("minutes {{ states('input_number.max_minutes')")


def _for_timer(net):
    return next(el for rung in net["rungs"] for el in rung["elements"] if el.get("isFor"))


async def test_an_edited_or_removed_for_timer_and_an_older_project(hass: HomeAssistant) -> None:
    """Untouched, the for goes back as written; an edited timer writes its new time; a removed timer
    takes the for with it; a timer saved before forValue existed still gives its time."""
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, DURATIONS[1])
    _for_timer(net)["label"] = "00:10:00"
    assert ast_to_yaml(hass, net)["conditions"][0]["for"] == {"hours": 0, "minutes": 10, "seconds": 0}
    net = yaml_to_ast(hass, DURATIONS[1])
    for rung in net["rungs"]:
        rung["elements"] = [el for el in rung["elements"] if not el.get("isFor")]
    assert "for" not in ast_to_yaml(hass, net)["conditions"][0]
    net = yaml_to_ast(hass, DURATIONS[-1])
    _for_timer(net).pop("forValue")
    assert ast_to_yaml(hass, net)["conditions"][0]["for"] == {"hours": 0, "minutes": 5, "seconds": 0}


# [ADDED 2026-10-29] The user's ladder has no WAIT block. A wait is drawn with the blocks of what it waits for - an
# edge contact for an on/off, a CMP for a number - in a PARALLEL when there are several, with a TON for its time
# limit, and it goes back exactly as it was. The first one is the user's garden watering (NET 3).
_METER = "sensor.valve_garden_summation_delivered"
_WAIT_NET3 = {"wait_for_trigger": [{"trigger": "numeric_state", "entity_id": _METER, "above": "input_number.garden_litres"},
                                   {"trigger": "state", "entity_id": _V, "to": "off"}],
              "timeout": {"minutes": _T_MIN}, "continue_on_timeout": True}
WAITS = [
    {**_T_BASE, "id": "wait_meter_or_valve_with_limit", "mode": "single",
     "actions": [_ON, _WAIT_NET3, _OFF,
                 {"if": [{"condition": "template", "value_template": "{{ wait.trigger is none }}"}],
                  "then": [{"action": "notify.notify", "data": {"message": "time ran out"}}]}]},
    {**_T_BASE, "id": "wait_one_state_to_on", "actions": [_ON, {"wait_for_trigger": [
        {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}]}, _OFF]},
    {**_T_BASE, "id": "wait_one_trigger_not_a_list", "actions": [_ON, {
        "wait_for_trigger": {"trigger": "state", "entity_id": _V, "to": "off"},
        "timeout": "00:30:00", "continue_on_timeout": False}, _OFF]},
    {**_T_BASE, "id": "wait_any_change_event_or_template", "actions": [_ON, {"wait_for_trigger": [
        {"trigger": "state", "entity_id": "input_select.mode"},
        {"trigger": "event", "event_type": "garden_stop"},
        {"trigger": "template", "value_template": "{{ states('sensor.t') | float(0) > 30 }}"}], "alias": "stop"}, _OFF]},
    {**_T_BASE, "id": "wait_one_template", "actions": [_ON, {"wait_for_trigger": [
        {"trigger": "template", "value_template": "{{ is_state('switch.garden_valve', 'off') }}"}]}, _OFF]},
    {**_T_BASE, "id": "wait_inside_a_branch", "actions": [{"if": [{"condition": "state", "entity_id": _V, "state": "on"}],
        "then": [{"wait_for_trigger": [{"trigger": "state", "entity_id": _V, "to": "off", "for": {"minutes": 2}}],
                  "timeout": 120}, _OFF]}]},
]
RECENT = [{**_T_BASE, "id": "was_on_lately", "conditions": [{"condition": "template", "value_template":
    "{{ is_state('binary_sensor.motion','on') and (now() - states.binary_sensor.motion.last_changed).total_seconds() < 300 }}"}],
    "actions": [_OFF]}]


@pytest.mark.parametrize("automation", WAITS + RECENT, ids=[a["id"] for a in WAITS + RECENT])
async def test_a_wait_drawn_with_the_users_blocks_goes_back_as_it_was(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("error") or report.get("issues")


# [ADDED 2026-10-29] A schedule is the CMP DATETIME block: IN1 the date and time, IN2 the schedule, = while it is on
# and the other one while it is off. The user: "it should have chosen CMP DATETIME, so I understand what the trigger
# is; if IN2 is ON, a | | will do". It goes back as it was, and an edit writes what the block now says.
_S = "schedule.garden"
CLOCKS = [
    {**_T_BASE, "id": "schedule_off_from_on", "triggers": [{"trigger": "state", "entity_id": _S, "to": "off", "from": "on"}],
     "conditions": [{"condition": "state", "entity_id": _S, "state": "off"}], "actions": [_OFF]},
    {**_T_BASE, "id": "schedule_not_on", "conditions": [{"condition": "not", "conditions": [
        {"condition": "state", "entity_id": _S, "state": "on"}]}], "actions": [_OFF]},
    {**_T_BASE, "id": "schedule_for_id_and_two_schedules", "triggers": [
        {"trigger": "state", "entity_id": _S, "to": "on", "for": {"minutes": 1}, "id": "start"},
        {"platform": "state", "entity_id": [_S, "schedule.lawn"], "to": "on"}], "actions": [_ON]},
    {**_T_BASE, "id": "wait_for_a_schedule", "actions": [_ON, {"wait_for_trigger": [
        {"trigger": "state", "entity_id": _S, "to": "off"}], "timeout": "02:00:00"}, _OFF]},
    {**_T_BASE, "id": "to_a_list_of_one", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": ["on"]}],
     "actions": [_ON]},
]


@pytest.mark.parametrize("automation", CLOCKS, ids=[a["id"] for a in CLOCKS])
async def test_a_schedule_drawn_as_cmp_datetime_goes_back_as_it_was(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("error") or report.get("issues")


def _clocks(net):
    return [el for rung in net["rungs"] for el in _walk_all(rung["elements"]) if el.get("sourceA") == "datetime"]


def _walk_all(elements):
    for el in elements:
        yield el
        for branch in el.get("branches") or []:
            yield from _walk_all(branch)


async def test_a_schedule_is_the_cmp_datetime_block(hass: HomeAssistant) -> None:
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, CLOCKS[0])
    trig, cond = _clocks(net)
    assert (trig["type"], trig["sourceB"], trig["isTrigger"]) == ("cmp_ne", _S, True)
    assert (cond["type"], cond["sourceB"], cond["isTrigger"]) == ("cmp_ne", _S, False)
    assert net["rungs"][0]["comment"].startswith("When the schedule garden ends, if the time is outside the schedule garden")
    (start,) = _clocks(yaml_to_ast(hass, _T_BASE | {"id": "x", "actions": [_OFF]}))
    assert (start["type"], start["sourceB"]) == ("cmp_eq", _S)
    (neg,) = [el for el in _clocks(yaml_to_ast(hass, CLOCKS[1])) if not el.get("isTrigger")]
    assert neg["type"] == "cmp_ne"  # not on is the same block as off
    wait = _wait_of(yaml_to_ast(hass, CLOCKS[3]))
    (ends,), (limit,) = wait["branches"]
    assert (ends["type"], ends["sourceA"], ends["sourceB"], ends["isTrigger"]) == ("cmp_ne", "datetime", _S, False)
    assert limit["type"] == "timer_ton"
    door = yaml_to_ast(hass, CLOCKS[4])["rungs"][0]["elements"][0]
    assert (door["type"], door["label"], door["isTrigger"]) == ("contact_no", "binary_sensor.door", True)


async def test_an_edited_cmp_datetime_writes_what_it_now_says(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    auto = {**_T_BASE, "id": "e", "triggers": [{"trigger": "state", "entity_id": _S, "to": "on", "from": "off",
                                                "for": {"minutes": 1}}],
            "conditions": [{"condition": "state", "entity_id": _S, "state": "on", "for": "00:01:00"}], "actions": [_OFF]}
    # Another schedule, and = turned into the other one: the trigger waits for that schedule to end - the from that
    # would keep it from ever firing goes, the for stays - and the condition asks for it to be off.
    net = yaml_to_ast(hass, auto)
    for el in _clocks(net):
        el["sourceB"], el["type"] = "schedule.lawn", "cmp_ne"
    out = ast_to_yaml(hass, net)
    assert out["triggers"] == [{"trigger": "state", "entity_id": "schedule.lawn", "to": "off", "for": {"minutes": 1}}]
    assert out["conditions"] == [{"condition": "state", "entity_id": "schedule.lawn", "state": "off", "for": "00:01:00"}]
    # A date and time helper on IN2: a time trigger at it.
    net = yaml_to_ast(hass, auto)
    _clocks(net)[0]["sourceB"] = "input_datetime.start"
    assert ast_to_yaml(hass, net)["triggers"] == [{"trigger": "time", "at": "input_datetime.start"}]
    # A block drawn new, with no YAML behind it, as a trigger and as a condition.
    net = yaml_to_ast(hass, CLOCKS[0])
    for el in _clocks(net):
        el.pop("raw", None)
        el.pop("sig", None)
        el["type"] = "cmp_eq"
    out = ast_to_yaml(hass, net)
    assert out["triggers"] == [{"trigger": "state", "entity_id": _S, "to": "on"}]
    assert out["conditions"] == [{"condition": "state", "entity_id": _S, "state": "on"}]
    # The not of a schedule that is on, given another schedule: the state the block says.
    net = yaml_to_ast(hass, CLOCKS[1])
    (neg,) = [el for el in _clocks(net) if not el.get("isTrigger")]
    neg["sourceB"] = "schedule.lawn"
    assert ast_to_yaml(hass, net)["conditions"] == [{"condition": "state", "entity_id": "schedule.lawn", "state": "off"}]
    # Only the operator changed on a trigger of two schedules: both stay.
    net = yaml_to_ast(hass, CLOCKS[2])
    two = next(el for el in _clocks(net) if el.get("raw", {}).get("platform"))
    two["type"] = "cmp_ne"
    trig = next(t for t in ast_to_yaml(hass, net)["triggers"] if t.get("platform"))
    assert trig == {"platform": "state", "entity_id": [_S, "schedule.lawn"], "to": "off"}
    # A wait for the schedule to end, given another schedule: the wait writes it.
    net = yaml_to_ast(hass, CLOCKS[3])
    _wait_of(net)["branches"][0][0]["sourceB"] = "schedule.lawn"
    out = next(a for a in ast_to_yaml(hass, net)["actions"] if "wait_for_trigger" in a)
    assert out["wait_for_trigger"] == [{"trigger": "state", "entity_id": "schedule.lawn", "to": "off"}]
    assert out["timeout"] == "02:00:00"


# [ADDED 2026-10-29] The user: "why did it make 4 triggers of the same CMP? If it is the same CMP, drop to a parallel
# line". The automation's triggers are drawn once; every rung below hangs from them, and the YAML stays the same.
# The first one is the user's garden watering (NET 4), its texts in English.
_V2 = "switch.valve_garden_switch"
_NET4 = {
    "id": "libi_ai_1793303366077", "alias": "Advanced garden watering", "mode": "single",
    "description": "Watering by the schedule, the litres, the forecast, a manual close and a time limit.",
    "triggers": [{"trigger": "state", "entity_id": "schedule.lvkh_zmnym_lhshqyyt_gynh", "to": "on"}],
    "conditions": [],
    "actions": [
        {"action": "weather.get_forecasts", "target": {"entity_id": "weather.guy_smart_home"},
         "data": {"type": "daily"}, "response_variable": "forecast"},
        {"if": [{"condition": "template", "value_template":
                 "{{ states('weather.guy_smart_home') not in ['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail']"
                 " and forecast['weather.guy_smart_home'].forecast[0].condition not in ['rainy', 'pouring',"
                 " 'lightning-rainy', 'snowy-rainy', 'hail'] }}"}],
         "then": [{"action": "switch.turn_on", "target": {"entity_id": _V2}},
                  {"variables": {"start_water": "{{ states('sensor.valve_garden_summation_delivered') | float(0) }}"}},
                  {"wait_for_trigger": [
                      {"trigger": "numeric_state", "entity_id": "sensor.valve_garden_summation_delivered",
                       "above": "input_number.kmvt_mym_lhshqyh_blytrym"},
                      {"trigger": "state", "entity_id": _V2, "to": "off"}],
                   "timeout": {"minutes": "{{ states('input_number.zmn_hshqyh_mqsymly_bdqvt') | int(45) }}"},
                   "continue_on_timeout": True}]},
        {"if": [{"condition": "template",
                 "value_template": "{{ not wait.trigger is none and wait.trigger.platform == 'numeric_state' }}"}],
         "then": [{"action": "switch.turn_off", "target": {"entity_id": _V2}}]},
        {"if": [{"condition": "template", "value_template": "{{ wait.trigger is none }}"}],
         "then": [{"action": "switch.turn_off", "target": {"entity_id": _V2}},
                  {"action": "notify.mobile_app_sm_s918b", "data": {"message": "Watering stopped: the time limit ran out"}},
                  {"action": "notify.mobile_app_sm_s938b", "data": {"message": "Watering stopped: the time limit ran out"}}]},
    ],
}
SHARED = [
    _NET4,
    {"id": "two_triggers_and_an_if", "alias": "x",
     "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"},
                  {"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
     "conditions": [{"condition": "state", "entity_id": "input_boolean.away", "state": "off"}],
     "actions": [{"action": "light.turn_on", "target": {"entity_id": L}},
                 {"if": [{"condition": "state", "entity_id": "sun.sun", "state": "below_horizon"}],
                  "then": [{"action": "light.turn_on", "target": {"entity_id": "light.porch"}}],
                  "else": [{"action": "light.turn_off", "target": {"entity_id": "light.porch"}}]},
                 {"delay": {"seconds": 30}}]},
    {"id": "option_with_its_own_trigger", "alias": "x", "triggers": [
        {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "id": "open"},
        {"trigger": "state", "entity_id": "binary_sensor.door", "to": "off", "id": "close"}],
     "conditions": [], "actions": [
        {"action": "light.turn_on", "target": {"entity_id": L}},
        {"choose": [{"conditions": [{"condition": "trigger", "id": "close"}],
                     "sequence": [{"action": "light.turn_off", "target": {"entity_id": L}}]}],
         "default": [{"action": "notify.notify", "data": {"message": "door"}}]},
        {"action": "switch.turn_on", "target": {"entity_id": "switch.fan"}}]},
]


@pytest.mark.parametrize("automation", SHARED, ids=[a["id"] for a in SHARED])
async def test_triggers_drawn_once_go_back_as_they_were(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("error") or report.get("issues")


def _trigger_count(rung):
    return sum(1 for el in _walk_all(rung["elements"]) if el.get("isTrigger"))


async def test_the_trigger_is_drawn_once_and_the_rungs_below_hang_from_it(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import hangs
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, _NET4)
    first, *below = net["rungs"]
    assert len(below) == 3 and _trigger_count(first) == 1 and first["elements"][0]["autoGate"]
    assert not first.get("sharesHead") and all(r["sharesHead"] and hangs(r) and _trigger_count(r) == 0 for r in below)
    assert first["comment"].startswith("When the schedule lvkh zmnym lhshqyyt gynh starts, then call")
    assert below[0]["comment"].startswith("If ")
    # Two triggers: the head rung is split into one rung per trigger, linked; the rungs after them hang, the else of
    # the if too. A rung of an option that names its own trigger starts with it, and the one after it starts with
    # the automation's triggers again, since it is not right below them.
    net = yaml_to_ast(hass, SHARED[1])
    assert [bool(r.get("sharesHead")) for r in net["rungs"]] == [False, False, True, True, True]
    assert len(net["links"]) == 1
    net = yaml_to_ast(hass, SHARED[2])
    assert [bool(r.get("sharesHead")) for r in net["rungs"]] == [False, False, False, False, False, True]
    assert net["rungs"][2]["elements"][0]["trigId"] == "close" and net["rungs"][3]["elements"][0]["autoGate"]


async def test_a_hanging_rung_compiles_with_the_trigger_it_hangs_from(hass: HomeAssistant) -> None:
    """WYSIWYG for a net drawn by hand: a rung under one trigger of two runs for that trigger only, and a rung with no
    trigger above it is compiled without one (the panel marks it red, so it is never saved that way)."""
    from custom_components.libi.libi_to_yaml import ast_to_yaml

    def contact(eid, ent):
        return {"id": eid, "type": "contact_no", "label": ent, "isTrigger": True}

    def coil(eid, ent):
        return {"id": eid, "type": "coil_s", "label": ent, "isTrigger": False}

    net = {"id": "n", "name": "x", "level": "automation", "rungs": [
        {"id": "r1", "elements": [contact("t1", "binary_sensor.a"), coil("c1", "light.one")]},
        {"id": "r2", "sharesHead": True, "elements": [coil("c2", "light.two")]},
        {"id": "r3", "elements": [contact("t2", "binary_sensor.b"), coil("c3", "light.three")]}]}
    out = ast_to_yaml(hass, net)
    assert out["triggers"] == [{"trigger": "state", "entity_id": "binary_sensor.a", "to": "on", "id": "t1"},
                               {"trigger": "state", "entity_id": "binary_sensor.b", "to": "on", "id": "t2"}]
    gates = [a["if"] for a in out["actions"]]
    assert gates == [[{"condition": "trigger", "id": "t1"}], [{"condition": "trigger", "id": "t1"}],
                     [{"condition": "trigger", "id": "t2"}]]
    assert net["rungs"][1]["elements"] == [coil("c2", "light.two")]  # the stored net is not changed
    alone = {"id": "n", "name": "x", "level": "automation", "rungs": [
        {"id": "r1", "sharesHead": True, "elements": [coil("c1", "light.one")]}]}
    assert ast_to_yaml(hass, alone)["triggers"] == []


# [ADDED 2026-10-29] The ladder way, as the user's own automations are written ("see how a YAML should look"): one
# trigger with an id for every event and a choose with an option per trigger id. A trigger that has to hold for a
# while is drawn with the TON of its for right after it, and written back from that TON.
_MINUTES = {"minutes": "{{ states('input_number.zmn_hshqyh_mqsymly_bdqvt') | int(45) }}"}
_GARDEN_LADDER = {
    "id": "garden_ladder", "alias": "Garden watering, the ladder way", "mode": "queued", "conditions": [],
    "triggers": [
        {"trigger": "state", "entity_id": "schedule.lvkh_zmnym_lhshqyyt_gynh", "to": "on", "id": "start"},
        {"trigger": "numeric_state", "entity_id": "sensor.valve_garden_summation_delivered",
         "above": "input_number.kmvt_mym_lhshqyh_blytrym", "id": "amount_reached"},
        {"trigger": "state", "entity_id": _V2, "to": "on", "for": _MINUTES, "id": "time_limit"},
        {"trigger": "homeassistant", "event": "start", "id": "restarted"}],
    "actions": [{"choose": [
        {"conditions": [{"condition": "trigger", "id": "start"},
                        {"condition": "template", "value_template": "{{ states('weather.guy_smart_home') not in ['rainy'] }}"}],
         "sequence": [{"action": "weather.get_forecasts", "target": {"entity_id": "weather.guy_smart_home"},
                       "data": {"type": "daily"}, "response_variable": "forecast"},
                      {"condition": "template", "value_template":
                          "{{ forecast['weather.guy_smart_home'].forecast[0].condition not in ['rainy'] }}"},
                      {"action": "switch.turn_on", "target": {"entity_id": _V2}}]},
        {"conditions": [{"condition": "trigger", "id": "amount_reached"},
                        {"condition": "state", "entity_id": _V2, "state": "on"}],
         "sequence": [{"action": "switch.turn_off", "target": {"entity_id": _V2}}]},
        {"conditions": [{"condition": "trigger", "id": "time_limit"}],
         "sequence": [{"action": "switch.turn_off", "target": {"entity_id": _V2}},
                      {"action": "notify.mobile_app_sm_s918b", "data": {"message": "The time limit ended the watering"}}]},
        {"conditions": [{"condition": "trigger", "id": "restarted"},
                        {"condition": "state", "entity_id": _V2, "state": "on"}],
         "sequence": [{"action": "switch.turn_off", "target": {"entity_id": _V2}}]}]}],
}
LADDER_WAY = [
    _GARDEN_LADDER,
    {**_T_BASE, "id": "trigger_for_then_steps", "triggers": [{"trigger": "state", "entity_id": _V, "to": "on",
                                                              "for": {"minutes": 30}}],
     "actions": [_OFF, {"if": [{"condition": "state", "entity_id": "input_boolean.away", "state": "on"}],
                        "then": [{"action": "notify.notify", "data": {"message": "valve closed"}}]}]},
    {**_T_BASE, "id": "two_triggers_one_with_for", "triggers": [
        {"trigger": "state", "entity_id": _V, "to": "on", "for": "00:10:00"},
        {"trigger": "state", "entity_id": "binary_sensor.rain", "to": "on"}], "actions": [_OFF]},
    {**_T_BASE, "id": "or_condition_with_a_for", "conditions": [{"condition": "or", "conditions": [
        {"condition": "state", "entity_id": "binary_sensor.door", "state": "on", "for": {"minutes": 5}},
        {"condition": "state", "entity_id": "input_boolean.away", "state": "on"}]}], "actions": [_ON]},
    # [ADDED 2026-10-31] Started as an alarm clock: at the time the user sets, on the days the user ticks.
    {**_T_BASE, "id": "alarm_clock", "triggers": [
        {"trigger": "time", "at": "input_datetime.garden_start", "id": "start"},
        {"trigger": "state", "entity_id": _V, "to": "on", "for": {"minutes": 45}, "id": "time_limit"}],
     "actions": [{"choose": [
         {"conditions": [{"condition": "trigger", "id": "start"}, {"condition": "or", "conditions": [
             {"condition": "and", "conditions": [{"condition": "time", "weekday": d},
                                                 {"condition": "state", "entity_id": f"input_boolean.garden_{d}",
                                                  "state": "on"}]}
             for d in ("sun", "mon", "tue", "wed", "thu", "fri", "sat")]}],
          "sequence": [_ON]},
         {"conditions": [{"condition": "trigger", "id": "time_limit"}], "sequence": [_OFF]}]}]},
    # [ADDED 2026-10-31, v3.76.0] The days in ONE 8-bit helper (bit 1 Sunday ... bit 7 Saturday), read by one CMP DAY.
    {**_T_BASE, "id": "alarm_clock_day_bits", "triggers": [
        {"trigger": "time", "at": "input_datetime.garden_start", "id": "start"},
        {"trigger": "state", "entity_id": _V, "to": "on", "for": {"minutes": 45}, "id": "time_limit"}],
     "actions": [{"choose": [
         {"conditions": [{"condition": "trigger", "id": "start"},
                         {"condition": "template", "value_template": day_bits_template("input_number.garden_days")}],
          "sequence": [_ON]},
         {"conditions": [{"condition": "trigger", "id": "time_limit"}], "sequence": [_OFF]}]}]},
    # [ADDED 2026-11-01, v3.80.0] The user's answers to LIBI's own questions, as the build is told to write them: an on/off
    # switch (an enable: the start checks it, turning it off stops the run), the valve online at the start and its going
    # offline told, a battery below 20 % told. Two valves, so the start checks that none of them is offline.
    {**_T_BASE, "id": "libi_answers", "triggers": [
        {"trigger": "time", "at": "input_datetime.garden_start", "id": "start"},
        {"trigger": "state", "entity_id": "input_boolean.garden_enabled", "to": "off", "id": "switched_off"},
        {"trigger": "state", "entity_id": [_V, _V2], "to": "unavailable", "for": {"minutes": 10},
         "id": "garden_valve_offline"},
        {"trigger": "numeric_state", "entity_id": "sensor.valve_garden_battery", "below": 20, "id": "battery_low"}],
     "actions": [{"choose": [
         {"conditions": [{"condition": "trigger", "id": "start"},
                         {"condition": "state", "entity_id": "input_boolean.garden_enabled", "state": "on"},
                         {"condition": "not", "conditions": [{"condition": "state", "entity_id": [_V, _V2],
                                                              "state": "unavailable", "match": "any"}]}],
          "sequence": [{"action": "switch.turn_on", "target": {"entity_id": [_V, _V2]}}]},
         {"conditions": [{"condition": "trigger", "id": "switched_off"}],
          "sequence": [{"action": "switch.turn_off", "target": {"entity_id": [_V, _V2]}}]},
         {"conditions": [{"condition": "trigger", "id": "garden_valve_offline"}],
          "sequence": [{"action": "notify.notify", "data": {"message": "{{ trigger.to_state.name }} is offline"}}]},
         {"conditions": [{"condition": "trigger", "id": "battery_low"}],
          "sequence": [{"action": "persistent_notification.create",
                        "data": {"message": "{{ trigger.to_state.name }}: {{ trigger.to_state.state }}%"}}]}]}]},
    # [ADDED 2026-11-02, v3.81.0] A message when it starts - a notification and its spoken twin, the Home Assistant app
    # reading it aloud - and one when it ends, a rung of the valve turning off (not when it comes back from unavailable);
    # queued, so the end is not dropped while the option that turned it off still runs. The rain now: not raining.
    {**_T_BASE, "id": "libi_messages", "mode": "queued", "triggers": [
        {"trigger": "time", "at": "input_datetime.garden_start", "id": "start"},
        {"trigger": "state", "entity_id": _V2, "not_from": ["unavailable", "unknown"], "to": "off", "id": "ended"}],
     "actions": [{"choose": [
         {"conditions": [{"condition": "trigger", "id": "start"},
                         {"condition": "not", "conditions": [{"condition": "state", "entity_id": "weather.guy_smart_home",
                                                              "state": ["rainy", "pouring", "lightning-rainy",
                                                                        "snowy-rainy", "hail"]}]}],
          "sequence": [{"action": "switch.turn_on", "target": {"entity_id": _V2}},
                       {"action": "notify.mobile_app_sm_s918b", "data": {"message": "The watering starts"}},
                       {"action": "notify.mobile_app_sm_s918b",
                        "data": {"message": "TTS", "data": {"tts_text": "The watering starts"}}}]},
         {"conditions": [{"condition": "trigger", "id": "ended"}],
          "sequence": [{"action": "notify.mobile_app_sm_s918b", "data": {"message": "The watering ended"}}]}]}]},
    # [ADDED 2026-11-02, v3.84.0] The zone chosen on the card: the person is in it when their state is the zone chosen - a
    # state compared with the state of a dropdown, one CMP EQ - at the time and on the days set there.
    {**_T_BASE, "id": "libi_zone_choice", "triggers": [
        {"trigger": "time", "at": "input_datetime.train_reminder", "id": "start"}],
     "conditions": [{"condition": "template", "value_template": day_bits_template("input_number.train_days")},
                    {"condition": "state", "entity_id": "person.yulia", "state": "input_select.reminder_zone"}],
     "actions": [{"action": "notify.mobile_app_sm_s918b", "data": {"message": "TTS", "data": {
         "tts_text": "It is {{ states('input_datetime.train_reminder')[:5] }}, get ready to leave for the train home"}}}]},
]


@pytest.mark.parametrize("automation", LADDER_WAY, ids=[a["id"] for a in LADDER_WAY])
async def test_the_ladder_way_goes_back_as_it_was(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("error") or report.get("issues")


async def test_the_ladder_way_is_one_trigger_per_rung_and_a_for_is_its_ton(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import head_unit
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, _GARDEN_LADDER)
    assert len(net["rungs"]) == 4 and not any(r.get("sharesHead") for r in net["rungs"]) and net["links"] == []
    assert [r["elements"][0]["trigId"] for r in net["rungs"]] == ["start", "amount_reached", "time_limit", "restarted"]
    assert all(_trigger_count(r) == 1 for r in net["rungs"])
    limit = net["rungs"][2]["elements"]
    assert [e["type"] for e in limit] == ["contact_no", "timer_ton", "coil_r", "move"]
    assert limit[0]["forTimer"] and limit[1]["isFor"] and limit[1]["forValue"] == _MINUTES
    assert net["rungs"][2]["comment"].startswith("When valve garden switch turns on for minutes {{ states(")
    # A single trigger with a for: the rungs below hang from the trigger and its TON, both drawn once.
    net = yaml_to_ast(hass, LADDER_WAY[1])
    first, below = net["rungs"]
    assert [e["type"] for e in head_unit(first)] == ["contact_no", "timer_ton"] and below["sharesHead"]
    assert _trigger_count(below) == 0 and not any(e["type"] == "timer_ton" for e in below["elements"])


async def test_an_edited_or_removed_ton_of_a_trigger_writes_its_for(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast

    def limit_trigger(net):
        return next(t for t in ast_to_yaml(hass, net)["triggers"] if t.get("id") == "time_limit")

    net = yaml_to_ast(hass, _GARDEN_LADDER)
    net["rungs"][2]["elements"][1]["label"] = "00:20:00"
    assert limit_trigger(net)["for"] == {"hours": 0, "minutes": 20, "seconds": 0}
    assert ast_to_yaml(hass, net)["actions"][0]["choose"][2]["sequence"][0] == {
        "action": "switch.turn_off", "target": {"entity_id": _V2}}  # the TON is the for, never a delay
    net = yaml_to_ast(hass, _GARDEN_LADDER)
    del net["rungs"][2]["elements"][1]  # the time limit taken off the rung
    assert "for" not in limit_trigger(net)
    # A rung that hangs from a trigger with a for runs under that for: the trigger is written once, with it.
    out = ast_to_yaml(hass, yaml_to_ast(hass, LADDER_WAY[1]))
    assert out["triggers"] == LADDER_WAY[1]["triggers"]


def _palette():
    """Every block the user's palette offers: the ones it adds, and the kinds each block can be switched to."""
    text = (Path(__file__).parents[1] / "custom_components" / "libi" / "frontend" / "libi-panel.js").read_text(encoding="utf-8")
    lists = re.findall(r"fm\.type === 'dot'\) \{\s*\[([^\]]*)\]", text) + re.findall(r"pick\(\[([^\]]*)\]\)", text)
    return {name for chunk in lists for name in re.findall(r"'([a-z_]+)'", chunk)}


def _types(elements):
    for el in elements:
        yield el["type"]
        for branch in el.get("branches") or []:
            yield from _types(branch)
        yield from _types(el.get("sequence") or [])


async def test_the_importer_draws_only_blocks_the_palette_has(hass: HomeAssistant) -> None:
    """Learn the user's blocks from the palette itself, so a block type the palette does not have fails here."""
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    palette = _palette()
    assert {"contact_no", "contact_n", "coil_t", "timer_toff", "cmp_rng", "math_sub", "ctu", "parallel"} <= palette, palette
    for automation in CORPUS + HOISTED + VARIABLES + REPEATS + DURATIONS + WAITS + RECENT + CLOCKS + SHARED + LADDER_WAY:
        net = yaml_to_ast(hass, automation)
        drawn = {t for rung in net["rungs"] for t in _types(rung["elements"])}
        assert drawn <= palette, (automation["id"], drawn - palette)


def _wait_of(net):
    return next(el for rung in net["rungs"] for el in rung["elements"] if el.get("waitFor"))


async def test_the_garden_wait_is_a_cmp_an_edge_contact_and_a_ton(hass: HomeAssistant) -> None:
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, WAITS[0])
    wait = _wait_of(net)
    assert wait["type"] == "parallel" and wait["closed"] and wait["fromAction"]
    (meter,), (valve,), (limit,) = wait["branches"]
    assert (meter["type"], meter["sourceA"], meter["sourceB"]) == ("cmp_gt", _METER, "input_number.garden_litres")
    assert (valve["type"], valve["label"]) == ("contact_n", _V)
    assert limit["type"] == "timer_ton" and limit["label"].startswith("minutes {{ states('input_number.max_minutes')")
    assert not any(x.get("isTrigger") for x in (meter, valve, limit))
    assert "wait until" in net["rungs"][0]["comment"]
    one = _wait_of(yaml_to_ast(hass, WAITS[1]))
    assert (one["type"], one["label"], one["waitOne"]) == ("contact_p", "binary_sensor.door", True)
    tof = next(el for rung in yaml_to_ast(hass, RECENT[0])["rungs"] for el in rung["elements"] if el.get("isRecent"))
    assert tof["type"] == "timer_toff"


async def test_an_edited_wait_writes_what_its_blocks_now_say(hass: HomeAssistant) -> None:
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast

    def compiled(net):
        return next(a for a in ast_to_yaml(hass, net)["actions"] if "wait_for_trigger" in a)

    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"][2][0]["label"] = "00:20:00"
    out = compiled(net)
    assert out["timeout"] == "00:20:00" and out["continue_on_timeout"] is True
    assert out["wait_for_trigger"] == _WAIT_NET3["wait_for_trigger"]
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"][0][0]["sourceB"] = "input_number.other"
    out = compiled(net)
    assert out["wait_for_trigger"][0]["above"] == "input_number.other" and out["timeout"] == _WAIT_NET3["timeout"]
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"].pop(1)  # closing the valve by hand no longer ends the wait
    assert compiled(net)["wait_for_trigger"] == _WAIT_NET3["wait_for_trigger"][:1]
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"][2] = []  # no time limit any more
    out = compiled(net)
    assert "timeout" not in out and out["continue_on_timeout"] is True
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"].insert(2, [{"id": "x1", "type": "contact_p", "label": "binary_sensor.rain"}])
    assert compiled(net)["wait_for_trigger"][2] == {"trigger": "state", "entity_id": "binary_sensor.rain", "to": "on"}
    net = yaml_to_ast(hass, WAITS[2])
    _wait_of(net)["branches"][1][0]["label"] = "00:10:00"
    out = compiled(net)
    assert out["wait_for_trigger"] == WAITS[2]["actions"][1]["wait_for_trigger"] and out["timeout"] == "00:10:00"
    assert out["continue_on_timeout"] is False


async def test_a_wait_the_ladder_cannot_say_is_kept_as_it_was(hass: HomeAssistant) -> None:
    """Two blocks in one branch, or an action inside the wait, have no wait_for_trigger form; the panel marks them
    red, and the compiler keeps the wait as it was instead of guessing. A wait whose blocks are all gone is gone."""
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"][0].append({"id": "x2", "type": "contact_no", "label": "binary_sensor.rain"})
    assert ast_to_yaml(hass, net)["actions"][1] == _WAIT_NET3
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"].append([{"id": "x3", "type": "coil_s", "label": "light.hall"}])
    assert ast_to_yaml(hass, net)["actions"][1] == _WAIT_NET3
    net = yaml_to_ast(hass, WAITS[0])
    _wait_of(net)["branches"] = [[], [], []]
    assert not any("wait_for_trigger" in a for a in ast_to_yaml(hass, net)["actions"])


async def test_a_wait_block_or_a_timer_tof_from_an_older_drawing_still_compiles(hass: HomeAssistant) -> None:
    """Drawings saved before 3.68.0 can hold a WAIT block and a TOF named timer_tof; both compile as before."""
    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import element_sig, yaml_to_ast
    net = yaml_to_ast(hass, WAITS[0])
    elements = net["rungs"][0]["elements"]
    old = {"id": "old1", "type": "wait", "label": _METER, "raw": _WAIT_NET3, "isTrigger": False, "fromAction": True}
    old["sig"] = element_sig(old)
    elements[elements.index(_wait_of(net))] = old
    assert ast_to_yaml(hass, net)["actions"][1] == _WAIT_NET3
    net = yaml_to_ast(hass, RECENT[0])
    for rung in net["rungs"]:
        for el in rung["elements"]:
            if el.get("isRecent"):
                el["type"] = "timer_tof"
    assert ast_to_yaml(hass, net)["conditions"] == RECENT[0]["conditions"]


_DAYS = "input_number.garden_days"


def _blocks(elements):
    for el in elements:
        yield el
        for branch in el.get("branches") or []:
            yield from _blocks(branch)


def _day_block(net):
    """The first CMP DAY of a net, in parallel branches as well."""
    return next(e for r in net["rungs"] for e in _blocks(r["elements"]) if e.get("sourceA") == "weekday")


async def test_the_days_of_an_8_bit_helper_are_one_cmp_day(hass: HomeAssistant) -> None:
    """[ADDED 2026-10-31, v3.76.0] The user: "an 8-bit variable - bit 1 Sunday, bit 2 Monday ... - shown as checkboxes".
    Home Assistant's time condition takes fixed days only, so CMP DAY = a helper is one template that reads today's
    bit. It is drawn as one CMP DAY block, its rung says so, and it goes back as it was; edited, it is written anew -
    for another helper, or as fixed days; drawn new, it is that template; a template written otherwise stays one."""
    import copy

    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    hass.states.async_set(_DAYS, "21.0", {"friendly_name": "Garden days", "min": 0, "max": 255})
    auto = next(a for a in LADDER_WAY if a["id"] == "alarm_clock_day_bits")
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    day = _day_block(net)
    assert (day["type"], day["sourceB"], day["kind"]) == ("cmp_eq", _DAYS, "date")
    assert sum(e.get("sourceA") == "weekday" for r in net["rungs"] for e in _blocks(r["elements"])) == 1
    assert "if the day is ticked in garden days, then" in net["rungs"][0]["comment"]

    def start_conditions(net):
        return ast_to_yaml(hass, net)["actions"][0]["choose"][0]["conditions"]

    day["sourceB"] = "input_number.other_days"
    assert start_conditions(net)[1] == {"condition": "template",
                                        "value_template": day_bits_template("input_number.other_days")}
    day["sourceB"] = "mon, wed"
    assert start_conditions(net)[1] == {"condition": "time", "weekday": ["mon", "wed"]}
    # Drawn new: no node of its own to start from.
    day.update(sourceB=_DAYS)
    for key in ("raw", "sig"):
        day.pop(key, None)
    assert start_conditions(net)[1] == {"condition": "template", "value_template": day_bits_template(_DAYS)}
    # Written in another way, it is a template like any other.
    other = copy.deepcopy(auto)
    other["actions"][0]["choose"][0]["conditions"][1]["value_template"] = day_bits_template(_DAYS).replace(" | ", "|")
    assert not any(e.get("sourceA") == "weekday" for r in yaml_to_ast(hass, other)["rungs"] for e in _blocks(r["elements"]))
    assert verify_round_trip(hass, other)["ok"]


async def test_fixed_days_edited_and_days_of_a_helper_in_a_time_window(hass: HomeAssistant) -> None:
    """[ADDED 2026-10-31, v3.76.0] A CMP DAY of fixed days that is edited keeps its time condition - it got the
    entity_id "weekday" patched into it before - and the days of a helper in a time window are a template of their
    own, next to the window."""
    import copy

    from custom_components.libi.libi_to_yaml import ast_to_yaml
    from custom_components.libi.yaml_to_libi import yaml_to_ast
    hass.states.async_set(_DAYS, "21.0", {"friendly_name": "Garden days"})
    auto = next(a for a in LADDER_WAY if a["id"] == "alarm_clock")
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    first = _day_block(net)
    first["sourceB"] = "mon, tue"
    assert ast_to_yaml(hass, net)["actions"][0]["choose"][0]["conditions"][1]["conditions"][0]["conditions"][0] == {
        "condition": "time", "weekday": ["mon", "tue"]}
    window = {**_T_BASE, "id": "window", "conditions": [{"condition": "time", "after": "06:00:00", "weekday": ["mon"]}],
              "actions": [_ON]}
    net = yaml_to_ast(hass, copy.deepcopy(window))
    _day_block(net)["sourceB"] = _DAYS
    assert ast_to_yaml(hass, net)["conditions"] == [{"condition": "and", "conditions": [
        {"condition": "time", "after": "06:00:00"},
        {"condition": "template", "value_template": day_bits_template(_DAYS)}]}]


async def test_the_day_bits_template_reads_the_bit_of_today(hass: HomeAssistant, freezer) -> None:
    """[ADDED 2026-10-31, v3.76.0] Run by Home Assistant's own template engine: 21 is bit 1, 3 and 5 - Sunday, Tuesday,
    Thursday. A helper that is not a number holds no day, so nothing runs on a day nobody ticked."""
    from homeassistant.helpers.template import Template
    from homeassistant.util import dt as dt_util
    hass.states.async_set(_DAYS, "21.0")
    template = Template(day_bits_template(_DAYS), hass)
    week = {"2026-11-01": True, "2026-11-02": False, "2026-11-03": True, "2026-11-04": False, "2026-11-05": True,
            "2026-11-06": False, "2026-11-07": False}  # Sunday to Saturday
    for date, expected in week.items():
        freezer.move_to(dt_util.parse_datetime(f"{date}T12:00:00").replace(tzinfo=dt_util.get_default_time_zone()))
        assert dt_util.now().strftime("%Y-%m-%d") == date
        assert template.async_render() is expected, date
    hass.states.async_set(_DAYS, "127.0")
    assert template.async_render() is True
    for state in ("0.0", "unavailable", "unknown"):
        hass.states.async_set(_DAYS, state)
        assert template.async_render() is False, state
