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
# [ADDED v3.96.0 | 2026-11-11] Purpose: The user (2026-11-11): "check every kind, not only automations". Every kind of
#   trigger, condition and action Home Assistant knows - in an automation, as a step of a script, inside a choose and an
#   if - and every shape of a scene's entities, read into a net and compiled back (RULE 5: the round trip is lossless).
#   It found, and now guards: a not of several checks drawn without its not, a condition of a new kind drawn as an
#   action, a template's short form dropped, two triggers of one id become one, three triggers written with a condition
#   made of them, the for of a check in a sequence written as a delay.
"""Home Assistant's own constructs through LIBI and back, in the three kinds: automation, script and scene."""
import copy

from custom_components.libi.libi_to_yaml import verify_round_trip

ON = {"action": "light.turn_on", "target": {"entity_id": "light.x"}}
OFF = {"action": "light.turn_off", "target": {"entity_id": "light.x"}}
GO = {"trigger": "state", "entity_id": "input_button.go"}
A_ON = {"condition": "state", "entity_id": "light.a", "state": "on"}
B_ON = {"condition": "state", "entity_id": "light.b", "state": "on"}

TRIGGERS = {
    "state basic": {"trigger": "state", "entity_id": "binary_sensor.door"},
    "state to on": {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"},
    "state from to": {"trigger": "state", "entity_id": "binary_sensor.door", "from": "off", "to": "on"},
    "state to with for": {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "for": "00:05:00"},
    "state for dict": {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "for": {"minutes": 5}},
    "state attribute": {"trigger": "state", "entity_id": "climate.ac", "attribute": "hvac_action", "to": "heating"},
    "state not_to": {"trigger": "state", "entity_id": "climate.ac", "not_to": ["unavailable", "unknown"]},
    "state not_from": {"trigger": "state", "entity_id": "climate.ac", "not_from": "unknown", "to": "heat"},
    "state two entities": {"trigger": "state", "entity_id": ["light.a", "light.b"], "to": "on"},
    "state to list": {"trigger": "state", "entity_id": "climate.ac", "to": ["heat", "cool"]},
    "state to null": {"trigger": "state", "entity_id": "climate.ac", "to": None},
    "state text value": {"trigger": "state", "entity_id": "sensor.mode", "to": "eco"},
    "numeric above": {"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 25},
    "numeric below": {"trigger": "numeric_state", "entity_id": "sensor.temp", "below": 10},
    "numeric both": {"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 10, "below": 25},
    "numeric attribute": {"trigger": "numeric_state", "entity_id": "climate.ac", "attribute": "current_temperature", "above": 25},
    "numeric value_template": {"trigger": "numeric_state", "entity_id": "sensor.temp", "value_template": "{{ state.state | float * 2 }}", "above": 30},
    "numeric for": {"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 25, "for": "00:10:00"},
    "numeric above helper": {"trigger": "numeric_state", "entity_id": "sensor.temp", "above": "input_number.limit"},
    "time fixed": {"trigger": "time", "at": "07:30:00"},
    "time list": {"trigger": "time", "at": ["07:30:00", "19:30:00"]},
    "time helper": {"trigger": "time", "at": "input_datetime.wake"},
    "time sensor offset": {"trigger": "time", "at": {"entity_id": "sensor.next_alarm", "offset": "-00:10:00"}},
    "time with weekday": {"trigger": "time", "at": "07:30:00", "weekday": ["mon", "tue"]},
    "time_pattern minutes": {"trigger": "time_pattern", "minutes": "/5"},
    "time_pattern hours": {"trigger": "time_pattern", "hours": "2", "minutes": 0},
    "sun sunset": {"trigger": "sun", "event": "sunset"},
    "sun sunrise offset": {"trigger": "sun", "event": "sunrise", "offset": "-00:30:00"},
    "zone enter": {"trigger": "zone", "entity_id": "person.guy", "zone": "zone.home", "event": "enter"},
    "zone leave": {"trigger": "zone", "entity_id": "person.guy", "zone": "zone.home", "event": "leave"},
    "event": {"trigger": "event", "event_type": "my_event"},
    "event with data": {"trigger": "event", "event_type": "zha_event", "event_data": {"command": "on"}},
    "homeassistant start": {"trigger": "homeassistant", "event": "start"},
    "homeassistant shutdown": {"trigger": "homeassistant", "event": "shutdown"},
    "mqtt": {"trigger": "mqtt", "topic": "home/door", "payload": "open"},
    "webhook": {"trigger": "webhook", "webhook_id": "abc123", "allowed_methods": ["POST"], "local_only": True},
    "template": {"trigger": "template", "value_template": "{{ states('sensor.a') | float > 5 }}"},
    "template for": {"trigger": "template", "value_template": "{{ is_state('light.a', 'on') }}", "for": "00:01:00"},
    "calendar": {"trigger": "calendar", "event": "start", "entity_id": "calendar.work", "offset": "-00:15:00"},
    "tag": {"trigger": "tag", "tag_id": "A7-6B-90-5F"},
    "conversation": {"trigger": "conversation", "command": ["turn on the lights"]},
    "persistent_notification": {"trigger": "persistent_notification", "update_type": ["added"]},
    "geo_location": {"trigger": "geo_location", "source": "nsw_rural_fire_service_feed", "zone": "zone.home", "event": "enter"},
    "device": {"trigger": "device", "device_id": "abc", "domain": "light", "type": "turned_on", "entity_id": "light.x"},
    "new style light.turned_on": {"trigger": "light.turned_on", "target": {"entity_id": "light.x"}, "options": {"behavior": "each"}},
    "trigger disabled": {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "enabled": False},
    "trigger alias": {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "alias": "Door opens"},
    "trigger variables": {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on", "variables": {"who": "door"}},
    "platform spelling": {"platform": "state", "entity_id": "binary_sensor.door", "to": "on"},
}

CONDITIONS = {
    "state on": A_ON,
    "state text": {"condition": "state", "entity_id": "climate.ac", "state": "heat"},
    "state list": {"condition": "state", "entity_id": "climate.ac", "state": ["heat", "cool"]},
    "state attribute": {"condition": "state", "entity_id": "climate.ac", "attribute": "fan_mode", "state": "auto"},
    "state for": {"condition": "state", "entity_id": "light.a", "state": "on", "for": "00:05:00"},
    "state two entities": {"condition": "state", "entity_id": ["light.a", "light.b"], "state": "on"},
    "state match any": {"condition": "state", "entity_id": ["light.a", "light.b"], "state": "on", "match": "any"},
    "state helper": {"condition": "state", "entity_id": "sensor.mode", "state": "input_select.mode"},
    "numeric above": {"condition": "numeric_state", "entity_id": "sensor.temp", "above": 20},
    "numeric below": {"condition": "numeric_state", "entity_id": "sensor.temp", "below": 20},
    "numeric both": {"condition": "numeric_state", "entity_id": "sensor.temp", "above": 10, "below": 20},
    "numeric attribute": {"condition": "numeric_state", "entity_id": "climate.ac", "attribute": "current_temperature", "below": 20},
    "numeric value_template": {"condition": "numeric_state", "entity_id": "sensor.temp", "value_template": "{{ state.state | float + 1 }}", "above": 5},
    "time after before": {"condition": "time", "after": "08:00:00", "before": "20:00:00"},
    "time weekday": {"condition": "time", "weekday": ["mon", "wed"]},
    "time all": {"condition": "time", "after": "08:00:00", "before": "20:00:00", "weekday": ["sat", "sun"]},
    "time helper": {"condition": "time", "after": "input_datetime.start", "before": "input_datetime.end"},
    "sun after": {"condition": "sun", "after": "sunset"},
    "sun offsets": {"condition": "sun", "after": "sunset", "after_offset": "-01:00:00", "before": "sunrise"},
    "zone": {"condition": "zone", "entity_id": "person.guy", "zone": "zone.home"},
    "template": {"condition": "template", "value_template": "{{ states('sensor.a') | float > 5 }}"},
    "template shorthand": "{{ is_state('light.a', 'on') }}",
    "and": {"condition": "and", "conditions": [A_ON, {"condition": "state", "entity_id": "light.b", "state": "off"}]},
    "or": {"condition": "or", "conditions": [A_ON, B_ON]},
    "not": {"condition": "not", "conditions": [{"condition": "state", "entity_id": "climate.ac", "state": "heat"}]},
    "not of two": {"condition": "not", "conditions": [A_ON, B_ON]},
    "not with for inside": {"condition": "not", "conditions": [{"condition": "state", "entity_id": "climate.ac", "state": "heat", "for": "00:05:00"}]},
    "or shorthand": {"or": [A_ON, {"condition": "numeric_state", "entity_id": "sensor.temp", "above": 5}]},
    "and in or": {"condition": "or", "conditions": [{"condition": "and", "conditions": [A_ON, B_ON]},
                                                    {"condition": "state", "entity_id": "light.c", "state": "on"}]},
    "device": {"condition": "device", "device_id": "abc", "domain": "light", "type": "is_on", "entity_id": "light.x"},
    "disabled": {**A_ON, "enabled": False},
    "alias": {**A_ON, "alias": "A is on"},
    "new style light.is_on": {"condition": "light.is_on", "target": {"entity_id": "light.x"}, "options": {"behavior": "any"}},
}

ACTIONS = {
    "service entity": ON,
    "service data": {"action": "light.turn_on", "target": {"entity_id": "light.x"}, "data": {"brightness_pct": 50, "transition": 2}},
    "service area": {"action": "light.turn_off", "target": {"area_id": "kitchen"}},
    "service device": {"action": "light.turn_off", "target": {"device_id": "abc"}},
    "service label floor": {"action": "light.turn_off", "target": {"label_id": "night", "floor_id": "up"}},
    "service two entities": {"action": "light.turn_on", "target": {"entity_id": ["light.x", "light.y"]}},
    "service old spelling": {"service": "light.turn_on", "entity_id": "light.x"},
    "service data entity": {"action": "light.turn_on", "data": {"entity_id": "light.x", "brightness": 100}},
    "service response": {"action": "weather.get_forecasts", "target": {"entity_id": "weather.home"}, "data": {"type": "daily"}, "response_variable": "fc"},
    "service template": {"action": "light.turn_{{ 'on' if is_state('sun.sun', 'below_horizon') else 'off' }}", "target": {"entity_id": "light.x"}},
    "service disabled": {**ON, "enabled": False},
    "service continue_on_error": {**ON, "continue_on_error": True},
    "service alias": {**ON, "alias": "Light on"},
    "toggle": {"action": "switch.toggle", "target": {"entity_id": "switch.s"}},
    "cover open": {"action": "cover.open_cover", "target": {"entity_id": "cover.c"}},
    "lock": {"action": "lock.lock", "target": {"entity_id": "lock.l"}},
    "climate set": {"action": "climate.set_temperature", "target": {"entity_id": "climate.ac"}, "data": {"temperature": 22, "hvac_mode": "heat"}},
    "input_number set": {"action": "input_number.set_value", "target": {"entity_id": "input_number.n"}, "data": {"value": 5}},
    "input_select": {"action": "input_select.select_option", "target": {"entity_id": "input_select.s"}, "data": {"option": "Away"}},
    "input_boolean on": {"action": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.b"}},
    "counter": {"action": "counter.increment", "target": {"entity_id": "counter.c"}},
    "notify": {"action": "notify.mobile_app_x", "data": {"message": "Hello", "title": "Hi"}},
    "notify with data": {"action": "notify.mobile_app_x", "data": {"message": "Hello", "data": {"tag": "t", "actions": [{"action": "YES", "title": "Yes"}]}}},
    "persistent_notification": {"action": "persistent_notification.create", "data": {"message": "Hello", "title": "Hi"}},
    "tts speak": {"action": "tts.speak", "target": {"entity_id": "tts.google"}, "data": {"media_player_entity_id": "media_player.k", "message": "Hello"}},
    "script call": {"action": "script.my_script", "data": {"x": 1}},
    "script turn_on": {"action": "script.turn_on", "target": {"entity_id": "script.my_script"}, "data": {"variables": {"x": 1}}},
    "scene turn_on": {"action": "scene.turn_on", "target": {"entity_id": "scene.movie"}},
    "scene shorthand": {"scene": "scene.movie"},
    "delay string": {"delay": "00:00:10"},
    "delay dict": {"delay": {"minutes": 2}},
    "delay seconds": {"delay": 5},
    "delay template": {"delay": "{{ states('input_number.wait') | int }}"},
    "wait_template": {"wait_template": "{{ is_state('light.x', 'off') }}", "timeout": "00:01:00", "continue_on_timeout": False},
    "wait_for_trigger": {"wait_for_trigger": [{"trigger": "state", "entity_id": "light.x", "to": "off"}], "timeout": {"minutes": 1}},
    "event": {"event": "my_event", "event_data": {"a": 1}},
    "condition step": A_ON,
    "variables": {"variables": {"a": 1, "b": "{{ 2 }}"}},
    "stop": {"stop": "Done"},
    "stop error": {"stop": "Bad", "error": True},
    "stop response": {"stop": "Done", "response_variable": "result"},
    "set_conversation_response": {"set_conversation_response": "OK"},
    "device action": {"device_id": "abc", "domain": "light", "type": "turn_on", "entity_id": "light.x"},
    "choose": {"choose": [{"conditions": [A_ON], "sequence": [ON]}], "default": [OFF]},
    "choose two": {"choose": [{"conditions": [A_ON], "sequence": [ON]}, {"conditions": [B_ON], "sequence": [{"delay": "00:00:05"}, ON]}]},
    "if then": {"if": [A_ON], "then": [ON]},
    "if then else": {"if": [A_ON], "then": [ON], "else": [OFF]},
    "repeat count": {"repeat": {"count": 3, "sequence": [ON, {"delay": "00:00:01"}]}},
    "repeat while": {"repeat": {"while": [A_ON], "sequence": [ON]}},
    "repeat until": {"repeat": {"until": [{"condition": "state", "entity_id": "light.a", "state": "off"}], "sequence": [ON]}},
    "repeat for_each": {"repeat": {"for_each": ["light.a", "light.b"], "sequence": [{"action": "light.turn_on", "target": {"entity_id": "{{ repeat.item }}"}}]}},
    "parallel": {"parallel": [ON, {"action": "switch.turn_on", "target": {"entity_id": "switch.s"}}]},
    "parallel sequences": {"parallel": [{"sequence": [ON, {"delay": 1}]}, {"sequence": [{"action": "switch.turn_on", "target": {"entity_id": "switch.s"}}]}]},
    "sequence": {"sequence": [ON, {"delay": 1}]},
    "nested if in choose": {"choose": [{"conditions": [A_ON], "sequence": [{"if": [B_ON], "then": [ON]}]}]},
}

TOP = {
    "mode queued max": {"mode": "queued", "max": 5},
    "mode restart": {"mode": "restart"},
    "max_exceeded": {"mode": "single", "max_exceeded": "silent"},
    "variables": {"variables": {"x": 1}},
    "trigger_variables": {"trigger_variables": {"x": 1}},
    "trace": {"trace": {"stored_traces": 20}},
    "initial_state": {"initial_state": False},
}

SCRIPT_TOP = {
    "plain": {},
    "no alias": {"__no_alias__": True},
    "icon mode": {"icon": "mdi:play", "mode": "queued", "max": 3, "max_exceeded": "silent"},
    "fields": {"fields": {"who": {"description": "Who", "example": "Guy", "selector": {"text": None}}}},
    "variables": {"variables": {"x": 1}},
    "description": {"description": "What it does"},
    "trace": {"trace": {"stored_traces": 10}},
}

SCENES = {
    "on off": {"light.a": "on", "switch.b": "off"},
    "bare yaml on": {"light.a": True, "switch.b": False},
    "state dict": {"light.a": {"state": "on"}},
    "brightness": {"light.a": {"state": "on", "brightness": 180, "color_temp": 300}},
    "attrs first": {"light.a": {"brightness": 180, "state": "on"}},
    "rgb list": {"light.a": {"state": "on", "rgb_color": [255, 0, 0], "effect": "none"}},
    "climate": {"climate.ac": {"state": "heat", "temperature": 22.5, "fan_mode": "auto"}},
    "cover": {"cover.c": {"state": "open", "current_position": 50}},
    "media": {"media_player.tv": {"state": "playing", "source": "HDMI 1", "volume_level": 0.3}},
    "plain other state": {"input_select.mode": "Away", "input_number.n": 5, "input_boolean.b": "on", "lock.l": "locked"},
    "number as text": {"input_number.n": "5.0"},
    "no state only attr": {"light.a": {"brightness": 100}},
    "empty dict": {"light.a": {}},
    "none": {"light.a": None},
    "nested dict attr": {"light.a": {"state": "on", "xy_color": [0.5, 0.4], "extra": {"a": 1}}},
    "many": {f"light.l{i}": "on" for i in range(12)},
}
SCENE_TOP = {"plain": {}, "icon": {"icon": "mdi:sofa"}, "metadata": {"metadata": {"light.a": {"entity_only": True}}}}


def auto(triggers=None, conditions=None, actions=None, **top):
    return {"id": "x", "alias": "x", "description": "", "triggers": triggers if triggers is not None else [copy.deepcopy(GO)],
            "conditions": conditions or [], "actions": actions if actions is not None else [copy.deepcopy(ON)], **top}


def script(sequence, **top):
    out = {"alias": "My script", "sequence": copy.deepcopy(sequence), **top}
    if out.pop("__no_alias__", None):
        out.pop("alias")
    return out


async def test_every_construct_comes_back_in_the_three_kinds(hass):
    cases = []
    for name, t in TRIGGERS.items():
        cases.append(("automation", "", "trigger", name, auto(triggers=[copy.deepcopy(t)])))
    for name, c in CONDITIONS.items():
        cases.append(("automation", "", "condition", name, auto(conditions=[copy.deepcopy(c)])))
        cases.append(("automation", "", "condition in choose", name, auto(actions=[{"choose": [{"conditions": [copy.deepcopy(c)], "sequence": [copy.deepcopy(ON)]}]}])))
        if isinstance(c, dict):  # a bare string is no step of a sequence in Home Assistant
            cases.append(("script", "s", "condition step", name, script([copy.deepcopy(c), ON])))
        cases.append(("script", "s", "condition in if", name, script([{"if": [copy.deepcopy(c)], "then": [ON]}])))
    for name, a in ACTIONS.items():
        cases.append(("automation", "", "action", name, auto(actions=[copy.deepcopy(a)])))
        cases.append(("automation", "", "action after another", name, auto(actions=[copy.deepcopy(ON), copy.deepcopy(a)])))
        cases.append(("script", "s", "step", name, script([a])))
        cases.append(("script", "s", "step after another", name, script([ON, a])))
        cases.append(("script", "s", "step before another", name, script([a, OFF])))
    for name, top in TOP.items():
        cases.append(("automation", "", "top", name, auto(**copy.deepcopy(top))))
    cases.append(("automation", "", "top", "blueprint", {"id": "x", "alias": "x", "description": "", "use_blueprint": {
        "path": "homeassistant/motion_light.yaml", "input": {"motion_entity": "binary_sensor.m"}}}))
    cases.append(("automation", "", "top", "old spelling", {"id": "x", "alias": "x", "trigger": [{"platform": "state", "entity_id": "input_button.go"}],
                                                          "condition": [], "action": [{"service": "light.turn_on", "entity_id": "light.x"}]}))
    two = [{"trigger": "state", "entity_id": "light.a", "to": "on", "id": "a"}, {"trigger": "time", "at": "07:00:00", "id": "t"}]
    cases.append(("automation", "", "mix", "two triggers one action", auto(triggers=copy.deepcopy(two))))
    cases.append(("automation", "", "mix", "trigger ids with choose", auto(triggers=copy.deepcopy(two), actions=[{"choose": [
        {"conditions": [{"condition": "trigger", "id": "a"}], "sequence": [copy.deepcopy(ON)]},
        {"conditions": [{"condition": "trigger", "id": "t"}], "sequence": [{"delay": 1}]}]}])))
    cases.append(("automation", "", "mix", "trigger id list", auto(triggers=copy.deepcopy(two), actions=[{"choose": [
        {"conditions": [{"condition": "trigger", "id": ["a", "t"]}], "sequence": [copy.deepcopy(ON)]}]}])))
    same = [{"trigger": "light.turned_on", "target": {"entity_id": "light.s"}, "options": {"behavior": "each"}, "id": "on"},
            {"trigger": "state", "entity_id": ["light.a", "light.b"], "to": "on", "id": "on"},
            {"trigger": "state", "entity_id": ["light.s", "light.a"], "to": "off", "id": "off"}]
    cases.append(("automation", "", "mix", "two triggers of one id", auto(triggers=copy.deepcopy(same), actions=[{"choose": [
        {"conditions": [{"condition": "trigger", "id": "on"}], "sequence": [copy.deepcopy(ON)]},
        {"conditions": [{"condition": "trigger", "id": "off"}], "sequence": [copy.deepcopy(OFF)]}]}])))
    cases.append(("automation", "", "mix", "two triggers of one id, plain", auto(triggers=copy.deepcopy(same))))
    cases.append(("automation", "", "mix", "or of trigger refs", auto(triggers=copy.deepcopy(two), actions=[{"choose": [
        {"conditions": [{"condition": "or", "conditions": [{"condition": "trigger", "id": "a"}, {"condition": "trigger", "id": "t"}]}],
         "sequence": [copy.deepcopy(ON)]}]}])))
    for nm, cond in (("not of or", {"condition": "not", "conditions": [{"condition": "or", "conditions": [A_ON, B_ON]}]}),
                     ("not of time window", {"condition": "not", "conditions": [{"condition": "time", "after": "08:00:00", "before": "20:00:00"}]}),
                     ("not with alias of two", {"condition": "not", "alias": "none on", "conditions": [A_ON, B_ON]}),
                     ("not of numeric", {"condition": "not", "conditions": [{"condition": "numeric_state", "entity_id": "sensor.t", "above": 5}]}),
                     ("and with alias", {"condition": "and", "alias": "both", "conditions": [A_ON, B_ON]}),
                     ("or with not inside", {"condition": "or", "conditions": [A_ON, {"condition": "not", "conditions": [B_ON]}]}),
                     ("not in or of two", {"condition": "or", "conditions": [A_ON, {"condition": "not", "conditions": [A_ON, B_ON]}]})):
        cases.append(("automation", "", "condition+", nm, auto(conditions=[copy.deepcopy(cond)])))
        cases.append(("script", "s", "condition+ in if", nm, script([{"if": [copy.deepcopy(cond)], "then": [ON]}])))
    three = [{"trigger": "state", "entity_id": "light.s", "to": "on"}, {"trigger": "time", "at": "07:00:00"},
             {"trigger": "sun", "event": "sunset"}, {"trigger": "numeric_state", "entity_id": "sensor.t", "above": 5}]
    cases.append(("automation", "", "mix", "three triggers", auto(triggers=copy.deepcopy(three[:3]))))
    cases.append(("automation", "", "mix", "four triggers", auto(triggers=copy.deepcopy(three))))
    cases.append(("automation", "", "mix", "four triggers and a condition", auto(triggers=copy.deepcopy(three), conditions=[A_ON])))
    cases.append(("automation", "", "mix", "four triggers with choose", auto(triggers=copy.deepcopy(three), actions=[{"choose": [
        {"conditions": [A_ON], "sequence": [copy.deepcopy(ON)]}], "default": [copy.deepcopy(OFF)]}])))
    for nm, cond in (("and turned off", {"condition": "and", "enabled": False, "conditions": [A_ON, B_ON]}),
                     ("or turned off", {"condition": "or", "enabled": False, "conditions": [A_ON, B_ON]}),
                     ("not turned off", {"condition": "not", "enabled": False, "conditions": [A_ON]})):
        cases.append(("automation", "", "condition+", nm, auto(conditions=[copy.deepcopy(cond)])))
    cases.append(("automation", "", "mix", "no actions", auto(actions=[])))
    cases.append(("automation", "", "mix", "no triggers", auto(triggers=[])))
    for name, top in SCRIPT_TOP.items():
        cases.append(("script", "s", "top", name, script([ON, {"delay": 1}, OFF], **copy.deepcopy(top))))
    cases.append(("script", "s", "top", "empty sequence", script([])))
    cases.append(("script", "s", "top", "fields used", script([{"action": "notify.notify", "data": {"message": "{{ who }}"}}],
                                                              fields={"who": {"description": "Who"}})))
    for name, entities in SCENES.items():
        cases.append(("scene", "", "entities", name, {"id": "sc1", "name": "Movie", "entities": copy.deepcopy(entities)}))
    for name, top in SCENE_TOP.items():
        cases.append(("scene", "", "top", name, {"id": "sc1", "name": "Movie", "entities": {"light.a": "on"}, **copy.deepcopy(top)}))
    cases.append(("scene", "", "top", "numeric id", {"id": 1700000000000, "name": "Movie", "entities": {"light.a": "on"}}))
    bad, counts = [], {}
    for domain, key, group, name, config in cases:
        counts[domain] = counts.get(domain, 0) + 1
        res = verify_round_trip(hass, copy.deepcopy(config), domain, key)
        if not res.get("ok"):
            bad.append((domain, group, name, res.get("error") or "; ".join((res.get("issues") or [])[:3])))
    assert counts["automation"] > 250 and counts["script"] > 240 and counts["scene"] >= 20, counts
    # What is known not to come back as it was, and why: an and with a name of its own is drawn as its checks - the
    # logic is the same, the name is not kept (the panel says so when such an entry is opened, and asks before a save).
    assert [(d, g, n) for d, g, n, _why in bad] == KNOWN, bad


KNOWN = [("automation", "condition+", "and with alias"), ("script", "condition+ in if", "and with alias")]


# [ADDED v3.96.0 | 2026-11-17] The user: "challenge yourself with code that is common in Home Assistant". Whole
# automations, a script and a scene as people write them - each must come back as it was, and the values a device is
# given must be drawn as MOVE blocks the user can read.
RECIPES = {
    "motion light": {"mode": "restart", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.hall_motion", "to": "on"}],
                     "conditions": [{"condition": "sun", "after": "sunset", "before": "sunrise"}],
                     "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.hall"}, "data": {"brightness_pct": 60, "transition": 1}},
                                 {"wait_for_trigger": [{"trigger": "state", "entity_id": "binary_sensor.hall_motion", "to": "off",
                                                        "for": {"minutes": 2}}]},
                                 {"action": "light.turn_off", "target": {"entity_id": "light.hall"}, "data": {"transition": 5}}]},
    "dim from a helper": {"triggers": [{"trigger": "state", "entity_id": "input_number.desk_level"}],
                          "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.desk"},
                                       "data": {"brightness_pct": "{{ states('input_number.desk_level') | int }}"}}]},
    "actionable notification": {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.front_door", "to": "on"}],
        "actions": [{"action": "notify.mobile_app_phone", "data": {"message": "Door opened: {{ trigger.to_state.name }}",
                                                                    "data": {"actions": [{"action": "LOCK_DOOR", "title": "Lock"}]}}},
                    {"wait_for_trigger": [{"trigger": "event", "event_type": "mobile_app_notification_action",
                                           "event_data": {"action": "LOCK_DOOR"}}], "timeout": "00:05:00", "continue_on_timeout": False},
                    {"action": "lock.lock", "target": {"entity_id": "lock.front_door"}}]},
    "snapshot and restore": {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.doorbell", "to": "on"}],
        "actions": [{"action": "scene.create", "data": {"scene_id": "before_doorbell", "snapshot_entities": ["light.hall", "light.porch"]}},
                    {"action": "light.turn_on", "target": {"entity_id": ["light.hall", "light.porch"]},
                     "data": {"rgb_color": [255, 0, 0], "brightness_pct": 100}},
                    {"delay": {"seconds": 30}},
                    {"action": "scene.turn_on", "target": {"entity_id": "scene.before_doorbell"}}]},
    "timer and choose": {
        "triggers": [{"trigger": "event", "event_type": "timer.finished", "event_data": {"entity_id": "timer.laundry"}, "id": "done"},
                     {"trigger": "state", "entity_id": "switch.washer", "to": "on", "id": "start"}],
        "actions": [{"choose": [{"conditions": [{"condition": "trigger", "id": "start"}],
                                 "sequence": [{"action": "timer.start", "target": {"entity_id": "timer.laundry"}, "data": {"duration": "01:30:00"}}]},
                                {"conditions": [{"condition": "trigger", "id": "done"}],
                                 "sequence": [{"action": "persistent_notification.create", "data": {"message": "Laundry is done"}}]}],
                     "default": [{"action": "counter.increment", "target": {"entity_id": "counter.washes"}}]}]},
    "cycle a mode": {"triggers": [{"trigger": "state", "entity_id": "sensor.button_action", "to": "single"}],
                     "actions": [{"action": "input_select.select_next", "target": {"entity_id": "input_select.house_mode"}, "data": {"cycle": True}},
                                 {"action": "input_boolean.toggle", "target": {"entity_id": "input_boolean.guest"}},
                                 {"action": "counter.decrement", "target": {"entity_id": "counter.left"}}]},
    "thermostat": {"triggers": [{"trigger": "numeric_state", "entity_id": "sensor.living_temp", "above": 26, "for": "00:10:00"}],
                   "conditions": [{"condition": "state", "entity_id": "binary_sensor.window", "state": "off"}],
                   "actions": [{"action": "climate.set_hvac_mode", "target": {"entity_id": "climate.ac"}, "data": {"hvac_mode": "cool"}},
                               {"action": "climate.set_temperature", "target": {"entity_id": "climate.ac"}, "data": {"temperature": 23}}]},
    "morning radio": {"triggers": [{"trigger": "time", "at": "07:00:00"}],
                      "conditions": [{"condition": "time", "weekday": ["mon", "tue", "wed", "thu", "fri"]}],
                      "actions": [{"action": "media_player.volume_set", "target": {"entity_id": "media_player.kitchen"}, "data": {"volume_level": 0.25}},
                                  {"action": "media_player.play_media", "target": {"entity_id": "media_player.kitchen"},
                                   "data": {"media_content_id": "https://radio.example/stream", "media_content_type": "music"}}]},
    "delay from a helper": {"triggers": [{"trigger": "state", "entity_id": "switch.pump", "to": "on"}],
                            "actions": [{"delay": {"minutes": "{{ states('input_number.pump_minutes') | int }}"}},
                                        {"action": "switch.turn_off", "target": {"entity_id": "switch.pump"}}]},
    "repeat while": {"triggers": [{"trigger": "state", "entity_id": "binary_sensor.leak", "to": "on"}],
                     "actions": [{"repeat": {"while": [{"condition": "state", "entity_id": "binary_sensor.leak", "state": "on"}],
                                             "sequence": [{"action": "notify.notify", "data": {"message": "Water leak!"}}, {"delay": {"minutes": 1}}]}}]},
    "template trigger for": {"triggers": [{"trigger": "template", "value_template": "{{ states('sensor.power') | float(0) < 5 }}",
                                           "for": {"minutes": 3}}],
                             "actions": [{"action": "switch.turn_off", "target": {"entity_id": "switch.tv_plug"}}]},
    "sunset colours": {"triggers": [{"trigger": "sun", "event": "sunset", "offset": "-00:30:00"}],
                       "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.led_strip"}, "data": {"color_temp_kelvin": 2700}},
                                   {"action": "light.turn_on", "target": {"entity_id": "light.desk"}, "data": {"rgb_color": [255, 100, 0]}},
                                   {"action": "fan.set_percentage", "target": {"entity_id": "fan.bedroom"}, "data": {"percentage": 30}},
                                   {"action": "cover.set_cover_position", "target": {"entity_id": "cover.living_blind"}, "data": {"position": 20}}]},
}
WAKE_UP = {"alias": "Wake up", "fields": {"level": {"selector": {"number": {"min": 0, "max": 100}}}},
           "sequence": [{"action": "light.turn_on", "target": {"entity_id": "light.bedroom"},
                         "data": {"brightness_pct": "{{ level }}", "transition": 60}}]}
EVENING = {"id": "1700000000077", "name": "Evening",
           "entities": {"light.living": {"state": "on", "brightness": 120, "color_temp_kelvin": 2700},
                        "light.led_strip": {"state": "on", "rgb_color": [255, 100, 0], "brightness": 200},
                        "cover.living_blind": {"state": "closed", "current_position": 0}, "media_player.tv": "off"}}


async def test_common_recipes_come_back_and_their_values_are_drawn(hass):
    from custom_components.libi.yaml_to_libi import entry_to_ast

    def moves(net):
        out = []

        def walk(els):
            for e in els:
                if e.get("type") == "move" and e.get("mode", "value") == "value" and e.get("valueKey") and e.get("moveKind") != "action":
                    out.append((e["target"], e["valueKey"], e["source"]))
                for b in e.get("branches") or []:
                    walk(b)
                walk(e.get("sequence") or [])
        for r in net["rungs"]:
            walk(r["elements"])
        return out

    drawn = {}
    for name, body in RECIPES.items():
        auto = {"id": name.replace(" ", "_"), "alias": name, **copy.deepcopy(body)}
        res = verify_round_trip(hass, copy.deepcopy(auto))
        assert res["ok"], (name, res)
        drawn[name] = moves(entry_to_ast(hass, "automation", auto["id"], copy.deepcopy(auto)))
    assert drawn["motion light"] == [("light.hall", "brightness_pct", 60)]
    assert drawn["dim from a helper"] == [("light.desk", "brightness_pct", "input_number.desk_level")]
    assert drawn["sunset colours"] == [("light.led_strip", "color_temp_kelvin", 2700), ("light.desk", "rgb_color", "[255, 100, 0]"),
                                       ("fan.bedroom", "percentage", 30), ("cover.living_blind", "position", 20)]
    assert drawn["morning radio"] == [("media_player.kitchen", "volume_level", 0.25)]
    assert drawn["thermostat"] == [("climate.ac", "temperature", 23)]
    assert drawn["snapshot and restore"] == []  # two lights, two values: kept as they were drawn
    assert verify_round_trip(hass, copy.deepcopy(WAKE_UP), "script", "wake_up")["ok"]
    assert moves(entry_to_ast(hass, "script", "wake_up", copy.deepcopy(WAKE_UP))) == [("light.bedroom", "brightness_pct", "{{ level }}")]
    assert verify_round_trip(hass, copy.deepcopy(EVENING), "scene", EVENING["id"])["ok"]

def test_the_triggers_keep_their_place_and_traces_fires_the_right_one(hass):
    """A choose that names the automation's triggers in another order: the save writes them in their own order, and
    Traces' Real fires the trigger at the place Home Assistant has it (trigger_place)."""
    from custom_components.libi.libi_to_yaml import ast_to_yaml, trigger_place
    from custom_components.libi.yaml_to_libi import yaml_to_ast

    auto = {"id": "laundry", "alias": "Laundry", **copy.deepcopy(RECIPES["timer and choose"])}
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    first = net["rungs"][0]["elements"][0]
    assert (first.get("trigId"), first.get("label")) == ("start", "switch.washer")
    place, trigger = trigger_place(net, first["id"])
    assert place == 1 and trigger["entity_id"] == "switch.washer"
    first["label"] = "switch.dryer"  # edited: compiled again, still second
    assert [t.get("id") for t in ast_to_yaml(hass, net)["triggers"]] == ["done", "start"]
    assert trigger_place(net, first["id"])[0] == 1
