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
# [ADDED v1.69.0] Added preview_yaml command to generate YAML strings on the fly for the UI sidebar.
# [ADDED v2.0.0 | 2026-08-17] Purpose: Import now returns a round trip verification next to the net,
#   so an automation that would not survive editing is flagged before the user touches it, and a
#   standalone verify command lets the panel check every automation without importing it.
# [ADDED v3.2.0 | 2026-08-20] Purpose: Updated imports to point to the renamed libi_to_yaml file.
# [ADDED v3.3.0 | 2026-08-20] Purpose: Fully migrated all internal references, file outputs, and API routes from ladder_ha to libi.
# [ADDED v3.5.0 | 2026-08-24] Purpose: A net now compiles by its level. Automations, scripts and
#   scenes are three different schemas, and each one is merged into the very file Home Assistant's
#   own editor writes: automations.yaml, scripts.yaml and scenes.yaml. Every default installation
#   already includes those three from configuration.yaml, so LIBI needs no configuration change and
#   no include line. Entries LIBI wrote before are replaced, everything the user wrote by hand is
#   left alone, and the matching reload service is called so nothing needs a restart.
import logging
import json
import os
from typing import Any, Optional, Type
import yaml

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .libi_to_yaml import ast_to_yaml, verify_round_trip, net_level, slugify
from .yaml_to_libi import yaml_to_ast

try:
    from pydantic import BaseModel, Field, ValidationError, root_validator
except ImportError:
    from pydantic.v1 import BaseModel, Field, ValidationError, root_validator

_LOGGER = logging.getLogger(__name__)

def _get_ast_path(hass: HomeAssistant) -> str: return hass.config.path("libi_ast.json")

# [CHANGED v3.5.0] These are the three files Home Assistant's own automation, script and scene
# editors read and write, and the three a fresh configuration.yaml already includes. Writing here is
# what lets LIBI stay a pure config entry integration: the user adds nothing to any YAML file.
def _get_automations_path(hass: HomeAssistant) -> str: return hass.config.path("automations.yaml")
def _get_scripts_path(hass: HomeAssistant) -> str: return hass.config.path("scripts.yaml")
def _get_scenes_path(hass: HomeAssistant) -> str: return hass.config.path("scenes.yaml")

# LIBI wrote its own file before v3.5.0. If an install still has an include line pointing at it, the
# file is emptied once on upgrade so the same automation cannot appear twice.
def _get_legacy_yaml_path(hass: HomeAssistant) -> str: return hass.config.path("libi_automations.yaml")

# What an empty net looks like per level. An automation with no actions, a script with no sequence
# and a scene with no entities are all half drawn rungs and are not written out.
_LEVEL_BODY_KEY = {"automation": "actions", "script": "sequence", "scene": "entities"}

# Which Home Assistant domain owns each level, used for the reload call after the write.
_LEVEL_DOMAIN = {"automation": "automation", "script": "script", "scene": "scene"}

def _read_ast_sync(hass: HomeAssistant) -> dict:
    path = _get_ast_path(hass)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    return {"nets": []}

def _read_target_sync(path: str, empty):
    """Reads one of Home Assistant's own files. Returns None when the file cannot be read or is not
    the shape it should be, and None means LIBI leaves that file completely alone rather than
    overwriting something it does not understand."""
    if not os.path.exists(path):
        return type(empty)()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] %s could not be read, leaving it untouched: %s", path, err)
        return None
    if data is None:
        return type(empty)()
    if not isinstance(data, type(empty)):
        _LOGGER.error("[libi] %s is not a %s, leaving it untouched", path, type(empty).__name__)
        return None
    return data

def _write_if_changed_sync(path: str, data, skip_when_empty: bool) -> bool:
    """Writes only when the result differs from what is already on disk, so an untouched domain is
    never rewritten and never reloaded. Returns whether the file was written."""
    if skip_when_empty and not data and not os.path.exists(path):
        return False
    new_text = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                if f.read() == new_text:
                    return False
        except Exception:  # noqa: BLE001
            pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return True

def _merge_list_sync(existing: list, mine: list, owned_ids: set) -> list:
    """Keeps every entry the user wrote by hand and replaces only the ones LIBI owns. Ownership is
    the id, both the ids LIBI is writing now and the ids it wrote the previous time, so a net that
    was renamed or deleted does not leave an orphan behind. An entry that is being replaced keeps
    its place in the file, so re-saving does not shuffle the order the user sees in the editor."""
    by_id = {str(item.get("id", "")): item for item in mine if isinstance(item, dict) and item.get("id")}
    out = []
    placed = set()
    for item in existing:
        key = str(item.get("id", "")) if isinstance(item, dict) else ""
        if key and key in by_id:
            out.append(by_id[key])
            placed.add(key)
        elif key and key in owned_ids:
            continue  # LIBI wrote this last time and no longer owns it
        else:
            out.append(item)
    out.extend(item for item in mine
               if not isinstance(item, dict) or str(item.get("id", "")) not in placed)
    return out

def _merge_map_sync(existing: dict, mine: dict, owned_keys: set) -> dict:
    """The same rule for scripts.yaml, which is a mapping keyed by object id rather than a list. A
    key that is being rewritten keeps its position, since a dict preserves insertion order."""
    out = {}
    for key, value in existing.items():
        if key in mine:
            out[key] = mine[key]
        elif key in owned_keys:
            continue  # LIBI wrote this last time and no longer owns it
        else:
            out[key] = value
    for key, value in mine.items():
        out.setdefault(key, value)
    return out

def _migrate_legacy_file_sync(hass: HomeAssistant) -> None:
    """An install upgrading from an earlier LIBI may still include libi_automations.yaml. The file is
    emptied rather than deleted, so an include line that points at it stays valid and stops producing
    a duplicate of every automation LIBI now writes into automations.yaml."""
    path = _get_legacy_yaml_path(hass)
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read().strip() in ("", "[]"):
                return
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]\n")
        _LOGGER.warning("[libi] libi_automations.yaml is no longer used and was emptied. LIBI now "
                        "writes into automations.yaml, the same file the Home Assistant editor uses. "
                        "The include line for it can be removed from configuration.yaml.")
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] could not empty the old libi_automations.yaml: %s", err)

def _write_ast_and_yaml_sync(hass: HomeAssistant, payload: dict) -> dict:
    """Compiles every net and merges the result into Home Assistant's own three files. Returns the
    domains whose file actually changed, so only those get reloaded."""
    previous = (_read_ast_sync(hass).get("libi_owned") or {})

    automations = []
    scripts: dict[str, Any] = {}
    scenes = []
    errors = []
    for net in payload.get("nets", []):
        level = net_level(net)
        try:
            compiled = ast_to_yaml(hass, net)
            # A net that compiles to nothing is almost always a half drawn rung. It stays in the AST
            # file but is not written out, so nothing silently breaks.
            if not compiled.get(_LEVEL_BODY_KEY.get(level, "actions")):
                _LOGGER.warning("[libi] %s net %s is empty, skipped in the output", level, net.get("name"))
                continue
            if level == "script":
                # scripts.yaml is a mapping, so the net needs an object id. The name becomes a slug and
                # a repeated name gets a number rather than quietly overwriting the net before it.
                base = slugify(net.get("name"), fallback="libi_" + slugify(net.get("id"), "script"))
                slug = base
                counter = 2
                while slug in scripts:
                    slug = f"{base}_{counter}"
                    counter += 1
                scripts[slug] = compiled
            elif level == "scene":
                scenes.append(compiled)
            else:
                automations.append(compiled)
        except Exception as e:
            _LOGGER.error(f"Failed to compile net {net.get('name')}: {e}")
            errors.append(f"{net.get('name')}: {e}")

    owned = {
        "automations": [str(a.get("id", "")) for a in automations if a.get("id")],
        "scripts": sorted(scripts.keys()),
        "scenes": [str(s.get("id", "")) for s in scenes if s.get("id")],
    }

    _migrate_legacy_file_sync(hass)

    changed = []
    plans = (
        ("automation", _get_automations_path(hass), [], automations,
         set(owned["automations"]) | set(previous.get("automations") or [])),
        ("script", _get_scripts_path(hass), {}, scripts,
         set(owned["scripts"]) | set(previous.get("scripts") or [])),
        ("scene", _get_scenes_path(hass), [], scenes,
         set(owned["scenes"]) | set(previous.get("scenes") or [])),
    )
    for domain, path, empty, mine, owned_keys in plans:
        existing = _read_target_sync(path, empty)
        if existing is None:
            errors.append(f"{os.path.basename(path)} could not be read and was left untouched")
            continue
        merged = _merge_map_sync(existing, mine, owned_keys) if isinstance(empty, dict) \
            else _merge_list_sync(existing, mine, owned_keys)
        if _write_if_changed_sync(path, merged, skip_when_empty=not mine and not owned_keys):
            changed.append(domain)

    # The AST is written last and carries the ownership record, so the next save knows exactly which
    # entries in Home Assistant's files belong to LIBI.
    stored = dict(payload)
    stored["libi_owned"] = owned
    with open(_get_ast_path(hass), "w", encoding="utf-8") as f: json.dump(stored, f, indent=2)

    return {"changed": changed, "errors": errors,
            "counts": {"automations": len(automations), "scripts": len(scripts), "scenes": len(scenes)}}

def _get_all_automations(hass: HomeAssistant):
    autos = []
    path = _get_automations_path(hass)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
            if isinstance(data, list):
                for a in data: autos.append({"id": a.get("id"), "name": a.get("alias", f"Automation {a.get('id')}"), "raw": a})
    return autos

class SaveAutomationCommand(BaseModel):
    id: int
    payload: dict[str, Any] = Field(default_factory=dict)
    @root_validator(pre=True)
    def normalize(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "payload" not in values and "nets" in values: values["payload"] = {"nets": values["nets"]}
        return values

def async_register_websockets(hass: HomeAssistant) -> None:
    ws_handle_save_automation._ws_command = "libi/save_automation"
    ws_handle_save_automation._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({vol.Required("type"): "libi/save_automation"}, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_save_automation)
    
    ws_handle_load_automation._ws_command = "libi/load_automation"
    ws_handle_load_automation._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({vol.Required("type"): "libi/load_automation"}, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_load_automation)
    
    ws_handle_list_automations._ws_command = "libi/list_automations"
    ws_handle_list_automations._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({vol.Required("type"): "libi/list_automations"}, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_list_automations)

    ws_handle_get_automation._ws_command = "libi/get_automation"
    ws_handle_get_automation._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/get_automation",
        vol.Required("automation_id"): str
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_get_automation)

    ws_handle_delete_automation._ws_command = "libi/delete_automation"
    ws_handle_delete_automation._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/delete_automation",
        vol.Required("automation_id"): str
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_delete_automation)

    ws_handle_verify_automation._ws_command = "libi/verify_automation"
    ws_handle_verify_automation._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/verify_automation",
        vol.Optional("automation_id"): str
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_verify_automation)

    ws_handle_preview_yaml._ws_command = "libi/preview_yaml"
    ws_handle_preview_yaml._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/preview_yaml",
        vol.Required("net"): dict
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, ws_handle_preview_yaml)
    
    _LOGGER.info("[libi] WebSocket commands registered.")

@websocket_api.async_response
async def ws_handle_save_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try: validated = SaveAutomationCommand.parse_obj(msg)
    except Exception as err:
        connection.send_error(msg.get("id", 0), "invalid_format", str(err))
        return
    result = await hass.async_add_executor_job(_write_ast_and_yaml_sync, hass, validated.payload or {})
    # [ADDED v3.5.0] Reloading through the service is what makes the change live without a restart,
    # and it is the same call the Home Assistant editors make after they save.
    errors = list(result.get("errors") or [])
    for domain in result.get("changed") or []:
        try:
            await hass.services.async_call(domain, "reload", blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] %s reload failed: %s", domain, err)
            errors.append(f"{domain} reload failed: {err}")
    counts = result.get("counts") or {}
    message = ("Saved. {automations} automations, {scripts} scripts, {scenes} scenes written into "
               "Home Assistant.").format(automations=counts.get("automations", 0),
                                         scripts=counts.get("scripts", 0),
                                         scenes=counts.get("scenes", 0))
    if errors:
        message += " Problems: " + "; ".join(errors[:5])
    connection.send_result(msg.get("id", 0), {"status": "error" if errors else "ok",
                                              "message": message,
                                              "reloaded": result.get("changed") or [],
                                              "errors": errors})

@websocket_api.async_response
async def ws_handle_load_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    data = await hass.async_add_executor_job(_read_ast_sync, hass)
    connection.send_result(msg.get("id", 0), data)

@websocket_api.async_response
async def ws_handle_list_automations(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    autos = await hass.async_add_executor_job(_get_all_automations, hass)
    res = [{"id": a["id"], "name": a["name"]} for a in autos]
    connection.send_result(msg.get("id", 0), {"automations": res})

@websocket_api.async_response
async def ws_handle_get_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    auto_id = msg.get("automation_id")
    autos = await hass.async_add_executor_job(_get_all_automations, hass)
    target = next((a for a in autos if a["id"] == auto_id), None)
    if not target:
        connection.send_error(msg.get("id", 0), "not_found", "Automation not found")
        return
    try:
        ast_net = yaml_to_ast(hass, target["raw"])
        report = verify_round_trip(hass, target["raw"])
        if not report.get("ok"):
            _LOGGER.warning("[libi] %s does not round trip cleanly: %s", auto_id, report.get("issues"))
        connection.send_result(msg.get("id", 0), {"net": ast_net, "verify": report})
    except Exception as e:
        connection.send_error(msg.get("id", 0), "parse_error", str(e))


@websocket_api.async_response
async def ws_handle_verify_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Imports and compiles back without writing anything, and reports what did not survive."""
    auto_id = msg.get("automation_id")
    autos = await hass.async_add_executor_job(_get_all_automations, hass)
    if auto_id:
        autos = [a for a in autos if a["id"] == auto_id]
    results = []
    for a in autos:
        report = verify_round_trip(hass, a["raw"])
        results.append({"id": a["id"], "name": a["name"], "ok": report.get("ok"),
                        "issues": report.get("issues", []), "count": report.get("count", 0)})
    connection.send_result(msg.get("id", 0), {"results": results,
                                              "ok": all(r["ok"] for r in results) if results else True})

@websocket_api.async_response
async def ws_handle_delete_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    auto_id = msg.get("automation_id")
    path = _get_automations_path(hass)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        if isinstance(data, list):
            new_data = [a for a in data if a.get("id") != auto_id]
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(new_data, f, default_flow_style=False, allow_unicode=True)
            await hass.services.async_call("automation", "reload")
    connection.send_result(msg.get("id", 0), {"status": "ok"})

@websocket_api.async_response
async def ws_handle_preview_yaml(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    net_ast = msg.get("net", {})
    try:
        yaml_dict = ast_to_yaml(hass, net_ast)
        yaml_str = yaml.dump(yaml_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        connection.send_result(msg.get("id", 0), {"yaml": yaml_str})
    except Exception as e:
        connection.send_error(msg.get("id", 0), "preview_error", str(e))