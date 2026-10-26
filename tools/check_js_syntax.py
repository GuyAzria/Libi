#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Home Organizer for Home Assistant
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
#
# [MODIFIED v2026.10.11 | 2026-10-11] Purpose: a bare run checks the panel,
#   it does not check nothing.
#
#   With no arguments this looped over an empty sys.argv[1:], printed
#   nothing and exited 0. That exit was reported as "24/24 parse" for an
#   entire working session while no file was read at all - and a
#   view-recipes.js that the browser refused ("missing ) after argument
#   list", two string literals side by side) reached a user's panel and
#   took the whole panel down with it.
#
#   A check that can succeed by doing nothing is worse than no check,
#   because it is believed. With no arguments it now checks every .js
#   file the integration ships - the same selection ha_full_check uses -
#   and it always says how many it read, so a run that read none is
#   visible as one.
# [ADDED v2026.9.22 | 2026-09-22] Purpose: A real syntax check for the panel's
#   ES modules, for machines with no node.
#
# WHY THIS EXISTS - read before replacing it with something simpler.
#
# A single syntax error in any of these modules is a WHITE SCREEN: the browser
# refuses the module and the panel never renders. It has happened, and the
# cause was one backtick typed inside a CSS comment - a comment that lives
# inside a JavaScript template literal, where a backtick is not a character
# but the end of the string.
#
# Structural checks do not find that. The stray backticks came as a PAIR on
# one line, so braces, quotes and templates all still balanced perfectly; the
# file was simply parsed as a different program. Only a parser sees it.
#
# esprima is not an option: it is ES2017 and this panel uses optional
# chaining, so it rejects code that is perfectly valid. tree-sitter parses
# modern JavaScript and marks what it cannot read as an ERROR node.
#
# Usage:  python tools/check_js_syntax.py [<file> ...]
#         With no files, every .js under custom_components/ except the
#         vendored barcode-detector.umd.js.
#         exit 0 when every file parses, 1 otherwise, 2 if there was
#         nothing to check.

import sys, io
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_javascript

PARSER = Parser(Language(tree_sitter_javascript.language()))

def errors(path):
    src = io.open(path, "rb").read()
    tree = PARSER.parse(src)
    found = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            line = node.start_point[0] + 1
            text = src[node.start_byte:node.start_byte + 60].decode("utf-8", "replace")
            found.append((line, node.type, text.replace("\n", " ").strip()))
        else:
            stack.extend(node.children)
    return sorted(found)

def default_files():
    """Every .js the integration ships - what a bare run is asked for."""
    root = Path(__file__).resolve().parent.parent / "custom_components"
    return sorted(str(p) for p in root.rglob("*.js")
                  if p.name != "barcode-detector.umd.js")


if __name__ == "__main__":
    bad = 0
    files = sys.argv[1:] or default_files()
    if not files:
        # Nothing found is a failure, never a pass: a check that succeeds
        # by reading nothing is the bug this function exists to prevent.
        print("  FAIL no JavaScript files found to check")
        sys.exit(2)
    for p in files:
        errs = errors(p)
        name = p.replace("\\", "/").split("/")[-1]
        if errs:
            bad += 1
            for line, kind, text in errs[:3]:
                print("  FAIL %-26s line %-5d %s: %s" % (name, line, kind, text[:60]))
        else:
            print("  ok   %-26s parses" % name)
    print("  %d file(s) checked, %d failed" % (len(files), bad))
    sys.exit(1 if bad else 0)
