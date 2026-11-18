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
# [ADDED v3.96.0 | 2026-11-17] Purpose: The user (2026-11-17): "check that dimming works with MOVE and through a variable,
#   and a colour for an LED strip". A MOVE drawn to a light was written as action: light.kitchen, which Home Assistant
#   saves and never runs; a variable on IN as the words of its id; a constant 0.5 in a MATH block as states('0.5'). And
#   a light's brightness or colour read from Home Assistant was a plain coil, the value out of sight.
# [CHANGED v3.96.2 | 2026-11-18] Purpose: The review of the release (RULE 41): a value that is the words of an entity
#   id stays those words when edited, and a scene's blocks pasted into an automation are the actions they show.
"""A MOVE that sets a value: on a helper and on a device, fixed or from a variable, drawn by hand and read back."""
import copy

import pytest
import yaml
from homeassistant.core import HomeAssistant

from custom_components.libi.libi_to_yaml import ast_to_yaml, verify_round_trip
from custom_components.libi.yaml_to_libi import (
    DEVICE_VALUE_SERVICES, LIGHT_VALUE_KEYS, read_template, scene_to_ast, template_entity, yaml_to_ast,
)

from .save_helpers import home_assistant_files, save
from .test_websocket import libi  # noqa: F401 - the fixture

MOTION = {"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}
KITCHEN = {"entity_id": "light.kitchen"}
LED = {"entity_id": "light.led"}


def _auto(*actions) -> dict:
    return {"id": "a1", "alias": "Lights", "triggers": [copy.deepcopy(MOTION)], "actions": [copy.deepcopy(a) for a in actions]}


def _net(*moves) -> dict:
    """A NET drawn by hand: the motion contact, then each MOVE (source, target, valueKey) in a row."""
    elements = [{"id": "e0", "type": "contact_no", "label": "binary_sensor.motion", "isTrigger": True}]
    for i, (source, target, key) in enumerate(moves, start=1):
        el = {"id": f"e{i}", "type": "move", "mode": "value", "source": source, "target": target}
        if key:
            el["valueKey"] = key
        elements.append(el)
    return {"id": "n1", "name": "Lights", "level": "automation", "rungs": [{"id": "r1", "elements": elements}]}


def _actions(hass, *moves) -> list:
    return ast_to_yaml(hass, _net(*moves))["actions"]


def _last(net) -> dict:
    return net["rungs"][0]["elements"][-1]


# ---------------------------------------------------------------- read from Home Assistant
READ = [
    ("brightness", {"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_pct": 50}}, "brightness_pct", 50),
    ("brightness 0-255", {"action": "light.turn_on", "target": KITCHEN, "data": {"brightness": 128}}, "brightness", 128),
    ("with a transition", {"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_pct": 30, "transition": 2}},
     "brightness_pct", 30),
    ("from a helper", {"action": "light.turn_on", "target": KITCHEN,
                       "data": {"brightness_pct": "{{ states('input_number.dim') | int }}"}}, "brightness_pct", "input_number.dim"),
    ("dim down", {"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_step_pct": -10}}, "brightness_step_pct", -10),
    ("colour", {"action": "light.turn_on", "target": LED, "data": {"rgb_color": [255, 136, 0]}}, "rgb_color", "[255, 136, 0]"),
    ("colour of a light", {"action": "light.turn_on", "target": LED,
                           "data": {"rgb_color": "{{ state_attr('light.kitchen', 'rgb_color') }}"}}, "rgb_color", "light.kitchen"),
    ("colour temperature", {"action": "light.turn_on", "target": KITCHEN, "data": {"color_temp_kelvin": 2700}},
     "color_temp_kelvin", 2700),
    ("colour by name", {"action": "light.turn_on", "target": LED, "data": {"color_name": "red"}}, "color_name", "red"),
    ("effect", {"action": "light.turn_on", "target": LED, "data": {"effect": "rainbow"}}, "effect", "rainbow"),
    ("fan speed", {"action": "fan.set_percentage", "target": {"entity_id": "fan.ceiling"}, "data": {"percentage": 40}},
     "percentage", 40),
    ("blind", {"action": "cover.set_cover_position", "target": {"entity_id": "cover.blind"}, "data": {"position": 0}},
     "position", 0),
    ("thermostat", {"action": "climate.set_temperature", "target": {"entity_id": "climate.ac"}, "data": {"temperature": 22.5}},
     "temperature", 22.5),
    ("volume", {"action": "media_player.volume_set", "target": {"entity_id": "media_player.tv"}, "data": {"volume_level": 0.3}},
     "volume_level", 0.3),
]


@pytest.mark.parametrize(("name", "action", "key", "shown"), READ, ids=[r[0] for r in READ])
def test_a_value_a_device_is_given_is_a_move_of_that_value(hass: HomeAssistant, name, action, key, shown):
    """The user sees 50 % and the colour - they were inside a coil - and the action comes back as it was."""
    auto = _auto(action)
    assert verify_round_trip(hass, copy.deepcopy(auto))["ok"], name
    el = _last(yaml_to_ast(hass, copy.deepcopy(auto)))
    assert (el["type"], el.get("mode"), el.get("valueKey"), el.get("source")) == ("move", "value", key, shown), el
    assert el["target"] == action["target"]["entity_id"]


KEPT = [
    ("two values", {"action": "light.turn_on", "target": LED, "data": {"rgb_color": [255, 0, 0], "brightness_pct": 80}}, "coil_s"),
    ("no value", {"action": "light.turn_on", "target": KITCHEN, "data": {"transition": 2}}, "coil_s"),
    ("toggle", {"action": "light.toggle", "target": KITCHEN, "data": {"brightness_pct": 40}}, "coil_t"),
    ("an area", {"action": "light.turn_on", "target": {"area_id": "living_room"}, "data": {"brightness_pct": 20}}, "move"),
    ("two lights", {"action": "light.turn_on", "target": {"entity_id": ["light.a", "light.b"]}, "data": {"brightness_pct": 60}}, "move"),
    ("entity in the data", {"action": "light.turn_on", "data": {"entity_id": "light.x", "brightness": 100}}, "coil_s"),
    ("thermostat and mode", {"action": "climate.set_temperature", "target": {"entity_id": "climate.ac"},
                             "data": {"temperature": 22, "hvac_mode": "cool"}}, "move"),
]


@pytest.mark.parametrize(("name", "action", "drawn"), KEPT, ids=[k[0] for k in KEPT])
def test_anything_but_one_value_on_one_device_keeps_its_drawing(hass: HomeAssistant, name, action, drawn):
    auto = _auto(action)
    assert verify_round_trip(hass, copy.deepcopy(auto))["ok"], name
    el = _last(yaml_to_ast(hass, copy.deepcopy(auto)))
    assert el["type"] == drawn and (drawn != "move" or el.get("moveKind") == "action"), el


def test_continue_on_error_of_a_helper_set_comes_back(hass: HomeAssistant):
    """The block's tick was not set, so the node was compiled again - without its continue_on_error."""
    for action in ({"action": "input_number.set_value", "target": {"entity_id": "input_number.a"}, "data": {"value": 5},
                    "continue_on_error": True},
                   {"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_pct": 5}, "continue_on_error": True}):
        auto = _auto(action)
        assert verify_round_trip(hass, copy.deepcopy(auto))["ok"], action
        net = yaml_to_ast(hass, copy.deepcopy(auto))
        assert _last(net)["continueOnError"] is True
        _last(net)["source"] = 7
        assert ast_to_yaml(hass, net)["actions"][0]["continue_on_error"] is True


# ---------------------------------------------------------------- drawn by hand
def test_a_move_drawn_to_a_device_calls_its_action(hass: HomeAssistant):
    """It was written as action: light.kitchen - saved by Home Assistant, never run."""
    on = {"entity_id": "light.kitchen"}
    assert _actions(hass, ("50", "light.kitchen", None)) == [
        {"action": "light.turn_on", "target": on, "data": {"brightness_pct": 50}}]
    assert _actions(hass, ("2700", "light.kitchen", "color_temp_kelvin")) == [
        {"action": "light.turn_on", "target": on, "data": {"color_temp_kelvin": 2700}}]
    assert _actions(hass, ("-10", "light.kitchen", "brightness_step_pct"))[0]["data"] == {"brightness_step_pct": -10}
    for source in ("[255, 136, 0]", "#ff8800", "255, 136, 0"):
        assert _actions(hass, (source, "light.led", "rgb_color"))[0]["data"] == {"rgb_color": [255, 136, 0]}, source
    assert _actions(hass, ("red", "light.led", "color_name"))[0]["data"] == {"color_name": "red"}
    assert _actions(hass, ("rainbow", "light.led", "effect"))[0]["data"] == {"effect": "rainbow"}
    assert [(a["action"], a["data"]) for a in _actions(
        hass, ("40", "fan.ceiling", None), ("0", "cover.blind", None), ("21.5", "climate.ac", None),
        ("0.3", "media_player.tv", None), ("55", "humidifier.room", None), ("10", "valve.garden", None),
        ("50", "water_heater.boiler", None))] == [
        ("fan.set_percentage", {"percentage": 40}), ("cover.set_cover_position", {"position": 0}),
        ("climate.set_temperature", {"temperature": 21.5}), ("media_player.volume_set", {"volume_level": 0.3}),
        ("humidifier.set_humidity", {"humidity": 55}), ("valve.set_valve_position", {"position": 10}),
        ("water_heater.set_temperature", {"temperature": 50})]
    # A helper as before: the value as typed.
    assert _actions(hass, ("hello", "input_text.note", None)) == [
        {"action": "input_text.set_value", "target": {"entity_id": "input_text.note"}, "data": {"value": "hello"}}]


def test_a_variable_on_in_is_its_value_when_the_action_runs(hass: HomeAssistant):
    """input_number.a into input_number.b wrote the words "input_number.a"."""
    def data(source, target, key=None):
        return _actions(hass, (source, target, key))[0]["data"]

    assert data("input_number.a", "input_number.b") == {"value": "{{ states('input_number.a') }}"}
    assert data("input_number.dim", "light.kitchen") == {"brightness_pct": "{{ states('input_number.dim') }}"}
    assert data("sensor.lux", "light.kitchen", "brightness") == {"brightness": "{{ states('sensor.lux') }}"}
    assert data("light.desk", "light.kitchen", "brightness") == {"brightness": "{{ state_attr('light.desk', 'brightness') }}"}
    assert data("light.desk", "light.kitchen") == {
        "brightness_pct": "{{ ((state_attr('light.desk', 'brightness') | int(0)) / 2.55) | round(0) }}"}
    assert data("light.desk", "light.led", "rgb_color") == {"rgb_color": "{{ state_attr('light.desk', 'rgb_color') }}"}
    # A colour by name read from a light is that light's colour, as a list.
    assert data("light.desk", "light.led", "color_name") == {"rgb_color": "{{ state_attr('light.desk', 'rgb_color') }}"}
    assert data("input_select.led_color", "light.led", "color_name") == {"color_name": "{{ states('input_select.led_color') }}"}
    hexed = data("input_text.led_color", "light.led", "rgb_color")["rgb_color"]
    assert hexed.startswith("{% set c = states('input_text.led_color')") and "int(0, 16)" in hexed
    assert data("input_select.mode", "input_select.copy") == {"option": "{{ states('input_select.mode') }}"}
    # A word with a point in it that is no entity stays the word.
    assert data("v1.2", "input_text.note") == {"value": "v1.2"}


def test_every_variable_written_is_read_back_as_that_variable(hass: HomeAssistant):
    """What a MOVE writes for a variable comes back as that variable on the IN pin (template_entity)."""
    for key in LIGHT_VALUE_KEYS + ("value", "option", "percentage", "position", "temperature"):
        for entity in ("input_number.a", "sensor.b", "light.c", "input_text.d", "input_select.e"):
            assert template_entity(read_template(entity, key), key) == entity, (key, entity)
    for written in ("{{ states('input_number.a') | int }}", "{{ states(\"input_number.a\") | float(0) }}",
                    "{{states('input_number.a')}}"):
        assert template_entity(written) == "input_number.a", written
    for written in ("{{ states('input_number.a') | int + 5 }}", "{{ state_attr('light.c', 'brightness') * 2 }}", "50"):
        assert template_entity(written, "brightness") == "", written


def test_an_edited_value_of_a_device_keeps_the_rest_of_its_call(hass: HomeAssistant):
    auto = _auto({"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_pct": 30, "transition": 2},
                  "alias": "Soft"})
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    el = _last(net)
    el["source"] = "70"
    assert ast_to_yaml(hass, net)["actions"] == [
        {"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_pct": 70, "transition": 2}, "alias": "Soft"}]
    # Another value of the light: the block sets one, so the old one goes and the transition stays.
    el.update(valueKey="rgb_color", source="[255, 0, 0]")
    assert ast_to_yaml(hass, net)["actions"][0]["data"] == {"transition": 2, "rgb_color": [255, 0, 0]}
    # Another kind of thing: its own action, not light.turn_on with a fan in it.
    el.update(valueKey=None, source="40", target="fan.ceiling")
    assert ast_to_yaml(hass, net)["actions"] == [
        {"action": "fan.set_percentage", "target": {"entity_id": "fan.ceiling"}, "data": {"percentage": 40}}]


def test_a_move_to_what_takes_no_value_does_not_compile(hass: HomeAssistant):
    """Home Assistant saves an action named after an entity, and never runs it: LIBI refuses it, and says why."""
    for source, target, key, words in (
            ("50", "switch.pump", None, "a switch has no value a MOVE can set"),
            ("1", "my_value", None, "OUT needs one entity"),
            ("bright", "light.kitchen", None, "brightness_pct takes a number"),
            ("#ff8800", "light.kitchen", None, "brightness_pct takes a number"),
            ("orange", "light.led", "rgb_color", "rgb_color takes a colour"),
            ("[1, 2]x", "light.led", "rgb_color", "rgb_color takes a colour")):
        with pytest.raises(ValueError, match=words):
            _actions(hass, (source, target, key))


def test_a_constant_with_a_point_in_a_math_block_is_a_constant(hass: HomeAssistant):
    """0.5 was read as an entity: states('0.5'), which is 0."""
    net = _net()
    net["rungs"][0]["elements"].append({"id": "e9", "type": "math_add", "sourceA": "input_number.a", "sourceB": "0.5",
                                        "target": "input_number.b"})
    value = ast_to_yaml(hass, net)["actions"][0]["data"]["value"]
    assert value == "{{ (states('input_number.a') | float(0)) + (0.5) }}"


def test_a_device_value_service_list_matches_the_panel():
    """The panel offers what the compiler takes (libi-panel.js MOVE_SETS): every device of it has its action here."""
    assert {svc.split(".")[0] for svc in DEVICE_VALUE_SERVICES} == {
        "light", "fan", "cover", "valve", "climate", "water_heater", "humidifier", "media_player"}


# ---------------------------------------------------------------- saved through Home Assistant, opened again
async def test_dimming_and_a_colour_drawn_by_hand_are_saved_and_read_back(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    """SAVE & COMPILE through Home Assistant's own config API: what reaches automations.yaml is what Home Assistant runs,
    and the NET drawn again from it shows the same blocks - the helper on IN, the colour as a colour."""
    await home_assistant_files(hass, libi, automations=[])
    client, http = await hass_ws_client(hass), await hass_client()
    net = _net(("input_number.dim", "light.kitchen", None), ("[255, 136, 0]", "light.led", "rgb_color"))
    plan, done = await save(client, http, [net])
    assert done and done["status"] == "ok", (plan, done)
    written = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert written[0]["actions"] == [
        {"action": "light.turn_on", "target": {"entity_id": "light.kitchen"},
         "data": {"brightness_pct": "{{ states('input_number.dim') }}"}},
        {"action": "light.turn_on", "target": {"entity_id": "light.led"}, "data": {"rgb_color": [255, 136, 0]}}]
    drawn = yaml_to_ast(hass, copy.deepcopy(written[0]))["rungs"][0]["elements"][1:]
    assert [(e["source"], e["target"], e["valueKey"]) for e in drawn] == [
        ("input_number.dim", "light.kitchen", "brightness_pct"), ("[255, 136, 0]", "light.led", "rgb_color")]


async def test_a_move_to_a_switch_is_not_saved(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    await home_assistant_files(hass, libi, automations=[])
    before = (libi / "automations.yaml").read_text(encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(("50", "switch.pump", None))])
    assert done is None and not plan["ok"], plan
    assert any("a switch has no value a MOVE can set" in e for e in plan["errors"]), plan["errors"]
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before


def test_a_rung_says_what_a_move_sets_and_to_what(hass: HomeAssistant):
    """A scene of one entity's attributes read "set it and set it and set it": now each value is said, once per thing."""
    scene = scene_to_ast(hass, {"id": "1", "name": "Movie", "entities": {
        "light.sofa": {"state": "on", "brightness": 80, "rgb_color": [255, 180, 120]},
        "sensor.valve_battery": {"state": "200", "unit_of_measurement": "%", "friendly_name": "Battery"}}})
    said = [r["comment"] for r in scene["rungs"]]
    assert said == ["Turn on sofa and set sofa brightness to 80, color to [255, 180, 120]",
                    "Set valve battery to 200, unit of measurement to %, friendly name to Battery"], said
    net = yaml_to_ast(hass, _auto({"action": "light.turn_on", "target": KITCHEN, "data": {"brightness_pct": 50}},
                                  {"action": "light.turn_on", "target": LED,
                                   "data": {"rgb_color": "{{ state_attr('light.kitchen', 'rgb_color') }}"}}))
    assert net["rungs"][0]["comment"] == ("When motion turns on, then set kitchen brightness to 50 % and set led color from "
                                          "kitchen"), net["rungs"][0]["comment"]


async def test_a_light_in_a_scene_built_by_the_ai_chat_is_a_scene_home_assistant_takes(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    """The AI chat builds a scene from light.turn_on actions: "brightness 50 %" was written as brightness_pct with no
    state, which Home Assistant refuses (and before the MOVE, the brightness was dropped). Now the light is on at 128."""
    await home_assistant_files(hass, libi, scenes=[])
    client, http = await hass_ws_client(hass), await hass_client()
    net = yaml_to_ast(hass, {"id": "s", "alias": "Evening", "triggers": [], "conditions": [], "actions": [
        {"action": "light.turn_on", "target": {"entity_id": "light.sofa"}, "data": {"brightness_pct": 50}},
        {"action": "light.turn_on", "target": {"entity_id": "light.led"}, "data": {"rgb_color": [255, 0, 0]}},
        {"action": "light.turn_off", "target": {"entity_id": "light.hall"}}]})
    net.update(id="n1", level="scene", name="Evening", ha_id=None)
    assert ast_to_yaml(hass, copy.deepcopy(net))["entities"] == {
        "light.sofa": {"state": "on", "brightness": 128}, "light.led": {"state": "on", "rgb_color": [255, 0, 0]},
        "light.hall": "off"}
    plan, done = await save(client, http, [net])
    assert done is not None and done["status"] == "ok", (plan, done)
    written = yaml.safe_load((libi / "scenes.yaml").read_text(encoding="utf-8"))
    assert written[0]["entities"]["light.sofa"] == {"state": "on", "brightness": 128}


def test_an_edited_stop_or_event_keeps_its_own_key(hass: HomeAssistant):
    """Edited, a stop and an event were written as an action named stop / named after the event."""
    for action, field, value, expected in (
            ({"stop": "Nothing to do", "response_variable": "result"}, "source", "Done early",
             {"stop": "Done early", "response_variable": "result"}),
            ({"event": "garden_done", "event_data": {"zone": "north"}}, "target", "garden_finished",
             {"event": "garden_finished", "event_data": {"zone": "north"}})):
        net = yaml_to_ast(hass, _auto(action))
        el = _last(net)
        el[field] = value
        assert ast_to_yaml(hass, net)["actions"] == [expected], (action, ast_to_yaml(hass, net)["actions"])


# ---------------------------------------------------------------- the review of the release (RULE 41, 2026-11-18)
def test_a_value_that_is_the_words_of_an_entity_id_stays_those_words(hass: HomeAssistant):
    """A text helper given the NAME of a speaker - media_player.living_room, words - and a list given one as its option.
    Edited, the words were read as the speaker: the helper was given its state, playing. They stay words, and the rung
    says them; a MOVE drawn with a variable's id on IN still reads that variable."""
    auto = _auto({"action": "input_text.set_value", "target": {"entity_id": "input_text.speaker"},
                  "data": {"value": "media_player.living_room"}},
                 {"action": "input_select.select_option", "target": {"entity_id": "input_select.speaker"},
                  "data": {"option": "media_player.kitchen"}})
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    text, choice = net["rungs"][0]["elements"][-2:]
    assert (text["source"], text.get("literal"), choice["source"], choice.get("literal")) == (
        "media_player.living_room", True, "media_player.kitchen", True), (text, choice)
    said = net["rungs"][0]["comment"]
    assert "to media_player.living_room" in said and "from living room" not in said, said
    assert ast_to_yaml(hass, copy.deepcopy(net))["actions"] == auto["actions"]  # untouched: as the file had it
    text["target"], choice["source"] = "input_text.other", "media_player.bedroom"
    written = ast_to_yaml(hass, net)["actions"]
    assert written == [{"action": "input_text.set_value", "target": {"entity_id": "input_text.other"},
                        "data": {"value": "media_player.living_room"}},
                       {"action": "input_select.select_option", "target": {"entity_id": "input_select.speaker"},
                        "data": {"option": "media_player.bedroom"}}], written
    drawn = _actions(hass, ("input_text.name", "input_text.speaker", "value"))
    assert drawn[0]["data"]["value"] == read_template("input_text.name", "value"), drawn


def test_a_block_of_a_scene_moved_into_an_automation_is_the_action_it_shows(hass: HomeAssistant):
    """A scene's blocks keep their place in the scene as their node. Pasted into an automation - or its NET made an
    automation - they were written as that node, an action scene: {...} that Home Assistant refuses."""
    scene = scene_to_ast(hass, {"id": "1", "name": "Movie", "entities": {
        "light.sofa": {"state": "on", "brightness": 80}, "switch.fan": "off"}})
    blocks = [el for rung in scene["rungs"] for el in rung["elements"]]
    assert [isinstance(el.get("raw"), dict) and isinstance(el["raw"].get("scene"), dict) for el in blocks] == [True] * 3
    net = {"id": "n1", "name": "Movie time", "level": "automation", "rungs": [{"id": "r1", "elements": [
        {"id": "t", "type": "contact_no", "label": "binary_sensor.motion", "isTrigger": True}] + copy.deepcopy(blocks)}]}
    written = ast_to_yaml(hass, net)["actions"]
    # A coil with no action of its own behind it is Home Assistant's turn on / turn off (libi_to_yaml, v3.30.0).
    assert written == [{"action": "homeassistant.turn_on", "target": {"entity_id": "light.sofa"}},
                       {"action": "light.turn_on", "target": {"entity_id": "light.sofa"}, "data": {"brightness": 80}},
                       {"action": "homeassistant.turn_off", "target": {"entity_id": "switch.fan"}}], written

