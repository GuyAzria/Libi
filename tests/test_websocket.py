"""The websocket commands against a real Home Assistant: authorization, schemas, and the rules
that protect the user's automations.yaml (CLAUDE.md RULE 5 and RULE 32)."""
import copy

import pytest
import yaml
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.libi.const import AI_MODE_NONE, CONF_AI_MODE, DOMAIN
from custom_components.libi.yaml_to_libi import yaml_to_ast

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
def reloads(hass: HomeAssistant):
    """Each reload service the save calls, recorded instead of reloading for real."""
    return {d: async_mock_service(hass, d, "reload") for d in ("automation", "script", "scene")}


def _net(hass, auto=AUTO):
    return yaml_to_ast(hass, copy.deepcopy(auto))


async def test_non_admin_is_rejected(hass, libi, hass_ws_client, hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for msg in ({"type": "libi/save_automation", "nets": []},
                {"type": "libi/list_automations"},
                {"type": "libi/delete_automation", "automation_id": "a1"},
                {"type": "libi/project_list"}):
        await client.send_json_auto_id(msg)
        res = await client.receive_json()
        assert res["success"] is False, msg
        assert res["error"]["code"] == "unauthorized", msg
    assert not (libi / "automations.yaml").exists()


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
                {"type": "libi/save_automation", "slug": slug, "nets": []}):
        await client.send_json_auto_id(msg)
        res = await client.receive_json()
        assert res["success"] is False, msg
        assert res["error"]["code"] == "invalid_slug", msg
    assert not list(libi.parent.glob("*.libi"))


async def test_save_writes_reloads_and_keeps_hand_written_entries(hass, libi, reloads, hass_ws_client):
    (libi / "automations.yaml").write_text(_dump([HAND]), encoding="utf-8")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/save_automation", "slug": "p", "name": "P",
                                    "nets": [_net(hass)]})
    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["saved"] is True
    assert res["result"]["status"] == "ok", res["result"]
    assert res["result"]["reloaded"] == ["automation"]
    assert len(reloads["automation"]) == 1
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert data[0] == HAND
    assert list(data[0]) == list(HAND)
    assert [a for a in data if a["id"] == "a1"][0]["mode"] == "single"


async def test_unchanged_save_is_not_written_or_reloaded(hass, libi, reloads, hass_ws_client):
    client = await hass_ws_client(hass)
    msg = {"type": "libi/save_automation", "slug": "p", "nets": [_net(hass)]}
    await client.send_json_auto_id(dict(msg))
    await client.receive_json()
    before = (libi / "automations.yaml").stat().st_mtime_ns
    await client.send_json_auto_id(dict(msg))
    res = await client.receive_json()
    assert res["result"]["written"] == []
    assert res["result"]["reloaded"] == []
    assert len(reloads["automation"]) == 1
    assert (libi / "automations.yaml").stat().st_mtime_ns == before


async def test_unreadable_file_means_nothing_is_written(hass, libi, reloads, hass_ws_client):
    broken = "- id: x\n  alias: [unclosed\n"
    (libi / "automations.yaml").write_text(broken, encoding="utf-8")
    (libi / "scripts.yaml").write_text("keep: {sequence: []}\n", encoding="utf-8")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/save_automation", "slug": "p", "nets": [_net(hass)]})
    res = await client.receive_json()
    assert res["result"]["saved"] is False
    assert res["result"]["status"] == "error"
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == broken
    assert (libi / "scripts.yaml").read_text(encoding="utf-8") == "keep: {sequence: []}\n"
    assert not (libi / "libi" / "p.libi").exists()
    assert not any(reloads.values())


async def test_failed_reload_is_reported(hass, libi, hass_ws_client):
    async def broken_reload(call: ServiceCall) -> None:
        raise HomeAssistantError("boom")

    hass.services.async_register("automation", "reload", broken_reload)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/save_automation", "slug": "p", "nets": [_net(hass)]})
    res = await client.receive_json()
    assert res["result"]["saved"] is True
    assert res["result"]["status"] == "error"
    assert res["result"]["reloaded"] == []
    assert any("automation reload failed" in e for e in res["result"]["errors"])


async def test_script_net_keeps_the_project_name(hass, libi, reloads, hass_ws_client):
    net = _net(hass)
    net["level"] = "script"
    net["name"] = "Night Routine"
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/save_automation", "slug": "garden", "nets": [net]})
    res = await client.receive_json()
    assert res["result"]["saved"] is True
    assert (libi / "libi" / "garden.libi").exists()
    assert not (libi / "libi" / "night_routine.libi").exists()
    assert "night_routine" in yaml.safe_load((libi / "scripts.yaml").read_text(encoding="utf-8"))


async def test_delete_removes_only_that_automation(hass, libi, reloads, hass_ws_client):
    (libi / "automations.yaml").write_text(_dump([HAND, AUTO]), encoding="utf-8")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/delete_automation", "automation_id": "a1"})
    res = await client.receive_json()
    assert res["result"]["deleted"] is True
    assert res["result"]["reloaded"] == ["automation"]
    data = yaml.safe_load((libi / "automations.yaml").read_text(encoding="utf-8"))
    assert data == [HAND]
    assert list(data[0]) == list(HAND)


async def test_delete_of_a_broken_file_is_refused(hass, libi, reloads, hass_ws_client):
    broken = "- id: a1\n  alias: [unclosed\n"
    (libi / "automations.yaml").write_text(broken, encoding="utf-8")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/delete_automation", "automation_id": "a1"})
    res = await client.receive_json()
    assert res["success"] is False
    assert res["error"]["code"] == "delete_failed"
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == broken
    assert not reloads["automation"]


async def test_project_round_trip(hass, libi, reloads, hass_ws_client):
    """Create, save, list, open (rebuilt from automations.yaml on the event loop) and delete."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "libi/project_create", "name": "Garden Pool"})
    slug = (await client.receive_json())["result"]["slug"]
    net = _net(hass)
    net["ha_id"] = "a1"
    await client.send_json_auto_id({"type": "libi/save_automation", "slug": slug, "nets": [net]})
    assert (await client.receive_json())["result"]["saved"] is True

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
