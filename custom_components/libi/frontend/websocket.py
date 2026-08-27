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
# [ADDED v3.14.0 | 2026-08-26] Purpose: A workspace is now a named project stored as a .libi file.
#   Opening "kitchen" and saving it must never touch what "garden" wrote, so the record of which
#   entries in Home Assistant's files belong to LIBI is kept per project rather than globally. A
#   project remembers every net exactly as it was left, unfinished logic included, and which
#   automation each net was loaded from. Deleting a project deletes only the .libi file.
# [ADDED v3.15.0 | 2026-08-26] Purpose: Opening a project reloads. A net anchored to an automation is
#   read fresh out of automations.yaml and converted to ladder again, so whichever project is opened
#   always shows the newest version and the same automation may sit in several projects without any
#   of them going stale. A net with no anchor is a draft that no YAML could hold, so it comes back
#   from the drawing saved in the .libi file, and so does an anchored net whose automation has since
#   been deleted from Home Assistant, which is then flagged as orphaned.
import logging
import json
import os
import re
from datetime import datetime, timezone
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

# [ADDED v3.14.0] Projects live in one folder of their own inside the configuration directory, so a
# backup of the configuration carries them and the user can copy a .libi file between machines.
PROJECT_EXT = ".libi"
PROJECT_DIR_NAME = "libi"

def _get_projects_dir(hass: HomeAssistant) -> str:
    return hass.config.path(PROJECT_DIR_NAME)

def _project_path(hass: HomeAssistant, slug: str) -> str:
    return os.path.join(_get_projects_dir(hass), f"{slug}{PROJECT_EXT}")

# Characters no file system will take, plus the ones that would let a name escape the folder.
_UNSAFE_IN_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def project_slug(name: str, fallback: str = "project") -> str:
    """The file name for a project. The name is kept as the user wrote it, Hebrew included, because
    a .libi file is meant to be found and copied by hand. Only characters that no file system will
    accept are stripped, and a name that leaves nothing behind falls back to a latin slug."""
    cleaned = _UNSAFE_IN_FILENAME.sub("", str(name or "")).strip().strip(".")
    cleaned = re.sub(r"\s+", "_", cleaned)
    if not cleaned or cleaned in (".", ".."):
        return slugify(name, fallback=fallback)
    return cleaned[:80]

def _read_project_sync(hass: HomeAssistant, slug: str) -> Optional[dict]:
    path = _project_path(hass, slug)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] project %s could not be read: %s", slug, err)
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("slug", slug)
    data.setdefault("name", slug)
    data.setdefault("nets", [])
    data.setdefault("owned", {})
    return data

def _list_projects_sync(hass: HomeAssistant) -> list:
    directory = _get_projects_dir(hass)
    out = []
    if not os.path.isdir(directory):
        return out
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(PROJECT_EXT):
            continue
        slug = fname[: -len(PROJECT_EXT)]
        data = _read_project_sync(hass, slug)
        if data is None:
            continue
        out.append({
            "slug": slug,
            "name": data.get("name") or slug,
            "nets": len(data.get("nets") or []),
            "updated": data.get("updated") or "",
        })
    return out

def _all_owned_except_sync(hass: HomeAssistant, keep_slug: str) -> dict:
    """Everything the other projects currently claim. Nothing in here is ever removed while saving
    this project, which is what stops one workspace from wiping another's automations."""
    out = {"automations": set(), "scripts": set(), "scenes": set()}
    for entry in _list_projects_sync(hass):
        if entry["slug"] == keep_slug:
            continue
        data = _read_project_sync(hass, entry["slug"]) or {}
        owned = data.get("owned") or {}
        for key in out:
            for item in (owned.get(key) or []):
                out[key].add(str(item))
    return out

def _migrate_single_ast_sync(hass: HomeAssistant) -> None:
    """An installation from before projects has one drawing in libi_ast.json. It becomes a project
    called Default on first use. The original file is left where it is, untouched."""
    directory = _get_projects_dir(hass)
    os.makedirs(directory, exist_ok=True)
    if any(f.endswith(PROJECT_EXT) for f in os.listdir(directory)):
        return
    legacy = _read_ast_sync(hass)
    if not (legacy.get("nets") or []):
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_project_sync(hass, "default", {
        "libi_project": 1, "slug": "default", "name": "Default",
        "created": now, "updated": now,
        "nets": legacy.get("nets") or [],
        "owned": legacy.get("libi_owned") or {},
    })
    _LOGGER.warning("[libi] the drawing in libi_ast.json was carried into a project called Default")

def _write_project_sync(hass: HomeAssistant, slug: str, data: dict) -> None:
    os.makedirs(_get_projects_dir(hass), exist_ok=True)
    with open(_project_path(hass, slug), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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

def _write_ast_and_yaml_sync(hass: HomeAssistant, payload: dict, slug: str = "", name: str = "") -> dict:
    """Compiles every net of one project and merges the result into Home Assistant's own three files.

    [CHANGED v3.14.0] The record of what LIBI owns is read from this project and from no other. Two
    projects can sit side by side in automations.yaml and saving one leaves the other alone, which
    is the whole point of having projects at all."""
    slug = slug or "default"
    _migrate_single_ast_sync(hass)
    project = _read_project_sync(hass, slug) or {}
    previous = project.get("owned") or {}
    # What the other projects claim right now. These ids are off limits no matter what this project
    # used to own, so a shared or copied id can never be deleted out from under another workspace.
    protected = _all_owned_except_sync(hass, slug)

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
         (set(owned["automations"]) | set(previous.get("automations") or [])) - protected["automations"]),
        ("script", _get_scripts_path(hass), {}, scripts,
         (set(owned["scripts"]) | set(previous.get("scripts") or [])) - protected["scripts"]),
        ("scene", _get_scenes_path(hass), [], scenes,
         (set(owned["scenes"]) | set(previous.get("scenes") or [])) - protected["scenes"]),
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

    # The project file is written last and carries the ownership record, so the next save of THIS
    # project knows exactly which entries in Home Assistant's files are its own.
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_project_sync(hass, slug, {
        "libi_project": 1,
        "slug": slug,
        "name": name or project.get("name") or slug,
        "created": project.get("created") or now,
        "updated": now,
        # Every net exactly as it was left, unfinished logic and all, including which automation each
        # one was loaded from, which is the ha_id carried on the net.
        "nets": payload.get("nets", []),
        "owned": owned,
    })

    return {"changed": changed, "errors": errors, "slug": slug,
            "counts": {"automations": len(automations), "scripts": len(scripts), "scenes": len(scenes)}}


def _delete_project_sync(hass: HomeAssistant, slug: str) -> dict:
    """Removes the .libi file and nothing else. The automations, scripts and scenes this project
    compiled stay exactly where they are in Home Assistant, because they are Home Assistant's now."""
    path = _project_path(hass, slug)
    if not os.path.exists(path):
        return {"ok": False, "error": "no such project"}
    try:
        os.remove(path)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] could not delete project %s: %s", slug, err)
        return {"ok": False, "error": str(err)}
    return {"ok": True}


def _create_project_sync(hass: HomeAssistant, name: str) -> dict:
    """A new, empty workspace. The name is kept as the user typed it and the file gets a slug."""
    _migrate_single_ast_sync(hass)
    base = project_slug(name, fallback="project")
    slug = base
    counter = 2
    while os.path.exists(_project_path(hass, slug)):
        slug = f"{base}_{counter}"
        counter += 1
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_project_sync(hass, slug, {
        "libi_project": 1, "slug": slug, "name": name or slug,
        "created": now, "updated": now, "nets": [], "owned": {},
    })
    return {"slug": slug, "name": name or slug}

def _automations_by_id_sync(hass: HomeAssistant) -> dict:
    """[ADDED v3.15.0] Everything in automations.yaml, keyed by its id."""
    out = {}
    path = _get_automations_path(hass)
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] automations.yaml could not be read while opening a project: %s", err)
        return out
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id") is not None:
                out[str(item["id"])] = item
    return out


def _hydrate_project_nets_sync(hass: HomeAssistant, nets: list) -> dict:
    """[ADDED v3.15.0] Turns what the project stored into what the canvas should show.

    A net that names an automation is rebuilt from that automation as it stands right now, so the
    newest version always wins. The things the ladder holds and YAML does not, the position of the
    net, whether it was collapsed and the level it was drawn at, are carried over from the project.
    A net with no anchor, or one whose automation is gone, keeps the drawing that was saved."""
    live = _automations_by_id_sync(hass)
    out = []
    stats = {"reloaded": 0, "draft": 0, "orphan": 0}

    for stored in (nets or []):
        if not isinstance(stored, dict):
            continue
        ha_id = str(stored.get("ha_id") or "")
        level = net_level(stored)

        # Only an automation has an anchor to reload from. A script or a scene keeps its drawing.
        if ha_id and level == "automation" and ha_id in live:
            try:
                fresh = yaml_to_ast(hass, live[ha_id])
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("[libi] could not rebuild net %s from automation %s: %s",
                              stored.get("name"), ha_id, err)
                keep = dict(stored)
                keep["source"] = "draft"
                keep["source_note"] = f"Could not be rebuilt from Home Assistant: {err}"
                out.append(keep)
                stats["draft"] += 1
                continue
            # The identity of the net in this project is the project's, not the importer's.
            fresh["id"] = stored.get("id") or fresh.get("id")
            fresh["ha_id"] = ha_id
            fresh["collapsed"] = bool(stored.get("collapsed"))
            fresh["level"] = level
            fresh["source"] = "ha"
            out.append(fresh)
            stats["reloaded"] += 1
            continue

        keep = dict(stored)
        if ha_id and level == "automation":
            # It was linked to an automation and that automation is no longer there.
            keep["source"] = "orphan"
            keep["source_note"] = "The automation this net was loaded from is no longer in Home Assistant. The saved drawing is shown instead."
            stats["orphan"] += 1
        else:
            keep["source"] = "draft"
            stats["draft"] += 1
        out.append(keep)

    return {"nets": out, "stats": stats}


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
    # [ADDED v3.14.0] The project commands behind the four items of the header menu.
    ws_handle_project_list._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/project_list"
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, "libi/project_list", ws_handle_project_list, ws_handle_project_list._ws_schema)

    ws_handle_project_open._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/project_open",
        vol.Required("slug"): str
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, "libi/project_open", ws_handle_project_open, ws_handle_project_open._ws_schema)

    ws_handle_project_create._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/project_create",
        vol.Required("name"): str
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, "libi/project_create", ws_handle_project_create, ws_handle_project_create._ws_schema)

    ws_handle_project_delete._ws_schema = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        vol.Required("type"): "libi/project_delete",
        vol.Required("slug"): str
    }, extra=vol.ALLOW_EXTRA)
    websocket_api.async_register_command(hass, "libi/project_delete", ws_handle_project_delete, ws_handle_project_delete._ws_schema)

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
    # [CHANGED v3.14.0] The save belongs to a project. Without a slug it is the Default workspace,
    # which is what an installation from before projects is migrated into.
    slug = str(msg.get("slug") or "default")
    name = str(msg.get("name") or "")
    result = await hass.async_add_executor_job(
        _write_ast_and_yaml_sync, hass, validated.payload or {}, slug, name)
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
                                              "slug": result.get("slug") or slug,
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

# [ADDED v3.14.0] ---------------------------------------------------------------- projects

@websocket_api.async_response
async def ws_handle_project_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    await hass.async_add_executor_job(_migrate_single_ast_sync, hass)
    projects = await hass.async_add_executor_job(_list_projects_sync, hass)
    connection.send_result(msg.get("id", 0), {"projects": projects})


@websocket_api.async_response
async def ws_handle_project_open(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    slug = str(msg.get("slug") or "")
    data = await hass.async_add_executor_job(_read_project_sync, hass, slug)
    if data is None:
        connection.send_error(msg.get("id", 0), "not_found", f"No project called {slug}")
        return
    # [CHANGED v3.15.0] Anchored nets are rebuilt from Home Assistant as it stands now, drafts and
    # orphans come back from the drawing the project saved.
    hydrated = await hass.async_add_executor_job(
        _hydrate_project_nets_sync, hass, data.get("nets") or [])
    connection.send_result(msg.get("id", 0), {
        "slug": data.get("slug") or slug,
        "name": data.get("name") or slug,
        "nets": hydrated["nets"],
        "stats": hydrated["stats"],
        "updated": data.get("updated") or "",
    })


@websocket_api.async_response
async def ws_handle_project_create(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    name = str(msg.get("name") or "").strip()
    if not name:
        connection.send_error(msg.get("id", 0), "bad_name", "A project needs a name")
        return
    created = await hass.async_add_executor_job(_create_project_sync, hass, name)
    connection.send_result(msg.get("id", 0), created)


@websocket_api.async_response
async def ws_handle_project_delete(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    slug = str(msg.get("slug") or "")
    result = await hass.async_add_executor_job(_delete_project_sync, hass, slug)
    if not result.get("ok"):
        connection.send_error(msg.get("id", 0), "delete_failed", result.get("error") or "could not delete")
        return
    # Nothing was reloaded and nothing was removed from Home Assistant. Only the drawing is gone.
    connection.send_result(msg.get("id", 0), {
        "status": "ok",
        "message": "The project file was deleted. Everything it compiled is still in Home Assistant.",
    })


@websocket_api.async_response
async def ws_handle_preview_yaml(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    net_ast = msg.get("net", {})
    try:
        yaml_dict = ast_to_yaml(hass, net_ast)
        yaml_str = yaml.dump(yaml_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        connection.send_result(msg.get("id", 0), {"yaml": yaml_str})
    except Exception as e:
        connection.send_error(msg.get("id", 0), "preview_error", str(e))