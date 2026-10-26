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
"""YAML -> ladder -> YAML must give back an equivalent automation (CLAUDE.md RULE 5)."""
import pytest
from homeassistant.core import HomeAssistant

from custom_components.libi.libi_to_yaml import verify_round_trip

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
]


@pytest.mark.parametrize("automation", CORPUS, ids=[a["id"] for a in CORPUS])
async def test_round_trip_is_lossless(hass: HomeAssistant, automation) -> None:
    report = verify_round_trip(hass, automation)
    assert report["ok"], report.get("issues")
