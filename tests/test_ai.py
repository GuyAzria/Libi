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
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.libi import ai
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


async def test_options_flow_switches_to_cloud_and_keeps_the_key(hass, libi_ai):
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
