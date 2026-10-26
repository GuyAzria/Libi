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
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.libi import libi_to_yaml
from custom_components.libi.libi_to_yaml import verify_round_trip

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
