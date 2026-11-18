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
# [ADDED v3.96.0 | 2026-11-18] Purpose: The user (2026-11-18): "I need RAND - a random whole number between IN1 and IN2;
#   MOD - the remainder, one more operation of MATH; MUX - input number K, the inputs the colours; min and max may be
#   variables, and the value goes into a variable". Each block is drawn, compiled, read back as the same block and run
#   by Home Assistant; and MATH with a constant on a pin, which came back as a MOVE of a long template, is MATH again.
# [CHANGED v3.96.2 | 2026-11-18] Purpose: The review of the release (RULE 41): RAND of a fraction, RAND of one number
#   never the one OUT holds and a MUX's K a fraction do not compile; a MUX of the words of entity ids keeps them as
#   words when edited; and RAND of one number never the one it holds is run from two variables, which no compiler
#   sees.
"""The blocks of the Math group - MATH, MOD, RAND, MUX - both ways, refused where they cannot run, and run."""
import copy
import logging
import re

import pytest
import yaml
from homeassistant.components.light import ColorMode
from homeassistant.setup import async_setup_component
from homeassistant.util import color as color_util
from pytest_homeassistant_custom_component.common import setup_test_component_platform

from custom_components.libi.libi_to_yaml import ast_to_yaml, verify_round_trip
from custom_components.libi.yaml_to_libi import SIG_FIELDS, calc_block, element_sig, yaml_to_ast

from .save_helpers import home_assistant_files, save
from .test_move_lights_live import STRIP, HouseLight
from .test_websocket import libi  # noqa: F401 - the fixture

MOTION = {"id": "e0", "type": "contact_no", "label": "binary_sensor.motion", "isTrigger": True}


def _net(*blocks, level="automation") -> dict:
    return {"id": "n1", "name": "Calc", "level": level,
            "rungs": [{"id": "r1", "elements": [copy.deepcopy(MOTION)] + [dict(b, id=f"e{i}") for i, b in
                                                                           enumerate(blocks, start=1)]}]}


def _actions(hass, *blocks) -> list:
    return ast_to_yaml(hass, _net(*blocks))["actions"]


def _drawn(hass, auto) -> list:
    return yaml_to_ast(hass, copy.deepcopy(auto))["rungs"][0]["elements"][1:]


FIELDS = ("type", "sourceA", "sourceB", "target", "inputs", "notSame", "valueKey", "precision", "fallback")

# Each block as the panel draws it, and the action it compiles to.
BLOCKS = [
    ("MATH ADD of two variables", {"type": "math_add", "sourceA": "input_number.a", "sourceB": "input_number.b",
                                   "target": "input_number.c"},
     {"action": "input_number.set_value", "target": {"entity_id": "input_number.c"},
      "data": {"value": "{{ (states('input_number.a') | float(0)) + (states('input_number.b') | float(0)) }}"}}),
    ("MATH SUB of a constant", {"type": "math_sub", "sourceA": "input_number.a", "sourceB": "5",
                                "target": "input_number.c"},
     {"action": "input_number.set_value", "target": {"entity_id": "input_number.c"},
      "data": {"value": "{{ (states('input_number.a') | float(0)) - (5) }}"}}),
    ("MATH DIV", {"type": "math_div", "sourceA": "sensor.power", "sourceB": "1000", "target": "input_number.kw",
                  "precision": 1, "fallback": 0},
     {"action": "input_number.set_value", "target": {"entity_id": "input_number.kw"},
      "data": {"value": "{{ (((states('sensor.power') | float(0)) / (1000)) | round(1)) if (1000) != 0 else 0 }}"}}),
    ("MOD into a counter", {"type": "math_mod", "sourceA": "counter.step", "sourceB": "4", "target": "counter.step"},
     {"action": "counter.set_value", "target": {"entity_id": "counter.step"},
      "data": {"value": "{{ (states('counter.step') | int(0)) % 4 }}"}}),
    ("RAND of fixed numbers", {"type": "math_rand", "sourceA": "0", "sourceB": "9", "target": "counter.index",
                               "notSame": False},
     {"action": "counter.set_value", "target": {"entity_id": "counter.index"},
      "data": {"value": "{{ range(0, 9 + 1) | random }}"}}),
    ("RAND of variables, never the one it holds",
     {"type": "math_rand", "sourceA": "input_number.low", "sourceB": "input_number.high", "target": "input_number.r",
      "notSame": True},
     {"action": "input_number.set_value", "target": {"entity_id": "input_number.r"},
      "data": {"value": "{{ range((states('input_number.low') | int(0)), (states('input_number.high') | int(0)) + 1) "
                        "| reject('eq', states('input_number.r') | int(None)) | list | random }}"}}),
    ("MUX of colours to a light", {"type": "mux", "sourceA": "counter.index",
                                   "inputs": ["red", "orange", "input_select.colour_3", "[0, 0, 255]"],
                                   "target": "light.strip", "valueKey": "color_name"},
     {"action": "light.turn_on", "target": {"entity_id": "light.strip"},
      "data": {"color_name": "{{ ['red', 'orange', states('input_select.colour_3'), [0, 0, 255]]"
                             "[(states('counter.index') | int(0))] }}"}}),
    ("MUX of words to a list helper", {"type": "mux", "sourceA": "2", "inputs": ["eco", "comfort", "boost"],
                                       "target": "input_select.mode"},
     {"action": "input_select.select_option", "target": {"entity_id": "input_select.mode"},
      "data": {"option": "{{ ['eco', 'comfort', 'boost'][2] }}"}}),
]


@pytest.mark.parametrize(("name", "block", "action"), BLOCKS, ids=[b[0] for b in BLOCKS])
def test_a_block_compiles_and_comes_back_as_the_same_block(hass, name, block, action):
    """Drawn by hand, compiled, read from the YAML: the same block with the same pins - and compiled again, the same
    YAML (the round trip check passes)."""
    out = _actions(hass, block)
    assert out == [action], (name, out)
    auto = {"id": "a", "alias": "Calc", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion",
                                                     "to": "on"}], "actions": out}
    back = _drawn(hass, auto)[0]
    want = {k: block[k] for k in FIELDS if k in block}
    if block["type"] == "mux" and "valueKey" not in block:
        want["valueKey"] = "option"
    got = {k: back[k] for k in FIELDS if k in back}
    assert got == want, (name, got)
    again = ast_to_yaml(hass, {"id": "n2", "name": "Calc", "level": "automation",
                                "rungs": [{"id": "r", "elements": [dict(MOTION)] + [{**back, "raw": None, "sig": None}]}]})
    assert again["actions"] == out, (name, again["actions"])
    assert verify_round_trip(hass, copy.deepcopy(auto))["ok"]


def test_an_edited_mux_keeps_the_rest_of_its_call(hass):
    """A MUX read from Home Assistant, its inputs changed: the transition and the other keys of the call stay."""
    auto = {"id": "a", "alias": "Colours", "triggers": [{"trigger": "time_pattern", "seconds": "/10"}], "actions": [
        {"action": "light.turn_on", "target": {"entity_id": "light.strip"}, "continue_on_error": True, "alias": "colour",
         "data": {"transition": 2, "color_name": "{{ ['red', 'blue'][states('counter.k') | int] }}"}}]}
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    mux = net["rungs"][0]["elements"][-1]
    assert (mux["type"], mux["sourceA"], mux["inputs"], mux["valueKey"]) == ("mux", "counter.k", ["red", "blue"],
                                                                             "color_name"), mux
    assert ast_to_yaml(hass, copy.deepcopy(net))["actions"] == auto["actions"]  # untouched: as the file had it
    mux["inputs"] = ["red", "blue", "lime"]
    step = ast_to_yaml(hass, net)["actions"][0]
    assert step == {"action": "light.turn_on", "target": {"entity_id": "light.strip"}, "continue_on_error": True,
                    "alias": "colour", "data": {"transition": 2, "color_name":
                                                "{{ ['red', 'blue', 'lime'][(states('counter.k') | int(0))] }}"}}, step


def test_math_with_a_constant_comes_back_as_math(hass):
    """It came back as a MOVE of {{ (states('input_number.a') | float(0)) + (5) }}: two entities were needed."""
    auto = {"id": "a", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion"}],
            "actions": [{"action": "input_number.set_value", "target": {"entity_id": "input_number.c"},
                         "data": {"value": "{{ (states('input_number.a') | float(0)) + (5) }}"}}]}
    el = _drawn(hass, auto)[0]
    assert (el["type"], el["sourceA"], el["sourceB"], el["target"]) == ("math_add", "input_number.a", "5",
                                                                        "input_number.c"), el


@pytest.mark.parametrize(("text", "block"), [
    ("{{ states('counter.step') | int % 4 }}", {"type": "math_mod", "sourceA": "counter.step", "sourceB": "4"}),
    ("{{ ['red', 'blue'][states('counter.k') | int] }}", {"type": "mux", "sourceA": "counter.k",
                                                          "inputs": ["red", "blue"]}),
    ("{{ range(1, 6 + 1) | random }}", {"type": "math_rand", "sourceA": "1", "sourceB": "6", "notSame": False}),
    # the words of an entity id are words, not the entity: they keep their quotes (the review of the release)
    ("{{ ['media_player.kitchen', 'red'][states('counter.k') | int] }}",
     {"type": "mux", "sourceA": "counter.k", "inputs": ["'media_player.kitchen'", "red"]}),
    # not blocks: another entity's value left out, one input, an entity-shaped expression, any other template
    ("{{ range(0, 9 + 1) | reject('eq', states('counter.other') | int(None)) | list | random }}", None),
    ("{{ ['red'][0] }}", None),
    ("{{ (trigger.idx) + (2) }}", None),
    ("{{ states('input_number.a') | float * 2 }}", None),
])
def test_what_is_read_as_a_block(text, block):
    assert calc_block(text, "counter.index") == block


@pytest.mark.parametrize(("block", "says"), [
    ({"type": "math_mod", "sourceA": "counter.step", "sourceB": "0", "target": "counter.step"}, "division by 0"),
    ({"type": "math_rand", "sourceA": "9", "sourceB": "0", "target": "counter.index"}, "IN1 (9) is the smallest"),
    ({"type": "math_rand", "sourceA": "0", "sourceB": "", "target": "counter.index"}, "IN2 needs a whole number"),
    ({"type": "math_rand", "sourceA": "0", "sourceB": "9", "target": "light.strip"}, "OUT is the variable"),
    ({"type": "mux", "sourceA": "0", "inputs": ["red"], "target": "light.strip"}, "two inputs or more"),
    ({"type": "mux", "sourceA": "0", "inputs": ["red", ""], "target": "light.strip"}, "none is empty"),
    ({"type": "mux", "sourceA": "3", "inputs": ["red", "blue"], "target": "light.strip"}, "inputs are 0 to 1"),
    ({"type": "mux", "sourceA": "", "inputs": ["red", "blue"], "target": "light.strip"}, "K, the number"),
    ({"type": "mux", "sourceA": "0", "inputs": ["5", "10"], "target": "switch.pump"}, "a switch has no value"),
    # [ADDED 2026-11-18] The review of the release (RULE 41): what Home Assistant would refuse only when it runs.
    ({"type": "math_rand", "sourceA": "0.5", "sourceB": "9", "target": "counter.index"}, "IN1 is a whole number, not 0.5"),
    ({"type": "math_rand", "sourceA": "0", "sourceB": "9.5", "target": "counter.index"}, "IN2 is a whole number, not 9.5"),
    ({"type": "math_rand", "sourceA": "3", "sourceB": "3", "target": "counter.index", "notSame": True},
     "from 3 to 3 there is one number"),
    ({"type": "mux", "sourceA": "1.5", "inputs": ["red", "blue"], "target": "light.strip"}, "K is a whole number"),
])
def test_a_block_that_cannot_run_does_not_compile(hass, block, says):
    with pytest.raises(ValueError, match=re.escape(says)):
        _actions(hass, block)


def test_a_rand_of_one_number_without_the_tick_is_that_number(hass):
    """From 3 to 3 with no "never the one OUT holds": always 3 - nothing to refuse."""
    assert _actions(hass, {"type": "math_rand", "sourceA": "3", "sourceB": "3", "target": "counter.index"})[0][
        "data"]["value"] == "{{ range(3, 3 + 1) | random }}"


def test_an_edited_mux_of_the_words_of_entity_ids_keeps_the_words(hass):
    """The review of the release: a text helper given speakers' NAMES in turn - words that look like entity ids. Edited,
    they were read as the speakers themselves, and the helper was given states('media_player.kitchen') - playing."""
    auto = {"id": "a", "alias": "Speakers", "triggers": [{"trigger": "time_pattern", "minutes": "/5"}], "actions": [
        {"action": "input_text.set_value", "target": {"entity_id": "input_text.speaker"},
         "data": {"value": "{{ ['media_player.kitchen', 'media_player.living_room'][states('counter.k') | int] }}"}}]}
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    mux = net["rungs"][0]["elements"][-1]
    assert (mux["type"], mux["inputs"]) == ("mux", ["'media_player.kitchen'", "'media_player.living_room'"]), mux
    assert ast_to_yaml(hass, copy.deepcopy(net))["actions"] == auto["actions"]  # untouched: as the file had it
    mux["sourceA"] = "counter.j"
    value = ast_to_yaml(hass, net)["actions"][0]["data"]["value"]
    assert value == "{{ ['media_player.kitchen', 'media_player.living_room'][(states('counter.j') | int(0))] }}", value


def test_a_block_of_the_math_group_in_a_scene_is_refused(hass):
    """A scene holds fixed states: a RAND in it was left out without a word."""
    net = {"id": "s", "name": "Scene", "level": "scene", "rungs": [{"id": "r", "elements": [
        {"id": "e1", "type": "math_rand", "sourceA": "0", "sourceB": "9", "target": "counter.index"}]}]}
    with pytest.raises(ValueError, match="A scene sets fixed states"):
        ast_to_yaml(hass, net)


def test_a_rung_says_what_each_block_sets(hass):
    auto = {"id": "a", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
            "actions": _actions(hass, *[b for _n, b, _a in BLOCKS[3:7]])}
    said = yaml_to_ast(hass, auto)["rungs"][0]["comment"]
    assert said.startswith("When motion turns on, then set step to step mod 4 and set index to a random number from 0 to "
                           "9 and set r to a random number from low to high, never the one it holds and set strip color "
                           "to input index of red, orange, colour 3, [0, 0, 255]"[:157]), said


def test_every_other_block_keeps_its_fingerprint():
    """The inputs of a MUX and the tick of a RAND are fingerprinted only where a block has them: a NET saved before
    reads as untouched, its nodes written back as they were."""
    el = {"type": "move", "source": "50", "target": "light.kitchen", "valueKey": "brightness_pct", "raw": {}}
    assert element_sig(el) == "|".join(f"{k}={el.get(k, '')}" for k in SIG_FIELDS)
    rand = {"type": "math_rand", "sourceA": "0", "sourceB": "9", "target": "counter.i", "notSame": False}
    assert element_sig(rand) != element_sig({**rand, "notSame": True})
    mux = {"type": "mux", "sourceA": "0", "inputs": ["red", "blue"], "target": "light.s"}
    assert element_sig(mux) != element_sig({**mux, "inputs": ["red", "lime"]})


# ---------------------------------------------------------------- run by Home Assistant
@pytest.fixture
async def counters(hass, libi):  # noqa: F811
    strip = HouseLight(STRIP, {ColorMode.COLOR_TEMP, ColorMode.XY})
    setup_test_component_platform(hass, "light", [strip])
    assert await async_setup_component(hass, "light", {"light": {"platform": "test"}})
    assert await async_setup_component(hass, "counter", {"counter": {"index": {}, "step": {}}})
    assert await async_setup_component(hass, "input_number", {"input_number": {
        "low": {"min": 0, "max": 100, "initial": 2}, "high": {"min": 0, "max": 100, "initial": 5},
        "c": {"min": 0, "max": 100, "step": 0.01}}})
    assert await async_setup_component(hass, "input_select", {"input_select": {
        f"colour_{i}": {"options": ["red", "orange", "yellow", "lime"], "initial": c}
        for i, c in enumerate(("red", "orange", "yellow", "lime"), start=1)}})
    hass.states.async_set("binary_sensor.motion", "off")
    await home_assistant_files(hass, libi, automations=[])
    await hass.async_block_till_done()
    return strip


async def _run(hass, times) -> None:
    for _ in range(times):
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()
        hass.states.async_set("binary_sensor.motion", "off")
        await hass.async_block_till_done()


async def test_rand_mod_and_mux_run_in_home_assistant(hass, counters, libi, hass_ws_client, hass_client, caplog):  # noqa: F811
    """RAND of two variables (2 to 5), never the one it holds, 40 runs: always in the range, never twice in a row, every
    number of it; MUX gives the strip the colour of the list helper the counter points at; CTU then MOD keep the step
    0 to 3 - the user's four colours one after another."""
    client, http = await hass_ws_client(hass), await hass_client()
    net = _net({"type": "math_rand", "sourceA": "input_number.low", "sourceB": "input_number.high",
                "target": "counter.index", "notSame": True},
               {"type": "mux", "sourceA": "counter.step",
                "inputs": [f"input_select.colour_{i}" for i in range(1, 5)], "target": STRIP, "valueKey": "color_name"},
               {"type": "ctu", "source": "counter.step", "value": "1"},
               {"type": "math_mod", "sourceA": "counter.step", "sourceB": "4", "target": "counter.step"})
    plan, done = await save(client, http, [net])
    assert done and done["status"] == "ok", (plan, done)
    written = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))[0]
    assert [s["action"] for s in written["actions"]] == ["counter.set_value", "light.turn_on", "counter.increment",
                                                         "counter.set_value"], written["actions"]
    seen, colours = [], []
    for _ in range(40):
        await _run(hass, 1)
        seen.append(int(hass.states.get("counter.index").state))
        colours.append(counters.sent[-1]["xy_color"])
    assert set(seen) == {2, 3, 4, 5}, seen
    assert all(a != b for a, b in zip(seen, seen[1:], strict=False)), seen
    names = ["red", "orange", "yellow", "lime"]
    want = [color_util.color_RGB_to_xy(*color_util.color_name_to_rgb(names[i % 4])) for i in range(40)]
    assert colours == want, colours[:6]
    assert hass.states.get("counter.step").state == "0"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "Error" in r.getMessage()]


async def test_a_rand_of_one_number_with_the_tick_fails_loudly(hass, counters, libi, hass_ws_client, hass_client):  # noqa: F811
    """From 3 to 3, never the one it holds - 3: nothing is left. Given as numbers it does not compile (above); read from
    two variables that hold 3 only when it runs, Home Assistant refuses the action, and nothing is set: a number outside
    the range is never written."""
    client, http = await hass_ws_client(hass), await hass_client()
    for name in ("low", "high"):
        await hass.services.async_call("input_number", "set_value", {"entity_id": f"input_number.{name}", "value": 3},
                                       blocking=True)
    await hass.services.async_call("counter", "set_value", {"entity_id": "counter.index", "value": 3}, blocking=True)
    plan, done = await save(client, http, [_net({"type": "math_rand", "sourceA": "input_number.low",
                                                 "sourceB": "input_number.high", "target": "counter.index",
                                                 "notSame": True})])
    assert done and done["status"] == "ok", (plan, done)
    await _run(hass, 1)
    assert hass.states.get("automation.calc").attributes.get("last_triggered") is not None  # it ran
    assert hass.states.get("counter.index").state == "3"


# ---------------------------------------------------------------- EVERY, a time pattern
EVERY_AUTO = {"id": "a", "alias": "Colours", "triggers": [{"trigger": "time_pattern", "seconds": "/10", "id": "tick",
                                                         "alias": "pulse"}],
              "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.strip"},
                           "data": {"color_name": "red"}}]}


def test_every_drawn_by_hand_edited_and_read_back(hass):
    """EVERY drawn by hand was a state trigger of an entity "time pattern", which Home Assistant refuses; edited from 10
    to 5 seconds it was written as it had been. Now both are the time pattern the block holds - its id and alias kept."""
    net = yaml_to_ast(hass, copy.deepcopy(EVERY_AUTO))
    every = net["rungs"][0]["elements"][0]
    assert (every["type"], every["sourceA"], every["sourceB"]) == ("cmp_eq", "time pattern", "seconds=/10"), every
    assert net["rungs"][0]["comment"] == "Every 10 seconds, then set strip color to red", net["rungs"][0]["comment"]
    every["sourceB"] = "seconds=/5"
    assert ast_to_yaml(hass, net)["triggers"] == [{"trigger": "time_pattern", "seconds": "/5", "id": "tick",
                                                   "alias": "pulse"}]
    every["sourceB"] = "hours=* minutes=0"
    assert ast_to_yaml(hass, net)["triggers"] == [{"trigger": "time_pattern", "id": "tick", "alias": "pulse",
                                                   "hours": "*", "minutes": 0}]
    drawn = _net({"type": "move", "mode": "value", "source": "red", "target": "light.strip", "valueKey": "color_name"})
    drawn["rungs"][0]["elements"][0] = {"id": "e0", "type": "cmp_eq", "sourceA": "time pattern", "sourceB": "minutes=/1",
                                        "isTrigger": True}
    out = ast_to_yaml(hass, drawn)
    assert out["triggers"] == [{"trigger": "time_pattern", "minutes": "/1"}], out["triggers"]  # one trigger: no id
    assert yaml_to_ast(hass, out)["rungs"][0]["comment"].startswith("Every minute, then"), out


@pytest.mark.parametrize(("source_b", "trigger", "says"), [
    ("every 10", True, "is no time pattern"),
    ("seconds=/10 seconds=/5", True, "is no time pattern"),
    ("seconds=/10", False, "it is a trigger, never a check"),
])
def test_an_every_that_cannot_start_its_rung_does_not_compile(hass, source_b, trigger, says):
    net = _net({"type": "coil", "label": "light.strip"})
    every = {"id": "e9", "type": "cmp_eq", "sourceA": "time pattern", "sourceB": source_b, "isTrigger": trigger}
    if trigger:
        net["rungs"][0]["elements"][0] = every
    else:
        net["rungs"][0]["elements"].insert(1, every)
    with pytest.raises(ValueError, match=re.escape(says)):
        ast_to_yaml(hass, net)


# ---------------------------------------------------------------- IN3, IN4 ... of ADD, SUB, MUL and DIV
MORE = [
    ("ADD of four", {"type": "math_add", "sourceA": "input_number.a", "sourceB": "5", "more": ["sensor.x", "2.5"],
                     "target": "input_number.c"},
     "{{ (states('input_number.a') | float(0)) + (5) + (states('sensor.x') | float(0)) + (2.5) }}"),
    ("MUL of three", {"type": "math_mul", "sourceA": "2", "sourceB": "3", "more": ["input_number.n"], "target": "input_number.c"},
     "{{ (2) * (3) * (states('input_number.n') | float(0)) }}"),
    ("DIV of three", {"type": "math_div", "sourceA": "sensor.p", "sourceB": "1000", "more": ["input_number.n"],
                      "target": "input_number.kw", "precision": 1, "fallback": 0},
     "{{ (((states('sensor.p') | float(0)) / (1000) / (states('input_number.n') | float(0))) | round(1)) if (1000) != 0 and "
     "(states('input_number.n') | float(0)) != 0 else 0 }}"),
]


@pytest.mark.parametrize(("name", "block", "value"), MORE, ids=[m[0] for m in MORE])
def test_math_of_more_inputs_compiles_and_comes_back(hass, name, block, value):
    """The user (2026-11-18): IN3, IN4, IN5 ... added in the Inspector. A + B + C, A / B / C - each divisor not 0 - and
    read back as the same block, its IN3 ... in more."""
    out = _actions(hass, block)
    assert out[0]["data"]["value"] == value, (name, out)
    auto = {"id": "a", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
            "actions": out}
    back = _drawn(hass, auto)[0]
    assert {k: back.get(k) for k in ("type", "sourceA", "sourceB", "more")} == \
        {k: block.get(k) for k in ("type", "sourceA", "sourceB", "more")}, (name, back)
    assert verify_round_trip(hass, copy.deepcopy(auto))["ok"]


@pytest.mark.parametrize(("block", "says"), [
    ({"type": "math_mod", "sourceA": "counter.step", "sourceB": "4", "more": ["2"], "target": "counter.step"},
     "MOD to counter.step: it takes two inputs"),
    ({"type": "math_rand", "sourceA": "0", "sourceB": "9", "more": ["3"], "target": "counter.index"},
     "RAND to counter.index: it takes two inputs"),
    ({"type": "math_add", "sourceA": "1", "sourceB": "2", "more": [""], "target": "input_number.c"},
     "MATH to input_number.c: IN3 needs a number or a variable"),
])
def test_an_input_too_many_or_empty_does_not_compile(hass, block, says):
    with pytest.raises(ValueError, match=re.escape(says)):
        _actions(hass, block)


def test_a_rung_says_every_input(hass):
    auto = {"id": "a", "alias": "x", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
            "actions": _actions(hass, MORE[0][1])}
    said = yaml_to_ast(hass, auto)["rungs"][0]["comment"]
    assert said == "When motion turns on, then set c to a plus 5 plus x plus 2.5", said


async def test_math_of_more_inputs_runs_in_home_assistant(hass, counters, libi, hass_ws_client, hass_client):  # noqa: F811
    """2 + 3 + low (2), into an input_number: 7. 2 / 3 / low: 0.33."""
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(
        {"type": "math_add", "sourceA": "2", "sourceB": "3", "more": ["input_number.low"], "target": "input_number.c"})])
    assert done and done["status"] == "ok", (plan, done)
    await _run(hass, 1)
    assert float(hass.states.get("input_number.c").state) == 7.0
