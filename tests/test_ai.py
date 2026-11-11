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
import json
import os
from unittest.mock import patch

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

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
# [ADDED 2026-11-01] The user's own words, in Hebrew as they wrote them, are data (tests/fixtures/user_text_he.json):
# English only in the code (CLAUDE.md RULE 17). LIBI must read them as written - the quote marks, a letter in front of
# "NET 1", the names of the user's helpers - so the tests use them as they are.
with open(os.path.join(os.path.dirname(__file__), "fixtures", "user_text_he.json"), encoding="utf-8") as _fixture:
    HE = json.load(_fixture)


def _model(*answers):
    """[v3.62.0] The model, answering in turn (the last answer again once they run out), keeping a copy of what
    each call was sent: the build sends the conversation on with what LIBI found wrong."""
    sent = []

    async def llm(_hass, _settings, _system, messages, _schema):
        sent.append(copy.deepcopy(messages))
        return copy.deepcopy(answers[min(len(sent), len(answers)) - 1])
    return llm, sent

PLAN = {
    "reply": "Pick the buttons and the lights.",
    "level": "automation",
    "name": "Salon light 10 minutes",
    "roles": [
        {"id": "trigger_buttons", "label": "Buttons", "purpose": "trigger",
         "domains": ["input_button", "event", "mqtt_thing"], "device_classes": [],
         "keywords": ["button", HE["button"]], "area_keywords": []},
        {"id": "salon_lights", "label": "Salon lights", "purpose": "target",
         "domains": ["light"], "device_classes": [], "keywords": ["light"],
         "area_keywords": ["salon", HE["salon"]]},
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
    hass.states.async_set("light.salon_lamp", "off", {"friendly_name": HE["salon_lamp"]})
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


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI = {CONF_AI_MODE: AI_MODE_CLOUD, CONF_CLOUD_PROVIDER: "gemini",
          CONF_CLOUD_API_KEY: SECRET, CONF_CLOUD_MODEL: "gemini-x"}
OVERLOADED = [{"error": {"code": 503, "status": "UNAVAILABLE",
                         "message": "The model is overloaded. Please try again later."}}]


async def test_llm_client_asks_again_while_the_model_is_busy(hass, aioclient_mock):
    """A 503 from a busy model is asked again after a short wait, and the answer that follows is used."""
    answers = [AiohttpClientMockResponse("post", GEMINI_URL, status=503, json=OVERLOADED),
               AiohttpClientMockResponse("post", GEMINI_URL, json={"choices": [{"message": {"content": '{"reply": "ok"}'}}]})]

    async def next_answer(method, url, data):
        return answers.pop(0)

    aioclient_mock.post(GEMINI_URL, side_effect=next_answer)
    with patch.object(ai, "RETRY_DELAYS", (0, 0)):
        out = await ai.async_llm_json(hass, GEMINI, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    assert out == {"reply": "ok"}
    assert aioclient_mock.call_count == 2
    # the same request both times
    assert aioclient_mock.mock_calls[0][2] == aioclient_mock.mock_calls[1][2]


async def test_llm_client_explains_a_model_that_stays_busy(hass, aioclient_mock):
    aioclient_mock.post(GEMINI_URL, status=503, json=OVERLOADED)
    with patch.object(ai, "RETRY_DELAYS", (0, 0)), pytest.raises(ai.AiError) as err:
        await ai.async_llm_json(hass, GEMINI, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    assert aioclient_mock.call_count == 3  # the first try and two more
    text = str(err.value)
    assert "busy or unavailable right now (503)" in text
    assert "The model is overloaded" in text
    assert SECRET not in text and "googleapis" not in text


async def test_llm_client_does_not_retry_a_wrong_model(hass, aioclient_mock):
    aioclient_mock.post(GEMINI_URL, status=404, json={"error": {"message": f"models/gemini-x is not found, key={SECRET}"}})
    with patch.object(ai, "RETRY_DELAYS", (0, 0)), pytest.raises(ai.AiError) as err:
        await ai.async_llm_json(hass, GEMINI, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    assert aioclient_mock.call_count == 1
    assert "does not know this model (404)" in str(err.value)
    assert SECRET not in str(err.value)


async def test_llm_client_local_server_busy(hass, aioclient_mock):
    aioclient_mock.post("http://ollama.local:11434/api/chat", status=500, json={"error": "out of memory"})
    settings = {CONF_AI_MODE: "Local AI", "local_url": "http://ollama.local:11434", "local_model": "gemma"}
    with patch.object(ai, "RETRY_DELAYS", (0,)), pytest.raises(ai.AiError) as err:
        await ai.async_llm_json(hass, settings, "sys", [{"role": "user", "content": "x"}], {"type": "object"})
    assert aioclient_mock.call_count == 2
    assert str(err.value).startswith("The local AI server is busy") and "out of memory" in str(err.value)


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

# [ADDED 2026-10-29] The same request the ladder way. The user: "see how a YAML should look" - one trigger with an id
# for every event and one choose with an option per trigger id, as in their own automations. Nothing waits in a run.
GARDEN_LADDER = {
    "reply": "Done.", "level": "automation", "name": "Garden watering",
    "description": "Sun, Tue, Thu and Sat at 05:00, 200 litres, at most one hour, not when it rains.",
    "config": {
        "mode": "queued",
        "triggers": [{"trigger": "time", "at": "05:00:00", "id": "start"},
                     {"trigger": "numeric_state", "entity_id": "role:water_meter", "above": 200, "id": "amount_reached"},
                     {"trigger": "state", "entity_id": "role:garden_valve", "to": "on", "for": {"hours": 1},
                      "id": "time_limit"}],
        "conditions": [],
        "actions": [{"choose": [
            {"conditions": [{"condition": "trigger", "id": "start"},
                            {"condition": "time", "weekday": ["sun", "tue", "thu", "sat"]}],
             "sequence": [
                 {"action": "weather.get_forecasts", "target": {"entity_id": W},
                  "data": {"type": "daily"}, "response_variable": "forecast"},
                 {"condition": "template", "value_template":
                     "{{ forecast['" + W + "'].forecast[0].condition not in ['rainy', 'pouring', 'lightning-rainy'] }}"},
                 {"action": "switch.turn_on", "target": {"entity_id": "role:garden_valve"}}]},
            {"conditions": [{"condition": "trigger", "id": "amount_reached"},
                            {"condition": "state", "entity_id": "role:garden_valve", "state": "on"}],
             "sequence": [{"action": "switch.turn_off", "target": {"entity_id": "role:garden_valve"}}]},
            {"conditions": [{"condition": "trigger", "id": "time_limit"}],
             "sequence": [{"action": "switch.turn_off", "target": {"entity_id": "role:garden_valve"}},
                          {"action": "notify.notify",
                           "data": {"message": "The garden got less than 200 litres in an hour."}}]}]}],
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
    request = [{"role": "user", "content": "update NET 1: instead of the button: Sun Tue Thu Sat at 05:00, 200 litres, "
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
    # [CHANGED 2026-10-29] The first answer waits inside the run (wait_template, wait.completed): it goes back, and the
    # ladder way answer - a trigger with an id for every event, one choose - is the one built.
    llm, sent = _model(GARDEN_NEW, GARDEN_LADDER)
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "messages": request,
                                        "plan": planned["plan"], "selections": selections})
        built = (await client.receive_json())["result"]
    assert "CURRENT NET" in sent[0][-1]["content"]
    assert built["ok"], built.get("errors")
    assert len(sent) == 2 and built["tries"] == 2
    back = sent[1][-1]["content"]
    assert "does not wait inside a run: actions[4] has wait_template" in back and "ONE choose" in back
    assert built["intent"] == "modify" and built["target_net"] == "n_garden"
    # Checked on the parsed YAML: in the text, quotes inside a quoted string are doubled.
    doc = yaml.safe_load(built["yaml"])
    trig = {t["id"]: t for t in doc["triggers"]}
    assert trig["start"] == {"trigger": "time", "at": "05:00:00", "id": "start"}
    assert trig["amount_reached"]["entity_id"] == "sensor.water_meter" and trig["amount_reached"]["above"] == 200
    assert trig["time_limit"]["entity_id"] == "switch.garden_valve" and trig["time_limit"]["for"] == {"hours": 1}
    start, amount, limit = doc["actions"][0]["choose"]
    assert start["conditions"][1]["weekday"] == ["sun", "tue", "thu", "sat"]
    acts = start["sequence"]
    assert acts[0]["action"] == "weather.get_forecasts" and acts[0]["target"]["entity_id"] == "weather.home"
    assert "forecast['weather.home']" in acts[1]["value_template"] and "rainy" in acts[1]["value_template"]
    assert acts[2]["target"]["entity_id"] == "switch.garden_valve"
    assert amount["sequence"][0]["action"] == "switch.turn_off" and limit["sequence"][1]["action"] == "notify.notify"
    assert not ai.waits_in(doc["actions"])
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
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_LADDER)) as llm:
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


async def test_new_logic_offers_the_device_a_net_on_the_page_uses_first(hass, garden, hass_ws_client):
    """The user's case: "a new NET with the valve from NET 1". The request is new logic, not a change,
    and the model's words are Hebrew and match no entity name. The valve NET 1 uses still comes
    first, says where it is used, and is not ticked - the user picks."""
    for i, name in enumerate(["1ed78263 Fresh air", "1ed78263 Panel light", "Aaa fan", "Boiler"]):
        hass.states.async_set(f"switch.other_{i}", "off", {"friendly_name": name})
    plan = {"reply": "", "intent": "create", "target_net": "", "level": "automation", "name": HE["smart_watering"],
            "roles": [{"id": "irrigation_valve", "label": HE["watering_valve"], "purpose": "target",
                       "domains": ["switch", "valve"], "device_classes": [], "keywords": [HE["valve"], HE["tap"]],
                       "area_keywords": []}], "questions": []}
    other = {"id": "n_other", "name": "Kitchen", "level": "automation", "rungs": []}
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden, other], "share": True,
                                        "messages": [{"role": "user", "content": HE["new_net_by_the_valve_in_net_1"]}]})
        res = (await client.receive_json())["result"]
    assert res["plan"]["intent"] == "create"
    found = res["candidates"]["irrigation_valve"]
    first = found["items"][0]
    assert first["entity_id"] == "switch.garden_valve", [i["entity_id"] for i in found["items"]]
    assert first["on_canvas"] == "NET 1 · Garden watering"
    assert found["exact"] is True
    assert res["preselect"] == {}
    assert not any("on_canvas" in i for i in found["items"][1:])


async def test_a_number_helper_without_a_range_is_created(hass, libi_ai, hass_ws_client):
    """The model proposed an input_number with no min and max. The chat shows 0-100, so 0-100 is what
    Home Assistant's input_number/create gets - it refuses a create without them."""
    assert await async_setup_component(hass, "input_number", {})
    kept, _roles = ai.clean_new_helpers([{"role": "litres", "domain": "input_number", "name": HE["water_amount"],
                                          "settings": {"unit_of_measurement": "L"}}], [])
    assert kept[0]["settings"] == {"min": 0, "max": 100, "unit_of_measurement": "L"}
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "input_number/create", "name": kept[0]["name"], **kept[0]["settings"]})
    res = await client.receive_json()
    assert res["success"], res


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


def test_the_plan_schema_lets_the_model_fill_every_helper_setting():
    """Gemini answers {} for an object schema without properties; every setting LIBI accepts must be listed."""
    settings = ai.PLAN_SCHEMA["properties"]["new_helpers"]["items"]["properties"]["settings"]
    for domain, fields in ai.HELPER_SPEC.items():
        for field in fields:
            assert field in settings["properties"], (domain, field)
    kept, _roles = ai.clean_new_helpers([{"role": "litres", "domain": "input_number", "name": "Litres",
                                          "settings": {"min": 0, "max": 500, "initial": "40"}}], [])
    assert kept[0]["settings"]["initial"] == 40


def test_days_a_time_and_an_amount_are_all_kept_even_on_one_role():
    """The user's garden request: days and a time picked on the screen, the amount from a helper. A model
    that names one role for several helpers used to leave only the first."""
    days = [{"role": "schedule", "domain": "input_boolean", "name": f"Water {d}", "settings": {}}
            for d in ("sun", "mon", "tue", "wed", "thu", "fri", "sat")]
    raw = days + [{"role": "schedule", "domain": "input_datetime", "name": "Watering time",
                   "settings": {"has_time": True}},
                  {"role": "litres", "domain": "input_number", "name": "Litres",
                   "settings": {"min": 0, "max": 500, "step": 5, "unit_of_measurement": "L"}}]
    roles = [{"id": "schedule", "label": "Schedule", "purpose": "condition", "domains": ["input_boolean"],
              "device_classes": [], "keywords": [], "area_keywords": []}]
    kept, roles = ai.clean_new_helpers(raw, roles)
    assert len(kept) == 9
    assert len({h["role"] for h in kept}) == 9
    role_ids = {r["id"] for r in roles}
    assert all(h["role"] in role_ids for h in kept)
    time = next(h for h in kept if h["domain"] == "input_datetime")
    assert time["settings"] == {"has_time": True}
    assert next(r for r in roles if r["id"] == time["role"])["domains"] == ["input_datetime"]


async def test_a_setting_with_no_match_gets_a_new_helper_from_libi(hass, garden, hass_ws_client):
    """The user's report: the model proposed no helper for the litres and no time helper, so the chat listed
    someone else's input_number settings as the "closest". LIBI proposes the helpers itself."""
    hass.states.async_set("input_number.work_alert_offset_guy", "5", {"friendly_name": "Work Alert Offset Guy"})
    plan = {"reply": "ok", "intent": "create", "target_net": "", "level": "automation", "name": "Garden",
            "roles": [{"id": "water_litres", "label": HE["water_amount_in_litres"], "purpose": "condition",
                       "domains": ["input_number"], "device_classes": [], "keywords": ["litres", HE["litre"]],
                       "area_keywords": []},
                      {"id": "start_time", "label": "Watering time", "purpose": "trigger",
                       "domains": ["input_datetime"], "device_classes": [], "keywords": [], "area_keywords": []},
                      {"id": "valve", "label": "Valve", "purpose": "target", "domains": ["switch"],
                       "device_classes": [], "keywords": ["nothing"], "area_keywords": []}],
            "questions": [], "new_helpers": []}
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": True,
                                        "messages": [{"role": "user", "content": "water the garden"}]})
        res = (await client.receive_json())["result"]
    helpers = {h["role"]: h for h in res["plan"]["new_helpers"]}
    assert helpers["water_litres"]["domain"] == "input_number"
    assert helpers["water_litres"]["name"] == HE["water_amount_in_litres"]
    assert helpers["water_litres"]["settings"] == {"min": 0, "max": 100}
    # No input_datetime exists in this Home Assistant yet; the role keeps the domain and gets a helper. [CHANGED
    # 2026-10-31] A time set on the screen stays a time, as on an alarm clock: v3.53.0 made it a schedule, whose days
    # and hours a dashboard card cannot change.
    assert helpers["start_time"]["domain"] == "input_datetime"
    assert helpers["start_time"]["settings"] == {"has_time": True}
    start = next(r for r in res["plan"]["roles"] if r["id"] == "start_time")
    assert start["domains"] == ["input_datetime"] and start["purpose"] == "trigger"
    # A device is never invented as a helper.
    assert "valve" not in helpers
    assert not any(h["role"].startswith("day_") for h in res["plan"]["new_helpers"])


EMPTY_WEEK = {d: [] for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}


def test_days_and_a_time_set_on_the_screen_are_an_alarm_clock():
    """[CHANGED 2026-10-31, v3.76.0] The user: "it does not let me choose the days of the week and the hours", "like an alarm
    clock, where I choose the days and the hour", and then "a variable for each day was not needed - one 8-bit variable,
    bit 1 Sunday, bit 2 Monday ..., shown as checkboxes". The days are ONE days helper: the switches the model still
    proposes for some days become it, named as they were, where they stood; its settings are the 8 bits', whatever the
    model gave; twice is the same as once. (v3.53.0 made a time and day switches one schedule, 3.73.0 a switch for each
    day.) [CHANGED 2026-11-10, v3.95.0] A schedule the user names is used as it is - the week schedule; LIBI then asks
    how new days are set (days_question), and this days helper is what that question replaces."""
    days = [{"role": f"day_{d}", "domain": "input_boolean", "name": f"Watering - {d}", "settings": {}}
            for d in ("thu", "sun", "tue")]
    time = {"role": "start_time", "domain": "input_datetime", "name": "Watering time", "settings": {"has_time": True}}
    litres = {"role": "litres", "domain": "input_number", "name": "L", "settings": {"min": 0, "max": 9}}
    bits = {"min": 0, "max": 255, "step": 1, "mode": "box"}

    def planned():
        kept, roles = ai.clean_new_helpers(copy.deepcopy([time] + days + [litres]), [])
        return {"intent": "create", "name": "Garden", "roles": roles, "new_helpers": kept}
    plan = planned()
    ai.helpers_for_open_roles(plan, {})
    assert [(h["role"], h["domain"], h["name"]) for h in plan["new_helpers"]] == [
        ("start_time", "input_datetime", "Watering time"), ("days", "input_number", "Watering - days"),
        ("litres", "input_number", "L")]
    days_helper = plan["new_helpers"][1]
    assert days_helper["settings"] == bits and days_helper["days_bits"] is True
    ids = {r["id"] for r in plan["roles"]}
    assert "days" in ids and not ids & {f"day_{d}" for d in DAYS}
    # Twice is the same as once: the build cleans the plan again.
    again, roles = ai.clean_new_helpers(copy.deepcopy(plan["new_helpers"]), copy.deepcopy(plan["roles"]))
    second = {**plan, "roles": roles, "new_helpers": again}
    ai.helpers_for_open_roles(second, {})
    assert [(h["role"], h["name"], h["settings"]) for h in second["new_helpers"]] == [
        (h["role"], h["name"], h["settings"]) for h in plan["new_helpers"]]
    # A switch named without " - <day>" gives the days helper the name of the plan; a days helper of the model's own
    # gets the 8 bits' settings, its icon kept.
    plain = {"intent": "create", "name": "Garden", "roles": [], "new_helpers": [
        {"role": "sunday", "domain": "input_boolean", "name": "Sunday", "settings": {}}]}
    ai.helpers_for_open_roles(plain, {})
    assert [(h["role"], h["name"]) for h in plain["new_helpers"]] == [("days", "Garden - days")]
    own, roles = ai.clean_new_helpers([{"role": "days", "domain": "input_number", "name": "Days",
                                        "settings": {"min": 0, "max": 100, "icon": "mdi:calendar"}}], [])
    own_plan = {"intent": "create", "name": "x", "roles": roles, "new_helpers": own}
    ai.helpers_for_open_roles(own_plan, {"days": {"items": [], "exact": True}})
    assert own_plan["new_helpers"][0]["settings"] == {"icon": "mdi:calendar", **bits}
    # [CHANGED 2026-11-10, v3.95.0] The user's choice: a schedule is one of the two ways to set the days and their hours
    # from the screen. One the user names is used as it is - the week schedule, still ticked - and the alarm clock the
    # model proposed beside it goes. (From v3.74.0 it gave way to the alarm clock, listed and not ticked.)
    named = planned()
    named["roles"].append({"id": "garden_schedule", "label": "Garden schedule", "purpose": "trigger",
                           "domains": ["schedule"], "device_classes": [], "keywords": [], "area_keywords": [],
                           "optional": True, "named": True})
    picks = {"garden_schedule": ["schedule.garden"], "litres": ["input_number.l"]}
    # As roles_for_named_helpers leaves it: the named schedule found, so the role needs no new helper of its own.
    found = {"garden_schedule": {"items": [{"entity_id": "schedule.garden"}], "exact": True}}
    ai.helpers_for_open_roles(named, found, picks)
    assert [h["role"] for h in named["new_helpers"]] == ["litres"]
    assert picks == {ai.SCHEDULE_ROLE: ["schedule.garden"], "litres": ["input_number.l"]}
    role = next(r for r in named["roles"] if r["id"] == ai.SCHEDULE_ROLE)
    assert role["purpose"] == "trigger" and not role.get("replaced") and list(found) == [ai.SCHEDULE_ROLE]
    assert not {"start_time", "days"} & {r["id"] for r in named["roles"]}
    # The request asks for a card and the days, and the model's schedule role found nothing and is not named: LIBI
    # proposes the alarm clock, named after the plan for the user to rename, and takes the role out - it asks next how
    # the days are set (days_question), a schedule being one of the answers.
    on_card = {"intent": "create", "name": "Garden watering", "new_helpers": [],
               "roles": [{"id": "when", "label": "When", "purpose": "trigger", "domains": ["schedule"],
                          "device_classes": [], "keywords": [], "area_keywords": []}],
               "requirements": [{"id": "r1", "text": "the days I choose", "kind": "days"},
                                {"id": "r2", "text": "a card", "kind": "card"}]}
    ai.helpers_for_open_roles(on_card, {}, {})
    assert [(h["role"], h["name"], h["settings"]) for h in on_card["new_helpers"]] == [
        ("start_time", "Garden watering", {"has_time": True, "has_date": False}), ("days", "Garden watering - days", bits)]
    assert next(r for r in on_card["roles"] if r["id"] == "start_time")["purpose"] == "trigger"
    assert "when" not in {r["id"] for r in on_card["roles"]}
    # Nothing to set on the screen: the schedule the user names is still the one used.
    kept = {"intent": "create", "name": "x", "roles": [], "new_helpers": []}
    picks = {"garden_schedule": ["schedule.garden"]}
    ai.helpers_for_open_roles(kept, {}, picks)
    assert picks == {"garden_schedule": ["schedule.garden"]} and kept["new_helpers"] == []
    # A time alone is only a time: no days are made up, and nothing becomes a schedule any more.
    alone = {"intent": "create", "name": "x", "roles": [], "new_helpers": [copy.deepcopy(time)]}
    ai.helpers_for_open_roles(alone, {})
    assert [(h["domain"], h["settings"]) for h in alone["new_helpers"]] == [("input_datetime", {"has_time": True})]


# A real schedule entity sets a timer for its next change; that it is still pending at the end is expected.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_the_models_schedule_is_created_by_home_assistant(hass, libi_ai, hass_ws_client):
    """The days and hours the model read from the request ("Monday, Tuesday and Thursday at six") become
    the week of a real schedule; a span that does not hold leaves the week empty."""
    assert await async_setup_component(hass, "schedule", {})
    kept, _roles = ai.clean_new_helpers([{"role": "when", "domain": "schedule", "name": "Garden watering",
                                          "settings": {"days": ["mon", "tue", "thu", "noday"],
                                                       "from": "06:00", "to": "06:30"}}], [])
    week = kept[0]["settings"]
    assert week["monday"] == [{"from": "06:00:00", "to": "06:30:00"}] and week["sunday"] == []
    assert sorted(d for d, r in week.items() if r) == ["monday", "thursday", "tuesday"]
    # The browser sends the plan back; the same week comes out of a second cleaning.
    again, _r = ai.clean_new_helpers(copy.deepcopy(kept), [])
    assert again[0]["settings"] == week
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "schedule/create", "name": kept[0]["name"], **week})
    res = await client.receive_json()
    assert res["success"], res
    for bad in ({"days": ["mon"], "from": "07:00", "to": "06:00"},
                {"days": ["mon"], "from": "25:00", "to": "26:00"},
                {"monday": [{"from": "06:00", "to": "07:00"}, {"from": "06:30", "to": "08:00"}]}):
        out, _r = ai.clean_new_helpers([{"role": "w", "domain": "schedule", "name": "W", "settings": bad}], [])
        assert out[0]["settings"] == EMPTY_WEEK, bad


async def test_a_net_built_with_device_actions_offers_its_valve_and_meter(hass, libi_ai, hass_ws_client):
    """The user's NET 1 came from the Home Assistant editor: device triggers and actions name the valve and
    the water meter by registry id. They were not found, so the list showed every switch but the valve."""
    reg = er.async_get(hass)
    valve = reg.async_get_or_create("switch", "test", "valve1", suggested_object_id="valve_garden_switch")
    meter = reg.async_get_or_create("sensor", "test", "meter1", suggested_object_id="valve_garden_volume")
    hass.states.async_set(valve.entity_id, "off", {"friendly_name": "Valve Garden"})
    hass.states.async_set(meter.entity_id, "120", {"friendly_name": "Valve Garden volume", "device_class": "water"})
    hass.states.async_set("switch.aaa_fresh_air", "off", {"friendly_name": "Fresh air"})
    compiled = {"id": "1697188443861", "alias": "Valve Garden Turn Off",
                "triggers": [{"trigger": "device", "domain": "sensor", "type": "volume",
                              "device_id": "d68bd67a02380d7af47fd214ce8eb28a", "entity_id": meter.id}],
                "actions": [{"domain": "switch", "type": "turn_off",
                             "device_id": "d68bd67a02380d7af47fd214ce8eb28a", "entity_id": valve.id}]}
    net1 = {"id": "n1", "name": "Valve Garden Turn Off", "elements": [], "wires": []}
    with patch.object(ai, "ast_to_yaml", return_value=compiled):
        text, by_id = ai.canvas_context(hass, [net1])
    assert valve.entity_id in by_id["n1"] and meter.entity_id in by_id["n1"] and valve.entity_id in text
    # The device id is the same shape and is not an entity: it is not listed.
    assert ai.registry_entities(hass, by_id["n1"]) == [(meter.entity_id, "Valve Garden volume"),
                                                         (valve.entity_id, "Valve Garden")]
    plan = {"reply": "ok", "intent": "create", "target_net": "", "level": "automation", "name": "Garden",
            "roles": [{"id": "valve", "label": "valve", "purpose": "target", "domains": ["switch"],
                       "device_classes": [], "keywords": ["nothing"], "area_keywords": []},
                      {"id": "meter", "label": "meter", "purpose": "measure", "domains": ["sensor"],
                       "device_classes": [], "keywords": ["nothing"], "area_keywords": []}],
            "questions": [], "new_helpers": []}
    client = await hass_ws_client(hass)
    with patch.object(ai, "ast_to_yaml", return_value=compiled), patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [net1], "share": True,
                                        "messages": [{"role": "user", "content": "use the devices of NET 1"}]})
        res = (await client.receive_json())["result"]
    first = res["candidates"]["valve"]["items"][0]
    assert first["entity_id"] == valve.entity_id and first["on_canvas"].startswith("NET 1")
    assert res["candidates"]["meter"]["items"][0]["entity_id"] == meter.entity_id


USER_NET1 = {
    # The user's NET 1 as LIBI stores it: the registry ids in "raw" are stale (the valve was paired again,
    # there is a switch.valve_garden_switch_2), the elements show the entities the importer resolved.
    "id": "n1", "ha_id": "1697188443861", "name": "Valve Garden Turn Off", "level": "automation", "mode": "single",
    "rungs": [{"id": "r1", "comment": "When valve garden summation delivered is between 0 and 500", "elements": [
        {"id": "e4", "type": "cmp_rng", "isTrigger": True, "sourceA": "sensor.valve_garden_summation_delivered",
         "sourceB": 0, "sourceC": 500, "src": "triggers[0]", "trigId": "t1",
         "raw": {"type": "volume", "device_id": "d68bd67a02380d7af47fd214ce8eb28a",
                 "entity_id": "761eb2f79a2cadc5400a670a021e8393", "domain": "sensor", "trigger": "device",
                 "below": 500, "above": 0, "id": "t1"}},
        {"id": "e2", "type": "coil_r", "label": "switch.valve_garden_switch", "src": "actions[0]",
         "deviceNode": "action", "deviceId": "d68bd67a02380d7af47fd214ce8eb28a", "fromAction": True,
         "raw": {"type": "turn_off", "device_id": "d68bd67a02380d7af47fd214ce8eb28a",
                 "entity_id": "9dd9119bcafee1b19b97a7916da76ed7", "domain": "switch"}},
        {"id": "e3", "type": "move", "mode": "notify", "target": "notify.mobile_app_phone", "source": "done",
         "raw": {"action": "notify.mobile_app_phone", "data": {"message": "done"}}}]}],
    "links": [], "source": "ha",
}
# What ast_to_yaml gives for it in the user's Home Assistant: unchanged elements write their raw YAML back,
# so the stale registry ids are all the YAML says about the valve and the meter.
USER_NET1_YAML = {
    "id": "1697188443861", "alias": "Valve Garden Turn Off", "description": "1",
    "triggers": [{"type": "volume", "device_id": "d68bd67a02380d7af47fd214ce8eb28a",
                  "entity_id": "761eb2f79a2cadc5400a670a021e8393", "domain": "sensor", "trigger": "device",
                  "below": 500, "above": 0, "id": "t1"}],
    "conditions": [],
    "actions": [{"type": "turn_off", "device_id": "d68bd67a02380d7af47fd214ce8eb28a",
                 "entity_id": "9dd9119bcafee1b19b97a7916da76ed7", "domain": "switch"},
                {"action": "notify.mobile_app_phone", "data": {"message": "done"}}],
    "mode": "single",
}


async def test_the_users_net1_offers_its_valve_meter_and_the_weather(hass, libi_ai, hass_ws_client):
    """The user's last report: the valve listed without its NET 1 tag, no way to pick the flow meter, and the
    weather entity missing from "weather or rain sensor" (a moisture class filter hid it)."""
    hass.states.async_set("switch.valve_garden_switch", "off", {"friendly_name": "valve_garden Switch"})
    hass.states.async_set("switch.valve_garden_switch_2", "off", {"friendly_name": "valve_garden"})
    hass.states.async_set("sensor.valve_garden_summation_delivered", "120",
                          {"friendly_name": "valve_garden Summation delivered", "device_class": "volume"})
    hass.states.async_set("weather.home", "sunny", {"friendly_name": "Forecast Home"})
    hass.states.async_set("binary_sensor.jacuzzi_moisture", "off", {"friendly_name": "Jacuzzi", "device_class": "moisture"})
    pin = patch.object(ai, "ast_to_yaml", return_value=USER_NET1_YAML)
    with pin:
        text, by_id = ai.canvas_context(hass, [USER_NET1])
    assert "switch.valve_garden_switch (valve_garden Switch)" in by_id["n1"]
    assert "notify.mobile_app_phone" not in ai.canvas_entities(hass, [USER_NET1], by_id)
    plan = {"reply": "ok", "intent": "create", "target_net": "", "level": "automation", "name": "Garden",
            "roles": [{"id": "valve", "label": "valve", "purpose": "target", "domains": ["switch"],
                       "device_classes": ["valve"], "keywords": ["garden"], "area_keywords": []},
                      # [v3.54.0] The user's screen: the NET 1 water meter (volume) was listed first here.
                      {"id": "rain", "label": "weather or rain", "purpose": "condition",
                       "domains": ["weather", "binary_sensor", "sensor"], "device_classes": ["moisture", "precipitation"],
                       "keywords": ["weather", "rain"], "area_keywords": []}],
            "questions": [], "new_helpers": []}
    client = await hass_ws_client(hass)
    with pin, patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [USER_NET1], "share": True,
                                        "messages": [{"role": "user", "content": "a new NET from the devices in NET 1"}]})
        res = (await client.receive_json())["result"]
    valve = res["candidates"]["valve"]
    assert valve["items"][0]["entity_id"] == "switch.valve_garden_switch" and valve["exact"] is True
    assert valve["items"][0]["on_canvas"] == "NET 1 · Valve Garden Turn Off"
    rain = [i["entity_id"] for i in res["candidates"]["rain"]["items"]]
    assert "weather.home" in rain and "sensor.valve_garden_summation_delivered" not in rain
    meter = next(r for r in res["plan"]["roles"] if r["domains"] == ["sensor"])
    assert meter["optional"] is True and meter["purpose"] == "measure"
    assert res["candidates"][meter["id"]]["items"][0]["entity_id"] == "sensor.valve_garden_summation_delivered"
    # The valve already has a role: it is not offered twice. Nothing is ticked.
    assert len(res["plan"]["roles"]) == 3 and res["preselect"] == {}
    # Without "NET 1" in the request no role is added.
    with pin, patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [USER_NET1], "share": True,
                                        "messages": [{"role": "user", "content": "water the garden"}]})
        res2 = (await client.receive_json())["result"]
    assert len(res2["plan"]["roles"]) == 2
    # An optional role nobody picked does not hold the build back; a required one still does.
    sel, problems = ai.clean_selections(hass, res["plan"], {"valve": ["switch.valve_garden_switch"],
                                                            "rain": ["weather.home"]})
    assert problems == [] and meter["id"] not in sel
    _sel, problems = ai.clean_selections(hass, res["plan"], {"rain": ["weather.home"]})
    assert problems == ["Pick at least one entity for 'valve'."]
    # The plan comes back from the browser and is cleaned again: optional survives.
    again = ai.clean_plan(hass, copy.deepcopy(res["plan"]))
    assert next(r for r in again["roles"] if r["id"] == meter["id"])["optional"] is True


LITRES_ROLE = {"id": "litres", "label": "Litres", "purpose": "condition", "domains": ["input_number"],
               "device_classes": [], "keywords": ["litres"], "area_keywords": []}


async def _used_helpers_home(hass):
    """Three litres helpers: one an automation uses, one only a template in automations.yaml names, one free."""
    for oid in ("garden_litres_used", "garden_litres_template", "garden_litres_free"):
        hass.states.async_set(f"input_number.{oid}", "40", {"friendly_name": oid.replace("_", " ")})
    hass.states.async_set("switch.valve", "off", {"friendly_name": "Valve"})
    assert await async_setup_component(hass, "automation", {"automation": [
        {"alias": "Other watering", "triggers": [{"trigger": "state", "entity_id": "input_number.garden_litres_used"}],
         "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.valve"}}]}]})
    await hass.async_block_till_done()
    return "- alias: x\n  conditions:\n  - condition: template\n    value_template: \"{{ states('input_number.garden_litres_template') }}\"\n"


async def test_a_setting_role_lists_only_helpers_nothing_else_uses(hass, libi_ai):
    """The user: show only helpers that are not in use, so the new card cannot change another automation."""
    config_text = await _used_helpers_home(hass)
    assert ai.helper_users(hass, "input_number.garden_litres_used", config_text) == ["Other watering"]
    assert ai.helper_users(hass, "input_number.garden_litres_template", config_text) == \
        ["a template in automations.yaml or scripts.yaml"]
    assert ai.helper_users(hass, "input_number.garden_litres_free", config_text) == []
    # A prefix of another id is not a mention of it.
    assert ai.helper_users(hass, "input_number.garden_litres", config_text) == []
    valve_role = {"id": "valve", "label": "Valve", "purpose": "target", "domains": ["switch"],
                  "device_classes": [], "keywords": ["valve"], "area_keywords": []}
    candidates = {"litres": ai.find_candidates(hass, LITRES_ROLE), "valve": ai.find_candidates(hass, valve_role)}
    ai.drop_used_helpers(hass, candidates, config_text)
    assert [i["entity_id"] for i in candidates["litres"]["items"]] == ["input_number.garden_litres_free"]
    assert candidates["litres"]["hidden_used"] == 2
    # A device is meant to be switched by more than one automation: not filtered.
    # (the fixture's switch.garden_valve matches "valve" as well).
    assert "switch.valve" in [i["entity_id"] for i in candidates["valve"]["items"]]
    assert "hidden_used" not in candidates["valve"]


def test_the_config_text_is_read_from_both_files_and_a_missing_one_adds_nothing(hass, config_dir):
    from custom_components.libi import websocket  # noqa: PLC0415

    assert websocket._config_text_sync(hass) == ""
    (config_dir / "scripts.yaml").write_text("x:\n  sequence:\n  - delay: \"{{ states('input_number.a') }}\"\n", encoding="utf-8")
    assert "input_number.a" in websocket._config_text_sync(hass)
    (config_dir / "automations.yaml").write_text("- alias: b\n  actions: []\n", encoding="utf-8")
    text = websocket._config_text_sync(hass)
    assert "alias: b" in text and "input_number.a" in text


async def test_a_proposed_helper_that_exists_is_not_created_twice(hass, libi_ai, hass_ws_client):
    """The user: an earlier chat created the helpers and the logic was never built. A new plan offers the
    unused one instead of creating it again; one that another automation uses gets a name of its own."""
    config_text = await _used_helpers_home(hass)
    plan = {"reply": "ok", "intent": "create", "target_net": "", "level": "automation", "name": "Garden",
            "roles": [LITRES_ROLE, {**LITRES_ROLE, "id": "rate", "label": "Rate", "keywords": ["rate"]}],
            "questions": [],
            "new_helpers": [{"role": "litres", "domain": "input_number", "name": "Garden litres free",
                             "settings": {"min": 0, "max": 100}},
                            {"role": "rate", "domain": "input_number", "name": "garden litres used",
                             "settings": {"min": 0, "max": 100}}]}
    with patch("custom_components.libi.websocket._config_text_sync", return_value=config_text), \
            patch.object(ai, "async_llm_json", return_value=plan):
        client = await hass_ws_client(hass)
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": True,
                                        "messages": [{"role": "user", "content": "garden litres"}]})
        res = (await client.receive_json())["result"]
    assert [h["name"] for h in res["plan"]["new_helpers"]] == ["garden litres used (2)"]
    first = res["candidates"]["litres"]["items"][0]
    assert first["entity_id"] == "input_number.garden_litres_free" and first["exists"] is True
    assert res["preselect"] == {}
    assert "input_number.garden_litres_used" not in [i["entity_id"] for c in res["candidates"].values() for i in c["items"]]


async def test_a_change_keeps_the_helpers_its_own_net_uses(hass, libi_ai, garden, hass_ws_client):
    """For a change, the net's own helper is offered and ticked although an automation (that net) uses it."""
    config_text = await _used_helpers_home(hass)
    plan = {**copy.deepcopy(GARDEN_PLAN), "roles": GARDEN_PLAN["roles"] + [LITRES_ROLE], "new_helpers": []}
    net = {**copy.deepcopy(garden)}
    with patch.object(ai, "canvas_context", return_value=("NETS", {garden["id"]: "entity_id: input_number.garden_litres_used\n"})), \
            patch("custom_components.libi.websocket._config_text_sync", return_value=config_text), \
            patch.object(ai, "async_llm_json", return_value=plan):
        client = await hass_ws_client(hass)
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [net], "share": True,
                                        "messages": [{"role": "user", "content": "change NET 1"}]})
        res = (await client.receive_json())["result"]
    assert res["preselect"].get("litres") == ["input_number.garden_litres_used"]
    assert res["candidates"]["litres"]["items"][0]["current"] is True


async def test_the_build_reads_config_and_card_written_as_json_text(hass, home):
    """The user's Build said "no trigger, no actions": Gemini answers {} for an object schema without
    properties. The schema asks for JSON text now; an object from another model is still taken."""
    props = ai.BUILD_SCHEMA["properties"]
    assert props["config"] == {"type": "string"} and props["ui_card"] == {"type": "string"}
    as_text = {**copy.deepcopy(GOOD_BUILD), "config": json.dumps(GOOD_BUILD["config"]),
               "ui_card": json.dumps({"type": "entities", "entities": ["role:salon_lights"]})}
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, as_text)
    assert out["ok"], out["errors"]
    assert out["auto"]["triggers"][0]["entity_id"] == ["input_button.door_button", "event.remote_button"]
    assert "light.salon_ceiling" in out["card_yaml"]
    fenced = {**as_text, "config": "```json\n" + as_text["config"] + "\n```", "ui_card": ""}
    assert (await ai.async_build_draft(hass, _plan(hass), SELECTED, fenced))["ok"]
    broken = {**as_text, "config": '{"triggers": [', "ui_card": ""}
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, broken)
    assert not out["ok"] and "The AI's configuration could not be read. Try Build again." in out["errors"]
    # [v3.57.0] That is the one error: no "needs a trigger" and "does nothing" that only follow from it.
    assert out["errors"] == ["The AI's configuration could not be read. Try Build again."]


async def test_the_build_reads_what_models_get_wrong_in_json_text(hass, home):
    """The user's first Build said "could not be read" and a second worked. What models write: \\' for
    the quotes of a Jinja template, a sentence after the object, YAML instead of JSON."""
    text = json.dumps(GOOD_BUILD["config"])
    jinja = text.replace('"actions": [', '"variables": {"x": "{{ states(\\\'sensor.t\\\') }}"}, "actions": [', 1)
    assert "\\'" in jinja and ai._json_object(jinja)["variables"] == {"x": "{{ states('sensor.t') }}"}
    for config in (jinja, text + "\nThat is the automation.",
                   yaml.dump(GOOD_BUILD["config"], allow_unicode=True, sort_keys=False)):
        out = await ai.async_build_draft(hass, _plan(hass), SELECTED, {**GOOD_BUILD, "config": config})
        assert out["ok"], (config, out["errors"])
    # Still read as data only: text that is no object is refused, not taken as an empty automation.
    for bad in ("just a sentence", "[1, 2]", "{'triggers': ["):
        assert ai._json_object(bad) is None, bad
    assert ai._json_object("") == {} and ai._json_object(text) == GOOD_BUILD["config"]


async def test_an_unreadable_build_is_asked_for_again(hass, libi_ai, hass_ws_client):
    """The user's first Build said "could not be read" and a second worked. [v3.62.0] It is one of the problems
    LIBI sends back to the model, with what to do, and at most MAX_BUILD_TRIES answers are asked for."""
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(PLAN)):
        await client.send_json_auto_id({"type": "libi/ai_plan",
                                        "messages": [{"role": "user", "content": "button -> salon light 10 min"}]})
        planned = (await client.receive_json())["result"]
    request = {"type": "libi/ai_build", "messages": [{"role": "user", "content": "x"}],
               "plan": planned["plan"], "selections": SELECTED, "answers": {"duration": "10 minutes"}}
    unreadable = {**copy.deepcopy(GOOD_BUILD), "config": '{"triggers": ['}
    llm, sent = _model(unreadable, GOOD_BUILD)
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id(request)
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    assert len(sent) == 2 and built["tries"] == 2
    assert sent[1][-2] == {"role": "assistant", "content": json.dumps(unreadable, ensure_ascii=False)}
    assert "could not be read" in sent[1][-1]["content"] and "ONE JSON object" in sent[1][-1]["content"]
    # Bounded: answers that stay unreadable are reported after MAX_BUILD_TRIES of them, not asked for again and again.
    llm, sent = _model(unreadable, unreadable, unreadable, GOOD_BUILD)
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id(request)
        built = (await client.receive_json())["result"]
    assert len(sent) == ai.MAX_BUILD_TRIES == 3 and built["tries"] == 3
    assert built["errors"] == ["The AI's configuration could not be read. Try Build again."]


async def test_the_schedule_trigger_the_build_prompt_teaches_is_accepted(hass, home):
    assert '"to": "on"' in ai.BUILD_SYSTEM and "schedule role" in ai.BUILD_SYSTEM
    # [CHANGED 2026-10-31] A schedule only when the user asks for one or names one; days and a time are an alarm clock.
    plan_prompt = " ".join(ai.PLAN_SYSTEM.split())
    assert "set as on an alarm clock" in plan_prompt
    # [CHANGED 2026-11-10, v3.95.0] A schedule the user names is used; LIBI asks how new days are set.
    assert "LIBI then asks the user whether the days are a switch for each day or a schedule" in plan_prompt
    assert "When the user names a schedule helper of their own for the days and hours, use it instead" in plan_prompt
    assert "only when the user asks for a schedule with fixed days and hours" in plan_prompt
    assert "give the schedule no role" not in plan_prompt
    hass.states.async_set("schedule.garden_watering", "off", {"friendly_name": "Garden watering"})
    plan = ai.clean_plan(hass, {**copy.deepcopy(PLAN), "roles": PLAN["roles"] + [
        {"id": "when", "label": "When", "purpose": "trigger", "domains": ["schedule"],
         "device_classes": [], "keywords": [], "area_keywords": []}]})
    sel = {**SELECTED, "when": ["schedule.garden_watering"]}
    out = await ai.async_build_draft(hass, plan, sel, _with(lambda c: c.update(
        {"triggers": [{"trigger": "state", "entity_id": "role:when", "to": "on"}]})))
    assert out["ok"], out["errors"]
    assert out["auto"]["triggers"][0]["entity_id"] == "schedule.garden_watering"


async def test_the_day_condition_the_build_prompt_teaches_is_accepted(hass, home):
    """[CHANGED 2026-10-31, v3.76.0] The days the user ticks are ONE helper of 8 bits: the prompt teaches the one condition
    that reads today's bit, written exactly as LIBI draws it as CMP DAY, and no longer a switch for each day; the build
    takes it, the helper filled in."""
    assert ai.day_bits_template("role:days") in ai.BUILD_SYSTEM and "role:day_mon" not in ai.BUILD_SYSTEM
    # [ADDED 2026-10-31] The time the user sets starts it, and the days are checked right after it.
    assert '"trigger": "time", "at": "role:<time role>", "id": "start"' in " ".join(ai.BUILD_SYSTEM.split())
    hass.states.async_set("input_number.garden_days", "21", {"friendly_name": "Garden days", "min": 0, "max": 255})
    plan = ai.clean_plan(hass, {**copy.deepcopy(PLAN), "roles": PLAN["roles"] + [
        {"id": "days", "label": "Days", "purpose": "condition", "domains": ["input_number"],
         "device_classes": [], "keywords": [], "area_keywords": []}]})
    sel = {**SELECTED, "days": ["input_number.garden_days"]}
    days = {"condition": "template", "value_template": ai.day_bits_template("role:days")}
    out = await ai.async_build_draft(hass, plan, sel, _with(lambda c: c["conditions"].append(days)))
    assert out["ok"], out["errors"]
    assert out["auto"]["conditions"][0] == {"condition": "template",
                                            "value_template": ai.day_bits_template("input_number.garden_days")}


def test_a_setting_with_an_exact_match_or_a_proposed_helper_gets_no_extra_helper():
    roles = [{"id": "litres", "label": "Litres", "purpose": "condition", "domains": ["input_number"],
              "device_classes": [], "keywords": [], "area_keywords": []},
             {"id": "mode", "label": "Mode", "purpose": "condition", "domains": ["input_select"],
              "device_classes": [], "keywords": [], "area_keywords": []},
             {"id": "days", "label": "Days", "purpose": "condition", "domains": ["input_boolean"],
              "device_classes": [], "keywords": [], "area_keywords": []}]
    plan = {"intent": "create", "roles": roles,
            "new_helpers": [{"role": "days", "domain": "input_boolean", "name": "Sunday", "settings": {}}]}
    ai.helpers_for_open_roles(plan, {"litres": {"items": [{"entity_id": "input_number.l"}], "exact": True},
                                     "mode": {"items": [], "exact": False}})
    # litres matched exactly, days already has one, an input_select has no options to invent.
    assert [h["role"] for h in plan["new_helpers"]] == ["days"]


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
    # [CHANGED 2026-10-31] Read as an alarm clock is: the time, then the days as ONE row of buttons, Sunday to Saturday,
    # each tapped to tick it (a button of that row opens the details unless it says toggle), then the other settings.
    assert rows[0] == {"entity": "input_datetime.garden_start", "name": "Start time"}
    assert rows[1]["type"] == "buttons"
    assert [b["entity"] for b in rows[1]["entities"]] == [f"input_boolean.garden_{d}" for d in DAYS]
    assert all(b["tap_action"] == {"action": "toggle"} for b in rows[1]["entities"])
    assert [b["name"] for b in rows[1]["entities"]][:2] == ["Water on Sun", "Water on Mon"]
    ids = [r.get("entity") for r in rows]
    # [CHANGED 2026-11-01, v3.79.0] After a divider: the alarm clock is a group of its own, as the card reads.
    assert rows[2] == {"type": "divider"} and ids[3:5] == ["input_number.garden_litres", "input_boolean.garden_weather"]
    assert "role:" not in out["card_yaml"]
    # [v3.63.0] The user's watering card asked for the valve: the devices the logic switches come last, after a
    # divider. [CHANGED 2026-11-01, v3.79.0] With what the logic reads under them, the meter and the weather - the
    # user's own garden card shows the litres next to the valve. No toggle in the header: with the weather choice on the
    # card it would switch the valve together with it.
    assert ids[5:] == [None, "switch.garden_valve", "sensor.water_meter", "weather.home"]
    assert card["show_header_toggle"] is False and card["state_color"] is True
    # the logic itself reads the same helpers
    assert "input_datetime.garden_start" in out["yaml"] and "input_number.garden_litres" in out["yaml"]
    # and the ladder drawing holds it unchanged, so SAVE & COMPILE writes what was built
    from custom_components.libi.libi_to_yaml import verify_round_trip
    report = verify_round_trip(hass, out["auto"])
    assert report["ok"], report["issues"]


async def test_the_settings_come_on_libis_own_card_and_the_models_only_without_them(hass, garden):
    """[CHANGED 2026-10-31] The settings the logic reads come on LIBI's own card, the same every run: the user's card had
    to let them set the days and the hours. The model's card is kept when the logic reads no setting."""
    plan, selections, build = await _garden_with_helpers(hass)
    build["ui_card"] = {"type": "tile", "entity": "role:litres"}
    out = await ai.async_build_draft(hass, plan, selections, build)
    assert out["ok"], out["errors"]
    card = yaml.safe_load(out["card_yaml"])
    assert card["type"] == "entities" and card["entities"][1]["type"] == "buttons"
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED,
                                     {**copy.deepcopy(GOOD_BUILD), "ui_card": {"type": "tile", "entity": "role:salon_lights"}})
    assert out["ok"], out["errors"]
    assert yaml.safe_load(out["card_yaml"]) == {"type": "tile", "entity": "light.salon_ceiling"}


async def test_no_card_without_helpers(hass, home):
    out = await ai.async_build_draft(hass, _plan(hass), SELECTED, copy.deepcopy(GOOD_BUILD))
    assert out["ok"], out["errors"]
    assert out["card_yaml"] == ""


def test_a_card_reads_as_a_dashboard(hass: HomeAssistant):
    """[ADDED 2026-11-01, v3.79.0] The user, of the card LIBI made: "the design should be nicer and easier to use". Its
    time row said the card's title again and its days "<title> - days": LIBI names an alarm clock after its net. Each
    row says its own part only, the groups stand apart, and the header has no toggle that would switch the valve
    together with a setting."""
    states = {
        "input_datetime.clock": ("Garden", {"has_time": True, "has_date": False}),
        "input_datetime.day": ("Garden", {"has_time": False, "has_date": True}),
        "input_number.bits": ("Garden - days", {}),
        "input_number.litres": ("Garden - litres", {}),
        "input_boolean.skip": ("Skip when it rains", {}),
        "switch.valve": ("Valve", {}),
        "sensor.a": ("Meter a", {}), "binary_sensor.b": ("Rain b", {}), "weather.c": ("Weather c", {}),
        "sensor.d": ("Meter d", {}), "sensor.e": ("Meter e", {}), "notify.phone": ("Phone", {}),
    }
    for eid, (name, attrs) in states.items():
        hass.states.async_set(eid, "0", {"friendly_name": name, **attrs})
    card = ai._card(hass, list(states), "Garden", day_bits={"input_number.bits"})
    assert (card["type"], card["title"], card["show_header_toggle"], card["state_color"]) == ("entities", "Garden", False, True)
    assert [(r.get("entity"), r.get("name")) for r in card["entities"]] == [
        # The time named as the card is the start time; a date is not, and keeps its name. The days say "Days".
        ("input_datetime.clock", "Start time"), ("input_datetime.day", "Garden"), ("input_number.bits", "Days"), (None, None),
        # What follows "<title> - " is a setting's own name, in capitals as a name starts.
        ("input_number.litres", "Litres"), ("input_boolean.skip", "Skip when it rains"), (None, None),
        # Under the valve what the logic reads, four at most; a notify service is neither.
        ("switch.valve", "Valve"), ("sensor.a", "Meter a"), ("binary_sensor.b", "Rain b"), ("weather.c", "Weather c"),
        ("sensor.d", "Meter d")]
    assert card["entities"][2]["type"] == ai.DAYS_ROW_TYPE
    # The words the days are named after leave the alarm clock's rows only: under another title a setting named after
    # them keeps its whole name.
    card = ai._card(hass, ["input_datetime.clock", "input_number.bits", "input_number.litres"], "Watering",
                    day_bits={"input_number.bits"})
    assert [r.get("name") for r in card["entities"]] == ["Start time", "Days", None, "Garden - litres"]
    # A name of its own stays: in any case, a name the title only starts, a tail with capitals, an empty title.
    assert ai._row_name("GARDEN", ["garden"], "Start time") == "Start time"
    assert ai._row_name("garden - days", ["Garden"], "x") == "Days"
    assert ai._row_name("Garden - iPhone", ["Garden"], "x") == "iPhone"
    assert ai._row_name("Garden watering", ["Garden"], "x") == "Garden watering"
    assert ai._row_name("Garden - ", ["Garden"], "x") == "Garden -"
    assert ai._row_name("Garden", ["", "  "], "x") == "Garden"
    # The model is asked for the unit of an amount, which the card shows next to the value.
    assert 'unit_of_measurement "L"' in ai.PLAN_SYSTEM and 'unit_of_measurement "min"' in " ".join(ai.PLAN_SYSTEM.split())
    # Readings alone make no card: a card is for what the user sets, or for the devices a net switches.
    assert ai._card(hass, ["sensor.a", "weather.c"], "Garden") == {}
    assert ai._card(hass, ["sensor.a", "weather.c"], "Garden", need_settings=False) == {}
    assert [r["entity"] for r in ai._card(hass, ["switch.valve", "sensor.a"], "x", need_settings=False)["entities"]] == [
        "switch.valve", "sensor.a"]


# ---------------------------------------------------------------- the user's rules for where logic goes (v3.59.0)
NETS = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]


def test_the_user_names_a_net_by_the_number_the_canvas_shows():
    assert ai.nets_named("update NET 3 and add a 4 minute timer", NETS) == ["n3"]
    assert ai.nets_named(HE["update_net_2"], NETS) == ["n2"]
    assert ai.nets_named(HE["in_net_1_and_net_3"], NETS) == ["n1", "n3"]
    for text in ("INTERNET 3", "NETWORK 3", "NET 9", "NET 12", "water the garden", ""):
        assert ai.nets_named(text, NETS) == [], text


def test_a_net_is_changed_only_when_the_user_names_it():
    """The user's rule: "update NET 3" changes NET 3; anything else is a new NET, whatever the model says."""
    def plan(target="n3", intent="modify"):
        return {"intent": intent, "target_net": target}

    p = plan()
    ai.only_named_changes(p, "update NET 3 and add a 4 minute timer", NETS)
    assert p == plan()
    p = plan("n1")
    ai.only_named_changes(p, "water the garden on fixed days", NETS)
    assert p == {"intent": "create", "target_net": "", "forced_new": True}
    # One net named: that is the one changed, not the one the model picked.
    p = plan("n1")
    ai.only_named_changes(p, "update NET 3", NETS)
    assert p == plan("n3")
    # Two named and the model's pick is neither: new logic.
    p = plan("n1")
    ai.only_named_changes(p, "use the valve of NET 2 and the meter of NET 3", NETS)
    assert p["intent"] == "create" and p["target_net"] == ""
    # New logic stays new: the rule never turns a request into a change.
    p = plan("", "create")
    ai.only_named_changes(p, "update NET 3", NETS)
    assert p == plan("", "create")


async def test_the_model_cannot_change_a_net_the_user_did_not_name(hass, garden, hass_ws_client):
    """In the user's test the model chose to change NET 1 although the message named no net."""
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_PLAN)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": "water the garden on fixed days"}]})
        res = (await client.receive_json())["result"]
    assert res["plan"]["intent"] == "create" and res["plan"]["target_net"] == "" and res["plan"]["forced_new"] is True
    assert res["preselect"] == {}
    # The model reads the nets with the number the user names them by.
    assert "--- NET 1 | net id n_garden" in llm.call_args.args[3][-1]["content"]

    # The build checks again: a plan the browser sends back as a change of an unnamed net is new logic.
    request = [{"role": "user", "content": "water the garden on fixed days"}]
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(GARDEN_NEW)) as llm:
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "messages": request,
                                        "plan": copy.deepcopy(GARDEN_PLAN),
                                        "selections": {"garden_valve": ["switch.garden_valve"],
                                                       "water_meter": ["sensor.water_meter"],
                                                       "weather": ["weather.home"]}})
        built = (await client.receive_json())["result"]
    assert built["intent"] == "create" and built["target_net"] == ""
    assert "CURRENT NET" not in llm.call_args.args[3][-1]["content"]


# ---------------------------------------------------------------- helpers the user names (v3.60.0)
USER_HELPERS = {  # the user's own helpers, named as in their Home Assistant
    "schedule.lvkh_zmnym_lhshqyyt_gynh": HE["garden_watering_schedule"],
    "input_number.kmvt_mym_lhshqyh_blytrym": HE["water_amount_in_litres"],
    "input_number.zmn_hshqyh_mqsymly_bdqvt": HE["max_watering_minutes"],
    "schedule.tests": "testS",
    "input_datetime.test": "test",
    "input_number.work_alert_offset_guy": "Work Alert Offset Guy",
}
SCHEDULE, LITRES, LIMIT = list(USER_HELPERS)[:3]
# Three lines of the user's message: two helpers it says exist, and one it only names.
USER_REQUEST = HE["user_request"]


def _user_helpers(hass):
    for eid, name in USER_HELPERS.items():
        hass.states.async_set(eid, "off", {"friendly_name": name})


async def test_the_helpers_the_user_names_are_found_by_their_whole_name(hass, home):
    _user_helpers(hass)
    assert ai.helpers_named(hass, USER_REQUEST) == [SCHEDULE, LITRES, LIMIT]
    # A one-word name counts only between quotes, so a test in a sentence is not the helper called test.
    assert ai.helpers_named(hass, "a timer for a test, for tests (testS)") == []
    assert ai.helpers_named(hass, 'use the helper "test"') == ["input_datetime.test"]
    # Inside a longer word it is not the name; written with _ and - it is; after a one-letter prefix of the
    # user's language it is too.
    assert ai.helpers_named(hass, "xwork alert offset guy, work alert offset guys") == []
    assert ai.helpers_named(hass, "Work_Alert-Offset guy") == ["input_number.work_alert_offset_guy"]
    assert ai.helpers_named(hass, HE["in_garden_watering_schedule"]) == [SCHEDULE]
    # Where one name holds another, the longer one is meant.
    hass.states.async_set("input_number.kmvt_mym", "0", {"friendly_name": HE["water_amount"]})
    assert ai.helpers_named(hass, HE["water_amount_in_litres"]) == [LITRES]
    assert ai.helpers_named(hass, HE["water_amount_and_water_amount_in_litres"]) == ["input_number.kmvt_mym", LITRES]
    assert ai.helpers_named(hass, "") == [] and ai.helpers_named(hass, "water the garden") == []


async def test_the_helpers_the_user_names_are_offered_and_ticked(hass, garden, hass_ws_client):
    """The user's test: the message said which schedule and which litres helper to use and named the time
    limit, and the model planned the valve, the meter and the weather only - so no helper could be picked,
    for the logic or for the card."""
    assert "every device and every helper" in ai.PLAN_SYSTEM and "the words of its name" in ai.PLAN_SYSTEM
    _user_helpers(hass)
    plan = {**copy.deepcopy(GARDEN_PLAN), "intent": "create", "target_net": "", "new_helpers": []}
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": USER_REQUEST}]})
        res = (await client.receive_json())["result"]
    roles = res["plan"]["roles"]
    assert [r["id"] for r in roles[:3]] == ["garden_valve", "water_meter", "weather"]
    named = roles[3:]
    assert [(r["domains"], r["label"]) for r in named] == [
        (["schedule"], USER_HELPERS[SCHEDULE]), (["input_number"], USER_HELPERS[LITRES]),
        (["input_number"], USER_HELPERS[LIMIT])]
    assert all(r["optional"] and r["named"] for r in named) and named[0]["purpose"] == "trigger"
    # Each holds that one helper, ticked and tagged - not "current", and not created again.
    assert [res["preselect"][r["id"]] for r in named] == [[SCHEDULE], [LITRES], [LIMIT]]
    for r in named:
        cand = res["candidates"][r["id"]]
        assert cand["exact"] is True and [i["entity_id"] for i in cand["items"]] == res["preselect"][r["id"]]
        assert cand["items"][0]["named"] is True and "current" not in cand["items"][0] and "used_by" not in cand["items"][0]
    assert res["plan"]["new_helpers"] == []
    # A change would not tick one of the net's own helpers in the role of the helper the user named.
    assert ai.preselect(hass, res["plan"], "entity_id: schedule.tests\n") == {}

    # Built with them: the plan comes back from the browser, and the helpers are in the logic and on the card.
    sched, litres, limit = (f"role:{r['id']}" for r in named)
    build = copy.deepcopy(GARDEN_LADDER)
    cfg = build["config"]
    cfg["triggers"] = [{"trigger": "state", "entity_id": sched, "to": "on", "id": "start"},
                       {"trigger": "numeric_state", "entity_id": "role:water_meter", "above": litres, "id": "amount_reached"},
                       {"trigger": "state", "entity_id": "role:garden_valve", "to": "on",
                        "for": {"minutes": "{{ states('" + limit + "') | int(30) }}"}, "id": "time_limit"}]
    cfg["actions"][0]["choose"][0]["conditions"] = [{"condition": "trigger", "id": "start"}]  # the schedule has the days
    selections = {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"],
                  "weather": ["weather.home"], **res["preselect"]}
    with patch.object(ai, "async_llm_json", return_value=build) as llm:
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": USER_REQUEST}],
                                        "plan": res["plan"], "selections": selections})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    sent = llm.call_args.args[3][-1]["content"]
    assert all(USER_HELPERS[e] in sent for e in (SCHEDULE, LITRES, LIMIT))
    doc = yaml.safe_load(built["yaml"])
    assert doc["triggers"][0] == {"trigger": "state", "entity_id": SCHEDULE, "to": "on", "id": "start"}
    assert doc["triggers"][1]["above"] == LITRES and LIMIT in doc["triggers"][2]["for"]["minutes"]
    card = yaml.safe_load(built["card_yaml"])
    # [v3.63.0] The settings, then after a divider the valve the logic switches (the user asked for it).
    # [CHANGED 2026-11-01, v3.79.0] The schedule a group of its own; under the valve what the logic reads.
    assert [row.get("entity") for row in card["entities"]] == [SCHEDULE, None, LITRES, LIMIT, None, "switch.garden_valve",
                                                               "sensor.water_meter", "weather.home"]
    assert built["round_trip"]["ok"], built["round_trip"]


async def test_a_named_helper_goes_into_the_role_meant_for_it(hass, home):
    """When the model did plan a role for the helper - one whose words found it, or one for a new helper of its
    very name - it is ticked there and that role gets no new helper. Two roles that found it equally both list
    it first and neither ticks it: the user picks."""
    _user_helpers(hass)
    raw = {"intent": "create",
           "roles": [{"id": "amount", "label": "Amount", "purpose": "condition", "domains": ["input_number"],
                      "device_classes": [], "keywords": [HE["litres"]], "area_keywords": []}],
           "new_helpers": [
               {"role": "amount", "domain": "input_number", "name": "Garden litres", "settings": {"min": 0, "max": 500}},
               {"role": "limit", "domain": "input_number", "name": USER_HELPERS[LIMIT], "settings": {"min": 1, "max": 120}},
               {"role": "days", "domain": "schedule", "name": "Watering days", "settings": {}}]}
    plan = ai.clean_plan(hass, raw)
    candidates = {r["id"]: ai.find_candidates(hass, r) for r in plan["roles"]}
    picks = ai.roles_for_named_helpers(hass, plan, [SCHEDULE, LITRES, LIMIT], candidates, "")
    assert picks == {"schedule_lvkh_zmnym_lhshqyyt_gynh": [SCHEDULE], "amount": [LITRES], "limit": [LIMIT]}
    assert candidates["limit"]["items"][0]["entity_id"] == LIMIT and candidates["limit"]["exact"] is True
    # The schedule was found by no role meant for it: the "days" role is for a new helper, and a proposal of
    # another name stays - whether a second schedule is wanted is the user's call, not a guess.
    assert [h["name"] for h in plan["new_helpers"]] == ["Watering days"]
    assert [r["id"] for r in plan["roles"]] == ["amount", "limit", "days", "schedule_lvkh_zmnym_lhshqyyt_gynh"]
    # The plan comes back from the browser and is cleaned again: the marks survive.
    again = ai.clean_plan(hass, copy.deepcopy(plan))
    assert next(r for r in again["roles"] if r["id"].startswith("schedule_")) == plan["roles"][-1]

    both = [{"id": i, "label": i, "purpose": "condition", "domains": ["input_number"], "device_classes": [],
             "keywords": [HE["watering"]], "area_keywords": []} for i in ("a", "b")]
    plan = ai.clean_plan(hass, {"intent": "create", "roles": both})
    candidates = {r["id"]: ai.find_candidates(hass, r) for r in plan["roles"]}
    assert [i["entity_id"] for i in candidates["a"]["items"]] == [LIMIT, LITRES]
    assert ai.roles_for_named_helpers(hass, plan, [LITRES], candidates, "") == {}
    assert [(c["items"][0]["entity_id"], c["items"][0]["named"]) for c in candidates.values()] == [(LITRES, True)] * 2
    assert len(plan["roles"]) == 2
    # A question builds nothing, so nothing is offered.
    assert ai.roles_for_named_helpers(hass, {"intent": "answer", "roles": [], "new_helpers": []}, [LITRES], {}, "") == {}


async def test_a_helper_the_user_names_is_offered_although_another_automation_uses_it(hass, libi_ai):
    """Helpers another automation uses are left out (v3.56.0) - but not one the user names: "use my helper X"
    is the user's own choice. The chat says who else uses it."""
    config_text = await _used_helpers_home(hass)
    plan = ai.clean_plan(hass, {"intent": "create", "roles": [copy.deepcopy(LITRES_ROLE)]})
    candidates = {"litres": ai.find_candidates(hass, LITRES_ROLE)}
    named = ai.helpers_named(hass, "use my helper garden litres used")
    assert named == ["input_number.garden_litres_used"]
    assert ai.roles_for_named_helpers(hass, plan, named, candidates, config_text) == {"litres": named}
    ai.drop_used_helpers(hass, candidates, config_text)
    first, *rest = candidates["litres"]["items"]
    assert (first["entity_id"], first["named"], first["used_by"]) == (named[0], True, ["Other watering"])
    # The one nobody named that a template uses is still left out, and counted.
    assert [i["entity_id"] for i in rest] == ["input_number.garden_litres_free"]
    assert candidates["litres"]["hidden_used"] == 1


# [ADDED 2026-11-01] The user's chat after NET 3 was deleted with its local variables (v3.77.0): the same request still
# names the schedule and the litres helper ("I already have a helper ..., use it"), and both are gone.
LEFT_HELPERS = {  # the user's helpers on 2026-11-01 08:29, read from their Home Assistant: the garden ones went at 08:28
    "schedule.work_days_guy": "Work Days Guy", "schedule.tests": "testS", "schedule.work_days_yulia": "Work Days Yulia",
    "input_number.work_alert_offset_guy": "Work Alert Offset Guy",
    "input_number.work_alert_offset_yulia": "Work Alert Offset Yulia",
    "input_datetime.work_entry_time_guy": "Work Entry Time Guy",
}
GONE_REQUEST = USER_REQUEST + HE["card_line"]
GONE_NAMES = [HE["garden_watering_schedule"], HE["water_amount_in_litres"]]


def _left_helpers(hass):
    for eid, name in LEFT_HELPERS.items():
        hass.states.async_set(eid, "off", {"friendly_name": name})


def _setting_role(rid, label, purpose, domains, keywords):
    return {"id": rid, "label": label, "purpose": purpose, "domains": domains, "device_classes": [],
            "keywords": keywords, "area_keywords": []}


def _gone_plan():
    """The plan as the model answered the user on 2026-11-01: a role for each helper the message says exists, with the
    word of its kind among the keywords, and a new helper for the time limit only."""
    lines = [(HE["requirement_lines"][0], "days"), (HE["requirement_lines"][1], "amount"),
             (HE["requirement_lines"][2], "weather_now"), (HE["requirement_lines"][3], "forecast"),
             (HE["requirement_lines"][4], "time_limit"), (HE["requirement_lines"][5], "message"),
             (HE["requirement_lines"][6], "other"), (HE["requirement_lines"][7], "card")]
    roles = copy.deepcopy(GARDEN_PLAN["roles"]) + [
        _setting_role("watering_schedule", HE["helper_garden_watering_schedule"], "trigger", ["schedule"],
                      ["schedule", "watering", GONE_NAMES[0]]),
        _setting_role("litres", HE["helper_water_amount_in_litres"], "condition", ["input_number"],
                      ["number", "litres", GONE_NAMES[1]]),
        _setting_role("max_minutes", HE["max_watering_minutes"], "condition", ["input_number"], ["minutes"])]
    return {"reply": HE["understood"], "intent": "create", "target_net": "", "level": "automation",
            "name": HE["smart_garden_watering_management"], "questions": [], "roles": roles,
            "requirements": [{"id": f"r{i}", "text": text, "kind": kind} for i, (text, kind) in enumerate(lines, start=1)],
            "new_helpers": [{"role": "max_minutes", "domain": "input_number", "name": HE["max_watering_minutes"],
                             "settings": {"min": 1, "max": 120, "step": 1, "mode": "slider", "icon": "mdi:timer-sand"}}]}


async def test_a_helper_the_message_names_that_is_gone_is_proposed_again(hass, garden, hass_ws_client):
    """[ADDED 2026-11-01] The user's report: "it made me no variable for the watering start time and the amount of
    water". NET 3 had been deleted with its local variables, and the request still said "I already have a helper ...,
    use it" of the schedule and of the litres. The chat listed the user's other schedules and numbers in those roles as
    exact matches - "schedule" and "number" are in the entity_id of every one - so it proposed no helper for either, no
    alarm clock either, and Build waited for a pick. A named helper that is gone is proposed again under the user's name
    for it. [CHANGED 2026-11-10, v3.95.0] The schedule too, as the week schedule - a schedule the user names is used as it
    is (the user's choice): its blocks start and end the watering, and no alarm clock is proposed beside it."""
    _left_helpers(hass)
    assert ai.helpers_named(hass, GONE_REQUEST) == []
    assert ai.helpers_missing(hass, GONE_REQUEST) == GONE_NAMES
    client = await hass_ws_client(hass)
    llm, sent = _model(_gone_plan())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": GONE_REQUEST}]})
        res = (await client.receive_json())["result"]
    plan = res["plan"]
    assert [(h["role"], h["domain"], h["name"]) for h in plan["new_helpers"]] == [
        ("max_minutes", "input_number", HE["max_watering_minutes"]), (ai.SCHEDULE_ROLE, "schedule", GONE_NAMES[0]),
        ("litres", "input_number", GONE_NAMES[1])]
    roles = {r["id"]: r for r in plan["roles"]}
    assert roles["litres"]["missing"] == GONE_NAMES[1] and res["candidates"]["litres"]["exact"] is False
    schedule = roles[ai.SCHEDULE_ROLE]
    assert (schedule["missing"], schedule.get("replaced"), schedule["purpose"]) == (GONE_NAMES[0], None, "trigger")
    assert not {"start_time", "days", "watering_schedule"} & set(roles) and res["preselect"] == {}
    assert ai.DAYS_QUESTION not in [q["id"] for q in plan["questions"]]
    # The model was told which of the names the message quotes nothing in this Home Assistant has.
    told = sent[0][-1]["content"]
    assert "NAMED, NOT FOUND" in told and all(f'"{name}"' in told for name in GONE_NAMES)
    assert "NAMED, NOT FOUND" in ai.PLAN_SYSTEM
    # The plan comes back from the browser and is cleaned again: the marks survive.
    def marks(roles):
        return [(r["id"], r.get("missing"), r.get("replaced"), bool(r.get("optional"))) for r in roles]
    assert marks(ai.clean_plan(hass, copy.deepcopy(plan))["roles"]) == marks(plan["roles"])

    # Created as the chat creates them, then built: the week schedule starts it and ends it, and the most minutes still
    # hold the valve closed after them - the time limit the request asks for.
    hass.states.async_set("schedule.watering", "off", {"friendly_name": GONE_NAMES[0]})
    hass.states.async_set("input_number.litres", "0", {"friendly_name": GONE_NAMES[1], "min": 0, "max": 100})
    hass.states.async_set("input_number.minutes", "30", {"friendly_name": HE["max_watering_minutes"], "min": 1, "max": 120})
    selections = {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"],
                  "weather": ["weather.home"], ai.SCHEDULE_ROLE: ["schedule.watering"],
                  "litres": ["input_number.litres"], "max_minutes": ["input_number.minutes"]}
    llm, sent = _model(_week_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "share": True, "plan": plan,
                                        "selections": selections,
                                        "messages": [{"role": "user", "content": GONE_REQUEST}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    assert [i["ok"] for i in built["checklist"] if i["ok"] is False] == [], built["checklist"]
    told = " ".join(sent[0][-1]["content"].split())
    assert 'SCHEDULE (the user sets its blocks - the days, and the hours of each day)' in told
    assert f'"entity_id": "role:{ai.SCHEDULE_ROLE}", "to": "off", "id": "end"' in told and "ALARM CLOCK" not in told
    doc = yaml.safe_load(built["yaml"])
    assert {"trigger": "state", "entity_id": "schedule.watering", "to": "on", "id": "start"} in doc["triggers"]
    assert {"trigger": "state", "entity_id": "schedule.watering", "to": "off", "id": "end"} in doc["triggers"]
    assert not any(t.get("trigger") == "time" for t in doc["triggers"])
    # The request has no line for the time: LIBI checks the start of a block with a line of its own, and the end always.
    assert [i["id"] for i in built["checklist"] if i["id"].startswith("week_")] == ["week_start", "week_end"]
    # The card: the schedule first - tapped, its settings set the days and the hours - then the settings, the valve and
    # what the logic reads. Only Home Assistant's own rows: the card works without LIBI.
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    assert [(r.get("entity"), r.get("name")) for r in rows] == [
        ("schedule.watering", GONE_NAMES[0]), (None, None),
        ("input_number.litres", GONE_NAMES[1]), ("input_number.minutes", hass.states.get("input_number.minutes").name), (None, None),
        ("switch.garden_valve", "Garden valve"), ("sensor.water_meter", "Water meter"), ("weather.home", "Home")]
    assert "custom:" not in built["card_yaml"]


async def test_without_sharing_the_model_is_not_told_but_the_helpers_are_proposed(hass, garden, hass_ws_client):
    """[ADDED 2026-11-01] Which names this Home Assistant lacks is a fact about it: the model hears it only when the user
    shares the helpers. LIBI proposes the helpers either way."""
    _left_helpers(hass)
    client = await hass_ws_client(hass)
    llm, sent = _model(_gone_plan())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": False,
                                        "messages": [{"role": "user", "content": GONE_REQUEST}]})
        res = (await client.receive_json())["result"]
    assert "NAMED, NOT FOUND" not in sent[0][-1]["content"] and GONE_NAMES[0] in sent[0][-1]["content"]
    assert [h["role"] for h in res["plan"]["new_helpers"]] == ["max_minutes", ai.SCHEDULE_ROLE, "litres"]


async def test_a_quoted_name_is_a_helper_only_where_a_role_for_a_setting_holds_it(hass, home):
    """[ADDED 2026-11-01] A quoted name nothing has is the user's helper only in the role of a setting whose label or words
    hold it. A message in quotes, a device named so, and a role the user's own helper fills are left alone; the model's
    proposal for the role takes the user's name, and one it made under that name in a role of its own is that helper."""
    _left_helpers(hass)
    text = HE["quoted_names"]
    assert ai.helpers_missing(hass, text) == [GONE_NAMES[1], "Garden Days", "Pool time", "watering is done"]
    assert ai.helpers_missing(hass, "no quotes at all") == [] and ai.missing_context([]) == ""
    # Every pair is taken: one too short, empty or too long to be a name does not shift the pairs after it.
    assert ai.helpers_missing(hass, f'the helper "x", "" and "{"a" * 70}", then "Pool pump"') == ["Pool pump"]
    # Nor does a quote left open on one line pair with the next line's.
    assert ai.helpers_missing(hass, 'a quote "that never ends\nand "Pool pump"') == ["Pool pump"]
    assert ai.missing_context(["Garden Days"]) == 'NAMED, NOT FOUND (nothing in this Home Assistant has these names):\n- "Garden Days"'

    def plan_of(roles, helpers=()):
        kept, roles = ai.clean_new_helpers(copy.deepcopy(list(helpers)), copy.deepcopy(roles))
        return {"intent": "create", "name": "Garden", "roles": roles, "new_helpers": kept, "requirements": []}
    # Someone else's helper that a word of the role finds by its name: found, and still not the user's.
    hass.states.async_set("input_number.water_heater_minutes", "20", {"friendly_name": "Water heater minutes"})
    litres = _setting_role("litres", HE["helper_water_amount_in_litres"], "condition", ["input_number"], ["number", "water"])
    valve = _setting_role("valve", "Valve for watering is done", "target", ["switch"], [])
    days = _setting_role("days_left", "Days", "condition", ["schedule"], ["garden days"])
    timer = _setting_role("timer", "Pool timer", "condition", ["timer"], ["pool timers"])
    plan = plan_of([litres, valve, days, timer])
    candidates = {r["id"]: ai.find_candidates(hass, r) for r in plan["roles"]}
    assert candidates["litres"]["exact"] is True
    ai.roles_for_missing_helpers(plan, ai.helpers_missing(hass, text), candidates, {"days_left"})
    roles = {r["id"]: r for r in plan["roles"]}
    assert roles["litres"]["missing"] == GONE_NAMES[1] and candidates["litres"]["exact"] is False
    # A device does not hold it, nor a role the user's own helper fills, nor a word that only begins with the name.
    assert not any("missing" in roles[rid] for rid in ("valve", "days_left", "timer"))
    # So LIBI proposes it, under the user's name, in place of listing someone else's helper as the match.
    lone = plan_of([litres])
    candidates = {"litres": ai.find_candidates(hass, litres)}
    ai.roles_for_missing_helpers(lone, [GONE_NAMES[1]], candidates, set())
    ai.helpers_for_open_roles(lone, candidates, {})
    assert [(h["role"], h["name"]) for h in lone["new_helpers"]] == [("litres", GONE_NAMES[1])]
    # The model's own proposal for the role takes the user's name, its settings kept.
    plan = plan_of([litres], [{"role": "litres", "domain": "input_number", "name": "Water amount",
                               "settings": {"min": 0, "max": 500, "step": 5, "unit_of_measurement": "L"}}])
    ai.roles_for_missing_helpers(plan, [GONE_NAMES[1]], {"litres": ai.find_candidates(hass, litres)}, set())
    assert [(h["name"], h["settings"]["max"]) for h in plan["new_helpers"]] == [(GONE_NAMES[1], 500)]
    # The model proposed the helper under the user's name in a role of its own: the second role for it goes.
    plan = plan_of([litres, _setting_role("water_amount", "Water", "condition", ["input_number"], [])],
                   [{"role": "water_amount", "domain": "input_number", "name": GONE_NAMES[1], "settings": {"max": 300}}])
    candidates = {r["id"]: ai.find_candidates(hass, r) for r in plan["roles"]}
    ai.roles_for_missing_helpers(plan, [GONE_NAMES[1]], candidates, set())
    assert [(r["id"], r.get("missing")) for r in plan["roles"]] == [("water_amount", GONE_NAMES[1])]
    assert list(candidates) == ["water_amount"] and [h["role"] for h in plan["new_helpers"]] == ["water_amount"]
    # A question builds nothing.
    answer = {"intent": "answer", "roles": [copy.deepcopy(litres)], "new_helpers": []}
    ai.roles_for_missing_helpers(answer, [GONE_NAMES[1]], {}, set())
    assert "missing" not in answer["roles"][0]


def test_a_setting_is_matched_by_its_name_not_by_the_word_of_its_kind(hass):
    """[ADDED 2026-11-01] "schedule", "number" or "time" is in the entity_id of every schedule, input_number and
    input_datetime: in the user's chat each of their helpers of the kind was an exact match, so LIBI proposed none. A
    setting is matched by its own name; a device still by its whole entity_id."""
    _left_helpers(hass)
    hass.states.async_set("light.porch", "off", {"friendly_name": "Porch"})
    hass.states.async_set("switch.porch_relay", "off", {"friendly_name": "Porch relay"})
    for rid, domains, words in (("s", ["schedule"], ["schedule"]), ("n", ["input_number"], ["number", "input"]),
                                ("t", ["input_datetime"], ["date"])):
        cand = ai.find_candidates(hass, _setting_role(rid, rid, "condition", domains, words))
        assert cand["exact"] is False and cand["items"], (rid, cand)
    # Its own name still is a match: one of the words of the user's helper.
    cand = ai.find_candidates(hass, _setting_role("o", "o", "condition", ["input_number"], ["offset"]))
    assert cand["exact"] is True and len(cand["items"]) == 2
    lights = ai.find_candidates(hass, _setting_role("l", "l", "target", ["light", "switch"], ["light"]))
    assert lights["exact"] is True and [i["entity_id"] for i in lights["items"]] == ["light.porch"]


def test_a_schedule_nothing_fills_gives_way_to_the_alarm_clock_only_where_the_screen_sets_the_days():
    """[ADDED 2026-11-01] A schedule role nothing of the user's fills, set on the screen. [CHANGED 2026-11-10, v3.95.0]
    The user's choice: one the user names and no longer has is proposed again under its name, as the week schedule - a
    schedule the user names is used. Only one found nowhere and not named gives way to the alarm clock, and is taken
    out: LIBI then asks how the days are set (days_question). Nothing set on the screen: the one named is proposed under
    its name; a schedule the model proposes itself (fixed days) and one the user has stay."""
    card = [{"id": "r1", "text": "the days I choose", "kind": "days"}, {"id": "r2", "text": "a card", "kind": "card"}]

    def plan_of(requirements, helpers=(), **role):
        rid = role.pop("rid", "when")
        kept, roles = ai.clean_new_helpers(copy.deepcopy(list(helpers)), [
            {**_setting_role(rid, "Garden schedule", "trigger", ["schedule"], []), **role}])
        return {"intent": "create", "name": "Garden", "roles": roles, "new_helpers": kept,
                "requirements": copy.deepcopy(requirements)}
    gone = plan_of([], missing="Garden schedule")
    ai.helpers_for_open_roles(gone, {"when": {"items": [], "exact": False}}, {})
    assert [(h["domain"], h["name"]) for h in gone["new_helpers"]] == [("schedule", "Garden schedule")]
    assert "replaced" not in gone["roles"][0]
    nowhere = plan_of(card)
    ai.helpers_for_open_roles(nowhere, {"when": {"items": [{"entity_id": "schedule.tests"}], "exact": False}}, {})
    assert [h["role"] for h in nowhere["new_helpers"]] == ["start_time", "days"]
    assert "when" not in {r["id"] for r in nowhere["roles"]}
    for plan in (plan_of(card, missing="Garden schedule"),
                 plan_of(card, [{"role": "when", "domain": "schedule", "name": "Garden schedule", "settings": {}}],
                     missing="Garden schedule")):
        ai.helpers_for_open_roles(plan, {"when": {"items": [{"entity_id": "schedule.tests"}], "exact": False}}, {})
        assert [(h["role"], h["domain"], h["name"]) for h in plan["new_helpers"]] == [
            (ai.SCHEDULE_ROLE, "schedule", "Garden schedule")], plan
        role = next(r for r in plan["roles"] if r["id"] == ai.SCHEDULE_ROLE)
        assert not role.get("replaced") and role["missing"] == "Garden schedule" and role["purpose"] == "trigger"
    for plan, found in ((plan_of(card, [{"role": "when", "domain": "schedule", "name": "Water Mon Tue", "settings": {}}]),
                         False), (plan_of(card), True)):
        ai.helpers_for_open_roles(plan, {"when": {"items": [{"entity_id": "schedule.garden"}], "exact": found}}, {})
        assert "replaced" not in plan["roles"][0] and not any(h["role"] == "start_time" for h in plan["new_helpers"])


async def test_a_water_meter_role_lists_the_meter_that_counts_the_litres(hass, home):
    """The user's meter list: the role asked for water and volume_flow_rate, and the meter that counts the
    litres - the one NET 1 uses - is of class volume, so it was not listed at all; the flow in l/h came first."""
    hass.states.async_set("sensor.valve_garden_summation_delivered", "120", {
        "friendly_name": "valve_garden Summation delivered", "device_class": "volume", "unit_of_measurement": "L"})
    hass.states.async_set("sensor.valve_garden_instantaneous_demand", "0", {
        "friendly_name": "valve_garden Instantaneous demand", "unit_of_measurement": "l/h"})
    hass.states.async_set("sensor.meter_26643_daily_consumption", "300", {
        "friendly_name": "Meter 26643 Daily consumption", "device_class": "water", "unit_of_measurement": "L"})
    hass.states.async_set("sensor.jacuzzi_humidity", "50", {"friendly_name": "Jacuzzi humidity", "device_class": "humidity"})
    role = {"id": "meter", "label": "garden flow meter", "purpose": "measure", "domains": ["sensor"],
            "device_classes": ["water", "volume_flow_rate"], "keywords": ["sensor", "flow", "meter", "garden"],
            "area_keywords": []}
    net1 = {"sensor.valve_garden_summation_delivered": "NET 1 · Valve Garden Turn Off"}
    found = ai.find_candidates(hass, role, net1)
    ids = [i["entity_id"] for i in found["items"]]
    assert ids[0] == "sensor.valve_garden_summation_delivered" and found["items"][0]["on_canvas"] == net1[ids[0]]
    assert {"sensor.valve_garden_instantaneous_demand", "sensor.meter_26643_daily_consumption"} <= set(ids)
    # Another kind of quantity is still left out, and a class the role asked for still ranks above a related one.
    assert "sensor.jacuzzi_humidity" not in ids
    ids = [i["entity_id"] for i in ai.find_candidates(hass, role)["items"]]
    assert ids.index("sensor.meter_26643_daily_consumption") < ids.index("sensor.valve_garden_summation_delivered")


async def test_the_garden_meter_is_offered_when_the_models_words_miss_it(hass, home):
    """[ADDED 2026-10-29] The user's run: the role asked for a water meter in words the house meter (water, m3) and
    the kitchen filter (water) have and the garden valve's meter (volume, L) has not, so the meter was not listed at
    all (0 / 5). A related class is a match: the meter is offered, below the class the role asked for."""
    for eid, name, dclass, unit in (
            ("sensor.meter_26643_daily_consumption", "Meter 26643 Daily consumption", "water", "m³"),
            ("sensor.meter_26643_total_consumption", "Meter 26643 Total consumption", "water", "m³"),
            ("sensor.tami4_filter_water_passed", "Tami4 Filter water passed", "water", "L"),
            ("sensor.valve_garden_summation_delivered", "valve_garden Summation delivered", "volume", "L")):
        hass.states.async_set(eid, "1", {"friendly_name": name, "device_class": dclass, "unit_of_measurement": unit})
    hass.states.async_set("sensor.valve_garden_instantaneous_demand", "0", {
        "friendly_name": "valve_garden Instantaneous demand", "unit_of_measurement": "l/h"})
    hass.states.async_set("sensor.jacuzzi_humidity", "50", {"friendly_name": "Jacuzzi water humidity", "device_class": "humidity"})
    role = {"id": "meter", "label": "flow / water meter", "purpose": "measure", "domains": ["sensor"],
            "device_classes": ["water"], "keywords": ["water", "meter", "consumption", "flow"], "area_keywords": []}
    found = ai.find_candidates(hass, role)
    ids = [i["entity_id"] for i in found["items"]]
    assert found["exact"] and "sensor.valve_garden_summation_delivered" in ids, ids
    assert ids.index("sensor.tami4_filter_water_passed") < ids.index("sensor.valve_garden_summation_delivered")
    # A sensor of no class that none of the words name, and another kind of quantity, are still left out.
    assert "sensor.valve_garden_instantaneous_demand" not in ids and "sensor.jacuzzi_humidity" not in ids


# ---------------------------------------------------------------- a draft that does not hold is corrected (v3.62.0)
async def test_a_threshold_template_of_one_entity_becomes_that_entity(hass, home):
    """The user's Build: "Home Assistant rejected the draft: expected float at 'above'". Home Assistant takes a
    number there, or an input_number, number or sensor - and the template only read the litres helper."""
    hass.states.async_set("input_number.litres", "200", {"friendly_name": "Litres", "min": 0, "max": 500})
    hass.states.async_set("sensor.meter", "20", {"friendly_name": "Meter"})
    plan = ai.clean_plan(hass, {**copy.deepcopy(PLAN), "roles": PLAN["roles"] + [
        {"id": rid, "label": rid, "purpose": "measure", "domains": [domain], "device_classes": [], "keywords": [],
         "area_keywords": []} for rid, domain in (("litres", "input_number"), ("meter", "sensor"))]})
    sel = {**SELECTED, "litres": ["input_number.litres"], "meter": ["sensor.meter"]}

    def wait(above):
        return _with(lambda c: c["actions"].insert(0, {"wait_for_trigger": [
            {"trigger": "numeric_state", "entity_id": "role:meter", "above": above}],
            "timeout": {"minutes": "{{ states('role:litres') | int(30) }}"}, "continue_on_timeout": True}))
    for above in ("{{ states('role:litres') | float(0) }}", "{{ states('role:litres') }}", "{{states('role:litres')|int}}"):
        out = await ai.async_build_draft(hass, plan, sel, wait(above))
        assert out["ok"], (above, out["errors"])
        assert out["auto"]["actions"][0]["wait_for_trigger"][0]["above"] == "input_number.litres"
    # A threshold worked out from the helper is not one entity: Home Assistant's to reject, and the model's to
    # correct - told what to do.
    out = await ai.async_build_draft(hass, plan, sel, wait("{{ states('role:litres') | float(0) - 5 }}"))
    assert out["errors"] == ["Home Assistant rejected the draft: expected float at 'above'"]
    assert "never a template" in ai.repair_request({}, out["errors"], sel)[1]["content"]
    assert ai._threshold("{{ states('light.x') }}") == "{{ states('light.x') }}"


async def test_the_message_services_the_user_names_are_checked(hass, home):
    """The user's test: two phones named as notify services, and the second one is no longer in the Companion app,
    so every draft that sent to it was rejected. LIBI says so in the plan and tells the model."""
    async_mock_service(hass, "notify", "mobile_app_sm_n985f_guy_phone")
    hass.states.async_set("notify.sm_n985f_guy_phone", "unknown", {"friendly_name": "sm_n985f_guy_phone"})
    said = ["send it to notify.mobile_app_sm_n985f_guy_phone and notify.mobile_app_mi_9t_pro.",
            "and to notify.sm_n985f_guy_phone (an entity) and to Notify.Mobile_App_SM_N985F_Guy_Phone again"]
    assert ai.services_named(hass, said) == (["notify.mobile_app_sm_n985f_guy_phone"], ["notify.mobile_app_mi_9t_pro"])
    assert ai.services_named(hass, ["water the garden", ""]) == ([], [])
    roles = [{"id": "phone", "label": "Phone", "purpose": "target", "domains": ["notify"], "device_classes": [],
              "keywords": [], "area_keywords": []},
             {"id": "valve", "label": "Valve", "purpose": "target", "domains": ["switch"], "device_classes": [],
              "keywords": [], "area_keywords": []}]
    plan = {"roles": copy.deepcopy(roles)}
    ai.optional_message_roles(plan, [])
    assert not any(r.get("optional") for r in plan["roles"])  # no service named: the user picks the phone
    ai.optional_message_roles(plan, ["notify.mobile_app_sm_n985f_guy_phone"])
    assert [(r.get("optional"), r.get("message")) for r in plan["roles"]] == [(True, True), (None, None)]
    context = ai.build_context(ai.clean_plan(hass, {"roles": roles}), {}, {}, hass, "", ai.services_named(hass, said))
    assert "notify.mobile_app_sm_n985f_guy_phone: exists, use it as written" in context
    assert "notify.mobile_app_mi_9t_pro: MISSING - it does not exist in this Home Assistant, leave it out" in context
    # A phone role keeps its domain even in a Home Assistant without notify entities, so it can be made optional.
    hass.states.async_remove("notify.sm_n985f_guy_phone")
    assert ai.clean_plan(hass, {"roles": roles})["roles"][0]["domains"] == ["notify"]


def _user_phones(hass):
    """[v3.64.0] Two phones as the Companion app registers them: a notify entity, a config entry with the device's
    name, and a notify service of that name. The user's message names the first; the second may take the place of
    the phone that is no longer registered."""
    reg = er.async_get(hass)
    # [v3.66.0] Each registered by a user whose person the list names, as in the user's Home Assistant.
    hass.states.async_set("person.guy", "home", {"friendly_name": "Guy", "user_id": "u_guy"})
    hass.states.async_set("person.yulia", "home", {"friendly_name": "Yulia", "user_id": "u_yulia"})
    for name, object_id, user, model in (("sm_n985f_guy_phone", "sm_n985f_guy_phone", "u_guy", "SM-N985F"),
                                         ("SM-S938B", "sm_s938b", "u_yulia", "SM-S938B")):
        entry = MockConfigEntry(domain="mobile_app", data={"device_name": name, "webhook_id": object_id, "user_id": user,
                                                           "manufacturer": "samsung", "model": model,
                                                           "secret": "do-not-show-" + object_id})
        entry.add_to_hass(hass)
        reg.async_get_or_create("notify", "mobile_app", object_id, suggested_object_id=object_id, config_entry=entry)
        hass.states.async_set(f"notify.{object_id}", "unknown", {"friendly_name": name})
        async_mock_service(hass, "notify", f"mobile_app_{object_id}")
    async_mock_service(hass, "notify", "send_message")


async def test_the_users_watering_is_built_after_the_ai_corrects_its_answer(hass, garden, hass_ws_client):
    """The user: "not once did it build the automation in a new NET - every time another error". The plan asks for
    the helpers, the valve, the meter and the weather, and LIBI offers the phones: the message names two notify
    services, the second phone is no longer in the Companion app, and the user ticks another phone in its place.
    The first answer writes the litres as a template threshold (LIBI makes it the helper) and sends to the services
    as written - one does not exist, and the phone ticked in its place gets nothing - so it goes back with what is
    wrong; the second answer sends to each ticked phone by its own service (one MOVE NOTIFY each) and is built,
    drawn and kept by the ladder as built."""
    _user_helpers(hass)
    _user_phones(hass)
    request = USER_REQUEST + HE["request_line_two_phones"]

    def role(rid, domain, keywords, purpose="condition", classes=()):
        return {"id": rid, "label": rid, "purpose": purpose, "domains": [domain], "device_classes": list(classes),
                "keywords": keywords, "area_keywords": []}
    plan = {"reply": "ok", "intent": "create", "target_net": "", "level": "automation", "name": "Smart garden watering",
            "roles": [role("schedule", "schedule", [HE["schedule"]], "trigger"), role("litres", "input_number", [HE["litres"]]),
                      role("max_minutes", "input_number", [HE["maximum"]]),
                      role("valve", "switch", ["garden", "valve"], "target"),
                      role("meter", "sensor", ["water", "meter"], "measure", ["water", "volume_flow_rate"]),
                      role("weather", "weather", ["weather"]), role("phone_1", "notify", ["phone"], "target"),
                      role("phone_2", "notify", ["phone"], "target")],
            "questions": [], "new_helpers": []}
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=plan):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": request}]})
        planned = (await client.receive_json())["result"]
    assert planned["plan"]["missing_services"] == ["notify.mobile_app_mi_9t_pro"]
    # [v3.64.0] One phones role by LIBI in place of the model's two, the phone the message names ticked;
    # [v3.66.0] first in the plan, where the note about the phone that does not exist is.
    assert planned["plan"]["roles"][0]["id"] == ai.PHONES_ROLE
    phones = [r for r in planned["plan"]["roles"] if r["domains"] == ["notify"]]
    assert [r["id"] for r in phones] == [ai.PHONES_ROLE] and phones[0]["phones"] is True and not phones[0]["optional"]
    assert planned["preselect"] == {"schedule": [SCHEDULE], "litres": [LITRES], "max_minutes": [LIMIT],
                                    ai.PHONES_ROLE: ["notify.sm_n985f_guy_phone"]}
    assert [i["entity_id"] for i in planned["candidates"][ai.PHONES_ROLE]["items"]] == ["notify.sm_n985f_guy_phone",
                                                                                        "notify.sm_s938b"]

    def answer(*phones):
        notify = [{"action": p, "data": {"message": "The garden did not get its water in time"}} for p in phones]
        return {"reply": "Built.", "level": "automation", "name": "Smart garden watering", "description": "x",
                # [CHANGED 2026-10-29] The ladder way: a trigger with an id for every event, one choose.
                "config": json.dumps({
                    "mode": "queued",
                    "triggers": [{"trigger": "state", "entity_id": "role:schedule", "to": "on", "id": "start"},
                                 {"trigger": "numeric_state", "entity_id": "role:meter",
                                  "above": "{{ states('role:litres') | float(0) }}", "id": "amount_reached"},
                                 {"trigger": "state", "entity_id": "role:valve", "to": "on",
                                  "for": {"minutes": "{{ states('role:max_minutes') | int(30) }}"}, "id": "time_limit"}],
                    "conditions": [],
                    "actions": [{"choose": [
                        {"conditions": [{"condition": "trigger", "id": "start"}],
                         "sequence": [
                             {"action": "weather.get_forecasts", "target": {"entity_id": "role:weather"},
                              "data": {"type": "daily"}, "response_variable": "forecast"},
                             {"condition": "template", "value_template":
                                 "{{ states('role:weather') not in ['rainy', 'pouring'] and forecast['role:weather']"
                                 ".forecast[0].condition not in ['rainy', 'pouring', 'lightning-rainy'] }}"},
                             {"action": "switch.turn_on", "target": {"entity_id": "role:valve"}}]},
                        {"conditions": [{"condition": "trigger", "id": "amount_reached"},
                                        {"condition": "state", "entity_id": "role:valve", "state": "on"}],
                         "sequence": [{"action": "switch.turn_off", "target": {"entity_id": "role:valve"}}]},
                        {"conditions": [{"condition": "trigger", "id": "time_limit"}],
                         "sequence": [{"action": "switch.turn_off", "target": {"entity_id": "role:valve"}}] + notify}]}]}),
                "ui_card": "", "notes": []}
    first = answer("notify.mobile_app_sm_n985f_guy_phone", "notify.mobile_app_mi_9t_pro")
    llm, sent = _model(first, answer("notify.mobile_app_sm_n985f_guy_phone", "notify.mobile_app_sm_s938b"))
    selections = {**planned["preselect"], "valve": ["switch.garden_valve"], "meter": ["sensor.water_meter"],
                  "weather": ["weather.home"], ai.PHONES_ROLE: ["notify.sm_n985f_guy_phone", "notify.sm_s938b"]}
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [garden], "share": True,
                                        "messages": [{"role": "user", "content": request}],
                                        "plan": planned["plan"], "selections": selections})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    assert len(sent) == 2 and built["tries"] == 2
    assert built["repaired"] == [
        "The service notify.mobile_app_mi_9t_pro does not exist in this Home Assistant.",
        "The message does not go to notify.mobile_app_sm_s938b, which the user ticked."]
    # The first answer was told which named service is missing and where the messages go; the second got the
    # first back, with the problems and what to do.
    context = sent[0][-1]["content"]
    assert "notify.mobile_app_mi_9t_pro: MISSING" in context
    assert ("PHONES (send each message to every one of these, one action each): notify.mobile_app_sm_n985f_guy_phone, "
            "notify.mobile_app_sm_s938b") in context
    assert "notify.mobile_app_sm_n985f_guy_phone: exists" not in context  # the ticked phone gets it through the role
    answer_back, problem = sent[1][-2], sent[1][-1]
    assert answer_back["role"] == "assistant" and json.loads(answer_back["content"]) == first
    assert "notify.mobile_app_mi_9t_pro does not exist" in problem["content"]
    assert "Use only services that exist" in problem["content"] and "to exactly the services under PHONES" in problem["content"]
    # The user's entities are never sent back to the model as entity ids, and whose a phone is never reaches it.
    for eid in (SCHEDULE, LITRES, LIMIT, "switch.garden_valve", "sensor.water_meter", "weather.home",
                "notify.sm_n985f_guy_phone", "notify.sm_s938b"):
        assert eid not in answer_back["content"] and eid not in problem["content"], eid
    assert not any(name in m["content"] for call in sent for m in call for name in ("Yulia", "samsung SM-"))
    doc = yaml.safe_load(built["yaml"])
    trig = {t["id"]: t for t in doc["triggers"]}
    assert trig["amount_reached"] == {"trigger": "numeric_state", "entity_id": "sensor.water_meter", "above": LITRES,
                                      "id": "amount_reached"}
    assert trig["time_limit"]["entity_id"] == "switch.garden_valve" and LIMIT in trig["time_limit"]["for"]["minutes"]
    # One MOVE NOTIFY per phone, as the user's ladder shows a message: each with the phone as its TGT.
    limit = doc["actions"][0]["choose"][2]
    assert [a["action"] for a in limit["sequence"][1:]] == ["notify.mobile_app_sm_n985f_guy_phone",
                                                            "notify.mobile_app_sm_s938b"]
    moves = [e for r in built["net"]["rungs"] for e in r["elements"] if e.get("type") == "move" and e.get("mode") == "notify"]
    assert [e["target"] for e in moves] == ["notify.mobile_app_sm_n985f_guy_phone", "notify.mobile_app_sm_s938b"]
    # Drawn, kept by the ladder as built, and with a card for the settings.
    assert built["net"]["source"] == "draft" and built["round_trip"]["ok"], built["round_trip"]
    card = yaml.safe_load(built["card_yaml"])
    # [v3.63.0] The settings, then after a divider the valve the logic switches (the user asked for it).
    # [CHANGED 2026-11-01, v3.79.0] The schedule a group of its own; under the valve what the logic reads.
    assert [row.get("entity") for row in card["entities"]] == [SCHEDULE, None, LITRES, LIMIT, None, "switch.garden_valve",
                                                               "sensor.water_meter", "weather.home"]


async def test_the_build_asks_three_times_at_most_and_keeps_the_best_answer(hass, libi_ai, hass_ws_client):
    """An answer the ladder would change is still better than one that does not hold: after three answers the best
    one is returned, with what the ladder could not keep. A model that cannot be reached for a correction leaves
    the answer it gave."""
    plan = ai.clean_plan(hass, copy.deepcopy(PLAN))
    bad = _with(lambda c: c["actions"].append({"action": "light.turn_on", "target": {"device_id": "abc"}}))
    changed = {"ok": False, "issues": ["changed .actions[0]"]}
    request = {"type": "libi/ai_build", "messages": [{"role": "user", "content": "x"}], "plan": plan,
               "selections": SELECTED}
    client = await hass_ws_client(hass)
    llm, sent = _model(GOOD_BUILD, bad, bad)
    with patch.object(ai, "async_llm_json", new=llm), \
            patch("custom_components.libi.websocket.verify_round_trip", return_value=changed):
        await client.send_json_auto_id(request)
        built = (await client.receive_json())["result"]
    assert len(sent) == 3 and built["tries"] == 3
    assert built["ok"] and built["round_trip"] == changed and built["repaired"] == [] and "net" in built
    assert "LIBI's ladder could not keep this part as written: changed .actions[0]" in sent[1][-1]["content"]
    assert "device_id" in sent[2][-1]["content"]

    asked = []

    async def unreachable(*_args):
        asked.append(1)
        if len(asked) > 1:
            raise ai.AiError("The AI could not be reached.")
        return copy.deepcopy(bad)
    with patch.object(ai, "async_llm_json", new=unreachable):
        await client.send_json_auto_id(request)
        res = await client.receive_json()
    built = res["result"]
    assert res["success"] and len(asked) == 2 and built["tries"] == 1
    assert built["ok"] is False and any("device_id" in e for e in built["errors"])


async def test_a_problem_names_the_users_entities_by_their_roles(hass):
    """What goes back to the model names the user's entities as the role references it wrote, also inside an error
    of Home Assistant's, and says what to do for the problems models make most."""
    sel = {"litres": ["input_number.kmvt_mym_lhshqyh_blytrym"], "valve": ["switch.valve_garden_switch"]}
    back = ai.repair_request({"config": "{\"actions\": []}"}, [
        "Home Assistant rejected the draft: Entity input_number.kmvt_mym_lhshqyh_blytrym is not a number at 'above'",
        "'area_id' is not allowed in an AI draft; devices are picked by you.",
        "The draft names switch.valve_garden_switch_2, which you did not pick. It was not used."], sel)
    text = back[1]["content"]
    assert "role:litres is not a number" in text and "input_number.kmvt" not in text
    # A different entity is not a picked one: the model wrote it, and it stays as written.
    assert "switch.valve_garden_switch_2, which you did not pick" in text
    assert "How: Write every device as role:<id>" in text
    assert back[0] == {"role": "assistant", "content": "{\"config\": \"{\\\"actions\\\": []}\"}"}


# ---------------------------------------------------------------- the dashboard card of any NET (v3.63.0)
USER_NET3 = {  # the user's NET 3, as the AI chat built it on 2026-10-29 (the time-limit message shortened)
    "id": "libi_ai_1793263302193", "alias": "Smart garden watering", "mode": "single",
    "triggers": [{"trigger": "state", "entity_id": SCHEDULE, "to": "on"}],
    "conditions": [],
    "actions": [
        {"action": "weather.get_forecasts", "target": {"entity_id": "weather.guy_smart_home"},
         "data": {"type": "daily"}, "response_variable": "forecast"},
        {"if": [{"condition": "template", "value_template":
                 "{{ forecast['weather.guy_smart_home'].forecast[0].condition not in ['rainy', 'pouring', 'lightning-rainy'] }}"}],
         "then": [
             {"action": "switch.turn_on", "target": {"entity_id": "switch.valve_garden_switch"}},
             {"wait_for_trigger": [
                 {"trigger": "numeric_state", "entity_id": "sensor.valve_garden_summation_delivered", "above": LITRES},
                 {"trigger": "state", "entity_id": "switch.valve_garden_switch", "to": "off"}],
              "timeout": {"minutes": "{{ states('" + LIMIT + "') | int(1) }}"}, "continue_on_timeout": True},
             {"if": [{"condition": "template",
                      "value_template": "{{ not wait.trigger is none and wait.trigger.platform == 'numeric_state' }}"}],
              "then": [{"action": "switch.turn_off", "target": {"entity_id": "switch.valve_garden_switch"}}],
              "else": [{"action": "switch.turn_off", "target": {"entity_id": "switch.valve_garden_switch"}},
                       {"if": [{"condition": "template",
                                "value_template": "{{ not wait.trigger is none and wait.trigger.platform == 'state' }}"}],
                        "then": [],
                        "else": [{"action": "notify.mobile_app_sm_n985f_guy_phone",
                                  "data": {"message": "The time limit ended the watering."}}]}]}]}],
}


def _user_garden(hass):
    _user_helpers(hass)
    hass.states.async_set("switch.valve_garden_switch", "off", {"friendly_name": "valve_garden Switch"})
    hass.states.async_set("sensor.valve_garden_summation_delivered", "501",
                          {"friendly_name": "valve_garden Summation delivered", "device_class": "volume",
                           "unit_of_measurement": "L"})
    hass.states.async_set("weather.guy_smart_home", "sunny", {"friendly_name": "Forecast home"})


async def test_a_dashboard_card_is_built_for_any_net(hass, libi_ai, hass_ws_client):
    """The user: "it made no YAML to copy for the UI card". The card the chat showed was gone with the chat, and it
    had no valve, which the user asked for. Any NET has its card in the NET menu now, from what LIBI compiles for
    it: the settings it reads, in the order the logic uses them, and after a divider the devices it switches."""
    _user_garden(hass)
    card = ai.card_for_config(hass, copy.deepcopy(USER_NET3), "Smart garden watering")
    assert card["type"] == "entities" and card["title"] == "Smart garden watering"
    # [CHANGED 2026-11-01, v3.79.0] The schedule, the settings, then the valve with what the logic reads, in the order the
    # logic reads them: the weather, the litres the valve delivered. The notify service is not on it.
    assert [r.get("entity") for r in card["entities"]] == [SCHEDULE, None, LITRES, LIMIT, None, "switch.valve_garden_switch",
                                                           "weather.guy_smart_home", "sensor.valve_garden_summation_delivered"]
    assert card["entities"][1] == card["entities"][4] == {"type": "divider"}
    assert "notify." not in str(card) and card["show_header_toggle"] is False

    # Over the websocket, for the net as the canvas holds it.
    net = yaml_to_ast(hass, copy.deepcopy(USER_NET3))
    net["name"] = HE["smart_garden_watering"]
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/net_card", "net": net})
    res = await client.receive_json()
    assert res["success"], res
    sent = yaml.safe_load(res["result"]["yaml"])
    assert sent["title"] == HE["smart_garden_watering"] and sent["entities"] == card["entities"]
    # A NET that only switches a device still gets a card of it; one with neither gets none.
    plain = {"alias": "x", "triggers": [{"trigger": "state", "entity_id": "input_button.door_button"}],
             "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.salon_ceiling"}}]}
    assert [r["entity"] for r in ai.card_for_config(hass, plain, "x")["entities"]] == ["light.salon_ceiling"]
    nothing = yaml_to_ast(hass, {"alias": "y", "triggers": [{"trigger": "time", "at": "05:00:00"}],
                                 "actions": [{"action": "notify.notify", "data": {"message": "hi"}}]})
    await client.send_json_auto_id({"type": "libi/net_card", "net": nothing})
    assert (await client.receive_json())["result"] == {"yaml": ""}
    # A device action names its entity by registry id: the card finds it there too.
    entry = er.async_get(hass).async_get_or_create("switch", "test", "valve9", suggested_object_id="garden_tap")
    hass.states.async_set(entry.entity_id, "off", {"friendly_name": "Garden tap"})
    by_device = {"alias": "z", "triggers": [{"trigger": "state", "entity_id": SCHEDULE, "to": "on"}],
                 "actions": [{"domain": "switch", "type": "turn_on", "device_id": "d" * 32, "entity_id": entry.id}]}
    assert [r.get("entity") for r in ai.card_for_config(hass, by_device, "z")["entities"]] == [SCHEDULE, None, entry.entity_id]


# ---------------------------------------------------------------- the phones a message goes to (v3.64.0)
async def test_libi_offers_the_phones_the_same_every_run(hass, libi_ai, hass_ws_client):
    """The user: "no repeatability - the same request, and this time it did not let me pick the phones". The model
    planned two phone roles in one run and none in the next. Whenever the message names notify services, the
    phones now come from LIBI: the same list each run, the phone the message names ticked, another one pickable in
    place of the phone that no longer exists."""
    _user_phones(hass)
    assert ai.phone_services(hass) == {"notify.sm_n985f_guy_phone": "notify.mobile_app_sm_n985f_guy_phone",
                                       "notify.sm_s938b": "notify.mobile_app_sm_s938b"}
    request = "send it to notify.mobile_app_sm_n985f_guy_phone and notify.mobile_app_mi_9t_pro"
    base = {"reply": "ok", "intent": "create", "target_net": "", "level": "automation", "name": "x",
            "questions": [], "new_helpers": []}
    phone = {"label": "phone", "purpose": "target", "domains": ["notify"], "device_classes": [], "keywords": [],
             "area_keywords": []}
    without = {**base, "roles": []}
    with_two = {**base, "roles": [{**phone, "id": "phone_1"}, {**phone, "id": "phone_2"}]}
    client = await hass_ws_client(hass)
    runs = []
    for plan in (without, with_two):
        with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(plan)):
            await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": True,
                                            "messages": [{"role": "user", "content": request}]})
            runs.append((await client.receive_json())["result"])
    for res in runs:
        assert [r["id"] for r in res["plan"]["roles"]] == [ai.PHONES_ROLE]
        assert res["preselect"] == {ai.PHONES_ROLE: ["notify.sm_n985f_guy_phone"]}
        assert res["plan"]["missing_services"] == ["notify.mobile_app_mi_9t_pro"]
    assert runs[0]["plan"]["roles"] == runs[1]["plan"]["roles"] and runs[0]["candidates"] == runs[1]["candidates"]
    first, second = runs[0]["candidates"][ai.PHONES_ROLE]["items"]
    assert first["entity_id"] == "notify.sm_n985f_guy_phone" and first["named"] is True
    # [v3.66.0] Whose each phone is and what it is - never anything secret of the app.
    assert (first["owner"], first["device"]) == ("Guy", "samsung SM-N985F")
    assert (second["owner"], second["device"]) == ("Yulia", "samsung SM-S938B") and "named" not in second
    assert "do-not-show" not in json.dumps(runs[0])
    # A message that names no notify service gets no phones role from LIBI.
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(with_two)):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": True,
                                        "messages": [{"role": "user", "content": "tell me when it is done"}]})
        res = (await client.receive_json())["result"]
    assert [r["id"] for r in res["plan"]["roles"]] == ["phone_1", "phone_2"] and res["preselect"] == {}


async def test_a_message_goes_to_each_ticked_phone_by_its_own_service(hass, home):
    """[v3.65.0] The user's ladder shows a message as a MOVE NOTIFY with the phone as its TGT, so the build sends to
    each ticked phone by its own notify service, one action each - not with notify.send_message, which the ladder
    shows as TGT notify.send_message. An answer that leaves out a ticked phone, or sends to one the user did not
    tick, goes back."""
    _user_phones(hass)
    plan = ai.clean_plan(hass, {**copy.deepcopy(PLAN), "roles": PLAN["roles"] + [
        {"id": ai.PHONES_ROLE, "label": "Phones to notify", "purpose": "target", "domains": ["notify"],
         "device_classes": [], "keywords": [], "area_keywords": []}]})
    sel = {**SELECTED, ai.PHONES_ROLE: ["notify.sm_n985f_guy_phone", "notify.sm_s938b"]}

    def message(*steps):
        return _with(lambda c: c["actions"].extend(steps))
    guy = {"action": "notify.mobile_app_sm_n985f_guy_phone", "data": {"message": "done"}}
    other = {"action": "notify.mobile_app_sm_s938b", "data": {"message": "done"}}
    out = await ai.async_build_draft(hass, plan, sel, message(guy, other))
    assert out["ok"], out["errors"]
    net = yaml_to_ast(hass, out["auto"])
    moves = [e for r in net["rungs"] for e in r["elements"] if e.get("type") == "move" and e.get("mode") == "notify"]
    assert [e["target"] for e in moves] == ["notify.mobile_app_sm_n985f_guy_phone", "notify.mobile_app_sm_s938b"]
    out = await ai.async_build_draft(hass, plan, sel, message(guy))
    assert out["errors"] == ["The message does not go to notify.mobile_app_sm_s938b, which the user ticked."]
    to_role = {"action": "notify.send_message", "target": {"entity_id": f"role:{ai.PHONES_ROLE}"},
               "data": {"message": "done"}}
    out = await ai.async_build_draft(hass, plan, sel, message(to_role))
    assert out["errors"] == [
        "The message does not go to notify.mobile_app_sm_n985f_guy_phone, notify.mobile_app_sm_s938b, which the user ticked.",
        "notify.send_message hides the phone on the ladder: send with each phone's own service."]
    only_first = {**SELECTED, ai.PHONES_ROLE: ["notify.sm_n985f_guy_phone"]}
    out = await ai.async_build_draft(hass, plan, only_first, message(guy, other))
    assert out["errors"] == ["notify.mobile_app_sm_s938b is a phone the user did not tick."]
    # The build is told each phone's service; a ticked phone is not listed again as a service to use as written.
    context = ai.build_context(plan, sel, {}, hass, "", (["notify.mobile_app_sm_n985f_guy_phone"], []))
    assert ("PHONES (send each message to every one of these, one action each): notify.mobile_app_sm_n985f_guy_phone, "
            "notify.mobile_app_sm_s938b") in context
    assert "notify.mobile_app_sm_n985f_guy_phone: exists" not in context
    # A notify entity with no service of its own is no phone to offer.
    hass.states.async_set("notify.living_room_tv", "unknown", {"friendly_name": "TV"})
    candidates = {}
    picked = ai.phones_role(hass, {"intent": "create", "roles": []}, [], candidates)
    assert picked == [] and "notify.living_room_tv" not in [i["entity_id"] for i in candidates[ai.PHONES_ROLE]["items"]]


# ---------------------------------------------------------------- the ladder's own elements (v3.65.0, v3.70.0)
async def test_a_schedule_is_a_cmp_like_a_time_or_a_day(hass, home):
    """The user: "I did not need a new schedule block - keep the ladder standard; the solution is the kinds of CMP",
    and then: "it should have chosen CMP DATETIME, so I understand what the trigger is". A schedule is the CMP
    DATETIME block - IN1 the date and time, IN2 the schedule, = while it is on - as a trigger and as a condition. A
    binary sensor stays a contact, and the YAML comes back as it was written."""
    from custom_components.libi.libi_to_yaml import verify_round_trip
    _user_helpers(hass)
    hass.states.async_set("binary_sensor.door", "off", {"friendly_name": "Door"})
    async_mock_service(hass, "switch", "turn_on")
    hass.states.async_set("switch.valve_garden_switch", "off", {"friendly_name": "valve_garden Switch"})
    auto = {"id": "s1", "alias": "Schedule", "mode": "single",
            "triggers": [{"trigger": "state", "entity_id": SCHEDULE, "to": "on"}],
            "conditions": [{"condition": "state", "entity_id": SCHEDULE, "state": "on"},
                           {"condition": "state", "entity_id": "binary_sensor.door", "state": "off"}],
            "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.valve_garden_switch"}}]}
    net = yaml_to_ast(hass, copy.deepcopy(auto))
    els = net["rungs"][0]["elements"]
    assert (els[0]["type"], els[0]["sourceA"], els[0]["sourceB"], els[0]["isTrigger"]) == ("cmp_eq", "datetime", SCHEDULE, True)
    assert (els[1]["type"], els[1]["sourceA"], els[1]["sourceB"]) == ("cmp_eq", "datetime", SCHEDULE)
    assert (els[2]["type"], els[2]["label"]) == ("contact_nc", "binary_sensor.door")
    assert not any(e.get("type") == "schedule" for e in els)
    assert net["rungs"][0]["comment"].startswith(
        "When the schedule lvkh zmnym lhshqyyt gynh starts, if the time is inside the schedule lvkh zmnym lhshqyyt gynh")
    report = verify_round_trip(hass, copy.deepcopy(auto))
    assert report["ok"], report["issues"]


def test_a_branch_sits_only_at_the_top_of_the_actions():
    """The ladder draws an if or a choose at the top of the actions, one rung per option; deeper, it is one block."""
    flat = USER_NET3["actions"][:1] + [{"condition": "template", "value_template": "{{ true }}"},
                                       {"if": [{"condition": "template", "value_template": "{{ true }}"}],
                                        "then": [{"delay": 1}], "else": [{"delay": 2}]},
                                       {"choose": [{"conditions": [], "sequence": [{"delay": 3}]}]}]
    assert ai.nested_branches(flat) == []
    assert ai.nested_branches(USER_NET3["actions"]) == ["actions[1].then[2]", "actions[1].then[2].else[1]"]
    deep = [{"repeat": {"count": 2, "sequence": [{"if": [], "then": []}]}},
            {"parallel": [{"sequence": [{"choose": []}]}, {"if": [], "then": []}]},
            {"choose": [{"conditions": [], "sequence": [{"if": [], "then": []}]}], "default": [{"choose": []}]}]
    assert ai.nested_branches(deep) == ["actions[0].repeat[0]", "actions[1].parallel[0][0]", "actions[1].parallel[1][0]",
                                        "actions[2].choose[0][0]", "actions[2].default[0]"]
    prompt = ai.BUILD_SYSTEM
    for words in ("THE LADDER LIBI DRAWS", "Never put an if or a choose inside another step", "CMP TIME", "CMP DAY",
                  "CMP DATETIME for a schedule", "MOVE NOTIFY", "MOVE TTS", 'a delay, and the "for" of a trigger, is a TON',
                  "Never wait inside a run", "ONE \"choose\" with one option per trigger id",
                  '{"condition": "trigger", "id": "<id>"}'):
        assert words in " ".join(prompt.split()), words


async def test_a_branch_inside_another_step_goes_back(hass, libi_ai, hass_ws_client):
    """The user's NET 3 had its if/else after the wait inside the then of the rain check, so the ladder showed it as
    one MOVE ACTION "if" block. Such an answer is valid, so it is kept as the fallback, and goes back with where
    the branch is; the flat answer that follows is the one built. When every answer keeps the branch deep, the
    answer is offered with a note that says so."""
    _user_garden(hass)
    async_mock_service(hass, "weather", "get_forecasts")
    async_mock_service(hass, "notify", "mobile_app_sm_n985f_guy_phone")
    roles = [{"id": rid, "label": rid, "purpose": "condition", "domains": [eid.split(".")[0]], "device_classes": [],
              "keywords": [], "area_keywords": []} for rid, eid in (
        ("schedule", SCHEDULE), ("litres", LITRES), ("limit", LIMIT), ("valve", "switch.valve_garden_switch"),
        ("meter", "sensor.valve_garden_summation_delivered"), ("weather", "weather.guy_smart_home"))]
    plan = ai.clean_plan(hass, {"intent": "create", "level": "automation", "name": "Garden", "roles": roles})
    selections = {r["id"]: [eid] for r, eid in zip(roles, (SCHEDULE, LITRES, LIMIT, "switch.valve_garden_switch",
                                                            "sensor.valve_garden_summation_delivered",
                                                            "weather.guy_smart_home"), strict=True)}
    nested_config = {k: v for k, v in copy.deepcopy(USER_NET3).items() if k in ("mode", "triggers", "conditions", "actions")}
    # [CHANGED 2026-10-29] The flat answer is the ladder way one: a trigger with an id for every event, one choose.
    rain = nested_config["actions"][1]["if"][0]["value_template"]
    valve = {"entity_id": "switch.valve_garden_switch"}
    flat_config = {"mode": "queued", "conditions": [], "triggers": [
        {"trigger": "state", "entity_id": SCHEDULE, "to": "on", "id": "start"},
        {"trigger": "numeric_state", "entity_id": "sensor.valve_garden_summation_delivered", "above": LITRES,
         "id": "amount_reached"},
        {"trigger": "state", "entity_id": "switch.valve_garden_switch", "to": "on",
         "for": {"minutes": "{{ states('" + LIMIT + "') | int(1) }}"}, "id": "time_limit"}],
        "actions": [{"choose": [
            {"conditions": [{"condition": "trigger", "id": "start"}],
             "sequence": [nested_config["actions"][0], {"condition": "template", "value_template": rain},
                          {"action": "switch.turn_on", "target": valve}]},
            {"conditions": [{"condition": "trigger", "id": "amount_reached"},
                            {"condition": "state", "entity_id": "switch.valve_garden_switch", "state": "on"}],
             "sequence": [{"action": "switch.turn_off", "target": valve}]},
            {"conditions": [{"condition": "trigger", "id": "time_limit"}],
             "sequence": [{"action": "switch.turn_off", "target": valve},
                          {"action": "notify.mobile_app_sm_n985f_guy_phone", "data": {"message": "The time limit ended it."}}]}]}]}

    def answer(config):
        return {"reply": "Built.", "level": "automation", "name": "Garden", "description": "x",
                "config": json.dumps(config), "ui_card": "", "notes": []}
    request = {"type": "libi/ai_build", "messages": [{"role": "user", "content": "x"}], "plan": plan,
               "selections": selections}
    client = await hass_ws_client(hass)
    llm, sent = _model(answer(nested_config), answer(flat_config))
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id(request)
        built = (await client.receive_json())["result"]
    assert built["ok"] and len(sent) == 2 and built["tries"] == 2, built.get("errors")
    assert built["repaired"][:2] == [
        "LIBI's ladder draws an if or a choose only at the top of the actions: actions[1].then[2] sits inside another step.",
        "LIBI's ladder draws an if or a choose only at the top of the actions: actions[1].then[2].else[1] sits inside "
        "another step."]
    # [ADDED 2026-10-29] It waited inside the run as well, which went back with the same answer.
    assert "LIBI's ladder does not wait inside a run: actions[1].then[1] has wait_for_trigger." in built["repaired"]
    assert "Branch only at the top of the actions" in sent[1][-1]["content"]
    assert ai.nested_branches(yaml.safe_load(built["yaml"])["actions"]) == [] and built["round_trip"]["ok"]
    # The notification is a MOVE NOTIFY of its own on the timeout rung, not part of a block.
    moves = [e for r in built["net"]["rungs"] for e in r["elements"] if e.get("type") == "move" and e.get("mode") == "notify"]
    assert [e["target"] for e in moves] == ["notify.mobile_app_sm_n985f_guy_phone"]
    # A model that keeps the branch deep: the answer is still offered, and its notes say what the ladder does.
    llm, sent = _model(answer(nested_config))
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id(request)
        built = (await client.receive_json())["result"]
    assert built["ok"] and len(sent) == 3 and built["tries"] == 3
    assert built["notes"][-2].startswith("Part of this logic is an if or a choose inside another step")
    assert built["notes"][-1].startswith("This logic waits inside a run, which a ladder does not do")


async def test_only_an_admin_gets_a_net_card(hass, libi_ai, hass_ws_client, hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "libi/net_card", "net": {"id": "n1", "rungs": []}})
    res = await client.receive_json()
    assert res["error"]["code"] == "unauthorized"


async def test_the_build_prompt_checks_the_rain_now_and_today(hass, home):
    """The user asked to skip when it rains now or rain is expected today; the build checked only the forecast,
    because that is all the prompt taught. The condition it teaches now is accepted and drawn as written."""
    prompt = ai.BUILD_SYSTEM
    assert "the weather" in prompt and "NOW and forecast[0] is TODAY" in prompt and "'snowy-rainy', 'hail'" in prompt
    # [ADDED 2026-10-31] The user's draft checked the rain now only: the start option reads and checks today's forecast.
    flat = " ".join(prompt.split())
    assert '"sequence": [<weather.get_forecasts, as above>, {"condition": "template"' in flat
    assert "checks both: the weather now AND today's forecast" in flat
    hass.states.async_set("weather.home", "sunny", {"friendly_name": "Home"})
    async_mock_service(hass, "weather", "get_forecasts")
    plan = ai.clean_plan(hass, {**copy.deepcopy(PLAN), "roles": PLAN["roles"] + [
        {"id": "weather", "label": "Weather", "purpose": "condition", "domains": ["weather"], "device_classes": [],
         "keywords": [], "area_keywords": []}]})
    rain = "['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail']"

    def weather_first(config):
        config["actions"][0:0] = [
            {"action": "weather.get_forecasts", "target": {"entity_id": "role:weather"}, "data": {"type": "daily"},
             "response_variable": "forecast"},
            {"condition": "template", "value_template": "{{ states('role:weather') not in " + rain
             + " and forecast['role:weather'].forecast[0].condition not in " + rain + " }}"}]
    out = await ai.async_build_draft(hass, plan, {**SELECTED, "weather": ["weather.home"]}, _with(weather_first))
    assert out["ok"], out["errors"]
    assert "states('weather.home') not in" in out["auto"]["actions"][1]["value_template"]
    from custom_components.libi.libi_to_yaml import verify_round_trip
    report = verify_round_trip(hass, out["auto"])
    assert report["ok"], report["issues"]


def test_the_build_prompt_names_no_wait_block() -> None:
    """[ADDED 2026-10-29] The user's ladder has no WAIT block, and the ladder way never waits inside a run.
    [CHANGED 2026-10-29] The prompt no longer teaches the wait_for_trigger of the garden: a time limit is a for."""
    prompt = " ".join(ai.BUILD_SYSTEM.split())
    assert "WAIT" not in ai.BUILD_SYSTEM and "wait.trigger is none" not in prompt and "continue_on_timeout\": true" not in prompt
    assert 'the time limit (id "time_limit"): {"trigger": "state", "entity_id": "role:<valve>", "to": "on", "for":' in prompt
    assert '{"trigger": "homeassistant", "event": "start", "id": "restarted"}' in prompt


# The user's NET 4 as the chat built it on 2026-10-29 (the texts in English): it waits inside the run, stops, and
# reads wait.trigger in the rungs after the wait.
USER_NET4_ACTIONS = [
    {"action": "weather.get_forecasts", "target": {"entity_id": "weather.guy_smart_home"}, "data": {"type": "daily"},
     "response_variable": "forecast"},
    {"if": [{"condition": "template", "value_template": "{{ states('weather.guy_smart_home') not in ['rainy'] }}"}],
     "then": [{"action": "switch.turn_on", "target": {"entity_id": "switch.valve_garden_switch"}},
              {"wait_for_trigger": [{"trigger": "numeric_state", "entity_id": "sensor.valve_garden_summation_delivered",
                                     "above": LITRES},
                                    {"trigger": "state", "entity_id": "switch.valve_garden_switch", "to": "off"}],
               "timeout": {"minutes": 45}, "continue_on_timeout": True}]},
    {"if": [{"condition": "template", "value_template":
             "{{ not wait.trigger is none and wait.trigger.platform == 'state' }}"}],
     "then": [{"stop": "Stopped by hand"}]},
    {"if": [{"condition": "template", "value_template": "{{ wait.trigger is none }}"}],
     "then": [{"action": "notify.mobile_app_sm_s918b", "data": {"message": "Please wait. The time ran out"}}]},
]


def test_a_draft_that_waits_inside_a_run_goes_back_to_be_written_the_ladder_way():
    """[ADDED 2026-10-29] The user: "the logic is not right at all, the ladder does not fit the logic - see how a YAML
    should look". Their NET 4 waited inside the run and read wait.trigger in the rungs after it, which on a day of
    rain had nothing to read. Every place it waits is found and sent back with how to write it; the ladder way
    answer has none, and a message that says "wait." is not mistaken for one."""
    assert ai.waits_in(USER_NET4_ACTIONS) == [
        "actions[1].then[1] has wait_for_trigger",
        "actions[2].if[0].value_template reads wait.",
        "actions[2].then[0] has stop",
        "actions[3].if[0].value_template reads wait."]
    assert ai.waits_in(GARDEN_LADDER["config"]["actions"]) == []
    draft = {"ok": True, "auto": {"actions": USER_NET4_ACTIONS}}
    problems = ai.draft_problems(draft, {"round_trip": {"ok": True, "issues": []}})
    assert problems[0] == "LIBI's ladder does not wait inside a run: actions[1].then[1] has wait_for_trigger."
    assert ai.draft_rank(draft, {"round_trip": {"ok": True, "issues": []}}) == 1
    back = ai.repair_request({"config": "{}"}, problems, {})[1]["content"]
    assert "How: One trigger with an id for every event" in back and "ONE choose" in back


# ---------------------------------------------------------------- the request, line by line (v3.73.0)
def test_the_request_is_split_into_lines_of_a_kind_libi_checks(hass):
    """[ADDED 2026-10-31] The user checked the logic against the request line by line and found the rain expected today
    missing. The plan splits the request into lines, each of a kind LIBI can see in the logic itself; the texts are
    only shown, and the plan that comes back from the browser is cleaned again."""
    kind = ai.PLAN_SCHEMA["properties"]["requirements"]["items"]["properties"]["kind"]
    assert kind["enum"] == list(ai.REQUIREMENT_KINDS) and "requirements" in ai.PLAN_SCHEMA["required"]
    prompt = " ".join(ai.PLAN_SYSTEM.split())
    for name in ai.REQUIREMENT_KINDS:
        assert f'"{name}"' in prompt, name
    assert '"rain now or rain expected today" is a weather_now line and a forecast line' in prompt
    raw = {"intent": "create", "requirements": [
        {"id": "r1", "text": "  Start at the time I set  ", "kind": "time"},
        {"id": "r1", "text": "the same id again", "kind": "days"},
        {"id": "R 2", "text": "<b>skip</b> when it rains", "kind": "rain"},
        {"id": "r3", "text": "", "kind": "card"},
        "not a line",
        {"text": "x" * 300, "kind": "amount"}]}
    plan = ai.clean_plan(hass, raw)
    # A repeated id and a line without text are dropped, an unknown kind is "other", a long text is cut.
    assert plan["requirements"] == [{"id": "r1", "text": "Start at the time I set", "kind": "time"},
                                    {"id": "r_2", "text": "<b>skip</b> when it rains", "kind": "other"},
                                    {"id": "r6", "text": "x" * 200, "kind": "amount"}]
    assert ai.clean_plan(hass, copy.deepcopy(plan))["requirements"] == plan["requirements"]
    assert ai.clean_plan(hass, {**raw, "intent": "answer"})["requirements"] == []
    many = {"intent": "create", "requirements": [{"id": f"r{i}", "text": f"line {i}", "kind": "other"} for i in range(30)]}
    assert len(ai.clean_plan(hass, many)["requirements"]) == ai.MAX_REQUIREMENTS
    assert "covers" in ai.BUILD_SCHEMA["required"]
    assert "REQUIREMENTS in the message are the user's request" in " ".join(ai.BUILD_SYSTEM.split())


ALARM_LINES = [  # the user's request of 2026-10-31, as the plan splits it: one line per point, each of a kind
    {"id": "r1", "text": "Watering starts at the time I set on the card", "kind": "time"},
    {"id": "r2", "text": "On the days I tick on the card, as on an alarm clock", "kind": "days"},
    {"id": "r3", "text": "Close the valve when the litres pass the amount", "kind": "amount"},
    {"id": "r4", "text": "Skip when it rains now", "kind": "weather_now"},
    {"id": "r5", "text": "Skip when rain is expected today", "kind": "forecast"},
    {"id": "r6", "text": "At most the minutes I set", "kind": "time_limit"},
    {"id": "r7", "text": "Then send me a message", "kind": "message"},
    {"id": "r8", "text": "Closing the valve by hand ends the watering", "kind": "other"},
    {"id": "r9", "text": "A card with all the settings and the valve", "kind": "card"},
]
# [CHANGED 2026-10-31, v3.76.0] The days the user ticks: ONE helper of 8 bits, read by one CMP DAY - the user's design. In
# 3.73.0 - 3.75.0 it was a switch for each day, each checked on its own day.
_TICKED = {"condition": "template", "value_template": ai.day_bits_template("role:days")}
_RAIN = "['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail']"


def _alarm_answer(forecast=True, days="bits"):
    """The user's watering the ladder way, started as an alarm clock: at the time the user sets, on the days the user
    ticks. Without the forecast it is the draft the user got on 2026-10-31: only the rain now was checked.
    [CHANGED v3.95.0] days "switches": a switch for each day, each checked on its own day (days_switches_condition)."""
    start = [{"action": "switch.turn_on", "target": {"entity_id": "role:garden_valve"}}]
    if forecast:
        start[0:0] = [{"action": "weather.get_forecasts", "target": {"entity_id": "role:weather"},
                       "data": {"type": "daily"}, "response_variable": "forecast"},
                      {"condition": "template",
                       "value_template": "{{ forecast['role:weather'].forecast[0].condition not in " + _RAIN + " }}"}]
    valve = {"entity_id": "role:garden_valve"}
    config = {"mode": "single", "conditions": [], "triggers": [
        {"trigger": "time", "at": "role:start_time", "id": "start"},
        {"trigger": "numeric_state", "entity_id": "role:water_meter", "above": "role:litres", "id": "amount_reached"},
        {"trigger": "state", "entity_id": "role:garden_valve", "to": "on",
         "for": {"minutes": "{{ states('role:max_minutes') | int(30) }}"}, "id": "time_limit"},
        {"trigger": "homeassistant", "event": "start", "id": "restarted"}],
        "actions": [{"choose": [
            {"conditions": [{"condition": "trigger", "id": "start"}, copy.deepcopy(_TICKED) if days == "bits" else
                            ai.days_switches_condition({d: f"role:day_{d}" for d in DAYS}),
                            {"condition": "template", "value_template": "{{ states('role:weather') not in " + _RAIN + " }}"}],
             "sequence": start},
            {"conditions": [{"condition": "trigger", "id": "amount_reached"}],
             "sequence": [{"action": "switch.turn_off", "target": valve}]},
            {"conditions": [{"condition": "trigger", "id": "time_limit"}],
             "sequence": [{"action": "switch.turn_off", "target": valve},
                          {"action": "notify.notify", "data": {"message": "The time limit ended the watering."}}]},
            {"conditions": [{"condition": "trigger", "id": "restarted"},
                            {"condition": "state", "entity_id": "role:garden_valve", "state": "on"}],
             "sequence": [{"action": "switch.turn_off", "target": valve}]}]}]}
    return {"reply": "Built.", "level": "automation", "name": "Garden watering", "description": "x",
            "config": json.dumps(config), "ui_card": "", "notes": [],
            "covers": [{"requirement": "r8", "trigger_id": "", "how": "Nothing opens the valve again once it is closed."},
                       {"requirement": "r6", "trigger_id": "time_limit", "how": "The valve on for the minutes set."}]}


def _week_answer():
    """[ADDED v3.95.0] The same watering on the week schedule: a block starts it, the block's end closes the valve, and
    the most minutes and the amount still close it within the block."""
    answer = _alarm_answer()
    config = json.loads(answer["config"])
    config["triggers"][0] = {"trigger": "state", "entity_id": f"role:{ai.SCHEDULE_ROLE}", "to": "on", "id": "start"}
    config["triggers"].insert(1, {"trigger": "state", "entity_id": f"role:{ai.SCHEDULE_ROLE}", "to": "off", "id": "end"})
    options = config["actions"][0]["choose"]
    options[0]["conditions"] = [c for c in options[0]["conditions"] if c != _TICKED]
    options.insert(1, {"conditions": [{"condition": "trigger", "id": "end"}],
                       "sequence": [{"action": "switch.turn_off", "target": {"entity_id": "role:garden_valve"}}]})
    return {**answer, "config": json.dumps(config)}


def _alarm_plan(hass):
    """The garden of the garden fixture with the helpers of an alarm clock: a start time and the days helper (8 bits; 21
    is Sunday, Tuesday and Thursday), the litres and the most minutes."""
    hass.states.async_set("input_datetime.garden_start", "05:00:00", {"friendly_name": "Watering - start",
                                                                      "has_time": True, "has_date": False})
    hass.states.async_set("input_number.garden_days", "21", {"friendly_name": "Watering - days", "min": 0, "max": 255,
                                                              "step": 1})
    hass.states.async_set("input_number.garden_litres", "200", {"friendly_name": "Litres", "min": 0, "max": 500})
    hass.states.async_set("input_number.garden_max_minutes", "60", {"friendly_name": "Max minutes", "min": 1, "max": 120})

    def role(rid, domain, purpose="condition"):
        return {"id": rid, "label": rid, "purpose": purpose, "domains": [domain], "device_classes": [],
                "keywords": [], "area_keywords": []}
    roles = GARDEN_PLAN["roles"] + [role("start_time", "input_datetime", "trigger"), role("days", "input_number"),
                                    role("litres", "input_number"), role("max_minutes", "input_number")]
    plan = ai.clean_plan(hass, {**copy.deepcopy(GARDEN_PLAN), "intent": "create", "target_net": "", "roles": roles,
                                "requirements": copy.deepcopy(ALARM_LINES)})
    selections = {"garden_valve": ["switch.garden_valve"], "water_meter": ["sensor.water_meter"],
                  "weather": ["weather.home"], "start_time": ["input_datetime.garden_start"],
                  "litres": ["input_number.garden_litres"], "max_minutes": ["input_number.garden_max_minutes"],
                  "days": ["input_number.garden_days"]}
    return plan, selections


async def test_the_alarm_clock_watering_is_checked_line_by_line(hass, garden, hass_ws_client):
    """[ADDED 2026-10-31] The user's draft checked the rain now and not the rain expected today, and its card could not
    set the days and the hours. LIBI checks each line of the request in the logic: the draft without the forecast goes
    back with what it misses and how to add it; the answer that follows does every line, each shown with its rung.
    The days are an alarm clock's: the time on the card, then the days helper as LIBI's row of checkboxes."""
    plan, selections = _alarm_plan(hass)
    request = {"type": "libi/ai_build", "nets": [], "messages": [{"role": "user", "content": "water the garden"}],
               "plan": plan, "selections": selections}
    client = await hass_ws_client(hass)
    llm, sent = _model(_alarm_answer(forecast=False), _alarm_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id(request)
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    assert len(sent) == 2 and built["tries"] == 2
    told = sent[0][-1]["content"]
    assert "REQUIREMENTS (the logic must do every one" in told and "- r5 (forecast): Skip when rain is expected today" in told
    missing = ('The request asks "Skip when rain is expected today" (forecast), and the logic does not do it: it never '
               'reads the forecast (weather.get_forecasts).')
    assert built["repaired"] == [missing]
    back = sent[1][-1]["content"]
    assert missing in back and "How: Keep everything else and add it the ladder way" in back
    # Every line, where it is: a line of a kind LIBI sees in the logic is checked there; the other is the AI's word only.
    lines = {item["id"]: (item["ok"], item["rung"]) for item in built["checklist"]}
    assert lines == {"r1": (True, 1), "r2": (True, 1), "r3": (True, 2), "r4": (True, 1), "r5": (True, 1),
                     "r6": (True, 3), "r7": (True, 3), "r8": (None, 0), "r9": (True, 0)}
    other = next(i for i in built["checklist"] if i["id"] == "r8")
    assert other["how"] == "Nothing opens the valve again once it is closed." and other["missing"] == ""
    assert [i["text"] for i in built["checklist"]] == [line["text"] for line in ALARM_LINES]
    # The first rung is the alarm clock: CMP TIME at the time set, then ONE CMP DAY of the days helper.
    first = built["net"]["rungs"][0]["elements"]
    assert (first[0]["type"], first[0]["sourceA"], first[0]["sourceB"], first[0]["isTrigger"]) == (
        "cmp_eq", "time", "input_datetime.garden_start", True)
    assert (first[1]["type"], first[1]["sourceA"], first[1]["sourceB"], first[1]["kind"]) == (
        "cmp_eq", "weekday", "input_number.garden_days", "date")
    assert built["round_trip"]["ok"], built["round_trip"]
    # The card, as an alarm clock reads: the time, the days as LIBI's row of checkboxes, the other settings, the valve.
    # [CHANGED 2026-11-01, v3.79.0] Each group after a divider, and without the words the days are named after
    # ("Watering - start", "Watering - days").
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    assert rows[0] == {"entity": "input_datetime.garden_start", "name": "Start"}
    assert rows[1] == {"type": "custom:libi-days-row", "entity": "input_number.garden_days", "name": "Days"}
    assert [r.get("entity") for r in rows[2:]] == [None, "input_number.garden_litres", "input_number.garden_max_minutes",
                                                   None, "switch.garden_valve", "sensor.water_meter", "weather.home"]


async def test_a_line_the_logic_still_misses_is_shown_and_the_card_of_a_net_is_an_alarm_clock(hass, garden, hass_ws_client):
    """[ADDED 2026-10-31] A model that leaves the forecast out in every answer: the draft is still offered - it holds -
    and its checklist says which line is not in the logic, and why. The dashboard card made later from the NET menu
    shows the days as the build's card does."""
    plan, selections = _alarm_plan(hass)
    client = await hass_ws_client(hass)
    llm, sent = _model(_alarm_answer(forecast=False))
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "messages": [{"role": "user", "content": "water the garden"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"] and len(sent) == 3 and built["tries"] == 3 and built["repaired"] == []
    gone = [i for i in built["checklist"] if i["ok"] is False]
    assert [(i["id"], i["missing"]) for i in gone] == [("r5", "it never reads the forecast (weather.get_forecasts)")]
    # A draft that does not hold has no checklist: there is no logic to check; a line LIBI cannot check is no problem.
    assert ai.requirement_report(plan, {"ok": False}, {}, {}) == []
    assert ai.requirement_problems([{"ok": None, "text": "x", "kind": "other", "missing": ""}]) == []
    card = ai.card_for_config(hass, yaml.safe_load(built["yaml"]), "Garden")
    assert card["entities"][0]["entity"] == "input_datetime.garden_start"
    assert card["entities"][1] == {"type": "custom:libi-days-row", "entity": "input_number.garden_days", "name": "Days"}


def test_each_kind_of_line_is_seen_in_the_logic_and_nothing_else_is():
    """[ADDED 2026-10-31] How LIBI sees each kind of line in a configuration. The weather now is a check of the weather
    entity's state, never today's forecast - the user's request asked for both, and the draft had only one of them."""
    now = {"condition": "template", "value_template": "{{ states('weather.home') not in ['rainy'] }}"}
    today = {"condition": "template", "value_template": "{{ forecast['weather.home'].forecast[0].condition != 'rainy' }}"}
    read = {"action": "weather.get_forecasts", "target": {"entity_id": "weather.home"}, "data": {"type": "daily"},
            "response_variable": "forecast"}
    seen = {
        "weather_now": ([now, {"condition": "state", "entity_id": "weather.home", "state": "rainy"},
                         {"condition": "template", "value_template": "{{ is_state('weather.home', 'rainy') }}"}],
                        [today, read, {"condition": "state", "entity_id": "sensor.rain", "state": "on"}]),
        "forecast": ([read], [now, today]),
        "time": ([{"trigger": "time", "at": "05:00:00"}, {"trigger": "sun", "event": "sunset"},
                  {"trigger": "time_pattern", "minutes": "/5"}, {"trigger": "state", "entity_id": "schedule.garden", "to": "on"},
                  {"condition": "time", "after": "06:00:00"}],
                 [{"condition": "time", "weekday": "mon"}, {"trigger": "state", "entity_id": "switch.valve", "to": "on"}]),
        "days": ([{"condition": "time", "weekday": ["mon"]}, {"condition": "state", "entity_id": "schedule.garden", "state": "on"}],
                 [{"trigger": "time", "at": "05:00:00"}, {"condition": "state", "entity_id": "input_boolean.x", "state": "on"}]),
        "amount": ([{"trigger": "numeric_state", "entity_id": "sensor.m", "above": 5},
                    {"condition": "numeric_state", "entity_id": "sensor.m", "below": 5}],
                   [{"trigger": "state", "entity_id": "sensor.m"}]),
        "time_limit": ([{"delay": {"minutes": 5}}, {"trigger": "state", "entity_id": "switch.v", "to": "on", "for": {"minutes": 9}},
                        {"condition": "state", "entity_id": "switch.v", "state": "on", "for": "00:05:00"}],
                       [{"trigger": "state", "entity_id": "switch.v", "to": "on", "for": {}},
                        {"action": "switch.turn_on", "target": {"entity_id": "switch.v"}}]),
        "message": ([{"action": "notify.mobile_app_sm_s918b", "data": {"message": "x"}},
                     {"action": "persistent_notification.create", "data": {"message": "x"}}, {"action": "tts.speak"}],
                    [{"action": "switch.turn_on"}, {"action": "notifyx.y"}]),
    }
    assert set(seen) | {"card", "other"} == set(ai.REQUIREMENT_KINDS)
    for kind, (yes, no) in seen.items():
        for node in yes:
            assert ai._KIND_TESTS[kind](node), (kind, node)
        for node in no:
            assert not ai._KIND_TESTS[kind](node), (kind, node)


async def test_a_schedule_the_user_names_is_the_week_schedule(hass, garden, hass_ws_client):
    """[CHANGED 2026-11-10, v3.95.0] The user: "it is better to have both options ... on a certain day I leave an hour
    earlier, which 7 variables cannot do", and the card must work without LIBI. Their message names their schedule ("I
    already have a helper ..., use it"): it is used as it is - the week schedule, ticked - and the alarm clock the model
    proposed beside it goes, with nothing to ask. (From v3.74.0 to v3.94 it gave way to the alarm clock: "no way in the
    UI to choose the days".) Without a schedule named, LIBI asks how the days are set: a switch for each day and a start
    time, or a schedule."""
    _user_helpers(hass)
    alarm = [{"role": "start_time", "domain": "input_datetime", "name": "Watering - start", "settings": {"has_time": True}},
             {"role": "day_sun", "domain": "input_boolean", "name": "Watering - Sun", "settings": {}}]
    lines = [{"id": "r1", "text": "on the days I choose in the UI", "kind": "days"},
             {"id": "r2", "text": "a card with the settings", "kind": "card"}]
    base = {**copy.deepcopy(GARDEN_PLAN), "intent": "create", "target_net": ""}
    client = await hass_ws_client(hass)

    async def plan_for(plan, words=USER_REQUEST):
        with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(plan)):
            await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [garden], "share": True,
                                            "messages": [{"role": "user", "content": words}]})
            return (await client.receive_json())["result"]
    for plan in ({**base, "new_helpers": alarm}, {**base, "new_helpers": [], "requirements": lines}):
        res = await plan_for(plan)
        assert res["plan"]["new_helpers"] == []
        schedule = next(r for r in res["plan"]["roles"] if r["domains"] == ["schedule"])
        assert schedule["id"] == ai.SCHEDULE_ROLE and schedule["purpose"] == "trigger" and not schedule.get("replaced")
        assert res["preselect"][ai.SCHEDULE_ROLE] == [SCHEDULE]
        ticked = [e for ids in res["preselect"].values() for e in ids]
        assert LITRES in ticked and LIMIT in ticked
        assert not {"start_time", "days", "day_sun"} & {r["id"] for r in res["plan"]["roles"]}
        assert ai.DAYS_QUESTION not in [q["id"] for q in res["plan"]["questions"]]
    # Nothing to set on the screen: the schedule the user names is the one used, ticked, in its own role.
    res = await plan_for({**base, "new_helpers": []})
    assert res["plan"]["new_helpers"] == [] and SCHEDULE in [e for ids in res["preselect"].values() for e in ids]
    assert not any(r.get("replaced") for r in res["plan"]["roles"])
    # Without a schedule named: the day switch the model proposed becomes the days helper, and LIBI asks how the days
    # are set - that helper goes, each answer bringing its own variables, named after it.
    res = await plan_for({**base, "new_helpers": alarm}, "water the garden at the time and on the days I set on the card")
    assert [(h["role"], h["name"]) for h in res["plan"]["new_helpers"]] == [("start_time", "Watering - start")]
    question = next(q for q in res["plan"]["questions"] if q["id"] == ai.DAYS_QUESTION)
    switches, week = (question["variants"][c] for c in question["choices"])
    assert [h["name"] for h in switches["helpers"]] == [f"Watering - {d.title()}" for d in DAYS]
    assert [(h["role"], h["domain"], h["name"]) for h in week["helpers"]] == [(ai.SCHEDULE_ROLE, "schedule", "Watering")]
    assert week["drop"] == ["start_time"]
    # A change of the NET ("update NET 3") ticks what the NET uses - but not the schedule that gave way.
    roles = [{"id": "watering_schedule", "domains": ["schedule"], "replaced": True}, {"id": "litres", "domains": ["input_number"]}]
    assert ai.preselect(hass, {"roles": roles}, f"entity_id: {SCHEDULE} above: {LITRES}") == {"litres": [LITRES]}


# ---------------------------------------------------------------- the alarm clock starts the logic (v3.75.0)
SCHEDULE_ROLE = {"id": "watering_schedule", "label": "Garden schedule", "purpose": "trigger", "domains": ["schedule"],
                 "device_classes": [], "keywords": [], "area_keywords": []}


def _by_schedule(answer):
    """The start of the user's NET 3 of 2026-10-31: when the schedule turns on, with the days of the alarm clock."""
    config = json.loads(answer["config"])
    config["triggers"][0] = {"trigger": "state", "entity_id": "role:watering_schedule", "to": "on", "id": "start"}
    return {**answer, "config": json.dumps(config)}


async def _build(client, plan, selections, *answers, nets=(), words="water the garden"):
    llm, sent = _model(*answers)
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": list(nets), "share": bool(nets), "plan": plan,
                                        "selections": selections, "messages": [{"role": "user", "content": words}]})
        return (await client.receive_json())["result"], sent


async def test_the_time_set_on_the_card_starts_the_logic_and_no_schedule_does(hass, garden, hass_ws_client):
    """[ADDED 2026-10-31, v3.75.0] The user: "better - it made a switch for every day, but gave me no field for the
    watering time". The schedule the message named was ticked as well, and the model started the watering when the
    schedule turned on and checked the days with the new switches: the time set on the card was in no rung - so it was
    not on the card either - and the checklist took the schedule for the time. With an alarm clock picked, LIBI tells
    the model that its time starts the logic, and a draft a schedule starts goes back."""
    plan, selections = _alarm_plan(hass)
    hass.states.async_set("schedule.garden", "off", {"friendly_name": "Garden schedule"})
    plan["roles"].append(copy.deepcopy(SCHEDULE_ROLE))
    selections["watering_schedule"] = ["schedule.garden"]
    assert ai.picked_alarm_clock(hass, plan, selections) == {
        "mode": "bits", "time_role": "start_time", "time": "input_datetime.garden_start", "days_role": "days",
        "days": "input_number.garden_days"}
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, _by_schedule(_alarm_answer()), _alarm_answer())
    assert built["ok"], built.get("errors")
    told = " ".join(sent[0][-1]["content"].split())
    days = json.dumps({"condition": "template", "value_template": ai.day_bits_template("role:days")})
    assert ('ALARM CLOCK (the user sets it on the card): it starts with {"trigger": "time", "at": "role:start_time", '
            '"id": "start"}, never by a schedule; the start option checks the days right after it, exactly so: '
            + days + '.') in told
    missing = ('The request asks "Watering starts at the time I set on the card" (time), and the logic does not do it: '
               'a schedule starts it - only the time set on the card may.')
    assert len(sent) == 2 and built["tries"] == 2 and built["repaired"] == [missing]
    back = sent[1][-1]["content"]
    assert missing in back and "How: It is an alarm clock (ALARM CLOCK in the message)" in back
    assert [i["ok"] for i in built["checklist"] if i["kind"] == "time"] == [True]
    # The time set on the card is in the logic, so it is on the card: first, before the row of days. The schedule is not.
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    assert rows[0] == {"entity": "input_datetime.garden_start", "name": "Start"}
    assert rows[1]["type"] == "custom:libi-days-row"
    assert "schedule.garden" not in built["yaml"] and "schedule.garden" not in built["card_yaml"]
    # The prompt says so too: a schedule starts the logic only without an alarm clock.
    assert "unless the message has an ALARM CLOCK" in " ".join(ai.BUILD_SYSTEM.split())


async def test_a_schedule_that_gave_way_is_never_part_of_the_logic(hass, garden, hass_ws_client):
    """[ADDED 2026-10-31, v3.75.0] A schedule that gave way to the alarm clock is not used - the user's choice - whatever
    the browser ticked: the model is not told of it, and a draft that still names it does not hold."""
    plan, selections = _alarm_plan(hass)
    hass.states.async_set("schedule.garden", "off", {"friendly_name": "Garden schedule"})
    plan["roles"].append({**copy.deepcopy(SCHEDULE_ROLE), "optional": True, "named": True, "replaced": True})
    selections["watering_schedule"] = ["schedule.garden"]  # ticked anyway - as the chat of 3.74.0 let the user
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, _by_schedule(_alarm_answer()), _alarm_answer())
    assert built["ok"], built.get("errors")
    assert "watering_schedule" not in sent[0][-1]["content"] and "schedule.garden" not in sent[0][-1]["content"]
    assert len(sent) == 2 and "The draft refers to 'watering_schedule', which has no entity picked." in built["repaired"]
    assert "schedule.garden" not in built["yaml"] and "schedule.garden" not in built["card_yaml"]


async def test_libi_checks_the_alarm_clock_also_without_a_line_for_it(hass, garden):
    """[ADDED 2026-10-31, v3.75.0] A plan whose lines say nothing of the time or the days: with an alarm clock picked, LIBI
    checks both with lines of its own - the time trigger at the time set on the card, the CMP DAY of the days helper."""
    plan, selections = _alarm_plan(hass)
    hass.states.async_set("schedule.garden", "off", {"friendly_name": "Garden schedule"})
    plan["roles"].append(copy.deepcopy(SCHEDULE_ROLE))
    selections["watering_schedule"] = ["schedule.garden"]
    plan["requirements"] = [line for line in plan["requirements"] if line["kind"] not in ("time", "days")]
    alarm = ai.picked_alarm_clock(hass, plan, selections)

    async def lines(answer, alarm=alarm):
        draft = await ai.async_build_draft(hass, plan, selections, answer)
        assert draft["ok"], draft["errors"]
        return {i["id"]: (i["ok"], i["missing"]) for i in ai.requirement_report(plan, draft, {}, answer, alarm)
                if i["id"].startswith("alarm_")}

    def changed(edit):
        answer = _alarm_answer()
        config = json.loads(answer["config"])
        edit(config)
        return {**answer, "config": json.dumps(config)}

    assert await lines(_alarm_answer()) == {"alarm_time": (True, ""), "alarm_days": (True, "")}
    assert [line["text"] for line in ai.requirement_report(plan, await ai.async_build_draft(
        hass, plan, selections, _alarm_answer()), {}, {}, alarm)][-2:] == list(ai._ALARM_LINES.values())
    assert (await lines(_by_schedule(_alarm_answer())))["alarm_time"] == (
        False, "a schedule starts it - only the time set on the card may")
    # A time of its own is not the time set on the card.
    fixed = changed(lambda c: c["triggers"][0].update({"at": "05:00:00"}))
    assert (await lines(fixed))["alarm_time"] == (False, "it does not start at the time set on the card")
    # Fixed days in place of the days helper are not the days ticked on the card.
    days = changed(lambda c: c["actions"][0]["choose"][0]["conditions"].__setitem__(
        1, {"condition": "time", "weekday": ["mon"]}))
    assert (await lines(days))["alarm_days"] == (
        False, "it does not check the days ticked on the card (CMP DAY of the days helper)")
    # No days helper picked: no alarm clock, and no line of LIBI's.
    assert ai.picked_alarm_clock(hass, plan, {**selections, "days": []}) == {}
    assert await lines(_alarm_answer(), alarm={}) == {}
    # Two times of day, neither in start_time: none is the start time, and the days are still checked.
    two = {**selections, "start_time": [], "litres": ["input_number.garden_litres"]}
    hass.states.async_set("input_datetime.garden_end", "06:00:00", {"friendly_name": "End", "has_time": True})
    plan["roles"] += [{"id": "start_at", "label": "a", "purpose": "trigger", "domains": ["input_datetime"]},
                      {"id": "end_at", "label": "b", "purpose": "condition", "domains": ["input_datetime"]}]
    two.update(start_at=["input_datetime.garden_start"], end_at=["input_datetime.garden_end"])
    assert ai.picked_alarm_clock(hass, plan, two)["time"] == ""


async def test_the_forecast_counts_only_when_a_step_checks_it_after_reading_it(hass, garden):
    """[ADDED 2026-10-31, v3.75.0] The user's NET 3 read today's forecast in its start option and checked it in a second
    option of the same trigger. A choose runs the first option that holds and never reaches the second, so it watered
    when rain was expected - and the checklist said yes, the logic reads the forecast."""
    plan, selections = _alarm_plan(hass)
    good = _alarm_answer()

    def forecast_line(answer):
        config = json.loads(answer["config"])
        return next(i for i in ai.requirement_report(plan, {"ok": True, "auto": config}, {}, answer)
                    if i["kind"] == "forecast")

    assert forecast_line(good)["ok"] is True
    config = json.loads(good["config"])
    start = config["actions"][0]["choose"][0]
    check = start["sequence"].pop(1)
    # The NET 3 way: the check in an option of its own, after the one that reads the forecast and opens the valve.
    config["actions"][0]["choose"].insert(1, {"conditions": [{"condition": "trigger", "id": "start"}, check],
                                              "sequence": [{"action": "switch.turn_on",
                                                            "target": {"entity_id": "role:garden_valve"}}]})
    split = {**good, "config": json.dumps(config)}
    line = forecast_line(split)
    assert (line["ok"], line["missing"]) == (False, ai._FORECAST_UNCHECKED)
    # Checked only after the valve is open is not checked before it.
    late = json.loads(good["config"])
    seq = late["actions"][0]["choose"][0]["sequence"]
    seq[1], seq[2] = seq[2], seq[1]
    assert forecast_line({**good, "config": json.dumps(late)})["ok"] is False
    # Read into a variable of another name, and checked by that name.
    named = json.loads(good["config"].replace("forecast['role:weather']", "today['role:weather']").replace(
        '"response_variable": "forecast"', '"response_variable": "today"'))
    assert forecast_line({**good, "config": json.dumps(named)})["ok"] is True
    assert ai._forecast_checked(json.loads(good["config"])) and not ai._forecast_checked(config)


# The user's NET 3 of 2026-10-31 as LIBI saved it: the days of an alarm clock, started by the schedule the user named. The
# time made with the days ("<name>" and "<name> - <day>") is in no rung.
SMART = "Smart garden watering"


def _net3_now():
    days = {"condition": "or", "conditions": [
        {"condition": "and", "conditions": [{"condition": "time", "weekday": [d]},
                                            {"condition": "state", "entity_id": f"input_boolean.smart_watering_{d}",
                                             "state": "on"}]}
        for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]}
    valve = {"entity_id": "switch.garden_valve"}
    return {"id": "libi_ai_1793438378596", "alias": SMART, "description": "x", "mode": "single",
            "triggers": [{"trigger": "state", "entity_id": SCHEDULE, "to": "on", "id": "start"},
                         {"trigger": "numeric_state", "entity_id": "sensor.water_meter", "above": LITRES,
                          "id": "amount_reached"},
                         {"trigger": "state", "entity_id": "switch.garden_valve", "to": "on",
                          "for": {"minutes": "{{ states('" + LIMIT + "') | int(30) }}"}, "id": "time_limit"},
                         {"trigger": "homeassistant", "event": "start", "id": "restarted"}],
            "conditions": [],
            "actions": [{"choose": [
                {"conditions": [{"condition": "trigger", "id": "start"}, days,
                                {"condition": "template", "value_template": "{{ states('weather.home') not in " + _RAIN + " }}"}],
                 "sequence": [{"action": "weather.get_forecasts", "target": {"entity_id": "weather.home"},
                               "data": {"type": "daily"}, "response_variable": "forecast"},
                              {"action": "switch.turn_on", "target": valve}]},
                # Today's forecast checked in a second rung of the same trigger, which Home Assistant never reaches
                # once the first one runs.
                {"conditions": [{"condition": "trigger", "id": "start"},
                                {"condition": "template", "value_template":
                                    "{{ forecast['weather.home'].forecast[0].condition not in " + _RAIN + " }}"}],
                 "sequence": [{"action": "switch.turn_on", "target": valve}]},
                {"conditions": [{"condition": "trigger", "id": "amount_reached"}],
                 "sequence": [{"action": "switch.turn_off", "target": valve}]},
                {"conditions": [{"condition": "trigger", "id": "time_limit"}],
                 "sequence": [{"action": "switch.turn_off", "target": valve},
                              {"action": "notify.notify", "data": {"message": "The time limit ended the watering."}}]},
                {"conditions": [{"condition": "trigger", "id": "restarted"},
                                {"condition": "state", "entity_id": "switch.garden_valve", "state": "on"}],
                 "sequence": [{"action": "switch.turn_off", "target": valve}]}]}]}


async def test_a_change_of_the_net_keeps_its_alarm_clock_and_its_settings(hass, garden, hass_ws_client, config_dir):
    """[ADDED 2026-10-31, v3.75.0] "Update NET 3" of the user's NET 3. The net's own helpers are used - by the net itself -
    so the chat hid them as used by another automation and proposed new ones; every day's role got all seven day
    switches, and the role of the most minutes the litres as well. A change keeps the net's alarm clock - each day's
    switch in its day's role, the time made with them in start_time - and ticks the settings that fit, whatever the
    model planned for them; the schedule that gave way is not ticked. Built, the time set on the card starts it.
    [CHANGED 2026-11-10, v3.95.0] The user's choice: a switch for each day is one of the two ways to set the days, so a net
    with them keeps them - each in its day's role, ticked - and nothing is proposed in their place (from v3.76.0 to v3.94
    one days helper was); a net of the days helper keeps it, ticked."""
    _user_helpers(hass)
    hass.states.async_set("input_datetime.smart_watering", "00:00:00", {"friendly_name": SMART, "has_time": True,
                                                                        "has_date": False})
    for d in DAYS:
        hass.states.async_set(f"input_boolean.smart_watering_{d}", "off", {"friendly_name": f"{SMART} - {d.title()}"})
    now = _net3_now()
    # In automations.yaml, so its helpers are used: by the net that is changed.
    (config_dir / "automations.yaml").write_text(yaml.dump([now], allow_unicode=True, sort_keys=False), encoding="utf-8")
    other = yaml_to_ast(hass, copy.deepcopy(GARDEN_NOW))
    other["id"] = "n2"
    net3 = yaml_to_ast(hass, copy.deepcopy(now))
    net3["id"] = "n4"
    nets = [garden, other, net3]
    words = "update NET 3:\n" + "\n".join(USER_REQUEST.split("\n")[:2]) + "\n- a card with the settings"

    def role(rid, domains, keywords, purpose="condition"):
        return {"id": rid, "label": rid, "purpose": purpose, "domains": domains, "device_classes": [],
                "keywords": keywords, "area_keywords": []}
    base = {"reply": "I will change NET 3.", "intent": "modify", "target_net": "n4", "level": "automation", "name": SMART,
            "roles": copy.deepcopy(GARDEN_PLAN["roles"]) + [role("litres", ["input_number"], ["litres", HE["litres"]]),
                                                            role("max_minutes", ["input_number"], ["minutes", HE["minutes"]])],
            "questions": [], "new_helpers": [], "requirements": copy.deepcopy(ALARM_LINES)}
    client = await hass_ws_client(hass)

    async def plan_for(plan, on_page=None):
        with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(plan)):
            await client.send_json_auto_id({"type": "libi/ai_plan", "nets": on_page or nets, "share": True,
                                            "messages": [{"role": "user", "content": words}]})
            return (await client.receive_json())["result"]
    clock = {"start_time": ["input_datetime.smart_watering"]}
    switches = {f"day_{d}": [f"input_boolean.smart_watering_{d}"] for d in DAYS}

    def proposed(res):
        return [(h["role"], h["domain"], h["name"], h["settings"]) for h in res["plan"]["new_helpers"]]

    # The model planned no alarm clock, as Gemini did for the user.
    res = await plan_for(base)
    assert res["plan"]["intent"] == "modify" and res["plan"]["target_net"] == "n4"
    # Each day's switch stays, ticked in its day's role; nothing is proposed in their place, and nothing is asked.
    assert proposed(res) == []
    pre = res["preselect"]
    assert {rid: pre.get(rid) for rid in clock} == clock and "days" not in pre
    assert {rid: pre.get(rid) for rid in switches} == switches
    assert ai.DAYS_QUESTION not in [q["id"] for q in res["plan"]["questions"]]
    assert pre["max_minutes"] == [LIMIT] and pre["litres"] == [LITRES]
    assert (pre["garden_valve"], pre["water_meter"], pre["weather"]) == (
        ["switch.garden_valve"], ["sensor.water_meter"], ["weather.home"])
    assert SCHEDULE not in [e for ids in pre.values() for e in ids]
    assert next(r for r in res["plan"]["roles"] if r["domains"] == ["schedule"])["replaced"] is True
    # Offered first and marked current - not hidden as used by another automation: the net itself uses them.
    for rid, ids in {**clock, "max_minutes": [LIMIT]}.items():
        cand = res["candidates"][rid]
        assert cand["items"][0]["entity_id"] == ids[0] and cand["items"][0]["current"] is True and cand["exact"] is True
    # Nothing the net uses is left out as used by another automation: the litres in the list of the minutes neither.
    hidden = {rid: cand["hidden_used"] for rid, cand in res["candidates"].items() if cand.get("hidden_used")}
    assert hidden == {}, hidden

    # The model proposed the alarm clock again, and the most minutes: the net's own fill them, nothing is created twice.
    again = [{"role": "start_time", "domain": "input_datetime", "name": SMART,
              "settings": {"has_time": True, "has_date": False}}] + [
        {"role": f"day_{d}", "domain": "input_boolean", "name": f"{SMART} - {d.title()}", "settings": {}} for d in DAYS] + [
        {"role": "max_minutes", "domain": "input_number", "name": "Most minutes", "settings": {"min": 1, "max": 120}}]
    res = await plan_for({**base, "new_helpers": again})
    assert proposed(res) == [] and {rid: res["preselect"].get(rid) for rid in clock} == clock
    assert {rid: res["preselect"].get(rid) for rid in switches} == switches
    assert res["preselect"]["max_minutes"] == [LIMIT]

    # Under names of its own: the days by their full names, the time as a trigger's helper of its own.
    full = {"sun": "sunday", "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
            "fri": "friday", "sat": "saturday"}
    own = [{"role": "watering_time", "domain": "input_datetime", "name": "Watering time", "settings": {"has_time": True}}] + [
        {"role": full[d], "domain": "input_boolean", "name": f"Water on {full[d]}", "settings": {}} for d in DAYS]
    res = await plan_for({**base, "roles": base["roles"] + [role("watering_time", ["input_datetime"], [], "trigger")],
                          "new_helpers": own})
    ids = {r["id"] for r in res["plan"]["roles"]}
    assert proposed(res) == [] and "watering_time" not in ids
    assert not ids & set(full.values()) and ids >= set(switches)
    assert res["preselect"]["start_time"] == clock["start_time"]

    # A start time role of the model's own, under a label no helper has: the net's time fills it, no new one is made.
    res = await plan_for({**base, "roles": base["roles"] + [role("start_time", ["input_datetime"], ["start"], "trigger")]})
    assert proposed(res) == [] and res["preselect"]["start_time"] == clock["start_time"]
    assert res["candidates"]["start_time"]["exact"] is True

    # No card asked for: the schedule the message names still gives way - the net has the alarm clock already.
    res = await plan_for({**base, "requirements": [line for line in ALARM_LINES if line["kind"] != "card"]})
    assert next(r for r in res["plan"]["roles"] if r["domains"] == ["schedule"])["replaced"] is True
    assert SCHEDULE not in [e for ids in res["preselect"].values() for e in ids]

    # Built from the first plan: the same automation, started at the time set on the card and run on the days switched
    # on - each day's switch checked on its own day - both on the card, the days as one row of Home Assistant's buttons.
    res = await plan_for(base)
    built, sent = await _build(client, res["plan"], res["preselect"], _alarm_answer(days="switches"), nets=nets, words=words)
    assert built["ok"], built.get("errors")
    assert "CURRENT NET" in sent[0][-1]["content"] and len(sent) == 1
    told = " ".join(sent[0][-1]["content"].split())
    assert json.dumps(ai.days_switches_condition({d: f"role:day_{d}" for d in DAYS})) in told
    assert built["intent"] == "modify" and built["net"]["ha_id"] == "libi_ai_1793438378596"
    doc = yaml.safe_load(built["yaml"])
    assert doc["triggers"][0] == {"trigger": "time", "at": "input_datetime.smart_watering", "id": "start"}
    assert ai.days_switches_condition({d: f"input_boolean.smart_watering_{d}" for d in DAYS}) in \
        doc["actions"][0]["choose"][0]["conditions"]
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    # [CHANGED 2026-11-01, v3.79.0] Named after the net, the time and the days say their part only.
    assert rows[0] == {"entity": "input_datetime.smart_watering", "name": "Start time"}
    assert rows[1]["type"] == "buttons" and [b["entity"] for b in rows[1]["entities"]] == [
        f"input_boolean.smart_watering_{d}" for d in DAYS]
    assert [b["name"] for b in rows[1]["entities"]] == [d.title() for d in DAYS]
    assert "custom:" not in built["card_yaml"]
    assert SCHEDULE not in built["yaml"] and SCHEDULE not in built["card_yaml"]
    assert all(i["ok"] is not False for i in built["checklist"]) and built["round_trip"]["ok"]

    # A NET of the days helper (made by 3.76.0 - 3.94): a change keeps it, ticked in its role, and proposes nothing.
    hass.states.async_set("input_number.smart_watering_days", "0", {"friendly_name": f"{SMART} - days", "min": 0,
                                                                     "max": 255, "step": 1})

    def to_bits(node):
        if isinstance(node, dict):
            if node.get("condition") == "or" and ai.config_days(node):
                return {"condition": "template",
                        "value_template": ai.day_bits_template("input_number.smart_watering_days")}
            return {k: to_bits(v) for k, v in node.items()}
        return [to_bits(v) for v in node] if isinstance(node, list) else node
    bits_net = yaml_to_ast(hass, to_bits(_net3_now()))
    bits_net["id"] = "n4"
    res = await plan_for(base, [garden, other, bits_net])
    assert res["plan"]["new_helpers"] == []
    assert (res["preselect"]["start_time"], res["preselect"]["days"]) == (
        ["input_datetime.smart_watering"], ["input_number.smart_watering_days"])
    assert ai.DAYS_QUESTION not in [q["id"] for q in res["plan"]["questions"]]


def test_two_rungs_of_one_trigger_are_found():
    """[ADDED 2026-10-31, v3.75.0] The user: "the ladder is not written right - this is not a PLC, it is driven by
    triggers". Their NET 3 had two rungs of the trigger start: the ladder draws both, and Home Assistant runs only the
    first that holds. LIBI finds them, also in an option of a list of ids and in conditions written as one dict."""
    assert ai.shared_options(_net3_now()["actions"]) == [("start", [1, 2])]
    assert ai.shared_options(json.loads(_alarm_answer()["config"])["actions"]) == []
    many = {"choose": [{"conditions": [{"condition": "trigger", "id": ["a", "b"]}]},
                       {"conditions": {"condition": "trigger", "id": "b"}},
                       {"conditions": [{"condition": "trigger", "id": "c"}]},
                       {"conditions": [{"condition": "trigger", "id": "b"}, {"condition": "state"}]}]}
    assert ai.shared_options([many]) == [("b", [1, 2, 4])]
    assert ai.shared_options("x") == [] and ai.shared_options([{"choose": "x"}, "y"]) == []


async def test_a_draft_with_two_rungs_of_one_trigger_goes_back_and_is_not_saved_on_its_own(hass, garden, hass_ws_client):
    """[ADDED 2026-10-31, v3.75.0] The draft that became the user's NET 3: today's forecast read in the start option and
    checked in a second option of the same trigger. It goes back with why; a model that keeps it gets a draft that
    says so and that the chat does not save on its own."""
    plan, selections = _alarm_plan(hass)
    two = _alarm_answer()
    config = json.loads(two["config"])
    check = config["actions"][0]["choose"][0]["sequence"].pop(1)
    config["actions"][0]["choose"].insert(1, {"conditions": [{"condition": "trigger", "id": "start"}, check], "sequence": [
        {"action": "switch.turn_on", "target": {"entity_id": "role:garden_valve"}}]})
    two["config"] = json.dumps(config)
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, two, _alarm_answer())
    assert built["ok"] and len(sent) == 2 and built["shared_rungs"] == []
    problem = ("LIBI's ladder draws every option of the choose as a rung of its own, but Home Assistant runs only the "
               'first option that holds: options 1 and 2 start with trigger id "start", so a later one runs only when '
               "the ones before it do not.")
    assert problem in built["repaired"] and "How: One option per trigger id" in sent[1][-1]["content"]
    built, sent = await _build(client, plan, selections, two)
    assert built["ok"] and len(sent) == 3 and built["shared_rungs"] == ["start"]
    assert any(note.startswith("Two rungs start with the same trigger (start): Home Assistant runs only the first")
               for note in built["notes"])
    assert "never two options for one trigger id" in " ".join(ai.BUILD_SYSTEM.split())


def test_day_roles_by_any_name_become_the_days_helper():
    """[CHANGED 2026-10-31, v3.76.0] The roles the model plans for the days, under any of their names (day_mon, monday),
    become the one days helper; the role of a day's switch the user named stays - it is the user's own. The alarm
    clock proposed in place of a schedule leaves them to that, so the days helper stands where they stood."""
    full = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    roles = [{"id": rid, "label": rid, "purpose": "condition", "domains": ["input_boolean"]} for rid in full]
    plan = {"intent": "create", "name": "W", "new_helpers": [], "roles": copy.deepcopy(roles) + [
        {"id": "sunday", "label": "sunday", "purpose": "condition", "domains": ["input_boolean"], "named": True}]}
    ai._days_as_bits(plan)
    assert [(h["role"], h["name"]) for h in plan["new_helpers"]] == [("days", "W - days")]
    assert [r["id"] for r in plan["roles"]] == ["sunday", "days"]
    plan = {"intent": "create", "name": "W", "new_helpers": [], "roles": copy.deepcopy(roles) + [
        {"id": "start_time", "label": "t", "purpose": "trigger", "domains": ["input_datetime"]},
        {"id": "when", "label": "w", "purpose": "trigger", "domains": ["schedule"]}]}
    named = {"when": ["schedule.garden"]}
    ai._alarm_clock_for(plan, named, [("when", "schedule.garden")])
    assert plan["new_helpers"] == [] and named == {}
    ai._days_as_bits(plan)
    assert [h["role"] for h in plan["new_helpers"]] == ["days"] and not any(ai._is_day_role(r) for r in plan["roles"])
    # A role named for a day that holds no switch (the sun of a garden) is not that day's switch.
    assert not ai._is_day_role({"id": "garden_sun", "domains": ["sun"]}) and ai._is_day_role({"id": "sunday",
                                                                                              "domains": ["input_boolean"]})


async def test_a_change_ticks_a_setting_only_where_it_is_the_one(hass, home):
    """[ADDED 2026-10-31, v3.75.0] preselect: nothing goes into a day's role or the days helper's (keep_net_alarm_clock
    fills that), a setting is ticked only when it is the one left that fits, what is taken already is left out, and the
    schedule of a net with an alarm clock is not ticked again. [CHANGED v3.76.0] Nor the switches of the days."""
    for d in ("mon", "tue"):
        hass.states.async_set(f"input_boolean.w_{d}", "off", {"friendly_name": f"W - {d.title()}"})
    hass.states.async_set("input_boolean.enabled", "on", {"friendly_name": "Enabled"})
    for eid in ("input_number.litres", "input_number.minutes"):
        hass.states.async_set(eid, "1", {"friendly_name": eid})
    hass.states.async_set("schedule.garden", "off", {"friendly_name": "Garden schedule"})
    days = [{"condition": "and", "conditions": [{"condition": "time", "weekday": d},
                                                {"condition": "state", "entity_id": f"input_boolean.w_{d}", "state": "on"}]}
            for d in ("mon", "tue")]
    net = yaml.dump({"triggers": [{"trigger": "state", "entity_id": "schedule.garden", "to": "on"}],
                     "conditions": [{"condition": "or", "conditions": days},
                                    {"condition": "state", "entity_id": "input_boolean.enabled", "state": "on"},
                                    {"condition": "numeric_state", "entity_id": "input_number.litres", "above": 0},
                                    {"condition": "numeric_state", "entity_id": "input_number.minutes", "above": 0}],
                     "actions": [{"action": "light.turn_on", "target": {"entity_id": ["light.kitchen", "light.salon_lamp"]}}]})
    roles = [{"id": "day_mon", "domains": ["input_boolean"]}, {"id": "enabled", "domains": ["input_boolean"]},
             {"id": "minutes", "domains": ["input_number"]}, {"id": "when", "domains": ["schedule"]},
             {"id": "lights", "domains": ["light"]}]
    taken = {"input_boolean.w_mon", "input_boolean.w_tue"}
    assert ai.preselect(hass, {"roles": roles}, net, taken) == {
        "enabled": ["input_boolean.enabled"], "lights": ["light.kitchen", "light.salon_lamp"]}
    assert ai.preselect(hass, {"roles": roles}, net, taken | {"input_number.litres"})["minutes"] == ["input_number.minutes"]
    # [CHANGED 2026-10-31, v3.76.0] The switches of the days are never a pick - the days are one helper now - so "enabled"
    # is the one that fits even when they were not taken.
    assert ai.preselect(hass, {"roles": roles}, net)["enabled"] == ["input_boolean.enabled"]
    # One setting that fits two roles is the user's to place; a role filled already is left as it is.
    two = roles + [{"id": "litres", "domains": ["input_number"]}]
    assert "minutes" not in ai.preselect(hass, {"roles": two}, net, taken | {"input_number.litres"})
    assert ai.preselect(hass, {"roles": two}, net, taken | {"input_number.litres"}, {"litres"})["minutes"] == [
        "input_number.minutes"]
    assert "enabled" not in ai.preselect(hass, {"roles": roles}, net, taken, {"enabled"})
    assert ai.net_alarm_clock(hass, yaml.safe_load(net)) == {"time": "", "days": "", "base": "W", "switches": {
        "mon": "input_boolean.w_mon", "tue": "input_boolean.w_tue"}, "schedule": ""}


# ---------------------------------------------------------------- LIBI's own questions (v3.80.0)
# [ADDED 2026-11-01, v3.80.0] The user, of a watering the chat built without asking: "things I would expect it to ask me
# - whether to add an enable button for the whole automation, what to do when the valve's battery runs out and it is
# offline, and a message when the battery is almost empty". The valve is the user's: a Zigbee valve on a battery, its
# litres meter and its battery on the same device (switch.valve_garden_switch, sensor.valve_garden_battery).
VALVE = "switch.valve_garden_switch"
METER = "sensor.valve_garden_summation_delivered"
BATTERY = "sensor.valve_garden_battery"
SWITCH = "input_boolean.garden_watering_enabled"


def _valve_device(hass, battery="87"):
    owner = MockConfigEntry(domain="test")
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=owner.entry_id, identifiers={("test", "valve_garden")},
                                                    name="valve_garden")
    reg = er.async_get(hass)
    for domain, uid, oid, state, attrs in (
            ("switch", "valve", "valve_garden_switch", "off", {"friendly_name": "valve_garden Switch"}),
            ("sensor", "meter", "valve_garden_summation_delivered", "120",
             {"friendly_name": "valve_garden Summation delivered", "device_class": "volume", "unit_of_measurement": "L"}),
            ("sensor", "battery", "valve_garden_battery", battery,
             {"friendly_name": "valve_garden Battery", "device_class": "battery", "unit_of_measurement": "%"}),
            ("sensor", "lqi", "valve_garden_lqi", "80", {"friendly_name": "valve_garden LQI"})):
        entry = reg.async_get_or_create(domain, "test", uid, suggested_object_id=oid, device_id=device.id,
                                        config_entry=owner)
        assert entry.entity_id == f"{domain}.{oid}"
        hass.states.async_set(entry.entity_id, state, attrs)
    return owner, device


SAFE_PLAN = {
    "reply": "Pick the valve and the meter.", "intent": "create", "target_net": "", "level": "automation",
    "name": "Garden watering",
    "roles": [{"id": "garden_valve", "label": "Garden valve", "purpose": "target", "domains": ["switch"],
               "device_classes": [], "keywords": ["valve", "garden"], "area_keywords": []},
              {"id": "water_meter", "label": "Water meter", "purpose": "measure", "domains": ["sensor"],
               "device_classes": ["volume"], "keywords": ["garden", "summation"], "area_keywords": []}],
    # The model asks one of its own, words one under LIBI's id, and plans a switch of its own: LIBI asks for that.
    "questions": [{"id": "duration", "text": "How long?", "choices": ["10 minutes"]},
                  {"id": "libi_battery", "text": "The model's battery question", "choices": ["Sure"]}],
    "new_helpers": [{"role": "enabled", "domain": "input_boolean", "name": "The model's switch", "settings": {}}],
    "requirements": [],
}


async def _safe_plan(hass, hass_ws_client, plan=None, nets=None, content="water the garden with the valve"):
    client = await hass_ws_client(hass)
    with patch.object(ai, "async_llm_json", return_value=copy.deepcopy(plan or SAFE_PLAN)):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": nets or [], "share": True,
                                        "messages": [{"role": "user", "content": content}]})
        return (await client.receive_json())["result"]


async def test_libi_asks_its_own_questions_for_an_automation_that_switches_a_device(hass, libi_ai, hass_ws_client):
    # The user's house: the valve is the only one, with its two switches on one device.
    hass.states.async_remove("switch.garden_valve")
    owner, device = _valve_device(hass)
    second =er.async_get(hass).async_get_or_create("switch", "test", "valve2", suggested_object_id="valve_garden_switch_2",
                                                    device_id=device.id, config_entry=owner)
    hass.states.async_set(second.entity_id, "unavailable", {"friendly_name": "valve_garden"})
    res = await _safe_plan(hass, hass_ws_client)
    plan = res["plan"]
    # [CHANGED 2026-11-02, v3.81.0] With a message when it starts and when it ends - the user: "always ask".
    assert [q["id"] for q in plan["questions"]] == ["duration", "libi_enable", "libi_start_message", "libi_end_message", "libi_offline", "libi_battery"]
    asked = {q["id"]: q for q in plan["questions"]}
    assert "libi" not in asked["duration"] and all(asked[q]["libi"] is True for q in ai.SAFETY_QUESTIONS)
    # In LIBI's own words, with LIBI's own choices - the model's question under LIBI's id is gone.
    assert asked["libi_battery"]["text"] == "A message when a battery is low? Now: valve_garden 87%."
    assert asked["libi_battery"]["choices"] == ["Yes, below 20%", "Yes, below 10%", "No"]
    assert asked["libi_offline"]["text"] == ("What if valve_garden is offline (unavailable) - its battery ran out, "
                                             "for example?")
    assert asked["libi_offline"]["choices"] == ["Tell me, and do not start", "Do not start, no message", "Nothing"]
    assert "with ZHA 6 hours by default" in asked["libi_offline"]["note"]
    assert "skips a device that is offline" in asked["libi_offline"]["note"]
    enable = asked["libi_enable"]
    assert enable["text"] == "An on/off switch for the whole automation, on the card?"
    assert enable["choices"] == ["Yes", "No"] and enable["yes"] == ["Yes"]
    assert "Off stops it at once" in enable["note"] and "A new switch starts off" in enable["note"]
    # A yes adds a role and a helper named after the logic; until then the plan has neither - nor the model's switch.
    assert enable["adds"]["role"]["id"] == "enabled" and enable["adds"]["role"]["domains"] == ["input_boolean"]
    assert enable["adds"]["role"]["optional"] is False
    assert enable["adds"]["helper"] == {"role": "enabled", "domain": "input_boolean", "name": "Garden watering - enabled",
                                        "settings": {"icon": "mdi:power"}}
    assert "enabled" not in [r["id"] for r in plan["roles"]] and plan["new_helpers"] == []
    assert "enabled" not in res["candidates"]
    # The cleaning keeps six of the model's questions, and LIBI's, which come back from the browser after them.
    again = ai.clean_plan(hass, copy.deepcopy(plan))
    assert [q["id"] for q in again["questions"]] == ["duration", "libi_enable", "libi_start_message", "libi_end_message", "libi_offline", "libi_battery"]
    # [ADDED 2026-11-02, v3.81.0] The messages, with LIBI's choices; no phone with the app is set up in this house.
    assert asked["libi_start_message"]["text"] == "A message when it starts - when it turns valve_garden on?"
    assert asked["libi_end_message"]["text"] == ("A message when it ends - when valve_garden turns off, whatever turned it "
                                                 "off?")
    assert asked["libi_start_message"]["choices"] == ["A notification", "Spoken", "Notification and spoken", "No"]
    assert asked["libi_end_message"]["choices"] == asked["libi_start_message"]["choices"]
    assert asked["libi_end_message"]["note"].startswith("No phone with the Home Assistant app is set up here")
    assert ai.PHONES_ROLE not in [r["id"] for r in plan["roles"]]
    many = {"intent": "create", "questions": [{"id": f"q{i}", "text": "x", "choices": []} for i in range(8)]
            + [{"id": qid, "text": "x", "choices": []} for qid in ai.SAFETY_QUESTIONS]}
    assert [q["id"] for q in ai.clean_plan(hass, many)["questions"]] == [f"q{i}" for i in range(6)] + list(ai.SAFETY_QUESTIONS)


async def test_an_existing_switch_of_that_name_is_offered_instead_of_a_new_one(hass, libi_ai, hass_ws_client):
    _valve_device(hass)
    hass.states.async_set(SWITCH, "off", {"friendly_name": "Garden watering - enabled"})
    enable = next(q for q in (await _safe_plan(hass, hass_ws_client))["plan"]["questions"] if q["id"] == "libi_enable")
    # [CHANGED 2026-11-02, v3.82.0] The free switch is the one it starts with, and a new one stays in reach, under a name of
    # its own - the user: "if a variable is free, choose it instead of creating a new one", "always the option to create".
    assert enable["adds"]["helper"]["pick"] == SWITCH and enable["adds"]["helper"]["name"] == "Garden watering - enabled (2)"
    assert enable["adds"]["role"]["variable"] is True
    first = enable["adds"]["candidates"]["items"][0]
    assert first["entity_id"] == SWITCH and first["exists"] is True and enable["adds"]["candidates"]["exact"] is True
    # A free switch LIBI made for another automation fits as well; one in use is never offered.
    hass.states.async_remove(SWITCH)
    hass.states.async_set("input_boolean.old_watering_enabled", "off", {"friendly_name": "Old watering - enabled"})
    hass.states.async_set("input_boolean.guest_mode", "off", {"friendly_name": "Guest mode"})
    enable = next(q for q in (await _safe_plan(hass, hass_ws_client))["plan"]["questions"] if q["id"] == "libi_enable")
    assert enable["adds"]["helper"]["pick"] == "input_boolean.old_watering_enabled"
    assert enable["adds"]["helper"]["name"] == "Garden watering - enabled"


async def test_libi_asks_nothing_where_nothing_is_switched_and_asks_for_a_battery_only_where_there_is_one(
        hass, libi_ai, hass_ws_client):
    _valve_device(hass)
    script = await _safe_plan(hass, hass_ws_client, {**SAFE_PLAN, "level": "script"})
    assert [q["id"] for q in script["plan"]["questions"]] == ["duration"]
    nothing = await _safe_plan(hass, hass_ws_client, {**SAFE_PLAN, "roles": SAFE_PLAN["roles"][1:]})
    assert [q["id"] for q in nothing["plan"]["questions"]] == ["duration"]
    # A light on the mains: no battery to ask about, and offline is no power or no network.
    hass.states.async_set("light.kitchen_ceiling", "off", {"friendly_name": "Kitchen ceiling"})
    lights = {**SAFE_PLAN, "roles": [{"id": "kitchen_light", "label": "Kitchen light", "purpose": "target",
                                      "domains": ["light"], "device_classes": [], "keywords": ["kitchen"],
                                      "area_keywords": []}]}
    res = await _safe_plan(hass, hass_ws_client, lights)
    asked = {q["id"]: q for q in res["plan"]["questions"]}
    assert list(asked) == ["duration", "libi_enable", "libi_start_message", "libi_end_message", "libi_offline"]
    assert asked["libi_end_message"]["text"] == "A message when it ends - when Kitchen light turns off, whatever turned it off?"
    # Two lights match, the user has not picked yet: the question names the role, not a light they may not pick.
    assert asked["libi_offline"]["text"] == ("What if Kitchen light is offline (unavailable) - no power or no network, "
                                             "for example?")
    assert "ZHA" not in asked["libi_offline"]["note"]
    two = {**lights, "roles": lights["roles"] + [{**SAFE_PLAN["roles"][0], "keywords": ["garden switch"]}]}
    texts = {q["id"]: q["text"] for q in (await _safe_plan(hass, hass_ws_client, two))["plan"]["questions"]}
    assert texts["libi_offline"] == ("What if Kitchen light and valve_garden are offline (unavailable) - its battery ran "
                                     "out, for example?")
    # The model planned the battery itself: the user asked for it, so LIBI does not ask again.
    own = {**SAFE_PLAN, "roles": SAFE_PLAN["roles"] + [{"id": "valve_battery", "label": "Battery", "purpose": "measure",
                                                        "domains": ["sensor"], "device_classes": ["battery"],
                                                        "keywords": ["battery"], "area_keywords": []}]}
    assert "libi_battery" not in [q["id"] for q in (await _safe_plan(hass, hass_ws_client, own))["plan"]["questions"]]


async def test_the_batteries_are_the_devices_own(hass, libi_ai):
    """[RULE 8] Found in the registries: the battery of the device of the entity, in %, not disabled - never a phone's."""
    owner, device = _valve_device(hass)
    reg = er.async_get(hass)
    off = reg.async_get_or_create("sensor", "test", "battery_old", suggested_object_id="valve_garden_battery_old",
                                  device_id=device.id, config_entry=owner, disabled_by=er.RegistryEntryDisabler.USER)
    hass.states.async_set(off.entity_id, "50", {"device_class": "battery", "unit_of_measurement": "%"})
    state = reg.async_get_or_create("sensor", "test", "battery_state", suggested_object_id="valve_garden_battery_state",
                                    device_id=device.id, config_entry=owner)
    hass.states.async_set(state.entity_id, "charging", {"device_class": "battery"})
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dr.async_get(hass).async_get_or_create(config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")})
    for oid in ("phone_battery_level", "phone_presence"):
        entry = reg.async_get_or_create("sensor", "mobile_app", oid, suggested_object_id=oid, device_id=phone.id,
                                        config_entry=phone_entry)
        hass.states.async_set(entry.entity_id, "40", {"device_class": "battery", "unit_of_measurement": "%"})
    assert ai.battery_sensors(hass, [VALVE, METER, "light.nothing"]) == [BATTERY]
    assert ai.battery_sensors(hass, ["sensor.phone_presence"]) == []
    assert ai._device_names(hass, [VALVE, METER, "light.kitchen"]) == ["valve_garden", "Kitchen"]
    assert [ai._join(n) for n in (["A"], ["A", "B"], ["A", "B", "C"], ["A", "B", "C", "D", "E"], [])] == [
        "A", "A and B", "A, B and C", "A, B, C and 2 more", ""]
    assert ai._level(hass, BATTERY) == "87%" and ai._level(hass, "sensor.nothing") == "?"


def _safe_answer(**without):
    """The watering as the build is told to write the user's answers: the switch checked by the start and turning it
    off a rung of its own, the valve's being online checked by the start and its going offline a rung of its own, and a
    rung for a low battery. without: a part left out or written wrong, as a model might."""
    valve = {"entity_id": "role:garden_valve"}
    start_checks = [{"condition": "trigger", "id": "start"},
                    {"condition": "state", "entity_id": "role:enabled", "state": "on"},
                    {"condition": "not", "conditions": [{"condition": "state", "entity_id": "role:garden_valve",
                                                         "state": "unavailable"}]}]
    if without.get("online"):
        start_checks.pop(2)
    if without.get("gate") or without.get("top"):
        start_checks.pop(1)
    triggers = [{"trigger": "time", "at": "05:00:00", "id": "start"},
                {"trigger": "numeric_state", "entity_id": "role:water_meter", "above": 200, "id": "amount_reached"},
                {"trigger": "state", "entity_id": "role:enabled", "to": "off", "id": "switched_off"},
                {"trigger": "state", "entity_id": "role:garden_valve", "to": "unavailable", "for": {"minutes": 10},
                 "id": "garden_valve_offline"},
                {"trigger": "numeric_state", "entity_id": "role:batteries", "below": without.get("below", 20),
                 "id": "battery_low"}]
    amount = [{"condition": "trigger", "id": "amount_reached"}]
    if without.get("blocks"):
        amount.append({"condition": "state", "entity_id": "role:enabled", "state": "on"})
    options = [
        {"conditions": start_checks, "sequence": [{"action": "switch.turn_on", "target": valve}]},
        {"conditions": amount, "sequence": [{"action": "switch.turn_off", "target": valve}]},
        {"conditions": [{"condition": "trigger", "id": "switched_off"}],
         "sequence": [{"action": "switch.turn_off", "target": valve}]},
        {"conditions": [{"condition": "trigger", "id": "garden_valve_offline"}],
         "sequence": [{"action": "notify.notify",
                       "data": {"message": "The garden valve is offline - its battery may be empty."}}]},
        {"conditions": [{"condition": "trigger", "id": "battery_low"}],
         "sequence": [{"action": "notify.notify",
                       "data": {"message": "{{ trigger.to_state.name }}: {{ trigger.to_state.state }}%"}}]}]
    if without.get("stop"):
        triggers.pop(2)
        options.pop(2)
    config = {"mode": "single", "triggers": triggers, "conditions": [], "actions": [{"choose": options}]}
    if without.get("top"):
        config["conditions"] = [{"condition": "state", "entity_id": "role:enabled", "state": "on"}]
    return {"reply": "Built.", "level": "automation", "name": "Garden watering", "description": "x",
            "config": json.dumps(config), "ui_card": "", "notes": [], "covers": []}


YES_TO_ALL = {"duration": "10 minutes", "libi_enable": "Yes", "libi_offline": "Tell me, and do not start",
              "libi_battery": "Yes, below 20%"}


async def _yes_plan(hass, hass_ws_client):
    """The plan of the chat after the user said yes to the switch: its role is in the plan, and its helper was made."""
    _valve_device(hass)
    hass.states.async_set(SWITCH, "on", {"friendly_name": "Garden watering - enabled"})
    planned = await _safe_plan(hass, hass_ws_client)
    plan = planned["plan"]
    enable = next(q for q in plan["questions"] if q["id"] == "libi_enable")
    plan["roles"].append(enable["adds"]["role"])
    return plan, {"garden_valve": [VALVE], "water_meter": [METER], "enabled": [SWITCH]}


async def test_the_answers_are_written_exactly_so_and_checked(hass, libi_ai, hass_ws_client):
    plan, selections = await _yes_plan(hass, hass_ws_client)
    # Another battery in the house, on a device the logic does not use: the model is never told of it.
    hass.states.async_set("sensor.door_sensor_battery", "64", {"friendly_name": "Door sensor Battery",
                                                               "device_class": "battery", "unit_of_measurement": "%"})
    client = await hass_ws_client(hass)
    llm, sent = _model(_safe_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "share": True, "plan": plan,
                                        "selections": selections, "answers": YES_TO_ALL,
                                        "messages": [{"role": "user", "content": "water the garden with the valve"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    told = sent[0][-1]["content"]
    # The model is told what each answer means, written exactly so - and not LIBI's questions as answers.
    assert "ANSWERS:\n- How long? -> 10 minutes\n" in told and "An on/off switch" not in told
    assert ('the start option checks it right after its trigger, exactly so: {"condition": "state", "entity_id": '
            '"role:enabled", "state": "on"}') in told
    assert '{"trigger": "state", "entity_id": "role:enabled", "to": "off", "id": "switched_off"}' in told
    assert ('{"condition": "not", "conditions": [{"condition": "state", "entity_id": "role:garden_valve", "state": '
            '"unavailable"}]}') in told
    assert ('{"trigger": "state", "entity_id": "role:garden_valve", "to": "unavailable", "for": {"minutes": 10}, '
            '"id": "garden_valve_offline"}') in told
    assert '{"trigger": "numeric_state", "entity_id": "role:batteries", "below": 20, "id": "battery_low"}' in told
    assert "with persistent_notification.create" in told
    # The battery is a role LIBI filled from the registry, and the model hears of it alone - not of every battery.
    assert "- role:batteries (measure) = 1 entity(ies) of domain sensor: valve_garden Battery" in told
    assert f" * {BATTERY} " in told and told.count("[battery]") == 1 and "sensor.door_sensor_battery" not in told
    # LIBI checked every answer in the logic, each with its rung.
    mine = {i["id"]: (i["ok"], i["rung"], i["kind"]) for i in built["checklist"]}
    assert mine == {"libi_enable": (True, 3, "enable"), "libi_online": (True, 1, "offline"),
                    "libi_offline": (True, 4, "offline"), "libi_battery": (True, 5, "battery")}
    assert built["round_trip"]["ok"], built["round_trip"]
    # Drawn with the palette's blocks: | | of the switch and CMP <> unavailable in the start, a CMP = unavailable with
    # its TON, | / | of the switch going off, CMP < 20 of the battery.
    rungs = built["net"]["rungs"]
    start = [(e["type"], e.get("label") or e.get("sourceA"), e.get("sourceB")) for e in rungs[0]["elements"]]
    assert ("contact_no", SWITCH, None) in start and ("cmp_ne", VALVE, "unavailable") in start, start
    offline = rungs[3]["elements"]
    assert (offline[0]["type"], offline[0]["sourceA"], offline[0]["sourceB"], offline[0]["isTrigger"]) == (
        "cmp_eq", VALVE, "unavailable", True)
    assert offline[1]["type"] == "timer_ton" and offline[1]["isFor"]
    assert (rungs[2]["elements"][0]["type"], rungs[2]["elements"][0]["label"]) == ("contact_nc", SWITCH)
    low = rungs[4]["elements"][0]
    assert (low["type"], low["sourceA"], str(low["sourceB"]), low["isTrigger"]) == ("cmp_lt", BATTERY, "20", True)
    # The switch first on the card, as on an alarm clock; the battery with what the logic reads.
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    assert rows[0] == {"entity": SWITCH, "name": "Enabled"} and rows[1] == {"type": "divider"}
    assert [r.get("entity") for r in rows[2:]] == [VALVE, METER, BATTERY]
    card = ai.card_for_config(hass, yaml.safe_load(built["yaml"]), "Garden watering")
    assert card["entities"][0] == {"entity": SWITCH, "name": "Enabled"}


@pytest.mark.parametrize("without, missing", [
    ({"top": True}, ("libi_enable", "the switch is in the conditions of the automation")),
    ({"gate": True}, ("libi_enable", "the start does not check that the on/off switch is on")),
    ({"stop": True}, ("libi_enable", "turning the switch off does not stop it")),
    ({"blocks": True}, ("libi_enable", "an option that turns things off checks the switch")),
    ({"online": True}, ("libi_online", f"it switches {VALVE} without checking that it is online")),
    ({"below": 10}, ("libi_battery", f"no message when {BATTERY} is below 20%")),
])
async def test_an_answer_the_logic_does_not_do_goes_back(hass, libi_ai, hass_ws_client, without, missing):
    plan, selections = await _yes_plan(hass, hass_ws_client)
    client = await hass_ws_client(hass)
    llm, sent = _model(_safe_answer(**without), _safe_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": YES_TO_ALL, "messages": [{"role": "user", "content": "water"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"] and built["tries"] == 2, built
    assert len(built["repaired"]) == 1 and built["repaired"][0].startswith('The user answered "'), built["repaired"]
    assert missing[1] in built["repaired"][0]
    assert "How: Write it exactly as the ON/OFF SWITCH, START MESSAGE, END MESSAGE, OFFLINE and LOW BATTERY lines" in sent[1][-1][
        "content"]
    assert all(i["ok"] for i in built["checklist"])


def test_each_answer_is_seen_in_the_logic_only_as_it_is_written():
    """safety_report on its own: a draft with all the user's answers, and each answer missed in turn."""
    def config(**without):
        text = _safe_answer(**without)["config"]
        for role, eid in (("garden_valve", VALVE), ("water_meter", METER), ("enabled", SWITCH), ("batteries", BATTERY)):
            text = text.replace(f"role:{role}", eid)
        return json.loads(text)
    safety = {"enable": SWITCH, "offline": "tell", "switched": {"garden_valve": [VALVE]}, "names": "valve_garden Switch",
              "battery": 20, "batteries": [BATTERY], "notes": []}
    rungs = {"start": 1, "amount_reached": 2, "switched_off": 3, "garden_valve_offline": 4, "battery_low": 5}
    full = ai.safety_report(safety, config(), rungs)
    assert [(i["id"], i["ok"], i["rung"]) for i in full] == [("libi_enable", True, 3), ("libi_online", True, 1),
                                                             ("libi_offline", True, 4), ("libi_battery", True, 5)]
    assert [i["text"] for i in full] == [
        "The switch on the card: off stops it at once, and nothing starts until it is on",
        "It does not start while valve_garden Switch is offline", "It tells you when valve_garden Switch is offline",
        "It tells you when a battery is below 20%"]
    for without, (iid, missing) in [({"top": True}, ("libi_enable", "the switch is in the conditions")),
                                    ({"stop": True}, ("libi_enable", "turning the switch off does not stop it")),
                                    ({"online": True}, ("libi_online", f"it switches {VALVE} without checking")),
                                    ({"below": 10}, ("libi_battery", f"no message when {BATTERY} is below 20%"))]:
        missed = [(i["id"], i["missing"]) for i in ai.safety_report(safety, config(**without), rungs) if not i["ok"]]
        assert [m[0] for m in missed] == [iid] and missed[0][1].startswith(missing), (without, missed)
    # No message for the valve going offline: the trigger alone is not enough.
    quiet = config()
    quiet["actions"][0]["choose"][3]["sequence"] = [{"action": "switch.turn_off", "target": {"entity_id": VALVE}}]
    assert [i["id"] for i in ai.safety_report(safety, quiet, rungs) if not i["ok"]] == ["libi_offline"]
    # Asked "do not start" only: the start's check, and no message is looked for.
    skip = ai.safety_report({**safety, "offline": "skip", "enable": "", "battery": 0}, config(), rungs)
    assert [(i["id"], i["ok"]) for i in skip] == [("libi_online", True)]
    # The valve off is online too; a check in an or or a not is no check.
    off = config(online=True)
    off["actions"][0]["choose"][0]["conditions"].append({"condition": "state", "entity_id": VALVE, "state": "off"})
    assert all(i["ok"] for i in ai.safety_report(safety, off, rungs))
    hidden = config(gate=True)
    hidden["actions"][0]["choose"][0]["conditions"].append({"condition": "or", "conditions": [
        {"condition": "state", "entity_id": SWITCH, "state": "on"}, {"condition": "state", "entity_id": VALVE, "state": "on"}]})
    assert [i["id"] for i in ai.safety_report(safety, hidden, rungs) if not i["ok"]] == ["libi_enable"]
    assert ai.requirement_problems(full) == [] and ai.requirement_problems(
        ai.safety_report(safety, config(stop=True), rungs))[0].startswith(
        'The user answered "The switch on the card: off stops it at once')


async def test_no_and_nothing_add_nothing_and_a_yes_without_a_battery_says_so(hass, libi_ai, hass_ws_client):
    plan, selections = await _yes_plan(hass, hass_ws_client)
    client = await hass_ws_client(hass)
    plain = json.loads(_safe_answer()["config"])
    plain["triggers"], plain["actions"] = plain["triggers"][:2], [{"choose": plain["actions"][0]["choose"][:2]}]
    for option in plain["actions"][0]["choose"]:
        option["conditions"] = option["conditions"][:1]
    llm, sent = _model({**_safe_answer(), "config": json.dumps(plain)})
    no = {"libi_enable": "No", "libi_offline": "Nothing", "libi_battery": "No"}
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": no, "messages": [{"role": "user", "content": "water"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    told = sent[0][-1]["content"]
    # The switch the user said no to is out of the logic, even with its role and pick sent back from the browser.
    assert "role:enabled" not in told and "ON/OFF SWITCH" not in told and "OFFLINE" not in told
    assert "LOW BATTERY" not in told and built["checklist"] == [] and len(sent) == 1
    # A yes to the battery for a device without one: nothing to write, and the user is told why - in the chat too.
    hass.states.async_set("switch.pump", "off", {"friendly_name": "Pump"})
    hass.states.async_set("sensor.pump_meter", "5", {"friendly_name": "Pump meter", "device_class": "volume",
                                                     "unit_of_measurement": "L"})
    pump = {"garden_valve": ["switch.pump"], "water_meter": ["sensor.pump_meter"]}
    llm, sent = _model({**_safe_answer(), "config": json.dumps(plain)})
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": pump,
                                        "answers": {**no, "libi_battery": "Yes, below 20%"},
                                        "messages": [{"role": "user", "content": "water"}]})
        quiet = (await client.receive_json())["result"]
    assert quiet["ok"], quiet.get("errors")
    assert "No battery was found on the devices you picked, so no message tells of a low battery." in quiet["notes"]
    assert "LOW BATTERY" not in sent[0][-1]["content"]
    safety = ai.safety_answers(hass, ai.clean_plan(hass, copy.deepcopy(plan)), {"garden_valve": ["switch.pump"]},
                               {"libi_battery": "Yes, below 20%", "libi_offline": "Do not start, no message"})
    assert safety["battery"] == 0 and safety["offline"] == "skip" and safety["switched"] == {"garden_valve": ["switch.pump"]}
    assert safety["notes"] == ["No battery was found on the devices you picked, so no message tells of a low battery."]
    assert "persistent_notification" in "\n".join(ai.safety_context(safety))
    assert ai.safety_context({}) == [] and ai.safety_report({}, {}, {}) == []
    # A yes with two switches picked is no switch: it is left out, and said.
    two = ai.safety_answers(hass, ai.clean_plan(hass, copy.deepcopy(plan)),
                            {"garden_valve": [VALVE], "enabled": [SWITCH, "input_boolean.other"]}, {"libi_enable": "Yes"})
    assert two["enable"] == "" and two["notes"] == ["The on/off switch needs exactly one helper, so it was left out."]


async def test_a_net_that_does_it_already_is_not_asked_again(hass, libi_ai, hass_ws_client):
    """Update NET 1: the net has its switch, tells of its valve offline and of its battery - LIBI does not ask again."""
    _valve_device(hass)
    hass.states.async_set(SWITCH, "on", {"friendly_name": "Garden watering - enabled"})
    selections = {"garden_valve": [VALVE], "water_meter": [METER], "enabled": [SWITCH], "batteries": [BATTERY]}
    plan = ai.clean_plan(hass, {**copy.deepcopy(SAFE_PLAN), "new_helpers": [], "roles": SAFE_PLAN["roles"] + [
        {"id": "enabled", "label": "x", "purpose": "condition", "domains": ["input_boolean"], "device_classes": [],
         "keywords": [], "area_keywords": []},
        {"id": "batteries", "label": "x", "purpose": "measure", "domains": ["sensor"], "device_classes": [],
         "keywords": [], "area_keywords": []}]})
    draft = await ai.async_build_draft(hass, plan, selections, _safe_answer())
    assert draft["ok"], draft["errors"]
    assert ai.config_enable(draft["auto"]) == {SWITCH}
    assert ai.config_offline(draft["auto"], [VALVE]) and ai.config_battery(draft["auto"], [BATTERY])
    net = yaml_to_ast(hass, draft["auto"])
    net["id"] = "n_garden"
    change = {**SAFE_PLAN, "intent": "modify", "target_net": "n_garden"}
    res = await _safe_plan(hass, hass_ws_client, change, [net], "update NET 1: water at six")
    assert res["plan"]["intent"] == "modify"
    # [CHANGED 2026-11-02, v3.81.0] The net sends no message when it starts or ends: those two are asked.
    assert [q["id"] for q in res["plan"]["questions"]] == ["duration", "libi_start_message", "libi_end_message"]
    # A net that tells of both as well is asked nothing.
    told = copy.deepcopy(draft["auto"])
    options = told["actions"][0]["choose"]
    options[0]["sequence"].append({"action": "notify.notify", "data": {"message": "started"}})
    told["triggers"].append({"trigger": "state", "entity_id": VALVE, "not_from": ["unavailable", "unknown"], "to": "off",
                             "id": "ended"})
    options.append({"conditions": [{"condition": "trigger", "id": "ended"}],
                    "sequence": [{"action": "notify.notify", "data": {"message": "ended"}}]})
    assert ai.config_start_message(told, [VALVE]) and ai.config_end_message(told, [VALVE])
    assert not ai.config_start_message(draft["auto"], [VALVE]) and not ai.config_end_message(draft["auto"], [VALVE])
    net = yaml_to_ast(hass, told)
    net["id"] = "n_garden"
    res = await _safe_plan(hass, hass_ws_client, change, [net], "update NET 1: water at six")
    assert [q["id"] for q in res["plan"]["questions"]] == ["duration"]


def test_the_plan_prompt_leaves_libis_questions_to_libi():
    text = " ".join(ai.PLAN_SYSTEM.split())
    # [CHANGED 2026-11-02, v3.81.0] And the messages when it starts and when it ends.
    assert ("LIBI itself asks whether to add an on/off switch for the whole automation, whether to send a message when "
            "it starts and when it ends (a notification or spoken), what to do when a device it switches is offline, and "
            "whether to send a message when a battery is low") in text
    assert "plan no role or helper for such a switch" in text
    assert "Do ask what else could go wrong in this logic that the user must decide" in text


# ---------------------------------------------------------------- a message when it starts and when it ends (v3.81.0)
# [ADDED 2026-11-02, v3.81.0] The user: "always ask whether you want a message at the end or the start of the process,
# spoken or a notification". Spoken is the Home Assistant app reading it aloud on the phone (Android); the user's house
# has no speaker, and every phone of theirs runs Android.
ANDROID, IPHONE = "notify.mobile_app_sm_s918b", "notify.mobile_app_iphone"


def _two_phones(hass):
    """An Android phone and an iPhone, as the Home Assistant app registers them: only the first reads a message aloud."""
    reg = er.async_get(hass)
    for name, object_id, os_name in (("SM-S918B", "sm_s918b", "Android"), ("iPhone", "iphone", "iOS")):
        entry = MockConfigEntry(domain="mobile_app", data={"device_name": name, "webhook_id": object_id,
                                                           "os_name": os_name, "manufacturer": "x", "model": name,
                                                           "secret": "do-not-show-" + object_id})
        entry.add_to_hass(hass)
        reg.async_get_or_create("notify", "mobile_app", object_id, suggested_object_id=object_id, config_entry=entry)
        hass.states.async_set(f"notify.{object_id}", "unknown", {"friendly_name": name})
        async_mock_service(hass, "notify", f"mobile_app_{object_id}")


async def test_libi_always_asks_for_a_message_when_it_starts_and_when_it_ends(hass, libi_ai, hass_ws_client):
    _valve_device(hass)
    _two_phones(hass)
    assert ai.phones_that_speak(hass) == {ANDROID}
    res = await _safe_plan(hass, hass_ws_client)
    asked = {q["id"]: q for q in res["plan"]["questions"]}
    assert list(asked) == ["duration", "libi_enable", "libi_start_message", "libi_end_message", "libi_offline", "libi_battery"]
    assert asked["libi_start_message"]["note"] == ("It goes to the phones picked in this plan. Spoken: the phone reads it "
                                                   "aloud - the Home Assistant app on Android.")
    # No phone in the plan: LIBI offers its list of them, optional, none ticked - whose phone each is, as always.
    phones = res["plan"]["roles"][0]
    assert (phones["id"], phones["optional"], phones["offered"], phones["phones"]) == (ai.PHONES_ROLE, True, True, True)
    assert [i["entity_id"] for i in res["candidates"][ai.PHONES_ROLE]["items"]] == ["notify.iphone", "notify.sm_s918b"]
    assert ai.PHONES_ROLE not in res["preselect"]
    assert "do-not-show" not in json.dumps(res)
    # The message names a phone: LIBI's list is the one of the plan, once.
    named = await _safe_plan(hass, hass_ws_client, content=f"water the garden and tell {ANDROID}")
    roles = [r for r in named["plan"]["roles"] if r["id"] == ai.PHONES_ROLE]
    assert len(roles) == 1 and not roles[0].get("offered") and named["preselect"][ai.PHONES_ROLE] == ["notify.sm_s918b"]


def _message_answer(**without):
    """The watering of _safe_answer with the messages the user asked for: when it starts, a notification to both phones
    and the text spoken by the Android one; when it ends, a notification to both."""
    config = json.loads(_safe_answer()["config"])
    note = lambda phone, text: {"action": phone, "data": {"message": text}}  # noqa: E731
    spoken = {"action": ANDROID, "data": {"message": "TTS", "data": {"tts_text": "The watering starts"}}}
    start = config["actions"][0]["choose"][0]["sequence"]
    start += [note(ANDROID, "The watering starts"), spoken, note(IPHONE, "The watering starts")]
    if without.get("spoken"):
        start.remove(spoken)
    ended = {"trigger": "state", "entity_id": "role:garden_valve", "not_from": ["unavailable", "unknown"], "to": "off",
             "id": "garden_valve_ended"}
    if without.get("from_anything"):
        ended.pop("not_from")
    if not without.get("end"):
        config["triggers"].append(ended)
        config["actions"][0]["choose"].append({"conditions": [{"condition": "trigger", "id": "garden_valve_ended"}],
                                               "sequence": [note(ANDROID, "The watering ended"),
                                                            note(IPHONE, "The watering ended")]})
    config["mode"] = "single" if without.get("single") else "queued"
    return {**_safe_answer(), "config": json.dumps(config)}


MESSAGES = {"libi_enable": "Yes", "libi_start_message": "Notification and spoken", "libi_end_message": "A notification",
            "libi_offline": "Tell me, and do not start", "libi_battery": "Yes, below 20%"}


async def test_the_messages_are_written_exactly_so_and_checked(hass, libi_ai, hass_ws_client):
    plan, selections = await _yes_plan(hass, hass_ws_client)
    _two_phones(hass)
    selections[ai.PHONES_ROLE] = ["notify.sm_s918b", "notify.iphone"]
    plan["roles"].insert(0, {"id": ai.PHONES_ROLE, "label": "Phones to notify", "purpose": "target", "domains": ["notify"],
                             "device_classes": [], "keywords": [], "area_keywords": [], "optional": True})
    client = await hass_ws_client(hass)
    llm, sent = _model(_message_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": MESSAGES, "messages": [{"role": "user", "content": "water"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    told = sent[0][-1]["content"]
    assert (f"START MESSAGE (the user's answer): in the start option, right after the step that turns role:garden_valve on - "
            f"to each of {ANDROID}, {IPHONE} a notification, ") in told
    assert f"and right after it, to each of {ANDROID}, the same text spoken: " in told
    assert '{"action": "<service>", "data": {"message": "TTS", "data": {"tts_text": "<the text>"}}}' in told
    assert ('END MESSAGE (role:garden_valve): a trigger {"trigger": "state", "entity_id": "role:garden_valve", "not_from": '
            '["unavailable", "unknown"], "to": "off", "id": "garden_valve_ended"} with an option of its own - a notification '
            f"to each of {ANDROID}, {IPHONE}") in told
    assert 'The automation\'s mode is then "queued"' in told
    mine = {i["id"]: (i["ok"], i["kind"]) for i in built["checklist"]}
    assert mine["libi_start"] == (True, "message") and mine["libi_end"] == (True, "message"), built["checklist"]
    assert [i["text"] for i in built["checklist"] if i["id"] in ("libi_start", "libi_end")] == [
        "It tells you when it starts (a notification and spoken)", "It tells you when it ends (a notification)"]
    assert built["round_trip"]["ok"], built["round_trip"]
    # Drawn with the palette's blocks: the notification and its spoken twin are ONE MOVE NOTIFY/TTS; the end is its rung.
    rungs = built["net"]["rungs"]
    moves = [(e.get("mode"), e.get("target")) for e in rungs[0]["elements"] if e["type"] == "move"]
    assert ("both", ANDROID) in moves and ("notify", IPHONE) in moves, moves
    end = rungs[-1]["elements"]
    assert (end[0]["type"], end[0]["label"], end[0]["isTrigger"]) == ("contact_nc", VALVE, True)
    assert [e.get("mode") for e in end[1:]] == ["notify", "notify"]


async def test_a_message_goes_to_the_notify_service_the_user_named(hass, libi_ai, hass_ws_client):
    """With no phone in the plan, a message of LIBI's questions goes to the notify service the user's message names - not
    to Home Assistant's own notifications."""
    plan, selections = await _yes_plan(hass, hass_ws_client)
    async_mock_service(hass, "notify", "family")
    client = await hass_ws_client(hass)
    llm, sent = _model(_safe_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": {**YES_TO_ALL, "libi_end_message": "A notification"},
                                        "messages": [{"role": "user", "content": "water, and tell notify.family"}]})
        await client.receive_json()
    told = sent[0][-1]["content"]
    assert "with an option of its own - a notification to each of notify.family: " in told
    assert 'a notification: {"action": "persistent_notification.create"' not in told


@pytest.mark.parametrize("without, iid, missing", [
    ({"spoken": True}, "libi_start", f"after it turns them on, it does not send the spoken message to {ANDROID}"),
    ({"end": True}, "libi_end", f"nothing tells you when {VALVE} turns off"),
    ({"from_anything": True}, "libi_end", f"the trigger of {VALVE} turning off also fires when it comes back from unavailable"),
    ({"single": True}, "libi_end", "in mode single Home Assistant drops the message"),
])
def test_each_message_is_seen_in_the_logic_only_as_it_is_written(without, iid, missing):
    def config(**leave):
        text = _message_answer(**leave)["config"]
        for role, eid in (("garden_valve", VALVE), ("water_meter", METER), ("enabled", SWITCH), ("batteries", BATTERY)):
            text = text.replace(f"role:{role}", eid)
        return json.loads(text)
    safety = {"start": "both", "end": "notify", "phones": [ANDROID, IPHONE], "speakers": [ANDROID],
              "switched": {"garden_valve": [VALVE]}, "names": "valve_garden Switch", "notes": []}
    assert all(i["ok"] for i in ai.safety_report(safety, config(), {}))
    missed = [(i["id"], i["missing"]) for i in ai.safety_report(safety, config(**without), {}) if not i["ok"]]
    assert [m[0] for m in missed] == [iid] and missed[0][1].startswith(missing), missed


async def test_a_message_without_a_phone_that_speaks_is_a_notification(hass, libi_ai):
    _valve_device(hass)
    _two_phones(hass)
    plan = ai.clean_plan(hass, {**copy.deepcopy(SAFE_PLAN), "new_helpers": [], "questions": [
        {"id": qid, "text": "x", "choices": []} for qid in ai.SAFETY_QUESTIONS]})
    plan["roles"].insert(0, {"id": ai.PHONES_ROLE, "label": "p", "purpose": "target", "domains": ["notify"],
                             "device_classes": [], "keywords": [], "area_keywords": [], "optional": True})
    iphone = ai.safety_answers(hass, copy.deepcopy(plan), {"garden_valve": [VALVE], ai.PHONES_ROLE: ["notify.iphone"]},
                               {"libi_start_message": "Spoken", "libi_end_message": "Notification and spoken"})
    assert (iphone["start"], iphone["end"], iphone["phones"], iphone["speakers"]) == ("notify", "notify", [IPHONE], [])
    assert iphone["notes"] == [
        "No phone picked reads a message aloud (the Home Assistant app on Android), so the message when it starts is a "
        "notification.",
        "No phone picked reads a message aloud (the Home Assistant app on Android), so the message when it ends is a "
        "notification."]
    # The phones the user named in the message are phones as well, and nothing is said twice.
    named = ai.safety_answers(hass, copy.deepcopy(plan), {"garden_valve": [VALVE], ai.PHONES_ROLE: ["notify.sm_s918b"]},
                              {"libi_start_message": "Spoken"}, [ANDROID, "notify.family"])
    assert named["phones"] == [ANDROID, "notify.family"] and named["speakers"] == [ANDROID] and named["start"] == "speak"
    # Spoken by the phone that speaks; the one that cannot gets the notification. Without a phone, Home Assistant's own.
    assert ai._wanted_messages("speak", [ANDROID, IPHONE], [ANDROID]) == [(ANDROID, True), (IPHONE, False)]
    assert ai._wanted_messages("both", [ANDROID, IPHONE], [ANDROID]) == [(ANDROID, False), (ANDROID, True), (IPHONE, False)]
    assert ai._wanted_messages("notify", [], []) == [("persistent_notification.create", False)]
    assert "persistent_notification.create" in ai._message_how("notify", [], [])
    assert ai._message_how("speak", [ANDROID, IPHONE], [ANDROID]).endswith(
        f'to {IPHONE}, which cannot speak, a notification: {{"action": "<service>", "data": {{"message": "<the text>"}}}}')
    # Nothing switched, nothing to tell of; not answered, nothing asked of the logic.
    assert ai.safety_answers(hass, copy.deepcopy(plan), {}, {"libi_start_message": "Spoken"})["start"] == ""
    assert ai.safety_answers(hass, copy.deepcopy(plan), {"garden_valve": [VALVE]}, {})["end"] == ""


def test_the_rain_now_is_checked_as_not_raining_never_as_sunny():
    """[ADDED 2026-11-02, v3.81.0] The user's watering at 05:00 asked that the weather now be sunny before it watered;
    before sunrise it is clear-night, so it never would have, and LIBI ticked the line. A check of the rain now holds the
    start back on rain only."""
    def config(*checks):
        return {"triggers": [{"trigger": "time", "at": "05:00:00", "id": "start"}], "conditions": [], "actions": [
            {"choose": [{"conditions": [{"condition": "trigger", "id": "start"}, *checks],
                         "sequence": [{"action": "switch.turn_on", "target": {"entity_id": VALVE}}]}]}]}
    plan = {"requirements": [{"id": "r1", "text": "Skip when it rains now", "kind": "weather_now"}]}

    def line(auto):
        item = ai.requirement_report(plan, {"ok": True, "auto": auto}, {}, {})[0]
        return item["ok"], item["missing"]
    w = "weather.guy_smart_home"
    sunny = {"condition": "state", "entity_id": w, "state": "sunny"}
    assert line(config(sunny)) == (False, ai._WEATHER_NOW_FAIR)
    assert "clear-night, before sunrise" in ai._WEATHER_NOW_FAIR
    rain = list(ai.RAIN_STATES)
    for good in ({"condition": "not", "conditions": [{"condition": "state", "entity_id": w, "state": rain}]},
                 {"condition": "template", "value_template": "{{ states('" + w + "') not in ['rainy', 'pouring'] }}"},
                 {"condition": "template", "value_template": "{{ not is_state('" + w + "', 'rainy') }}"},
                 {"condition": "state", "entity_id": w, "state": ["sunny", "clear-night", "partlycloudy", "cloudy", "fog"]}):
        assert line(config(good)) == (True, ""), good
    for bad in (sunny, {"condition": "template", "value_template": "{{ is_state('" + w + "', 'sunny') }}"},
                {"condition": "template", "value_template": "{{ states('" + w + "') in ['sunny', 'partlycloudy'] }}"},
                {"condition": "not", "conditions": [{"condition": "state", "entity_id": w, "state": "sunny"}]},
                {"condition": "state", "entity_id": w, "state": "rainy"}):
        assert line(config(bad)) == (False, ai._WEATHER_NOW_FAIR), bad
    # A good check does not make up for one that asks for the sun.
    assert line(config(sunny, {"condition": "not", "conditions": [{"condition": "state", "entity_id": w, "state": rain}]}))[0] is False
    # The weather read only in a message holds nothing back.
    told = config()
    told["actions"][0]["choose"][0]["sequence"].append(
        {"action": "notify.notify", "data": {"message": "{{ states('" + w + "') }}"}})
    assert line(told) == (False, ai._WEATHER_NOW_UNCHECKED)
    flat = " ".join(ai.BUILD_SYSTEM.split())
    assert "The weather NOW is checked for rain, never for fair weather: before sunrise it is clear-night" in flat
    assert "<the rain NOW: not raining, as Weather says>" in flat


async def test_the_users_sunny_check_goes_back_to_be_written_as_not_raining(hass, garden, hass_ws_client):
    """[ADDED 2026-11-02, v3.81.0] The user's draft of 2026-11-01, the rain now written as "sunny": it goes back, with how
    to write it, and the answer that checks for rain is the one built."""
    plan, selections = _alarm_plan(hass)
    sunny = json.loads(_alarm_answer()["config"])
    sunny["actions"][0]["choose"][0]["conditions"][2] = {"condition": "state", "entity_id": "role:weather", "state": "sunny"}
    client = await hass_ws_client(hass)
    llm, sent = _model({**_alarm_answer(), "config": json.dumps(sunny)}, _alarm_answer())
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "messages": [{"role": "user", "content": "water the garden"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"] and built["tries"] == 2, built
    assert built["repaired"] == [f'The request asks "Skip when it rains now" (weather_now), and the logic does not do it: '
                                 f'{ai._WEATHER_NOW_FAIR}.']
    assert "never that it is sunny" in sent[1][-1]["content"]
    assert next(i for i in built["checklist"] if i["id"] == "r4")["ok"] is True


def _ticked_answer(phone, also=None):
    """[v3.81.1] The watering with a message when it starts and when it ends, to the phone the user ticked - and to
    another one too (also), as a model that follows the message rather than the ticks writes it."""
    config = json.loads(_safe_answer()["config"])
    note = lambda text: [{"action": p, "data": {"message": text}} for p in [phone] + ([also] if also else [])]  # noqa: E731
    config["actions"][0]["choose"][0]["sequence"] += note("The watering starts")
    config["triggers"].append({"trigger": "state", "entity_id": "role:garden_valve", "not_from": ["unavailable", "unknown"],
                               "to": "off", "id": "garden_valve_ended"})
    config["actions"][0]["choose"].append({"conditions": [{"condition": "trigger", "id": "garden_valve_ended"}],
                                           "sequence": note("The watering ended")})
    config["mode"] = "queued"
    return {**_safe_answer(), "config": json.dumps(config)}


async def test_the_phones_the_user_ticks_win_over_the_ones_the_message_names(hass, libi_ai, hass_ws_client):
    """[ADDED 2026-11-02, v3.81.1] The user's chat: the message names notify.mobile_app_sm_n985f_guy_phone (and a phone
    that is gone), and in the list the user ticked another phone. The model was told the named phone "exists, use it as
    written", LIBI's check of the ticks sent that back, and LIBI's new lines wanted a message to it all the same - two of
    them stayed missing ("I picked other phones in the box than in the message, and it ignored my choice")."""
    plan, selections = await _yes_plan(hass, hass_ws_client)
    _user_phones(hass)
    plan["roles"].insert(0, {"id": ai.PHONES_ROLE, "label": "Phones to notify", "purpose": "target", "domains": ["notify"],
                             "device_classes": [], "keywords": [], "area_keywords": [], "optional": False})
    selections[ai.PHONES_ROLE] = ["notify.sm_s938b"]
    named, ticked = "notify.mobile_app_sm_n985f_guy_phone", "notify.mobile_app_sm_s938b"
    request = [{"role": "user", "content": f"water the garden, and send me a message to {named} and "
                                           "notify.mobile_app_mi_9t_pro"}]
    answers = {**YES_TO_ALL, "libi_start_message": "A notification", "libi_end_message": "A notification"}
    client = await hass_ws_client(hass)
    llm, sent = _model(_ticked_answer(ticked, also=named), _ticked_answer(ticked))
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": answers, "messages": request})
        built = (await client.receive_json())["result"]
    told = sent[0][-1]["content"]
    assert f"- {named}: a phone the user left unticked in the list - leave it out" in told
    assert f"- {named}: exists, use it as written" not in told
    assert "- notify.mobile_app_mi_9t_pro: MISSING" in told
    assert f"right after the step that turns role:garden_valve on - a notification to each of {ticked}: " in told
    assert named not in told.split("START MESSAGE", 1)[1].split("\n", 1)[0]
    # The draft that followed the message goes back once; the one that keeps to the ticks does every line.
    assert built["ok"] and built["tries"] == 2, built
    assert built["repaired"] == [f"{named} is a phone the user did not tick."]
    lines = {i["id"]: i["ok"] for i in built["checklist"]}
    assert lines["libi_start"] is True and lines["libi_end"] is True, built["checklist"]
    assert all(ok is not False for ok in lines.values()), built["checklist"]
    # LIBI's own messages: the ticked phones, and a named service that is no phone; never a named phone left unticked.
    safety = ai.safety_answers(hass, ai.clean_plan(hass, copy.deepcopy(plan)), copy.deepcopy(selections), answers,
                               [named, "notify.family"])
    assert safety["phones"] == [ticked, "notify.family"]
    # Without a ticked phone the services the message names are used as written, as before.
    alone = ai.safety_answers(hass, ai.clean_plan(hass, copy.deepcopy(plan)), {"garden_valve": [VALVE]}, answers, [named])
    assert alone["phones"] == [named]


# ---------------------------------------------------------------- the local variables in one window (v3.82.0)
# [ADDED 2026-11-02, v3.82.0] The user: "I deleted all the variables of the last NET - why did it not ask me to create them
# again? ... all the local variables at the start, in the same window, always with the option to create them all new; and
# if a variable is free, choose it instead of creating a new one".
VAR_PLAN = {
    "reply": "Set it from the screen.", "intent": "create", "target_net": "", "level": "automation", "name": "Garden",
    "roles": [{"id": "garden_valve", "label": "Garden valve", "purpose": "target", "domains": ["switch"],
               "device_classes": [], "keywords": ["valve"], "area_keywords": []},
              {"id": "litres", "label": "Litres", "purpose": "condition", "domains": ["input_number"],
               "device_classes": [], "keywords": ["litres"], "area_keywords": []},
              {"id": "max_minutes", "label": "Max minutes", "purpose": "condition", "domains": ["input_number"],
               "device_classes": [], "keywords": ["minutes"], "area_keywords": []},
              {"id": "start_time", "label": "Start time", "purpose": "trigger", "domains": ["input_datetime"],
               "device_classes": [], "keywords": ["start"], "area_keywords": []},
              {"id": "valve_target", "label": "Valve target", "purpose": "condition", "domains": ["number"],
               "device_classes": [], "keywords": ["target"], "area_keywords": []}],
    "questions": [], "new_helpers": [], "requirements": []}


def _garden_settings(hass):
    hass.states.async_set("input_number.garden_litres", "200", {"friendly_name": "Garden litres", "min": 0, "max": 500,
                                                                "step": 10, "mode": "box", "unit_of_measurement": "L"})
    hass.states.async_set("input_number.max_minutes", "45", {"friendly_name": "Max minutes", "min": 1, "max": 120,
                                                             "step": 1, "mode": "slider"})
    hass.states.async_set("number.valve_target", "50", {"friendly_name": "Valve target"})


async def test_every_local_variable_can_be_made_new_and_a_free_one_is_chosen(hass, libi_ai, hass_ws_client):
    _garden_settings(hass)
    res = await _safe_plan(hass, hass_ws_client, VAR_PLAN)
    plan = res["plan"]
    roles = {r["id"]: r for r in plan["roles"]}
    assert [rid for rid, r in roles.items() if r.get("variable")] == ["litres", "max_minutes", "start_time", "valve_target"]
    assert not roles["garden_valve"].get("variable")
    # Free helpers that fit are what the variables start with; the helper LIBI would make instead, set up like each one
    # and under a name of its own, is its alternative.
    alternatives = {h["role"]: h for h in plan["alternatives"]}
    assert set(alternatives) == {"litres", "max_minutes"}
    assert alternatives["litres"]["pick"] == "input_number.garden_litres"
    assert alternatives["litres"]["name"] == "Garden litres (2)"
    assert alternatives["litres"]["settings"] == {"min": 0, "max": 500, "step": 10, "mode": "box", "unit_of_measurement": "L"}
    assert alternatives["max_minutes"]["pick"] == "input_number.max_minutes"
    assert alternatives["max_minutes"]["settings"]["mode"] == "slider"
    # Nothing fits the start time: the helper to make is proposed, as before; a number of a device cannot be made.
    assert [h["role"] for h in plan["new_helpers"]] == ["start_time"]
    assert "valve_target" not in alternatives and "valve_target" not in [h["role"] for h in plan["new_helpers"]]
    # The user's case: every helper of the last NET deleted - each one is to be made again.
    for eid in ("input_number.garden_litres", "input_number.max_minutes"):
        hass.states.async_remove(eid)
    again = (await _safe_plan(hass, hass_ws_client, VAR_PLAN))["plan"]
    assert again["alternatives"] == []
    assert [h["role"] for h in again["new_helpers"]] == ["litres", "max_minutes", "start_time"]
    # The cleaning on the way back keeps what the build needs; the alternatives are the chat's only.
    assert "alternatives" not in ai.clean_plan(hass, copy.deepcopy(plan))


def test_a_variable_starts_with_the_helper_that_is_ticked_named_or_free_and_never_one_taken():
    cand = {"exact": True, "items": [{"entity_id": "input_number.a"}, {"entity_id": "input_number.b", "exists": True},
                                     {"entity_id": "input_number.c", "named": True}]}
    role = {"id": "litres"}
    assert ai._fitting(role, cand, {"litres": ["input_number.a"]}, set()) == "input_number.a"
    assert ai._fitting(role, cand, {}, set()) == "input_number.b"
    assert ai._fitting(role, cand, {}, {"input_number.b"}) == "input_number.c"
    assert ai._fitting(role, cand, {}, {"input_number.b", "input_number.c"}) == "input_number.a"
    # The closest only are never chosen by themselves.
    assert ai._fitting(role, {"exact": False, "items": [{"entity_id": "input_number.a"}]}, {}, set()) == ""
    assert ai._fitting(role, {}, {}, set()) == ""


async def test_two_variables_never_start_with_one_helper(hass, libi_ai, hass_ws_client):
    hass.states.async_set("input_number.garden_minutes", "45", {"friendly_name": "Garden minutes litres", "min": 1, "max": 120})
    both = {**copy.deepcopy(VAR_PLAN), "roles": VAR_PLAN["roles"][:3]}
    both["roles"][2]["keywords"] = ["minutes"]
    plan = (await _safe_plan(hass, hass_ws_client, both))["plan"]
    picks = [h.get("pick") for h in plan["alternatives"]]
    assert picks.count("input_number.garden_minutes") == 1, plan["alternatives"]
    assert [h["role"] for h in plan["new_helpers"]] == [r for r in ("litres", "max_minutes")
                                                         if r not in [a["role"] for a in plan["alternatives"]]]


async def test_a_unique_name_is_kept_apart_from_the_users(hass):
    hass.states.async_set("input_number.a", "1", {"friendly_name": "Garden litres"})
    hass.states.async_set("input_number.b", "1", {"friendly_name": "Garden litres (2)"})
    assert ai._unique_name(hass, "input_number", "Garden litres") == "Garden litres (3)"
    assert ai._unique_name(hass, "input_number", "Other") == "Other"
    assert ai._unique_name(hass, "input_boolean", "Garden litres") == "Garden litres"


# ---------------------------------------------------------------- who is where, and where to say it (v3.83.0)
# [ADDED 2026-11-02, v3.83.0] The user's train reminder: "a spoken reminder when I am at a zone I choose, at a time I set:
# it is X o'clock, get ready to leave for the train home". With "work" in the request only the zones named so were
# offered - not the one needed, "Yulia in Lod" - and no one to be in it; with "X" a person to pick and no zone at all.
def _places(hass):
    for eid, name in (("zone.work", "Guy at work Tzur Yigal"), ("zone.yulia_at_work", "Yulia at work Petah Tikva"),
                      ("zone.yvlyh_blvd", "Yulia in Lod"), ("zone.home", "Home")):
        hass.states.async_set(eid, "0", {"friendly_name": name})
    for eid, name in (("person.yulia", "Yulia"), ("person.guy", "Guy")):
        hass.states.async_set(eid, "home", {"friendly_name": name})
    hass.states.async_set("device_tracker.sm_s918b_2", "home", {"friendly_name": "SM-S938B"})
    _two_phones(hass)


REMINDER = {"reply": "Pick the zone.", "intent": "create", "target_net": "", "level": "automation",
            "name": "Train reminder", "questions": [], "new_helpers": [],
            "requirements": [{"id": "r1", "text": "Only when I am at the zone", "kind": "other"},
                             {"id": "r2", "text": "At the time I set", "kind": "time"},
                             {"id": "r3", "text": "A spoken reminder to leave for the train", "kind": "message"}]}
ZONE_ROLE = {"id": "work_zone", "label": "Work zone", "purpose": "condition", "domains": ["zone"], "device_classes": [],
             "keywords": ["work"], "area_keywords": []}
WHO_ROLE = {"id": "who", "label": "Person or device", "purpose": "condition", "domains": ["person", "device_tracker"],
            "device_classes": [], "keywords": [], "area_keywords": []}
TIME_ROLE = {"id": "reminder_time", "label": "Reminder time", "purpose": "trigger", "domains": ["input_datetime"],
             "device_classes": [], "keywords": ["reminder"], "area_keywords": []}


async def test_every_zone_is_offered_and_a_zone_gets_who_must_be_there(hass, libi_ai, hass_ws_client):
    _places(hass)
    res = await _safe_plan(hass, hass_ws_client, {**REMINDER, "roles": [ZONE_ROLE, TIME_ROLE]})
    zones = [i["entity_id"] for i in res["candidates"]["work_zone"]["items"]]
    # Every zone, the ones the words match first - the zone the user needed was not offered at all before.
    assert set(zones) == {"zone.work", "zone.yulia_at_work", "zone.yvlyh_blvd", "zone.home"}
    assert zones[:2] == ["zone.work", "zone.yulia_at_work"] and res["candidates"]["work_zone"]["exact"] is True
    roles = {r["id"]: r for r in res["plan"]["roles"]}
    who = roles["who_is_there"]
    assert (who["label"], who["domains"], who["optional"]) == ("Who must be there", ["person", "device_tracker"], False)
    assert {"person.yulia", "person.guy", "device_tracker.sm_s918b_2"} <= {i["entity_id"] for i in res["candidates"]["who_is_there"]["items"]}
    # The point of it is a message, and the plan named no phone: the phones are offered, one to be ticked.
    phones = roles[ai.PHONES_ROLE]
    assert (phones["optional"], phones.get("offered"), phones["for_message"]) == (False, False, True)
    assert {i["entity_id"] for i in res["candidates"][ai.PHONES_ROLE]["items"]} == {"notify.sm_s918b", "notify.iphone"}


async def test_a_person_gets_a_zone_to_be_in(hass, libi_ai, hass_ws_client):
    _places(hass)
    asked = {**REMINDER, "roles": [WHO_ROLE, TIME_ROLE],
             "questions": [{"id": "which_zone", "text": "Which zone?", "choices": []}]}
    res = await _safe_plan(hass, hass_ws_client, asked)
    roles = {r["id"]: r for r in res["plan"]["roles"]}
    zone = roles["the_zone"]
    # Optional: the logic may read home or away from the person alone.
    assert (zone["label"], zone["domains"], zone["optional"]) == ("The zone", ["zone"], True)
    assert {i["entity_id"] for i in res["candidates"]["the_zone"]["items"]} == {"zone.work", "zone.yulia_at_work",
                                                                                 "zone.yvlyh_blvd", "zone.home"}
    # Both there already: nothing added. A question has nothing to complete, nor a message without a message line.
    both = await _safe_plan(hass, hass_ws_client, {**REMINDER, "roles": [ZONE_ROLE, WHO_ROLE, TIME_ROLE]})
    assert [r["id"] for r in both["plan"]["roles"] if r["id"] in ("who_is_there", "the_zone")] == []
    quiet = {**REMINDER, "roles": [ZONE_ROLE, WHO_ROLE, TIME_ROLE], "requirements": REMINDER["requirements"][:2]}
    assert ai.PHONES_ROLE not in [r["id"] for r in (await _safe_plan(hass, hass_ws_client, quiet))["plan"]["roles"]]
    plan = {"intent": "answer", "roles": [ZONE_ROLE], "requirements": REMINDER["requirements"]}
    ai.presence_roles(hass, plan, {}) or ai.message_phones(hass, plan, {})
    assert plan["roles"] == [ZONE_ROLE]


async def test_the_reminder_is_spoken_by_the_phone(hass, libi_ai, hass_ws_client):
    _places(hass)
    hass.states.async_set("input_datetime.train_reminder", "16:45:00", {"friendly_name": "Train reminder time",
                                                                        "has_time": True, "has_date": False})
    res = await _safe_plan(hass, hass_ws_client, {**REMINDER, "roles": [ZONE_ROLE, TIME_ROLE]})
    plan = res["plan"]
    selections = {"work_zone": ["zone.yvlyh_blvd"], "who_is_there": ["person.yulia"],
                  "reminder_time": ["input_datetime.train_reminder"], ai.PHONES_ROLE: ["notify.sm_s918b"]}
    config = {"mode": "single", "triggers": [{"trigger": "time", "at": "role:reminder_time", "id": "start"}],
              "conditions": [{"condition": "zone", "entity_id": "role:who_is_there", "zone": "role:work_zone"}],
              "actions": [{"action": ANDROID, "data": {"message": "TTS", "data": {
                  "tts_text": "It is {{ states('role:reminder_time')[:5] }}, get ready to leave for the train home"}}}]}
    answer = {"reply": "Built.", "level": "automation", "name": "Train reminder", "description": "x",
              "config": json.dumps(config), "ui_card": "", "notes": [], "covers": []}
    client = await hass_ws_client(hass)
    llm, sent = _model(answer)
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": {}, "messages": [{"role": "user", "content": "train reminder"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    # The build is told how a phone reads a message aloud.
    told = " ".join(ai.BUILD_SYSTEM.split())
    assert ('A message spoken aloud is the phone reading it - the Home Assistant app on Android: {"action": '
            '"notify.mobile_app_<phone>", "data": {"message": "TTS", "data": {"tts_text": "..."}}}, one per phone') in told
    assert "PHONES (send each message to every one of these, one action each): " + ANDROID in sent[0][-1]["content"]
    assert built["round_trip"]["ok"], built["round_trip"]
    elements = built["net"]["rungs"][0]["elements"]
    kinds = [(e["type"], e.get("sourceA"), e.get("sourceB"), e.get("mode")) for e in elements]
    assert ("cmp_eq", "person.yulia", "zone.yvlyh_blvd", None) in kinds, kinds
    assert any(e["type"] == "move" and e.get("mode") == "tts" and e.get("target") == ANDROID for e in elements), kinds
    assert "input_datetime.train_reminder" in json.dumps(built["yaml"])


def test_the_plan_prompt_makes_a_place_and_who_is_there_roles():
    text = " ".join(ai.PLAN_SYSTEM.split())
    # [CHANGED 2026-11-02, v3.84.0] Two roles, never one for both: the user's next plan had one list of people, trackers and
    # zones for who and where at once.
    assert ('Being at a place is a zone: a role with domains ["zone"] for the place AND a role with domains ["person", '
            '"device_tracker"] for who must be there - two roles, never one for both, and never a question for either') in text


# ---------------------------------------------------------------- the zone chosen on the card (v3.84.0)
# [ADDED 2026-11-02, v3.84.0] The user's train reminder again: "if I am at a zone X I choose from the UI, at a time I set
# from the UI, on the days I choose there". The plan made the zone a text helper (input_text "the zone chosen for the
# reminder", with a map icon), in which no zone can be chosen, and gave one list of the people, the trackers and the
# zones - "location tracking / zone" - for who and where at once.
MIXED_ROLE = {"id": "location_tracking", "label": "Location tracking / zone", "purpose": "condition",
              "domains": ["device_tracker", "person", "zone"], "device_classes": [], "keywords": ["work", "location"],
              "area_keywords": []}
CHOSEN_ROLE = {"id": "selected_zone", "label": "The zone chosen for the reminder", "purpose": "condition",
               "domains": ["input_text"], "device_classes": [], "keywords": [], "area_keywords": []}
# The zones of _places as a person's state names them: home in the Home zone, Home first, the others by name.
ZONES = ["home", "Guy at work Tzur Yigal", "Yulia at work Petah Tikva", "Yulia in Lod"]


async def test_the_zone_chosen_on_the_card_is_a_dropdown_of_the_zones(hass, libi_ai, hass_ws_client):
    _places(hass)
    # A passive zone is never anyone's state, nor a name longer than an option; a dropdown of anything else is no zone.
    hass.states.async_set("zone.parents_exit", "0", {"friendly_name": "Parents exit", "passive": True})
    hass.states.async_set("zone.far", "0", {"friendly_name": "x" * 61})
    hass.states.async_set("input_select.mode", "away", {"friendly_name": "Mode zone", "options": ["home", "away"]})
    asked = {**REMINDER, "roles": [MIXED_ROLE, CHOSEN_ROLE, TIME_ROLE],
             "new_helpers": [{"role": "selected_zone", "domain": "input_text", "name": "The zone chosen for the reminder",
                              "settings": {"icon": "mdi:map-marker", "max": 100}}]}
    res = await _safe_plan(hass, hass_ws_client, asked)
    roles = {r["id"]: r for r in res["plan"]["roles"]}
    chosen = roles["selected_zone"]
    assert (chosen["domains"], chosen["zone_choice"], chosen["variable"]) == (["input_select"], True, True)
    helper = next(h for h in res["plan"]["new_helpers"] if h["role"] == "selected_zone")
    assert (helper["domain"], helper["name"], helper["settings"]) == (
        "input_select", "The zone chosen for the reminder", {"icon": "mdi:map-marker", "options": ZONES})
    assert res["candidates"]["selected_zone"]["items"] == []
    # One role for who and where is who must be there, the people first; no zone is picked - the card chooses it.
    who = roles["location_tracking"]
    assert (who["label"], who["domains"]) == ("Who must be there", ["device_tracker", "person"])
    listed = res["candidates"]["location_tracking"]
    assert [i["entity_id"] for i in listed["items"]] == ["person.guy", "person.yulia", "device_tracker.sm_s918b_2"]
    assert listed["exact"] is True
    assert not any("zone" in r["domains"] for r in res["plan"]["roles"])
    assert "who_is_there" not in roles and "the_zone" not in roles


async def test_a_free_dropdown_of_zones_is_the_zone_chosen(hass, libi_ai, hass_ws_client):
    _places(hass)
    hass.states.async_set("input_select.zone_for_alerts", "home", {"friendly_name": "Zone for alerts",
                                                                   "options": ["home", "Yulia in Lod"]})
    hass.states.async_set("input_select.mode", "away", {"friendly_name": "Mode zone", "options": ["home", "away"]})
    # The model's own options are not the user's zones: LIBI's are.
    asked = {**REMINDER, "roles": [WHO_ROLE, {**CHOSEN_ROLE, "domains": ["input_select"]}, TIME_ROLE],
             "new_helpers": [{"role": "selected_zone", "domain": "input_select", "name": "Reminder zone",
                              "settings": {"options": ["Work", "Lod"]}}]}
    res = await _safe_plan(hass, hass_ws_client, asked)
    assert [i["entity_id"] for i in res["candidates"]["selected_zone"]["items"]] == ["input_select.zone_for_alerts"]
    # The free one is chosen instead of a new one; the new one stays in reach, with the zones as they are now.
    assert not any(h["role"] == "selected_zone" for h in res["plan"]["new_helpers"])
    alt = next(a for a in res["plan"]["alternatives"] if a["role"] == "selected_zone")
    assert (alt["pick"], alt["domain"], alt["name"], alt["settings"]) == (
        "input_select.zone_for_alerts", "input_select", "Zone for alerts (2)", {"icon": "mdi:map-marker", "options": ZONES})


async def test_one_role_for_who_and_where_is_split_into_the_two(hass, libi_ai, hass_ws_client):
    _places(hass)
    hass.states.async_set("device_tracker.galaxy_watch5", "home", {"friendly_name": "Galaxy Watch5"})
    mixed = {**MIXED_ROLE, "keywords": ["work", "watch"]}
    res = await _safe_plan(hass, hass_ws_client, {**REMINDER, "roles": [mixed, TIME_ROLE]})
    roles = {r["id"]: r for r in res["plan"]["roles"]}
    assert (roles["location_tracking"]["label"], roles["location_tracking"]["domains"]) == (
        "Who must be there", ["device_tracker", "person"])
    # Everyone who can be there, the one its words match first: a word for one tracker does not hide the people.
    assert [i["entity_id"] for i in res["candidates"]["location_tracking"]["items"]] == [
        "device_tracker.galaxy_watch5", "person.guy", "person.yulia", "device_tracker.sm_s918b_2"]
    # The plan asked for a zone: one must be picked, every zone listed, the ones the words of that role match first.
    zone = roles["the_zone"]
    assert (zone["label"], zone["domains"], zone["optional"]) == ("The zone", ["zone"], False)
    zones = [i["entity_id"] for i in res["candidates"]["the_zone"]["items"]]
    assert zones[:2] == ["zone.work", "zone.yulia_at_work"], zones
    assert set(zones) == {"zone.work", "zone.yulia_at_work", "zone.yvlyh_blvd", "zone.home"}


async def test_the_zone_chosen_on_the_card_is_one_cmp_eq(hass, libi_ai, hass_ws_client):
    _places(hass)
    hass.states.async_set("input_select.reminder_zone", "Yulia in Lod", {"friendly_name": "Reminder zone", "options": ZONES})
    hass.states.async_set("input_datetime.train_reminder", "16:45:00", {"friendly_name": "Train reminder time",
                                                                        "has_time": True, "has_date": False})
    asked = {**REMINDER, "roles": [MIXED_ROLE, CHOSEN_ROLE, TIME_ROLE],
             "new_helpers": [{"role": "selected_zone", "domain": "input_text", "name": "Reminder zone (2)", "settings": {}}]}
    res = await _safe_plan(hass, hass_ws_client, asked)
    plan = res["plan"]
    assert [i["entity_id"] for i in res["candidates"]["selected_zone"]["items"]] == ["input_select.reminder_zone"]
    selections = {"location_tracking": ["person.yulia"], "selected_zone": ["input_select.reminder_zone"],
                  "reminder_time": ["input_datetime.train_reminder"], ai.PHONES_ROLE: ["notify.sm_s918b"]}
    config = {"mode": "single", "triggers": [{"trigger": "time", "at": "role:reminder_time", "id": "start"}],
              "conditions": [{"condition": "state", "entity_id": "role:location_tracking", "state": "role:selected_zone"}],
              "actions": [{"action": ANDROID, "data": {"message": "TTS", "data": {
                  "tts_text": "It is {{ states('role:reminder_time')[:5] }}, get ready to leave for the train home"}}}]}
    answer = {"reply": "Built.", "level": "automation", "name": "Train reminder", "description": "x",
              "config": json.dumps(config), "ui_card": "", "notes": [], "covers": []}
    client = await hass_ws_client(hass)
    llm, sent = _model(answer)
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": {}, "messages": [{"role": "user", "content": "train reminder"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    # The build is told how the zone chosen is read: the state of who must be there is the zone chosen.
    told = sent[0][-1]["content"]
    assert ("ZONE CHOICE (the user chooses the zone on the card): role:selected_zone holds the zone chosen" in told
            and '{"condition": "state", "entity_id": "role:location_tracking", "state": "role:selected_zone"}' in told), told
    assert built["round_trip"]["ok"], built["round_trip"]
    kinds = [(e["type"], e.get("sourceA"), e.get("sourceB")) for e in built["net"]["rungs"][0]["elements"]]
    assert ("cmp_eq", "person.yulia", "input_select.reminder_zone") in kinds, kinds
    assert "state: input_select.reminder_zone" in built["yaml"], built["yaml"]
    # Nothing to say without who or without the zone chosen.
    assert ai.zone_choice_context(plan, {"selected_zone": ["input_select.reminder_zone"]}) == []
    assert ai.zone_choice_context(plan, {"location_tracking": ["person.yulia"]}) == []


async def test_a_setting_is_the_zone_chosen_only_when_it_is_one(hass):
    _places(hass)

    def plan_of(*roles, helpers=(), intent="create"):
        return {"intent": intent, "new_helpers": [dict(h) for h in helpers], "roles": [dict(r) for r in roles]}

    who = {"id": "who", "label": "Who", "domains": ["person"]}
    # An area alone is not a place to be in; with who must be there it is.
    area = plan_of({"id": "selected_area", "label": "Area", "domains": ["input_text"]})
    ai.zone_choices(hass, area, {})
    assert "zone_choice" not in area["roles"][0]
    area = plan_of({"id": "selected_area", "label": "Area", "domains": ["input_text"]}, who)
    ai.zone_choices(hass, area, {})
    assert area["roles"][0]["zone_choice"] is True and area["roles"][0]["domains"] == ["input_select"]
    # A helper with a map icon is one too; a text of anything else stays as it is, and an answer has nothing to choose.
    marked = plan_of({"id": "chosen", "label": "x", "domains": ["input_text"]}, who,
                     helpers=[{"role": "chosen", "domain": "input_text", "name": "x", "settings": {"icon": "mdi:map-marker"}}])
    ai.zone_choices(hass, marked, {})
    assert marked["roles"][0]["zone_choice"] is True and marked["new_helpers"][0]["domain"] == "input_select"
    note = plan_of({"id": "message_text", "label": "x", "domains": ["input_text"]}, who)
    ai.zone_choices(hass, note, {})
    assert "zone_choice" not in note["roles"][0] and note["roles"][0]["domains"] == ["input_text"]
    answer = plan_of({"id": "zone_choice", "label": "x", "domains": ["input_select"]}, intent="answer")
    ai.zone_choices(hass, answer, {})
    assert "zone_choice" not in answer["roles"][0]
    # LIBI's own role for it is one whatever the model put in it.
    named = plan_of({"id": "zone_choice", "label": "x", "domains": ["zone"]}, who)
    ai.zone_choices(hass, named, {})
    assert named["roles"][0]["zone_choice"] is True and named["roles"][0]["domains"] == ["input_select"]
    # The card chooses the zone, so a zone to pick in the chat goes.
    both = plan_of(ZONE_ROLE, {"id": "zone_choice", "label": "x", "domains": ["input_select"]})
    found = {"work_zone": {"items": [], "exact": False}}
    ai.zone_choices(hass, both, found)
    assert [r["id"] for r in both["roles"]] == ["zone_choice"] and "work_zone" not in found


async def test_a_dropdown_that_holds_no_zones_is_not_the_zone_chosen(hass, libi_ai, hass_ws_client):
    _places(hass)
    # A free helper of the name proposed is offered as the one that exists - but a dropdown of anything else cannot choose a
    # zone, so a new one is made.
    hass.states.async_set("input_select.reminder_zone", "a", {"friendly_name": "Reminder zone", "options": ["a", "b"]})
    asked = {**REMINDER, "roles": [WHO_ROLE, CHOSEN_ROLE, TIME_ROLE],
             "new_helpers": [{"role": "selected_zone", "domain": "input_text", "name": "Reminder zone", "settings": {}}]}
    res = await _safe_plan(hass, hass_ws_client, asked)
    assert res["candidates"]["selected_zone"]["items"] == []
    helper = next(h for h in res["plan"]["new_helpers"] if h["role"] == "selected_zone")
    assert (helper["domain"], helper["name"], helper["settings"]) == (
        "input_select", "The zone chosen for the reminder", {"icon": "mdi:map-marker", "options": ZONES})


async def test_the_zones_are_named_as_a_persons_state_names_them(hass):
    # One of the user's zones ends in a space ("Yulia at work Petah Tikva "), another has two spaces inside ("Guy's mother"):
    # a person's state in a zone is its name as it is, so the options are too - a trimmed one would never be the state.
    hass.states.async_set("zone.home", "0", {"friendly_name": "At home"})
    hass.states.async_set("zone.mam", "0", {"friendly_name": "Guy  mother"})
    hass.states.async_set("zone.yulia_at_work", "0", {"friendly_name": "Yulia at work Petah Tikva "})
    assert ai.zone_states(hass) == ["home", "Guy  mother", "Yulia at work Petah Tikva "]


def test_a_dropdown_without_options_is_kept_only_for_the_zone_chosen():
    kept, roles = ai.clean_new_helpers([
        {"role": "zone_choice", "domain": "input_select", "name": "Reminder zone", "settings": {"initial": "home"}},
        {"role": "mode", "domain": "input_select", "name": "Mode", "settings": {"initial": "x"}}], [])
    assert [(h["role"], h["settings"]) for h in kept] == [("zone_choice", {})]
    assert [r["id"] for r in roles] == ["zone_choice"]


def test_the_prompts_make_the_zone_chosen_on_the_card_a_dropdown():
    plan = " ".join(ai.PLAN_SYSTEM.split())
    assert ('A zone the user chooses on the screen is an input_select in role "zone_choice", settings {}: LIBI puts the '
            "user's zones in it, as a person's state names them.") in plan
    assert ("A place the user chooses on the screen is no zone role but a helper (new_helpers, below), with the role for "
            "who must be there.") in plan
    build = " ".join(ai.BUILD_SYSTEM.split())
    assert ('A zone the user chooses on the card (ZONE CHOICE in the message): who must be there is in it when their state '
            'is the zone chosen - {"condition": "state", "entity_id": "role:<who>", "state": "role:<zone choice role>"}, '
            "which Home Assistant compares with the state of that dropdown, and LIBI draws as one CMP EQ.") in build


# ---------------------------------------------------------------- how the days are set (v3.95.0)
# The user's choice (2026-11-10): "it is better to have both options - the chat asks whether to use a schedule ... on a
# certain day I leave an hour earlier, which 7 variables cannot do; the choice in the UI must be easy and work if LIBI is
# deleted". LIBI asks: a switch for each day and a start time, or one schedule whose blocks start and end the logic.
KITCHEN = "Kitchen morning light"
KITCHEN_LINES = [{"id": "r1", "text": "at a time I set on the dashboard", "kind": "time"},
                 {"id": "r2", "text": "only on the days I pick there", "kind": "days"},
                 {"id": "r3", "text": "off after the number of minutes I set", "kind": "time_limit"},
                 {"id": "r4", "text": "a dashboard card", "kind": "card"}]
KITCHEN_PLAN = {
    "reply": "Pick the light.", "intent": "create", "target_net": "", "level": "automation", "name": KITCHEN,
    "roles": [{"id": "light", "label": "Kitchen table light", "purpose": "target", "domains": ["light"],
               "device_classes": [], "keywords": ["kitchen", "table"], "area_keywords": []}],
    "questions": [],
    "new_helpers": [{"role": "start_time", "domain": "input_datetime", "name": KITCHEN,
                     "settings": {"has_time": True, "has_date": False}},
                    {"role": "days", "domain": "input_number", "name": f"{KITCHEN} - days",
                     "settings": {"min": 0, "max": 255, "step": 1, "mode": "box"}},
                    {"role": "minutes", "domain": "input_number", "name": f"{KITCHEN} - minutes",
                     "settings": {"min": 1, "max": 120, "step": 1}}],
    "requirements": KITCHEN_LINES,
}
DAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


async def test_libi_asks_how_the_days_are_set_and_each_answer_brings_its_own_variables(hass, libi_ai, hass_ws_client):
    hass.states.async_set("light.kitchen_table", "off", {"friendly_name": "KITCHEN Table"})
    res = await _safe_plan(hass, hass_ws_client, KITCHEN_PLAN, content="Every morning at a time I set ...")
    plan = res["plan"]
    # The days helper the model proposed is what the question replaces: no longer in the plan.
    ids = {r["id"] for r in plan["roles"]}
    assert "days" not in ids and {"start_time", "minutes"} <= ids and "days" not in res["candidates"]
    assert [h["role"] for h in plan["new_helpers"]] == ["start_time", "minutes"]
    question = next(q for q in plan["questions"] if q["id"] == ai.DAYS_QUESTION)
    assert question["libi"] is True and question["text"] == "How do you want to set the days and the time on the dashboard?"
    assert question["choices"] == ["A switch for each day, and a start time",
                                   "A schedule: the days, and the hours of each day"]
    assert "the card works without LIBI" in question["note"] and "its own hours" in question["note"]
    switches, week = (question["variants"][c] for c in question["choices"])
    # A switch for each day, Sunday first, each a local variable of its own; the start time and the minutes stay.
    assert [(r["id"], r["label"], r["variable"]) for r in switches["roles"]] == [
        (f"day_{d}", name, True) for d, name in zip(DAYS, DAY_NAMES, strict=True)]
    assert [(h["domain"], h["name"]) for h in switches["helpers"]] == [
        ("input_boolean", f"{KITCHEN} - {d.title()}") for d in DAYS]
    assert switches["drop"] == [] and set(switches["candidates"]) == {f"day_{d}" for d in DAYS}
    # One schedule, an empty week - nothing runs until a block is set: its block is the start and the end, so the start
    # time and the minutes go with it.
    assert [(r["id"], r["purpose"], r["domains"]) for r in week["roles"]] == [(ai.SCHEDULE_ROLE, "trigger", ["schedule"])]
    assert week["helpers"] == [{"role": ai.SCHEDULE_ROLE, "domain": "schedule", "name": KITCHEN, "settings": EMPTY_WEEK}]
    assert week["drop"] == ["start_time", "minutes"]
    # LIBI's question comes back from the browser with the plan.
    assert ai.DAYS_QUESTION in [q["id"] for q in ai.clean_plan(hass, copy.deepcopy(plan))["questions"]]
    # A free schedule of that name is offered first, in place of a new one.
    hass.states.async_set("schedule.kitchen_morning_light", "off", {"friendly_name": KITCHEN})
    res = await _safe_plan(hass, hass_ws_client, KITCHEN_PLAN, content="Every morning at a time I set ...")
    question = next(q for q in res["plan"]["questions"] if q["id"] == ai.DAYS_QUESTION)
    week = question["variants"][question["choices"][1]]
    assert week["helpers"][0]["pick"] == "schedule.kitchen_morning_light"
    assert week["helpers"][0]["name"] == f"{KITCHEN} (2)"
    assert week["candidates"][ai.SCHEDULE_ROLE]["items"][0]["entity_id"] == "schedule.kitchen_morning_light"
    # Without the days helper there is nothing to ask.
    res = await _safe_plan(hass, hass_ws_client, {**KITCHEN_PLAN, "new_helpers": KITCHEN_PLAN["new_helpers"][:1]})
    assert ai.DAYS_QUESTION not in [q["id"] for q in res["plan"]["questions"]]


def _kitchen_states(hass):
    hass.states.async_set("light.kitchen_table", "off", {"friendly_name": "KITCHEN Table"})
    hass.states.async_set("input_datetime.kitchen_start", "06:30:00", {"friendly_name": KITCHEN, "has_time": True,
                                                                       "has_date": False})
    hass.states.async_set("input_number.kitchen_minutes", "10", {"friendly_name": f"{KITCHEN} - minutes", "min": 1,
                                                                  "max": 120})
    for d in DAYS:
        hass.states.async_set(f"input_boolean.kitchen_{d}", "off", {"friendly_name": f"{KITCHEN} - {d.title()}"})
    hass.states.async_set("schedule.kitchen", "off", {"friendly_name": KITCHEN})


def _kitchen_role(rid, domain, purpose="condition"):
    return {"id": rid, "label": rid, "purpose": purpose, "domains": [domain], "device_classes": [], "keywords": [],
            "area_keywords": []}


def _kitchen_answer(triggers, start_conditions=()):
    light = {"entity_id": "role:light"}
    options = [{"conditions": [{"condition": "trigger", "id": "start"}, *start_conditions],
                "sequence": [{"action": "light.turn_on", "target": light}]}]
    options += [{"conditions": [{"condition": "trigger", "id": tid}],
                 "sequence": [{"action": "light.turn_off", "target": light}]}
                for tid in [t["id"] for t in triggers if t["id"] != "start"]]
    config = {"mode": "single", "triggers": triggers, "conditions": [], "actions": [{"choose": options}]}
    return {"reply": "Built.", "level": "automation", "name": KITCHEN, "description": "x", "config": json.dumps(config),
            "ui_card": "", "notes": [], "covers": []}


async def test_a_switch_for_each_day_is_checked_on_its_own_day_and_set_on_the_card(hass, libi_ai, hass_ws_client):
    _kitchen_states(hass)
    plan = ai.clean_plan(hass, {**copy.deepcopy(KITCHEN_PLAN), "new_helpers": [], "roles": [
        KITCHEN_PLAN["roles"][0], _kitchen_role("start_time", "input_datetime", "trigger"),
        _kitchen_role("minutes", "input_number")] + [_kitchen_role(f"day_{d}", "input_boolean") for d in DAYS]})
    selections = {"light": ["light.kitchen_table"], "start_time": ["input_datetime.kitchen_start"],
                  "minutes": ["input_number.kitchen_minutes"],
                  **{f"day_{d}": [f"input_boolean.kitchen_{d}"] for d in DAYS}}
    assert ai.picked_alarm_clock(hass, plan, selections)["mode"] == "switches"
    triggers = [{"trigger": "time", "at": "role:start_time", "id": "start"},
                {"trigger": "state", "entity_id": "role:light", "to": "on",
                 "for": {"minutes": "{{ states('role:minutes') | int(1) }}"}, "id": "time_limit"}]
    roles = {d: f"role:day_{d}" for d in DAYS}
    no_saturday = _kitchen_answer(triggers, [ai.days_switches_condition({d: roles[d] for d in DAYS[:-1]})])
    full = _kitchen_answer(triggers, [ai.days_switches_condition(roles)])
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, no_saturday, full)
    assert built["ok"], built.get("errors")
    told = " ".join(sent[0][-1]["content"].split())
    assert ('ALARM CLOCK (the user sets it on the card): it starts with {"trigger": "time", "at": "role:start_time", '
            '"id": "start"}, never by a schedule; the start option checks the days right after it, exactly so: '
            + json.dumps(ai.days_switches_condition(roles)) + ".") in told
    # A draft that leaves a day out goes back, saying which check is missing.
    assert built["tries"] == 2 and built["repaired"] == [
        'The request asks "only on the days I pick there" (days), and the logic does not do it: it does not check, on '
        "each day, that day's switch on the card."]
    doc = yaml.safe_load(built["yaml"])
    expected = ai.days_switches_condition({d: f"input_boolean.kitchen_{d}" for d in DAYS})
    assert expected in doc["actions"][0]["choose"][0]["conditions"]
    assert all(i["ok"] is not False for i in built["checklist"]) and built["round_trip"]["ok"]
    # The card: the start time, the days as one row of Home Assistant's buttons, the minutes, the light - no row of
    # LIBI's, so the card works without LIBI.
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    assert rows[0] == {"entity": "input_datetime.kitchen_start", "name": "Start time"}
    assert rows[1]["type"] == "buttons"
    assert [(b["entity"], b["name"], b["tap_action"]) for b in rows[1]["entities"]] == [
        (f"input_boolean.kitchen_{d}", d.title(), {"action": "toggle"}) for d in DAYS]
    assert ("input_number.kitchen_minutes", "Minutes") in [(r.get("entity"), r.get("name")) for r in rows]
    assert "custom:" not in built["card_yaml"]


async def test_the_week_schedule_starts_and_ends_the_logic(hass, libi_ai, hass_ws_client):
    _kitchen_states(hass)
    plan = ai.clean_plan(hass, {**copy.deepcopy(KITCHEN_PLAN), "new_helpers": [], "roles": [
        KITCHEN_PLAN["roles"][0], _kitchen_role(ai.SCHEDULE_ROLE, "schedule", "trigger")]})
    selections = {"light": ["light.kitchen_table"], ai.SCHEDULE_ROLE: ["schedule.kitchen"]}
    assert ai.picked_alarm_clock(hass, plan, selections) == {
        "mode": "schedule", "schedule_role": ai.SCHEDULE_ROLE, "schedule": "schedule.kitchen", "time_role": "",
        "time": "", "days": ""}
    role = f"role:{ai.SCHEDULE_ROLE}"
    start = {"trigger": "state", "entity_id": role, "to": "on", "id": "start"}
    no_end = _kitchen_answer([start])
    both = _kitchen_answer([start, {"trigger": "state", "entity_id": role, "to": "off", "id": "end"}])
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, no_end, both)
    assert built["ok"], built.get("errors")
    told = " ".join(sent[0][-1]["content"].split())
    assert ("SCHEDULE (the user sets its blocks - the days, and the hours of each day): it starts when a block starts, "
            f'{{"trigger": "state", "entity_id": "{role}", "to": "on", "id": "start"}}, and the option of '
            f'{{"trigger": "state", "entity_id": "{role}", "to": "off", "id": "end"}} turns off what the start turned '
            "on. No time trigger, no days check and no other time limit: the end of the block is the end. A logic that "
            "turns nothing on - a message, a reminder - has no end trigger and no end option.") in told
    assert "ALARM CLOCK" not in told
    # Without the end of the block: the request's minutes and LIBI's own line go back to the model.
    end = "it does not end when the block ends (a state trigger of the schedule to off)"
    assert built["tries"] == 2 and built["repaired"] == [
        f'The request asks "off after the number of minutes I set" (time_limit), and the logic does not do it: {end}.',
        f'The request asks "It ends when the block ends" (time_limit), and the logic does not do it: {end}.']
    doc = yaml.safe_load(built["yaml"])
    assert doc["triggers"] == [{"trigger": "state", "entity_id": "schedule.kitchen", "to": "on", "id": "start"},
                               {"trigger": "state", "entity_id": "schedule.kitchen", "to": "off", "id": "end"}]
    assert [(i["id"], i["ok"]) for i in built["checklist"]] == [
        ("r1", True), ("r2", True), ("r3", True), ("r4", True), ("week_end", True)]
    assert built["round_trip"]["ok"]
    # The card: the schedule - named as the card is, it reads "Schedule" - and the light; nothing of LIBI's.
    rows = yaml.safe_load(built["card_yaml"])["entities"]
    assert rows[0] == {"entity": "schedule.kitchen", "name": "Schedule"} and "custom:" not in built["card_yaml"]


async def test_a_change_of_a_net_keeps_its_week_schedule(hass, libi_ai, hass_ws_client):
    _kitchen_states(hass)
    light = {"entity_id": "light.kitchen_table"}
    config = {"id": "k1", "alias": KITCHEN, "mode": "single", "conditions": [], "triggers": [
        {"trigger": "state", "entity_id": "schedule.kitchen", "to": "on", "id": "start"},
        {"trigger": "state", "entity_id": "schedule.kitchen", "to": "off", "id": "end"}],
        "actions": [{"choose": [
            {"conditions": [{"condition": "trigger", "id": "start"}],
             "sequence": [{"action": "light.turn_on", "target": light}]},
            {"conditions": [{"condition": "trigger", "id": "end"}],
             "sequence": [{"action": "light.turn_off", "target": light}]}]}]}
    assert ai.net_week_schedule(hass, config) == "schedule.kitchen"
    # Only a schedule that starts it and ends it: one that only starts a net is the model's own (fixed days).
    assert ai.net_week_schedule(hass, {**config, "triggers": config["triggers"][:1]}) == ""
    net = yaml_to_ast(hass, copy.deepcopy(config))
    net["id"] = "n1"
    # The model planned the alarm clock again, as for a new automation: the net's schedule stays, nothing is asked.
    change = {**copy.deepcopy(KITCHEN_PLAN), "intent": "modify", "target_net": "n1"}
    res = await _safe_plan(hass, hass_ws_client, change, nets=[net], content="update NET 1: also turn it on at sunset")
    plan = res["plan"]
    assert plan["intent"] == "modify" and res["preselect"][ai.SCHEDULE_ROLE] == ["schedule.kitchen"]
    assert not {"start_time", "days"} & {r["id"] for r in plan["roles"]}
    # The minutes stay a setting of the change - the helper of that name exists, so it is offered, not made again.
    assert "minutes" in {r["id"] for r in plan["roles"]} and plan["new_helpers"] == []
    assert ai.DAYS_QUESTION not in [q["id"] for q in plan["questions"]]


# ---------------------------------------------------------------- the user's language (v3.95.0)
# The user (2026-11-10): "my question was in English, and it named the variables in Hebrew and answered in Hebrew -
# everything must be in English, especially when I ask in English". The model took the language from the house: its nets,
# helpers and zones are named in Hebrew. The user's language is the one of the user's own last message.
ENGLISH_REQUEST = "Every morning at a time I set on the dashboard, turn on the kitchen table light."


def test_the_users_language_is_the_one_of_their_last_message():
    assert ai.scripts_of(ENGLISH_REQUEST) == {"LATIN"} and "HEBREW" in ai.scripts_of(USER_REQUEST)
    rule = ai.language_rule(ENGLISH_REQUEST)
    assert rule.startswith("USER LANGUAGE: the language of the user's last message, written in Latin letters.")
    assert "they never set the language" in rule and "not copied from them" in rule
    assert ai.language_rule("16:30") == ""
    hebrew = HE["smart_garden_watering_management"]
    answer = {"reply": hebrew, "name": "Train reminder", "requirements": [{"text": "At the time I set", "kind": "time"}],
              "roles": [{"label": hebrew, "keywords": ["train", hebrew], "area_keywords": [hebrew]}],
              "new_helpers": [{"name": hebrew}], "config": json.dumps({"alias": hebrew})}
    # The reply, the label and the new helper's name - not the keywords, which are in both languages on purpose, nor the
    # configuration.
    problems = ai.language_problems(answer, ENGLISH_REQUEST)
    assert len(problems) == 3 and all(p == f'"{hebrew}" is shown to the user, and it is not in the language of the '
                                           "user's last message (Latin letters): write it in that language"
                                      for p in problems), problems
    # A request in Hebrew: Hebrew is its language, and Home Assistant's own terms in Latin letters are fine.
    assert ai.language_problems(answer, USER_REQUEST) == []
    assert ai.language_problems({"reply": f"{hebrew} - SAVE & COMPILE"}, USER_REQUEST) == []
    assert all("USER LANGUAGE at the end of the message" in " ".join(p.split()) for p in (ai.PLAN_SYSTEM, ai.BUILD_SYSTEM))


async def test_a_plan_in_other_letters_than_the_request_goes_back_once(hass, libi_ai, hass_ws_client):
    hass.states.async_set("light.kitchen_table", "off", {"friendly_name": "KITCHEN Table"})
    hebrew = HE["smart_garden_watering_management"]
    first = {**copy.deepcopy(KITCHEN_PLAN), "reply": hebrew, "name": hebrew}
    client = await hass_ws_client(hass)

    async def plan_for(words, *answers):
        llm, sent = _model(*answers)
        with patch.object(ai, "async_llm_json", new=llm):
            await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": True,
                                            "messages": [{"role": "user", "content": words}]})
            return (await client.receive_json())["result"], sent
    res, sent = await plan_for(ENGLISH_REQUEST, first, copy.deepcopy(KITCHEN_PLAN))
    assert len(sent) == 2
    assert "USER LANGUAGE: the language of the user's last message, written in Latin letters." in sent[0][-1]["content"]
    back = sent[1][-1]["content"]
    assert back.startswith("LIBI checked your answer") and f'"{hebrew}" is shown to the user' in back
    assert res["plan"]["name"] == KITCHEN and res["plan"]["reply"] == KITCHEN_PLAN["reply"]
    # Still in other letters the second time: that plan is shown - the model is asked once, not again and again.
    res, sent = await plan_for(ENGLISH_REQUEST, first)
    assert len(sent) == 2 and res["plan"]["name"] == hebrew
    # A request in Hebrew: Hebrew is its language, nothing goes back.
    res, sent = await plan_for(USER_REQUEST, first)
    assert len(sent) == 1 and "written in Hebrew" in sent[0][-1]["content"]


async def test_a_draft_in_other_letters_than_the_request_goes_back(hass, libi_ai, hass_ws_client):
    _kitchen_states(hass)
    plan = ai.clean_plan(hass, {**copy.deepcopy(KITCHEN_PLAN), "new_helpers": [], "requirements": [], "roles": [
        KITCHEN_PLAN["roles"][0], _kitchen_role(ai.SCHEDULE_ROLE, "schedule", "trigger")]})
    selections = {"light": ["light.kitchen_table"], ai.SCHEDULE_ROLE: ["schedule.kitchen"]}
    role = f"role:{ai.SCHEDULE_ROLE}"
    english = _kitchen_answer([{"trigger": "state", "entity_id": role, "to": "on", "id": "start"},
                               {"trigger": "state", "entity_id": role, "to": "off", "id": "end"}])
    hebrew = {**english, "reply": HE["smart_garden_watering_management"]}
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, hebrew, english, words=ENGLISH_REQUEST)
    assert built["ok"], built.get("errors")
    assert "USER LANGUAGE: the language of the user's last message, written in Latin letters." in sent[0][-1]["content"]
    assert built["tries"] == 2 and built["repaired"] == [
        f'"{HE["smart_garden_watering_management"]}" is shown to the user, and it is not in the language of the user\'s '
        "last message (Latin letters): write it in that language"]
    assert built["reply"] == "Built."


# ---------------------------------------------------------------- LIBI Global in the AI chat (v3.95.0)
# The user (2026-11-10): "check why the chat did not let me pick my phone from the Global list - I got the list of the
# devices". The phones list offered each phone's notify entity only; the recipients of LIBI Global - the phones the user
# keeps in one place, each a script.libi_send_to_<name> - were not in it.
RECIPIENT = "script.libi_send_to_guy_my_phone"


def _global_recipient(hass):
    """A recipient of LIBI Global as Home Assistant has it loaded; one whose script is not loaded (deleted, or not yet
    reloaded); and another script of the user's, which is no recipient."""
    hass.states.async_set(RECIPIENT, "off", {"friendly_name": "LIBI Global: Guy My PHONE"})
    async_mock_service(hass, "script", "libi_send_to_guy_my_phone")
    hass.states.async_set("script.libi_send_to_gone", "off", {"friendly_name": "LIBI Global: Gone"})
    hass.states.async_set("script.water_garden", "off", {"friendly_name": "Water the garden"})
    async_mock_service(hass, "script", "water_garden")


async def test_the_recipients_of_libi_global_come_first_in_the_phones_list(hass, libi_ai, hass_ws_client):
    _places(hass)
    _global_recipient(hass)
    assert ai.global_recipients(hass) == {RECIPIENT: "Guy My PHONE"}
    assert ai.message_targets(hass) == {"notify.sm_s918b": ANDROID, "notify.iphone": IPHONE, RECIPIENT: RECIPIENT}
    res = await _safe_plan(hass, hass_ws_client, {**REMINDER, "roles": [ZONE_ROLE, TIME_ROLE]})
    items = res["candidates"][ai.PHONES_ROLE]["items"]
    assert items[0] == {"entity_id": RECIPIENT, "name": "Guy My PHONE", "area": "", "state": "", "device": "",
                        "global": True}
    assert [i["entity_id"] for i in items[1:]] == ["notify.iphone", "notify.sm_s918b"]
    assert not any(i.get("global") for i in items[1:])
    # LIBI's own messages are offered the same list - and a recipient alone is a list to offer.
    plan, candidates = {"roles": []}, {}
    assert ai.offer_phones(hass, plan, candidates)
    assert [i["entity_id"] for i in candidates[ai.PHONES_ROLE]["items"]] == [RECIPIENT, "notify.iphone", "notify.sm_s918b"]
    # Ticked, it is a pick of the phones list - of no other list; and no other script is one.
    sel, errors = ai.clean_selections(hass, res["plan"], {ai.PHONES_ROLE: [RECIPIENT, "script.water_garden"],
                                                          "work_zone": [RECIPIENT, "zone.work"]})
    assert sel[ai.PHONES_ROLE] == [RECIPIENT] and sel["work_zone"] == ["zone.work"]
    assert "script.water_garden does not fit 'Phones to notify'." in errors
    assert f"{RECIPIENT} does not fit 'Work zone'." in errors


def _recipient_reminder(action):
    config = {"mode": "single", "triggers": [{"trigger": "time", "at": "role:reminder_time", "id": "start"}],
              "conditions": [{"condition": "zone", "entity_id": "role:who_is_there", "zone": "role:work_zone"}],
              "actions": [{"action": action, "data": {"message": "TTS", "data": {
                  "tts_text": "Get ready to leave for the train home"}}}]}
    return {"reply": "Built.", "level": "automation", "name": "Train reminder", "description": "x",
            "config": json.dumps(config), "ui_card": "", "notes": [], "covers": []}


async def test_the_reminder_goes_to_the_recipient_of_libi_global_the_user_ticked(hass, libi_ai, hass_ws_client):
    _places(hass)
    _global_recipient(hass)
    hass.states.async_set("input_datetime.train_reminder", "16:45:00", {"friendly_name": "Train reminder time",
                                                                        "has_time": True, "has_date": False})
    plan = (await _safe_plan(hass, hass_ws_client, {**REMINDER, "roles": [ZONE_ROLE, TIME_ROLE]}))["plan"]
    selections = {"work_zone": ["zone.yvlyh_blvd"], "who_is_there": ["person.yulia"],
                  "reminder_time": ["input_datetime.train_reminder"], ai.PHONES_ROLE: [RECIPIENT]}
    client = await hass_ws_client(hass)
    llm, sent = _model(_recipient_reminder(RECIPIENT))
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_build", "nets": [], "plan": plan, "selections": selections,
                                        "answers": {}, "messages": [{"role": "user", "content": "train reminder"}]})
        built = (await client.receive_json())["result"]
    assert built["ok"], built.get("errors")
    told = " ".join(sent[0][-1]["content"].split())
    assert "PHONES (send each message to every one of these, one action each): " + RECIPIENT in told
    assert ("A script.libi_send_to_... in PHONES is a recipient of LIBI Global - the phones the user keeps in one place. "
            "Send to it as to a phone's notify service, with the same data") in told
    # The message line of the plan is met by it, and it is drawn as a phone's message is: MOVE TTS, the recipient its TGT.
    assert {i["id"]: i["ok"] for i in built["checklist"]}["r3"] is True, built["checklist"]
    assert built["round_trip"]["ok"], built["round_trip"]
    elements = built["net"]["rungs"][0]["elements"]
    assert any(e["type"] == "move" and e.get("mode") == "tts" and e.get("target") == RECIPIENT for e in elements), elements
    # Not ticked, it is no service an AI draft may call, and the phone the user ticked would get nothing (RULE 7).
    only_phone = {**selections, ai.PHONES_ROLE: ["notify.sm_s918b"]}
    out = await ai.async_build_draft(hass, plan, only_phone, _recipient_reminder(RECIPIENT))
    assert out["errors"] == [f"The service {RECIPIENT} is not allowed in an AI draft.",
                             f"The message does not go to {ANDROID}, which the user ticked.",
                             f"{RECIPIENT} is a phone the user did not tick."], out["errors"]
    # Another script in its place is not one either, ticked or not.
    out = await ai.async_build_draft(hass, plan, {**selections, ai.PHONES_ROLE: [RECIPIENT, "script.water_garden"]},
                                     _recipient_reminder("script.water_garden"))
    assert "The service script.water_garden is not allowed in an AI draft." in out["errors"]
    assert f"The message does not go to {RECIPIENT}, which the user ticked." in out["errors"]


async def test_a_recipient_of_libi_global_reads_a_spoken_message_aloud(hass, libi_ai):
    """Its script has each Android phone in it read the message aloud and gives an iPhone the spoken text: LIBI's own
    spoken messages go to it as spoken, with no note that nothing picked can speak."""
    _valve_device(hass)
    _two_phones(hass)
    _global_recipient(hass)
    plan = ai.clean_plan(hass, {**copy.deepcopy(SAFE_PLAN), "new_helpers": [], "questions": [
        {"id": qid, "text": "x", "choices": []} for qid in ai.SAFETY_QUESTIONS]})
    plan["roles"].insert(0, {"id": ai.PHONES_ROLE, "label": "p", "purpose": "target", "domains": ["notify"],
                             "device_classes": [], "keywords": [], "area_keywords": [], "optional": True})
    out = ai.safety_answers(hass, copy.deepcopy(plan), {"garden_valve": [VALVE], ai.PHONES_ROLE: [RECIPIENT]},
                            {"libi_start_message": "Spoken", "libi_end_message": "A notification"})
    assert (out["start"], out["end"], out["phones"], out["speakers"], out["notes"]) == (
        "speak", "notify", [RECIPIENT], [RECIPIENT], [])
    assert ai._wanted_messages("speak", out["phones"], out["speakers"]) == [(RECIPIENT, True)]
    # With the iPhone ticked as well, the iPhone alone gets the notification.
    both = ai.safety_answers(hass, copy.deepcopy(plan), {"garden_valve": [VALVE],
                                                         ai.PHONES_ROLE: [RECIPIENT, "notify.iphone"]},
                             {"libi_start_message": "Spoken"})
    assert both["phones"] == [RECIPIENT, IPHONE] and both["speakers"] == [RECIPIENT]
    assert ai._wanted_messages("speak", both["phones"], both["speakers"]) == [(RECIPIENT, True), (IPHONE, False)]
    # A NET that already sends to it after the valve turns on, or when it turns off, already has the message.
    told = {"action": RECIPIENT, "data": {"message": "The watering"}}
    config = {"triggers": [{"trigger": "time", "at": "05:00", "id": "go"},
                           {"trigger": "state", "entity_id": VALVE, "to": "off", "id": "ended"}],
              "actions": [{"choose": [
                  {"conditions": [{"condition": "trigger", "id": "go"}],
                   "sequence": [{"action": "switch.turn_on", "target": {"entity_id": VALVE}}, told]},
                  {"conditions": [{"condition": "trigger", "id": "ended"}], "sequence": [told]}]}]}
    assert ai.config_start_message(config, [VALVE]) and ai.config_end_message(config, [VALVE])
    config["actions"][0]["choose"][0]["sequence"].pop()
    config["actions"][0]["choose"][1]["sequence"] = [{"action": "script.water_garden"}]
    assert not ai.config_start_message(config, [VALVE]) and not ai.config_end_message(config, [VALVE])


# ---------------------------------------------------------------- a reminder on the week schedule (v3.95.0)
# The user's train reminder (2026-11-10): a message on the days and the hours of a schedule, if Guy is in the zone chosen
# on the card. LIBI asked for "It ends when the block ends" although nothing is turned on, the model wrote the end trigger
# with an option of no steps, and the panel drew that rung in red: "Terminal Cap Error", not saved.
TRAIN = "schedule.train_departure_reminder"
TRAIN_ZONE = "input_select.train_reminder_zone_selection"


def _train(hass):
    _places(hass)
    _global_recipient(hass)
    hass.states.async_set(TRAIN, "off", {"friendly_name": "Train departure reminder"})
    hass.states.async_set(TRAIN_ZONE, "Yulia in Lod", {"friendly_name": "Train reminder zone selection",
                                                       "options": ZONES})
    plan = ai.clean_plan(hass, {**copy.deepcopy(REMINDER), "roles": [
        _kitchen_role(ai.SCHEDULE_ROLE, "schedule", "trigger"), _kitchen_role("who", "person"),
        _kitchen_role("zone_choice", "input_select")]})
    plan["roles"].insert(0, {"id": ai.PHONES_ROLE, "label": "Phones to notify", "purpose": "target",
                             "domains": ["notify"], "device_classes": [], "keywords": [], "area_keywords": []})
    selections = {ai.SCHEDULE_ROLE: [TRAIN], "who": ["person.guy"], "zone_choice": [TRAIN_ZONE],
                  ai.PHONES_ROLE: [RECIPIENT]}
    return plan, selections


def _train_answer(*, end):
    """The user's draft: when a block starts, if Guy is in the zone chosen on the card, the message and the spoken message
    to the recipient - and, with end, the end of the block with an option of no steps."""
    role = f"role:{ai.SCHEDULE_ROLE}"
    said = "It is {{ now().strftime('%H:%M') }}. Time to get ready to leave for the train home."
    options = [{"conditions": [{"condition": "trigger", "id": "start"},
                               {"condition": "state", "entity_id": "role:who", "state": "role:zone_choice"}],
                "sequence": [{"action": RECIPIENT, "data": {"message": said, "title": "Train Reminder"}},
                             {"action": RECIPIENT, "data": {"message": "TTS", "data": {"tts_text": said}}}]}]
    triggers = [{"trigger": "state", "entity_id": role, "to": "on", "id": "start"}]
    if end:
        triggers.append({"trigger": "state", "entity_id": role, "to": "off", "id": "end"})
        options.append({"conditions": [{"condition": "trigger", "id": "end"}], "sequence": []})
    config = {"mode": "single", "triggers": triggers, "conditions": [], "actions": [{"choose": options}]}
    return {"reply": "Built.", "level": "automation", "name": "Train Departure Reminder", "description": "x",
            "config": json.dumps(config), "ui_card": "", "notes": [], "covers": []}


async def test_a_reminder_on_the_week_schedule_has_no_end_of_the_block(hass, libi_ai, hass_ws_client):
    plan, selections = _train(hass)
    client = await hass_ws_client(hass)
    built, sent = await _build(client, plan, selections, _train_answer(end=False), words="train reminder")
    assert built["ok"], built.get("errors")
    assert built["tries"] == 1, built.get("repaired")
    # Nothing is turned on, so nothing is to end: LIBI's line of the block's end is not asked.
    assert "week_end" not in [i["id"] for i in built["checklist"]]
    assert all(i["ok"] is not False for i in built["checklist"]), built["checklist"]
    told = " ".join(sent[0][-1]["content"].split())
    assert "A logic that turns nothing on - a message, a reminder - has no end trigger and no end option." in told
    assert ai.rungs_without_action(built["net"]) == []
    doc = yaml.safe_load(built["yaml"])
    assert doc["triggers"] == [{"trigger": "state", "entity_id": TRAIN, "to": "on", "id": "start"}]


async def test_a_rung_that_ends_with_no_action_goes_back_to_the_model(hass, libi_ai, hass_ws_client):
    plan, selections = _train(hass)
    client = await hass_ws_client(hass)
    # The user's draft first: its rung of the block's end is the trigger alone, which the panel draws in red.
    built, _sent = await _build(client, plan, selections, _train_answer(end=True), _train_answer(end=False),
                                words="train reminder")
    assert built["ok"], built.get("errors")
    assert built["tries"] == 2 and built["repaired"] == [
        "LIBI's ladder ends every rung with an action - a coil, a MOVE, a message: rung 2 (trigger id \"end\") ends with "
        "none, and is drawn as an error. Leave out an option with no steps, and a trigger only it was for."]
    assert len(built["net"]["rungs"]) == 1 and ai.rungs_without_action(built["net"]) == []


def test_every_rung_ends_with_an_action_as_the_panel_requires():
    """The panel's rule (libi-core.js, checkPathEnd and the linked rungs): the last block of a rung is an action, a wait,
    or open branches that each end so; of rungs drawn side by side, one is enough."""
    contact = {"type": "contact_no", "raw": {"trigger": "state", "entity_id": "x.y", "id": "go"}}
    move, coil, ton = {"type": "move"}, {"type": "coil"}, {"type": "timer_ton"}
    net = {"rungs": [
        {"id": "r1", "elements": [contact, move]},
        {"id": "r2", "elements": [contact]},
        {"id": "r3", "elements": [contact, {"type": "parallel", "closed": False, "branches": [[coil], [ton, move]]}]},
        {"id": "r4", "elements": [contact, {"type": "parallel", "closed": False, "branches": [[coil], [ton]]}]},
        {"id": "r5", "elements": [contact, {"type": "parallel", "closed": True, "branches": [[coil], [move]]}]},
        {"id": "r6", "elements": [contact, {"type": "repeat", "sequence": [ton]}]},
        {"id": "r7", "elements": [contact, {"type": "timer_ton", "waitFor": True}]},
        {"id": "r8", "elements": [contact, {"type": "math_add"}]},
        {"id": "r9", "elements": []},
        {"id": "r10", "elements": [contact, ton]}, {"id": "r11", "elements": [contact, move]},
        {"id": "r12", "elements": [contact]}, {"id": "r13", "elements": [ton]}],
        "links": [{"aRung": "r10", "bRung": "r11"}, {"aRung": "r12", "bRung": "r13"}]}
    assert ai.rungs_without_action(net) == [(2, "go"), (4, "go"), (5, "go"), (6, "go"), (12, "go"), (13, "")]
    assert ai.rungs_without_action(None) == [] and ai.rungs_without_action({"rungs": "x"}) == []


# ---------------------------------------------------------------- a check that never holds (v3.95.5)
# The user's train reminder was saved with state: zone.work (2026-11-11): Home Assistant compares a state with that text,
# and it never holds. A draft that compares a state with an entity's id goes back to the model.
def test_a_draft_that_compares_a_state_with_an_entity_goes_back():
    config = {"triggers": [{"trigger": "state", "entity_id": "climate.ac", "to": "input_select.mode", "id": "go"}],
              "conditions": [{"condition": "state", "entity_id": "binary_sensor.door", "state": "sensor.other"},
                             {"condition": "state", "entity_id": "person.guy", "state": "input_select.zone"},
                             {"condition": "state", "entity_id": "person.guy", "state": "zone.work"},
                             {"condition": "state", "entity_id": "light.x", "state": ["on", "light.y"]},
                             {"condition": "state", "entity_id": "climate.ac", "state": "heat"}],
              "actions": []}
    said = 'is compared with the text "{}", which its state never is: compare it with a value - a condition reads an '            'input helper as its value, and a person in a zone is a zone condition.'
    assert ai.literal_checks(config) == [
        "climate.ac " + said.format("input_select.mode"), "binary_sensor.door " + said.format("sensor.other"),
        "person.guy " + said.format("zone.work"), "light.x " + said.format("light.y")]
    # A condition may read an input helper; a trigger may not - Home Assistant reads no helper there.
    draft = {"ok": True, "errors": [], "auto": {"triggers": [], "actions": [], "conditions": [
        {"condition": "state", "entity_id": "person.guy", "state": "zone.work"}]}}
    assert ai.draft_problems(draft, {"net": {"rungs": []}}) == ["person.guy " + said.format("zone.work")]
    assert ai.draft_problems({**draft, "auto": {"conditions": [config["conditions"][1]]}}, {"net": {"rungs": []}}) == []
    # [CHANGED 2026-11-11, v3.95.5] A dropdown, a text or a sensor may hold an entity's id as its value - "which speaker"
    # is media_player.kitchen: never counted (the second pass of the review of the release, RULE 41).
    assert ai.literal_checks({"conditions": [
        {"condition": "state", "entity_id": "input_select.speaker", "state": "media_player.kitchen"},
        {"condition": "state", "entity_id": "sensor.template_pick", "state": "light.x"},
        {"condition": "state", "entity_id": "select.mode", "state": "climate.ac"}]}) == []


# ---------------------------------------------------------------- the review of the release (v3.95.5, RULE 41)
def test_a_list_compared_with_an_entity_goes_back_too():
    config = {"triggers": [{"trigger": "state", "entity_id": "person.guy", "to": ["zone.work"], "id": "go"}],
              "conditions": [{"condition": "state", "entity_id": "light.a", "state": ["on", ["sensor.b"]]}]}
    found = ai.literal_checks(config)
    assert [f.split(" is compared")[0] for f in found] == ["person.guy", "light.a"], found
    assert '"zone.work"' in found[0] and '"sensor.b"' in found[1]


async def test_the_names_of_the_house_are_not_a_language(hass, libi_ai, hass_ws_client):
    """A request in English about a valve named in Hebrew: the model quotes its name, and must - it is not a text in
    another language, and it never goes back for it."""
    name = HE["smart_garden_watering_management"]
    hass.states.async_set("switch.valve", "off", {"friendly_name": name})
    raw = {"reply": f"It turns on {name} at the time you set.", "name": "Morning watering"}
    assert name in ai.house_names(hass)
    assert ai.language_problems(raw, ENGLISH_REQUEST, ai.house_names(hass)) == []
    assert len(ai.language_problems(raw, ENGLISH_REQUEST)) == 1
    # A Hebrew text that is no name of the house still goes back.
    other = {"reply": HE["smart_garden_watering_management"][::-1]}
    assert len(ai.language_problems(other, ENGLISH_REQUEST, ai.house_names(hass))) == 1
    # In the chat: the plan that quotes the valve is not sent back.
    hass.states.async_set("light.kitchen_table", "off", {"friendly_name": "KITCHEN Table"})
    client = await hass_ws_client(hass)
    llm, sent = _model({**copy.deepcopy(KITCHEN_PLAN), "reply": raw["reply"]})
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_plan", "nets": [], "share": True,
                                        "messages": [{"role": "user", "content": ENGLISH_REQUEST}]})
        res = (await client.receive_json())["result"]
    assert len(sent) == 1 and res["plan"]["reply"] == raw["reply"]


async def test_a_switch_for_each_day_is_offered_only_when_it_fits(hass, libi_ai, hass_ws_client):
    """Seven roles more than MAX_ROLES allows: clean_plan would have dropped some of the days without a word."""
    hass.states.async_set("light.kitchen_table", "off", {"friendly_name": "KITCHEN Table"})
    extra = [{"id": f"extra_{i}", "label": f"Extra {i}", "purpose": "condition", "domains": ["sensor"],
              "device_classes": [], "keywords": [], "area_keywords": []} for i in range(14)]
    crowded = {**copy.deepcopy(KITCHEN_PLAN), "roles": KITCHEN_PLAN["roles"] + extra}
    res = await _safe_plan(hass, hass_ws_client, crowded, content="Every morning at a time I set ...")
    question = next(q for q in res["plan"]["questions"] if q["id"] == ai.DAYS_QUESTION)
    assert question["choices"] == ["A schedule: the days, and the hours of each day"]
    assert list(question["variants"]) == question["choices"]
    assert "A switch for each day does not fit this plan" in question["note"]


def test_the_roles_a_yes_adds_count_too(hass):
    """The second pass of the review of the release: a yes to the on/off switch adds its role in the chat, after the
    plan - with it, seven more may not fit."""
    def plan(extra, questions):
        roles = [{"id": "days", "label": "Days", "purpose": "condition", "domains": ["input_number"], "device_classes": [],
                  "keywords": [], "area_keywords": []}]
        roles += [{"id": f"r{i}", "label": f"R{i}", "purpose": "condition", "domains": ["sensor"], "device_classes": [],
                   "keywords": [], "area_keywords": []} for i in range(extra)]
        return {"intent": "create", "level": "automation", "name": KITCHEN, "roles": roles, "questions": questions,
                "new_helpers": [{"role": "days", "domain": "input_number", "name": f"{KITCHEN} - days",
                                 "settings": {"min": 0, "max": 255, "step": 1, "mode": "box"}}]}
    enable = {"id": ai.ENABLE_QUESTION, "adds": {"role": {"id": ai.ENABLE_ROLE}, "helper": {}}}
    full = plan(ai.MAX_ROLES - 7, [])
    ai.days_question(hass, full, {}, {})
    asked = next(q for q in full["questions"] if q["id"] == ai.DAYS_QUESTION)
    assert len(asked["choices"]) == 2, asked["choices"]
    crowded = plan(ai.MAX_ROLES - 7, [enable])
    ai.days_question(hass, crowded, {}, {})
    asked = next(q for q in crowded["questions"] if q["id"] == ai.DAYS_QUESTION)
    assert asked["choices"] == ["A schedule: the days, and the hours of each day"], asked["choices"]


def test_the_third_pass_of_the_review():
    """An attribute may hold an entity's id (a person's source is a tracker); a sign such as \u00b5 is no language, and
    Japanese - kanji, hiragana and katakana - is one."""
    assert ai.literal_checks({"conditions": [{"condition": "state", "entity_id": "person.guy", "attribute": "source",
                                              "state": "device_tracker.guy_phone"}]}) == []
    assert ai.scripts_of("PM2.5 above 35 \u00b5g/m\u00b3, \u00aa") == {"LATIN"}
    assert ai.language_problems({"reply": "PM2.5 above 35 \u00b5g/m\u00b3"}, ENGLISH_REQUEST) == []
    assert ai.scripts_of("\u3053\u3093\u306b\u3061\u306f \u30ab\u30bf\u30ab\u30ca \u6f22\u5b57") == {"CJK"}


def test_the_fourth_pass_of_the_review(hass):
    """A schedule trigger written to [on] / to [off] is the week schedule; a drawn rung whose last element is no block
    is skipped, not a crash."""
    hass.states.async_set("schedule.week", "off", {"friendly_name": "Week"})
    config = {"triggers": [{"trigger": "state", "entity_id": "schedule.week", "to": ["on"], "id": "start"},
                           {"trigger": "state", "entity_id": "schedule.week", "to": ["off"], "id": "end"}]}
    assert ai.net_week_schedule(hass, config) == "schedule.week"
    net = {"rungs": [{"id": "r1", "elements": ["x"]}, {"id": "r2", "elements": [{"type": "move"}]}],
           "links": [{"aRung": "r1", "bRung": "r2"}]}
    assert ai.rungs_without_action(net) == []


async def test_the_fifth_pass_of_the_review(hass, libi_ai, hass_ws_client):
    """A NET named in Hebrew, quoted by a reply to a request in English, is a name, not a language; a week schedule
    written to [on] / to [off] with platform: is seen as the start and the end."""
    _kitchen_states(hass)
    name = HE["smart_garden_watering_management"]
    client = await hass_ws_client(hass)
    llm, sent = _model({**copy.deepcopy(KITCHEN_PLAN), "reply": f"I change {name}."})
    with patch.object(ai, "async_llm_json", new=llm):
        await client.send_json_auto_id({"type": "libi/ai_plan", "share": True,
                                        "nets": [{"id": "n3", "name": name, "level": "automation", "rungs": []}],
                                        "messages": [{"role": "user", "content": ENGLISH_REQUEST}]})
        res = (await client.receive_json())["result"]
    assert len(sent) == 1 and res["plan"]["reply"] == f"I change {name}."
    plan = ai.clean_plan(hass, {**copy.deepcopy(KITCHEN_PLAN), "new_helpers": [], "requirements": [], "roles": [
        KITCHEN_PLAN["roles"][0], _kitchen_role(ai.SCHEDULE_ROLE, "schedule", "trigger")]})
    alarm = ai.picked_alarm_clock(hass, plan, {"light": ["light.kitchen_table"], ai.SCHEDULE_ROLE: ["schedule.kitchen"]})
    auto = {"triggers": [{"platform": "state", "entity_id": "schedule.kitchen", "to": ["on"], "id": "start"},
                         {"platform": "state", "entity_id": "schedule.kitchen", "to": ["off"], "id": "end"}],
            "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.kitchen_table"}}]}
    report = ai.requirement_report(plan, {"ok": True, "auto": auto}, {"net": {"rungs": []}}, {}, alarm)
    assert {i["id"]: i["ok"] for i in report} == {"week_start": True, "week_end": True}, report
