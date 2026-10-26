#!/usr/bin/env python3
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
"""Run the panel's behavioural tests in a real headless browser.

[ADDED v1.0.0 | 2026-10-26] Purpose: Frontend behaviour a syntax check cannot reach (CLAUDE.md
RULE 3a). Each tests/frontend/test_*.html loads the real module, runs it against canned websocket
answers, and writes {"passed": n, "failed": [...]} into <pre id="out">. Chrome or Edge runs it with
--dump-dom; no Node is needed.

Usage: python tools/run_frontend_tests.py   (exit 0 when every page passes, 1 otherwise, 2 when no
browser or no test page was found - never a silent pass)
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = [
    "chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def browser():
    for c in CANDIDATES:
        found = shutil.which(c) or (c if os.path.isfile(c) else None)
        if found:
            return found
    return None


def run(exe, page):
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-sandbox",
             "--allow-file-access-from-files", f"--user-data-dir={profile}",
             "--virtual-time-budget=10000", "--dump-dom", page.as_uri()],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
    m = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    if not m:
        return None, (proc.stderr or proc.stdout)[-800:]
    try:
        return json.loads(html.unescape(m.group(1))), ""
    except ValueError:
        return None, html.unescape(m.group(1))[:800]


def main():
    exe = browser()
    pages = sorted((ROOT / "tests" / "frontend").glob("test_*.html"))
    if not exe or not pages:
        print("  FAIL no browser found" if not exe else "  FAIL no test pages found")
        return 2
    bad = 0
    for page in pages:
        result, err = run(exe, page)
        if result is None:
            bad += 1
            print(f"  FAIL {page.name}: no result ({err.strip()})")
            continue
        for f in result["failed"]:
            print(f"  FAIL {page.name}: {f['name']} {f.get('detail', '')}")
        bad += bool(result["failed"])
        print(f"  {'ok  ' if not result['failed'] else 'FAIL'} {page.name}: {result['passed']} passed, "
              f"{len(result['failed'])} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
