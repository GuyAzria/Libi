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
# [ADDED v1.0.0 | 2026-10-27] Purpose: Net versions. Opening records V1, a save that changes a net records
#   the next one, going back to an earlier version makes it the active one without copying it, and the
#   history never claims a version that did not reach Home Assistant's files.
# [ADDED v3.85.0 | 2026-11-04] Purpose: Saved through Home Assistant's config API (save_helpers); an automation opened
#   the first time is V1, the original exactly as it was, and V2 its copy; V1 put back restores it; an original is never
#   dropped.
"""The version history of a net, against a real Home Assistant."""
import copy
import json

import pytest
import yaml
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.libi import websocket as ws
from custom_components.libi.const import AI_MODE_NONE, CONF_AI_MODE, DOMAIN
from custom_components.libi.libi_to_yaml import same_config
from custom_components.libi.yaml_to_libi import yaml_to_ast

from .save_helpers import home_assistant_files, save, send

AUTO = {
    "id": "a1", "alias": "Lamp", "description": "keep me", "mode": "single",
    "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
    "conditions": [],
    "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}],
}
# Written in the older spelling, as many of the user's automations are: V1 keeps it exactly so.
LEGACY = {"id": "a1", "alias": "Lamp", "trigger": [{"platform": "state", "entity_id": "binary_sensor.door", "to": "on"}],
          "action": [{"service": "light.turn_on", "target": {"entity_id": "light.x"}}], "mode": "single"}


def _dump(data) -> str:
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


@pytest.fixture
async def libi(hass: HomeAssistant, config_dir):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_AI_MODE: AI_MODE_NONE})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return config_dir


def _net(hass, light="light.x"):
    auto = copy.deepcopy(AUTO)
    auto["actions"][0]["target"]["entity_id"] = light
    net = yaml_to_ast(hass, auto)
    net["id"] = "n1"
    net["ha_id"] = "a1"
    return net


def _reid(net):
    """What the panel's duplicateNet does to a version it puts back: every rung and element gets a
    new id. The YAML must not change, or going back to V1 would record a V3."""
    out = copy.deepcopy(net)
    counter = [900]

    def walk(items):
        for el in items or []:
            counter[0] += 1
            el["id"] = f"e{counter[0]}"
            for branch in el.get("branches") or []:
                walk(branch)
            walk(el.get("sequence"))

    for rung in out.get("rungs") or []:
        counter[0] += 1
        rung["id"] = f"r{counter[0]}"
        walk(rung.get("elements"))
    return out


async def _versions(client, net_id="n1", slug="p"):
    res = await send(client, {"type": "libi/net_versions", "slug": slug, "net_id": net_id})
    assert res["success"], res
    return res["result"]


def _entry(config_dir, key="a1"):
    data = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    return [a for a in data if a["id"] == key][0]


def _actions(config_dir):
    return _entry(config_dir)["actions"]


async def _setup(hass, config_dir, hass_ws_client, hass_client, automations=None):
    calls = await home_assistant_files(hass, config_dir, automations=automations)
    return calls, await hass_ws_client(hass), await hass_client()


async def test_save_records_versions_and_going_back_reuses_v1(hass, libi, hass_ws_client, hass_client):
    """A NET drawn from scratch: its first save is V1, and it gets no copy (the user's rule, 2026-11-04)."""
    calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client)
    _plan, first = await save(client, http, [_net(hass)])
    assert first["versions"]["n1"] == {"active": 1, "latest": 1, "count": 1}

    # An unchanged save is not a version, and the history file is not rewritten.
    path = libi / "libi" / "p.versions.json"
    before = path.stat().st_mtime_ns
    _plan, again = await save(client, http, [_net(hass)])
    assert again["versions"]["n1"] == {"active": 1, "latest": 1, "count": 1}
    assert path.stat().st_mtime_ns == before

    _plan, second = await save(client, http, [_net(hass, "light.y")])
    assert second["versions"]["n1"] == {"active": 2, "latest": 2, "count": 2}
    assert _actions(libi)[0]["target"]["entity_id"] == "light.y"

    listed = await _versions(client)
    assert [v["v"] for v in listed["versions"]] == [2, 1]
    assert listed["active"] == 2
    assert all(v["reason"] == "saved" for v in listed["versions"])
    v1 = listed["versions"][1]
    assert "light.x" in v1["yaml"]
    assert "source" not in v1["net"]

    # Putting V1 back on the canvas and saving makes V1 the one that runs - no V3 copy of it.
    back = _reid(v1["net"])
    back["id"], back["ha_id"] = "n1", "a1"
    _plan, third = await save(client, http, [back])
    assert third["versions"]["n1"] == {"active": 1, "latest": 2, "count": 2}
    assert _actions(libi)[0]["target"]["entity_id"] == "light.x"
    assert calls["automation"] == 3


async def test_an_automation_opened_the_first_time_is_v1_the_original_and_v2_its_copy(hass, libi, hass_ws_client,
                                                                                      hass_client):
    """[CHANGED 2026-11-04, v3.85.0] The user's rule: an automation opened the first time is kept as it was - V1, the
    original exactly as Home Assistant has it, its old spelling too - and copied to V2, the version to work on. Opening
    it again records nothing (RULE 6, idempotent). Until 3.84.0 opening recorded one V1, as LIBI would write it."""
    calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client, automations=[LEGACY])
    as_written = (libi / "automations.yaml").read_text(encoding="utf-8")
    (libi / "libi").mkdir(exist_ok=True)
    (libi / "libi" / "old.libi").write_text(json.dumps({
        "libi_project": 1, "slug": "old", "name": "Old", "nets": [_net(hass)],
        "owned": {"automations": ["a1"]}}), encoding="utf-8")
    opened = (await send(client, {"type": "libi/project_open", "slug": "old"}))["result"]
    assert opened["versions"]["n1"] == {"active": 2, "latest": 2, "count": 2, "original": 1}
    listed = await _versions(client, slug="old")
    assert [(v["v"], v["reason"], v.get("original", False)) for v in listed["versions"]] == [
        (2, "copy", False), (1, "original", True)]
    assert listed["versions"][1]["config"] == LEGACY and listed["versions"][0]["config"] == LEGACY
    assert "trigger:" in listed["versions"][1]["yaml"] and "triggers:" not in listed["versions"][1]["yaml"]
    path = libi / "libi" / "old.versions.json"
    before = path.stat().st_mtime_ns
    again = (await send(client, {"type": "libi/project_open", "slug": "old"}))["result"]
    assert again["versions"] == opened["versions"]
    assert path.stat().st_mtime_ns == before
    # Opening writes nothing into Home Assistant's files.
    assert calls["automation"] == 0
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == as_written

    # Saved without a change, nothing is sent - not even in LIBI's spelling - and V2 stays the one that runs.
    plan, saved = await save(client, http, opened["nets"], slug="old")
    assert (plan["upserts"], plan["unchanged"]) == ([], 1)
    assert saved["versions"]["n1"] == {"active": 2, "latest": 2, "count": 2, "original": 1}
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == as_written


async def test_v1_put_back_on_the_canvas_restores_the_original(hass, libi, hass_ws_client, hass_client):
    _calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client, automations=[LEGACY])
    loaded = await send(client, {"type": "libi/get_automation", "automation_id": "a1", "slug": "p", "net_id": "n1"})
    net = {**loaded["result"]["net"], "id": "n1"}
    edited = json.loads(json.dumps(net).replace("light.x", "light.y"))
    _plan, done = await save(client, http, [edited])
    assert done["versions"]["n1"] == {"active": 3, "latest": 3, "count": 3, "original": 1}
    assert _actions(libi)[0]["target"]["entity_id"] == "light.y"

    v1 = next(v for v in (await _versions(client))["versions"] if v["v"] == 1)
    back = _reid(v1["net"])
    back["id"], back["ha_id"] = "n1", "a1"
    plan, done = await save(client, http, [back])
    # What is sent is the original exactly; Home Assistant writes it in today's spelling, as its own editor does.
    assert [op["config"] for op in plan["upserts"]] == [LEGACY]
    assert same_config(_entry(libi), LEGACY)
    assert done["versions"]["n1"] == {"active": 2, "latest": 3, "count": 3, "original": 1}
    # Saved again as it is, nothing is sent: the file holds the original, spelled the way Home Assistant writes it.
    plan, _done = await save(client, http, [back])
    assert plan["upserts"] == []
    # And opened again, it is the same version: it means what V2 holds, however Home Assistant spells it.
    opened = (await send(client, {"type": "libi/project_open", "slug": "p"}))["result"]
    assert opened["versions"]["n1"] == {"active": 2, "latest": 3, "count": 3, "original": 1}


async def test_loading_an_automation_into_a_net_records_its_original_once(hass, libi, hass_ws_client, hass_client):
    hall = copy.deepcopy(AUTO)
    hall.update(id="a2", alias="Hall")
    calls, client, _http = await _setup(hass, libi, hass_ws_client, hass_client, automations=[LEGACY, hall])

    async def load(auto_id):
        res = await send(client, {"type": "libi/get_automation", "automation_id": auto_id, "slug": "p", "net_id": "n1"})
        assert res["success"], res
        return res["result"]["versions"]["n1"]

    first = await load("a1")
    assert first == {"active": 2, "latest": 2, "count": 2, "original": 1}
    assert await load("a1") == first
    # Another automation loaded into the same NET: its own original and copy.
    assert await load("a2") == {"active": 4, "latest": 4, "count": 4, "original": 3}
    assert [v["reason"] for v in (await _versions(client))["versions"]] == ["copy", "original", "copy", "original"]
    assert calls["automation"] == 0


async def test_change_outside_libi_is_a_new_version(hass, libi, hass_ws_client, hass_client):
    _calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client)
    await save(client, http, [_net(hass)])
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    data[0]["actions"][0]["target"]["entity_id"] = "light.z"
    (libi / "automations.yaml").write_text(_dump(data), encoding="utf-8")
    opened = (await send(client, {"type": "libi/project_open", "slug": "p"}))["result"]
    assert opened["versions"]["n1"] == {"active": 2, "latest": 2, "count": 2}
    listed = await _versions(client)
    assert listed["versions"][0]["reason"] == "external"
    assert "light.z" in listed["versions"][0]["yaml"]


async def test_refused_save_records_no_version(hass, libi, hass_ws_client, hass_client):
    (libi / "automations.yaml").write_text("- id: x\n  alias: [unclosed\n", encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [_net(hass)])
    assert plan["ok"] is False and done is None
    assert not (libi / "libi" / "p.versions.json").exists()


async def test_unreadable_history_is_left_alone(hass, libi, hass_ws_client, hass_client):
    _calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client)
    (libi / "libi").mkdir()
    broken = "{not json"
    (libi / "libi" / "p.versions.json").write_text(broken, encoding="utf-8")
    _plan, done = await save(client, http, [_net(hass)])
    assert done["saved"] is True
    assert done["versions"] == {}
    assert (libi / "libi" / "p.versions.json").read_text(encoding="utf-8") == broken
    res = await send(client, {"type": "libi/net_versions", "slug": "p", "net_id": "n1"})
    assert res["success"] is False
    assert res["error"]["code"] == "read_failed"


async def test_removed_net_takes_its_history_along(hass, libi, hass_ws_client, hass_client):
    _calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client)
    await save(client, http, [_net(hass)])
    _plan, done = await save(client, http, [])
    assert done["versions"] == {}
    assert (await _versions(client))["versions"] == []


async def test_delete_project_removes_its_history(hass, libi, hass_ws_client, hass_client):
    _calls, client, http = await _setup(hass, libi, hass_ws_client, hass_client)
    await save(client, http, [_net(hass)])
    assert (libi / "libi" / "p.versions.json").exists()
    assert (await send(client, {"type": "libi/project_delete", "slug": "p"}))["success"]
    assert not (libi / "libi" / "p.versions.json").exists()
    assert "a1" in (libi / "automations.yaml").read_text(encoding="utf-8")


def test_history_is_capped_at_the_newest_versions():
    history = {"libi_versions": 1, "nets": {}}
    net = {"id": "n1", "name": "x"}
    # [CHANGED 2026-11-04, v3.85.0] The original is never dropped: the NET can always go back to it.
    assert ws._record_original(history, net, "automation", "a1", {"alias": "original"}, "t") is True
    total = ws.MAX_NET_VERSIONS + 5
    for i in range(3, total + 1):
        ws._record_versions(history, [(net, {"alias": f"v{i}"}, None)], "saved", "t")
    rec = history["nets"]["n1"]
    kept = [v["v"] for v in rec["versions"]]
    assert len(kept) == ws.MAX_NET_VERSIONS and kept[0] == 1 and rec["versions"][0]["original"] is True
    assert kept[1:] == list(range(total - ws.MAX_NET_VERSIONS + 2, total + 1))
    assert rec["active"] == total
    # Going back to a version that is still kept makes it active and adds nothing.
    assert ws._record_versions(history, [(net, {"alias": "v20"}, None)], "saved", "t") is True
    assert rec["active"] == 20
    assert len(rec["versions"]) == ws.MAX_NET_VERSIONS
    # The same again changes nothing, so the file is not rewritten.
    assert ws._record_versions(history, [(net, {"alias": "v20"}, None)], "saved", "t") is False
    # And the original is recorded once per automation.
    assert ws._record_original(history, net, "automation", "a1", {"alias": "original"}, "t") is False


def test_a_version_from_before_3_85_is_found_by_its_text():
    """A version recorded before 3.85.0 has its YAML text alone: it is still the one a save of the same YAML finds."""
    history = {"nets": {"n1": {"active": 1, "versions": [{"v": 1, "yaml": "alias: x\n", "net": {}}]}}}
    assert ws._record_versions(history, [({"id": "n1"}, {"alias": "x"}, "alias: x\n")], "saved", "t") is False
    assert [v["v"] for v in history["nets"]["n1"]["versions"]] == [1]


async def test_net_versions_is_admin_only_and_checks_the_slug(hass, libi, hass_ws_client,
                                                            hass_read_only_access_token):
    reader = await hass_ws_client(hass, hass_read_only_access_token)
    res = await send(reader, {"type": "libi/net_versions", "slug": "p", "net_id": "n1"})
    assert res["success"] is False
    assert res["error"]["code"] == "unauthorized"
    admin = await hass_ws_client(hass)
    res = await send(admin, {"type": "libi/net_versions", "slug": "../x", "net_id": "n1"})
    assert res["error"]["code"] == "invalid_slug"
