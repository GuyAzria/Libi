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
"""The websocket commands against a real Home Assistant: authorization, schemas, and the rules
that protect the user's automations.yaml (CLAUDE.md RULE 5 and RULE 32)."""
import copy
import json
import logging
import os

import pytest
import yaml
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.libi import ai
from custom_components.libi import websocket as ws
from custom_components.libi.const import AI_MODE_NONE, CONF_AI_MODE, DOMAIN
from custom_components.libi.libi_to_yaml import same_config
from custom_components.libi.yaml_to_libi import day_bits_template, yaml_to_ast

from .save_helpers import home_assistant_files, save, send

AUTO = {
    "id": "a1", "alias": "Lamp", "description": "keep me", "mode": "single",
    "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
    "conditions": [],
    "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}],
}
HAND = {"id": "hand1", "alias": "Hand written", "triggers": [], "actions": [{"delay": 1}],
        "zz_custom": 1, "aa_first": 2}


def _dump(data) -> str:
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


@pytest.fixture
async def libi(hass: HomeAssistant, config_dir):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_AI_MODE: AI_MODE_NONE})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return config_dir


@pytest.fixture
def writes(monkeypatch):
    """[ADDED v3.85.0] The name of every file LIBI itself writes."""
    seen = []
    real = ws.write_utf8_file_atomic

    def record(path, content, *args, **kwargs):
        seen.append(os.path.basename(path))
        return real(path, content, *args, **kwargs)

    monkeypatch.setattr(ws, "write_utf8_file_atomic", record)
    return seen


def _net(hass, auto=AUTO):
    return yaml_to_ast(hass, copy.deepcopy(auto))


async def test_non_admin_is_rejected(hass, libi, hass_ws_client, hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for msg in ({"type": "libi/compile_project", "nets": []},
                {"type": "libi/save_done", "nets": []},
                {"type": "libi/net_delete_plan", "net_id": "n1", "nets": []},
                {"type": "libi/net_removed", "net_id": "n1", "mode": "kept"},
                {"type": "libi/save_automation", "nets": []},
                {"type": "libi/list_automations"},
                {"type": "libi/delete_automation", "automation_id": "a1"},
                {"type": "libi/net_helpers", "net": {}},
                {"type": "libi/local_names"},
                {"type": "libi/local_name_set", "entity_id": "light.x", "name": "Mine"},
                {"type": "libi/phones"},
                {"type": "libi/global"},
                {"type": "libi/global_plan", "name": "Guy", "phones": ["notify.mobile_app_x"]},
                {"type": "libi/global_done", "key": "libi_send_to_guy", "op": "remove"},
                {"type": "libi/global_move_plan", "key": "libi_send_to_guy",
                 "entries": [{"domain": "automation", "key": "a1"}]},
                {"type": "libi/global_move_done", "key": "libi_send_to_guy",
                 "done": [{"domain": "automation", "key": "a1", "op": "upsert"}]},
                {"type": "libi/project_list"}):
        await client.send_json_auto_id(msg)
        res = await client.receive_json()
        assert res["success"] is False, msg
        assert res["error"]["code"] == "unauthorized", msg
    assert not (libi / "automations.yaml").exists()
    assert not (libi / "libi" / "local_names.json").exists()


async def test_unknown_field_is_rejected(hass, libi, hass_ws_client):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/project_open", "slug": "x", "slgu": "typo"})
    res = await client.receive_json()
    assert res["success"] is False
    assert res["error"]["code"] == "invalid_format"


@pytest.mark.parametrize("slug", ["../escape", "..\\escape", "a/b", ".hidden"])
async def test_path_slug_is_rejected(hass, libi, hass_ws_client, slug):
    client = await hass_ws_client(hass)
    for msg in ({"type": "libi/project_open", "slug": slug},
                {"type": "libi/project_delete", "slug": slug},
                {"type": "libi/net_helpers", "net": {}, "slug": slug},
                {"type": "libi/compile_project", "slug": slug, "nets": []},
                {"type": "libi/save_done", "slug": slug, "nets": []},
                {"type": "libi/net_delete_plan", "slug": slug, "net_id": "n1", "nets": []},
                {"type": "libi/net_removed", "slug": slug, "net_id": "n1", "mode": "kept"},
                {"type": "libi/get_automation", "slug": slug, "automation_id": "a1"}):
        await client.send_json_auto_id(msg)
        res = await client.receive_json()
        assert res["success"] is False, msg
        assert res["error"]["code"] == "invalid_slug", msg
    assert not list(libi.parent.glob("*.libi"))


# [CHANGED 2026-11-04, v3.85.0] Home Assistant's own config API writes automations.yaml, scripts.yaml and scenes.yaml -
# the HACS review: an integration does not patch the user's YAML files. SAVE & COMPILE is libi/compile_project, the
# panel's calls to that API, and libi/save_done (save_helpers.save makes them as the panel does).
async def test_save_goes_through_home_assistants_config_api(hass, libi, writes, hass_ws_client, hass_client):
    calls = await home_assistant_files(hass, libi, automations=[HAND])
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass)])
    # Compiled and checked, nothing written: one entry to send, the hand written one not among them.
    assert [(op["domain"], op["key"]) for op in plan["upserts"]] == [("automation", "a1")] and plan["removals"] == []
    assert done["saved"] is True and done["status"] == "ok", done
    assert (done["written"], done["reloaded"]) == (["automation"], ["automation"])
    assert calls["automation"] == 1
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert data[0] == HAND
    assert list(data[0]) == list(HAND)
    assert [a for a in data if a["id"] == "a1"][0]["mode"] == "single"
    assert hass.states.get("automation.lamp").attributes["id"] == "a1"
    # LIBI wrote its own project and history - none of Home Assistant's files.
    assert sorted(set(writes)) == ["p.libi", "p.versions.json"], writes


async def test_unchanged_save_sends_nothing(hass, libi, hass_ws_client, hass_client):
    calls = await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    await save(client, http, [_net(hass)])
    before = (libi / "automations.yaml").stat().st_mtime_ns
    plan, done = await save(client, http, [_net(hass)])
    assert (plan["upserts"], plan["removals"], plan["unchanged"]) == ([], [], 1)
    assert (done["saved"], done["written"], done["reloaded"], done["errors"]) == (True, [], [], [])
    assert calls["automation"] == 1
    assert (libi / "automations.yaml").stat().st_mtime_ns == before


async def test_unreadable_file_means_nothing_is_written(hass, libi, writes, hass_ws_client, hass_client):
    broken = "- id: x\n  alias: [unclosed\n"
    (libi / "automations.yaml").write_text(broken, encoding="utf-8")
    (libi / "scripts.yaml").write_text("keep: {sequence: []}\n", encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass)])
    assert plan["ok"] is False and done is None
    assert plan["errors"] == ["automations.yaml could not be read", "nothing was saved"]
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == broken
    assert (libi / "scripts.yaml").read_text(encoding="utf-8") == "keep: {sequence: []}\n"
    assert not (libi / "libi" / "p.libi").exists()
    assert writes == []


async def test_a_net_that_does_not_compile_saves_nothing(hass, libi, writes, monkeypatch, hass_ws_client, hass_client):
    """The user's rule (2026-11-04): SAVE & COMPILE compiles first; when that does not hold, it says why and saves
    nothing - not the NETs that did compile either."""
    calls = await home_assistant_files(hass, libi)
    real = ws.ast_to_yaml

    def compile_or_fail(hass_, net):
        if net.get("name") == "Broken":
            raise ValueError("a rung that goes nowhere")
        return real(hass_, net)

    monkeypatch.setattr(ws, "ast_to_yaml", compile_or_fail)
    broken = _net(hass)
    broken.update(id="n_broken", name="Broken")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass), broken])
    assert (plan["ok"], plan["errors"], done) == (False, ['NET 2 "Broken": a rung that goes nowhere'], None)
    assert yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8")) == []
    assert calls["automation"] == 0 and writes == []


async def test_what_home_assistant_does_not_accept_is_not_sent(hass, libi, writes, hass_ws_client, hass_client):
    """Checked with Home Assistant's own validator before anything is sent, so one entry it would refuse keeps all of
    them back."""
    calls = await home_assistant_files(hass, libi)
    bad = copy.deepcopy(AUTO)
    bad.update(id="a2", alias="Bad", triggers=[{"trigger": "no_such_trigger"}])
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass), _net(hass, bad)])
    assert plan["ok"] is False and done is None
    assert len(plan["errors"]) == 1 and plan["errors"][0].startswith('NET 2 "Bad": Home Assistant does not accept it'), plan
    assert yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8")) == []
    assert calls["automation"] == 0 and writes == []


async def test_failed_reload_is_reported(hass, libi, monkeypatch, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)

    async def no_reload(call: ServiceCall) -> None:
        return None

    hass.services.async_register("automation", "reload", no_reload)
    monkeypatch.setattr(ws, "RELOAD_WAIT_SECONDS", 0.5)
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await save(client, http, [_net(hass)])
    assert (done["saved"], done["status"], done["written"], done["reloaded"]) == (True, "error", ["automation"], [])
    assert any("automation a1: Home Assistant has not reloaded it within" in e for e in done["errors"]), done


async def test_an_automation_not_set_up_again_is_not_reloaded(hass, libi, monkeypatch, hass_ws_client, hass_client):
    """An automation that runs already: written, but not set up again, it is the old one that still runs."""
    await home_assistant_files(hass, libi, automations=[AUTO])
    assert hass.states.get("automation.lamp") is not None

    async def no_reload(call: ServiceCall) -> None:
        return None

    hass.services.async_register("automation", "reload", no_reload)
    monkeypatch.setattr(ws, "RELOAD_WAIT_SECONDS", 0.5)
    client, http = await hass_ws_client(hass), await hass_client()
    edited = json.loads(json.dumps(_net(hass)).replace("light.x", "light.y"))
    _plan, done = await save(client, http, [edited])
    assert (done["status"], done["reloaded"]) == ("error", []), done
    assert any("automation a1: Home Assistant has not reloaded it within" in e for e in done["errors"]), done


async def test_the_wait_for_home_assistant(hass, libi, monkeypatch):
    """Back unavailable is a reload that failed; an entity still there after a delete is not removed."""
    monkeypatch.setattr(ws, "RELOAD_WAIT_SECONDS", 0.3)
    reg = er.async_get(hass)
    entry = reg.async_get_or_create("automation", "automation", "a9", suggested_object_id="broken")
    since = ws._since("")
    hass.states.async_set(entry.entity_id, "unavailable", {"id": "a9"})
    bad, errors = await ws._wait_for_reloads(hass, [{"domain": "automation", "key": "a9", "op": "upsert"}], since)
    assert bad == {"automation"} and errors == [
        "automation.broken is unavailable: Home Assistant did not accept it - see Settings ▸ System ▸ Logs"], errors
    bad, errors = await ws._wait_for_reloads(hass, [{"domain": "automation", "key": "a9", "op": "remove"}], since)
    assert bad == {"automation"} and errors[0].startswith("automation a9: Home Assistant has not removed it within"), errors
    reg.async_remove(entry.entity_id)
    assert await ws._wait_for_reloads(hass, [{"domain": "automation", "key": "a9", "op": "remove"}], since) == (set(), [])


async def test_a_refused_change_stops_the_rest_and_only_what_reached_home_assistant_counts(hass, libi, hass_ws_client,
                                                                                          hass_client):
    await home_assistant_files(hass, libi)
    hall = copy.deepcopy(AUTO)
    hall.update(id="a2", alias="Hall")
    nets = [_net(hass), _net(hass, hall)]
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await save(client, http, nets, refuse=("a2",))
    assert (done["saved"], done["status"]) == (True, "error")
    assert 'NET 2 "Hall": Home Assistant refused it: Message malformed: refused by the test' in done["errors"], done
    assert [a["id"] for a in yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))] == ["a1"]
    project = json.loads((libi / "libi" / "p.libi").read_text(encoding="utf-8"))
    assert project["owned"]["automations"] == ["a1"]
    # Only what runs is a version.
    assert set(done["versions"]) == {"n_a1"}
    # The next save sends what did not get there, and nothing else.
    plan, done = await save(client, http, nets)
    assert [op["key"] for op in plan["upserts"]] == ["a2"] and done["status"] == "ok", done


async def test_nothing_reached_home_assistant_so_nothing_is_saved(hass, libi, writes, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await save(client, http, [_net(hass)], refuse=("a1",))
    assert (done["saved"], done["written"]) == (False, []) and done["message"].startswith("Not saved."), done
    assert not (libi / "libi" / "p.libi").exists() and writes == []


async def test_scripts_and_scenes_go_through_the_api(hass, libi, hass_ws_client, hass_client):
    calls = await home_assistant_files(hass, libi)
    script = _net(hass)
    script.update(id="n_script", level="script", name="Night Routine")
    scene = {"id": "n_scene", "name": "Evening", "level": "scene", "rungs": [
        {"id": "r1", "elements": [{"id": "e1", "type": "coil_s", "label": "light.x"}]}]}
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [script, scene], slug="garden")
    assert sorted((op["domain"], op["key"]) for op in plan["upserts"]) == [("scene", "n_scene"), ("script", "night_routine")]
    assert done["status"] == "ok", done
    assert sorted(done["reloaded"]) == ["scene", "script"] and calls["script"] == 1 and calls["scene"] == 1
    assert "night_routine" in yaml.safe_load((libi / "scripts.yaml").read_text(encoding="utf-8"))
    assert [s["id"] for s in yaml.safe_load((libi / "scenes.yaml").read_text(encoding="utf-8"))] == ["n_scene"]
    assert (libi / "libi" / "garden.libi").exists()
    assert not (libi / "libi" / "night_routine.libi").exists()


async def test_a_net_gone_from_the_project_is_removed_through_the_api(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    hall = copy.deepcopy(AUTO)
    hall.update(id="a2", alias="Hall")
    client, http = await hass_ws_client(hass), await hass_client()
    await save(client, http, [_net(hass), _net(hass, hall)])
    assert hass.states.get("automation.hall") is not None
    plan, done = await save(client, http, [_net(hass)])
    assert plan["removals"] == [{"domain": "automation", "key": "a2", "label": 'automation "Hall" (a2)'}], plan
    assert done["status"] == "ok", done
    assert [a["id"] for a in yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))] == ["a1"]
    assert hass.states.get("automation.hall") is None


async def test_another_projects_entry_is_never_removed(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    hall = copy.deepcopy(AUTO)
    hall.update(id="a2", alias="Hall")
    client, http = await hass_ws_client(hass), await hass_client()
    await save(client, http, [_net(hass), _net(hass, hall)], slug="p")
    await save(client, http, [_net(hass, hall)], slug="q")
    plan, _done = await save(client, http, [_net(hass)], slug="p")
    assert plan["removals"] == []
    assert "a2" in [a["id"] for a in yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))]


# [ADDED 2026-11-05, v3.90.0] The HACS review of 2026-11-05: a save removes only what LIBI created itself, and only once
# the user confirms (the panel asks; save_helpers.save answers for the user). An entry opened from Home Assistant that
# leaves the canvas any other way than Delete NET leaves the project, and stays in Home Assistant as it is.
def _automations(libi) -> list:
    return yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8")) or []


def _project(libi, slug="p") -> dict:
    return json.loads((libi / "libi" / f"{slug}.libi").read_text(encoding="utf-8"))


async def test_an_automation_opened_from_home_assistant_is_never_deleted_by_a_save(hass, libi, hass_ws_client,
                                                                                   hass_client):
    """Frenck's case: a hand-written automation opened in LIBI and saved once, then gone from the canvas (Clear all
    nets, undo, the AI chat's Replace) - the next SAVE & COMPILE deleted it from automations.yaml."""
    await home_assistant_files(hass, libi, automations=[HAND, AUTO])
    client, http = await hass_ws_client(hass), await hass_client()
    net = await _opened(client)
    edited = json.loads(json.dumps(net).replace("light.x", "light.y"))
    plan, done = await save(client, http, [edited])
    assert [(op["key"], op["new"]) for op in plan["upserts"]] == [("a1", False)] and done["status"] == "ok", done
    assert _project(libi)["owned"]["automations"] == ["a1"] and _project(libi)["made"]["automations"] == []
    # Clear all nets, then SAVE & COMPILE: nothing is deleted - the automation leaves the project, and that is said.
    plan, done = await save(client, http, [])
    assert plan["removals"] == []
    assert plan["released"] == [{"domain": "automation", "key": "a1", "label": 'automation "Lamp" (a1)'}]
    assert done["status"] == "ok" and done["released"] == ['automation "Lamp" (a1)'], done
    assert done["message"].endswith('Left in Home Assistant as it is, and no longer in this project: automation "Lamp" '
                                    '(a1).'), done["message"]
    assert [a["id"] for a in _automations(libi)] == ["hand1", "a1"]
    assert _automations(libi)[1]["actions"][0]["target"] == {"entity_id": "light.y"}
    assert hass.states.get("automation.lamp") is not None
    assert _project(libi)["owned"]["automations"] == []
    # It is the user's again: no later save offers it, or says it again.
    plan, done = await save(client, http, [])
    assert (plan["removals"], plan["released"], done["released"]) == ([], [], [])


async def test_an_automation_loaded_over_another_in_the_same_net_keeps_the_first(hass, libi, hass_ws_client,
                                                                                 hass_client):
    hall = dict(AUTO, id="a2", alias="Hall")
    await home_assistant_files(hass, libi, automations=[AUTO, hall])
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await save(client, http, [json.loads(json.dumps(await _opened(client)).replace("light.x", "light.z"))])
    assert done["status"] == "ok", done
    plan, done = await save(client, http, [await _opened(client, "a2")])
    assert plan["removals"] == [] and [r["key"] for r in plan["released"]] == ["a1"], plan
    assert [a["id"] for a in _automations(libi)] == ["a1", "a2"]
    assert _project(libi)["owned"]["automations"] == ["a2"]


async def test_what_libi_made_is_removed_only_once_the_user_confirms(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi, automations=[HAND])
    client, http = await hass_ws_client(hass), await hass_client()
    plan, _done = await save(client, http, [_net(hass)])
    assert [(op["key"], op["new"]) for op in plan["upserts"]] == [("a1", True)]
    assert _project(libi)["made"]["automations"] == ["a1"]
    # Asked, and Cancel: nothing is sent, nothing is recorded.
    plan, done = await save(client, http, [], removals="cancel")
    assert done is None and plan["removals"] == [{"domain": "automation", "key": "a1", "label": 'automation "Lamp" (a1)'}]
    assert [a["id"] for a in _automations(libi)] == ["hand1", "a1"] and _project(libi)["owned"]["automations"] == ["a1"]
    # Keep in Home Assistant: nothing is deleted, the automation leaves the project, and no later save asks again.
    plan, done = await save(client, http, [], removals="keep")
    assert done["status"] == "ok" and done["released"] == ['automation "Lamp" (a1)'], done
    assert [a["id"] for a in _automations(libi)] == ["hand1", "a1"] and hass.states.get("automation.lamp") is not None
    assert (_project(libi)["owned"]["automations"], _project(libi)["made"]["automations"]) == ([], [])
    plan, _done = await save(client, http, [])
    assert (plan["removals"], plan["released"]) == ([], [])


async def test_what_libi_made_and_then_left_to_the_user_is_never_offered_again(hass, libi, hass_ws_client, hass_client):
    """Remove from LIBI only lets go of what LIBI made: opened again later, it is the user's, and a save never deletes it."""
    await home_assistant_files(hass, libi, automations=[HAND])
    client, http = await hass_ws_client(hass), await hass_client()
    hand = await _opened(client, "hand1", "n_hand")
    await save(client, http, [_net(hass), hand])
    assert (_project(libi)["owned"]["automations"], _project(libi)["made"]["automations"]) == (["a1", "hand1"], ["a1"])
    assert (await _removed(client, net_id="n_a1", mode="kept", domain="automation", key="a1"))["ok"]
    assert (_project(libi)["owned"]["automations"], _project(libi)["made"]["automations"]) == (["hand1"], [])
    _plan, done = await save(client, http, [hand, await _opened(client)])
    assert done["status"] == "ok" and _project(libi)["owned"]["automations"] == ["a1", "hand1"], done
    plan, _done = await save(client, http, [])
    assert plan["removals"] == [] and [r["key"] for r in plan["released"]] == ["a1", "hand1"], plan
    assert [a["id"] for a in _automations(libi)] == ["hand1", "a1"]


async def test_a_removal_home_assistant_refused_is_asked_again(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    hall = dict(AUTO, id="a2", alias="Hall")
    client, http = await hass_ws_client(hass), await hass_client()
    await save(client, http, [_net(hass), _net(hass, hall)])
    _plan, done = await save(client, http, [_net(hass)], refuse=("a2",))
    assert done["status"] == "error" and "a2" in [a["id"] for a in _automations(libi)], done
    assert _project(libi)["made"]["automations"] == ["a1", "a2"]
    plan, done = await save(client, http, [_net(hass)])
    assert [r["key"] for r in plan["removals"]] == ["a2"] and done["status"] == "ok", done
    assert [a["id"] for a in _automations(libi)] == ["a1"]


async def test_what_a_project_from_before_3_90_saved_is_never_removed_by_a_save(hass, libi, hass_ws_client,
                                                                                hass_client):
    """A project of an older LIBI has no record of what it created, so it is all treated as the user's: a save never
    removes it. A panel from before the update does not say what it created either."""
    await home_assistant_files(hass, libi, automations=[AUTO])
    (libi / "libi").mkdir(exist_ok=True)
    (libi / "libi" / "p.libi").write_text(json.dumps({"libi_project": 1, "slug": "p", "name": "P", "nets": [],
                                                      "owned": {"automations": ["a1"]}}), encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [])
    assert plan["removals"] == [] and [r["key"] for r in plan["released"]] == ["a1"] and done["status"] == "ok", done
    assert [a["id"] for a in _automations(libi)] == ["a1"]
    hall = dict(AUTO, id="a2", alias="Hall")
    planned = (await send(client, {"type": "libi/compile_project", "slug": "p", "nets": [_net(hass, hall)]}))["result"]
    assert (await http.post("/api/config/automation/config/a2", json=planned["upserts"][0]["config"])).status == 200
    old_panel = await send(client, {"type": "libi/save_done", "slug": "p", "nets": [_net(hass, hall)],
                                    "done": [{"domain": "automation", "key": "a2", "op": "upsert"}],
                                    "stamp": planned["stamp"]})
    assert old_panel["result"]["status"] == "ok", old_panel
    assert _project(libi)["made"]["automations"] == []
    plan, _done = await save(client, http, [])
    assert plan["removals"] == [] and [r["key"] for r in plan["released"]] == ["a2"]


async def test_an_unreadable_project_saves_nothing(hass, libi, writes, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    (libi / "libi").mkdir(exist_ok=True)
    (libi / "libi" / "p.libi").write_text("{not json", encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass)])
    assert done is None and plan["errors"] == ["the project p could not be read", "nothing was saved"], plan
    assert (libi / "libi" / "p.libi").read_text(encoding="utf-8") == "{not json" and writes == []
    assert _automations(libi) == []


# [ADDED 2026-11-05, v3.90.0] The HACS review: a NET never takes an entry Home Assistant holds for someone else. A script
# NET called "Good night" replaced the user's script.good_night; a NET drawn in LIBI is n1 in every project.
GOOD_NIGHT = {"alias": "Good night", "sequence": [{"delay": 1}]}


def _script_net(hass, name="Good night", nid="n1"):
    net = _net(hass)
    net.pop("ha_id", None)
    net.update(id=nid, level="script", name=name)
    return net


async def test_a_script_net_never_replaces_a_script_of_the_same_name(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi, scripts={"good_night": GOOD_NIGHT})
    client, http = await hass_ws_client(hass), await hass_client()
    net = _script_net(hass)
    plan, done = await save(client, http, [net])
    assert [(op["domain"], op["key"], op["new"]) for op in plan["upserts"]] == [("script", "good_night_2", True)]
    assert done["status"] == "ok", done
    scripts = yaml.safe_load((libi / "scripts.yaml").read_text(encoding="utf-8"))
    assert scripts["good_night"] == GOOD_NIGHT and sorted(scripts) == ["good_night", "good_night_2"]
    assert _project(libi)["owned"]["scripts"] == ["good_night_2"]
    # The next save finds the same key, so nothing changes; and deleting the NET deletes its own script.
    plan, _done = await save(client, http, [net])
    assert (plan["upserts"], plan["unchanged"]) == ([], 1)
    info = (await send(client, {"type": "libi/net_delete_plan", "slug": "p", "net_id": "n1", "nets": [net]}))["result"]
    assert (info["domain"], info["key"], info["in_ha"]) == ("script", "good_night_2", True)
    # Nor one another project saved.
    plan, _done = await save(client, http, [_script_net(hass)], slug="q")
    assert [op["key"] for op in plan["upserts"]] == ["good_night_3"]
    assert yaml.safe_load((libi / "scripts.yaml").read_text(encoding="utf-8"))["good_night"] == GOOD_NIGHT


async def test_a_net_drawn_in_libi_never_replaces_another_projects_automation(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    drawn = _net(hass)
    drawn.pop("ha_id", None)
    drawn["id"] = "n1"
    client, http = await hass_ws_client(hass), await hass_client()
    plan, _done = await save(client, http, [drawn], slug="p")
    assert [op["key"] for op in plan["upserts"]] == ["n1"]
    other = json.loads(json.dumps(drawn).replace("light.x", "light.other"))
    plan, done = await save(client, http, [other], slug="q")
    assert [(op["key"], op["config"]["id"]) for op in plan["upserts"]] == [("n1_2", "n1_2")] and done["status"] == "ok"
    by_id = {a["id"]: a for a in _automations(libi)}
    assert by_id["n1"]["actions"][0]["target"] == {"entity_id": "light.x"}
    assert by_id["n1_2"]["actions"][0]["target"] == {"entity_id": "light.other"}
    plan, _done = await save(client, http, [other], slug="q")
    assert (plan["upserts"], plan["unchanged"]) == ([], 1)
    info = (await send(client, {"type": "libi/net_delete_plan", "slug": "q", "net_id": "n1", "nets": [other]}))["result"]
    assert (info["key"], info["in_ha"]) == ("n1_2", True)


async def test_the_plan_refuses_an_entry_the_project_neither_owns_nor_opened(hass, libi):
    """Whatever chose the key: the plan itself does not change an entry this project did not save or open."""
    await home_assistant_files(hass, libi, automations=[HAND])
    entry = {"net": {"id": "n9"}, "label": 'NET 1 "x"', "domain": "automation", "key": "hand1", "linked": False,
             "config": {"id": "hand1", "alias": "Mine now", "triggers": [], "actions": []}}
    plan = await hass.async_add_executor_job(ws._plan_save_sync, hass, "p", [entry])
    assert plan == {"ok": False, "errors": ['NET 1 "x": automation "Hand written" (hand1) is already in Home Assistant, '
                                            "and this project did not save it - it is not changed", "nothing was saved"]}
    assert _automations(libi) == [HAND]


async def test_a_page_from_before_the_update_cannot_write(hass, libi, writes, hass_ws_client):
    (libi / "automations.yaml").write_text(_dump([AUTO]), encoding="utf-8")
    client = await hass_ws_client(hass)
    for msg in ({"type": "libi/save_automation", "slug": "p", "name": "P", "nets": [_net(hass)]},
                {"type": "libi/delete_automation", "automation_id": "a1"}):
        res = await send(client, msg)
        assert res["success"] is False and res["error"]["code"] == "outdated_panel", res
        assert res["error"]["message"].startswith("LIBI was updated: reload this page"), res
    assert yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8")) == [AUTO]
    assert writes == []


async def test_the_file_of_libi_before_3_5_is_left_alone(hass, libi, writes, caplog):
    """The HACS review: LIBI never writes libi_automations.yaml again; the log says when it still holds automations."""
    legacy = _dump([AUTO])
    (libi / "libi_automations.yaml").write_text(legacy, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        await hass.async_add_executor_job(ws.legacy_file_note_sync, hass)
    assert "still holds 1 automation(s). LIBI no longer uses or changes it" in caplog.text
    assert (libi / "libi_automations.yaml").read_text(encoding="utf-8") == legacy
    # Emptied by an earlier LIBI: nothing to say.
    caplog.clear()
    (libi / "libi_automations.yaml").write_text("[]\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        await hass.async_add_executor_job(ws.legacy_file_note_sync, hass)
    assert "libi_automations.yaml" not in caplog.text
    assert writes == []


async def test_project_round_trip(hass, libi, hass_ws_client, hass_client):
    """Create, save, list, open (rebuilt from automations.yaml on the event loop) and delete."""
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    await client.send_json_auto_id({"type": "libi/project_create", "name": "Garden Pool"})
    slug = (await client.receive_json())["result"]["slug"]
    net = _net(hass)
    net["ha_id"] = "a1"
    _plan, done = await save(client, http, [net], slug=slug)
    assert done["saved"] is True

    await client.send_json_auto_id({"type": "libi/project_list"})
    listed = (await client.receive_json())["result"]["projects"]
    assert [p["slug"] for p in listed] == [slug]

    await client.send_json_auto_id({"type": "libi/project_open", "slug": slug})
    opened = (await client.receive_json())["result"]
    assert opened["stats"]["reloaded"] == 1
    assert opened["nets"][0]["source"] == "ha"

    await client.send_json_auto_id({"type": "libi/project_delete", "slug": slug})
    assert (await client.receive_json())["success"]
    # Deleting a project never deletes what it compiled.
    assert "a1" in (libi / "automations.yaml").read_text(encoding="utf-8")


async def test_get_automation_round_trips(hass, libi, hass_ws_client):
    (libi / "automations.yaml").write_text(_dump([AUTO]), encoding="utf-8")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/get_automation", "automation_id": "a1"})
    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["verify"]["ok"] is True, res["result"]["verify"]
    # Not loaded into a NET: no version is recorded.
    assert res["result"]["versions"] == {} and not (libi / "libi" / "default.versions.json").exists()


# [ADDED 2026-11-04, v3.85.0] Deleting a NET asks what becomes of its entry in Home Assistant - the user's rule: deleted
# completely, or V1, the original as it was before LIBI changed it, put back; or left as it is now. The panel makes the
# call to Home Assistant's config API, libi/net_removed lets the project go of the NET.
ORIGINAL = {"id": "a1", "alias": "Lamp", "trigger": [{"platform": "state", "entity_id": "binary_sensor.door", "to": "on"}],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.x"}}], "mode": "single"}


async def _opened(client, auto_id="a1", net_id="n1", slug="p") -> dict:
    """The automation loaded into a NET from the list, as the panel loads it: V1 and V2 are recorded."""
    res = await send(client, {"type": "libi/get_automation", "automation_id": auto_id, "slug": slug, "net_id": net_id})
    assert res["success"], res
    return {**res["result"]["net"], "id": net_id}


async def _removed(client, **fields) -> dict:
    res = await send(client, {"type": "libi/net_removed", "slug": "p", **fields})
    assert res["success"], res
    return res["result"]


async def test_deleting_a_net_completely_deletes_its_automation(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi, automations=[AUTO])
    client, http = await hass_ws_client(hass), await hass_client()
    net = await _opened(client)
    await save(client, http, [net])
    planned = await send(client, {"type": "libi/net_delete_plan", "slug": "p", "net_id": "n1", "nets": [net]})
    info = planned["result"]
    assert (info["domain"], info["key"], info["in_ha"], info["errors"]) == ("automation", "a1", True, [])
    assert info["original"] == {"v": 1, "config": AUTO}
    stamp = (await send(client, {"type": "libi/compile_project", "slug": "p", "nets": []}))["result"]["stamp"]
    assert (await http.delete("/api/config/automation/config/a1")).status == 200
    assert await _removed(client, net_id="n1", mode="deleted", domain="automation", key="a1", stamp=stamp) == {
        "ok": True, "errors": []}
    assert yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8")) == []
    assert hass.states.get("automation.lamp") is None
    project = json.loads((libi / "libi" / "p.libi").read_text(encoding="utf-8"))
    assert (project["nets"], project["owned"]["automations"]) == ([], [])
    assert (await send(client, {"type": "libi/net_versions", "slug": "p", "net_id": "n1"}))["result"]["versions"] == []


async def test_deleting_a_net_back_to_v1_puts_the_original_back_as_it_was(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi, automations=[ORIGINAL])
    client, http = await hass_ws_client(hass), await hass_client()
    net = await _opened(client)
    edited = json.loads(json.dumps(net).replace("light.x", "light.y"))
    _plan, done = await save(client, http, [edited])
    assert done["status"] == "ok", done
    assert yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))[0] != ORIGINAL
    info = (await send(client, {"type": "libi/net_delete_plan", "slug": "p", "net_id": "n1", "nets": [edited]}))["result"]
    assert info["original"]["config"] == ORIGINAL
    stamp = (await send(client, {"type": "libi/compile_project", "slug": "p", "nets": []}))["result"]["stamp"]
    assert (await http.post("/api/config/automation/config/a1", json=info["original"]["config"])).status == 200
    assert (await _removed(client, net_id="n1", mode="restored", domain="automation", key="a1", stamp=stamp))["ok"]
    # Back as it was: LIBI sends the original exactly, and Home Assistant writes it in today's spelling (trigger is
    # triggers, service is action), as its own editor does. No longer the project's, so a save leaves it.
    restored = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert len(restored) == 1 and same_config(restored[0], ORIGINAL), restored
    plan, _done = await save(client, http, [])
    assert plan["removals"] == []
    assert same_config(yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))[0], ORIGINAL)


async def test_a_net_deleted_whose_automation_home_assistant_kept_is_said(hass, libi, monkeypatch, hass_ws_client,
                                                                           hass_client):
    """The project lets go of the NET, but an automation Home Assistant has not removed is said, not hidden (RULE 10)."""
    await home_assistant_files(hass, libi, automations=[AUTO])
    monkeypatch.setattr(ws, "RELOAD_WAIT_SECONDS", 0.5)
    client = await hass_ws_client(hass)
    result = await _removed(client, net_id="n_a1", mode="deleted", domain="automation", key="a1")
    assert result["ok"] is False
    assert result["errors"][0].startswith("automation a1: Home Assistant has not removed it within"), result


async def test_removing_a_net_from_libi_only_keeps_its_automation(hass, libi, hass_ws_client, hass_client):
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    await save(client, http, [_net(hass)])
    assert (await _removed(client, net_id="n_a1", mode="kept", domain="automation", key="a1")) == {"ok": True, "errors": []}
    plan, _done = await save(client, http, [])
    assert plan["removals"] == []
    assert [a["id"] for a in yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))] == ["a1"]
    assert hass.states.get("automation.lamp") is not None


async def test_the_delete_plan_of_a_draft_has_nothing_in_home_assistant(hass, libi, hass_ws_client):
    client = await hass_ws_client(hass)
    draft = {"id": "n_draft", "name": "Draft", "rungs": []}
    info = (await send(client, {"type": "libi/net_delete_plan", "slug": "p", "net_id": "n_draft", "nets": [draft]}))["result"]
    assert (info["domain"], info["key"], info["in_ha"], info["original"]) == ("", "", False, None)
    res = await send(client, {"type": "libi/net_delete_plan", "slug": "p", "net_id": "nope", "nets": [draft]})
    assert res["success"] is False and res["error"]["code"] == "not_found"


# [ADDED v3.77.0] The local variables of a NET, offered when the NET is deleted (libi/net_helpers).
GARDEN = {
    "id": "garden", "alias": "Garden",
    "triggers": [{"trigger": "state", "entity_id": "input_boolean.in_a_group", "to": "on"}],
    "conditions": [
        {"condition": "template", "value_template": day_bits_template("input_number.garden_days")},
        {"condition": "template", "value_template": "{{ states.input_number.shared_litres.state | int(0) > 0 }}"},
        {"condition": "state", "entity_id": "input_boolean.used_by_script", "state": "on"},
        {"condition": "state", "entity_id": "input_boolean.on_another_net", "state": "on"},
        {"condition": "state", "entity_id": "input_boolean.in_another_project", "state": "on"},
        {"condition": "numeric_state", "entity_id": "input_number.yaml_days", "above": 0},
    ],
    "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}],
}
OTHER = {"id": "other", "alias": "Other", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door"}],
         "conditions": [{"condition": "template", "value_template": "{{ states.input_number.shared_litres.state | int(0) > 5 }}"}],
         "actions": [{"action": "light.turn_off", "target": {"entity_id": "light.x"}}]}
SCRIPTS = {"water": {"alias": "Water", "sequence": [
    {"action": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.used_by_script"}}]}}
LAMP = {"id": "n_lamp", "name": "Lamp", "rungs": [{"id": "r1", "elements": [
    {"id": "e1", "type": "contact_no", "label": "input_boolean.on_another_net"}]}]}
POOL = {"libi_project": 1, "slug": "pool", "name": "Pool", "owned": {}, "nets": [
    {"id": "n_pool", "name": "Pump", "rungs": [{"id": "r1", "elements": [
        {"id": "e1", "type": "coil_s", "label": "input_boolean.in_another_project"}]}]}]}


async def _make_helpers(hass, client) -> None:
    """Helpers made in Home Assistant's UI (storage, the kind LIBI may delete), one written in YAML, and a group."""
    assert await async_setup_component(hass, "input_number", {"input_number": {"yaml_days": {"min": 0, "max": 255}}})
    assert await async_setup_component(hass, "input_boolean", {})
    for msg in ({"type": "input_number/create", "name": "garden days", "min": 0, "max": 255},
                {"type": "input_number/create", "name": "shared litres", "min": 0, "max": 500},
                {"type": "input_boolean/create", "name": "used by script"},
                {"type": "input_boolean/create", "name": "on another net"},
                {"type": "input_boolean/create", "name": "in another project"},
                {"type": "input_boolean/create", "name": "in a group"},
                {"type": "input_boolean/create", "name": "pump"},
                {"type": "input_boolean/create", "name": "only in file"}):
        await client.send_json_auto_id(msg)
        assert (await client.receive_json())["success"], msg
    assert await async_setup_component(hass, "group", {"group": {"garden_group": {"entities": ["input_boolean.in_a_group"]}}})
    await hass.async_block_till_done()


async def _net_helpers(client, net, **fields) -> dict:
    await client.send_json_auto_id({"type": "libi/net_helpers", "net": net, **fields})
    res = await client.receive_json()
    assert res["success"], res
    return res["result"]


async def test_the_local_variables_of_a_net_are_the_helpers_nothing_else_uses(hass, libi, hass_ws_client):
    # What runs is the automation in the file, which still reads a helper the drawing no longer shows (an edit not saved).
    saved = copy.deepcopy(GARDEN)
    saved["conditions"].append({"condition": "state", "entity_id": "input_boolean.only_in_file", "state": "on"})
    (libi / "automations.yaml").write_text(_dump([OTHER, saved]), encoding="utf-8")
    (libi / "scripts.yaml").write_text(_dump(SCRIPTS), encoding="utf-8")
    (libi / "libi").mkdir(exist_ok=True)
    (libi / "libi" / "pool.libi").write_text(json.dumps(POOL), encoding="utf-8")
    client = await hass_ws_client(hass)
    await _make_helpers(hass, client)
    # Its entity_id renamed in Home Assistant: the id the delete command takes is still the helper's own, "pump".
    er.async_get(hass).async_update_entity("input_boolean.pump", new_entity_id="input_boolean.night_pump")
    await hass.async_block_till_done()
    net = _net(hass, GARDEN)
    net["vars"] = ["input_boolean.night_pump"]  # made for this NET in the variables bar, not placed yet

    result = await _net_helpers(client, net, nets=[net, LAMP], slug="garden", automation_id="garden")
    assert result["error"] == ""
    assert result["helpers"] == [
        {"entity_id": "input_boolean.night_pump", "name": "pump", "domain": "input_boolean", "item_id": "pump"},
        {"entity_id": "input_boolean.only_in_file", "name": "only in file", "domain": "input_boolean", "item_id": "only_in_file"},
        {"entity_id": "input_number.garden_days", "name": "garden days", "domain": "input_number", "item_id": "garden_days"}]
    kept = {k["entity_id"]: k["reason"] for k in result["kept"]}
    assert kept == {
        "input_boolean.in_a_group": "used by garden_group",
        "input_boolean.in_another_project": 'used by NET "Pump" of project "Pool"',
        "input_boolean.on_another_net": 'used by NET "Lamp" on the canvas',
        "input_boolean.used_by_script": 'used by script "Water"',
        # Read in a template as states.input_number.shared_litres.state: still a use.
        "input_number.shared_litres": 'used by automation "Other"',
        "input_number.yaml_days": "written in YAML, so it cannot be deleted from here",
    }, kept

    # Its own automation stays when nothing deletes it, and then it uses every one of them.
    result = await _net_helpers(client, net, nets=[LAMP], slug="garden")
    assert [h["entity_id"] for h in result["helpers"]] == ["input_boolean.night_pump"]
    assert all(k["reason"] == 'used by automation "Garden"' for k in result["kept"]
               if k["entity_id"] in ("input_number.garden_days", "input_boolean.in_a_group"))

    # The id given is the one Home Assistant's own delete command takes.
    for msg in ({"type": "input_number/delete", "input_number_id": "garden_days"},
                {"type": "input_boolean/delete", "input_boolean_id": "pump"}):
        await client.send_json_auto_id(msg)
        assert (await client.receive_json())["success"], msg
    await hass.async_block_till_done()
    assert hass.states.get("input_number.garden_days") is None
    assert hass.states.get("input_boolean.night_pump") is None


async def test_an_automation_still_loaded_keeps_its_variables(hass, libi, hass_ws_client):
    """Not in automations.yaml (a package, or a reload that failed), but running: Home Assistant's index says so."""
    client = await hass_ws_client(hass)
    await _make_helpers(hass, client)
    pump = {"id": "pkg", "alias": "Pump at night",
            "triggers": [{"trigger": "state", "entity_id": "input_boolean.pump", "to": "on"}],
            "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}]}
    assert await async_setup_component(hass, "automation", {"automation": [pump]})
    await hass.async_block_till_done()
    net = _net(hass, pump)
    result = await _net_helpers(client, net)
    assert result["helpers"] == []
    assert result["kept"] == [{"entity_id": "input_boolean.pump", "name": "pump", "reason": "used by Pump at night"}]
    # The automation being deleted is the one user that does not count.
    result = await _net_helpers(client, net, automation_id="pkg")
    assert [h["entity_id"] for h in result["helpers"]] == ["input_boolean.pump"]


@pytest.mark.parametrize("broken", ["scripts.yaml", "libi/broken.libi"])
async def test_no_variable_is_offered_when_a_user_cannot_be_read(hass, libi, hass_ws_client, broken):
    (libi / "libi").mkdir(exist_ok=True)
    (libi / broken).write_text("{not: [valid\n", encoding="utf-8")
    client = await hass_ws_client(hass)
    await _make_helpers(hass, client)
    result = await _net_helpers(client, _net(hass, GARDEN), automation_id="garden")
    assert result["helpers"] == []
    assert result["error"], result


# [ADDED 2026-11-04, v3.86.0] Names in LIBI only - the user's request: an entity Home Assistant cannot rename (no unique
# ID), or one the user names in LIBI only, gets a name LIBI shows wherever it shows the entity. Home Assistant is not
# changed; the names are config/libi/local_names.json, one file for every project.
async def test_a_fresh_install_has_no_local_names_and_writes_nothing(hass, libi, writes, hass_ws_client):
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/local_names"})
    assert res["success"] and res["result"] == {"names": {}}
    assert writes == [] and not (libi / "libi" / "local_names.json").exists()


async def test_a_local_name_is_kept_shown_and_taken_away(hass, libi, writes, hass_ws_client):
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/local_name_set", "entity_id": "input_number.kmvt_mym", "name": "  Water	litres  "})
    assert res["success"], res
    assert res["result"]["names"] == {"input_number.kmvt_mym": "Water litres"}
    stored = json.loads((libi / "libi" / "local_names.json").read_text(encoding="utf-8"))
    assert stored == {"libi_local_names": 1, "names": {"input_number.kmvt_mym": "Water litres"}}
    res = await send(client, {"type": "libi/local_names"})
    assert res["result"]["names"] == {"input_number.kmvt_mym": "Water litres"}
    # The same name again changes nothing, so nothing is written.
    assert writes == ["local_names.json"]
    await send(client, {"type": "libi/local_name_set", "entity_id": "input_number.kmvt_mym", "name": "Water litres"})
    assert writes == ["local_names.json"]
    # An empty name takes it away; taking away a name nobody gave writes nothing.
    res = await send(client, {"type": "libi/local_name_set", "entity_id": "input_number.kmvt_mym", "name": " "})
    assert res["success"] and res["result"]["names"] == {}
    assert json.loads((libi / "libi" / "local_names.json").read_text(encoding="utf-8"))["names"] == {}
    await send(client, {"type": "libi/local_name_set", "entity_id": "light.none", "name": ""})
    assert writes == ["local_names.json", "local_names.json"]


async def test_a_local_name_never_reaches_home_assistant(hass, libi, hass_ws_client):
    reg = er.async_get(hass)
    reg.async_get_or_create("light", "test", "lamp-1", suggested_object_id="lamp", original_name="Lamp")
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/local_name_set", "entity_id": "light.lamp", "name": "Hall.Lamp"})
    assert res["success"], res
    assert reg.async_get("light.lamp").name is None and reg.async_get("light.lamp").original_name == "Lamp"
    assert not (libi / "automations.yaml").exists() and not (libi / "scripts.yaml").exists()


async def test_a_local_names_file_that_cannot_be_read_is_never_written_over(hass, libi, writes, hass_ws_client):
    (libi / "libi").mkdir(exist_ok=True)
    path = libi / "libi" / "local_names.json"
    path.write_text("{not json", encoding="utf-8")
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/local_names"})
    assert res["success"] is False and res["error"]["code"] == "read_failed"
    res = await send(client, {"type": "libi/local_name_set", "entity_id": "light.x", "name": "Mine"})
    assert res["success"] is False and res["error"]["code"] == "read_failed"
    assert path.read_text(encoding="utf-8") == "{not json" and writes == []


@pytest.mark.parametrize(("entity_id", "name", "code"), [
    ("../escape", "x", "invalid_entity_id"),
    ("light", "x", "invalid_entity_id"),
    ("Light.X", "x", "invalid_entity_id"),
    ("light.x", "n" * 101, "name_too_long"),
])
async def test_a_local_name_for_no_entity_or_too_long_is_refused(hass, libi, writes, hass_ws_client, entity_id, name, code):
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/local_name_set", "entity_id": entity_id, "name": name})
    assert res["success"] is False and res["error"]["code"] == code
    assert writes == []


# [ADDED 2026-11-04, v3.87.0] The phones and the action that reaches each. The user's train reminder had a phone's notify
# entity (notify.sm_s918b) as its action: the MOVE TTS block's entity picker listed the phone by that entity, LIBI saved
# it, Home Assistant accepted it, and at its time it failed with "unknown action" - nothing was said.
def _phones(hass):
    """The phones as the Companion app registers them: a config entry with the device's name, a notify entity, and a
    notify action of that name. Two of them were registered under one name, so they share one action."""
    reg = er.async_get(hass)
    hass.states.async_set("person.guy", "home", {"friendly_name": "Guy", "user_id": "u_guy"})
    hass.states.async_set("person.yulia", "home", {"friendly_name": "Yulia", "user_id": "u_yulia"})
    for device, object_id, user, model, system in (
            ("SM-S918B", "sm_s918b", "u_guy", "SM-S918B", "Android"),
            ("SM-S938B", "sm_s938b", "u_yulia", "SM-S938B", "Android"),
            ("Guy iPhone", "guy_iphone", "u_guy", "iPhone 15", "iOS"),
            ("SM-N985F", "sm_n985f", "u_guy", "SM-N985F", "Android"),
            ("SM-N985F", "sm_n985f_2", "u_guy", "SM-N985F", "Android")):
        entry = MockConfigEntry(domain="mobile_app", data={
            "device_name": device, "webhook_id": f"hook-{object_id}", "user_id": user, "manufacturer": "samsung",
            "model": model, "os_name": system, "secret": f"do-not-show-{object_id}"})
        entry.add_to_hass(hass)
        reg.async_get_or_create("notify", "mobile_app", object_id, suggested_object_id=object_id, config_entry=entry)
        hass.states.async_set(f"notify.{object_id}", "unknown", {"friendly_name": device})
    for service in ("mobile_app_sm_s918b", "mobile_app_sm_s938b", "mobile_app_guy_iphone", "mobile_app_sm_n985f",
                    "persistent_notification", "send_message"):
        async_mock_service(hass, "notify", service)


def _reminder(action, key="train", alias="Train reminder"):
    return {"id": key, "alias": alias, "description": "", "mode": "single",
            "triggers": [{"trigger": "state", "entity_id": "input_boolean.train_time", "to": "on"}], "conditions": [],
            "actions": [{"action": action, "data": {"message": "TTS", "data": {
                "tts_text": "Time to go to the train", "media_stream": "alarm_stream"}}}]}


async def test_the_phones_and_the_action_that_reaches_each(hass, libi, hass_ws_client):
    _phones(hass)
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/phones"})
    assert res["success"], res
    phones = res["result"]["phones"]
    assert [p["entity_id"] for p in phones] == ["notify.guy_iphone", "notify.sm_n985f", "notify.sm_n985f_2",
                                                "notify.sm_s918b", "notify.sm_s938b"]
    by_id = {p["entity_id"]: p for p in phones}
    assert by_id["notify.sm_s938b"] == {"entity_id": "notify.sm_s938b", "service": "notify.mobile_app_sm_s938b",
                                        "name": "SM-S938B", "owner": "Yulia", "device": "samsung SM-S938B",
                                        "speaks": True, "shared": False}
    assert by_id["notify.sm_s918b"]["service"] == "notify.mobile_app_sm_s918b" and by_id["notify.sm_s918b"]["owner"] == "Guy"
    # An iPhone shows the word TTS: it does not read a message aloud.
    assert by_id["notify.guy_iphone"]["speaks"] is False
    # Two phones under one name have one action, which reaches only one of them.
    assert by_id["notify.sm_n985f"]["shared"] is True and by_id["notify.sm_n985f_2"]["shared"] is True
    assert by_id["notify.sm_n985f"]["service"] == by_id["notify.sm_n985f_2"]["service"] == "notify.mobile_app_sm_n985f"
    # Never a webhook id or a secret of the app.
    assert "hook-" not in json.dumps(res) and "do-not-show" not in json.dumps(res)


async def test_no_phones_is_an_empty_list(hass, libi, hass_ws_client):
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/phones"})
    assert res["success"] and res["result"] == {"phones": []}


@pytest.mark.parametrize(("action", "said"), [
    ("notify.sm_s918b", "notify.sm_s918b is the notify entity of the phone SM-S918B, not an action: Home Assistant cannot "
                        "send with it. The phone's action is notify.mobile_app_sm_s918b - pick the phone again in the "
                        "MOVE block."),
    ("notify.sm_n985f_2", "notify.sm_n985f_2 is the notify entity of a phone, not an action, and another phone is "
                          "registered under the same name in the Companion app: their one action, "
                          "notify.mobile_app_sm_n985f, reaches only one of them. Give one of the phones another name in "
                          "the app."),
    ("notify.mobile_app_mi_9t_pro", "notify.mobile_app_mi_9t_pro is not an action in this Home Assistant - a phone no "
                                    "longer registered in the Companion app? Nothing would be sent."),
])
async def test_a_notify_action_home_assistant_does_not_have_is_not_saved(hass, libi, writes, hass_ws_client,
                                                                         hass_client, action, said):
    """Home Assistant's own validator accepts it - it does not check that an action exists - so LIBI does."""
    _phones(hass)
    calls = await home_assistant_files(hass, libi)
    before = (libi / "automations.yaml").read_text(encoding="utf-8")
    assert await ai.validate_with_home_assistant(hass, "automation", _reminder(action)) is None
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass, _reminder(action))])
    assert done is None and plan["ok"] is False
    assert plan["errors"] == [f'NET 1 "Train reminder": {said}']
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before
    assert calls["automation"] == 0 and writes == []


async def test_the_phones_action_is_saved(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass, _reminder("notify.mobile_app_sm_s918b"))])
    assert plan["ok"] is True and done["saved"] is True and done["status"] == "ok", (plan, done)
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert [a["actions"][0]["action"] for a in data] == ["notify.mobile_app_sm_s918b"]


async def test_an_automation_not_changed_is_not_stopped_by_its_own_notify_action(hass, libi, hass_ws_client, hass_client):
    """An automation that already sends to a phone no longer in the Companion app is not sent again, so it does not stop
    a save of another NET - it is the user's, as it is."""
    _phones(hass)
    old = _reminder("notify.mobile_app_mi_9t_pro", key="old", alias="Old phone")
    await home_assistant_files(hass, libi, automations=[old])
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass, old), _net(hass)])
    assert plan["ok"] is True, plan
    assert [op["key"] for op in plan["upserts"]] == ["a1"]
    assert done["saved"] is True and done["status"] == "ok", done
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert [a for a in data if a["id"] == "old"][0]["actions"][0]["action"] == "notify.mobile_app_mi_9t_pro"


async def test_every_notify_action_of_an_entry_is_checked_the_nested_ones_too(hass, libi):
    _phones(hass)
    script = {"sequence": [
        {"if": [{"condition": "state", "entity_id": "person.guy", "state": "home"}],
         "then": [{"repeat": {"count": 2, "sequence": [{"parallel": [{"action": "notify.gone_one"}]}]}}],
         "else": [{"choose": [{"conditions": [], "sequence": [{"service": "notify.gone_two"}]}],
                   "default": [{"sequence": [{"action": "notify.sm_s938b"}]}]}]},
        # A notification's own buttons are "actions" too: they are not actions of the script.
        {"action": "notify.mobile_app_sm_s938b", "data": {"message": "Open?", "data": {
            "actions": [{"action": "notify.not_a_step", "title": "Open"}]}}},
        {"action": "light.turn_on", "target": {"entity_id": "light.x"}},
        {"action": "notify.gone_one"}]}
    problems = ai.notify_action_problems(hass, "script", script)
    assert [p.split(" ")[0] for p in problems] == ["notify.gone_one", "notify.gone_two", "notify.sm_s938b"]
    assert ai.notify_action_problems(hass, "automation", {"action": [{"action": "notify.gone_one"}]})[0].startswith(
        "notify.gone_one is not an action")
    assert ai.notify_action_problems(hass, "scene", {"entities": {"light.x": "on"}}) == []
    assert ai.notify_action_problems(hass, "automation", _reminder("notify.persistent_notification")) == []


# [ADDED 2026-11-05, v3.88.0] Home Assistant removes a changed entry's entity and adds it again. In between, the entity
# registry writes "unavailable" with restored: true - a second save of a LIBI Global recipient was reported as not
# accepted by Home Assistant, though it was saved and reloaded. Set here by hand, so it does not depend on timing.
async def test_the_state_written_between_removing_and_adding_is_not_a_failed_reload(hass):
    import asyncio
    from datetime import datetime, timedelta, timezone

    entry = er.async_get(hass).async_get_or_create("script", "script", "libi_send_to_guy",
                                                     suggested_object_id="libi_send_to_guy")
    op = [{"domain": "script", "key": "libi_send_to_guy", "op": "upsert"}]
    since = datetime.now(timezone.utc) - timedelta(seconds=1)
    hass.states.async_set(entry.entity_id, "unavailable", {"restored": True})

    async def reloaded():
        await asyncio.sleep(0.6)
        hass.states.async_set(entry.entity_id, "off", {"friendly_name": "LIBI Global: Guy"})

    task = hass.async_create_task(reloaded())
    assert await ws._wait_for_reloads(hass, op, since) == (set(), [])
    await task
    # An entity Home Assistant set up as unavailable - it did not accept the entry - is still a failure.
    since = datetime.now(timezone.utc) - timedelta(seconds=1)
    hass.states.async_set(entry.entity_id, "unavailable", {"friendly_name": "LIBI Global: Guy"})
    bad, errors = await ws._wait_for_reloads(hass, op, since)
    assert bad == {"script"} and errors[0].startswith("script.libi_send_to_guy is unavailable")
