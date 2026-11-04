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
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    assert plan["removals"] == [{"domain": "automation", "key": "a2"}] and done["status"] == "ok", done
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
