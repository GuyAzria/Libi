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
"""The AI chat: the model drafts, Home Assistant decides (CLAUDE.md RULES 7-11, 32).

The model is replaced by canned answers, so these tests check what LIBI does with whatever a model
returns - including answers that try to name entities, devices and services on their own."""
import copy
import os
from unittest.mock import patch

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.libi import ai
from custom_components.libi.yaml_to_libi import yaml_to_ast
from custom_components.libi.const import (
    AI_MODE_CLOUD,
    AI_MODE_NONE,
    CONF_AI_MODE,
    CONF_CLOUD_API_KEY,
    CONF_CLOUD_MODEL,
    CONF_CLOUD_PROVIDER,
    DOMAIN,
)

SECRET = "sk-test-secret-123456"

PLAN = {
    "reply": "Pick the buttons and the lights.",
    "level": "automation",
    "name": "Salon light 10 minutes",
    "roles": [
        {"id": "trigger_buttons", "label": "Buttons", "purpose": "trigger",
         "domains": ["input_button", "event", "mqtt_thing"], "device_classes": [],
         "keywords": ["button", "כפתור"], "area_keywords": []},
        {"id": "salon_lights", "label": "Salon lights", "purpose": "target",
         "domains": ["light"], "device_classes": [], "keywords": ["light"],
         "area_keywords": ["salon", "סלון"]},
    ],
    "questions": [{"id": "duration", "text": "How long?", "choices": ["10 minutes"]}],
}

GOOD_BUILD = {
    "reply": "Done.", "level": "automation", "name": "Salon light 10 minutes",
    "description": "A button turns the salon light on for ten minutes.",
    "config": {
        "mode": "restart",
        "triggers": [{"trigger": "state", "entity_id": "role:trigger_buttons"}],
        "conditions": [],
        "actions": [
            {"action": "light.turn_on", "target": {"entity_id": "role:salon_lights"}},
            {"delay": {"minutes": 10}},
            {"action": "light.turn_off", "target": {"entity_id": "role:salon_lights"}},
        ],
    },
    "ui_card": {}, "notes": [],
}


@pytest.fixture
async def home(hass: HomeAssistant):
    await async_setup_component(hass, "homeassistant", {})
    hass.states.async_set("input_button.door_button", "unknown", {"friendly_name": "Door button"})
    hass.states.async_set("event.remote_button", "unknown", {"friendly_name": "Remote button"})
    hass.states.async_set("light.salon_ceiling", "off", {"friendly_name": "Salon ceiling"})
    hass.states.async_set("light.salon_lamp", "off", {"friendly_name": "סלון מנורה"})
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    hass.states.async_set("switch.garden_valve", "off", {"friendly_name": "Garden valve"})
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Front door"})
    for svc in ("turn_on", "turn_off"):
        async_mock_service(hass, "light", svc)
        async_mock_service(hass, "switch", svc)
    async_mock_service(hass, "lock", "unlock")
    async_mock_service(hass, "shell_command", "danger")
    async_mock_service(hass, "notify", "notify")
    return hass


@pytest.fixture
async def libi_ai(hass, home, config_dir):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_AI_MODE: AI_MODE_CLOUD, CONF_CLOUD_PROVIDER: "gemini",
        CONF_CLOUD_API_KEY: SECRET, CONF_CLOUD_MODEL: "gemini-x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


SELECTED = {"trigger_buttons": ["input_button.door_button", "event.remote_button"],
            "salon_lights": ["light.salon_ceiling"]}


def _plan(hass):
    return ai.clean_plan(hass, copy.deepcopy(PLAN))


async def test_plan_drops_domains_that_do_not_exist(hass, home):
    plan = _plan(hass)
    assert plan["roles"][0]["domains"] == ["input_button", "event"]


async def test_candidates_come_from_the_registry_and_prefer_the_area(hass, home):
    plan = _plan(hass)
    lights = ai.find_candidates(hass, plan["roles"][1])
    ids = [c["entity_id"] for c in lights["items"]]
    assert lights["exact"] is True
    assert set(ids) == {"light.salon_ceiling", "light.salon_lamp"}  # by English and by Hebrew name
    buttons = ai.find_candidates(hass, plan["roles"][0])
    assert {c["entity_id"] for c in buttons["items"]} == {"input_button.door_button", "event.remote_button"}


async def test_good_draft_substitutes_the_users_picks(hass, home):
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, copy.deepcopy(GOOD_BUILD))
    assert out["ok"], out["errors"]
    auto = out["auto"]
    assert auto["triggers"][0]["entity_id"] == ["input_button.door_button", "event.remote_button"]
    assert auto["actions"][0]["target"]["entity_id"] == "light.salon_ceiling"
    assert auto["id"].startswith("libi_ai_")
    assert out["sensitive"] == []


def _with(change):
    build = copy.deepcopy(GOOD_BUILD)
    change(build["config"])
    return build


@pytest.mark.parametrize("change, expect", [
    (lambda c: c["actions"].append({"action": "light.turn_on", "target": {"entity_id": "light.kitchen"}}),
     "did not pick"),
    (lambda c: c["actions"].append({"action": "light.turn_on", "target": {"device_id": "abc123"}}),
     "device_id"),
    (lambda c: c["actions"].append({"action": "shell_command.danger"}), "not allowed"),
    (lambda c: c["actions"].append({"action": "light.turn_on", "target": {"entity_id": "role:trigger_buttons"}}),
     "is not a light"),
    (lambda c: c["triggers"].append({"trigger": "mqtt", "topic": "x"}), "not allowed"),
    (lambda c: c["conditions"].append({"condition": "template",
                                       "value_template": "{{ is_state('light.kitchen', 'on') }}"}),
     "did not pick"),
    (lambda c: c["actions"].append({"action": "light.turn_on", "target": {"entity_id": "all"}}), "'all'"),
    (lambda c: c["actions"].append({"action": "light.flash_everything", "target": {"entity_id": "role:salon_lights"}}),
     "does not exist"),
])
async def test_bad_drafts_are_rejected(hass, home, change, expect):
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, _with(change))
    assert out["ok"] is False
    assert any(expect in e for e in out["errors"]), out["errors"]


async def test_sensitive_devices_are_flagged(hass, home):
    plan = ai.clean_plan(hass, {**copy.deepcopy(PLAN), "roles": PLAN["roles"] + [
        {"id": "door_lock", "label": "Lock", "purpose": "target", "domains": ["lock"],
         "device_classes": [], "keywords": [], "area_keywords": []}]})
    sel = {**SELECTED, "door_lock": ["lock.front_door"]}
    out = await ai.async_build_draft(hass, plan, sel, _with(lambda c: c["actions"].append(
        {"action": "lock.unlock", "target": {"entity_id": "role:door_lock"}})))
    assert out["ok"], out["errors"]
    assert out["sensitive"] == ["lock.front_door"]


async def test_selection_must_exist_and_fit_the_role(hass, home):
    plan = _plan(hass)
    sel, errors = ai.clean_selections(hass, plan, {"trigger_buttons": ["light.kitchen", "input_button.nope"],
                                                   "salon_lights": ["light.salon_ceiling"]})
    assert "trigger_buttons" not in sel
    assert any("does not fit" in e for e in errors)
    assert any("does not exist" in e for e in errors)


async def test_status_never_contains_the_key(hass, libi_ai, hass_ws_client):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/ai_status"})
    res = await client.receive_json()
    assert res["result"]["configured"] is True
    assert res["result"]["provider"] == "gemini"
    assert SECRET not in str(res)


async def test_plan_and_build_over_websocket(hass, libi_ai, hass_ws_client):
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(PLAN)):
        await client.send_json_auto_id({"type": "libi/ai_plan",
                                        "messages": [{"role": "user", "content": "button -> salon light 10 min"}]})
        planned = (await client.receive_json())["result"]
    assert set(planned["candidates"]) == {"trigger_buttons", "salon_lights"}

    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GOOD_BUILD)):
        await client.send_json_auto_id({"type": "libi/ai_build", "messages": [{"role": "user", "content": "x"}],
                                        "plan": planned["plan"], "selections": SELECTED,
                                        "answers": {"duration": "10 minutes"}})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    assert built["net"]["level"] == "automation"
    assert built["net"]["source"] == "draft"
    # A draft is never written: no automations.yaml appears.
    assert not os.path.exists(hass.config.path("automations.yaml"))


async def test_home_assistant_validator_has_the_last_word(hass, home):
    """Passes LIBI's own checks, but a numeric_state trigger needs above or below."""
    bad = _with(lambda c: c["triggers"].__setitem__(0, {"trigger": "numeric_state",
                                                        "entity_id": "role:trigger_buttons"}))
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, bad)
    assert out["ok"] is False
    assert any("Home Assistant rejected" in e for e in out["errors"]), out["errors"]


async def test_build_with_a_foreign_entity_returns_no_net(hass, libi_ai, hass_ws_client):
    client = await hass_ws_client(hass)
    bad = _with(lambda c: c["actions"].append({"action": "light.turn_on", "target": {"entity_id": "light.kitchen"}}))
    with patch.object(ai, "async_llm_json", return_value=bad):
        await client.send_json_auto_id({"type": "libi/ai_build", "messages": [{"role": "user", "content": "x"}],
                                        "plan": PLAN, "selections": SELECTED})
        res = (await client.receive_json())["result"]
    assert res["ok"] is False
    assert "net" not in res


async def test_non_admin_cannot_use_the_ai(hass, libi_ai, hass_ws_client, hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "libi/ai_plan", "messages": [{"role": "user", "content": "x"}]})
    res = await client.receive_json()
    assert res["error"]["code"] == "unauthorized"


async def test_not_configured(hass, home, config_dir, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_AI_MODE: AI_MODE_NONE})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/ai_plan", "messages": [{"role": "user", "content": "x"}]})
    res = await client.receive_json()
    assert res["error"]["code"] == "not_configured"


async def test_options_flow_switches_to_cloud_and_keeps_the_key(hass, libi_ai, aioclient_mock):
    aioclient_mock.get("https://api.openai.com/v1/models", json={"data": [{"id": "gpt-4o"}]})
    result = await hass.config_entries.options.async_init(libi_ai.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_AI_MODE: AI_MODE_CLOUD})
    assert result["step_id"] == "cloud"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CLOUD_PROVIDER: "openai", CONF_CLOUD_MODEL: "gpt-4o"})
    assert result["type"] == "create_entry"
    settings = ai.ai_settings(hass)
    assert settings[CONF_CLOUD_PROVIDER] == "openai"
    assert settings[CONF_CLOUD_API_KEY] == SECRET


async def test_llm_client_ollama(hass, aioclient_mock):
    aioclient_mock.post("http://ollama.local:11434/api/chat",
                        json={"message": {"content": '{"reply": "hi"}'}})
    settings = {CONF_AI_MODE: "Local AI", "local_url": "http://ollama.local:11434/", "local_model": "gemma"}
    out = await ai.async_llm_json(hass, settings, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    assert out == {"reply": "hi"}
    body = aioclient_mock.mock_calls[0][2]
    assert body["model"] == "gemma" and body["stream"] is False and body["format"] == {"type": "object"}


async def test_llm_client_gemini_falls_back_to_json_mode(hass, aioclient_mock):
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    aioclient_mock.post(url, status=400)
    settings = {CONF_AI_MODE: AI_MODE_CLOUD, CONF_CLOUD_PROVIDER: "gemini",
                CONF_CLOUD_API_KEY: SECRET, CONF_CLOUD_MODEL: "gemini-x"}
    with pytest.raises(ai.AiError) as err:
        await ai.async_llm_json(hass, settings, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    # first json_schema, then the plain JSON mode; the key only ever in the header
    assert [c[2]["response_format"]["type"] for c in aioclient_mock.mock_calls] == ["json_schema", "json_object"]
    assert all(c[3]["Authorization"] == f"Bearer {SECRET}" for c in aioclient_mock.mock_calls)
    assert SECRET not in str(err.value)
    assert "googleapis" not in str(err.value)


async def test_llm_client_reads_openai_answers(hass, aioclient_mock):
    aioclient_mock.post("https://api.openai.com/v1/chat/completions",
                        json={"choices": [{"message": {"content": '```json\n{"reply": "ok"}\n```'}}]})
    settings = {CONF_AI_MODE: AI_MODE_CLOUD, CONF_CLOUD_PROVIDER: "openai",
                CONF_CLOUD_API_KEY: SECRET, CONF_CLOUD_MODEL: "gpt-4o"}
    out = await ai.async_llm_json(hass, settings, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    assert out == {"reply": "ok"}


# ---------------------------------------------------------------------------------------- the canvas

GARDEN_NOW = {  # what the garden net does today: a button, then 50 litres
    "id": "garden_watering", "alias": "Garden watering", "mode": "single",
    "triggers": [{"trigger": "state", "entity_id": "input_button.garden_button"}],
    "conditions": [],
    "actions": [
        {"variables": {"start": "{{ states('sensor.water_meter') | float(0) }}"}},
        {"action": "switch.turn_on", "target": {"entity_id": "switch.garden_valve"}},
        {"wait_template": "{{ states('sensor.water_meter') | float(0) - start >= 50 }}"},
        {"action": "switch.turn_off", "target": {"entity_id": "switch.garden_valve"}},
    ],
}

GARDEN_PLAN = {
    "reply": "I will change the garden watering.", "intent": "modify", "target_net": "n_garden",
    "level": "automation", "name": "Garden watering",
    "roles": [
        {"id": "garden_valve", "label": "Garden valve", "purpose": "target", "domains": ["switch", "valve"],
         "device_classes": [], "keywords": ["garden", "valve"], "area_keywords": []},
        {"id": "water_meter", "label": "Water meter", "purpose": "measure", "domains": ["sensor"],
         "device_classes": ["water"], "keywords": ["water"], "area_keywords": []},
        {"id": "weather", "label": "Weather", "purpose": "condition", "domains": ["weather"],
         "device_classes": [], "keywords": ["weather"], "area_keywords": []},
    ],
    "questions": [],
}

W = "role:weather"
GARDEN_NEW = {
    "reply": "Done.", "level": "automation", "name": "Garden watering",
    "description": "Sun, Tue, Thu and Sat at 05:00, 200 litres, at most one hour, not when it rains.",
    "config": {
        "mode": "single",
        "triggers": [{"trigger": "time", "at": "05:00:00"}],
        "conditions": [{"condition": "time", "weekday": ["sun", "tue", "thu", "sat"]}],
        "actions": [
            {"action": "weather.get_forecasts", "target": {"entity_id": W},
             "data": {"type": "daily"}, "response_variable": "forecast"},
            {"condition": "template",
             "value_template": "{{ forecast['" + W + "'].forecast[0].condition not in ['rainy', 'pouring', 'lightning-rainy'] }}"},
            {"variables": {"start": "{{ states('role:water_meter') | float(0) }}"}},
            {"action": "switch.turn_on", "target": {"entity_id": "role:garden_valve"}},
            {"wait_template": "{{ states('role:water_meter') | float(0) - start >= 200 }}",
             "timeout": "01:00:00", "continue_on_timeout": True},
            {"action": "switch.turn_off", "target": {"entity_id": "role:garden_valve"}},
            {"if": [{"condition": "template", "value_template": "{{ not wait.completed }}"}],
             "then": [{"action": "notify.notify", "data": {"message": "The garden got less than 200 litres in an hour."}}]},
        ],
    },
    "ui_card": {}, "notes": [],
}


@pytest.fixture
async def garden(hass, libi_ai):
    hass.states.async_set("input_button.garden_button", "unknown", {"friendly_name": "Garden button"})
    hass.states.async_set("switch.garden_valve", "off", {"friendly_name": "Garden valve"})
    hass.states.async_set("sensor.water_meter", "1200", {"friendly_name": "Water meter", "device_class": "water",
                                                         "unit_of_measurement": "L"})
    hass.states.async_set("weather.home", "sunny", {"friendly_name": "Home"})
    async_mock_service(hass, "weather", "get_forecasts")
    net = yaml_to_ast(hass, copy.deepcopy(GARDEN_NOW))
    net["id"] = "n_garden"
    return net


async def test_question_about_the_canvas_gets_an_answer_only(hass, garden, hass_ws_client):
    client = await hass_ws_client(hass)
    answer = {"reply": "It opens the garden valve for 50 litres when you press the button.", "intent": "answer",
              "target_net": "", "level": "automation", "name": "",
              "roles": [{"id": "x", "label": "x", "purpose": "target", "domains": ["switch"],
                         "device_classes": [], "keywords": [], "area_keywords": []}], "questions": []}
    with patch.object(ai, "async_llm_json", return_value=answer) as llm:
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden],
                                        "messages": [{"role": "user", "content": "what does the garden net do?"}]})
        res = (await client.receive_json())["result"]
    sent = llm.call_args.args[3][-1]["content"]
    assert "NETS ON THE CANVAS" in sent and "n_garden" in sent and "switch.garden_valve" in sent
    assert res["plan"]["intent"] == "answer"
    assert res["plan"]["roles"] == [] and res["candidates"] == {}


async def test_nets_are_not_sent_when_not_shared(hass, garden, hass_ws_client):
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_PLAN)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_plan",
                                        "messages": [{"role": "user", "content": "change the garden"}]})
        res = (await client.receive_json())["result"]
    assert "NETS ON THE CANVAS" not in llm.call_args.args[3][-1]["content"]
    # Without the canvas there is no net to change, so it becomes new logic.
    assert res["plan"]["intent"] == "create" and res["plan"]["target_net"] == ""


async def test_garden_change_end_to_end(hass, garden, hass_ws_client):
    """The user's own example: from a button and 50 litres to four mornings a week, 200 litres,
    at most an hour, and not when it rains - validated by LIBI and by Home Assistant."""
    client = await hass_ws_client(hass)
    request = [{"role": "user", "content": "instead of the button: Sun Tue Thu Sat at 05:00, 200 litres, "
                                           "stop after an hour, and not when it rains"}]
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_PLAN)):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "messages": request})
        planned = (await client.receive_json())["result"]
    assert planned["plan"]["intent"] == "modify" and planned["plan"]["target_net"] == "n_garden"
    # The devices the net already uses are ticked; the weather entity is new, so it is not.
    assert planned["preselect"] == {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"]}
    assert any(i.get("current") for i in planned["candidates"]["garden_valve"]["items"])
    assert "weather.home" in [i["entity_id"] for i in planned["candidates"]["weather"]["items"]]

    selections = {**planned["preselect"], "weather": ["weather.home"]}
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_NEW)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "messages": request,
                                        "plan": planned["plan"], "selections": selections})
        built = (await client.receive_json())["result"]
    assert "CURRENT NET" in llm.call_args.args[3][-1]["content"]
    assert built["ok"], built.get("errors")
    assert built["intent"] == "modify" and built["target_net"] == "n_garden"
    # Checked on the parsed YAML: in the text, quotes inside a quoted string are doubled.
    doc = yaml.safe_load(built["yaml"])
    assert doc["triggers"] == [{"trigger": "time", "at": "05:00:00"}]
    assert doc["conditions"][0]["weekday"] == ["sun", "tue", "thu", "sat"]
    acts = doc["actions"]
    assert acts[0]["action"] == "weather.get_forecasts" and acts[0]["target"]["entity_id"] == "weather.home"
    assert "forecast['weather.home']" in acts[1]["value_template"] and "rainy" in acts[1]["value_template"]
    assert "sensor.water_meter" in acts[2]["variables"]["start"]
    assert acts[3]["target"]["entity_id"] == "switch.garden_valve"
    assert ">= 200" in acts[4]["wait_template"] and acts[4]["continue_on_timeout"] is True
    assert str(acts[4]["timeout"]) in ("01:00:00", "3600")
    assert acts[5]["action"] == "switch.turn_off"
    assert "role:" not in built["yaml"]  # every role filled with the user's pick
    # The new garden logic survives the ladder drawing unchanged, so SAVE & COMPILE writes it as built.
    assert built["round_trip"]["ok"], built["round_trip"]
    # Saving the change updates the same automation.
    assert built["net"]["ha_id"] == "garden_watering"


async def test_weather_forecast_only_on_a_weather_entity(hass, garden):
    plan = ai.clean_plan(hass, copy.deepcopy(GARDEN_PLAN), {"n_garden"})
    sel = {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"], "weather": ["weather.home"]}
    bad = copy.deepcopy(GARDEN_NEW)
    bad["config"]["actions"][0]["target"]["entity_id"] = "role:garden_valve"
    out = await ai.async_build_draft(hass, plan, sel, bad)
    assert out["ok"] is False
    assert any("is not a weather" in e for e in out["errors"]), out["errors"]


async def test_target_must_be_a_net_on_the_canvas(hass, garden):
    plan = ai.clean_plan(hass, {**copy.deepcopy(GARDEN_PLAN), "target_net": "n_someone_else"}, {"n_garden"})
    assert plan["intent"] == "create" and plan["target_net"] == ""


# ---------------------------------------------------------------------------------------- the prompt and the context

def test_the_prompt_names_every_rule_the_validator_checks():
    """The rules in the prompt are generated from the validator's lists. If a rule is added to the
    validator, this fails until the prompt says it too - and the prompt never offers the old syntax."""
    prompt = ai.BUILD_SYSTEM
    for name in ai.TRIGGERS | ai.CONDITIONS | ai.ENTITY_SERVICE_DOMAINS | ai.FORBIDDEN_KEYS:
        assert name in prompt, name
    for service in ai.READ_SERVICES | ai.MESSAGE_SERVICES | ai.GENERIC_SERVICES:
        assert service in prompt, service
    for domain in ai.MESSAGE_DOMAINS:
        assert f"{domain}.*" in prompt, domain
    for domain, services in ai.RESTRICTED.items():
        assert f"{domain}: only {', '.join(sorted(services))}" in prompt, domain
    keys_line = next(line for line in prompt.splitlines() if line.startswith("- Allowed keys"))
    for key in ai.KNOWN_KEYS - ai.LEGACY_KEYS:
        assert key in keys_line, key
    for legacy in ai.LEGACY_KEYS:
        assert f" {legacy}," not in keys_line and f" {legacy}." not in keys_line, legacy
    assert "{RULES}" not in prompt
    assert 'never "platform"' in prompt and '"state": "on" (not "to")' in prompt


async def test_valid_home_assistant_keys_are_accepted(hass, home):
    build = copy.deepcopy(GOOD_BUILD)
    build["config"]["triggers"] = [{"trigger": "state", "entity_id": "role:trigger_buttons",
                                    "not_from": ["unavailable"], "not_to": ["unavailable"]}]
    build["config"]["conditions"] = [{"condition": "sun", "after": "sunset", "after_offset": "-00:30:00"}]
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, build)
    assert out["ok"], out["errors"]


async def test_only_the_nets_on_the_page_are_sent_as_yaml(hass, garden, hass_ws_client):
    """With sharing on, the YAML the model gets is the nets open in the LIBI page and nothing else:
    an automation that is only in automations.yaml - not open in LIBI - never reaches the model."""
    import pathlib
    d = pathlib.Path(hass.config.config_dir)
    (d / "automations.yaml").write_text(
        "- id: porch\n  alias: Porch light not on the page\n  triggers: []\n  actions: []\n", encoding="utf-8")
    (d / "scripts.yaml").write_text("bedtime:\n  alias: Bedtime script\n  sequence: []\n", encoding="utf-8")
    (d / "scenes.yaml").write_text("- id: movie\n  name: Movie scene\n  entities: {}\n", encoding="utf-8")
    hass.states.async_set("input_number.garden_litres", "200", {"friendly_name": "Garden litres", "min": 0,
                                                                 "max": 500, "unit_of_measurement": "L"})
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_PLAN)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": "change the garden"}]})
        await client.receive_json()
    sent = llm.call_args.args[3][-1]["content"]
    # the net on the page, as YAML
    assert "NETS ON THE CANVAS" in sent and "n_garden" in sent and "switch.garden_valve" in sent
    # nothing from the files
    for absent in ("Porch light not on the page", "Bedtime script", "Movie scene", "EXISTING CONFIGURATION"):
        assert absent not in sent, absent
    # the helpers are entities, not YAML, and are shared
    assert "HELPERS:" in sent and "input_number.garden_litres" in sent

    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_PLAN)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_plan",
                                        "messages": [{"role": "user", "content": "change the garden"}]})
        await client.receive_json()
    quiet = llm.call_args.args[3][-1]["content"]
    assert "NETS ON THE CANVAS" not in quiet and "HELPERS:" not in quiet


async def test_the_build_gets_the_devices_with_units(hass, garden, hass_ws_client):
    client = await hass_ws_client(hass)
    plan = ai.clean_plan(hass, copy.deepcopy(GARDEN_PLAN), {"n_garden"})
    selections = {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"],
                  "weather": ["weather.home"]}
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_NEW)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": "x"}],
                                        "plan": plan, "selections": selections})
        built = (await client.receive_json())["result"]
    sent = llm.call_args.args[3][-1]["content"]
    assert "DEVICES (per role" in sent
    assert "* sensor.water_meter" in sent and "1200 L" in sent and "[water]" in sent
    assert "EXISTING CONFIGURATION" not in sent
    assert built["ok"], built.get("errors")


# ---------------------------------------------------------------------------------------- helpers the AI proposes

PROPOSED = [
    {"role": "day_sun", "domain": "input_boolean", "name": "Garden Sunday", "settings": {"icon": "mdi:calendar"}},
    {"role": "start_time", "domain": "input_datetime", "name": "Garden start", "settings": {"has_time": True, "has_date": False}},
    {"role": "litres", "domain": "input_number", "name": "Garden litres",
     "settings": {"min": 0, "max": 500, "step": 10, "initial": 200, "unit_of_measurement": "L", "mode": "box"}},
    {"role": "use_weather", "domain": "input_boolean", "name": "Garden depends on weather", "settings": {}},
    # dropped: not a helper LIBI may create, an impossible range, an unknown setting kept out
    {"role": "evil", "domain": "shell_command", "name": "Run this", "settings": {"command": "rm -rf /"}},
    {"role": "bad_range", "domain": "input_number", "name": "Broken", "settings": {"min": 10, "max": 5}},
    {"role": "odd", "domain": "input_text", "name": "Note", "settings": {"max": 50, "secret_field": "x"}},
]


def test_proposed_helpers_are_checked(hass):
    roles = []
    kept, roles = ai.clean_new_helpers(copy.deepcopy(PROPOSED), roles)
    domains = {h["role"]: h["domain"] for h in kept}
    assert domains == {"day_sun": "input_boolean", "start_time": "input_datetime", "litres": "input_number",
                       "use_weather": "input_boolean", "odd": "input_text"}
    litres = next(h for h in kept if h["role"] == "litres")
    assert litres["settings"] == {"min": 0, "max": 500, "step": 10, "initial": 200, "unit_of_measurement": "L", "mode": "box"}
    assert "secret_field" not in next(h for h in kept if h["role"] == "odd")["settings"]
    # every kept helper fills a role of its own domain
    assert {r["id"]: r["domains"] for r in roles}["litres"] == ["input_number"]


async def test_the_proposal_creates_real_helpers(hass, libi_ai, hass_ws_client):
    """The settings LIBI keeps are exactly what Home Assistant's <domain>/create accepts, and the new
    entity is <domain>.<returned id> - checked against a real Home Assistant."""
    for domain in ("input_boolean", "input_number", "input_datetime", "input_text"):
        assert await async_setup_component(hass, domain, {})
    kept, _roles = ai.clean_new_helpers(copy.deepcopy(PROPOSED), [])
    client = await hass_ws_client(hass)
    for item in kept:
        await client.send_json_auto_id({"type": f"{item['domain']}/create", "name": item["name"], **item["settings"]})
        res = await client.receive_json()
        assert res["success"], (item, res)
        await hass.async_block_till_done()
        eid = f"{item['domain']}.{res['result']['id']}"
        assert hass.states.get(eid) is not None, eid
    assert hass.states.get("input_number.garden_litres").attributes["max"] == 500
    assert hass.states.get("input_datetime.garden_start").attributes["has_date"] is False


async def test_a_plan_carries_the_checked_helpers(hass, garden, hass_ws_client):
    plan = {**copy.deepcopy(GARDEN_PLAN), "new_helpers": copy.deepcopy(PROPOSED)}
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": "let me set the days, time and litres"}]})
        res = (await client.receive_json())["result"]
    names = [h["name"] for h in res["plan"]["new_helpers"]]
    assert "Garden litres" in names and "Run this" not in names and "Broken" not in names
    assert "litres" in [r["id"] for r in res["plan"]["roles"]]


def test_the_plan_prompt_lists_every_helper_kind():
    for domain, fields in ai.HELPER_SPEC.items():
        assert domain in ai.PLAN_SYSTEM, domain
        for field in fields:
            assert field in ai.PLAN_SYSTEM, (domain, field)
    assert "{HELPER_RULES}" not in ai.PLAN_SYSTEM


# ---------------------------------------------------------------------------------------- the settings card

DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


async def _garden_with_helpers(hass):
    """The garden net plus the helpers the user sets on the screen: days, start time, litres, weather."""
    for d in DAYS:
        hass.states.async_set(f"input_boolean.garden_{d}", "off", {"friendly_name": f"Water on {d.title()}"})
    hass.states.async_set("input_datetime.garden_start", "05:00:00", {"friendly_name": "Start time", "has_time": True,
                                                                      "has_date": False})
    hass.states.async_set("input_number.garden_litres", "200", {"friendly_name": "Litres", "min": 0, "max": 500})
    hass.states.async_set("input_boolean.garden_weather", "on", {"friendly_name": "Skip when it rains"})
    roles = [
        {"id": "start_time", "label": "Start time", "purpose": "trigger", "domains": ["input_datetime"],
         "device_classes": [], "keywords": [], "area_keywords": []},
        {"id": "litres", "label": "Litres", "purpose": "condition", "domains": ["input_number"],
         "device_classes": [], "keywords": [], "area_keywords": []},
        {"id": "use_weather", "label": "Weather", "purpose": "condition", "domains": ["input_boolean"],
         "device_classes": [], "keywords": [], "area_keywords": []},
    ] + [{"id": f"day_{d}", "label": d, "purpose": "condition", "domains": ["input_boolean"],
          "device_classes": [], "keywords": [], "area_keywords": []} for d in reversed(DAYS)]  # out of order on purpose
    plan = ai.clean_plan(hass, {**copy.deepcopy(GARDEN_PLAN), "roles": GARDEN_PLAN["roles"] + roles}, {"n_garden"})
    selections = {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"],
                  "weather": ["weather.home"], "start_time": ["input_datetime.garden_start"],
                  "litres": ["input_number.garden_litres"], "use_weather": ["input_boolean.garden_weather"],
                  **{f"day_{d}": [f"input_boolean.garden_{d}"] for d in DAYS}}
    day_checks = [{"condition": "and", "conditions": [
        {"condition": "time", "weekday": [d]},
        {"condition": "state", "entity_id": f"role:day_{d}", "state": "on"}]} for d in DAYS]
    build = copy.deepcopy(GARDEN_NEW)
    cfg = build["config"]
    cfg["triggers"] = [{"trigger": "time", "at": "role:start_time"}]
    cfg["conditions"] = [{"condition": "or", "conditions": day_checks}]
    cfg["actions"][1] = {"condition": "or", "conditions": [
        {"condition": "state", "entity_id": "role:use_weather", "state": "off"},
        {"condition": "template", "value_template":
            "{{ forecast['role:weather'].forecast[0].condition not in ['rainy', 'pouring', 'lightning-rainy'] }}"}]}
    cfg["actions"][4]["wait_template"] = ("{{ states('role:water_meter') | float(0) - start >= "
                                          "states('role:litres') | float(0) }}")
    build["ui_card"] = {}
    return plan, selections, build


async def test_the_settings_card_comes_with_the_logic(hass, garden):
    """The model gave no card: LIBI builds one from the helpers the user picked, so the days, the
    time, the litres and the weather choice can be set from a dashboard."""
    plan, selections, build = await _garden_with_helpers(hass)
    out = await ai.async_build_draft(hass, plan, selections, build)
    assert out["ok"], out["errors"]
    card = yaml.safe_load(out["card_yaml"])
    assert card["type"] == "entities" and card["title"] == "Garden watering"
    rows = card["entities"]
    ids = [r.get("entity") for r in rows if "entity" in r]
    assert ids[:3] == ["input_datetime.garden_start", "input_number.garden_litres", "input_boolean.garden_weather"]
    assert {"type": "section", "label": "Days"} in rows
    assert ids[3:] == [f"input_boolean.garden_{d}" for d in DAYS]  # Sunday to Saturday, in week order
    assert "role:" not in out["card_yaml"]
    # the valve, the meter and the weather entity are not settings, so they are not on the card
    assert "switch.garden_valve" not in out["card_yaml"] and "sensor.water_meter" not in out["card_yaml"]
    # the logic itself reads the same helpers
    assert "input_datetime.garden_start" in out["yaml"] and "input_number.garden_litres" in out["yaml"]
    # and the ladder drawing holds it unchanged, so SAVE & COMPILE writes what was built
    from custom_components.libi.libi_to_yaml import verify_round_trip
    report = verify_round_trip(hass, out["auto"])
    assert report["ok"], report["issues"]


async def test_a_card_from_the_model_is_kept(hass, garden):
    plan, selections, build = await _garden_with_helpers(hass)
    build["ui_card"] = {"type": "tile", "entity": "role:litres"}
    out = await ai.async_build_draft(hass, plan, selections, build)
    assert out["ok"], out["errors"]
    assert yaml.safe_load(out["card_yaml"]) == {"type": "tile", "entity": "input_number.garden_litres"}


async def test_no_card_without_helpers(hass, home):
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, copy.deepcopy(GOOD_BUILD))
    assert out["ok"], out["errors"]
    assert out["card_yaml"] == ""
