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
# [ADDED v3.96.0 | 2026-11-18] Purpose: The user's request to the AI chat (2026-11-18): four colours chosen on a card,
#   the next one every 10 seconds, an on/off button on the card, and a random button - a colour of its own every 10
#   seconds, never the one lit now - "and make the AI use RAND, MOD and MUX for it". Through LIBI's real plan and build
#   routes, the model's answers canned as LIBI's prompts ask; drawn as the Math group's blocks; saved through Home
#   Assistant's config API and run with the clock moved on. A colour name Home Assistant does not know goes back to the
#   model, and a list of such names is said to the user.
# [CHANGED v3.96.2 | 2026-11-18] Purpose: The review of the release (RULE 41): a list helper read as the colour on
#   its own is checked too, not only one inside a MUX.
"""The AI chat's colours in turn or at random: RAND, MOD and MUX blocks, run by Home Assistant."""
import copy
import json
import logging
import re
from datetime import timedelta
from unittest.mock import patch

import pytest
import yaml
from homeassistant.components.light import ColorMode
from homeassistant.setup import async_setup_component
from homeassistant.util import color as color_util
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, \
    setup_test_component_platform

from custom_components.libi import ai
from custom_components.libi.const import (AI_MODE_CLOUD, CONF_AI_MODE, CONF_CLOUD_API_KEY, CONF_CLOUD_MODEL,
                                          CONF_CLOUD_PROVIDER, DOMAIN)

from .save_helpers import home_assistant_files, save
from .test_move_lights_live import STRIP, HouseLight

REQUEST = ("An automation: I choose 4 colours on a card, and every 10 seconds the LED strip changes to the next colour, "
           "one after the other. An on/off button for the automation on the card. And another button for random "
           "colours, not related to the colours chosen on the card: it picks a colour by itself every 10 seconds, never "
           "the colour lit now.")
# Each its own colour on an xy light such as the house's strip: purple and magenta are one there, as green and lime.
PALETTE = ["red", "orange", "yellow", "lime", "cyan", "blue", "purple", "pink", "white", "turquoise"]
COLOURS = [f"input_select.led_colour_{i}" for i in range(1, 5)]


def _role(rid, label, purpose, domains, keywords):
    return {"id": rid, "label": label, "purpose": purpose, "domains": domains, "device_classes": [],
            "keywords": keywords, "area_keywords": []}


PLAN = {
    "requirements": [
        {"id": "four_colours", "text": "I choose 4 colours on a card", "kind": "card"},
        {"id": "in_turn", "text": "every 10 seconds the next colour, one after the other", "kind": "time"},
        {"id": "at_random", "text": "a random button: a colour of its own every 10 seconds, never the one lit now",
         "kind": "other"}],
    "reply": "Pick the LED strip; LIBI makes the four colour lists, the random switch and two counters it uses itself.",
    "intent": "create", "target_net": "", "level": "automation", "name": "LED colours",
    "roles": [_role("strip", "LED strip", "target", ["light"], ["led", "strip"])]
    + [_role(f"colour_{i}", f"Colour {i}", "condition", ["input_select"], ["colour"]) for i in range(1, 5)]
    + [_role("random_mode", "Random colours", "condition", ["input_boolean"], ["random"]),
       _role("step", "Colour step", "measure", ["counter"], ["step"]),
       _role("index", "Colour index", "measure", ["counter"], ["index"])],
    "questions": [],
    "new_helpers": [{"role": f"colour_{i}", "domain": "input_select", "name": f"LED colour {i}",
                     "settings": {"options": PALETTE, "initial": PALETTE[i]}} for i in range(1, 5)]
    + [{"role": "random_mode", "domain": "input_boolean", "name": "LED random colours", "settings": {}},
       {"role": "step", "domain": "counter", "name": "LED colour step", "settings": {}},
       {"role": "index", "domain": "counter", "name": "LED colour index", "settings": {}}],
}

MUX_IN_TURN = ("{{ [states('role:colour_1'), states('role:colour_2'), states('role:colour_3'), states('role:colour_4')]"
               "[(states('role:step') | int(0))] }}")


def _config(palette=PALETTE):
    mux_random = "{{ [" + ", ".join(f"'{c}'" for c in palette) + "][(states('role:index') | int(0))] }}"
    return {
        "mode": "queued",
        "triggers": [{"trigger": "time_pattern", "seconds": "/10", "id": "in_turn"},
                     {"trigger": "time_pattern", "seconds": "/10", "id": "at_random"},
                     {"trigger": "state", "entity_id": "role:enabled", "to": "off", "id": "switched_off"}],
        "conditions": [],
        "actions": [{"choose": [
            {"conditions": [{"condition": "trigger", "id": "in_turn"},
                            {"condition": "state", "entity_id": "role:enabled", "state": "on"},
                            {"condition": "state", "entity_id": "role:random_mode", "state": "off"}],
             "sequence": [
                 {"action": "light.turn_on", "target": {"entity_id": "role:strip"}, "data": {"color_name": MUX_IN_TURN}},
                 {"action": "counter.increment", "target": {"entity_id": "role:step"}},
                 {"action": "counter.set_value", "target": {"entity_id": "role:step"},
                  "data": {"value": "{{ (states('role:step') | int(0)) % 4 }}"}}]},
            {"conditions": [{"condition": "trigger", "id": "at_random"},
                            {"condition": "state", "entity_id": "role:enabled", "state": "on"},
                            {"condition": "state", "entity_id": "role:random_mode", "state": "on"}],
             "sequence": [
                 {"action": "counter.set_value", "target": {"entity_id": "role:index"},
                  "data": {"value": "{{ range(0, " + str(len(palette) - 1) + " + 1) | reject('eq', states('role:index') "
                                    "| int(None)) | list | random }}"}},
                 {"action": "light.turn_on", "target": {"entity_id": "role:strip"}, "data": {"color_name": mux_random}}]},
            {"conditions": [{"condition": "trigger", "id": "switched_off"}],
             "sequence": [{"action": "light.turn_off", "target": {"entity_id": "role:strip"}}]}]}],
    }


def _build(config):
    return {"reply": "Every 10 seconds the strip takes the next of your four colours, or a random one.",
            "level": "automation", "name": "LED colours",
            "description": "Four colours from the card in turn every 10 seconds, or random ones; an on/off switch.",
            "config": json.dumps(config), "ui_card": "", "notes": [],
            "covers": [{"requirement": "four_colours", "trigger_id": "", "how": "The card has the four colour lists."},
                       {"requirement": "in_turn", "trigger_id": "in_turn", "how": "Every 10 seconds the next colour."},
                       {"requirement": "at_random", "trigger_id": "at_random", "how": "A random colour, never the one lit."}]}


@pytest.fixture
async def house(hass, config_dir, monkeypatch):
    # The clock is moved on (freezer): aiohttp's access log cannot read the local time then, and logs an error.
    monkeypatch.setattr(logging.getLogger("aiohttp.access"), "disabled", True)
    strip = HouseLight(STRIP, {ColorMode.COLOR_TEMP, ColorMode.XY})
    setup_test_component_platform(hass, "light", [strip])
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "light", {"light": {"platform": "test"}})
    assert await async_setup_component(hass, "input_select", {"input_select": {
        **{f"led_colour_{i}": {"name": f"LED colour {i}", "options": PALETTE, "initial": PALETTE[i]} for i in range(1, 5)},
        "led_bad_colours": {"name": "LED bad colours", "options": ["ruby", "red"]}}})
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {
        "led_random_colours": {"name": "LED random colours"}, "led_colours_enabled": {"name": "LED colours - enabled"}}})
    assert await async_setup_component(hass, "counter", {"counter": {
        "led_colour_step": {"name": "LED colour step"}, "led_colour_index": {"name": "LED colour index"}}})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_AI_MODE: AI_MODE_CLOUD, CONF_CLOUD_PROVIDER: "gemini",
                                                 CONF_CLOUD_API_KEY: "sk-test", CONF_CLOUD_MODEL: "gemini-x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await home_assistant_files(hass, config_dir, automations=[])
    await hass.async_block_till_done()
    return strip


SELECTED = {"strip": [STRIP], "random_mode": ["input_boolean.led_random_colours"], "step": ["counter.led_colour_step"],
            "index": ["counter.led_colour_index"], **{f"colour_{i}": [COLOURS[i - 1]] for i in range(1, 5)}}


async def _plan(client):
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(PLAN)):
        await client.send_json_auto_id({"type": "libi/ai_plan", "messages": [{"role": "user", "content": REQUEST}]})
        planned = await client.receive_json()
    assert planned["success"], planned
    plan = planned["result"]["plan"]
    # The user says yes to LIBI's own on/off switch - the chat puts its role in the plan, as libi-ai.js does - and no to
    # the messages: a message when it starts would come every 10 seconds.
    question = next(q for q in plan["questions"] if q["id"] == ai.ENABLE_QUESTION)
    plan["roles"].append({**question["adds"]["role"], "variable": True})
    answers = {q["id"]: ("Yes" if q["id"] == ai.ENABLE_QUESTION else "No" if "No" in q["choices"] else "Nothing")
               for q in plan["questions"] if q.get("choices")}
    return plan, answers


async def _build_with(client, plan, answers, *raws, selections=None):
    with patch.object(ai, "async_llm_json", side_effect=[copy.deepcopy(r) for r in raws]) as model:
        await client.send_json_auto_id({"type": "libi/ai_build", "messages": [{"role": "user", "content": REQUEST}],
                                        "plan": plan, "selections": {**SELECTED, ai.ENABLE_ROLE:
                                                                     ["input_boolean.led_colours_enabled"],
                                                                     **(selections or {})},
                                        "answers": answers})
        built = await client.receive_json()
    assert built["success"], built
    return built["result"], model


def _blocks(rung):
    return [(e["type"], e.get("valueKey") or ("not the one it holds" if e.get("notSame") else ""))
            for e in rung["elements"]]


async def test_the_ai_chat_draws_colours_in_turn_and_at_random_with_rand_mod_and_mux(hass, house, config_dir,
                                                                                    hass_ws_client, hass_client, freezer):
    client = await hass_ws_client(hass)
    plan, answers = await _plan(client)
    res, model = await _build_with(client, plan, answers, _build(_config()))
    assert res["ok"] and model.call_count == 1 and not res["notes"], (res.get("errors"), res.get("notes"), res.get("repaired"))
    assert res["round_trip"]["ok"], res["round_trip"]
    rungs = res["net"]["rungs"]
    assert [_blocks(r) for r in rungs] == [
        [("cmp_eq", ""), ("contact_no", ""), ("contact_nc", ""), ("mux", "color_name"), ("ctu", ""), ("math_mod", "")],
        [("cmp_eq", ""), ("contact_no", ""), ("contact_no", ""), ("math_rand", "not the one it holds"),
         ("mux", "color_name")],
        [("contact_nc", ""), ("coil_r", "")]], [_blocks(r) for r in rungs]
    rand = rungs[1]["elements"][3]
    assert (rand["sourceA"], rand["sourceB"], rand["target"]) == ("0", "9", "counter.led_colour_index"), rand
    mux = rungs[0]["elements"][3]
    assert (mux["sourceA"], mux["inputs"], mux["target"]) == ("counter.led_colour_step", COLOURS, STRIP), mux
    said = (rungs[0]["comment"], rungs[1]["comment"])
    assert said[0].startswith("Every 10 seconds, if led colours enabled is on and led random colours is off,"), said
    assert "a random number from 0 to 9, never the one it holds" in said[1], said
    card = yaml.safe_load(res["card_yaml"])
    shown = [row.get("entity") for row in card["entities"] if row.get("entity")]
    assert shown == ["input_boolean.led_colours_enabled", *COLOURS, "input_boolean.led_random_colours", STRIP], shown

    # SAVE & COMPILE through Home Assistant, then the card is used and the clock moves on.
    net = dict(res["net"], id="n1", ha_id=None)
    done = (await save(client, await hass_client(), [net]))[1]
    assert done and done["status"] == "ok", done

    async def tick(n):
        colours = []
        for _ in range(n):
            now = dt_util.utcnow()
            freezer.move_to(now + timedelta(seconds=10 - now.second % 10, microseconds=-now.microsecond))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
            last = house.sent[-1] if house.sent else {}
            colours.append("off" if last.get("off") else next(
                (c for c in PALETTE if color_util.color_RGB_to_xy(*color_util.color_name_to_rgb(c)) == last.get("xy_color")), "-"))
        return colours

    assert await tick(2) == ["-", "-"]  # switched off: nothing
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.led_colours_enabled"},
                                   blocking=True)
    assert await tick(6) == ["orange", "yellow", "lime", "cyan", "orange", "yellow"]
    await hass.services.async_call("input_select", "select_option", {"entity_id": COLOURS[0], "option": "blue"},
                                   blocking=True)
    assert await tick(3) == ["lime", "cyan", "blue"]  # a colour changed on the card is the one used
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.led_random_colours"},
                                   blocking=True)
    xy = {color_util.color_RGB_to_xy(*color_util.color_name_to_rgb(c)) for c in PALETTE}
    assert len(xy) == len(PALETTE)  # the test tells each colour by what the strip is sent
    random_colours = await tick(40)
    assert all(a != b for a, b in zip(random_colours, random_colours[1:], strict=False)), random_colours
    assert set(random_colours) <= set(PALETTE) and len(set(random_colours)) >= 5, random_colours
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": "input_boolean.led_colours_enabled"},
                                   blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(STRIP).state == "off"
    assert await tick(3) == ["off", "off", "off"]  # off stops it at once, and nothing starts again
    # Unloaded as Home Assistant does: its time pattern's listener is not left behind with the clock moved on.
    await hass.services.async_call("automation", "turn_off", {"entity_id": "all"}, blocking=True)
    await hass.async_block_till_done()


async def test_a_colour_home_assistant_does_not_know_goes_back_to_the_model(hass, house, hass_ws_client):
    """"ruby" is no colour name Home Assistant knows: the strip would turn white. The model is told, and its second
    answer is the one drawn."""
    client = await hass_ws_client(hass)
    plan, answers = await _plan(client)
    bad = _config(["ruby" if c == "red" else c for c in PALETTE])
    res, model = await _build_with(client, plan, answers, _build(bad), _build(_config()))
    assert res["ok"] and model.call_count == 2, res.get("errors")
    assert any('"ruby" is no colour name Home Assistant knows' in p for p in res["repaired"]), res["repaired"]
    sent = model.call_args_list[1].args[3][-1]["content"]
    assert "ruby" in sent and "English name" in sent, sent[-400:]


async def test_a_list_of_names_home_assistant_does_not_know_is_said(hass, house, hass_ws_client):
    """A list helper the user has, with "ruby" among its colours: the model cannot change it, so the user is told."""
    client = await hass_ws_client(hass)
    plan, answers = await _plan(client)
    res, _model = await _build_with(client, plan, answers, _build(_config()),
                                    selections={"colour_1": ["input_select.led_bad_colours"]})
    assert res["ok"], res.get("errors")
    assert any("LED bad colours holds colours Home Assistant does not know by name (ruby)" in n for n in res["notes"]), \
        res["notes"]


async def test_a_list_read_as_the_colour_on_its_own_is_said_too(hass, house):
    """The review of the release (RULE 41): a list helper read as the colour by itself - {{ states('...') }}, one
    colour chosen on the card - was never looked at; only the lists inside a MUX were."""
    def light(value):
        return {"actions": [{"action": "light.turn_on", "target": {"entity_id": STRIP}, "data": {"color_name": value}}]}
    notes = ai.colour_notes(hass, light("{{ states('input_select.led_bad_colours') }}"))
    assert notes and "LED bad colours holds colours Home Assistant does not know by name (ruby)" in notes[0], notes
    assert ai.colour_notes(hass, light(f"{{{{ states('{COLOURS[0]}') }}}}")) == []  # every name of it is a colour
    assert ai.colour_problems(light("{{ states('input_select.led_bad_colours') }}")) == []  # the helper's, not the model's


def test_the_palettes_the_prompts_name_are_colours_of_their_own():
    """purple and magenta are one colour on an xy light: a palette "never the one shown" picks from holds one."""
    for text in (ai.BUILD_SYSTEM, ai.PLAN_SYSTEM):
        flat = " ".join(text.split())  # the prompt wraps its lines
        assert re.search(r"red, orange, yellow, lime, cyan, blue, purple, pink, white, turquoise", flat), flat[:200]
        assert "magenta, pink" not in flat
    listed = ["red", "orange", "yellow", "lime", "cyan", "blue", "purple", "pink", "white", "turquoise"]
    assert len({color_util.color_RGB_to_xy(*color_util.color_name_to_rgb(c)) for c in listed}) == len(listed)


def test_the_build_prompt_tells_the_forms_of_rand_mod_and_mux():
    for form in ("range(<low>, <high> + 1) | random", "| reject('eq', states('role:<it>') | int(None)) | list | random",
                 "(states('role:<a>') | int(0)) % <n>", "[(states('role:<k>') | int(0))]", '"ids "in_turn" and "at_random"'
                 [1:], "never translated"):
        assert form in ai.BUILD_SYSTEM, form
    assert "is a counter helper" in ai.PLAN_SYSTEM and "English as its" in ai.PLAN_SYSTEM
