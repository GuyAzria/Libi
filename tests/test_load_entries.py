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
# [ADDED v3.96.0 | 2026-11-11] Purpose: The user (2026-11-11): "automations, scripts and scenes all go from YAML to LIBI
#   and back". A script and a scene of Home Assistant's files open into a NET, and from then on are that entry for the
#   save, with the rules an automation opened from Home Assistant has (CLAUDE.md RULES 5, 38 and 40): nothing written
#   while nothing changed, what the ladder does not draw kept, the same key, never deleted by a save, one project each.
"""Scripts and scenes read from Home Assistant: LOAD's list, opening one into a NET, and every save after it - through
Home Assistant's own config API, against its real script and scene integrations."""
import copy
import json

import pytest
import yaml
from homeassistant.core import HomeAssistant

from custom_components.libi.libi_to_yaml import ast_to_yaml, verify_round_trip
from custom_components.libi.yaml_to_libi import entry_to_ast, scene_to_ast, script_to_ast

from .save_helpers import home_assistant_files, save, send
from .test_websocket import libi  # noqa: F401 - the fixture

NIGHT = {"alias": "Night routine", "icon": "mdi:weather-night", "mode": "queued", "max": 3,
         "fields": {"who": {"description": "Who", "example": "Guy"}},
         "sequence": [{"action": "light.turn_off", "target": {"entity_id": "light.x"}},
                      {"delay": "00:00:05"},
                      {"if": [{"condition": "state", "entity_id": "binary_sensor.door", "state": "on"}],
                       "then": [{"action": "persistent_notification.create", "data": {"message": "Door is open, {{ who }}"}}]}]}
RECIPIENT = {"alias": "LIBI Global: Guy", "sequence": [{"action": "notify.notify", "data": {"message": "x"}}]}
MOVIE = {"id": "1700000000001", "name": "Movie", "icon": "mdi:sofa",
         "entities": {"light.sofa": {"state": "on", "brightness": 80, "rgb_color": [255, 180, 120]},
                      "light.ceiling": "off", "media_player.tv": {"state": "playing", "source": "HDMI 1"}},
         "metadata": {"light.sofa": {"entity_only": True}}}
NO_ID = {"name": "Hand written", "entities": {"light.x": "on"}}


def _scripts(libi) -> dict:  # noqa: F811
    return yaml.safe_load((libi / "scripts.yaml").read_text(encoding="utf-8")) or {}


def _scenes(libi) -> list:  # noqa: F811
    return yaml.safe_load((libi / "scenes.yaml").read_text(encoding="utf-8")) or []


def _project(libi, slug="p") -> dict:  # noqa: F811
    return json.loads((libi / "libi" / f"{slug}.libi").read_text(encoding="utf-8"))


async def _open(client, domain: str, key: str, net_id="n1", slug="p") -> dict:
    """An entry loaded into a NET from LOAD's list, as the panel loads it."""
    res = await send(client, {"type": "libi/get_automation", "domain": domain, "automation_id": key, "slug": slug,
                              "net_id": net_id})
    assert res["success"], res
    assert res["result"]["verify"]["ok"], res["result"]["verify"]
    return {**res["result"]["net"], "id": net_id}


async def _files(hass, libi):  # noqa: F811
    return await home_assistant_files(hass, libi, scripts={"night": copy.deepcopy(NIGHT),
                                                           "libi_send_to_guy": copy.deepcopy(RECIPIENT)},
                                      scenes=[copy.deepcopy(MOVIE), copy.deepcopy(NO_ID)])


# ---------------------------------------------------------------- the importers
def test_a_script_is_drawn_as_its_sequence_and_compiles_back(hass: HomeAssistant):
    net = script_to_ast(hass, "night", copy.deepcopy(NIGHT))
    assert (net["level"], net["ha_id"], net["name"], net["mode"], net["max"]) == ("script", "night", "Night routine", "queued", 3)
    assert net["extra"] == {"icon": "mdi:weather-night", "fields": NIGHT["fields"]}
    # A rung of the plain steps, a rung of the if: no trigger anywhere.
    kinds = [[e["type"] for e in r["elements"]] for r in net["rungs"]]
    assert kinds == [["coil_r", "timer_ton"], ["contact_no", "move"]], kinds
    assert not any(e.get("isTrigger") for r in net["rungs"] for e in r["elements"])
    assert ast_to_yaml(hass, net) == NIGHT
    assert verify_round_trip(hass, copy.deepcopy(NIGHT), "script", "night") == {"ok": True, "issues": [], "count": 0}
    # With no alias it is shown by its key, and gets no alias while that is still its name.
    bare = {"sequence": [{"delay": 1}]}
    net = entry_to_ast(hass, "script", "bare_one", copy.deepcopy(bare))
    assert net["name"] == "bare_one" and ast_to_yaml(hass, net) == bare
    net["name"] = "Now named"
    assert ast_to_yaml(hass, net)["alias"] == "Now named"


def test_a_scene_is_a_rung_for_each_entity_and_compiles_back(hass: HomeAssistant):
    net = scene_to_ast(hass, copy.deepcopy(MOVIE))
    assert (net["level"], net["ha_id"], net["name"]) == ("scene", "1700000000001", "Movie")
    assert net["extra"] == {"icon": "mdi:sofa", "metadata": MOVIE["metadata"]}
    drawn = [[(e["type"], e.get("label") or e.get("target"), e.get("valueKey"), e.get("source")) for e in r["elements"]]
             for r in net["rungs"]]
    assert drawn == [
        [("coil_s", "light.sofa", None, None), ("move", "light.sofa", "brightness", "80"),
         ("move", "light.sofa", "rgb_color", "[255, 180, 120]")],
        [("coil_r", "light.ceiling", None, None)],
        [("move", "media_player.tv", None, "playing"), ("move", "media_player.tv", "source", "HDMI 1")]], drawn
    assert ast_to_yaml(hass, net) == MOVIE
    assert verify_round_trip(hass, copy.deepcopy(MOVIE), "scene") == {"ok": True, "issues": [], "count": 0}
    # on written without quotes is YAML's true: it stays as the file has it while the block is not changed.
    bare = {"id": "s2", "name": "Bare", "entities": {"light.a": True, "switch.b": False, "light.c": {"state": True}}}
    assert ast_to_yaml(hass, scene_to_ast(hass, copy.deepcopy(bare))) == bare
    # Changed: brightness as a number, a colour typed as a list as that list, the coil turned round as off.
    net = scene_to_ast(hass, copy.deepcopy(MOVIE))
    sofa = net["rungs"][0]["elements"]
    sofa[0]["type"] = "coil_r"
    sofa[1]["source"] = "120"
    sofa[2]["source"] = "[0, 0, 255]"
    out = ast_to_yaml(hass, net)
    assert out["entities"]["light.sofa"] == {"state": "off", "brightness": 120, "rgb_color": [0, 0, 255]}
    assert out["entities"]["media_player.tv"] == MOVIE["entities"]["media_player.tv"]
    assert (out["icon"], out["metadata"]) == (MOVIE["icon"], MOVIE["metadata"])


# ---------------------------------------------------------------- LOAD's list
async def test_load_lists_scripts_and_scenes(hass, libi, hass_ws_client):  # noqa: F811
    await _files(hass, libi)
    client = await hass_ws_client(hass)
    res = (await send(client, {"type": "libi/list_automations"}))["result"]
    # A recipient of LIBI Global is set in the Global tab, and a scene with no id cannot be addressed: neither is listed.
    assert res["scripts"] == [{"id": "night", "name": "Night routine", "in_use": []}]
    assert res["scenes"] == [{"id": "1700000000001", "name": "Movie", "in_use": []}]
    assert res["automations"] == [] and res["unreadable"] == []
    refused = await send(client, {"type": "libi/get_automation", "domain": "script", "automation_id": "libi_send_to_guy",
                                  "slug": "p", "net_id": "n1"})
    assert not refused["success"] and refused["error"]["code"] == "not_found"
    # An automation is still found by its id alone, as an older panel asks.
    missing = await send(client, {"type": "libi/get_automation", "automation_id": "night", "slug": "p", "net_id": "n1"})
    assert not missing["success"] and missing["error"]["code"] == "not_found"


# ---------------------------------------------------------------- a script opened from Home Assistant
async def test_a_script_opened_from_home_assistant_is_that_script(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    calls = await _files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    before = (libi / "scripts.yaml").read_text(encoding="utf-8")
    net = await _open(client, "script", "night")
    assert (net["level"], net["ha_id"]) == ("script", "night")
    # Saved with nothing changed: nothing is sent, nothing reloads, and it is this project's to update - not its to delete.
    plan, done = await save(client, http, [net])
    assert (plan["upserts"], plan["removals"], plan["unchanged"]) == ([], [], 1) and done["status"] == "ok", plan
    assert (libi / "scripts.yaml").read_text(encoding="utf-8") == before and calls["script"] == 0
    project = _project(libi)
    assert project["owned"]["scripts"] == ["night"] and project["made"]["scripts"] == []
    assert project["keys"] == {"n1": {"domain": "script", "key": "night", "base": "night"}}
    # Changed and renamed: its own key, never the slug of its name; the icon, the fields and the mode stay.
    changed = json.loads(json.dumps(net))
    changed["name"] = "Bed time"
    changed["rungs"][0]["elements"][1]["label"] = "00:00:09"
    plan, done = await save(client, http, [changed])
    assert [(op["domain"], op["key"], op["new"]) for op in plan["upserts"]] == [("script", "night", False)], plan
    assert done["status"] == "ok", done
    saved = _scripts(libi)
    assert set(saved) == {"night", "libi_send_to_guy"} and saved["libi_send_to_guy"] == RECIPIENT
    assert saved["night"] == {**NIGHT, "alias": "Bed time", "sequence": [NIGHT["sequence"][0], {"delay": "00:00:09"},
                                                                         NIGHT["sequence"][2]]}
    assert _project(libi)["made"]["scripts"] == []
    # The project opened again: the NET is drawn from the script as Home Assistant has it now.
    users = {**saved["night"], "alias": "Changed in Home Assistant"}
    assert (await http.post("/api/config/script/config/night", json=users)).status == 200
    opened = (await send(client, {"type": "libi/project_open", "slug": "p"}))["result"]
    assert [(n["name"], n["level"], n["ha_id"], n["source"]) for n in opened["nets"]] == [
        ("Changed in Home Assistant", "script", "night", "ha")]
    # Off the canvas (Clear all nets) and saved: the script stays in Home Assistant as it is, and leaves the project.
    kept = (libi / "scripts.yaml").read_text(encoding="utf-8")
    plan, done = await save(client, http, [])
    assert (plan["upserts"], plan["removals"]) == ([], []) and [r["key"] for r in plan["released"]] == ["night"], plan
    assert done["status"] == "ok" and (libi / "scripts.yaml").read_text(encoding="utf-8") == kept
    assert _project(libi)["owned"]["scripts"] == []


async def test_a_script_belongs_to_one_project_and_its_net_may_delete_only_it(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    await _files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    net = await _open(client, "script", "night")
    await save(client, http, [net], slug="p", name="Home")
    listed = (await send(client, {"type": "libi/list_automations"}))["result"]["scripts"]
    assert listed == [{"id": "night", "name": "Night routine", "in_use": [{"slug": "p", "name": "Home", "nets": ["n1"]}]}]
    refused = await send(client, {"type": "libi/get_automation", "domain": "script", "automation_id": "night",
                                  "slug": "q", "net_id": "n1"})
    assert not refused["success"] and refused["error"]["code"] == "in_use", refused
    assert refused["error"]["message"].startswith("This script is already in the project Home. A script belongs to one project")
    own = await send(client, {"type": "libi/get_automation", "domain": "script", "automation_id": "night",
                              "slug": "p", "net_id": "n1"})
    assert own["success"], own
    # Delete NET offers the NET's own script, opened from Home Assistant - not made by LIBI.
    revision = _project(libi)["revision"]
    plan = (await send(client, {"type": "libi/net_delete_plan", "slug": "p", "net_id": "n1", "nets": [net],
                                "revision": revision}))["result"]
    assert (plan["domain"], plan["key"], plan["made"], plan["in_ha"]) == ("script", "night", False, True), plan
    assert plan["original"] and plan["original"]["config"] == NIGHT
    # A script NET that only carries that key - a copy, nothing opened into it - is not that script: named by its name.
    stranger = {**json.loads(json.dumps(net)), "id": "n7", "name": "Another one"}
    plan, _done = await save(client, http, [stranger], slug="q", name="Other")
    assert [(op["key"], op["new"]) for op in plan["upserts"]] == [("another_one", True)], plan
    assert _scripts(libi)["night"] == NIGHT


async def test_a_script_drawn_in_libi_is_still_named_by_its_name(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    """The AI chat's drafts carry an ha_id of their own: a script NET nobody opened from Home Assistant keeps the rule it
    had - the slug of its name, the next free one when that is taken."""
    await _files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    drawn = script_to_ast(hass, "x", {"alias": "Night", "sequence": [{"delay": 2}]})
    drawn.update(id="n1", ha_id="libi_ai_123", name="Night")
    plan, done = await save(client, http, [drawn])
    assert [(op["key"], op["new"]) for op in plan["upserts"]] == [("night_2", True)] and done["status"] == "ok", plan
    assert _scripts(libi)["night"] == NIGHT and _project(libi)["made"]["scripts"] == ["night_2"]
    plan, done = await save(client, http, [drawn])
    assert (plan["upserts"], plan["unchanged"]) == ([], 1), plan


# ---------------------------------------------------------------- a scene opened from Home Assistant
async def test_a_scene_opened_from_home_assistant_is_that_scene(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    calls = await _files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    before = (libi / "scenes.yaml").read_text(encoding="utf-8")
    net = await _open(client, "scene", "1700000000001")
    assert (net["level"], net["ha_id"]) == ("scene", "1700000000001")
    plan, done = await save(client, http, [net])
    assert (plan["upserts"], plan["removals"], plan["unchanged"]) == ([], [], 1) and done["status"] == "ok", plan
    assert (libi / "scenes.yaml").read_text(encoding="utf-8") == before and calls["scene"] == 0
    assert _project(libi)["made"]["scenes"] == []
    # One value changed: that scene, under its id; every other entity, the icon and the metadata as they were; the scene
    # with no id is not touched.
    changed = json.loads(json.dumps(net))
    changed["rungs"][0]["elements"][1]["source"] = "200"
    plan, done = await save(client, http, [changed])
    assert [(op["domain"], op["key"], op["new"]) for op in plan["upserts"]] == [("scene", "1700000000001", False)], plan
    assert done["status"] == "ok", done
    saved = _scenes(libi)
    # (Home Assistant's own config API gives a scene with no id one when it writes the file - as its editor does.)
    assert len(saved) == 2 and {k: v for k, v in saved[1].items() if k != "id"} == NO_ID
    assert saved[0] == {**MOVIE, "entities": {**MOVIE["entities"], "light.sofa": {**MOVIE["entities"]["light.sofa"], "brightness": 200}}}
    # Opened again from Home Assistant as it is now; then off the canvas: it stays.
    opened = (await send(client, {"type": "libi/project_open", "slug": "p"}))["result"]
    assert [(n["level"], n["ha_id"], n["source"]) for n in opened["nets"]] == [("scene", "1700000000001", "ha")]
    assert opened["nets"][0]["rungs"][0]["elements"][1]["source"] == "200"
    kept = (libi / "scenes.yaml").read_text(encoding="utf-8")
    plan, done = await save(client, http, [])
    assert (plan["upserts"], plan["removals"]) == ([], []) and [r["key"] for r in plan["released"]] == ["1700000000001"]
    assert done["status"] == "ok" and (libi / "scenes.yaml").read_text(encoding="utf-8") == kept


@pytest.mark.parametrize("entities", [
    {"input_number.level": "5"}, {"input_select.mode": "Away"}, {"cover.c": {"state": "open", "current_position": 40}},
    {"climate.ac": {"state": "heat", "temperature": 21.5}}, {"light.a": {"state": "on", "xy_color": [0.4, 0.3]}}])
async def test_what_a_scene_net_compiles_to_is_a_scene_home_assistant_takes(hass, libi, hass_ws_client, hass_client, entities):  # noqa: F811
    """Drawn in LIBI - every block typed, none carrying a value of a file: Home Assistant's config API takes the scene."""
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    net = scene_to_ast(hass, {"id": "x", "name": "Drawn", "entities": copy.deepcopy(entities)})
    net.update(id="n1", ha_id=None)
    for rung in net["rungs"]:
        for el in rung["elements"]:
            el.pop("raw", None)
            el.pop("sig", None)
    plan, done = await save(client, http, [net])
    assert done is not None and done["status"] == "ok", (plan, done)
    assert _scenes(libi)[0]["entities"] == entities


# ---------------------------------------------------------------- what the ladder cannot draw
def test_a_condition_kept_as_it_is_is_written_back_whatever_its_block_shows(hass: HomeAssistant):
    """A condition of a kind the ladder has no drawing for, an or that is turned off, a not it cannot turn round: one
    block each, and the node goes back as it was - also when the block's text or type was changed some other way."""
    kept = [{"condition": "light.is_on", "target": {"entity_id": "light.x"}, "options": {"behavior": "any"}},
            {"condition": "or", "enabled": False, "conditions": [{"condition": "state", "entity_id": "light.a", "state": "on"},
                                                                  {"condition": "state", "entity_id": "light.b", "state": "on"}]},
            {"condition": "not", "conditions": [{"condition": "time", "after": "08:00:00", "before": "20:00:00"}]},
            {"condition": "not", "conditions": [{"condition": "state", "entity_id": "climate.ac", "state": "heat", "for": "00:05:00"}]}]
    script = {"alias": "Kept", "sequence": [{"if": copy.deepcopy(kept), "then": [{"delay": 1}]}]}
    net = script_to_ast(hass, "kept", copy.deepcopy(script))
    blocks = [e for r in net["rungs"] for e in r["elements"] if e.get("opaque")]
    assert len(blocks) == 4 and all(e["type"] == "cmp_eq" and e["sourceB"] == "true" for e in blocks), blocks
    assert ast_to_yaml(hass, net) == script
    for el in blocks:
        el.update(sourceA="light.somewhere", sourceB="off", type="cmp_ne")
    assert ast_to_yaml(hass, net) == script
    # A not of two checks is each of them turned round - never the two checks without their not.
    two = {"alias": "Two", "sequence": [{"if": [{"condition": "not", "conditions": [
        {"condition": "state", "entity_id": "light.a", "state": "on"},
        {"condition": "state", "entity_id": "climate.ac", "state": "heat"}]}], "then": [{"delay": 1}]}]}
    net = script_to_ast(hass, "two", copy.deepcopy(two))
    drawn = [(e["type"], e.get("label") or e.get("sourceA")) for e in net["rungs"][0]["elements"][:2]]
    assert drawn == [("contact_nc", "light.a"), ("cmp_ne", "climate.ac")], drawn
    assert verify_round_trip(hass, copy.deepcopy(two), "script", "two")["ok"]


async def test_a_save_says_what_it_would_lose_of_a_script_opened_from_home_assistant(hass, libi, hass_ws_client, hass_client):  # noqa: F811
    """An and with a name of its own is drawn as its checks: the name is not kept. Changed in LIBI, the save says so
    before it writes (loses) - as for an automation. Not changed, nothing is written at all."""
    named = {"alias": "Named", "sequence": [{"if": [{"condition": "and", "alias": "both on", "conditions": [
        {"condition": "state", "entity_id": "light.a", "state": "on"},
        {"condition": "state", "entity_id": "light.b", "state": "on"}]}], "then": [{"delay": 1}]}]}
    await home_assistant_files(hass, libi, scripts={"named": copy.deepcopy(named)})
    client, http = await hass_ws_client(hass), await hass_client()
    res = await send(client, {"type": "libi/get_automation", "domain": "script", "automation_id": "named", "slug": "p",
                              "net_id": "n1"})
    assert res["success"] and res["result"]["verify"]["ok"] is False, res
    net = {**res["result"]["net"], "id": "n1"}
    before = (libi / "scripts.yaml").read_text(encoding="utf-8")
    plan, done = await save(client, http, [net])
    assert (plan["upserts"], plan["unchanged"]) == ([], 1) and (libi / "scripts.yaml").read_text(encoding="utf-8") == before
    changed = json.loads(json.dumps(net))
    changed["rungs"][0]["elements"][-1]["label"] = "00:00:07"
    plan, done = await save(client, http, [changed], loses="cancel")
    assert done is None and [op["key"] for op in plan["upserts"]] == ["named"] and plan["upserts"][0]["loses"], plan
    assert (libi / "scripts.yaml").read_text(encoding="utf-8") == before
