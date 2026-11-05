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
# [ADDED v1.0.0 | 2026-11-05] Purpose: LIBI Global against a real Home Assistant - a recipient of messages is a script,
#   saved through Home Assistant's config API, that sends to the phones ticked for it; changing its phones changes where
#   every NET that sends to it sends, and no automation is written again (the user's request, 2026-11-05).
# [ADDED v1.1.0 | 2026-11-05] Purpose: libi/global_move_plan and libi/global_move_done - the automations that send
#   straight to a recipient's phone send through it once confirmed, and what is not moved (LIBI 3.89.0).
"""LIBI Global: libi/global, libi/global_plan and libi/global_done, as the panel calls them, and the script running;
libi/global_move_plan and libi/global_move_done, the phone replaced with its recipient."""
import copy
import json
import os

import pytest
import yaml
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.libi import recipients
from custom_components.libi.libi_to_yaml import verify_round_trip
from custom_components.libi.yaml_to_libi import yaml_to_ast

from .save_helpers import dump, home_assistant_files, save, send
from .test_websocket import _phones, libi, writes  # noqa: F401 - fixtures

GUY = "notify.mobile_app_sm_s918b"
YULIA = "notify.mobile_app_sm_s938b"
IPHONE = "notify.mobile_app_guy_iphone"
# The user's own words are data, in tests/fixtures/user_text_he.json: English only in the code (CLAUDE.md RULE 17).
with open(os.path.join(os.path.dirname(__file__), "fixtures", "user_text_he.json"), encoding="utf-8") as _fixture:
    HE = json.load(_fixture)
SPOKEN = {"message": "TTS", "data": {"tts_text": "Time to go to the train", "media_stream": "alarm_stream"}}


def _phone_calls(hass) -> dict:
    """The phones of _phones, each recording what it was sent."""
    return {s: async_mock_service(hass, "notify", s.split(".", 1)[1]) for s in (GUY, YULIA, IPHONE)}


def _reminder(action: str, data: dict | None = None, key: str = "train") -> dict:
    return {"id": key, "alias": "Train reminder", "description": "", "mode": "single",
            "triggers": [{"trigger": "state", "entity_id": "input_boolean.train_time", "to": "on"}], "conditions": [],
            "actions": [{"action": action, "data": copy.deepcopy(data or SPOKEN)}]}


async def _global_save(client, http, name="Guy", phones=(GUY,), key="", remove=False, refuse=False):
    """A recipient saved as the panel saves it: libi/global_plan, Home Assistant's config API, libi/global_done.
    Returns the plan and what libi/global_done answered (None when nothing was sent)."""
    planned = await send(client, {"type": "libi/global_plan", "key": key, "name": name, "phones": list(phones),
                                  "remove": remove})
    assert planned["success"], planned
    plan = planned["result"]
    if not plan["ok"] or plan.get("unchanged"):
        return plan, None
    op = plan["op"]
    url = f"/api/config/script/config/{op['key']}"
    failure = None
    if refuse:
        failure = {"domain": "script", "key": op["key"], "op": op["op"], "message": "Message malformed: refused by the test"}
    else:
        resp = await (http.post(url, json=op["config"]) if op["op"] == "upsert" else http.delete(url))
        assert resp.status == 200, await resp.text()
    finished = await send(client, {"type": "libi/global_done", "key": op["key"], "op": op["op"], "label": op["label"],
                                   "failure": failure, "stamp": plan["stamp"]})
    assert finished["success"], finished
    return plan, finished["result"]


def _scripts(config_dir) -> dict:
    return yaml.safe_load((config_dir / "scripts.yaml").read_text(encoding="utf-8")) or {}


async def test_global_is_empty_at_first_and_lists_the_phones(hass, libi, hass_ws_client):
    _phones(hass)
    await home_assistant_files(hass, libi)
    client = await hass_ws_client(hass)
    res = await send(client, {"type": "libi/global"})
    assert res["success"], res
    assert res["result"]["ok"] is True and res["result"]["recipients"] == []
    assert [p["service"] for p in res["result"]["phones"]][:1] == [IPHONE]


async def test_a_recipient_is_a_script_that_sends_to_its_phones(hass, libi, writes, hass_ws_client, hass_client):
    """The whole way: made in LIBI Global, saved by Home Assistant's config API, reloaded, and run - each phone gets what
    a notify action of its own would have given it; the iPhone, which does not read aloud, gets the spoken text."""
    _phones(hass)
    calls = _phone_calls(hass)
    reloads = await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await _global_save(client, http, phones=[GUY, IPHONE])
    assert plan["ok"] is True and plan["op"]["key"] == "libi_send_to_guy", plan
    # The phones in the order of the list, not of the ticks: the same phones make the same script.
    assert [s["action"] for s in plan["op"]["config"]["sequence"][0]["parallel"]] == [IPHONE, GUY]
    assert done["saved"] is True and done["reloaded"] is True and done["status"] == "ok", done
    assert reloads["script"] == 1 and writes == []
    assert [(r["key"], r["name"], r["phones"], r["edited"]) for r in done["recipients"]] == [
        ("libi_send_to_guy", "Guy", [IPHONE, GUY], False)]
    assert _scripts(libi)["libi_send_to_guy"]["alias"] == "LIBI Global: Guy"
    assert hass.states.get("script.libi_send_to_guy") is not None

    # A NET that speaks to Guy, compiled as SAVE & COMPILE compiles it, and its action run.
    net = yaml_to_ast(hass, _reminder("script.libi_send_to_guy"))
    move = net["rungs"][0]["elements"][-1]
    assert (move["type"], move["mode"], move["target"]) == ("move", "tts", "script.libi_send_to_guy")
    plan2, saved = await save(client, http, [net])
    assert saved["saved"] is True and saved["status"] == "ok", saved
    action = plan2["upserts"][0]["config"]["actions"][0]
    assert action == {"action": "script.libi_send_to_guy", "data": SPOKEN}
    await hass.services.async_call("script", "libi_send_to_guy", action["data"], blocking=True)
    assert [c.data for c in calls[GUY]] == [SPOKEN]
    assert [c.data for c in calls[IPHONE]] == [{"message": "Time to go to the train", "data": SPOKEN["data"]}]
    assert calls[YULIA] == []

    # A notification with a title, and one without: no empty title, no empty data.
    await hass.services.async_call("script", "libi_send_to_guy", {"message": "Hi", "title": "Train"}, blocking=True)
    await hass.services.async_call("script", "libi_send_to_guy", {"message": "Bye"}, blocking=True)
    assert [c.data for c in calls[GUY]][1:] == [{"message": "Hi", "title": "Train"}, {"message": "Bye"}]
    assert [c.data for c in calls[IPHONE]][1:] == [{"message": "Hi", "title": "Train"}, {"message": "Bye"}]


async def test_a_phone_replaced_is_changed_once_and_no_automation_is_written(hass, libi, hass_ws_client, hass_client):
    """The user's request: tomorrow Guy has a new phone. The recipient changes, the NETs that send to it do not."""
    _phones(hass)
    calls = _phone_calls(hass)
    await home_assistant_files(hass, libi, automations=[_reminder("script.libi_send_to_guy")])
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await _global_save(client, http, phones=[GUY])
    assert done["saved"] is True, done
    before = (libi / "automations.yaml").read_text(encoding="utf-8")
    await hass.services.async_call("script", "libi_send_to_guy", SPOKEN, blocking=True)
    _plan, done = await _global_save(client, http, key="libi_send_to_guy", phones=[YULIA])
    assert done["saved"] is True and done["status"] == "ok", done
    assert done["recipients"][0]["phones"] == [YULIA]
    await hass.services.async_call("script", "libi_send_to_guy", SPOKEN, blocking=True)
    assert len(calls[GUY]) == 1 and [c.data for c in calls[YULIA]] == [SPOKEN]
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before
    # The automation that sends to Guy is listed with him.
    assert [(u["domain"], u["key"]) for u in done["recipients"][0]["used_by"]] == [("automation", "train")]


async def test_an_unchanged_recipient_is_not_sent_again(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    reloads = await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    await _global_save(client, http, phones=[GUY, YULIA])
    plan, done = await _global_save(client, http, key="libi_send_to_guy", phones=[YULIA, GUY])
    assert plan["ok"] is True and plan["unchanged"] is True and done is None
    assert reloads["script"] == 1


@pytest.mark.parametrize(("name", "phones", "said"), [
    ("  ", [GUY], "A recipient needs a name."),
    ("Yulia", [], "Tick at least one phone."),
    ("Yulia", ["notify.mobile_app_mi_9t_pro"], "notify.mobile_app_mi_9t_pro: not a phone of this Home Assistant now"),
    # Two phones registered under one name share one action, which reaches only one of them.
    ("Yulia", ["notify.mobile_app_sm_n985f"], "notify.mobile_app_sm_n985f: not a phone of this Home Assistant now"),
    # A notify action that is not a phone, or a model's choice of a service: only the phones the list offers.
    ("Yulia", ["light.turn_on"], "light.turn_on: not a phone of this Home Assistant now"),
    ("guy", [YULIA], "There is already a recipient named guy."),
])
async def test_a_recipient_that_does_not_hold_is_not_sent(hass, libi, hass_ws_client, hass_client, name, phones, said):
    _phones(hass)
    reloads = await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    await _global_save(client, http, phones=[GUY])
    before = (libi / "scripts.yaml").read_text(encoding="utf-8")
    plan, done = await _global_save(client, http, name=name, phones=phones)
    assert plan["ok"] is False and done is None
    assert plan["errors"][0].startswith(said), plan
    assert (libi / "scripts.yaml").read_text(encoding="utf-8") == before and reloads["script"] == 1


async def test_only_a_recipient_is_changed_through_global(hass, libi, hass_ws_client, hass_client):
    """Another script of the user's is not LIBI Global's to write, even by its key."""
    _phones(hass)
    lamp = {"alias": "Lamp", "sequence": [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}]}
    await home_assistant_files(hass, libi, scripts={"lamp": lamp})
    client, http = await hass_ws_client(hass), await hass_client()
    for key in ("lamp", "libi_send_to_nobody"):
        plan, done = await _global_save(client, http, key=key, phones=[GUY])
        assert plan["ok"] is False and done is None and "no longer in scripts.yaml" in plan["errors"][0]
    assert _scripts(libi) == {"lamp": lamp}
    res = await send(client, {"type": "libi/global_done", "key": "lamp", "op": "remove"})
    assert res["success"] is False and res["error"]["code"] == "invalid_key"


async def test_a_new_name_of_another_alphabet_keeps_one_key(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    he = HE["recipient_guy"]  # a name in Hebrew, as the user may give one; Home Assistant's slug spells it out
    plan, done = await _global_save(client, http, name=he, phones=[GUY])
    assert plan["op"]["key"] == "libi_send_to_gy" and done["recipients"][0]["name"] == he, (plan, done)
    _plan, done = await _global_save(client, http, key="libi_send_to_gy", name="Guy", phones=[GUY])
    assert [(r["key"], r["name"]) for r in done["recipients"]] == [("libi_send_to_gy", "Guy")]
    assert list(_scripts(libi)) == ["libi_send_to_gy"]


async def test_a_recipient_in_use_is_not_deleted(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    await home_assistant_files(hass, libi, automations=[_reminder("script.libi_send_to_guy")])
    client, http = await hass_ws_client(hass), await hass_client()
    await _global_save(client, http, phones=[GUY])
    # A NET drawn but not saved yet sends to Guy too.
    draft = yaml_to_ast(hass, _reminder("script.libi_send_to_guy", key="draft"))
    draft["name"] = "Draft reminder"
    project = libi / "libi"
    project.mkdir(exist_ok=True)
    (project / "work.libi").write_text(json.dumps({"libi_project": 1, "name": "Work_days", "nets": [draft]}),
                                       encoding="utf-8")
    plan, done = await _global_save(client, http, key="libi_send_to_guy", remove=True)
    assert plan["ok"] is False and done is None
    assert 'automation "Train reminder"' in plan["errors"][0] and 'project Work_days ▸ NET "Draft reminder"' in \
        plan["errors"][0], plan
    assert "libi_send_to_guy" in _scripts(libi)

    # A NET that sends to another recipient whose key starts the same does not keep Guy.
    other = yaml_to_ast(hass, _reminder("script.libi_send_to_guy_2", key="other"))
    (project / "work.libi").write_text(json.dumps({"libi_project": 1, "name": "Work_days", "nets": [other]}),
                                       encoding="utf-8")
    (libi / "automations.yaml").write_text(dump([]), encoding="utf-8")
    plan, done = await _global_save(client, http, key="libi_send_to_guy", remove=True)
    assert plan["ok"] is True and done["saved"] is True and done["status"] == "ok", (plan, done)
    assert done["message"] == "Deleted: Guy." and done["recipients"] == []
    assert "libi_send_to_guy" not in _scripts(libi)
    assert hass.states.get("script.libi_send_to_guy") is None


async def test_a_refused_save_is_said_and_not_saved(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await _global_save(client, http, phones=[GUY], refuse=True)
    assert done["saved"] is False and done["reloaded"] is False and done["status"] == "error"
    assert done["message"].startswith("Not saved: Home Assistant refused it: Message malformed"), done
    assert _scripts(libi) == {}


async def test_an_unreadable_scripts_yaml_lists_and_changes_nothing(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    await home_assistant_files(hass, libi)
    (libi / "scripts.yaml").write_text("lamp: [unclosed\n", encoding="utf-8")
    client, http = await hass_ws_client(hass), await hass_client()
    res = await send(client, {"type": "libi/global"})
    assert res["result"]["ok"] is False and res["result"]["errors"] == ["scripts.yaml could not be read"]
    plan, done = await _global_save(client, http, phones=[GUY])
    assert plan["ok"] is False and done is None and plan["errors"][-1] == "nothing was changed"
    assert (libi / "scripts.yaml").read_text(encoding="utf-8") == "lamp: [unclosed\n"


async def test_a_recipient_changed_outside_libi_is_said(hass, libi, hass_ws_client):
    """Changed in Home Assistant's script editor: LIBI shows the phones it calls and says it was edited."""
    _phones(hass)
    edited = recipients.recipient_config("Guy", [(GUY, True)])
    edited["sequence"].append({"action": YULIA, "data": {"message": "{{ message }}"}})
    direct = _reminder(GUY, {"message": "straight to the phone"}, key="direct")
    await home_assistant_files(hass, libi, automations=[direct], scripts={"libi_send_to_guy": edited})
    client = await hass_ws_client(hass)
    res = (await send(client, {"type": "libi/global"}))["result"]
    guy = res["recipients"][0]
    assert (guy["edited"], guy["phones"], guy["missing"]) == (True, [GUY, YULIA], [])
    # The automation that still sends straight to one of Guy's phones, to move to him.
    assert [(d["key"], d["phones"]) for d in guy["direct"]] == [("direct", [GUY])]
    # [ADDED v1.1.0] But not now: what this script does is not what LIBI wrote.
    assert guy["move_why"].startswith("it was changed outside LIBI") and guy["direct"][0]["moves"] == 0


async def test_a_net_sending_to_a_recipient_that_is_gone_is_not_saved(hass, libi, writes, hass_ws_client, hass_client):
    _phones(hass)
    reloads = await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    plan, done = await save(client, http, [yaml_to_ast(hass, _reminder("script.libi_send_to_nobody"))])
    assert done is None and plan["ok"] is False
    assert plan["errors"] == ['NET 1 "Train reminder": script.libi_send_to_nobody is a recipient of LIBI Global that '
                              "Home Assistant does not have: nothing would be sent. Pick another one in the MOVE block, "
                              "or make it again in LIBI ▸ Global."]
    assert reloads["automation"] == 0 and writes == []


async def test_a_script_net_cannot_take_a_recipients_key(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    await home_assistant_files(hass, libi)
    client, http = await hass_ws_client(hass), await hass_client()
    net = yaml_to_ast(hass, _reminder(GUY))
    net.update(level="script", name="LIBI send to Guy")
    plan, done = await save(client, http, [net])
    assert done is None and plan["ok"] is False
    assert "a name kept for the recipients of LIBI Global" in plan["errors"][0], plan
    assert _scripts(libi) == {}


@pytest.mark.parametrize("actions", [
    [{"action": "script.libi_send_to_guy", "data": SPOKEN}],
    [{"action": "script.libi_send_to_guy", "data": {"message": "Hi", "title": "Train"}}],
    # A notification and its spoken twin are one MOVE NOTIFY/TTS block.
    [{"action": "script.libi_send_to_guy", "data": {"message": "Hi"}},
     {"action": "script.libi_send_to_guy", "data": SPOKEN}],
    # [ADDED v1.1.0] A step of Home Assistant's editor moved to the recipient (libi/global_move_plan) keeps its key.
    [{"service": "script.libi_send_to_guy", "metadata": {}, "data": {"message": "Hi"}}],
])
async def test_a_net_that_sends_to_a_recipient_goes_back_as_it_was(hass, actions):
    auto = _reminder(GUY)
    auto["actions"] = copy.deepcopy(actions)
    report = verify_round_trip(hass, auto)
    assert report["ok"], report
    move = yaml_to_ast(hass, auto)["rungs"][0]["elements"][-1]
    assert move["type"] == "move" and move["target"] == "script.libi_send_to_guy"
    assert move["mode"] == {1: "tts" if "tts_text" in str(actions) else "notify", 2: "both"}[len(actions)]


def test_the_key_and_the_name_of_a_recipient():
    assert recipients.new_key("Guy & Yulia", set()) == "libi_send_to_guy_yulia"
    assert recipients.new_key("Guy", {"libi_send_to_guy"}) == "libi_send_to_guy_2"
    assert recipients.new_key("!!!", set()) == "libi_send_to_recipient"
    assert recipients.clean_name("  Guy\n\tphone  ") == "Guy phone"
    assert len(recipients.clean_name("x" * 200)) == recipients.MAX_NAME
    assert not recipients.is_recipient_key("libi_send_to_") and recipients.is_recipient_key("libi_send_to_guy")
    # The templates are kept exactly through scripts.yaml: read back, a recipient is not taken for an edited one.
    config = recipients.recipient_config("Guy", [(GUY, True), (IPHONE, False)])
    assert yaml.safe_load(dump(config)) == config
    assert recipients.read_recipient("libi_send_to_guy", yaml.safe_load(dump(config)))["edited"] is False


# ---- [ADDED v1.1.0] The phone replaced with its recipient in the automations that send straight to it ----------------

RECIPIENT = "script.libi_send_to_guy"


def _alarm(key: str, alias: str, steps: list, entity: str = "binary_sensor.smoke") -> dict:
    return {"id": key, "alias": alias, "description": "", "mode": "single",
            "triggers": [{"trigger": "state", "entity_id": entity, "to": "on"}], "conditions": [],
            "actions": copy.deepcopy(steps)}


async def _move(client, http, entries, key="libi_send_to_guy", slug=""):
    """The replacement as the panel makes it: libi/global_move_plan, each entry through Home Assistant's config API,
    libi/global_move_done. Returns the plan and what libi/global_move_done answered (None when the plan refused)."""
    planned = await send(client, {"type": "libi/global_move_plan", "key": key, "slug": slug, "entries": entries})
    assert planned["success"], planned
    plan = planned["result"]
    if not plan["ok"]:
        return plan, None
    done = []
    for op in plan["ops"]:
        resp = await http.post(f"/api/config/{op['domain']}/config/{op['key']}", json=op["config"])
        assert resp.status == 200, await resp.text()
        done.append({"domain": op["domain"], "key": op["key"], "op": op["op"]})
    finished = await send(client, {"type": "libi/global_move_done", "key": key, "done": done, "failure": None,
                                   "stamp": plan["stamp"]})
    assert finished["success"], finished
    return plan, finished["result"]


def _automations(config_dir) -> dict:
    return {a["id"]: a for a in yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8")) or []}


async def test_what_sends_straight_to_the_phone_sends_through_the_recipient_once_confirmed(hass, libi, hass_ws_client,
                                                                                          hass_client):
    """The user's request (2026-11-05): the automations made in Home Assistant's editor that send straight to Guy's
    phone send through Guy instead, the ones confirmed - only the action of those steps changes, and the phone gets what
    it got before."""
    _phones(hass)
    calls = _phone_calls(hass)
    hass.states.async_set("binary_sensor.smoke", "off")
    # As Home Assistant's editor writes them: service or action, metadata, a message and the app's data, nested steps.
    smoke = _alarm("smoke", "Alarm Smoke Sensor", [
        {"service": GUY, "metadata": {}, "data": {"message": "Smoke on the 2nd floor",
                                                  "data": {"ttl": 0, "priority": "high"}}},
        {"choose": [{"conditions": [{"condition": "state", "entity_id": "binary_sensor.smoke", "state": "on"}],
                     "sequence": [{"action": GUY, "data": {"message": "Still smoke", "title": "Smoke"}}]}]},
        # More than a phone's notify data: it would not reach the phone the same way, so it stays as it is.
        {"action": GUY, "data": {"message": "x", "target": "abc"}},
        {"action": YULIA, "data": {"message": "Smoke"}}])
    dishwasher = _alarm("dish", "Dishwasher done", [{"action": GUY, "data": {"message": "Done"}}], "binary_sensor.d")
    yulia = _alarm("yulia", "Yulia only", [{"action": YULIA, "data": {"message": "Hi"}}], "binary_sensor.y")
    announce = {"alias": "Announce", "sequence": [{"action": GUY, "data": {"message": "{{ text }}"}}]}
    reloads = await home_assistant_files(hass, libi, automations=[smoke, dishwasher, yulia],
                                         scripts={"announce": announce})
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await _global_save(client, http, phones=[GUY])
    guy = done["recipients"][0]
    assert guy["move_why"] == ""
    assert [(d["domain"], d["key"], d["moves"], d["stays"], d["why"], d["owner"]) for d in guy["direct"]] == [
        ("automation", "smoke", 2, 1, "", None), ("script", "announce", 1, 0, "", None),
        ("automation", "dish", 1, 0, "", None)]

    # The dishwasher is not ticked.
    plan, moved = await _move(client, http, [{"domain": "automation", "key": "smoke"},
                                             {"domain": "script", "key": "announce"}])
    assert plan["ok"] is True and [(op["domain"], op["key"]) for op in plan["ops"]] == [
        ("automation", "smoke"), ("script", "announce")]
    assert moved["status"] == "ok" and moved["reloaded"] is True, moved
    assert moved["message"] == "Replaced in 2: Alarm Smoke Sensor, Announce. They send through Guy from now on."
    assert reloads == {"automation": 1, "script": 2, "scene": 0}
    autos = _automations(libi)
    expected = copy.deepcopy(smoke)
    # LIBI sends it with its key kept; Home Assistant's config API writes the old service: as action:, as its own editor
    # does with every automation it saves.
    del expected["actions"][0]["service"]
    expected["actions"][0]["action"] = RECIPIENT
    expected["actions"][1]["choose"][0]["sequence"][0]["action"] = RECIPIENT
    assert autos["smoke"] == expected
    assert autos["dish"] == dishwasher and autos["yulia"] == yulia
    assert _scripts(libi)["announce"] == {"alias": "Announce", "sequence": [
        {"action": RECIPIENT, "data": {"message": "{{ text }}"}}]}
    # Still listed: the step that stays, and the dishwasher.
    guy = moved["recipients"][0]
    assert [(d["key"], d["moves"], d["stays"]) for d in guy["direct"]] == [("smoke", 0, 1), ("dish", 1, 0)]
    assert guy["direct"][0]["why"].startswith("it sends more to the phone than a message")
    assert sorted(u["key"] for u in guy["used_by"]) == ["announce", "smoke"]

    # And the phone gets what it got before, through Guy.
    hass.states.async_set("binary_sensor.smoke", "on")
    await hass.async_block_till_done()
    assert [c.data for c in calls[GUY]][:2] == [
        {"message": "Smoke on the 2nd floor", "data": {"ttl": 0, "priority": "high"}},
        {"message": "Still smoke", "title": "Smoke"}]
    assert [c.data for c in calls[YULIA]] == [{"message": "Smoke"}]
    await hass.services.async_call("script", "announce", {"text": "Hello"}, blocking=True)
    assert calls[GUY][-1].data == {"message": "Hello"}

    # Nothing left to move there: asked again, it is refused and nothing is written.
    before = (libi / "automations.yaml").read_text(encoding="utf-8")
    plan, moved = await _move(client, http, [{"domain": "automation", "key": "smoke"}])
    assert moved is None and plan["errors"][0].startswith("Alarm Smoke Sensor: it sends more to the phone"), plan
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before


async def test_what_would_not_send_the_same_is_not_moved(hass, libi, hass_ws_client, hass_client):
    """RULE 5: an entry is changed only when it then does what it did. Not one a NET of LIBI draws (its next save would
    put the phone back), not one of the project open on the page (changed there), not one not sending to the phone, not
    to a recipient of two phones - and nothing at all when a project cannot be read."""
    _phones(hass)
    drawn = _alarm("drawn", "Drawn in LIBI", [{"action": GUY, "data": {"message": "a"}}], "binary_sensor.a")
    linked = _alarm("linked", "Loaded into LIBI", [{"action": GUY, "data": {"message": "b"}}], "binary_sensor.b")
    paged = _alarm("paged", "On the page", [{"action": GUY, "data": {"message": "c"}}], "binary_sensor.c")
    lamp = _alarm("lamp", "Lamp", [{"action": "light.turn_on", "target": {"entity_id": "light.x"}}], "binary_sensor.l")
    await home_assistant_files(hass, libi, automations=[drawn, linked, paged, lamp])
    folder = libi / "libi"
    folder.mkdir(exist_ok=True)

    def project(slug, name, nets, owned):
        (folder / f"{slug}.libi").write_text(json.dumps({"libi_project": 1, "name": name, "nets": nets,
                                                         "owned": {"automations": owned}}), encoding="utf-8")

    # A NET drawn in LIBI is saved from its drawing; one loaded from Home Assistant (ha_id) is drawn from its automation.
    project("garden", "Garden", [{"id": "drawn", "name": "Drawn", "level": "automation", "rungs": []},
                                 {"id": "n2", "ha_id": "linked", "name": "Loaded", "level": "automation", "rungs": []}],
            ["drawn", "linked"])
    project("work", "Work", [{"id": "n1", "ha_id": "paged", "name": "Paged", "level": "automation", "rungs": []}],
            ["paged"])
    client, http = await hass_ws_client(hass), await hass_client()
    _plan, done = await _global_save(client, http, phones=[GUY])
    direct = {d["key"]: d for d in done["recipients"][0]["direct"]}
    assert direct["drawn"]["moves"] == 1 and direct["drawn"]["why"].startswith('a NET of LIBI project "Garden" draws it')
    assert direct["linked"]["owner"] == {"slug": "garden", "name": "Garden", "drawn": False}
    assert direct["linked"]["why"] == "" and direct["paged"]["owner"]["slug"] == "work"
    before = (libi / "automations.yaml").read_text(encoding="utf-8")

    for entries, said in (
            ([{"domain": "automation", "key": "drawn"}], 'Drawn in LIBI: a NET of LIBI project "Garden" draws it'),
            ([{"domain": "automation", "key": "paged"}], "On the page: a NET of the project open on this page"),
            ([{"domain": "automation", "key": "lamp"}], "automation lamp no longer sends straight to Guy's phone"),
            # A page's choice of an entry is not taken for it: only those listed as movable.
            ([{"domain": "scene", "key": "linked"}], "scene linked no longer sends straight to Guy's phone"),
            ([], "Nothing was ticked, so nothing was changed.")):
        plan, moved = await _move(client, http, entries, slug="work")
        assert moved is None and plan["ok"] is False and plan["errors"][0].startswith(said), (entries, plan)
    # One of them does not hold: none of them is changed.
    plan, moved = await _move(client, http, [{"domain": "automation", "key": "linked"},
                                             {"domain": "automation", "key": "drawn"}])
    assert moved is None and plan["ok"] is False
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before

    # A project that cannot be read: LIBI cannot tell whether a NET draws them.
    (folder / "broken.libi").write_text("{not json", encoding="utf-8")
    plan, moved = await _move(client, http, [{"domain": "automation", "key": "linked"}])
    assert moved is None and plan["errors"][0].startswith("project broken could not be read"), plan
    (folder / "broken.libi").unlink()

    # Not a recipient of LIBI Global's.
    res = await send(client, {"type": "libi/global_move_plan", "key": "announce", "entries": []})
    assert res["success"] is False and res["error"]["code"] == "invalid_key"
    assert (libi / "automations.yaml").read_text(encoding="utf-8") == before

    # A recipient of two phones: an automation that sends to one of them would send to both.
    _plan, done = await _global_save(client, http, name="Both", phones=[GUY, YULIA])
    both = next(r for r in done["recipients"] if r["name"] == "Both")
    assert both["move_why"].startswith("it sends to 2 phones") and {d["moves"] for d in both["direct"]} == {0}
    plan, moved = await _move(client, http, [{"domain": "automation", "key": "linked"}], key=both["key"])
    assert moved is None and plan["errors"][0].startswith("Nothing can be sent through Both: it sends to 2 phones")

    # The one loaded from Home Assistant, in a project not open, is moved: it is drawn again from its automation.
    plan, moved = await _move(client, http, [{"domain": "automation", "key": "linked"}], slug="work")
    assert moved["status"] == "ok" and moved["moved"] == ["Loaded into LIBI"], moved
    autos = _automations(libi)
    assert autos["linked"]["actions"][0]["action"] == RECIPIENT
    assert autos["drawn"] == drawn and autos["paged"] == paged and autos["lamp"] == lamp


async def test_a_move_home_assistant_refuses_is_said(hass, libi, hass_ws_client, hass_client):
    _phones(hass)
    dish = _alarm("dish", "Dishwasher done", [{"action": GUY, "data": {"message": "Done"}}])
    await home_assistant_files(hass, libi, automations=[dish])
    client, http = await hass_ws_client(hass), await hass_client()
    await _global_save(client, http, phones=[GUY])
    planned = await send(client, {"type": "libi/global_move_plan", "key": "libi_send_to_guy",
                                  "entries": [{"domain": "automation", "key": "dish"}]})
    assert planned["result"]["ok"] is True
    res = await send(client, {"type": "libi/global_move_done", "key": "libi_send_to_guy", "done": [], "stamp": "",
                              "failure": {"domain": "automation", "key": "dish", "label": "Dishwasher done",
                                          "message": "Message malformed: refused by the test", "not_sent": 0}})
    done = res["result"]
    assert done["status"] == "error" and done["moved"] == [] and done["reloaded"] is False
    assert done["message"] == ("Nothing was replaced: Dishwasher done: Home Assistant refused it: Message malformed: "
                               "refused by the test")
    # Said done by the page, but the file does not show it: not moved.
    res = await send(client, {"type": "libi/global_move_done", "key": "libi_send_to_guy", "stamp": "",
                              "done": [{"domain": "automation", "key": "dish", "op": "upsert"}]})
    assert res["result"]["moved"] == [] and "its file does not show the change" in res["result"]["message"]
    assert _automations(libi)["dish"] == dish


def test_only_a_step_the_recipient_passes_on_as_it_is_moves():
    def moves(step):
        return recipients.move_entry("automation", {"actions": [step]}, GUY, RECIPIENT)[1:]

    assert moves({"action": GUY, "data": {"message": "Hi", "title": "T", "data": {"ttl": 0}}}) == (1, 0)
    assert moves({"service": GUY, "metadata": {}, "alias": "Tell Guy", "enabled": False, "continue_on_error": True,
                  "data": {"message": "Hi"}}) == (1, 0)
    for step in ({"action": GUY, "data": {}},  # no message: it fails as it is; through Guy it would not
                 {"action": GUY, "data": "{{ {'message': 'Hi'} }}"},  # a template: what it holds is not known
                 {"action": GUY, "data_template": {"message": "Hi"}},
                 {"action": GUY, "target": {"entity_id": "x"}, "data": {"message": "Hi"}},
                 {"action": GUY, "response_variable": "r", "data": {"message": "Hi"}},
                 {"action": GUY, "data": {"message": "Hi", "target": ["x"]}}):
        assert moves(step) == (0, 1), step
    assert moves({"action": YULIA, "data": {"message": "Hi"}}) == (0, 0)
    # The original is not changed; a script's steps are its sequence.
    config = {"sequence": [{"parallel": [{"action": GUY, "data": {"message": "Hi"}}]}]}
    moved, count, _kept = recipients.move_entry("script", config, GUY, RECIPIENT)
    assert count == 1 and moved["sequence"][0]["parallel"][0]["action"] == RECIPIENT
    assert config["sequence"][0]["parallel"][0]["action"] == GUY
