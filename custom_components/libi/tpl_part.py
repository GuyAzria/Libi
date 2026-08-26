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
# [ADDED v2.2.0 | 2026-08-17] Purpose: There is no TEMPLATE block any more.
#   A Jinja condition is an expression, and an expression is exactly what ladder logic draws:
#   or becomes parallel branches, and becomes a series, a comparison becomes a CMP block and the
#   arithmetic inside a comparison becomes a MATH block feeding it.
#   The original text still travels in raw, so an untouched condition compiles back to itself.
import re

# ---------------------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------------------

TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<num>\d+\.\d+|\d+)
  | (?P<op>==|!=|>=|<=|>|<|\+|-|\*|/|\(|\)|,|\|)
  | (?P<word>[A-Za-z_][A-Za-z_0-9\.]*)
""", re.VERBOSE)

KEYWORDS = {"and", "or", "not", "in", "is", "none", "true", "false", "if", "else"}
CMP_OPS = {"==": "cmp_eq", "!=": "cmp_ne", ">": "cmp_gt", "<": "cmp_lt", ">=": "cmp_ge", "<=": "cmp_le"}
MATH_OPS = {"+": "math_add", "-": "math_sub", "*": "math_mul", "/": "math_div"}


def tokenize(text):
    out = []
    i = 0
    while i < len(text):
        m = TOKEN_RE.match(text, i)
        if not m:
            return None
        i = m.end()
        if m.lastgroup == "ws":
            continue
        out.append((m.lastgroup, m.group()))
    return out


class _P:
    """Small recursive descent parser. Returns None whenever it meets something it does not know,
    which is the signal to keep the expression whole instead of guessing."""

    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, val):
        if self.peek()[1] == val:
            self.i += 1
            return True
        return False

    # or_expr := and_expr ('or' and_expr)*
    def parse_or(self):
        left = self.parse_and()
        if left is None:
            return None
        parts = [left]
        while self.peek()[1] == "or":
            self.take()
            nxt = self.parse_and()
            if nxt is None:
                return None
            parts.append(nxt)
        return parts[0] if len(parts) == 1 else {"kind": "or", "parts": parts}

    def parse_and(self):
        left = self.parse_not()
        if left is None:
            return None
        parts = [left]
        while self.peek()[1] == "and":
            self.take()
            nxt = self.parse_not()
            if nxt is None:
                return None
            parts.append(nxt)
        return parts[0] if len(parts) == 1 else {"kind": "and", "parts": parts}

    def parse_not(self):
        if self.peek()[1] == "not":
            self.take()
            inner = self.parse_not()
            return None if inner is None else {"kind": "not", "part": inner}
        return self.parse_cmp()

    # comparison := arith [ op arith ] , also handles "is none" and "is not none"
    def parse_cmp(self):
        left = self.parse_arith()
        if left is None:
            return None
        kind, val = self.peek()
        if val in CMP_OPS:
            self.take()
            right = self.parse_arith()
            if right is None:
                return None
            return {"kind": "cmp", "op": val, "left": left, "right": right}
        if val == "is":
            self.take()
            negate = False
            if self.peek()[1] == "not":
                self.take()
                negate = True
            right = self.parse_arith()
            if right is None:
                return None
            return {"kind": "cmp", "op": "!=" if negate else "==", "left": left, "right": right}
        return {"kind": "truth", "expr": left}

    def parse_arith(self):
        left = self.parse_term()
        if left is None:
            return None
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            right = self.parse_term()
            if right is None:
                return None
            left = {"kind": "math", "op": op, "left": left, "right": right,
                    "text": f"{text_of(left)} {op} {text_of(right)}"}
        return left

    def parse_term(self):
        left = self.parse_atom()
        if left is None:
            return None
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            right = self.parse_atom()
            if right is None:
                return None
            left = {"kind": "math", "op": op, "left": left, "right": right,
                    "text": f"{text_of(left)} {op} {text_of(right)}"}
        return left

    def parse_atom(self):
        kind, val = self.peek()
        if val == "(":
            self.take()
            inner = self.parse_or()
            if inner is None or not self.expect(")"):
                return None
            # A bracket around plain arithmetic is not a truth test, it is just grouping.
            if isinstance(inner, dict) and inner.get("kind") == "truth":
                inner = inner["expr"]
            node = dict(inner)
            node["text"] = f"({text_of(inner)})"
        elif kind == "str":
            self.take()
            node = {"kind": "lit", "value": val[1:-1], "text": val, "quoted": True}
        elif kind == "num":
            self.take()
            node = {"kind": "lit", "value": val, "text": val}
        elif kind == "word":
            self.take()
            if self.peek()[1] == "(":
                args, raw = self.parse_args()
                if args is None:
                    return None
                node = {"kind": "call", "name": val, "args": args, "text": f"{val}({raw})"}
            else:
                node = {"kind": "name", "value": val, "text": val}
        else:
            return None
        return self.parse_filters(node)

    def parse_args(self):
        if not self.expect("("):
            return None, ""
        args = []
        raw = []
        depth = 0
        if self.peek()[1] == ")":
            self.take()
            return args, ""
        while True:
            node = self.parse_or()
            if node is None:
                return None, ""
            if isinstance(node, dict) and node.get("kind") == "truth":
                node = node["expr"]
            args.append(node)
            raw.append(text_of(node))
            if self.expect(","):
                continue
            if self.expect(")"):
                break
            return None, ""
        return args, ", ".join(raw)

    def parse_filters(self, node):
        """A jinja filter does not change what is being compared, so it is remembered and dropped."""
        while self.peek()[1] == "|":
            self.take()
            kind, name = self.take()
            if kind != "word":
                return None
            suffix = f" | {name}"
            if self.peek()[1] == "(":
                args, raw = self.parse_args()
                if args is None:
                    return None
                suffix += f"({raw})"
            node = dict(node)
            node["text"] = node.get("text", "") + suffix
            node["filtered"] = True
        return node


def parse_template(text):
    body = str(text or "").strip()
    m = re.fullmatch(r"\{\{(.*)\}\}", body, re.DOTALL)
    if m:
        body = m.group(1).strip()
    elif "{%" in body or "{{" in body:
        return None  # statements and mixed text stay whole
    tokens = tokenize(body)
    if not tokens:
        return None
    p = _P(tokens)
    tree = p.parse_or()
    if tree is None or p.i != len(p.t):
        return None
    return tree


# ---------------------------------------------------------------------------------------
# Naming: what the operand is called on the canvas
# ---------------------------------------------------------------------------------------

def label_of(node):
    kind = node.get("kind")
    if kind == "lit":
        return str(node.get("value"))
    if kind == "name":
        val = node["value"]
        if val.startswith("this.attributes."):
            return "this." + val.split("this.attributes.", 1)[1]
        if val in ("none", "None"):
            return "none"
        return val
    if kind == "call":
        name = node["name"]
        args = node.get("args") or []
        if name == "states" and args:
            return label_of(args[0])
        if name in ("as_timestamp", "int", "float", "round") and args:
            return label_of(args[0])
        if name == "now" and not args:
            return "now"
        if name == "utcnow" and not args:
            return "utcnow"
        if name == "today_at" and args:
            return f"today {label_of(args[0])}"
        if name == "is_state" and len(args) >= 2:
            return f"{label_of(args[0])} = {label_of(args[1])}"
        if name == "state_attr" and len(args) >= 2:
            return f"{label_of(args[0])}.{label_of(args[1])}"
        return f"{name}({', '.join(label_of(a) for a in args)})"
    if kind == "math":
        return f"{label_of(node['left'])} {node['op']} {label_of(node['right'])}"
    if kind == "truth":
        return label_of(node["expr"])
    return node.get("text", "?")


def text_of(node):
    """The original expression text, used when compiling back."""
    return node.get("text") or label_of(node)