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
# [ADDED v3.96.0 | 2026-11-17] Purpose: The user (2026-11-17): "how can you check that a device that has this works, and
#   that I can control the colour from the dashboard?". Each NET is drawn as the panel draws it, saved through Home
#   Assistant's own config API, and run by Home Assistant on lights made like the house's: the ZHA LED strip (xy and
#   colour temperature), a Tuya kind of strip (hs, effects), a Reolink floodlight (brightness only) and a ZHA relay (on
#   and off). The dashboard is what it sends: input_select.select_option, input_number.set_value, input_text.set_value
#   and a light's colour wheel (light.turn_on). It found that a contact drawn on a dashboard helper was a trigger
#   to: "on", which a helper never reaches - "when I pick a colour" never ran.
"""A MOVE saved by LIBI, run by Home Assistant: dimming, a colour from the palette, and the values set on a dashboard."""
import copy
import logging
import re
from pathlib import Path

import pytest
import yaml
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN, ATTR_EFFECT, ATTR_HS_COLOR, ATTR_RGB_COLOR, ATTR_XY_COLOR, ColorMode,
    LightEntity, LightEntityFeature,
)
from homeassistant.setup import async_setup_component
from homeassistant.util import color as color_util
from pytest_homeassistant_custom_component.common import setup_test_component_platform

from custom_components.libi.libi_to_yaml import ast_to_yaml, verify_round_trip
from custom_components.libi.yaml_to_libi import NEVER_ON_DOMAINS, VALUE_DOMAINS, yaml_to_ast

from .save_helpers import home_assistant_files, save
from .test_websocket import libi  # noqa: F401 - the fixture

PANEL = Path(__file__).resolve().parents[1] / "custom_components" / "libi" / "frontend" / "libi-panel.js"
STRIP = "light.led_strip_outdoor_kitchen"     # ZHA: color_temp and xy, as in the house
TUYA = "light.led_strip_tuya"                 # a Tuya or WLED kind of strip: hs, color_temp and effects
FLOOD = "light.salon_floodlight"              # Reolink floodlight, the Tuya ceiling fan light: brightness only
RELAY = "light.light_kitchen_1"               # the ZHA wall switches: on and off only
NOT_A_VALUE = ["unavailable", "unknown"]


class HouseLight(LightEntity):
    """A light as its integration gives it to Home Assistant: it keeps what it is sent, in the colour modes it has, and
    remembers each call (sent) - what Home Assistant made of the automation's action."""

    _attr_should_poll = False

    def __init__(self, entity_id: str, modes: set, effects=None):
        self.entity_id = entity_id
        self._attr_unique_id = entity_id
        self._attr_name = entity_id.split(".")[1].replace("_", " ")
        self._attr_supported_color_modes = modes
        self._attr_color_mode = next(m for m in (ColorMode.XY, ColorMode.HS, ColorMode.BRIGHTNESS, ColorMode.ONOFF)
                                     if m in modes)
        self._attr_is_on = False
        self._attr_brightness = None if modes == {ColorMode.ONOFF} else 255
        self._attr_min_color_temp_kelvin, self._attr_max_color_temp_kelvin = 2000, 6500
        self._attr_color_temp_kelvin = 4000 if ColorMode.COLOR_TEMP in modes else None
        self._attr_xy_color = (0.3227, 0.329) if ColorMode.XY in modes else None
        self._attr_hs_color = (0.0, 0.0) if ColorMode.HS in modes else None
        if effects:
            self._attr_effect_list = list(effects)
            self._attr_effect = None
            self._attr_supported_features = LightEntityFeature.EFFECT
        self.sent: list[dict] = []

    async def async_turn_on(self, **kwargs) -> None:
        self.sent.append(dict(kwargs))
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_XY_COLOR in kwargs:
            self._attr_xy_color, self._attr_color_mode = kwargs[ATTR_XY_COLOR], ColorMode.XY
        if ATTR_HS_COLOR in kwargs:
            self._attr_hs_color, self._attr_color_mode = kwargs[ATTR_HS_COLOR], ColorMode.HS
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_temp_kelvin, self._attr_color_mode = kwargs[ATTR_COLOR_TEMP_KELVIN], ColorMode.COLOR_TEMP
        if ATTR_EFFECT in kwargs:
            self._attr_effect = kwargs[ATTR_EFFECT]
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.sent.append({"off": True})
        self._attr_is_on = False
        self.async_write_ha_state()


@pytest.fixture
async def house(hass, libi):  # noqa: F811
    """The lights, the dashboard's helpers, a motion sensor, and Home Assistant's automation integration set up from
    this test's files - so a SAVE reloads it for real."""
    lights = {STRIP: HouseLight(STRIP, {ColorMode.COLOR_TEMP, ColorMode.XY}),
              TUYA: HouseLight(TUYA, {ColorMode.HS, ColorMode.COLOR_TEMP}, effects=["rainbow", "breath"]),
              FLOOD: HouseLight(FLOOD, {ColorMode.BRIGHTNESS}),
              RELAY: HouseLight(RELAY, {ColorMode.ONOFF})}
    setup_test_component_platform(hass, "light", list(lights.values()))
    assert await async_setup_component(hass, "light", {"light": {"platform": "test"}})
    assert await async_setup_component(hass, "input_number", {"input_number": {
        "dim": {"min": 0, "max": 100, "step": 1, "initial": 40},
        "kelvin": {"min": 2000, "max": 6500, "step": 100, "initial": 2700}}})
    assert await async_setup_component(hass, "input_select", {"input_select": {
        "strip_color": {"options": ["red", "orange", "blue", "lime"], "initial": "red"},
        "strip_effect": {"options": ["rainbow", "breath"], "initial": "rainbow"}}})
    assert await async_setup_component(hass, "input_text", {"input_text": {"strip_hex": {"initial": "#ffffff"}}})
    hass.states.async_set("binary_sensor.motion", "off")
    await home_assistant_files(hass, libi, automations=[])
    await hass.async_block_till_done()
    return lights


def _net(*rungs, name="Lights") -> dict:
    """A NET drawn by hand: each rung a list of blocks as the panel makes them."""
    return {"id": "n1", "name": name, "level": "automation",
            "rungs": [{"id": f"r{i}", "elements": [dict(e, id=f"e{i}_{j}") for j, e in enumerate(r)]}
                      for i, r in enumerate(rungs, start=1)]}


def _when(entity, kind="contact_p") -> dict:
    return {"type": kind, "label": entity, "isTrigger": True}


def _move(source, target, key=None) -> dict:
    return {"type": "move", "mode": "value", "source": source, "target": target, **({"valueKey": key} if key else {})}


async def _saved(hass, libi, hass_ws_client, hass_client, net) -> dict:  # noqa: F811
    """SAVE & COMPILE as the panel makes it; the automation as it reached automations.yaml."""
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [net])
    assert done and done["status"] == "ok", (plan, done)
    await hass.async_block_till_done()
    return yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))[0]


async def _dashboard(hass, domain, service, data) -> None:
    """What a dashboard card sends when the user changes a value on it."""
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


def _near(a, b, tol=2) -> bool:
    return a is not None and len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def _same_hue(shown, rgb) -> bool:
    """The colour a dashboard shows for a light is the one picked: Home Assistant shows an xy light's colour converted
    back to rgb, which is not exact (blue sent as xy shows as 11, 0, 255) - so hue and saturation, as the eye sees it."""
    (h1, s1), (h2, s2) = color_util.color_RGB_to_hs(*shown), color_util.color_RGB_to_hs(*rgb)
    return min(abs(h1 - h2), 360 - abs(h1 - h2)) <= 4 and abs(s1 - s2) <= 5


def _no_trouble(caplog) -> list:
    """What Home Assistant logged as going wrong while the automations ran: an action it refused, a colour it did not
    know (it then makes the light white), an entity it could not find."""
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and re.search(
        r"unknown color|Error executing|Error while executing|Error in|Invalid|not valid|not found", r.getMessage())]


# ---------------------------------------------------------------- the dashboard drives the light
async def test_the_strip_follows_the_colour_picked_in_a_list_on_the_dashboard(hass, house, libi, hass_ws_client,  # noqa: F811
                                                                              hass_client, caplog):
    """A P contact on the input_select starts the rung the moment another colour is picked; MOVE Color by name gives the
    strip that colour. It was a trigger to: "on", which a list of colours never reaches."""
    saved = await _saved(hass, libi, hass_ws_client, hass_client, _net(
        [_when("input_select.strip_color"), _move("input_select.strip_color", STRIP, "color_name")]))
    assert saved["triggers"] == [{"trigger": "state", "entity_id": "input_select.strip_color",
                                  "not_from": NOT_A_VALUE, "not_to": NOT_A_VALUE}], saved["triggers"]
    strip = house[STRIP]
    for name, rgb in (("blue", (0, 0, 255)), ("lime", (0, 255, 0)), ("orange", (255, 165, 0))):
        await _dashboard(hass, "input_select", "select_option", {"entity_id": "input_select.strip_color", "option": name})
        assert strip.sent[-1].get(ATTR_XY_COLOR) == color_util.color_RGB_to_xy(*rgb), (name, strip.sent)
        shown = hass.states.get(STRIP).attributes
        assert hass.states.get(STRIP).state == "on" and _same_hue(shown[ATTR_RGB_COLOR], rgb), (name, dict(shown))
    assert len(strip.sent) == 3, strip.sent
    # The helper drops off and comes back (a restart, a reload): no value was picked, so the rung does not run - with
    # a bare to: null it would, and Home Assistant would make the strip white for the colour "unavailable".
    hass.states.async_set("input_select.strip_color", "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set("input_select.strip_color", "orange", {"options": ["red", "orange", "blue", "lime"]})
    await hass.async_block_till_done()
    assert len(strip.sent) == 3, strip.sent
    assert _no_trouble(caplog) == []


async def test_a_colour_typed_as_hex_on_the_dashboard_reaches_the_strip(hass, house, libi, hass_ws_client, hass_client,  # noqa: F811
                                                                         caplog):
    """A text helper holding #rrggbb: the template LIBI writes turns it into the list a light takes - checked here by
    Home Assistant's own template engine, upper case, lower case and without the #."""
    saved = await _saved(hass, libi, hass_ws_client, hass_client, _net(
        [_when("input_text.strip_hex"), _move("input_text.strip_hex", TUYA, "rgb_color")]))
    assert "int(0, 16)" in saved["actions"][0]["data"]["rgb_color"], saved["actions"]
    tuya = house[TUYA]
    for text, rgb in (("#ff8800", (255, 136, 0)), ("#00FF7F", (0, 255, 127)), ("1e90ff", (30, 144, 255))):
        await _dashboard(hass, "input_text", "set_value", {"entity_id": "input_text.strip_hex", "value": text})
        assert tuya.sent[-1].get(ATTR_HS_COLOR) == color_util.color_RGB_to_hs(*rgb), (text, tuya.sent)
        assert _near(hass.states.get(TUYA).attributes[ATTR_RGB_COLOR], rgb), (text, hass.states.get(TUYA).attributes)
    assert _no_trouble(caplog) == []


async def test_dimming_from_a_slider_on_the_dashboard(hass, house, libi, hass_ws_client, hass_client, caplog):  # noqa: F811
    """A P contact on the input_number, MOVE of its value to a dimmable floodlight: brightness in % of the slider.
    0 turns the light off, as Home Assistant does with a brightness of 0."""
    await _saved(hass, libi, hass_ws_client, hass_client, _net(
        [_when("input_number.dim"), _move("input_number.dim", FLOOD)]))
    flood = house[FLOOD]
    for pct, brightness in ((60, 153), (20, 51), (100, 255)):
        await _dashboard(hass, "input_number", "set_value", {"entity_id": "input_number.dim", "value": pct})
        assert hass.states.get(FLOOD).state == "on", pct
        assert hass.states.get(FLOOD).attributes[ATTR_BRIGHTNESS] == brightness, (pct, flood.sent)
    await _dashboard(hass, "input_number", "set_value", {"entity_id": "input_number.dim", "value": 0})
    assert hass.states.get(FLOOD).state == "off" and flood.sent[-1] == {"off": True}, flood.sent
    assert _no_trouble(caplog) == []


async def test_a_light_takes_the_colour_of_another_lights_colour_wheel(hass, house, libi, hass_ws_client, hass_client,  # noqa: F811
                                                                       caplog):
    """The palette on a dashboard is a colour light's own wheel: the colour picked there on the strip, copied by a MOVE
    (IN = the strip) to the other strip when motion starts the rung."""
    await _saved(hass, libi, hass_ws_client, hass_client, _net(
        [_when("binary_sensor.motion", "contact_no"), _move(STRIP, TUYA, "rgb_color")]))
    await _dashboard(hass, "light", "turn_on", {"entity_id": STRIP, "hs_color": [280, 80]})  # the colour wheel
    picked = hass.states.get(STRIP).attributes[ATTR_RGB_COLOR]
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert house[TUYA].sent[-1].get(ATTR_HS_COLOR) == color_util.color_RGB_to_hs(*picked), (picked, house[TUYA].sent)
    assert _no_trouble(caplog) == []


# ---------------------------------------------------------------- fixed values, and what each kind of light does with them
async def test_a_fixed_brightness_a_palette_colour_a_temperature_and_an_effect(hass, house, libi, hass_ws_client,  # noqa: F811
                                                                               hass_client, caplog):
    """The values the Inspector sets with its slider and its palette, and two read from the dashboard's helpers, on the
    lights that take them; dim down by 10 % after 40 % is 30 %."""
    await _saved(hass, libi, hass_ws_client, hass_client, _net(
        [_when("binary_sensor.motion", "contact_no"), _move("40", FLOOD), _move("-10", FLOOD, "brightness_step_pct"),
         _move("[255, 136, 0]", STRIP, "rgb_color"), _move("input_number.kelvin", TUYA, "color_temp_kelvin"),
         _move("input_select.strip_effect", TUYA, "effect")]))
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert [s.get(ATTR_BRIGHTNESS) for s in house[FLOOD].sent] == [102, 76], house[FLOOD].sent
    assert house[STRIP].sent[-1].get(ATTR_XY_COLOR) == color_util.color_RGB_to_xy(255, 136, 0), house[STRIP].sent
    tuya = hass.states.get(TUYA).attributes
    assert tuya[ATTR_COLOR_TEMP_KELVIN] == 2700 and tuya["color_mode"] == ColorMode.COLOR_TEMP, dict(tuya)
    assert tuya[ATTR_EFFECT] == "rainbow", dict(tuya)
    assert _no_trouble(caplog) == []


async def test_a_value_a_light_cannot_take_is_left_out_and_the_light_is_turned_on(hass, house, libi, hass_ws_client,  # noqa: F811
                                                                                  hass_client):
    """Most lights of the house only turn on and off (the ZHA wall switches), the floodlights only dim. Home Assistant
    leaves out what a light cannot take and turns it on - what the Inspector now says (_lightNote)."""
    await _saved(hass, libi, hass_ws_client, hass_client, _net(
        [_when("binary_sensor.motion", "contact_no"), _move("40", RELAY), _move("[255, 0, 0]", FLOOD, "rgb_color")]))
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert hass.states.get(RELAY).state == "on" and house[RELAY].sent == [{}], house[RELAY].sent
    assert hass.states.get(FLOOD).state == "on" and house[FLOOD].sent == [{}], house[FLOOD].sent


# ---------------------------------------------------------------- the compiler and the panel
def test_a_p_contact_on_a_value_is_the_moment_it_changes_and_reads_back_as_drawn(hass):
    """Drawn by hand, saved, opened again: the same P contact, the rung saying "changes" - and the round trip check
    passes. A P contact on what turns on and off is still the moment it turns on."""
    net = _net([_when("input_select.strip_color"), _move("input_select.strip_color", STRIP, "color_name")],
               [_when("input_button.doorbell"), _move("100", FLOOD)],
               [_when("binary_sensor.motion"), _move("40", FLOOD)])
    auto = ast_to_yaml(hass, net)
    assert auto["triggers"][:2] == [
        {"trigger": "state", "entity_id": e, "not_from": NOT_A_VALUE, "not_to": NOT_A_VALUE, "id": f"t{i}"}
        for i, e in ((1, "input_select.strip_color"), (2, "input_button.doorbell"))], auto["triggers"]
    assert auto["triggers"][2] == {"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on", "id": "t3"}
    drawn = yaml_to_ast(hass, copy.deepcopy(auto))
    firsts = [r["elements"][0] for r in drawn["rungs"]]
    assert [(e["type"], e["label"]) for e in firsts[:2]] == [("contact_p", "input_select.strip_color"),
                                                             ("contact_p", "input_button.doorbell")]
    said = [r["comment"] for r in drawn["rungs"]]
    assert said[0].startswith("When strip color changes,") and said[1].startswith("When doorbell is pressed,"), said
    report = verify_round_trip(hass, copy.deepcopy(auto))
    assert report["ok"], report


@pytest.mark.parametrize("kind", ["contact_no", "contact_nc", "contact_n"])
async def test_a_contact_waiting_for_on_or_off_on_a_number_is_not_saved(hass, house, libi, hass_ws_client, hass_client,  # noqa: F811
                                                                        kind):
    """A number, a date, a button is never on or off: such a contact never holds - an automation that never runs. SAVE
    refuses it and says what to draw instead; automations.yaml is not touched."""
    before = (libi / "automations.yaml").read_text(encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net([_when("input_number.dim", kind), _move("input_number.dim", FLOOD)])])
    assert done is None and not plan["ok"], plan
    assert any("input_number.dim is never on or off" in e and "P contact" in e for e in plan["errors"]), plan["errors"]
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before
    condition = _net([_when("binary_sensor.motion", "contact_no"),
                      {"type": kind, "label": "counter.visits", "isTrigger": False}, _move("40", FLOOD)])
    with pytest.raises(ValueError, match="counter.visits is never on or off"):
        ast_to_yaml(hass, condition)


def test_a_contact_from_home_assistant_on_a_value_is_written_back_as_it_was(hass):
    """An automation the user has - written in Home Assistant, waiting for "on" on a list - is not refused and not
    changed: LIBI saves what it did not change as it was (CLAUDE.md RULE 5); the Inspector says it never holds."""
    auto = {"id": "a1", "alias": "Old", "triggers": [{"trigger": "state", "entity_id": "input_select.mode", "to": "on"}],
            "conditions": [{"condition": "state", "entity_id": "input_number.dim", "state": "on"}],
            "actions": [{"action": "light.turn_on", "target": {"entity_id": FLOOD}}]}
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    out = ast_to_yaml(hass, net)
    assert [{k: v for k, v in t.items() if k != "id"} for t in out["triggers"]] == auto["triggers"], out["triggers"]
    assert out["conditions"] == auto["conditions"], out["conditions"]
    report = verify_round_trip(hass, copy.deepcopy(auto))
    assert report["ok"], report


def _panel_set(name: str) -> set:
    m = re.search(rf"export const {name} = new Set\(\[(.*?)\]\);", PANEL.read_text(encoding="utf-8"), re.S)
    assert m, name
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def test_the_panel_and_the_compiler_have_the_same_values():
    """What the panel shows red, and calls the moment a value changes, is what the compiler refuses and writes."""
    assert _panel_set("VALUE_DOMAINS") == set(VALUE_DOMAINS)
    assert _panel_set("NEVER_ON_DOMAINS") == set(NEVER_ON_DOMAINS)
    assert NEVER_ON_DOMAINS <= VALUE_DOMAINS


def test_every_colour_name_the_panel_offers_is_one_home_assistant_knows():
    """Color by name offers a list (libi-panel.js COLOR_NAMES); a name Home Assistant does not know makes the light
    white, with only a warning in the log."""
    m = re.search(r"const COLOR_NAMES = \[(.*?)\];", PANEL.read_text(encoding="utf-8"), re.S)
    names = re.findall(r"'([a-z ]+)'", m.group(1))
    assert len(names) >= 10
    unknown = [n for n in names if n.replace(" ", "") not in color_util.COLORS]
    assert unknown == [], unknown
