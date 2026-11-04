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
# [ADDED v3.85.0 | 2026-11-04] Purpose: SAVE & COMPILE as the panel makes it, against a real Home Assistant -
#   libi/compile_project, each change through Home Assistant's own config API, libi/save_done.
"""SAVE & COMPILE as the panel makes it, for the tests: libi/compile_project, then each change through Home Assistant's
own config API - the endpoints its automation, script and scene editors use - then libi/save_done."""
import copy

import yaml
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

CONFIGURATION = "automation: !include automations.yaml\nscript: !include scripts.yaml\nscene: !include scenes.yaml\n"


def dump(data) -> str:
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


async def home_assistant_files(hass: HomeAssistant, config_dir, automations=None, scripts=None, scenes=None) -> dict:
    """Home Assistant's automation, script and scene integrations, set up from this test's folder - the files its config
    API writes - so a save through that API reloads for real. Returns the reload calls, counted per domain. Home
    Assistant normalises a config it is set up with in place (trigger becomes triggers), so it gets a copy."""
    (config_dir / "configuration.yaml").write_text(CONFIGURATION, encoding="utf-8")
    for name, data, empty in (("automations.yaml", automations, []), ("scripts.yaml", scripts, {}),
                              ("scenes.yaml", scenes, [])):
        path = config_dir / name
        if data is not None or not path.exists():
            path.write_text(dump(data if data is not None else empty), encoding="utf-8")
    assert await async_setup_component(hass, "automation", {"automation": copy.deepcopy(automations or [])})
    assert await async_setup_component(hass, "script", {"script": copy.deepcopy(scripts or {})})
    assert await async_setup_component(hass, "scene", {"scene": copy.deepcopy(scenes or [])})
    await hass.async_block_till_done()
    calls = {"automation": 0, "script": 0, "scene": 0}

    def count(event) -> None:
        if event.data.get("service") == "reload" and event.data.get("domain") in calls:
            calls[event.data["domain"]] += 1

    hass.bus.async_listen(EVENT_CALL_SERVICE, count)
    return calls


async def send(client, msg: dict) -> dict:
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def save(client, http, nets: list, slug: str = "p", name: str = "P", refuse: tuple = ()) -> tuple[dict, dict | None]:
    """SAVE & COMPILE as the panel makes it. The changes go through Home Assistant's config API one by one, and the first
    one refused stops the rest, as in the panel; a key in `refuse` is refused as Home Assistant refuses an entry it does
    not accept. Returns the plan and what libi/save_done answered (None when the plan refused the save)."""
    planned = await send(client, {"type": "libi/compile_project", "slug": slug, "name": name, "nets": nets})
    assert planned["success"], planned
    plan = planned["result"]
    if not plan["ok"]:
        return plan, None
    ops = ([dict(op, op="upsert") for op in plan["upserts"]] + [dict(op, op="remove") for op in plan["removals"]])
    done, failure = [], None
    for index, op in enumerate(ops):
        url = f"/api/config/{op['domain']}/config/{op['key']}"
        if op["key"] in refuse:
            status, message = 400, "Message malformed: refused by the test"
        else:
            resp = await (http.post(url, json=op["config"]) if op["op"] == "upsert" else http.delete(url))
            status = resp.status
            message = (await resp.json()).get("message", "") if status != 200 else ""
        if status != 200:
            failure = {"domain": op["domain"], "key": op["key"], "op": op["op"], "label": op.get("label", ""),
                       "message": message, "not_sent": len(ops) - index - 1}
            break
        done.append({"domain": op["domain"], "key": op["key"], "op": op["op"]})
    finished = await send(client, {"type": "libi/save_done", "slug": slug, "name": name, "nets": nets, "done": done,
                                   "failure": failure, "stamp": plan["stamp"]})
    assert finished["success"], finished
    return plan, finished["result"]
