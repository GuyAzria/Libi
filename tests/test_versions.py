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
"""The version history of a net, against a real Home Assistant."""
import copy
import json

import pytest
import yaml
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.libi import websocket as ws
from custom_components.libi.const import AI_MODE_NONE, CONF_AI_MODE, DOMAIN
from custom_components.libi.yaml_to_libi import yaml_to_ast

AUTO = {
    "id": "a1", "alias": "Lamp", "description": "keep me", "mode": "single",
    "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
    "conditions": [],
    "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}],
}


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
def reloads(hass: HomeAssistant):
    return {d: async_mock_service(hass, d, "reload") for d in ("automation", "script", "scene")}


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


async def _send(client, msg):
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def _save(client, nets, slug="p"):
    res = await _send(client, {"type": "libi/save_automation", "slug": slug, "name": "P", "nets": nets})
    assert res["success"], res
    return res["result"]


async def _versions(client, net_id="n1", slug="p"):
    res = await _send(client, {"type": "libi/net_versions", "slug": slug, "net_id": net_id})
    assert res["success"], res
    return res["result"]


def _actions(config_dir):
    data = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    return [a for a in data if a["id"] == "a1"][0]["actions"]


async def test_save_records_versions_and_going_back_reuses_v1(hass, libi, reloads, hass_ws_client):
    client = await hass_ws_client(hass)
    first = await _save(client, [_net(hass)])
    assert first["versions"]["n1"] == {"active": 1, "latest": 1, "count": 1}

    # An unchanged save is not a version, and the history file is not rewritten.
    path = libi / "libi" / "p.versions.json"
    before = path.stat().st_mtime_ns
    again = await _save(client, [_net(hass)])
    assert again["versions"]["n1"] == {"active": 1, "latest": 1, "count": 1}
    assert path.stat().st_mtime_ns == before

    second = await _save(client, [_net(hass, "light.y")])
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
    third = await _save(client, [back])
    assert third["versions"]["n1"] == {"active": 1, "latest": 2, "count": 2}
    assert _actions(libi)[0]["target"]["entity_id"] == "light.x"
    assert len(reloads["automation"]) == 3


async def test_open_records_v1_once_for_an_older_project(hass, libi, reloads, hass_ws_client):
    """A project saved by an older LIBI has no history: opening it records V1, and opening it
    again records nothing (RULE 6, idempotent)."""
    (libi / "automations.yaml").write_text(_dump([AUTO]), encoding="utf-8")
    (libi / "libi").mkdir()
    (libi / "libi" / "old.libi").write_text(json.dumps({
        "libi_project": 1, "slug": "old", "name": "Old", "nets": [_net(hass)],
        "owned": {"automations": ["a1"]}}), encoding="utf-8")
    client = await hass_ws_client(hass)
    opened = (await _send(client, {"type": "libi/project_open", "slug": "old"}))["result"]
    assert opened["versions"]["n1"] == {"active": 1, "latest": 1, "count": 1}
    path = libi / "libi" / "old.versions.json"
    before = path.stat().st_mtime_ns
    again = (await _send(client, {"type": "libi/project_open", "slug": "old"}))["result"]
    assert again["versions"] == opened["versions"]
    assert path.stat().st_mtime_ns == before
    listed = await _versions(client, slug="old")
    assert listed["versions"][0]["reason"] == "opened"
    # Opening writes nothing into Home Assistant's files.
    assert not reloads["automation"]
    assert yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8")) == [AUTO]

    # Saved back unchanged, the net is still V1.
    saved = await _save(client, opened["nets"], slug="old")
    assert saved["versions"]["n1"] == {"active": 1, "latest": 1, "count": 1}


async def test_change_outside_libi_is_a_new_version(hass, libi, reloads, hass_ws_client):
    client = await hass_ws_client(hass)
    await _save(client, [_net(hass)])
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    data[0]["actions"][0]["target"]["entity_id"] = "light.z"
    (libi / "automations.yaml").write_text(_dump(data), encoding="utf-8")
    opened = (await _send(client, {"type": "libi/project_open", "slug": "p"}))["result"]
    assert opened["versions"]["n1"] == {"active": 2, "latest": 2, "count": 2}
    listed = await _versions(client)
    assert listed["versions"][0]["reason"] == "external"
    assert "light.z" in listed["versions"][0]["yaml"]


async def test_refused_save_records_no_version(hass, libi, reloads, hass_ws_client):
    (libi / "automations.yaml").write_text("- id: x\n  alias: [unclosed\n", encoding="utf-8")
    client = await hass_ws_client(hass)
    result = await _save(client, [_net(hass)])
    assert result["saved"] is False
    assert not (libi / "libi" / "p.versions.json").exists()


async def test_unreadable_history_is_left_alone(hass, libi, reloads, hass_ws_client):
    (libi / "libi").mkdir()
    broken = "{not json"
    (libi / "libi" / "p.versions.json").write_text(broken, encoding="utf-8")
    client = await hass_ws_client(hass)
    result = await _save(client, [_net(hass)])
    assert result["saved"] is True
    assert result["versions"] == {}
    assert (libi / "libi" / "p.versions.json").read_text(encoding="utf-8") == broken
    res = await _send(client, {"type": "libi/net_versions", "slug": "p", "net_id": "n1"})
    assert res["success"] is False
    assert res["error"]["code"] == "read_failed"


async def test_removed_net_takes_its_history_along(hass, libi, reloads, hass_ws_client):
    client = await hass_ws_client(hass)
    await _save(client, [_net(hass)])
    result = await _save(client, [])
    assert result["versions"] == {}
    assert (await _versions(client))["versions"] == []


async def test_delete_project_removes_its_history(hass, libi, reloads, hass_ws_client):
    client = await hass_ws_client(hass)
    await _save(client, [_net(hass)])
    assert (libi / "libi" / "p.versions.json").exists()
    assert (await _send(client, {"type": "libi/project_delete", "slug": "p"}))["success"]
    assert not (libi / "libi" / "p.versions.json").exists()
    assert "a1" in (libi / "automations.yaml").read_text(encoding="utf-8")


def test_history_is_capped_at_the_newest_versions():
    history = {"libi_versions": 1, "nets": {}}
    net = {"id": "n1", "name": "x"}
    total = ws.MAX_NET_VERSIONS + 5
    for i in range(1, total + 1):
        ws._record_versions(history, [(net, f"yaml {i}")], "saved", "t")
    rec = history["nets"]["n1"]
    assert [v["v"] for v in rec["versions"]] == list(range(6, total + 1))
    assert rec["active"] == total
    # Going back to a version that is still kept makes it active and adds nothing.
    assert ws._record_versions(history, [(net, "yaml 10")], "saved", "t") is True
    assert rec["active"] == 10
    assert len(rec["versions"]) == ws.MAX_NET_VERSIONS
    # The same again changes nothing, so the file is not rewritten.
    assert ws._record_versions(history, [(net, "yaml 10")], "saved", "t") is False


async def test_net_versions_is_admin_only_and_checks_the_slug(hass, libi, hass_ws_client,
                                                            hass_read_only_access_token):
    reader = await hass_ws_client(hass, hass_read_only_access_token)
    res = await _send(reader, {"type": "libi/net_versions", "slug": "p", "net_id": "n1"})
    assert res["success"] is False
    assert res["error"]["code"] == "unauthorized"
    admin = await hass_ws_client(hass)
    res = await _send(admin, {"type": "libi/net_versions", "slug": "../x", "net_id": "n1"})
    assert res["error"]["code"] == "invalid_slug"
