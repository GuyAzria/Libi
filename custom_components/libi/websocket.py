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
# [CHANGED v3.93.0 | 2026-11-06] Purpose: libi/project_open and libi/save_done give the key each NET has in Home
#   Assistant (keys): the panel's Online finds the automation of a NET drawn in LIBI, and its trace, by it.
# [ADDED v3.94.0 | 2026-11-07] Purpose: libi/online_fire - Online's Real runs an automation in Home Assistant as if the
#   trigger FORCE TRUE was pressed on fired (online.py), after the user confirmed; never one that can reach a lock, an
#   alarm or a cover.
import asyncio
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol
import yaml

from homeassistant.components import websocket_api
from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util.file import write_utf8_file_atomic

from . import ai, online, recipients
from .const import RECIPIENT_PREFIX
from .libi_to_yaml import ast_to_yaml, verify_round_trip, net_level, same_config, slugify
from .yaml_to_libi import called_actions, yaml_to_ast

_LOGGER = logging.getLogger(__name__)

# [ADDED v3.34.0] Every read-modify-write of the project files, and every read of automations.yaml, scripts.yaml and
# scenes.yaml, runs in the executor, so two saves can overlap. One lock makes each of them whole. [CHANGED v3.85.0] LIBI
# writes none of those three files: Home Assistant's config API does, under a lock of its own.
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


# [ADDED v3.47.0] Each net's earlier versions live next to the project, in a file of their own, so
# the .libi format is unchanged and an older LIBI still opens the project. The history is an archive:
# what runs is always what is in automations.yaml, scripts.yaml and scenes.yaml (RULE 21).
VERSIONS_SUFFIX = ".versions.json"
MAX_NET_VERSIONS = 30
# Keys that describe how the canvas shows a net right now, not the logic. A snapshot leaves them out.
_SNAPSHOT_SKIP = ("source", "source_note", "collapsed")


def _versions_path(hass: HomeAssistant, slug: str) -> str:
    return os.path.join(_get_projects_dir(hass), f"{slug}{VERSIONS_SUFFIX}")


def _read_versions_sync(hass: HomeAssistant, slug: str) -> dict | None:
    """The version history of one project. A file that does not exist yet is an empty history; a
    file that cannot be read returns None, and None means the history is left alone - never
    replaced by an empty one."""
    path = _versions_path(hass, slug)
    if not os.path.exists(path):
        return {"libi_versions": 1, "nets": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] the version history of %s could not be read, leaving it untouched: %s", slug, err)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nets"), dict):
        _LOGGER.error("[libi] the version history of %s is not in the expected shape, leaving it untouched", slug)
        return None
    return data


def _net_config(hass: HomeAssistant, net: dict) -> dict | None:
    """[ADDED v3.85.0] What a net puts into Home Assistant. A net that compiles to nothing, or does not compile, is not
    written to Home Assistant and has no version: None."""
    try:
        compiled = ast_to_yaml(hass, net)
    except Exception:  # noqa: BLE001
        return None
    if not compiled.get(_LEVEL_BODY_KEY.get(net_level(net), "actions")):
        return None
    return compiled


def _version_yaml(config: dict) -> str:
    """[ADDED v3.85.0] A version's YAML, as the versions list shows it."""
    return yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _net_yaml_text(hass: HomeAssistant, net: dict) -> str | None:
    """What a net puts into Home Assistant, as text. Two versions are the same when this is the
    same, so a moved element or a renumbered id does not make a new version.
    [CHANGED v3.85.0] Compared only with a version recorded before 3.85.0, which has its text alone (_record_versions)."""
    config = _net_config(hass, net)
    return _version_yaml(config) if config is not None else None


def _record_versions(history: dict, entries: list, reason: str, now: str) -> bool:
    """Adds a version for every net whose config is new and points `active` at the version whose config is the one
    in Home Assistant. A net that is back at an earlier version does not get a copy of it: that earlier version
    becomes the active one again. Returns whether anything changed, so an unchanged history is not rewritten.
    [CHANGED v3.85.0] entries are (net, config, text). Compared by what the config means (same_config) - Home Assistant's
    config API writes keys in an order and a spelling of its own - and, with a version recorded before 3.85.0, which has
    its text alone, by that text. Of two versions alike - V1, the original, and V2, its copy - the newer is the active
    one. An original is never dropped."""
    changed = False
    for net, config, text in entries:
        nid = str(net.get("id") or "")
        if not nid or config is None:
            continue
        text = text or _version_yaml(config)
        rec = history["nets"].setdefault(nid, {"active": 0, "versions": []})
        versions = rec.setdefault("versions", [])
        match = next((v for v in reversed(versions)
                      if (same_config(v.get("config"), config) if "config" in v else v.get("yaml") == text)), None)
        if match is None:
            number = max((int(v.get("v") or 0) for v in versions), default=0) + 1
            versions.append({
                "v": number, "saved": now,
                "reason": reason if versions or reason != "external" else "opened",
                "name": str(net.get("name") or ""),
                "yaml": _version_yaml(config),
                "config": copy.deepcopy(config),
                "net": {k: val for k, val in net.items() if k not in _SNAPSHOT_SKIP},
            })
            active = number
            changed = True
        else:
            active = int(match.get("v") or 0)
        if rec.get("active") != active:
            rec["active"] = active
            changed = True
        # The oldest go first; neither the version that runs nor an original is ever dropped.
        while len(versions) > MAX_NET_VERSIONS:
            drop = next((i for i, v in enumerate(versions)
                         if v.get("v") != rec["active"] and not v.get("original")), None)
            if drop is None:
                break
            versions.pop(drop)
            changed = True
    return changed


def _record_original(history: dict, net: dict, domain: str, key: str, config: dict, now: str) -> bool:
    """[ADDED v3.85.0] The user's rule (2026-11-04): an automation opened in LIBI for the first time is kept exactly as
    Home Assistant has it - V1, the original - and copied unchanged to V2, the version to work on, so the NET can always
    go back to the original. Once per automation a NET opens; returns whether it was recorded."""
    nid = str(net.get("id") or "")
    if not nid or not isinstance(config, dict):
        return False
    rec = history["nets"].setdefault(nid, {"active": 0, "versions": []})
    versions = rec.setdefault("versions", [])
    if any(v.get("original") and (v.get("domain"), str(v.get("key"))) == (domain, key) for v in versions):
        return False
    first = max((int(v.get("v") or 0) for v in versions), default=0) + 1
    drawing = {k: val for k, val in net.items() if k not in _SNAPSHOT_SKIP}
    base = {"saved": now, "name": str(net.get("name") or ""), "yaml": _version_yaml(config)}
    versions.append({**base, "v": first, "reason": "original", "original": True, "domain": domain, "key": key,
                     "config": copy.deepcopy(config), "net": copy.deepcopy(drawing)})
    versions.append({**base, "v": first + 1, "reason": "copy", "config": copy.deepcopy(config),
                     "net": copy.deepcopy(drawing)})
    rec["active"] = first + 1
    return True


def _versions_summary(history: dict | None) -> dict:
    """Per net: the version that runs, the newest one and how many there are. Enough to draw the
    badge; the list itself comes from libi/net_versions. [CHANGED v3.85.0] And its original, when it has one."""
    out = {}
    for nid, rec in ((history or {}).get("nets") or {}).items():
        versions = rec.get("versions") or []
        if not versions:
            continue
        out[nid] = {"active": rec.get("active") or 0,
                    "latest": max(int(v.get("v") or 0) for v in versions),
                    "count": len(versions)}
        original = max((int(v.get("v") or 0) for v in versions if v.get("original")), default=0)
        if original:
            out[nid]["original"] = original
    return out


def _update_versions_locked(hass: HomeAssistant, slug: str, entries: list, reason: str,
                            keep_ids: set | None = None, originals: tuple | list = ()) -> dict:
    """Reads, records and writes the history of one project. Called with _FILE_LOCK held. With
    `keep_ids`, the history of a net that is no longer in the project is removed.
    [CHANGED v3.85.0] originals: (net, domain, key, config) of automations opened for the first time (_record_original)."""
    history = _read_versions_sync(hass, slug)
    if history is None:
        return {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    changed = False
    for net, domain, key, config in originals:
        changed = _record_original(history, net, domain, key, config, now) or changed
    changed = _record_versions(history, entries, reason, now) or changed
    if keep_ids is not None:
        for nid in [n for n in history["nets"] if n not in keep_ids]:
            del history["nets"][nid]
            changed = True
    if changed:
        try:
            os.makedirs(_get_projects_dir(hass), exist_ok=True)
            write_utf8_file_atomic(_versions_path(hass, slug),
                                   json.dumps(history, indent=2, ensure_ascii=False))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] the version history of %s could not be written: %s", slug, err)
    return _versions_summary(history)


def _record_open_versions_sync(hass: HomeAssistant, slug: str, nets: list, live: dict) -> dict:
    """[ADDED v3.47.0] Opening a project records what is in Home Assistant now.
    [CHANGED v3.85.0] The user's rule (2026-11-04): an automation opened for the first time is V1, the original exactly
    as Home Assistant has it (`live`), and V2, a copy of it to work on. A NET with a history gets a version only when its
    automation was changed outside LIBI since; a NET drawn from scratch gets its V1 the first time it is saved."""
    with _FILE_LOCK:
        history = _read_versions_sync(hass, slug) or {"nets": {}}
        originals, entries = [], []
        for net in nets:
            if not isinstance(net, dict):
                continue
            ha_id = str(net.get("ha_id") or "")
            linked = net.get("source") == "ha" and ha_id in live
            if linked and not (history["nets"].get(str(net.get("id") or "")) or {}).get("versions"):
                originals.append((net, "automation", ha_id, live[ha_id]))
            elif linked:
                entries.append((net, live[ha_id], _net_yaml_text(hass, net)))
            else:
                entries.append((net, _net_config(hass, net), None))
        return _update_versions_locked(hass, slug, entries, "external", originals=originals)


def _record_original_sync(hass: HomeAssistant, slug: str, net: dict, key: str, config: dict) -> dict:
    """[ADDED v3.85.0] An automation loaded into a NET from the list: its V1, the original, and V2, its copy."""
    with _FILE_LOCK:
        return _update_versions_locked(hass, slug, [], "external", originals=[(net, "automation", key, config)])


# [ADDED v3.86.0] The names the user gave entities in LIBI only, the user's request (2026-11-04): shown wherever LIBI shows
# the entity, never written to Home Assistant. One file for every project, next to them; not a project (.libi).
LOCAL_NAMES_FILE = "local_names.json"
MAX_LOCAL_NAME = 100
_LOCAL_NAME_ENTITY = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def _local_names_path(hass: HomeAssistant) -> str:
    return os.path.join(_get_projects_dir(hass), LOCAL_NAMES_FILE)


def _read_local_names_sync(hass: HomeAssistant) -> dict | None:
    """[ADDED v3.86.0] entity_id -> name. A file that does not exist yet is no names; one that cannot be read is None, and
    None is never written over."""
    path = _local_names_path(hass)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("[libi] %s could not be read, leaving it untouched: %s", LOCAL_NAMES_FILE, err)
        return None
    names = data.get("names") if isinstance(data, dict) else None
    if not isinstance(names, dict):
        _LOGGER.error("[libi] %s is not in the expected shape, leaving it untouched", LOCAL_NAMES_FILE)
        return None
    return {str(k): v for k, v in names.items() if isinstance(v, str)}


def _set_local_name_sync(hass: HomeAssistant, entity_id: str, name: str) -> dict | None:
    """[ADDED v3.86.0] Gives an entity its name in LIBI, or takes it away (an empty name). Nothing is written when nothing
    changes, and nothing when the file cannot be read (None)."""
    with _FILE_LOCK:
        names = _read_local_names_sync(hass)
        if names is None:
            return None
        if names.get(entity_id, "") == name:
            return names
        if name:
            names[entity_id] = name
        else:
            del names[entity_id]
        os.makedirs(_get_projects_dir(hass), exist_ok=True)
        write_utf8_file_atomic(_local_names_path(hass), json.dumps(
            {"libi_local_names": 1, "names": dict(sorted(names.items()))}, indent=2, ensure_ascii=False))
        return names


def _net_versions_sync(hass: HomeAssistant, slug: str, net_id: str) -> dict | None:
    with _FILE_LOCK:
        history = _read_versions_sync(hass, slug)
    if history is None:
        return None
    rec = history["nets"].get(net_id) or {}
    versions = sorted(rec.get("versions") or [], key=lambda v: int(v.get("v") or 0), reverse=True)
    return {"active": rec.get("active") or 0, "versions": versions}


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
            # [ADDED v3.91.0] How many times LIBI wrote it (_stale).
            "revision": _revision_of(data),
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
        "revision": 1, "libi_project": 1, "slug": "default", "name": "Default",
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
# editors read and write, and the three a fresh configuration.yaml already includes.
# [CHANGED v3.85.0] LIBI only reads them. Home Assistant's own config API writes them - the endpoints its editors use,
# called by the panel - and validates, writes and reloads: the HACS review of 2026-11-03, an integration does not patch
# the user's YAML files.
def _get_automations_path(hass: HomeAssistant) -> str: return hass.config.path("automations.yaml")
def _get_scripts_path(hass: HomeAssistant) -> str: return hass.config.path("scripts.yaml")
def _get_scenes_path(hass: HomeAssistant) -> str: return hass.config.path("scenes.yaml")

# LIBI wrote its own file before v3.5.0, and up to v3.84.0 a save emptied it. [CHANGED v3.85.0] It is never written
# again: the log says when it still holds automations (legacy_file_note_sync).
def _get_legacy_yaml_path(hass: HomeAssistant) -> str: return hass.config.path("libi_automations.yaml")

# What an empty net looks like per level. An automation with no actions, a script with no sequence
# and a scene with no entities are all half drawn rungs and are not written out.
_LEVEL_BODY_KEY = {"automation": "actions", "script": "sequence", "scene": "entities"}

# [ADDED v3.85.0] Per domain: its file and the shape of it, the key of its record in a project's "owned", and the
# platform its entities are registered under, by the key of their config (a scene of the editor's is homeassistant's).
_DOMAIN_FILES = {"automation": (_get_automations_path, list), "script": (_get_scripts_path, dict),
                 "scene": (_get_scenes_path, list)}
_OWNED_KEYS = {"automation": "automations", "script": "scripts", "scene": "scenes"}
_ENTITY_PLATFORM = {"automation": "automation", "script": "script", "scene": "homeassistant"}
# [ADDED v3.85.0] Home Assistant's config API reloads in the background after it writes: how long LIBI waits to see it.
RELOAD_WAIT_SECONDS = 20.0

def _config_text_sync(hass: HomeAssistant) -> str:
    """[ADDED v3.56.0] The text of automations.yaml and scripts.yaml, only to see whether a helper's
    entity_id appears in them (a template). Read only; a file that cannot be read adds nothing."""
    parts = []
    with _FILE_LOCK:
        for path in (_get_automations_path(hass), _get_scripts_path(hass)):
            try:
                with open(path, encoding="utf-8") as handle:
                    parts.append(handle.read())
            except OSError:
                continue
    return "\n".join(parts)


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

def _read_home_assistant_files(hass: HomeAssistant) -> tuple[dict, list[str]]:
    """[ADDED v3.85.0] automations.yaml, scripts.yaml and scenes.yaml as they are now, read only. A file that cannot be
    read is an error, and then nothing is planned or recorded (RULE 5)."""
    files: dict[str, Any] = {}
    errors: list[str] = []
    for domain, (path_of, empty) in _DOMAIN_FILES.items():
        files[domain] = _read_target_sync(path_of(hass), empty())
        if files[domain] is None:
            errors.append(f"{os.path.basename(path_of(hass))} could not be read")
    return files, errors


def _file_entry(data: Any, key: str) -> Any:
    """[ADDED v3.85.0] The entry a file holds under a key: the item with that id in a list, the value under that key in
    scripts.yaml. None when there is none."""
    if isinstance(data, dict):
        return data.get(key)
    return next((item for item in data or [] if isinstance(item, dict) and str(item.get("id", "")) == key), None)


def _file_keys(data: Any) -> set[str]:
    """[ADDED v3.90.0] Every key a file holds: the ids of the entries of a list, the keys of scripts.yaml."""
    if isinstance(data, dict):
        return {str(key) for key in data}
    return {str(item["id"]) for item in data or [] if isinstance(item, dict) and item.get("id") is not None}


def _entry_label(domain: str, key: str, entry: Any) -> str:
    """[ADDED v3.90.0] An entry of Home Assistant's as the user knows it: its kind and its name, and its key."""
    name = str((entry or {}).get("alias") or (entry or {}).get("name") or "").strip() if isinstance(entry, dict) else ""
    return f'{domain} "{name[:80]}" ({key})' if name else f"{domain} {key}"


def _fingerprint(entry: Any) -> str:
    """[ADDED v3.91.0] An entry of Home Assistant's files as a fingerprint, '' when there is none. SAVE & COMPILE plans
    with it and checks it again just before each change is sent (libi/save_check): an entry that changed in between is
    not written over (CLAUDE.md RULE 38)."""
    if entry is None:
        return ""

    def canonical(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): canonical(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(v) for v in value]
        return value

    text = json.dumps(canonical(entry), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _revision_of(project: dict | None) -> int:
    """[ADDED v3.91.0] How many times LIBI wrote a project - 0 for one written before 3.91.0."""
    try:
        return max(0, int((project or {}).get("revision") or 0))
    except (TypeError, ValueError):
        return 0


def _stale(ctx: dict, revision: Any) -> str:
    """[ADDED v3.91.0] Why this page may not save into the project, or '' when it may. CLAUDE.md RULE 39, stale
    snapshots: the project on disk must be the one the page opened - the same revision - so a page opened before another
    page saved it does not write over that save (its NETs, and what LIBI made), and a page that never opened it does not
    replace its NETs. A project not there yet takes a page with no revision."""
    if not ctx["exists"]:
        return "This project was deleted since this page opened it. Nothing was saved." if revision is not None else ""
    if revision is None:
        return ("This page has not opened this project, so it cannot save into it. Open the project first, or make a new "
                "one. Nothing was saved.")
    if revision != ctx["revision"]:
        return ("This project was saved from another LIBI page since this page opened it. Nothing was saved: open the "
                "project again, then make the change there.")
    return ""


def _save_context_sync(hass: HomeAssistant, slug: str, ours: tuple | list = ()) -> dict:
    """[ADDED v3.90.0 as _taken_sync] What the NETs of this project may take (_compile_nets), read together:
    - taken, per domain: every key Home Assistant's files hold that this project does not own, and every key another
      project owns. `ours` is (domain, key) of what this save just sent - in the files now, in the project only once the
      save is recorded;
    [CHANGED v3.91.0] CLAUDE.md RULE 38 -
    - owned, per domain: this project's; and opened, per NET: the automations loaded into it from Home Assistant (its
      originals). Only with one of these is a NET with an ha_id that automation - an ha_id alone is a matching key, and a
      copy of a NET had one (n1's copy was "a1_copy", over the user's own a1_copy);
    - keys, per NET: the key its last save gave it, kept while this project owns it - a key moved aside (good_night_2)
      does not move back when the other one goes, which made a second script;
    - exists, revision: the project on disk (_stale).
    A file or this project that cannot be read is an error: then nothing is planned or recorded (RULE 31)."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        exists = os.path.exists(_project_path(hass, slug))
        project = _read_project_sync(hass, slug)
        if project is None and exists:
            errors.append(f"the project {slug} could not be read")
        protected = _all_owned_except_sync(hass, slug)
        history = _read_versions_sync(hass, slug)
    if errors:
        return {"errors": errors}
    project = project or {}
    held = project.get("owned") if isinstance(project.get("owned"), dict) else {}
    owned = {domain: {str(k) for k in held.get(owned_key) or []} for domain, owned_key in _OWNED_KEYS.items()}
    taken: dict[str, set[str]] = {}
    for domain, owned_key in _OWNED_KEYS.items():
        mine = owned[domain] | {str(k) for d, k in ours if d == domain}
        taken[domain] = (_file_keys(files[domain]) | protected[owned_key]) - mine
    opened: dict[str, set[str]] = {}
    for nid, rec in ((history or {}).get("nets") or {}).items():
        for version in (rec or {}).get("versions") or []:
            if version.get("original") and version.get("domain") == "automation" and version.get("key"):
                opened.setdefault(str(nid), set()).add(str(version["key"]))
    keys = project.get("keys") if isinstance(project.get("keys"), dict) else {}
    return {"errors": [], "taken": taken, "owned": owned, "opened": opened, "keys": keys, "exists": exists,
            "revision": _revision_of(project) if exists else None,
            "made": {domain: {str(k) for k in (project.get("made") or {}).get(owned_key) or []}
                     for domain, owned_key in _OWNED_KEYS.items()}}


def legacy_file_note_sync(hass: HomeAssistant) -> None:
    """[CHANGED v3.85.0] Read only - the HACS review: LIBI leaves libi_automations.yaml alone and says in the log when it
    still holds automations. Up to v3.84.0 a save emptied it, so an install upgraded since has [] there and hears nothing."""
    path = _get_legacy_yaml_path(hass)
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("[libi] libi_automations.yaml, from LIBI before 3.5.0, could not be read; LIBI leaves it as it "
                        "is: %s", err)
        return
    if isinstance(data, list) and data:
        _LOGGER.warning(
            "[libi] libi_automations.yaml, from LIBI before 3.5.0, still holds %d automation(s). LIBI no longer uses or "
            "changes it. If configuration.yaml still includes it, the same automations may also be in automations.yaml "
            "and run twice: check them, then remove the file and its include line.", len(data))


def _compile_nets(hass: HomeAssistant, nets: list, ctx: dict | None = None) -> tuple[list[dict], list[str]]:
    """[ADDED v3.85.0] Every net of a project, compiled: one entry for each that compiles to something - its domain,
    the key Home Assistant files it under and its config. A net that compiles to nothing is a half drawn one: it stays
    in the project and is not sent. A net that does not compile is an error, and then nothing is saved.
    scripts.yaml is a mapping, so a script needs an object id: its name as a slug, a repeated name with a number.
    [CHANGED v3.90.0] A NET never takes an entry it has no claim to - the HACS review (2026-11-05): a script NET called
    "Good night" replaced the user's script.good_night. ctx["taken"] (_save_context_sync) holds, per domain, the keys
    Home Assistant holds for someone else; such a key goes to the next free one - good_night_2, n1_2.
    [CHANGED v3.91.0] CLAUDE.md RULE 38. A NET with an ha_id is the automation it names (linked) only when this project
    owns it or opened it into that NET; otherwise it keeps that id and the plan refuses it if Home Assistant has it for
    someone else - never moved to another key, which would make a second automation. A key moved aside stays with its
    NET while this project owns it (ctx["keys"]), and is kept for it before any other NET is given one. Two NETs never
    save to one entry: an error, and nothing is saved."""
    ctx = ctx or {}
    taken = ctx.get("taken") or {}
    owned = ctx.get("owned") or {}
    opened = ctx.get("opened") or {}
    kept = ctx.get("keys") or {}
    entries: list[dict] = []
    errors: list[str] = []
    for index, net in enumerate(nets or []):
        if not isinstance(net, dict):
            continue
        level = net_level(net)
        label = f'NET {index + 1} "{str(net.get("name") or "")[:60]}"'
        try:
            compiled = ast_to_yaml(hass, net)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] failed to compile net %s: %s", net.get("name"), err)
            errors.append(f"{label}: {err}")
            continue
        if not compiled.get(_LEVEL_BODY_KEY.get(level, "actions")):
            continue
        nid = str(net.get("id") or "")
        ha_id = "" if level == "script" else str(net.get("ha_id") or "")
        if level == "script":
            base = slugify(net.get("name"), fallback="libi_" + slugify(net.get("id"), "script"))
        else:
            base = str(compiled.get("id") or "")
            if not base:
                errors.append(f"{label}: it has no id for Home Assistant")
                continue
        linked = bool(ha_id) and base == ha_id and (base in owned.get(level, ()) or base in opened.get(nid, ()))
        entries.append({"net": net, "label": label, "domain": level, "base": base, "key": "", "config": compiled,
                        "linked": linked, "named": bool(ha_id)})
    claimed: dict[tuple[str, str], dict] = {}

    def claim(entry: dict, key: str) -> None:
        other = claimed.get((entry["domain"], key))
        if other is not None:
            entry["refused"] = True
            errors.append(f'{entry["label"]}: it would be {entry["domain"]} {key}, which {other["label"]} is too - two NETs '
                          f'cannot be one {entry["domain"]}. Delete one of them, or load another automation into it.')
            return
        claimed[(entry["domain"], key)] = entry
        entry["key"] = key
        # The id an automation or a scene is filed under is its key - Home Assistant's config API writes the config's own
        # id over the key it is posted to.
        if entry["domain"] != "script":
            entry["config"]["id"] = key

    # First what stays: the automation a NET is, and the key a NET was given before and this project still owns.
    for entry in entries:
        record = kept.get(str(entry["net"].get("id") or ""))
        if entry["linked"]:
            claim(entry, entry["base"])
        elif (isinstance(record, dict) and record.get("domain") == entry["domain"] and record.get("base") == entry["base"]
              and str(record.get("key") or "") in owned.get(entry["domain"], ())):
            claim(entry, str(record["key"]))
    # Then the rest, in order: an id a NET names stays its id; any other key that is taken or claimed goes to the next
    # free one, one no other NET of this save has.
    for entry in entries:
        if entry["key"] or entry.get("refused"):
            continue
        domain, base = entry["domain"], entry["base"]
        if entry["named"]:
            claim(entry, base)
            continue
        key, counter = base, 2
        while (domain, key) in claimed or key in taken.get(domain, ()):
            key, counter = f"{base}_{counter}", counter + 1
        claim(entry, key)
    for entry in entries:
        # [ADDED v3.88.0] The keys of LIBI Global's recipients are theirs: a NET saved there would replace one.
        if entry["domain"] == "script" and entry["key"].startswith(RECIPIENT_PREFIX):
            errors.append(f'{entry["label"]}: as a script it would be {entry["key"]}, a name kept for the recipients of '
                          "LIBI Global - give the NET another name.")
    for entry in entries:
        entry.pop("refused", None)
    return [e for e in entries if e["key"]], errors


def _originals(history: dict | None) -> dict[str, dict]:
    """[ADDED v3.85.0] Per net, its newest original: the V1 an automation was opened with."""
    out: dict[str, dict] = {}
    for nid, rec in ((history or {}).get("nets") or {}).items():
        for version in rec.get("versions") or []:
            if version.get("original") and isinstance(version.get("config"), dict):
                out[nid] = version
    return out


async def _originals_as_they_were(hass: HomeAssistant, slug: str, entries: list[dict]) -> None:
    """[ADDED v3.85.0] A net nobody changed since its automation was opened goes back as its original - V1, exactly as
    Home Assistant had it - not as LIBI would write it: a save never rewrites an automation nobody changed (RULE 5), and
    V1 put back on the canvas restores it as it was. Unchanged is the net compiling to what its original opens as. The
    importer reads the registries, so this runs on the event loop and yields after every net."""
    originals = _originals(await hass.async_add_executor_job(_read_versions_sync, hass, slug))
    for entry in entries:
        original = originals.get(str(entry["net"].get("id") or ""))
        if not original or (original.get("domain"), str(original.get("key"))) != (entry["domain"], entry["key"]):
            continue
        if _as_libi_compiles(hass, entry, original["config"]) == entry["config"]:
            entry["config"] = copy.deepcopy(original["config"])
            entry["original"] = True
        await asyncio.sleep(0)


def _as_libi_compiles(hass: HomeAssistant, entry: dict, config: Any) -> dict | None:
    """[ADDED v3.90.0] An automation as its NET compiles once LIBI opens it: what the NET is when nobody changed it in
    LIBI. None when it cannot be compared. Reads the registries, so on the event loop."""
    if entry["domain"] != "automation" or not isinstance(config, dict):
        return None
    try:
        opened = yaml_to_ast(hass, copy.deepcopy(config))
        opened.update(id=entry["net"].get("id"), ha_id=entry["key"], level=entry["domain"])
        return ast_to_yaml(hass, opened)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("[libi] %s could not be compared with what Home Assistant has: %s", entry["label"], err)
        return None


def _last_seen_sync(hass: HomeAssistant, slug: str) -> tuple[dict, list[str], dict[str, set[str]], dict | None]:
    """[ADDED v3.90.0] Home Assistant's files, what this project owns in them, and its version history - what LIBI last
    saw of each NET - read together."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        owned = (_read_project_sync(hass, slug) or {}).get("owned") or {}
        history = _read_versions_sync(hass, slug)
    return files, errors, {d: {str(k) for k in owned.get(o) or []} for d, o in _OWNED_KEYS.items()}, history


def _seen_config(history: dict | None, net_id: str) -> dict | None:
    """[ADDED v3.90.0] The config of the version of a NET that LIBI last saw in Home Assistant - the active one, recorded
    when the project was opened or saved. None when there is none."""
    rec = ((history or {}).get("nets") or {}).get(net_id) or {}
    versions = [v for v in rec.get("versions") or [] if isinstance(v.get("config"), dict)]
    active = next((v for v in versions if v.get("v") == rec.get("active")), None)
    return active["config"] if active else None


async def _as_last_seen(hass: HomeAssistant, slug: str, entries: list[dict]) -> None:
    """[ADDED v3.90.0] RULE 5 - a save never rewrites what the user did not change - for every NET, against what LIBI
    last saw of it in Home Assistant (its active version):
    - not changed in LIBI since: nothing is sent, whatever Home Assistant has now - what LIBI cannot draw is not lost,
      and a change made in Home Assistant's editor is not undone (left, when Home Assistant's differs);
    - changed in LIBI, and Home Assistant's changed too since then: a conflict - the save asks before it replaces it;
    - changed in LIBI, of an automation LIBI cannot draw all of: what the save would lose (loses) - asked too;
    - no longer in Home Assistant though this project saved it: deleted outside LIBI since (gone) - never put back
      without asking.
    Without a version history to read, a NET is sent as before."""
    files, errors, owned, history = await hass.async_add_executor_job(_last_seen_sync, hass, slug)
    if errors:
        return
    for entry in entries:
        current = _file_entry(files[entry["domain"]], entry["key"])
        seen = _seen_config(history, str(entry["net"].get("id") or ""))
        untouched = seen is not None and (entry["config"] == seen or same_config(entry["config"], seen)
                                          or _as_libi_compiles(hass, entry, seen) == entry["config"])
        if current is None:
            entry["gone"] = entry["key"] in owned[entry["domain"]]
            entry["changed"] = not untouched
        elif untouched:
            entry["left"] = not same_config(current, seen)
            entry["config"] = copy.deepcopy(current)
        elif not same_config(current, entry["config"]):
            entry["conflict"] = seen is not None and not same_config(current, seen)
            # The original put back is sent exactly as it was: nothing of it is lost.
            if entry["domain"] == "automation" and not entry.get("original"):
                try:
                    report = verify_round_trip(hass, copy.deepcopy(current))
                except Exception as err:  # noqa: BLE001
                    report = {"ok": False, "issues": [f"it could not be checked: {ai._sanitize(err)}"]}
                if not report.get("ok"):
                    entry["loses"] = [str(issue)[:200] for issue in (report.get("issues") or [])[:5]] or ["it changes"]
        await asyncio.sleep(0)


def _plan_save_sync(hass: HomeAssistant, slug: str, entries: list[dict]) -> dict:
    """[ADDED v3.85.0] What a save changes in Home Assistant's files - read, never written: each entry whose config does
    not mean what the one in its file means (same_config), or is not there yet, and each entry this project wrote before
    and no longer has - never one another project claims. A file that cannot be read means no plan at all (RULE 5).
    [CHANGED v3.90.0] The HACS review (2026-11-05): a save removed every entry the project had saved once, an automation
    opened from Home Assistant's editor too. Now a removal is only an entry this project created in Home Assistant (its
    "made"), and the panel lists them and asks before it sends any DELETE. Every other entry the canvas no longer has is
    released: it stays in Home Assistant as it is, and leaves the project. An upsert says whether it creates its entry
    (new), so the project knows what it made; one that would change an entry this project neither owns nor opened is
    refused, whatever chose its key. After _as_last_seen: a NET not changed in LIBI is unchanged here (left names the
    ones Home Assistant changed since); an upsert says whether it replaces a change made in Home Assistant (conflict) and
    what LIBI cannot draw of it (loses); an entry deleted outside LIBI is not an upsert but gone - the panel asks about
    each of these before it sends anything.
    [CHANGED v3.91.0] Each change says what it found (before, _fingerprint), which libi/save_check checks again just
    before the panel sends it (RULE 38)."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        if errors:
            return {"ok": False, "errors": errors + ["nothing was saved"]}
        project = _read_project_sync(hass, slug) or {}
        previous = project.get("owned") or {}
        made = project.get("made") or {}
        protected = _all_owned_except_sync(hass, slug)
    now: dict[str, set] = {domain: set() for domain in _DOMAIN_FILES}
    upserts: list[dict] = []
    gone: list[dict] = []
    left: list[str] = []
    unchanged = 0
    for entry in entries:
        now[entry["domain"]].add(entry["key"])
        current = _file_entry(files[entry["domain"]], entry["key"])
        if current is not None and same_config(current, entry["config"]):
            unchanged += 1
            if entry.get("left"):
                left.append(_entry_label(entry["domain"], entry["key"], current))
            continue
        # [ADDED v3.90.0] Deleted outside LIBI since this project saved it: put back only if the user says so.
        if current is None and entry.get("gone"):
            gone.append({"before": "", "domain": entry["domain"], "key": entry["key"], "config": entry["config"],
                         "net_id": str(entry["net"].get("id") or ""), "changed": bool(entry.get("changed")),
                         "label": f'{entry["label"]}: {_entry_label(entry["domain"], entry["key"], entry["config"])}'})
            continue
        if (current is not None and not entry.get("linked")
                and entry["key"] not in {str(k) for k in previous.get(_OWNED_KEYS[entry["domain"]]) or []}):
            # [CHANGED v3.91.0] A NET that only names it - a copy made before 3.91.0 - can be saved as one of its own.
            hint = (". To save this NET as an automation of its own, duplicate it and delete this one"
                    if entry.get("named") else "")
            errors.append(f"{entry['label']}: {_entry_label(entry['domain'], entry['key'], current)} is already in Home "
                          f"Assistant, and this project did not save it - it is not changed{hint}")
            continue
        upserts.append({"before": _fingerprint(current), "domain": entry["domain"], "key": entry["key"],
                        "config": entry["config"],
                        "net_id": str(entry["net"].get("id") or ""), "label": entry["label"], "new": current is None,
                        "conflict": bool(entry.get("conflict")), "loses": list(entry.get("loses") or [])})
    removals: list[dict] = []
    released: list[dict] = []
    for domain, owned_key in _OWNED_KEYS.items():
        off_canvas = {str(k) for k in previous.get(owned_key) or []} - now[domain] - protected[owned_key]
        mine = {str(k) for k in made.get(owned_key) or []}
        for key in sorted(off_canvas):
            current = _file_entry(files[domain], key)
            if current is not None:
                (removals if key in mine else released).append(
                    {"before": _fingerprint(current), "domain": domain, "key": key,
                     "label": _entry_label(domain, key, current)})
    if errors:
        return {"ok": False, "errors": errors + ["nothing was saved"]}
    return {"ok": True, "errors": [], "upserts": upserts, "removals": removals, "released": released,
            "gone": gone, "left": left, "unchanged": unchanged}


def _record_save_sync(hass: HomeAssistant, slug: str, name: str, nets: list, entries: list[dict],
                      write_project: bool, done: list[dict], kept: list[tuple[str, str]]) -> dict:
    """[ADDED v3.85.0] After the panel sent the changes to Home Assistant's config API: Home Assistant's files are read
    back - the browser's word is not taken for it - and the project records what they hold. Its nets; the entries it
    owns there, a removal that failed included, so the next save removes it; a version of every net that runs as it was
    built. Only a save that reached Home Assistant, or had nothing to change there, writes the project.
    [CHANGED v3.90.0] And what it made: the entries its upserts created (done, new), the only ones a later save may
    offer to remove. An entry the canvas no longer has that this project did not make, or whose removal the user
    declined (kept), leaves the project and stays in Home Assistant as it is (released) - a later save never touches
    it. Only a removal that did not happen - refused, or not sent - is kept, to be asked again.
    [CHANGED v3.91.0] Made is only what libi/save_check confirmed (ws_handle_save_done). And the key of each NET (keys),
    which the next save gives it again, and the project's revision, one more."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        if errors:
            return {"saved": False, "errors": errors}
        project = _read_project_sync(hass, slug) or {}
        previous = project.get("owned") or {}
        made_before = project.get("made") or {}
        protected = _all_owned_except_sync(hass, slug)
        owned: dict[str, list] = {}
        made: dict[str, list] = {}
        released: list[str] = []
        for domain, owned_key in _OWNED_KEYS.items():
            on_canvas = {e["key"] for e in entries if e["domain"] == domain}
            before = {str(k) for k in previous.get(owned_key) or []} - protected[owned_key]
            created = {str(k) for k in made_before.get(owned_key) or []} - protected[owned_key]
            created |= {op["key"] for op in done if op["domain"] == domain and op["op"] == "upsert" and op.get("new")}
            retry = (created & before) - on_canvas - {key for d, key in kept if d == domain}
            owned[owned_key] = sorted(k for k in on_canvas | retry if _file_entry(files[domain], k) is not None)
            made[owned_key] = sorted(k for k in created if k in owned[owned_key])
            released += [_entry_label(domain, k, _file_entry(files[domain], k)) for k in sorted(before - on_canvas - retry)
                         if _file_entry(files[domain], k) is not None]
        running = [e for e in entries
                   if (current := _file_entry(files[e["domain"]], e["key"])) is not None and same_config(current, e["config"])]
        if not write_project:
            return {"saved": False, "errors": []}
        # [ADDED v3.91.0] The key each NET has in Home Assistant now, so the next save gives it the same one (RULE 38).
        keys = {str(e["net"]["id"]): {"domain": e["domain"], "key": e["key"], "base": e["base"]}
                for e in entries if e["net"].get("id") and e["key"] in owned[_OWNED_KEYS[e["domain"]]]}
        revision = _revision_of(project) + 1
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_project_sync(hass, slug, {
            # [ADDED v3.91.0] One more each time LIBI writes the project: a page that opened an older one saves nothing.
            "revision": revision,
            "libi_project": 1,
            "slug": slug,
            "name": name or project.get("name") or slug,
            "created": project.get("created") or now,
            "updated": now,
            # Every net exactly as it was left, unfinished logic and all, including which automation each
            # one was loaded from, which is the ha_id carried on the net.
            "nets": nets,
            "owned": owned,
            # [ADDED v3.90.0] Of those, the ones this project created in Home Assistant. A project from before 3.90.0
            # has none: a save never removes what it saved then.
            "made": made,
            "keys": keys,
        })
        # [ADDED v3.47.0] Only what runs in Home Assistant is a version, so the history never holds one that did not
        # run. A net removed from the project takes its history along.
        keep_ids = {str(n.get("id")) for n in nets if isinstance(n, dict) and n.get("id")}
        versions = _update_versions_locked(hass, slug, [(e["net"], e["config"], None) for e in running], "saved",
                                           keep_ids)
    return {"saved": True, "errors": [], "versions": versions, "released": released, "revision": revision, "keys": keys,
            "counts": {owned_key: sum(1 for e in entries if e["domain"] == domain)
                       for domain, owned_key in _OWNED_KEYS.items()}}


def _net_entry_sync(hass: HomeAssistant, slug: str, net_id: str, domain: str, key: str) -> dict:
    """[ADDED v3.85.0] Whether a NET's entry is in Home Assistant's files now, and its original (V1), if it has one."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        history = _read_versions_sync(hass, slug)
    versions = (((history or {}).get("nets") or {}).get(net_id) or {}).get("versions") or []
    original = next((v for v in reversed(versions) if v.get("original") and isinstance(v.get("config"), dict)
                     and (v.get("domain"), str(v.get("key"))) == (domain, key)), None)
    current = _file_entry(files.get(domain), key) if domain and key and not errors else None
    # [CHANGED v3.91.0] With its name, for the dialog, and its fingerprint, checked again just before it is changed.
    return {"in_ha": current is not None,
            "label": _entry_label(domain, key, current) if current is not None else "",
            "before": _fingerprint(current),
            "errors": errors,
            "original": {"v": original.get("v"), "config": original["config"]} if original else None}


def _release_net_sync(hass: HomeAssistant, slug: str, net_id: str, domain: str, key: str) -> int | None:
    """[ADDED v3.85.0] The project lets go of a NET deleted from the canvas: its drawing, the entry it owned in Home
    Assistant - so no later save removes what is now the user's alone - and its history.
    [CHANGED v3.91.0] And the key it kept (keys); returns the project's new revision, None when there is no project."""
    revision = None
    with _FILE_LOCK:
        project = _read_project_sync(hass, slug)
        if project is not None:
            project["nets"] = [n for n in project.get("nets") or []
                               if not (isinstance(n, dict) and str(n.get("id") or "") == net_id)]
            if domain in _OWNED_KEYS and key:
                # [CHANGED v3.90.0] Its record of what this project made goes with it.
                for record in ("owned", "made"):
                    held = project.get(record) or {}
                    held[_OWNED_KEYS[domain]] = [k for k in held.get(_OWNED_KEYS[domain]) or [] if str(k) != key]
                    project[record] = held
            if isinstance(project.get("keys"), dict):
                project["keys"].pop(net_id, None)
            revision = project["revision"] = _revision_of(project) + 1
            project["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write_project_sync(hass, slug, project)
        history = _read_versions_sync(hass, slug)
        if history is not None and net_id in history["nets"]:
            del history["nets"][net_id]
            os.makedirs(_get_projects_dir(hass), exist_ok=True)
            write_utf8_file_atomic(_versions_path(hass, slug), json.dumps(history, indent=2, ensure_ascii=False))
    return revision


def _delete_project_sync(hass: HomeAssistant, slug: str) -> dict:
    """Removes the .libi file and its version history, and nothing else. The automations, scripts
    and scenes this project compiled stay exactly where they are in Home Assistant, because they are
    Home Assistant's now."""
    path = _project_path(hass, slug)
    with _FILE_LOCK:
        if not os.path.exists(path):
            return {"ok": False, "error": "no such project"}
        try:
            os.remove(path)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] could not delete project %s: %s", slug, err)
            return {"ok": False, "error": str(err)}
        # [ADDED v3.47.0] A history without its project would be picked up by a new project that
        # happens to get the same name.
        try:
            if os.path.exists(_versions_path(hass, slug)):
                os.remove(_versions_path(hass, slug))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("[libi] could not delete the version history of %s: %s", slug, err)
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
            "revision": 1, "libi_project": 1, "slug": slug, "name": name or slug,
            "created": now, "updated": now, "nets": [], "owned": {},
        })
    # [CHANGED v3.91.0] With its revision, which the page saves with (_stale).
    return {"slug": slug, "name": name or slug, "revision": 1}


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


def _since(stamp: str) -> datetime:
    """[ADDED v3.85.0] When a save began, from the stamp libi/compile_project gave - never later than now. Without one, a
    minute ago."""
    now = datetime.now(timezone.utc)
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return now - timedelta(seconds=60)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return min(when, now)


def _an_op(op: Any) -> dict | None:
    """[ADDED v3.85.0] A change the panel says it made through Home Assistant's config API, or None when it is not one.
    [CHANGED v3.90.0] An upsert keeps `new`, the plan's own word that it created its entry (libi/compile_project)."""
    if not isinstance(op, dict) or op.get("domain") not in _DOMAIN_FILES or op.get("op") not in ("upsert", "remove"):
        return None
    key = str(op.get("key") or "")
    if not 0 < len(key) <= 255:
        return None
    new = op["op"] == "upsert" and op.get("new") is True
    # [CHANGED v3.91.0] With the token libi/save_check gave it (_made_checked).
    return {"domain": op["domain"], "key": key, "op": op["op"], "new": new,
            "token": str(op.get("token") or "")[:128] if new else ""}


# [ADDED v3.91.0] CLAUDE.md RULE 38: what a save made counts only when libi/save_check confirmed, just before the panel
# sent it, that its entry was not there - the plan's word alone, or the browser's, never gives a later save the right to
# remove it. The check signs its word with a key of this run of Home Assistant, for the save it belongs to (its stamp).
_SAVE_SECRET = secrets.token_bytes(32)
MADE_TOKEN_MAX_AGE = timedelta(hours=1)


def _made_token(slug: str, domain: str, key: str, stamp: str) -> str:
    return hmac.new(_SAVE_SECRET, "\n".join((slug, domain, key, stamp)).encode("utf-8"), hashlib.sha256).hexdigest()


def _made_checked(slug: str, op: dict, stamp: str) -> bool:
    """[ADDED v3.91.0] Whether this upsert created its entry, as libi/save_check confirmed it for this save, within the
    hour. Not so - no token, one of another save, or Home Assistant restarted since - and the entry is not made: never
    removed by a later save without the Delete NET dialog (fail closed)."""
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if not timedelta(0) <= datetime.now(timezone.utc) - when <= MADE_TOKEN_MAX_AGE:
        return False
    return bool(op.get("token")) and hmac.compare_digest(op["token"], _made_token(slug, op["domain"], op["key"], stamp))


def _a_key(item: Any) -> tuple[str, str] | None:
    """[ADDED v3.90.0] An entry the panel names - a removal the user declined - or None when it is not one."""
    if not isinstance(item, dict) or item.get("domain") not in _DOMAIN_FILES:
        return None
    key = str(item.get("key") or "")
    return (item["domain"], key) if 0 < len(key) <= 255 else None


async def _wait_for_reloads(hass: HomeAssistant, ops: list[dict], since: datetime) -> tuple[set[str], list[str]]:
    """[ADDED v3.85.0] Home Assistant's config API reloads in the background after it writes. An entry it saved is
    reloaded once its entity is back, set up after the save began; one it removed, once its entity is gone. Not so within
    RELOAD_WAIT_SECONDS, or back unavailable, is a failure, said next to the save and never hidden behind it (RULE 10).
    Returns the domains that failed, and why."""
    ent_reg = er.async_get(hass)
    pending = {(op["domain"], op["key"], op["op"]) for op in ops}
    bad: set[str] = set()
    errors: list[str] = []
    deadline = time.monotonic() + RELOAD_WAIT_SECONDS
    while pending:
        for item in sorted(pending):
            domain, key, op = item
            entity_id = ent_reg.async_get_entity_id(domain, _ENTITY_PLATFORM[domain], key)
            if op == "remove":
                if entity_id is None:
                    pending.discard(item)
                continue
            state = hass.states.get(entity_id) if entity_id else None
            # [CHANGED v3.88.0] Home Assistant removes a changed entry's entity and adds it again; in between, its
            # registry entry writes "unavailable" with restored: true. That is the reload under way, not its failure:
            # the second save of a recipient was reported as not accepted, though Home Assistant had saved it.
            if state is not None and state.attributes.get(ATTR_RESTORED):
                continue
            if state is not None and state.last_changed >= since:
                pending.discard(item)
                if state.state == STATE_UNAVAILABLE:
                    bad.add(domain)
                    errors.append(f"{entity_id} is unavailable: Home Assistant did not accept it - see Settings ▸ "
                                  "System ▸ Logs")
        if not pending or time.monotonic() >= deadline:
            break
        await asyncio.sleep(0.25)
    for domain, key, op in sorted(pending):
        bad.add(domain)
        errors.append(f"{domain} {key}: Home Assistant has not {'removed' if op == 'remove' else 'reloaded'} it within "
                      f"{int(RELOAD_WAIT_SECONDS)} seconds - see Settings ▸ System ▸ Logs")
    return bad, errors


def async_register_websockets(hass: HomeAssistant) -> None:
    """[CHANGED v3.34.0] Each command carries its own schema and admin requirement on its decorator.
    Writing automations and reading their full configuration are admin actions in Home Assistant's
    own editor, so they are here too."""
    for handler in (
        ws_handle_save_automation, ws_handle_load_automation, ws_handle_list_automations,
        ws_handle_get_automation, ws_handle_delete_automation, ws_handle_verify_automation,
        ws_handle_compile_project, ws_handle_save_check, ws_handle_save_done, ws_handle_net_delete_plan,
        ws_handle_net_removed,
        ws_handle_project_list, ws_handle_project_open, ws_handle_project_create,
        ws_handle_project_delete, ws_handle_preview_yaml, ws_handle_net_card,
        ws_handle_ai_status, ws_handle_ai_plan, ws_handle_ai_build,
        ws_handle_net_versions, ws_handle_net_helpers, ws_handle_local_names, ws_handle_local_name_set,
        ws_handle_phones, ws_handle_global, ws_handle_global_plan, ws_handle_global_done,
        ws_handle_global_move_plan, ws_handle_global_move_done, ws_handle_online_fire,
    ):
        websocket_api.async_register_command(hass, handler)
    _LOGGER.debug("[libi] WebSocket commands registered")


# [CHANGED v3.85.0] A page that still runs the LIBI before 3.85.0 - open since before the update - would save with these
# two, which wrote Home Assistant's files. They write nothing now: the page is told to reload.
_OUTDATED = "LIBI was updated: reload this page. Nothing was saved or deleted."


@websocket_api.websocket_command({
    vol.Required("type"): "libi/save_automation",
    vol.Optional("slug"): str,
    vol.Optional("name"): str,
    vol.Optional("nets"): [dict],
    vol.Optional("payload"): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_save_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[CHANGED v3.85.0] Refused: SAVE & COMPILE is libi/compile_project, Home Assistant's config API and libi/save_done."""
    connection.send_error(msg["id"], "outdated_panel", _OUTDATED)


@websocket_api.websocket_command({
    vol.Required("type"): "libi/compile_project",
    vol.Optional("slug", default="default"): str,
    vol.Optional("name", default=""): str,
    vol.Required("nets"): [dict],
    # [ADDED v3.91.0] The revision of the project this page opened; None when it opened none. Not sent at all: a page
    # from before 3.91.0.
    vol.Optional("revision"): vol.Any(None, int),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_compile_project(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.85.0] SAVE & COMPILE, step 1 - the user's rule (2026-11-04): compile first, and save only when that
    holds. Every net is compiled; every one that changes something in Home Assistant is checked with Home Assistant's
    own validator, the one its config API runs before it writes. When any of it does not hold, the answer says why and
    nothing is saved. Otherwise it is what to send to Home Assistant's config API. Nothing is written here."""
    slug = msg["slug"] or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    stamp = datetime.now(timezone.utc).isoformat()
    # [ADDED v3.91.0] A page from before 3.91.0 neither checks each change before it sends it nor knows the project's
    # revision: it is told to reload, and nothing is planned.
    if "revision" not in msg:
        connection.send_result(msg["id"], {"ok": False, "stale": True, "errors": [_OUTDATED], "stamp": stamp})
        return
    # [CHANGED v3.90.0] What Home Assistant holds for someone else, so no NET takes it (the HACS review, 2026-11-05).
    ctx = await hass.async_add_executor_job(_save_context_sync, hass, slug)
    if ctx["errors"]:
        connection.send_result(msg["id"], {"ok": False, "errors": ctx["errors"] + ["nothing was saved"], "stamp": stamp})
        return
    # [ADDED v3.91.0] Only the project as this page opened it (RULE 39).
    stale = _stale(ctx, msg.get("revision"))
    if stale:
        connection.send_result(msg["id"], {"ok": False, "stale": True, "errors": [stale], "stamp": stamp})
        return
    entries, errors = _compile_nets(hass, msg["nets"], ctx)
    if errors:
        connection.send_result(msg["id"], {"ok": False, "errors": errors, "stamp": stamp})
        return
    await _originals_as_they_were(hass, slug, entries)
    await _as_last_seen(hass, slug, entries)
    plan = await hass.async_add_executor_job(_plan_save_sync, hass, slug, entries)
    # [CHANGED v3.90.0] What the user may choose to put back is checked as well.
    for op in (plan.get("upserts") or []) + (plan.get("gone") or []):
        # [ADDED v3.87.0] Home Assistant saves a notify action it does not have and fails only when it runs - the user's
        # train reminder (2026-11-04). Checked on what is sent: an entry LIBI does not change is not stopped by one.
        plan["errors"] += [f"{op['label']}: {p}" for p in ai.notify_action_problems(hass, op["domain"], op["config"])]
        problem = await ai.validate_with_home_assistant(hass, op["domain"], op["config"])
        if problem:
            plan["errors"].append(f"{op['label']}: Home Assistant does not accept it: {problem}")
    if plan["errors"]:
        plan = {"ok": False, "errors": plan["errors"]}
    connection.send_result(msg["id"], {**plan, "stamp": stamp})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/save_done",
    vol.Optional("slug", default="default"): str,
    vol.Optional("name", default=""): str,
    vol.Required("nets"): [dict],
    vol.Optional("done", default=[]): [dict],
    vol.Optional("failure"): vol.Any(None, dict),
    vol.Optional("stamp", default=""): str,
    # [ADDED v3.90.0] The removals the user chose to keep in Home Assistant when the panel asked.
    vol.Optional("kept", default=[]): [dict],
    # [ADDED v3.91.0] As libi/compile_project.
    vol.Optional("revision", default=None): vol.Any(None, int),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_save_done(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.85.0] SAVE & COMPILE, step 3, after the panel sent the changes to Home Assistant's config API, which
    stops at the first one refused: the project records what reached Home Assistant's files, read back from them, and
    LIBI waits for every reload. A save is reported as one only when Home Assistant confirms it (RULE 10).
    [CHANGED v3.90.0] The NETs get the keys libi/compile_project gave them: what this save sent is in the files now, so
    it is not taken. What leaves the project and stays in Home Assistant is said.
    [CHANGED v3.91.0] An upsert counts as made only with libi/save_check's token for this save; a page older than the
    project (revision) that sent nothing records nothing."""
    slug = msg["slug"] or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    done = [op for op in (_an_op(x) for x in msg["done"]) if op]
    # [ADDED v3.91.0] Made only what libi/save_check confirmed was created (RULE 38).
    for op in done:
        op["new"] = op["new"] and _made_checked(slug, op, msg["stamp"])
    kept = [item for item in (_a_key(x) for x in msg["kept"]) if item]
    failure = msg.get("failure") if isinstance(msg.get("failure"), dict) else None
    sent = [(op["domain"], op["key"]) for op in done if op["op"] == "upsert"]
    ctx = await hass.async_add_executor_job(_save_context_sync, hass, slug, sent)
    errors = list(ctx["errors"])
    # [ADDED v3.91.0] A page older than the project records nothing over it. What it sent passed libi/save_check with
    # that revision just before it went, so another page saved in the moment between: it is recorded - what LIBI made
    # is never lost track of - and said.
    stale = "" if errors else _stale(ctx, msg.get("revision"))
    if stale and not done:
        errors.append(stale)
    elif stale:
        errors.append("Another LIBI page saved this project at the same moment: open the project again and check it.")
    result: dict = {"saved": False, "errors": []}
    if not errors or (stale and done and not ctx["errors"]):
        entries, compile_errors = _compile_nets(hass, msg["nets"], ctx)
        errors += compile_errors
        await _originals_as_they_were(hass, slug, entries)
        result = await hass.async_add_executor_job(_record_save_sync, hass, slug, msg["name"], msg["nets"], entries,
                                                   bool(done) or failure is None, done, kept)
    errors = list(result.get("errors") or []) + errors
    if failure:
        what = str(failure.get("label") or f"{failure.get('domain', '')} {failure.get('key', '')}").strip()
        # [ADDED v3.91.0] One libi/save_check stopped is not one Home Assistant refused.
        why = "not sent" if failure.get("stopped") else "Home Assistant refused it"
        errors.append(f"{what}: {why}: {str(failure.get('message') or 'no reason given')[:300]}")
        not_sent = failure.get("not_sent")
        if isinstance(not_sent, int) and not_sent > 0:
            errors.append(f"{not_sent} more change(s) were not sent.")
    bad, reload_errors = await _wait_for_reloads(hass, done, _since(msg["stamp"]))
    errors += reload_errors
    written = sorted({op["domain"] for op in done})
    saved = bool(result.get("saved"))
    counts = result.get("counts") or {}
    if saved:
        message = ("Saved. {automations} automations, {scripts} scripts, {scenes} scenes in this project; {changed} "
                   "sent to Home Assistant.").format(automations=counts.get("automations", 0),
                                                     scripts=counts.get("scripts", 0),
                                                     scenes=counts.get("scenes", 0),
                                                     changed=f"{len(done)} change(s)" if done else "no change")
    else:
        message = "Not saved."
    # [ADDED v3.90.0] What left the project and stays in Home Assistant, said: no save touches it again.
    released = result.get("released") or []
    if released:
        message += (f" Left in Home Assistant as {'it is' if len(released) == 1 else 'they are'}, and no longer in this "
                    f"project: {', '.join(released[:10])}{' and more' if len(released) > 10 else ''}.")
    if errors:
        message += " Problems: " + "; ".join(errors[:5])
    connection.send_result(msg["id"], {"status": "error" if errors else "ok",
                                       "saved": saved,
                                       "message": message,
                                       "slug": slug,
                                       "written": written,
                                       "reloaded": [d for d in written if d not in bad],
                                       "versions": result.get("versions") or {},
                                       "released": released,
                                       # [ADDED v3.91.0] The project's revision now, None when it was not written.
                                       "revision": result.get("revision"),
                                       # [ADDED v3.93.0] The key of each NET in Home Assistant now, for Online.
                                       "keys": result.get("keys") or {},
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
    # [ADDED v3.85.0] The NET it is loaded into, whose V1 and V2 it becomes (the user's rule of 2026-11-04).
    vol.Optional("slug"): str,
    vol.Optional("net_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_get_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    auto_id = msg["automation_id"]
    slug = msg.get("slug") or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
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
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "parse_error", str(err))
        return
    versions = {}
    if msg.get("net_id"):
        opened = {**ast_net, "id": msg["net_id"], "ha_id": auto_id}
        versions = await hass.async_add_executor_job(_record_original_sync, hass, slug, opened, auto_id,
                                                     copy.deepcopy(target["raw"]))
    connection.send_result(msg["id"], {"net": ast_net, "verify": report, "versions": versions})


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
    vol.Optional("automation_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_delete_automation(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[CHANGED v3.85.0] Refused: deleting is the panel's call to Home Assistant's config API, then libi/net_removed."""
    connection.send_error(msg["id"], "outdated_panel", _OUTDATED)


@websocket_api.websocket_command({
    vol.Required("type"): "libi/net_delete_plan",
    vol.Optional("slug", default="default"): str,
    vol.Required("net_id"): str,
    vol.Required("nets"): [dict],
    # [ADDED v3.91.0] As libi/compile_project.
    vol.Optional("revision"): vol.Any(None, int),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_net_delete_plan(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.85.0] What deleting a NET can do - the user's rule (2026-11-04): delete it completely, or delete it and
    go back to V1, the original as Home Assistant had it before LIBI changed it. Says where the NET's entry is in Home
    Assistant (the key of a script depends on the other nets) and what its V1 holds. Reads only.
    [CHANGED v3.91.0] Only the NET's own entry, by name, and whether LIBI made it; only from the project as the page
    opened it."""
    slug = msg["slug"] or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    net = next((n for n in msg["nets"] if str(n.get("id") or "") == msg["net_id"]), None)
    if net is None:
        connection.send_error(msg["id"], "not_found", "No such NET")
        return
    # [CHANGED v3.90.0] The key a save gives the NET, which may not be the one Home Assistant holds for someone else: the
    # entry deleted is this NET's own.
    ctx = await hass.async_add_executor_job(_save_context_sync, hass, slug)
    errors = (ctx["errors"] or ([_OUTDATED] if "revision" not in msg else [])
              or [e for e in [_stale(ctx, msg.get("revision"))] if e])
    if errors:
        connection.send_result(msg["id"], {"domain": "", "key": "", "stamp": "", "in_ha": False, "original": None,
                                           "errors": errors})
        return
    entries, _errors = _compile_nets(hass, msg["nets"], ctx)
    entry = next((e for e in entries if e["net"] is net), None)
    if entry:
        domain, key = entry["domain"], entry["key"]
    elif net.get("ha_id") and net_level(net) == "automation":
        domain, key = "automation", str(net["ha_id"])
    else:
        domain, key = "", ""
    # [ADDED v3.91.0] RULE 38: only the NET's own entry - one this project saved, or the automation opened into this NET
    # - is offered for deletion; one it only names is someone else's.
    if domain and key not in ctx["owned"].get(domain, ()) and key not in ctx["opened"].get(msg["net_id"], ()):
        domain, key = "", ""
    stamp = datetime.now(timezone.utc).isoformat()
    info = await hass.async_add_executor_job(_net_entry_sync, hass, slug, msg["net_id"], domain, key)
    # The stamp is when the delete began: libi/net_removed waits for what Home Assistant does after it. [ADDED v3.91.0]
    # And, for the dialog, whether LIBI made the entry or it was opened from Home Assistant (made).
    connection.send_result(msg["id"], {"domain": domain, "key": key, "stamp": stamp,
                                       "made": bool(domain) and key in ctx["made"].get(domain, ()), **info})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/net_removed",
    vol.Optional("slug", default="default"): str,
    vol.Required("net_id"): str,
    vol.Required("mode"): vol.In(["deleted", "restored", "kept"]),
    vol.Optional("domain", default=""): vol.In(["", "automation", "script", "scene"]),
    vol.Optional("key", default=""): str,
    vol.Optional("stamp", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_net_removed(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.85.0] A NET deleted from the canvas: with its entry, which the panel removed through Home Assistant's
    config API; with V1 put back there the same way; or with its entry left in Home Assistant as it is. The project lets
    go of it, and LIBI waits for Home Assistant to remove or reload the entry (RULE 10)."""
    slug = msg["slug"] or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    domain, key = msg["domain"], msg["key"][:255]
    revision = await hass.async_add_executor_job(_release_net_sync, hass, slug, msg["net_id"], domain, key)
    errors: list[str] = []
    if domain and key and msg["mode"] in ("deleted", "restored"):
        op = {"domain": domain, "key": key, "op": "remove" if msg["mode"] == "deleted" else "upsert"}
        _bad, errors = await _wait_for_reloads(hass, [op], _since(msg["stamp"]))
    # [CHANGED v3.91.0] With the project's revision now, which this page saves with from here on.
    connection.send_result(msg["id"], {"ok": not errors, "errors": errors, "revision": revision})


def _save_check_sync(hass: HomeAssistant, slug: str, revision: Any, domain: str, key: str, before: str,
                     new: bool, stamp: str) -> dict:
    """[ADDED v3.91.0] libi/save_check, read under the lock: the project as the page opened it (_stale), and the entry as
    the plan found it (its fingerprint); a create still a create - not there, and no other project's."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        exists = os.path.exists(_project_path(hass, slug))
        project = _read_project_sync(hass, slug)
        protected = _all_owned_except_sync(hass, slug)
    if exists and project is None:
        errors.append(f"the project {slug} could not be read")
    if errors:
        return {"ok": False, "error": "; ".join(errors)}
    stale = _stale({"exists": exists, "revision": _revision_of(project) if exists else None}, revision)
    if stale:
        return {"ok": False, "error": stale}
    if _fingerprint(_file_entry(files[domain], key)) != before:
        return {"ok": False, "error": "it changed in Home Assistant after SAVE & COMPILE checked it - in its own editor, "
                                      "or from another LIBI page or project - so it was not sent. Press SAVE & COMPILE "
                                      "again."}
    if new and (before or key in protected[_OWNED_KEYS[domain]]):
        return {"ok": False, "error": "another LIBI project took this key after SAVE & COMPILE checked it, so it was not "
                                      "sent. Press SAVE & COMPILE again."}
    return {"ok": True, "token": _made_token(slug, domain, key, stamp) if new else ""}


@websocket_api.websocket_command({
    vol.Required("type"): "libi/save_check",
    vol.Optional("slug", default="default"): str,
    vol.Optional("revision", default=None): vol.Any(None, int),
    vol.Required("domain"): vol.In(list(_DOMAIN_FILES)),
    vol.Required("key"): vol.All(str, vol.Length(min=1, max=255)),
    vol.Required("before"): str,
    vol.Optional("new", default=False): bool,
    vol.Optional("stamp", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_save_check(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.91.0] CLAUDE.md RULE 38: just before the panel sends one change to Home Assistant's config API - a change
    SAVE & COMPILE planned, or the Delete NET dialog's - LIBI checks again that it is still the change that was planned:
    the project as this page opened it, the entry as the plan found it, and a create still a create. Not so, and the
    panel sends nothing more: what changed in between - while the questions were open, the user created the script in
    Home Assistant's editor - is never written over. A create confirmed here gets a token, which libi/save_done takes as
    the proof that this project made it. Reads only."""
    slug = msg["slug"] or "default"
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    connection.send_result(msg["id"], await hass.async_add_executor_job(
        _save_check_sync, hass, slug, msg["revision"], msg["domain"], msg["key"], msg["before"], msg["new"],
        msg["stamp"]))


@websocket_api.websocket_command({
    vol.Required("type"): "libi/online_fire",
    vol.Required("entity_id"): vol.All(str, vol.Match(r"^automation\.[a-z0-9_]+$")),
    vol.Optional("trigger", default=None): vol.Any(None, vol.All(int, vol.Range(min=0, max=9999))),
    vol.Optional("trigger_id", default=None): vol.Any(None, vol.All(str, vol.Length(max=255))),
    vol.Optional("net", default=None): vol.Any(None, dict),
    vol.Optional("element_id", default=None): vol.Any(None, vol.All(str, vol.Length(max=255))),
    vol.Optional("skip_condition", default=False): bool,
    vol.Optional("fire", default=False): bool,
    vol.Optional("before", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_online_fire(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.94.0] Online's Real (online.py): without fire, what a run of the automation as if the trigger fired
    would be - or why LIBI does not run it - for the panel to ask the user. With fire, after the user confirmed: the plan
    is made again, and the run starts only when it is still the automation the user was shown (before). An
    administrator's action, as running an automation is in Home Assistant's own editor."""
    answer, entity, variables = online.fire_plan(hass, msg["entity_id"], msg["trigger"], msg["trigger_id"],
                                                 msg["net"], msg["element_id"])
    if not answer["ok"] or not msg["fire"]:
        connection.send_result(msg["id"], answer)
        return
    if msg["before"] != answer["before"]:
        connection.send_result(msg["id"], {"ok": False, "stale": True, "reason": (
            "The automation changed in Home Assistant since you were asked, so it was not run. Try again.")})
        return
    online.fire(hass, entity, variables, msg["skip_condition"], connection.context(msg))
    connection.send_result(msg["id"], {**answer, "fired": True})


# [ADDED v3.77.0] ------------------------------------------------------- the local variables of a NET
# A helper the NET uses and nothing else uses is what a ladder programmer calls a local variable. Deleting a NET asks
# whether to delete them too - the user's request. LIBI only finds them here; the panel deletes the ones the user
# confirms with Home Assistant's own helper commands, and only once the NET's automation is gone.
_HELPER_ID = re.compile(r"(?<!\w)(?:" + "|".join(ai.HELPER_DOMAINS) + r")\.[a-z0-9_]+(?!\w)")


def _as_text(item) -> str:
    return json.dumps(item, ensure_ascii=False, default=str)


def _lists(members, entity_id: str) -> bool:
    return members == entity_id or (isinstance(members, (list, tuple)) and entity_id in members)


def _helper_users_sync(hass: HomeAssistant, slug: str, automation_id: str) -> dict:
    """[ADDED v3.77.0] Everything else that could use a helper, as text with a name: every automation in
    automations.yaml but the one being deleted (its text is returned apart, as more of what the NET uses), every script
    and scene, and every NET of the other projects - the open project is the canvas, which the panel sends. Read only.
    A file that cannot be read is an error, and then no helper counts as local (RULE 31)."""
    out = {"own": "", "users": [], "error": ""}
    with _FILE_LOCK:
        automations = _read_target_sync(_get_automations_path(hass), [])
        scripts = _read_target_sync(_get_scripts_path(hass), {})
        scenes = _read_target_sync(_get_scenes_path(hass), [])
        if automations is None or scripts is None or scenes is None:
            out["error"] = "automations.yaml, scripts.yaml or scenes.yaml could not be read"
            return out
        for item in automations:
            if isinstance(item, dict) and automation_id and str(item.get("id", "")) == automation_id:
                out["own"] = _as_text(item)
            elif isinstance(item, dict):
                out["users"].append((f'automation "{item.get("alias") or item.get("id")}"', _as_text(item)))
        for key, item in scripts.items():
            name = item.get("alias") if isinstance(item, dict) else ""
            out["users"].append((f'script "{name or key}"', _as_text(item)))
        for item in scenes:
            if isinstance(item, dict):
                out["users"].append((f'scene "{item.get("name") or item.get("id")}"', _as_text(item)))
        directory = _get_projects_dir(hass)
        for fname in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
            other = fname[: -len(PROJECT_EXT)]
            if not fname.endswith(PROJECT_EXT) or other == slug or not valid_project_slug(other):
                continue
            data = _read_project_sync(hass, other)
            if data is None:
                out["error"] = f"the project {fname} could not be read"
                return out
            for net in data.get("nets") or []:
                if isinstance(net, dict):
                    out["users"].append((f'NET "{net.get("name") or net.get("id")}" of project "{data.get("name") or other}"',
                                         _as_text(net)))
    return out


@callback
def _local_helpers(hass: HomeAssistant, net: dict, nets: list, texts: dict, automation_id: str) -> dict:
    """[ADDED v3.77.0] The NET's local variables: the helpers its drawing - or its automation being deleted - names and
    nothing else uses: no text of _helper_users_sync, no other NET on the canvas, and, when no text names them, neither
    Home Assistant's own index of automations and scripts (which holds the ones written outside automations.yaml too,
    but sees an entity_id, never a template) nor a group, a scene or any other entity that lists it as a member. Only a
    helper made in Home Assistant's UI can be deleted; one written in YAML is kept."""
    from homeassistant.components.automation import automations_with_entity  # noqa: PLC0415
    from homeassistant.components.script import scripts_with_entity  # noqa: PLC0415

    if texts["error"]:
        return {"helpers": [], "kept": [], "error": texts["error"]}
    users = list(texts["users"]) + [
        (f'NET "{other.get("name") or other.get("id")}" on the canvas', _as_text(other))
        for other in nets if isinstance(other, dict) and other.get("id") != net.get("id")]
    # The automation being deleted is still loaded until the reload: the index lists it, and it does not count.
    going = {s.entity_id for s in hass.states.async_all("automation")
             if automation_id and str(s.attributes.get("id", "")) == automation_id}
    registry = er.async_get(hass)
    helpers, kept = [], []
    for eid in sorted(set(_HELPER_ID.findall(_as_text(net) + texts["own"]))):
        state = hass.states.get(eid)
        if state is None:
            continue
        name = ai._sanitize(state.name)[:60]
        by = [label for label, text in users if ai.mentions(eid, text)]
        reason = ""
        if not by:
            try:
                index = [x for x in automations_with_entity(hass, eid) if x not in going] + scripts_with_entity(hass, eid)
                # A group, a scene and every other entity made of others list their members in entity_id.
                index += [s.entity_id for s in hass.states.async_all() if _lists(s.attributes.get("entity_id"), eid)]
                by = [hass.states.get(x).name if hass.states.get(x) else x for x in index]
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("[libi] could not ask Home Assistant what uses %s: %s", eid, ai._sanitize(err))
                reason = "not checked: Home Assistant could not say what uses it"
        if by:
            reason = f"used by {ai._sanitize(by[0])[:80]}" + (f" and {len(by) - 1} more" if len(by) > 1 else "")
        entry = registry.async_get(eid)
        if not reason and (state.attributes.get("editable") is not True or entry is None or entry.platform != state.domain):
            reason = "written in YAML, so it cannot be deleted from here"
        if reason:
            kept.append({"entity_id": eid, "name": name, "reason": reason})
        else:
            helpers.append({"entity_id": eid, "name": name, "domain": state.domain, "item_id": entry.unique_id})
    return {"helpers": helpers, "kept": kept, "error": ""}


@websocket_api.websocket_command({
    vol.Required("type"): "libi/net_helpers",
    vol.Required("net"): dict,
    vol.Optional("nets", default=[]): [dict],
    vol.Optional("slug", default=""): str,
    vol.Optional("automation_id", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_net_helpers(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.77.0] The local variables of a NET (_local_helpers), for the question the panel asks when the NET is
    deleted. Reads only. slug: the open project, whose NETs are the canvas (nets). automation_id: the NET's automation
    the panel is deleting, the one user that does not count; asked again without it once that automation is gone."""
    if msg["slug"] and not valid_project_slug(msg["slug"]):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    texts = await hass.async_add_executor_job(_helper_users_sync, hass, msg["slug"], msg["automation_id"])
    connection.send_result(msg["id"], _local_helpers(hass, msg["net"], msg["nets"], texts, msg["automation_id"]))

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
    # [ADDED v3.47.0] What runs now becomes V1, or the next version when it was changed elsewhere.
    # [CHANGED v3.85.0] An automation opened for the first time is V1, the original as it is in Home Assistant, and V2.
    versions = await hass.async_add_executor_job(
        _record_open_versions_sync, hass, slug, hydrated["nets"], live)
    connection.send_result(msg["id"], {
        "slug": data.get("slug") or slug,
        "name": data.get("name") or slug,
        "nets": hydrated["nets"],
        "stats": hydrated["stats"],
        "versions": versions,
        "updated": data.get("updated") or "",
        # [ADDED v3.91.0] What this page saves with: only this project as it is now (_stale).
        "revision": _revision_of(data),
        # [ADDED v3.93.0] The key of each NET in Home Assistant, for Online: the automation of a NET drawn in LIBI.
        "keys": data.get("keys") if isinstance(data.get("keys"), dict) else {},
    })


@websocket_api.websocket_command({
    vol.Required("type"): "libi/local_names",
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_local_names(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.86.0] The names the user gave entities in LIBI only."""
    names = await hass.async_add_executor_job(_read_local_names_sync, hass)
    if names is None:
        connection.send_error(msg["id"], "read_failed", f"{LOCAL_NAMES_FILE} could not be read")
        return
    connection.send_result(msg["id"], {"names": names})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/local_name_set",
    vol.Required("entity_id"): str,
    vol.Required("name"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_local_name_set(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.86.0] Gives an entity a name in LIBI only, or an empty name takes it away. Home Assistant is not changed:
    the name is shown by LIBI alone. One line of plain text; the panel escapes it wherever it shows it."""
    entity_id = str(msg["entity_id"]).strip()
    if not _LOCAL_NAME_ENTITY.match(entity_id):
        connection.send_error(msg["id"], "invalid_entity_id", "Not an entity id")
        return
    name = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(msg["name"])).split())
    if len(name) > MAX_LOCAL_NAME:
        connection.send_error(msg["id"], "name_too_long", f"A name in LIBI is at most {MAX_LOCAL_NAME} characters")
        return
    names = await hass.async_add_executor_job(_set_local_name_sync, hass, entity_id, name)
    if names is None:
        connection.send_error(msg["id"], "read_failed", f"{LOCAL_NAMES_FILE} could not be read, so nothing was changed")
        return
    connection.send_result(msg["id"], {"names": names})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/phones",
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_phones(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.87.0] The phones the Companion app registered, each with the action that sends to it - the list the MOVE
    NOTIFY / TTS block picks from (ai.phone_list). Home Assistant's memory only; nothing is written."""
    connection.send_result(msg["id"], {"phones": ai.phone_list(hass)})


# ---- [ADDED v3.88.0] LIBI Global: the recipients of messages (recipients.py) -----------------------------------------

def _read_files_sync(hass: HomeAssistant) -> tuple[dict, list[str]]:
    """[ADDED v3.88.0] automations.yaml, scripts.yaml and scenes.yaml as they are now, read under the lock."""
    with _FILE_LOCK:
        return _read_home_assistant_files(hass)


def _owners_locked(hass: HomeAssistant) -> tuple[dict[tuple[str, str], dict], list[str]]:
    """[ADDED v3.89.0] The project of LIBI's that saved each automation and script (its "owned"), and whether a NET of it
    draws that entry: every one but an automation NET loaded from Home Assistant (ha_id), which is drawn again from its
    automation each time the project opens. A drawn one is saved from its drawing, which would put a phone replaced in its
    YAML back. With the projects that could not be read. Called with _FILE_LOCK held."""
    out: dict[tuple[str, str], dict] = {}
    unreadable: list[str] = []
    directory = _get_projects_dir(hass)
    # Not _list_projects_sync: it leaves out a project it cannot read, and here one is a reason to change nothing.
    for fname in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        slug = fname[: -len(PROJECT_EXT)] if fname.endswith(PROJECT_EXT) else ""
        if not valid_project_slug(slug):
            continue
        data = _read_project_sync(hass, slug)
        if data is None:
            unreadable.append(slug)
            continue
        linked = {str(n["ha_id"]) for n in data.get("nets") or []
                  if isinstance(n, dict) and n.get("ha_id") and net_level(n) == "automation"}
        owned = data.get("owned") if isinstance(data.get("owned"), dict) else {}
        for domain, owned_key in _OWNED_KEYS.items():
            for key in owned.get(owned_key) or []:
                out[(domain, str(key))] = {"slug": slug, "name": str(data.get("name") or slug)[:60],
                                           "drawn": not (domain == "automation" and str(key) in linked)}
    return out, unreadable


def _read_global_sync(hass: HomeAssistant) -> tuple[dict, list[str], dict, list[str]]:
    """[ADDED v3.89.0] Home Assistant's files and who of LIBI's projects owns what in them, read together under the lock."""
    with _FILE_LOCK:
        files, errors = _read_home_assistant_files(hass)
        owners, unreadable = _owners_locked(hass)
    return files, errors, owners, unreadable


def _entry_calls(files: dict) -> dict[str, list[dict]]:
    """[ADDED v3.88.0] Who calls each action: every automation in automations.yaml and every script in scripts.yaml, by
    the actions its steps call (called_actions), each named by its alias as the user knows it."""
    out: dict[str, list[dict]] = {}

    def add(domain: str, key: str, name: str, steps: Any) -> None:
        for action in dict.fromkeys(called_actions(steps)):
            out.setdefault(action, []).append({"domain": domain, "key": key, "name": name[:100]})

    for item in files.get("automation") or []:
        if isinstance(item, dict):
            key = str(item.get("id") or "")
            add("automation", key, str(item.get("alias") or key), item.get("actions", item.get("action")))
    for key, item in (files.get("script") or {}).items():
        if isinstance(item, dict):
            add("script", str(key), str(item.get("alias") or key), item.get("sequence"))
    return out


def _projects_using_sync(hass: HomeAssistant, action: str) -> list[str]:
    """[ADDED v3.88.0] The NETs of LIBI's projects that hold an action, saved to Home Assistant or not yet. The whole id:
    script.libi_send_to_guy is not in a NET that sends to script.libi_send_to_guy_2."""
    whole = re.compile(re.escape(action) + r"(?![a-z0-9_])")
    found: list[str] = []
    with _FILE_LOCK:
        for entry in _list_projects_sync(hass):
            data = _read_project_sync(hass, entry["slug"]) or {}
            for net in data.get("nets") or []:
                if isinstance(net, dict) and whole.search(json.dumps(net, ensure_ascii=False)):
                    found.append(f'project {data.get("name") or entry["slug"]} ▸ NET "{str(net.get("name") or "")[:60]}"')
    return found


@callback
def _move_why(hass: HomeAssistant, item: dict) -> str:
    """[ADDED v3.89.0] Why nothing can be moved to a recipient, or '' when it can: it must send to one phone - an entry that
    sends to one of several would send to all of them - exactly as LIBI writes it, and run in Home Assistant now."""
    if item["edited"]:
        return "it was changed outside LIBI - save it in LIBI Global first"
    if item["missing"]:
        return "its phone is no longer in Home Assistant"
    if len(item["phones"]) != 1:
        return (f"it sends to {len(item['phones'])} phones, and one that sends to one of them would then send to all of "
                "them - change those by hand if that is what you want")
    if not hass.services.has_service("script", item["key"]):
        return "Home Assistant does not run its script yet - see Settings ▸ System ▸ Logs"
    return ""


@callback
def _global_listing(hass: HomeAssistant, files: dict, owners: dict | None = None) -> dict:
    """[ADDED v3.88.0] LIBI Global as it is now: each recipient in scripts.yaml with its phones - those Home Assistant no
    longer has (missing) - the entries that send to it (used_by) and the ones that still send straight to one of its
    phones (direct), to move to it; and the phones to tick (ai.phone_list).
    [CHANGED v3.89.0] Each direct one with how many of its steps would move to the recipient (moves) and how many would
    not (stays), the project of LIBI's that owns it (owner), and why it would not move (why); the recipient with why
    nothing can move to it (move_why)."""
    phones = ai.phone_list(hass)
    calls = _entry_calls(files)
    owners = owners or {}
    out = []
    for key, config in (files.get("script") or {}).items():
        if not recipients.is_recipient_key(key) or not isinstance(config, dict):
            continue
        item = recipients.read_recipient(key, config)
        item["missing"] = [s for s in item["phones"] if not hass.services.has_service("notify", s.split(".", 1)[1])]
        item["used_by"] = [c for c in calls.get(item["action"], []) if c["key"] != key]
        item["move_why"] = _move_why(hass, item)
        direct: dict[tuple, dict] = {}
        for service in item["phones"]:
            for c in calls.get(service, []):
                if c["domain"] == "script" and recipients.is_recipient_key(c["key"]):
                    continue
                direct.setdefault((c["domain"], c["key"]), dict(c, phones=[]))["phones"].append(service)
        for d in direct.values():
            d["owner"] = owners.get((d["domain"], d["key"]))
            entry = _file_entry(files.get(d["domain"]), d["key"]) if d["key"] else None
            d["moves"], d["stays"], d["why"] = 0, 0, item["move_why"]
            if not item["move_why"] and isinstance(entry, dict):
                _moved, d["moves"], d["stays"] = recipients.move_entry(d["domain"], entry, item["phones"][0],
                                                                       item["action"])
            if d["why"]:
                continue
            if not d["key"]:
                d["why"] = "it has no id, so Home Assistant's editor cannot save it either"
            elif d["owner"] and d["owner"]["drawn"]:
                d["why"] = (f'a NET of LIBI project "{d["owner"]["name"]}" draws it: open that project, and replace it '
                            "there")
            elif not d["moves"]:
                d["why"] = "it sends more to the phone than a message, a title and data - change it by hand"
        item["direct"] = sorted(direct.values(), key=lambda c: (c["name"].lower(), c["key"]))
        out.append(item)
    out.sort(key=lambda r: (r["name"].casefold(), r["key"]))
    return {"recipients": out, "phones": phones}


async def _global_state(hass: HomeAssistant) -> dict:
    """[ADDED v3.88.0] LIBI Global, or why it cannot be read: a file that cannot be read lists nothing, and then nothing
    can be saved either (RULE 5)."""
    files, errors, owners, _unreadable = await hass.async_add_executor_job(_read_global_sync, hass)
    return _global_state_of(hass, files, errors, owners)


@callback
def _global_state_of(hass: HomeAssistant, files: dict, errors: list[str], owners: dict) -> dict:
    """[ADDED v3.89.0] LIBI Global from the files as they were read."""
    if errors:
        return {"ok": False, "errors": errors, "recipients": [], "phones": ai.phone_list(hass)}
    return {"ok": True, "errors": [], **_global_listing(hass, files, owners)}


@websocket_api.websocket_command({vol.Required("type"): "libi/global"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_global(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.88.0] LIBI Global: the recipients as scripts.yaml holds them, and the phones. Nothing is written.
    [CHANGED v3.92.0] And who uses each entity named in LIBI only (name_users): the Global tab lists those names too."""
    files, errors, owners, _unreadable = await hass.async_add_executor_job(_read_global_sync, hass)
    state = _global_state_of(hass, files, errors, owners)
    names = None if errors else await hass.async_add_executor_job(_read_local_names_sync, hass)
    state["name_users"] = _name_users(files, names) if names else {}
    connection.send_result(msg["id"], state)


def _name_users(files: dict, names: dict) -> dict[str, list[dict]]:
    """[ADDED v3.92.0] For each entity named in LIBI only, the automations, scripts and scenes of Home Assistant's files
    that use it - its whole id in them, so light.hall is not in light.hall_2 - each by its name as the user knows it."""
    entries: list[tuple[str, str, str, str]] = []
    for domain in ("automation", "scene"):
        for item in files.get(domain) or []:
            if isinstance(item, dict):
                key = str(item.get("id") or "")
                entries.append((domain, key, str(item.get("alias") or item.get("name") or key),
                                json.dumps(item, ensure_ascii=False, default=str)))
    for key, item in (files.get("script") or {}).items():
        if isinstance(item, dict):
            entries.append(("script", str(key), str(item.get("alias") or key), json.dumps(item, ensure_ascii=False, default=str)))
    out: dict[str, list[dict]] = {}
    for entity_id in names:
        whole = re.compile(r"(?<![a-z0-9_.])" + re.escape(entity_id) + r"(?![a-z0-9_])")
        out[entity_id] = [{"domain": domain, "key": key, "name": name[:100]}
                          for domain, key, name, text in entries if whole.search(text)]
    return out


@websocket_api.websocket_command({
    vol.Required("type"): "libi/global_plan",
    vol.Optional("key", default=""): str,
    vol.Optional("name", default=""): str,
    vol.Optional("phones", default=[]): [str],
    vol.Optional("remove", default=False): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_global_plan(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.88.0] LIBI Global, step 1 of a save, as in SAVE & COMPILE: the recipient's script, built from its name
    and phones that are phones of this Home Assistant now, and checked with Home Assistant's own validator - or, to delete
    it, that nothing sends to it, saved or not. Nothing is written: the answer is what to send to Home Assistant's config
    API, nothing when it would not change, or why not."""
    stamp = datetime.now(timezone.utc).isoformat()

    def refuse(*errors: str) -> None:
        connection.send_result(msg["id"], {"ok": False, "errors": list(errors), "stamp": stamp})

    files, errors = await hass.async_add_executor_job(_read_files_sync, hass)
    if errors:
        refuse(*errors, "nothing was changed")
        return
    listing = _global_listing(hass, files)
    key = msg["key"].strip()
    current = next((r for r in listing["recipients"] if r["key"] == key), None) if key else None
    if key and current is None:
        refuse("This recipient is no longer in scripts.yaml. Open LIBI ▸ Global again.")
        return
    if msg["remove"]:
        if current is None:
            refuse("No recipient was named, so nothing was deleted.")
            return
        users = [f'{c["domain"]} "{c["name"]}"' for c in current["used_by"]]
        users += await hass.async_add_executor_job(_projects_using_sync, hass, current["action"])
        if users:
            refuse(f'{current["name"]} is not deleted: it is still sent to by {"; ".join(dict.fromkeys(users))[:600]}. '
                   "Send those to another recipient or a phone first.")
            return
        connection.send_result(msg["id"], {"ok": True, "unchanged": False, "key": key, "stamp": stamp, "op": {
            "domain": "script", "key": key, "op": "remove", "label": current["name"]}})
        return
    name = recipients.clean_name(msg["name"])
    if not name:
        refuse("A recipient needs a name.")
        return
    if any(r["name"].casefold() == name.casefold() for r in listing["recipients"] if r["key"] != key):
        refuse(f"There is already a recipient named {name}.")
        return
    phones = {p["service"]: p for p in listing["phones"] if not p["shared"]}
    picked = list(dict.fromkeys(s.strip() for s in msg["phones"]))
    gone = [s for s in picked if s not in phones]
    if gone:
        refuse(f"{', '.join(gone)[:300]}: not a phone of this Home Assistant now - removed from the Companion app, or "
               "sharing its name with another phone there? Untick it.")
        return
    if not picked:
        refuse("Tick at least one phone.")
        return
    if len(picked) > recipients.MAX_PHONES:
        refuse(f"A recipient sends to {recipients.MAX_PHONES} phones at most.")
        return
    # In the order of the list, so the same phones make the same script whichever was ticked first.
    chosen = [(p["service"], bool(p["speaks"])) for p in listing["phones"] if p["service"] in picked and not p["shared"]]
    config = recipients.recipient_config(name, chosen)
    if not key:
        taken = {str(k) for k in files["script"]} | {state.object_id for state in hass.states.async_all("script")}
        key = recipients.new_key(name, taken)
    existing = files["script"].get(key)
    if isinstance(existing, dict) and same_config(existing, config):
        connection.send_result(msg["id"], {"ok": True, "unchanged": True, "key": key, "stamp": stamp})
        return
    problem = await ai.validate_with_home_assistant(hass, "script", config)
    if problem:
        refuse(f"Home Assistant does not accept it: {problem}")
        return
    connection.send_result(msg["id"], {"ok": True, "unchanged": False, "key": key, "stamp": stamp, "op": {
        "domain": "script", "key": key, "op": "upsert", "config": config, "label": name}})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/global_done",
    vol.Required("key"): str,
    vol.Required("op"): vol.In(["upsert", "remove"]),
    vol.Optional("label", default=""): str,
    vol.Optional("failure"): vol.Any(None, dict),
    vol.Optional("stamp", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_global_done(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.88.0] LIBI Global, step 3, after the panel sent the recipient to Home Assistant's config API:
    scripts.yaml is read back - the browser's word is not taken for it - and LIBI waits for the reload. Saved only when
    the file holds it as LIBI writes it (or, deleted, no longer holds it); a reload that fails is said next to it, never
    hidden behind saved (RULE 10). The answer carries LIBI Global as it is now."""
    key = msg["key"]
    if not recipients.is_recipient_key(key):
        connection.send_error(msg["id"], "invalid_key", "Not a recipient of LIBI Global")
        return
    errors: list[str] = []
    failure = msg.get("failure") if isinstance(msg.get("failure"), dict) else None
    reloaded = False
    if failure:
        errors.append(f"Home Assistant refused it: {str(failure.get('message') or 'no reason given')[:300]}")
    else:
        bad, reload_errors = await _wait_for_reloads(hass, [{"domain": "script", "key": key, "op": msg["op"]}],
                                                     _since(msg["stamp"]))
        errors += reload_errors
        reloaded = not bad
    state = await _global_state(hass)
    errors += state["errors"]
    there = next((r for r in state["recipients"] if r["key"] == key), None)
    name = there["name"] if there else (recipients.clean_name(msg["label"]) or key)
    saved = False
    if state["ok"] and not failure:
        if msg["op"] == "upsert":
            saved = there is not None and not there["edited"]
            if not saved:
                errors.append("scripts.yaml does not hold it as LIBI wrote it: Home Assistant did not save it.")
        else:
            saved = there is None
            if not saved:
                errors.append("It is still in scripts.yaml: Home Assistant did not delete it.")
    if saved and not errors:
        message = (f"Saved. Every NET that sends to {name} sends to these phones from now on." if msg["op"] == "upsert"
                   else f"Deleted: {name}.")
    elif saved:
        message = f"{'Saved to' if msg['op'] == 'upsert' else 'Deleted from'} scripts.yaml, but: " + "; ".join(errors[:5])
    else:
        message = "Not saved: " + "; ".join(errors[:5])
    connection.send_result(msg["id"], {**state, "status": "error" if errors else "ok", "saved": saved,
                                       "reloaded": saved and reloaded, "message": message, "errors": errors,
                                       "key": key})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/global_move_plan",
    vol.Required("key"): str,
    vol.Optional("slug", default=""): str,
    vol.Optional("entries", default=[]): [dict],
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_global_move_plan(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                                     msg: dict[str, Any]) -> None:
    """[ADDED v3.89.0] A phone replaced with its recipient, step 1 - the user's request (2026-11-05): in each automation
    and script the user ticked that sends straight to the one phone of a recipient, the steps that send to it call the
    recipient instead, nothing else changed (recipients.move_entry), and each is checked with Home Assistant's own
    validator. Only entries libi/global lists as movable now: not one a NET of LIBI draws - its next save would put the
    phone back; the NETs of the open project (slug) are changed on its page - and not when a project cannot be read, as
    then LIBI cannot tell. Anything ticked that does not hold refuses the whole of it. Nothing is written: the answer is
    what to send to Home Assistant's config API, or why not."""
    stamp = datetime.now(timezone.utc).isoformat()

    def refuse(*errors: str) -> None:
        connection.send_result(msg["id"], {"ok": False, "errors": list(errors), "stamp": stamp})

    key = msg["key"]
    if not recipients.is_recipient_key(key):
        connection.send_error(msg["id"], "invalid_key", "Not a recipient of LIBI Global")
        return
    files, errors, owners, unreadable = await hass.async_add_executor_job(_read_global_sync, hass)
    if errors or unreadable:
        refuse(*errors, *[f"project {slug} could not be read, so LIBI cannot tell whether a NET draws them"
                          for slug in unreadable], "nothing was changed")
        return
    current = next((r for r in _global_listing(hass, files, owners)["recipients"] if r["key"] == key), None)
    if current is None:
        refuse("This recipient is no longer in scripts.yaml. Open LIBI ▸ Global again.")
        return
    if current["move_why"]:
        refuse(f'Nothing can be sent through {current["name"]}: {current["move_why"]}.')
        return
    wanted = list(dict.fromkeys((str(e.get("domain") or ""), str(e.get("key") or "")) for e in msg["entries"]))
    if not wanted:
        refuse("Nothing was ticked, so nothing was changed.")
        return
    direct = {(d["domain"], d["key"]): d for d in current["direct"]}
    ops: list[dict] = []
    problems: list[str] = []
    for domain, entry_key in wanted:
        d = direct.get((domain, entry_key))
        if d is None:
            problems.append(f"{domain} {entry_key[:60]} no longer sends straight to {current['name']}'s phone")
        elif d["why"] or not d["moves"]:
            problems.append(f'{d["name"]}: {d["why"] or "nothing in it can be moved"}')
        elif d["owner"] and d["owner"]["slug"] == msg["slug"]:
            problems.append(f'{d["name"]}: a NET of the project open on this page - it is changed on the page')
        else:
            config, _moves, _stays = recipients.move_entry(domain, _file_entry(files[domain], entry_key),
                                                           current["phones"][0], current["action"])
            problem = await ai.validate_with_home_assistant(hass, domain, config)
            if problem:
                problems.append(f'{d["name"]}: Home Assistant does not accept it: {problem}')
                continue
            ops.append({"domain": domain, "key": entry_key, "op": "upsert", "config": config, "label": d["name"]})
    if problems:
        refuse(*problems[:10], "Nothing was changed. Open LIBI ▸ Global again.")
        return
    connection.send_result(msg["id"], {"ok": True, "key": key, "ops": ops, "stamp": stamp})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/global_move_done",
    vol.Required("key"): str,
    vol.Optional("done", default=[]): [dict],
    vol.Optional("failure"): vol.Any(None, dict),
    vol.Optional("stamp", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_global_move_done(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                                     msg: dict[str, Any]) -> None:
    """[ADDED v3.89.0] A phone replaced with its recipient, step 3, after the panel sent each entry to Home Assistant's
    config API, which stops at the first one refused: LIBI waits for each reload and reads the files back - the browser's
    word is not taken for it. An entry is moved only when its file calls the recipient and no step that could move still
    sends straight to the phone; a reload that fails is said, never hidden (RULE 10). The answer carries LIBI Global as
    it is now."""
    key = msg["key"]
    if not recipients.is_recipient_key(key):
        connection.send_error(msg["id"], "invalid_key", "Not a recipient of LIBI Global")
        return
    done = [op for op in (_an_op(x) for x in msg["done"])
            if op and op["op"] == "upsert" and op["domain"] in ("automation", "script")]
    errors: list[str] = []
    failure = msg.get("failure") if isinstance(msg.get("failure"), dict) else None
    if failure:
        errors.append(f"{str(failure.get('label') or failure.get('key') or '')[:100]}: Home Assistant refused it: "
                      f"{str(failure.get('message') or 'no reason given')[:300]}")
        not_sent = failure.get("not_sent")
        if isinstance(not_sent, int) and not_sent > 0:
            errors.append(f"{not_sent} more were not sent.")
    bad, reload_errors = await _wait_for_reloads(hass, done, _since(msg["stamp"]))
    errors += reload_errors
    files, read_errors, owners, _unreadable = await hass.async_add_executor_job(_read_global_sync, hass)
    state = _global_state_of(hass, files, read_errors, owners)
    errors += state["errors"]
    there = next((r for r in state["recipients"] if r["key"] == key), None)
    name = there["name"] if there else key
    moved: list[str] = []
    for op in done if state["ok"] else []:
        entry = _file_entry(files[op["domain"]], op["key"])
        label = str((entry or {}).get("alias") or op["key"])[:100]
        left = (recipients.move_entry(op["domain"], entry, there["phones"][0], there["action"])[1]
                if there and len(there["phones"]) == 1 and isinstance(entry, dict) else 0)
        if (isinstance(entry, dict) and there and left == 0
                and there["action"] in called_actions(entry.get(recipients.steps_key(op["domain"], entry)))):
            moved.append(label)
        else:
            errors.append(f"{label}: its file does not show the change - Home Assistant did not save it.")
    if moved and not errors:
        message = f"Replaced in {len(moved)}: {', '.join(moved)}. They send through {name} from now on."
    elif moved:
        message = f"Replaced in {len(moved)}: {', '.join(moved)}. But: " + "; ".join(errors[:5])
    else:
        message = "Nothing was replaced: " + ("; ".join(errors[:5]) or "nothing was sent.")
    connection.send_result(msg["id"], {**state, "status": "error" if errors else "ok", "moved": moved,
                                       "reloaded": bool(done) and not bad, "message": message, "errors": errors,
                                       "key": key})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/net_versions",
    vol.Required("slug"): str,
    vol.Required("net_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_net_versions(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.47.0] Every saved version of one net, newest first, each with its YAML and the
    drawing. Reads only; going back to a version is a normal save from the canvas."""
    slug = msg["slug"]
    if not valid_project_slug(slug):
        connection.send_error(msg["id"], "invalid_slug", "Not a valid project name")
        return
    result = await hass.async_add_executor_job(_net_versions_sync, hass, slug, msg["net_id"])
    if result is None:
        connection.send_error(msg["id"], "read_failed", "The version history could not be read")
        return
    connection.send_result(msg["id"], result)


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


@websocket_api.websocket_command({
    vol.Required("type"): "libi/net_card",
    vol.Required("net"): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_handle_net_card(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """[ADDED v3.63.0] A dashboard card for a net, from what LIBI compiles for it: the settings it reads and the
    devices it switches. The card the AI chat showed was gone with the chat. Nothing is written anywhere."""
    try:
        config = ast_to_yaml(hass, msg["net"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "card_error", ai._sanitize(err))
        return
    alias = config.get("alias") if isinstance(config, dict) else ""
    card = ai.card_for_config(hass, config, str(msg["net"].get("name") or alias or "LIBI")[:60])
    text = yaml.dump(card, default_flow_style=False, allow_unicode=True, sort_keys=False) if card else ""
    connection.send_result(msg["id"], {"yaml": text})


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
    # [ADDED v3.40.0] The nets on the canvas, when the chat's "share" switch is on.
    vol.Optional("nets", default=[]): [dict],
    # [ADDED v3.41.0] The same switch: also the helpers of this Home Assistant (no YAML files).
    vol.Optional("share", default=False): bool,
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
    canvas, by_id = ai.canvas_context(hass, msg["nets"])
    request = messages[-1]["content"]
    # [ADDED v3.62.0] The user's own words, before the context below is added to them.
    said = [m["content"] for m in messages if m["role"] == "user"]
    # [ADDED v3.78.0] The names the message quotes that nothing in this Home Assistant has - a helper it says exists that
    # is gone - told to the model with the helpers, and proposed again below.
    missing = ai.helpers_missing(hass, request)
    extra = [canvas] if canvas else []
    if msg["share"]:
        extra += [ai.helpers_context(hass), ai.missing_context(missing)]
    extra = [x for x in extra if x]
    if extra:
        messages[-1] = {"role": "user", "content": messages[-1]["content"] + "\n\n" + "\n\n".join(extra)}
    try:
        raw = await ai.async_llm_json(hass, settings, ai.PLAN_SYSTEM, messages, ai.PLAN_SCHEMA)
    except ai.AiError as err:
        connection.send_error(msg["id"], "ai_error", str(err))
        return
    plan = ai.clean_plan(hass, raw, set(by_id))
    # [ADDED v3.59.0] The user's rule, from the user's own words: no net is changed that was not named.
    ai.only_named_changes(plan, request, msg["nets"])
    # [ADDED v3.62.0] A message service the user named that does not exist is said now, not at Build; a phone
    # role is optional when the user named services that do exist.
    services, plan["missing_services"] = ai.services_named(hass, said)
    on_canvas = ai.canvas_entities(hass, msg["nets"], by_id)
    candidates = {}
    for role in plan["roles"]:
        candidates[role["id"]] = ai.find_candidates(hass, role, on_canvas)
        await asyncio.sleep(0)
    # [ADDED v3.84.0] A zone chosen on the card is a dropdown of the user's zones, before anything is proposed for it.
    ai.zone_choices(hass, plan, candidates)
    # [ADDED v3.56.0] Settings another automation or script uses are not offered, and a helper that
    # already exists is not proposed again.
    config_text = await hass.async_add_executor_job(_config_text_sync, hass)
    # [ADDED v3.60.0] A helper the user's own message names is offered and ticked, and not hidden below.
    named = ai.roles_for_named_helpers(hass, plan, ai.helpers_named(hass, request), candidates, config_text)
    # [ADDED v3.40.0] A change starts from the devices the net already uses: they are ticked and,
    # when the search did not find them, added to the list, marked as the current ones.
    # [CHANGED v3.75.0] Before anything is hidden or proposed, and with the net's alarm clock in the roles of its days
    # and its time: the net's own helpers are used - by the net itself - so a change of the user's NET 3 hid them and
    # offered new ones.
    preselect: dict[str, list[str]] = {}
    own: set[str] = set()
    if plan["target_net"]:
        net_yaml = by_id.get(plan["target_net"], "")
        own = ai.net_entities(hass, net_yaml)
        preselect = ai.keep_net_alarm_clock(hass, plan, net_yaml)
        taken = {e for ids in [*named.values(), *preselect.values()] for e in ids}
        for rid, ids in ai.preselect(hass, plan, net_yaml, taken, set(named) | set(preselect)).items():
            preselect.setdefault(rid, ids)
        ai.offer_current(hass, candidates, preselect)
        plan["new_helpers"] = [h for h in plan["new_helpers"] if h["role"] not in preselect]
    # [ADDED v3.78.0] A helper the message names that this Home Assistant does not have, in a role no helper of the user's
    # fills: proposed again under that name (the user's chat of 2026-11-01, after NET 3 was deleted with its helpers).
    ai.roles_for_missing_helpers(plan, missing, candidates, set(named) | set(preselect))
    ai.drop_used_helpers(hass, candidates, config_text, own | {e for ids in preselect.values() for e in ids})
    # [CHANGED v3.74.0] With the helpers the message names: a schedule the user names gives way to the alarm clock when
    # the days and the hours are set on the screen.
    ai.helpers_for_open_roles(plan, candidates, named)
    ai.dedupe_new_helpers(hass, plan, candidates, config_text)
    ai.roles_for_named_nets(hass, plan, request, msg["nets"], by_id, candidates, on_canvas)
    # [ADDED v3.60.0] Ticked at the start as well, after the loop above: a helper the user named is not "current".
    for rid, ids in named.items():
        preselect[rid] = preselect.get(rid, []) + [e for e in ids if e not in preselect.get(rid, [])]
    # [ADDED v3.82.0] The local variables in one place: each can be made new, and a free helper that fits comes first.
    ai.local_variables(hass, plan, candidates, preselect)
    # [ADDED v3.64.0] The phones a message goes to, by LIBI, the named ones ticked; without a notify entity to offer,
    # a phone role of the model's is optional and the services named are used as written.
    phones = ai.phones_role(hass, plan, services, candidates) if services or plan["missing_services"] else None
    if phones is None:
        ai.optional_message_roles(plan, services)
    elif phones:
        preselect[ai.PHONES_ROLE] = phones
    # [ADDED v3.83.0] Being at a place takes who and where; a message must have somewhere to go.
    ai.presence_roles(hass, plan, candidates)
    ai.message_phones(hass, plan, candidates)
    # [ADDED v3.80.0] LIBI's own questions, after every role is known: an on/off switch for the whole automation, what to
    # do when a device it switches is offline, a message when a battery runs low.
    ai.safety_questions(hass, plan, candidates, preselect, by_id.get(plan["target_net"], "") if plan["target_net"] else "",
                        config_text, own | {e for ids in preselect.values() for e in ids})
    connection.send_result(msg["id"], {"plan": plan, "candidates": candidates, "preselect": preselect})


@websocket_api.websocket_command({
    vol.Required("type"): "libi/ai_build",
    vol.Required("messages"): [dict],
    vol.Required("plan"): dict,
    vol.Required("selections"): dict,
    vol.Optional("answers", default={}): dict,
    vol.Optional("nets", default=[]): [dict],
    vol.Optional("share", default=False): bool,
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
    _canvas, by_id = ai.canvas_context(hass, msg["nets"])
    plan = ai.clean_plan(hass, msg["plan"], set(by_id))
    messages = ai.clean_messages(msg["messages"])
    # [ADDED v3.59.0] The same rule as for the plan, from the user's last message: the plan comes back from
    # the browser, so its intent is not taken on trust either.
    request = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    ai.only_named_changes(plan, request, msg["nets"])
    if plan["intent"] == "answer":
        connection.send_error(msg["id"], "invalid_format", "A question has nothing to build.")
        return
    answers = {str(k)[:40]: str(v)[:200] for k, v in msg["answers"].items()}
    # [ADDED v3.80.0] The on/off switch the user did not say yes to asks for no pick.
    ai.drop_declined(plan, answers)
    selections, problems = ai.clean_selections(hass, plan, msg["selections"])
    if problems:
        connection.send_result(msg["id"], {"ok": False, "errors": problems})
        return
    # [ADDED v3.75.0] A schedule that gave way to the alarm clock is not part of the logic, whatever the browser ticked:
    # the user's choice (2026-10-31) is that it is no longer used, and ticked it started the user's NET 3 in place of
    # the time set on the card.
    for role in plan["roles"]:
        if role.get("replaced"):
            selections.pop(role["id"], None)
    # [ADDED v3.54.0] An optional role nobody picked is not part of the logic.
    plan["roles"] = [r for r in plan["roles"]
                     if not r.get("replaced") and (r["id"] in selections or not r.get("optional"))]
    # [ADDED v3.75.0] The alarm clock the user picked: its time starts the logic (requirement_report checks it).
    alarm = ai.picked_alarm_clock(hass, plan, selections)
    # [ADDED v3.80.0] What the user answered to LIBI's own questions: the switch, the devices offline, the batteries -
    # which LIBI finds itself on the devices picked.
    # [ADDED v3.62.0] Which of the message services the user named exist, from the user's own words.
    services = ai.services_named(hass, [m["content"] for m in messages if m["role"] == "user"])
    # [CHANGED v3.81.0] With the phones the user named, for the messages of the answers.
    safety = ai.safety_answers(hass, plan, selections, answers, services[0])
    context = ai.build_context(plan, selections, answers, hass, by_id.get(plan["target_net"], ""), services, safety)
    if msg["share"]:
        # The candidates are found again here rather than taken back from the browser.
        on_canvas = ai.canvas_entities(hass, msg["nets"], by_id)
        # [CHANGED v3.80.0] A role LIBI filled itself lists only what LIBI put in it, not every battery of the house.
        candidates = {role["id"]: ai.filled_candidates(hass, selections.get(role["id"]) or []) if role.get("filled")
                      else ai.find_candidates(hass, role, on_canvas) for role in plan["roles"]}
        parts = [ai.candidates_context(hass, plan, candidates, selections), ai.helpers_context(hass)]
        context += "\n\n" + "\n\n".join(x for x in parts if x)
    messages.append({"role": "user", "content": context})
    # [ADDED v3.40.0] A change keeps the automation's id, so saving it updates that automation
    # instead of adding a second one next to it.
    target = next((n for n in msg["nets"] if isinstance(n, dict) and str(n.get("id")) == plan["target_net"]), None)
    # [CHANGED v3.62.0] An answer that does not hold - rejected by LIBI or by Home Assistant, not drawable, or
    # changed by the ladder - goes back to the model with what is wrong and how to fix it, up to MAX_BUILD_TRIES
    # answers in all (this replaces the one retry of v3.57.0). Every answer is checked the same way and the best
    # is returned: one slip of the model no longer ends the build, and nothing unchecked is ever offered.
    best, history = None, []
    for attempt in range(1, ai.MAX_BUILD_TRIES + 1):
        try:
            raw = await ai.async_llm_json(hass, settings, ai.BUILD_SYSTEM, messages, ai.BUILD_SCHEMA)
        except ai.AiError as err:
            if best is None:
                connection.send_error(msg["id"], "ai_error", str(err))
                return
            break
        draft = await ai.async_build_draft(hass, plan, selections, raw)
        if target and target.get("ha_id") and draft["level"] == "automation":
            draft["auto"]["id"] = str(target["ha_id"])
        drawn = _draw_draft(hass, draft)
        # [ADDED v3.73.0] And every line of the user's request, checked in the logic: a draft that misses one goes back.
        report = ai.requirement_report(plan, draft, drawn, raw, alarm, safety)
        problems = ai.draft_problems(draft, drawn) + ai.requirement_problems(report)
        history.append((attempt, problems))
        rank = ai.draft_rank(draft, drawn, problems)
        if best is None or rank <= best[4]:
            best = (draft, drawn, problems, attempt, rank, report)
        if not problems:
            break
        if attempt < ai.MAX_BUILD_TRIES:
            messages += ai.repair_request(raw, problems, selections)
    draft, drawn, problems, chosen, _rank, report = best
    result = {key: draft[key] for key in ("ok", "errors", "level", "yaml", "card_yaml",
                                           "sensitive", "reply", "notes")}
    # [ADDED v3.80.0] A yes to one of LIBI's questions that could not be kept, said: no battery on the devices picked.
    if safety["notes"]:
        result["notes"] = list(result["notes"]) + safety["notes"]
    # [ADDED v3.65.0] A branch the model kept inside another step, after every correction: the user is told.
    if draft["ok"] and ai.nested_branches(draft["auto"].get("actions")):
        result["notes"] = list(result["notes"]) + [
            "Part of this logic is an if or a choose inside another step, so the ladder shows it as one block "
            "instead of its elements."]
    # [ADDED v3.72.0] A wait the model kept after every correction: the rungs after it read what it waited for.
    if draft["ok"] and ai.waits_in(draft["auto"].get("actions")):
        result["notes"] = list(result["notes"]) + [
            "This logic waits inside a run, which a ladder does not do: the rungs after the wait read what it waited "
            "for. Ask again for it the ladder way - a trigger with an id for every event, and a choose."]
    # [ADDED v3.75.0] Two rungs of one trigger the model kept after every correction: Home Assistant runs only the first
    # of them that holds, which is not what the ladder shows - so the chat does not save the draft on its own.
    shared = ai.shared_options(draft["auto"].get("actions")) if draft["ok"] else []
    if shared:
        result["notes"] = list(result["notes"]) + [
            f"Two rungs start with the same trigger ({', '.join(tid for tid, _numbers in shared)}): Home Assistant runs "
            "only the first one that holds, so the second runs only when the first does not. Ask again for one rung "
            "per trigger."]
    result["shared_rungs"] = [tid for tid, _numbers in shared]
    result["intent"] = plan["intent"]
    result["target_net"] = plan["target_net"]
    # [ADDED v3.62.0] How many answers it took, and what the model corrected on the way to the one returned.
    result["tries"] = len(history)
    result["repaired"] = list(dict.fromkeys(p for n, found in history if n < chosen for p in found
                                            if p not in problems))[:10]
    if drawn.get("error"):
        result.update(ok=False, errors=[drawn["error"]])
    elif draft["ok"]:
        net = drawn["net"]
        net["level"] = draft["level"]
        net["name"] = draft["auto"]["alias"]
        net["source"] = "draft"
        net["source_note"] = "Drafted by the AI chat. Review it, then SAVE & COMPILE to write it."
        result["net"] = net
        result["round_trip"] = drawn["round_trip"]
        # [ADDED v3.73.0] The request line by line: what LIBI saw in the logic, and the rung that does each line.
        result["checklist"] = report
    connection.send_result(msg["id"], result)


def _draw_draft(hass: HomeAssistant, draft: dict) -> dict:
    """[ADDED v3.62.0] A draft that holds, drawn as a ladder net, and how well the ladder keeps it. Runs on the
    event loop: the importer reads Home Assistant's registries (CLAUDE.md RULE 13)."""
    if not draft["ok"]:
        return {}
    try:
        net = yaml_to_ast(hass, draft["auto"])
    except Exception as err:  # noqa: BLE001
        return {"error": f"The draft could not be drawn: {ai._sanitize(err)}"}
    report = verify_round_trip(hass, draft["auto"]) if draft["level"] == "automation" else {"ok": True}
    return {"net": net, "round_trip": {"ok": bool(report.get("ok")), "issues": report.get("issues", [])[:10]}}
