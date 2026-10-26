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
# [ADDED v3.34.0 | 2026-10-26] Purpose: Every command is admin only and has a strict schema, a
#   project slug can no longer name a path outside the projects folder, a save refuses to write
#   anything when one of Home Assistant's files cannot be read, files are written atomically under
#   one lock, and deleting an automation follows the same read, merge and reload rules as a save.
#   Saving a project with a script net no longer writes the project under the script's name.
# [ADDED v3.36.0 | 2026-10-26] Purpose: The AI chat commands ai_status, ai_plan and ai_build. They
#   only ever return a DRAFT net; writing it to Home Assistant stays the ordinary save. See ai.py.
import asyncio
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol
import yaml

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.file import write_utf8_file_atomic

from . import ai
from .libi_to_yaml import ast_to_yaml, verify_round_trip, net_level, slugify
from .yaml_to_libi import yaml_to_ast

_LOGGER = logging.getLogger(__name__)

# [ADDED v3.34.0] Every read-modify-write of automations.yaml, scripts.yaml, scenes.yaml and the
# project files runs in the executor, so two saves can overlap. One lock makes each of them whole.
_FILE_LOCK = threading.Lock()


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


def valid_project_slug(slug: str) -> bool:
    """[ADDED v3.34.0] A slug that arrives from the browser names a file inside the projects folder
    and nothing else. A separator, a control character or a leading dot is refused rather than
    cleaned, so "../x" can never be turned into some other file. A file copied in by hand keeps
    working, spaces and all, because only what could escape the folder is refused."""
    slug = str(slug or "")
    return (bool(slug) and len(slug) <= 120 and not slug.startswith(".")
            and not _UNSAFE_IN_FILENAME.search(slug))


def _read_project_sync(hass: HomeAssistant, slug: str) -> dict | None:
    path = _project_path(hass, slug)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
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
        if not valid_project_slug(slug):
            continue
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
    # [CHANGED v3.34.0] Atomic, so a crash halfway through cannot leave half a project behind.
    write_utf8_file_atomic(_project_path(hass, slug),
                           json.dumps(data, indent=2, ensure_ascii=False))

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

def _read_ast_sync(hass: HomeAssistant) -> dict:
    path = _get_ast_path(hass)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f: return json.load(f)
    return {"nets": []}

def _read_target_sync(path: str, empty):
    """Reads one of Home Assistant's own files. Returns None when the file cannot be read or is not
    the shape it should be, and None means LIBI leaves that file completely alone rather than
    overwriting something it does not understand."""
    if not os.path.exists(path):
        return type(empty)()
    try:
        with open(path, encoding="utf-8") as f:
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
            with open(path, encoding="utf-8") as f:
                if f.read() == new_text:
                    return False
        except Exception:  # noqa: BLE001
            pass
    # [CHANGED v3.34.0] Atomic: Home Assistant never reads a half written automations.yaml.
    write_utf8_file_atomic(path, new_text)
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
        with open(path, encoding="utf-8") as f:
            if f.read().strip() in ("", "[]"):
                return
        write_utf8_file_atomic(path, "[]\n")
        _LOGGER.warning("[libi] libi_automations.yaml is no longer used and was emptied. LIBI now "
                        "writes into automations.yaml, the same file the Home Assistant editor uses. "
                        "The include line for it can be removed from configuration.yaml.")
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] could not empty the old libi_automations.yaml: %s", err)

def _write_ast_and_yaml_sync(hass: HomeAssistant, payload: dict, slug: str = "", name: str = "") -> dict:
    """Compiles every net of one project and merges the result into Home Assistant's own three files.

    [CHANGED v3.14.0] The record of what LIBI owns is read from this project and from no other. Two
    projects can sit side by side in automations.yaml and saving one leaves the other alone, which
    is the whole point of having projects at all.

    [CHANGED v3.34.0] All three files are read before any of them is written. When one cannot be
    read, nothing at all is written, the project file included, so the ownership record never claims
    an entry that is not on disk."""
    with _FILE_LOCK:
        return _write_ast_and_yaml_locked(hass, payload, slug or "default", name)


def _write_ast_and_yaml_locked(hass: HomeAssistant, payload: dict, slug: str, name: str) -> dict:
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
                # [CHANGED v3.34.0] Its own variable: reusing `slug` here renamed the project file.
                base = slugify(net.get("name"), fallback="libi_" + slugify(net.get("id"), "script"))
                script_key = base
                counter = 2
                while script_key in scripts:
                    script_key = f"{base}_{counter}"
                    counter += 1
                scripts[script_key] = compiled
            elif level == "scene":
                scenes.append(compiled)
            else:
                automations.append(compiled)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] failed to compile net %s: %s", net.get("name"), err)
            errors.append(f"{net.get('name')}: {err}")

    owned = {
        "automations": [str(a.get("id", "")) for a in automations if a.get("id")],
        "scripts": sorted(scripts.keys()),
        "scenes": [str(s.get("id", "")) for s in scenes if s.get("id")],
    }

    plans = (
        ("automation", _get_automations_path(hass), [], automations,
         (set(owned["automations"]) | set(previous.get("automations") or [])) - protected["automations"]),
        ("script", _get_scripts_path(hass), {}, scripts,
         (set(owned["scripts"]) | set(previous.get("scripts") or [])) - protected["scripts"]),
        ("scene", _get_scenes_path(hass), [], scenes,
         (set(owned["scenes"]) | set(previous.get("scenes") or [])) - protected["scenes"]),
    )
    existing_by_domain = {}
    for domain, path, empty, _mine, _owned_keys in plans:
        existing = _read_target_sync(path, empty)
        if existing is None:
            errors.append(f"{os.path.basename(path)} could not be read")
        existing_by_domain[domain] = existing
    if any(v is None for v in existing_by_domain.values()):
        errors.append("nothing was saved")
        return {"changed": [], "errors": errors, "slug": slug, "saved": False,
                "counts": {"automations": 0, "scripts": 0, "scenes": 0}}

    _migrate_legacy_file_sync(hass)

    changed = []
    for domain, path, empty, mine, owned_keys in plans:
        existing = existing_by_domain[domain]
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

    return {"changed": changed, "errors": errors, "slug": slug, "saved": True,
            "counts": {"automations": len(automations), "scripts": len(scripts), "scenes": len(scenes)}}


def _delete_project_sync(hass: HomeAssistant, slug: str) -> dict:
    """Removes the .libi file and nothing else. The automations, scripts and scenes this project
    compiled stay exactly where they are in Home Assistant, because they are Home Assistant's now."""
    path = _project_path(hass, slug)
    with _FILE_LOCK:
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
    with _FILE_LOCK:
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


def _delete_automation_sync(hass: HomeAssistant, auto_id: str) -> dict:
    """[ADDED v3.34.0] Removes the one automation the user deleted in LIBI and leaves every other
    entry exactly as it was, under the same rules as a save: an unreadable file is not written, and
    a file that would not change is not rewritten (and not reloaded)."""
    path = _get_automations_path(hass)
    with _FILE_LOCK:
        existing = _read_target_sync(path, [])
        if existing is None:
            return {"ok": False, "changed": False,
                    "error": "automations.yaml could not be read and was left untouched"}
        kept = [a for a in existing
                if not (isinstance(a, dict) and str(a.get("id", "")) == auto_id)]
        if len(kept) == len(existing):
            return {"ok": True, "changed": False}
        changed = _write_if_changed_sync(path, kept, skip_when_empty=False)
    return {"ok": True, "changed": changed}


def _automations_by_id_sync(hass: HomeAssistant) -> dict:
    """[ADDED v3.15.0] Everything in automations.yaml, keyed by its id."""
    out = {}
    path = _get_automations_path(hass)
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] automations.yaml could not be read while opening a project: %s", err)
        return out
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id") is not None:
                out[str(item["id"])] = item
    return out


@callback
def _hydrate_project_nets(hass: HomeAssistant, nets: list, live: dict) -> dict:
    """[ADDED v3.15.0] Turns what the project stored into what the canvas should show.

    A net that names an automation is rebuilt from that automation as it stands right now, so the
    newest version always wins. The things the ladder holds and YAML does not, the position of the
    net, whether it was collapsed and the level it was drawn at, are carried over from the project.
    A net with no anchor, or one whose automation is gone, keeps the drawing that was saved.

    [CHANGED v3.34.0] Runs on the event loop: the importer resolves device and area ids through
    Home Assistant's registries, which are not safe to read from an executor thread. `live` is the
    content of automations.yaml, read in the executor beforehand."""
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
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
            if isinstance(data, list):
                for a in data:
                    if isinstance(a, dict):
                        autos.append({"id": a.get("id"), "name": a.get("alias", f"Automation {a.get('id')}"), "raw": a})
    return autos


async def _reload(hass: HomeAssistant, domains, errors: list) -> list:
    """[ADDED v3.34.0] Reloads each domain whose file was written and waits for it. A reload that
    fails is reported as a failure next to the save, never hidden behind it."""
    reloaded = []
    for domain in domains or []:
        try:
            await hass.services.async_call(domain, "reload", blocking=True)
            reloaded.append(domain)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] %s reload failed: %s", domain, err)
            errors.append(f"{domain} reload failed: {err}")
    return reloaded


def async_register_websockets(hass: HomeAssistant) -> None:
    """[CHANGED v3.34.0] Each command carries its own schema and admin requirement on its decorator.
    Writing automations and reading their full configuration are admin actions in Home Assistant's
    own editor, so they are here too."""
    for handler in (
        ws_handle_save_automation, ws_handle_load_automation, ws_handle_list_automations,
        ws_handle_get_automation, ws_handle_delete_automation, ws_handle_verify_automation,
        ws_handle_project_list, ws_handle_project_open, ws_handle_project_create,
        ws_handle_project_delete, ws_handle_preview_yaml,
        ws_handle_ai_status, ws_handle_ai_plan, ws_handle_ai_build,
    ):
        websocket_api.async_register_command(hass, handler)
    _LOGGER.debug("[libi] WebSocket commands registered")


@websocket_api.websocket_command({
    vol.Required("type"): "libi/save_automation",
    vol.Optional("slug", default="default"): str,
    vol.Optional("name", default=""): str,
    vol.Optional("nets"): [dict],
    # Older panels sent the nets wrapped in a payload object.
    vol.Optional("payload"): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_save_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    # [CHANGED v3.14.0] The save belongs to a project. Without a slug it is the Default workspace,
    # which is what an installation from before projects is migrated into.
    slug = msg["slug"] or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    payload = {"nets": msg["nets"]} if "nets" in msg else (msg.get("payload") or {})
    if not isinstance(payload.get("nets", []), list):
        connection.send_error(msg["id"], "invalid_format", "nets must be a list")
        return
    result = await hass.async_add_executor_job(
        _write_ast_and_yaml_sync, hass, payload, slug, msg["name"])
    # [ADDED v3.5.0] Reloading through the service is what makes the change live without a restart,
    # and it is the same call the Home Assistant editors make after they save.
    errors = list(result.get("errors") or [])
    reloaded = await _reload(hass, result.get("changed"), errors)
    counts = result.get("counts") or {}
    if result.get("saved"):
        message = ("Saved. {automations} automations, {scripts} scripts, {scenes} scenes written into "
                   "Home Assistant.").format(automations=counts.get("automations", 0),
                                             scripts=counts.get("scripts", 0),
                                             scenes=counts.get("scenes", 0))
    else:
        message = "Not saved."
    if errors:
        message += " Problems: " + "; ".join(errors[:5])
    connection.send_result(msg["id"], {"status": "error" if errors else "ok",
                                       "saved": bool(result.get("saved")),
                                       "message": message,
                                       "slug": result.get("slug") or slug,
                                       "written": result.get("changed") or [],
                                       "reloaded": reloaded,
                                       "errors": errors})


@websocket_api.websocket_command({vol.Required("type"): "libi/load_automation"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_load_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    data = await hass.async_add_executor_job(_read_ast_sync, hass)
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command({vol.Required("type"): "libi/list_automations"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_list_automations(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    autos = await hass.async_add_executor_job(_get_all_automations, hass)
    res = [{"id": a["id"], "name": a["name"]} for a in autos]
    connection.send_result(msg["id"], {"automations": res})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/get_automation",
    vol.Required("automation_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_get_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    auto_id = msg["automation_id"]
    autos = await hass.async_add_executor_job(_get_all_automations, hass)
    target = next((a for a in autos if str(a["id"]) == auto_id), None)
    if not target:
        connection.send_error(msg["id"], "not_found", "Automation not found")
        return
    try:
        ast_net = yaml_to_ast(hass, target["raw"])
        report = verify_round_trip(hass, target["raw"])
        if not report.get("ok"):
            _LOGGER.warning("[libi] %s does not round trip cleanly: %s", auto_id, report.get("issues"))
        connection.send_result(msg["id"], {"net": ast_net, "verify": report})
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "parse_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "libi/verify_automation",
    vol.Optional("automation_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_verify_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Imports and compiles back without writing anything, and reports what did not survive."""
    auto_id = msg.get("automation_id")
    autos = await hass.async_add_executor_job(_get_all_automations, hass)
    if auto_id:
        autos = [a for a in autos if str(a["id"]) == auto_id]
    results = []
    for a in autos:
        report = verify_round_trip(hass, a["raw"])
        results.append({"id": a["id"], "name": a["name"], "ok": report.get("ok"),
                        "issues": report.get("issues", []), "count": report.get("count", 0)})
        # [ADDED v3.34.0] The importer reads the registries, so this stays on the event loop; it
        # yields after every automation so a large automations.yaml does not stall Home Assistant.
        await asyncio.sleep(0)
    connection.send_result(msg["id"], {"results": results,
                                       "ok": all(r["ok"] for r in results) if results else True})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/delete_automation",
    vol.Required("automation_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_delete_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[CHANGED v3.34.0] Read, filter and write in the executor under the file lock, then wait for
    the reload. Before this the file was read and rewritten on the event loop with its keys sorted,
    which reordered every automation in it, and the result was "ok" whatever happened."""
    result = await hass.async_add_executor_job(
        _delete_automation_sync, hass, msg["automation_id"])
    if not result.get("ok"):
        connection.send_error(msg["id"], "delete_failed", result.get("error") or "could not delete")
        return
    errors: list = []
    reloaded = await _reload(hass, ["automation"] if result.get("changed") else [], errors)
    connection.send_result(msg["id"], {"status": "error" if errors else "ok",
                                       "deleted": bool(result.get("changed")),
                                       "reloaded": reloaded,
                                       "errors": errors})

# [ADDED v3.14.0] ---------------------------------------------------------------- projects

@websocket_api.websocket_command({vol.Required("type"): "libi/project_list"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_project_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    projects = await hass.async_add_executor_job(_migrate_and_list_projects_sync, hass)
    connection.send_result(msg["id"], {"projects": projects})


def _migrate_and_list_projects_sync(hass: HomeAssistant) -> list:
    with _FILE_LOCK:
        _migrate_single_ast_sync(hass)
        return _list_projects_sync(hass)


@websocket_api.websocket_command({
    vol.Required("type"): "libi/project_open",
    vol.Required("slug"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_project_open(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    slug = msg["slug"]
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    data = await hass.async_add_executor_job(_read_project_sync, hass, slug)
    if data is None:
        connection.send_error(msg["id"], "not_found", f"No project called {slug}")
        return
    # [CHANGED v3.15.0] Anchored nets are rebuilt from Home Assistant as it stands now, drafts and
    # orphans come back from the drawing the project saved.
    live = await hass.async_add_executor_job(_automations_by_id_sync, hass)
    hydrated = _hydrate_project_nets(hass, data.get("nets") or [], live)
    connection.send_result(msg["id"], {
        "slug": data.get("slug") or slug,
        "name": data.get("name") or slug,
        "nets": hydrated["nets"],
        "stats": hydrated["stats"],
        "updated": data.get("updated") or "",
    })


@websocket_api.websocket_command({
    vol.Required("type"): "libi/project_create",
    vol.Required("name"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_project_create(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    name = msg["name"].strip()
    if not name:
        connection.send_error(msg["id"], "bad_name", "A project needs a name")
        return
    created = await hass.async_add_executor_job(_create_project_sync, hass, name)
    connection.send_result(msg["id"], created)


@websocket_api.websocket_command({
    vol.Required("type"): "libi/project_delete",
    vol.Required("slug"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_project_delete(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    slug = msg["slug"]
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    result = await hass.async_add_executor_job(_delete_project_sync, hass, slug)
    if not result.get("ok"):
        connection.send_error(msg["id"], "delete_failed", result.get("error") or "could not delete")
        return
    # Nothing was reloaded and nothing was removed from Home Assistant. Only the drawing is gone.
    connection.send_result(msg["id"], {
        "status": "ok",
        "message": "The project file was deleted. Everything it compiled is still in Home Assistant.",
    })


@websocket_api.websocket_command({
    vol.Required("type"): "libi/preview_yaml",
    vol.Required("net"): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_preview_yaml(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        yaml_dict = ast_to_yaml(hass, msg["net"])
        yaml_str = yaml.dump(yaml_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        connection.send_result(msg["id"], {"yaml": yaml_str})
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "preview_error", str(err))


# [ADDED v3.36.0] ------------------------------------------------------------------- AI chat
# The model only drafts. Every entity comes from the user's own picks, every service and trigger is
# checked against an allow list and against Home Assistant's validator in ai.py, and the result is a
# net on the canvas that is written only when the user presses SAVE & COMPILE.

@websocket_api.websocket_command({vol.Required("type"): "libi/ai_status"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_ai_status(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], ai.ai_status(ai.ai_settings(hass)))


@websocket_api.websocket_command({
    vol.Required("type"): "libi/ai_plan",
    vol.Required("messages"): [dict],
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_ai_plan(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Step 1: the model turns the request into roles and questions; LIBI finds the candidates."""
    settings = ai.ai_settings(hass)
    if not ai.ai_status(settings)["configured"]:
        connection.send_error(msg["id"], "not_configured", "AI is not set up.")
        return
    messages = ai.clean_messages(msg["messages"])
    if not messages or messages[-1]["role"] != "user":
        connection.send_error(msg["id"], "invalid_format", "The last message must be the user's.")
        return
    try:
        raw = await ai.async_llm_json(hass, settings, ai.PLAN_SYSTEM, messages, ai.PLAN_SCHEMA)
    except ai.AiError as err:
        connection.send_error(msg["id"], "ai_error", str(err))
        return
    plan = ai.clean_plan(hass, raw)
    candidates = {}
    for role in plan["roles"]:
        candidates[role["id"]] = ai.find_candidates(hass, role)
        await asyncio.sleep(0)
    connection.send_result(msg["id"], {"plan": plan, "candidates": candidates})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/ai_build",
    vol.Required("messages"): [dict],
    vol.Required("plan"): dict,
    vol.Required("selections"): dict,
    vol.Optional("answers", default={}): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_ai_build(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Step 2: the user picked the entities; the model writes the logic with role references only,
    and LIBI validates it and draws it. Nothing is written to Home Assistant here."""
    settings = ai.ai_settings(hass)
    if not ai.ai_status(settings)["configured"]:
        connection.send_error(msg["id"], "not_configured", "AI is not set up.")
        return
    # The plan comes back from the browser, so it is cleaned again rather than trusted.
    plan = ai.clean_plan(hass, msg["plan"])
    selections, problems = ai.clean_selections(hass, plan, msg["selections"])
    if problems:
        connection.send_result(msg["id"], {"ok": False, "errors": problems})
        return
    answers = {str(k)[:40]: str(v)[:200] for k, v in msg["answers"].items()}
    messages = ai.clean_messages(msg["messages"])
    messages.append({"role": "user", "content": ai.build_context(plan, selections, answers, hass)})
    try:
        raw = await ai.async_llm_json(hass, settings, ai.BUILD_SYSTEM, messages, ai.BUILD_SCHEMA)
    except ai.AiError as err:
        connection.send_error(msg["id"], "ai_error", str(err))
        return
    draft = await ai.async_build_draft(hass, plan, selections, raw)
    result = {key: draft[key] for key in ("ok", "errors", "level", "yaml", "card_yaml",
                                           "sensitive", "reply", "notes")}
    if draft["ok"]:
        try:
            net = yaml_to_ast(hass, draft["auto"])
        except Exception as err:  # noqa: BLE001
            result.update(ok=False, errors=[f"The draft could not be drawn: {ai._sanitize(err)}"])
            connection.send_result(msg["id"], result)
            return
        net["level"] = draft["level"]
        net["name"] = draft["auto"]["alias"]
        net["source"] = "draft"
        net["source_note"] = "Drafted by the AI chat. Review it, then SAVE & COMPILE to write it."
        result["net"] = net
        report = verify_round_trip(hass, draft["auto"]) if draft["level"] == "automation" else {"ok": True}
        result["round_trip"] = {"ok": bool(report.get("ok")), "issues": report.get("issues", [])[:10]}
    connection.send_result(msg["id"], result)
