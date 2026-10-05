"""
preload_sources.py -- the command lists an app SHIPS (P2-J / backlog 3.5)

Some programs carry their own textbook: a keymap file, a plugin manifest, an operator registry in their Python scripts, a request
table inside the remote-control plugin they ship. Reading those is free knowledge about what the app can do, available before the
app ever runs. This module finds them by FORMAT (no app names) and turns them into command candidates that are

  * DEMOTED: stored with 'archetype' trust (hint-only; the loop may rank them for the judge but never executes them directly),
    opaque (no machine-checkable postcondition yet), with origin 'preload:<format>' so the dossier says where each came from;
  * PROMOTED only by evidence: `promote_if_probed` lifts a preloaded command to 'learned' when a live probe (a verified E0 menu read
    or an E1 effect) corresponds to it - never by being present in a file.

Formats read (all bounded in files, bytes and seconds):
  keymap          keybinding / shortcut files (existing parsers)                                   -> verb 'palette'/'key'
  manifest        extension-style package.json `contributes.commands`                              -> verb 'palette'
  operator-registry   Python scripts that register operators with `bl_idname = "group.name"` + `bl_label`  -> verb 'operator'
  protocol-json   JSON files that list requests: [{"requestType"/"command"/"name": ..., "description"/"comment": ...}] -> verb 'api'
  api-strings     a shipped plugin binary's string table of request names (>= 20 verb-prefixed CamelCase names, one cluster) -> verb 'api'
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

PRELOAD_CONF = 0.4

_VERBS = ("Get", "Set", "Create", "Remove", "Delete", "Start", "Stop", "Toggle", "Trigger", "Open", "Save", "Press", "Broadcast", "Call",
          "Duplicate", "Offset", "Sleep", "Pause", "Resume", "Restart", "Switch", "Send", "Reset", "Clear", "List", "Add", "Load", "Close",
          "Enable", "Disable", "Take", "Move", "Rename", "Select", "Apply")
_API_NAME = re.compile(r"\b(?:" + "|".join(_VERBS) + r")(?:[A-Z][a-z0-9]+){1,5}\b")
_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]+|[a-z0-9]+")
_OPERATOR = re.compile(r"""bl_idname\s*=\s*["']([A-Za-z0-9_]+\.[A-Za-z0-9_]+)["'](?:[^\n]*\n){0,6}?[^\n]*?bl_label\s*=\s*["']([^"'\n]+)["']""")
_OPERATOR_REV = re.compile(r"""bl_label\s*=\s*["']([^"'\n]+)["'](?:[^\n]*\n){0,6}?[^\n]*?bl_idname\s*=\s*["']([A-Za-z0-9_]+\.[A-Za-z0-9_]+)["']""")


def humanize(camel: str) -> str:
    """'StartRecord' -> 'Start Record'; 'object.mode_set' -> 'Object: Mode Set' (a label a person - or a UI - would use)."""
    if "." in camel and " " not in camel:
        grp, _, op = camel.partition(".")
        return f"{grp.title()}: " + " ".join(op.split("_")).title()
    return " ".join(w if w.isupper() and len(w) > 1 else w.capitalize() for w in _CAMEL.findall(camel))


def _text(path: str, limit: int = 1_500_000) -> str:
    try:
        if os.path.getsize(path) > limit:
            return ""
        return open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


# ----------------------------------------------------------------------------------------------------------------- the readers

def read_operator_registry(text: str) -> List[Dict[str, Any]]:
    """Python plugin scripts that register operators (bl_idname = 'group.name' with a bl_label next to it)."""
    out, seen = [], set()
    for rx, swap in ((_OPERATOR, False), (_OPERATOR_REV, True)):
        for m in rx.finditer(text):
            idn, label = (m.group(2), m.group(1)) if swap else (m.group(1), m.group(2))
            if idn in seen:
                continue
            seen.add(idn)
            out.append({"name": f"{label.strip()}", "goal": label.strip(), "verb": "operator", "command_id": idn, "opaque": True,
                        "origin_fmt": "operator-registry", "palette_title": humanize(idn)})
    return out


def read_protocol_json(text: str) -> List[Dict[str, Any]]:
    """A JSON document that LISTS requests/commands: any array of objects carrying a request-ish key and (optionally) a description."""
    try:
        obj = json.loads(text)
    except Exception:
        return []
    keys = ("requestType", "request", "command", "commandName", "method", "name", "id")
    found: List[Dict[str, Any]] = []

    def _walk(o: Any, depth: int = 0) -> None:
        if depth > 5 or len(found) > 4000:
            return
        if isinstance(o, list):
            dicts = [x for x in o if isinstance(x, dict)]
            if len(dicts) >= 5 and len(dicts) >= 0.8 * len(o):
                for d in dicts:
                    k = next((k for k in keys if isinstance(d.get(k), str) and 3 <= len(d[k]) <= 80), None)
                    if k:
                        desc = next((d[x] for x in ("description", "comment", "title", "help") if isinstance(d.get(x), str)), "")
                        found.append({"name": humanize(d[k]), "goal": humanize(d[k]), "verb": "api", "command_id": d[k], "opaque": True,
                                      "origin_fmt": "protocol-json", "evidence": desc[:140]})
            for x in o:
                _walk(x, depth + 1)
        elif isinstance(o, dict):
            for v in o.values():
                _walk(v, depth + 1)
    _walk(obj)
    return found


MAX_API_NAMES = 500


def read_api_strings(path: str, max_bytes: int = 24_000_000) -> List[Dict[str, Any]]:
    """Request names inside a shipped plugin binary: ASCII strings shaped Verb+CamelWords. Only a CLUSTER counts (>= 20 distinct names
    in one file), so one stray identifier is never read as an API."""
    try:
        if os.path.getsize(path) > max_bytes:
            return []
        data = open(path, "rb").read()
    except Exception:
        return []
    names: Dict[str, int] = {}
    from core_organs.pe_imports import imported_function_names
    imported = imported_function_names(data)                  # the OS calls this binary makes are not its own request vocabulary
    for m in re.finditer(rb"[A-Za-z0-9]{6,60}", data):
        s = m.group(0).decode("ascii", "ignore")
        if _API_NAME.fullmatch(s) and s not in imported and not s.endswith(("W", "A", "Ex", "ExW", "2")):
            names[s] = names.get(s, 0) + 1
    if len(names) < 20 or len(names) > MAX_API_NAMES:
        return []                         # thousands of Get/Set names is a program's INTERNAL class library (measured: 2,380 in a conferencing client), not a request API
    return [{"name": humanize(n), "goal": humanize(n), "verb": "api", "command_id": n, "opaque": True, "origin_fmt": "api-strings"}
            for n in sorted(names)]


# ----------------------------------------------------------------------------------------------------------------- the scan

_PY_SKIP = ("site-packages", "__pycache__", "node_modules", ".git", "locales", "locale", "assets", "icons", "datafiles")
_PROTO_FILE = re.compile(r"(protocol|requests?|commands?|api|schema|actions?)[\w.-]*\.json$", re.I)
_PLUGIN_BIN = re.compile(r"(plugin|websocket|remote|rpc|api|control)[\w.-]*\.(dll|so|dylib)$", re.I)


def scan(root: str, *, budget_s: float = 4.0, max_files: int = 600) -> Dict[str, Any]:
    """Walk an install directory (bounded) and return {'commands': [...], 'sources': [{path, format, found}], 'skipped': [...]}."""
    t0 = time.time()
    rep: Dict[str, Any] = {"commands": [], "sources": [], "skipped": []}
    if not root or not os.path.isdir(root):
        rep["skipped"].append("no-install-dir")
        return rep
    seen: set = set()
    n = 0

    def _add(path: str, fmt: str, items: List[Dict[str, Any]]) -> None:
        got = 0
        for c in items:
            ident = (c.get("command_id") or c["name"]).lower()
            if ident in seen:
                continue
            seen.add(ident)
            rep["commands"].append(dict(c, risk=c.get("risk")))
            got += 1
        if got:
            rep["sources"].append({"path": path, "format": fmt, "found": got})

    from core_organs import static_knowledge as sk
    from core_organs import organ_48_app_behavior_model as bm
    for dp, dn, fn in os.walk(root):
        if time.time() - t0 > budget_s:
            rep["skipped"].append("walk-budget")
            break
        depth = dp[len(root):].count(os.sep)
        dn[:] = [d for d in dn if d.lower() not in _PY_SKIP] if depth < 7 else []
        for f in fn:
            if n >= max_files:
                rep["skipped"].append("file-cap")
                break
            p = os.path.join(dp, f)
            low = f.lower()
            if low.endswith(".py") and os.path.getsize(p) < 600_000:
                n += 1
                items = read_operator_registry(_text(p))
                if items:
                    _add(p, "operator-registry", items)
            elif _PROTO_FILE.search(low):
                n += 1
                items = read_protocol_json(_text(p))
                if items:
                    _add(p, "protocol-json", items)
            elif low == "package.json":
                n += 1
                try:
                    items = sk.parse_manifest_contributes(json.loads(_text(p)))
                except Exception:
                    items = []
                if items:
                    _add(p, "manifest", [dict(i, origin_fmt="manifest-contributes") for i in items])
            elif re.match(r"^(keybindings?|keymaps?)[\w.-]*\.(json|jsonc|py|txt|ini|conf)$", low):
                n += 1
                items = bm.harvest_keymap_text(_text(p))
                if items:
                    _add(p, "keymap", items)
            elif _PLUGIN_BIN.search(low):
                n += 1
                items = read_api_strings(p)
                if items:
                    _add(p, "api-strings", items)
    rep["elapsed_s"] = round(time.time() - t0, 2)
    return rep


# ----------------------------------------------------------------------------------------------------------------- trust handling

def ingest_preload(model, app_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Store preloaded commands DEMOTED ('archetype' trust, opaque, low confidence, origin 'preload:<format>')."""
    from core_organs import organ_48_app_behavior_model as bm
    key = bm._app_key(app_name)
    n = 0
    for c in items:
        cc = {k: v for k, v in c.items() if k not in ("origin_fmt",)}
        if cc.get("risk") is None:
            cc.pop("risk", None)
        cc["opaque"] = True
        ev = f"shipped {c.get('origin_fmt', 'source')}" + (f"; id={c['command_id']}" if c.get("command_id") else "") + \
             (f"; {c['evidence']}" if c.get("evidence") else "")
        cid = model.upsert_command(key, cc, source="archetype", origin=f"preload:{c.get('origin_fmt', 'source')}", evidence=ev)
        model._conn.execute("UPDATE bm_commands SET confidence=? WHERE cmd_id=? AND source='archetype' AND successes=0", (PRELOAD_CONF, cid))
        n += 1
    model._conn.commit()
    return {"app_key": key, "preloaded": n}


def preload_for(model, app_name: str, root: str, **kw) -> Dict[str, Any]:
    rep = scan(root, **kw)
    out = ingest_preload(model, app_name, rep["commands"])
    out.update({"sources": rep["sources"], "skipped": rep["skipped"], "elapsed_s": rep.get("elapsed_s")})
    return out


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def promote_if_probed(model, app_name: str, observed_labels: List[str], *, evidence: str) -> List[str]:
    """A preloaded command is lifted to 'learned' ONLY when a live, verified observation matches it (the same canonical words as a
    control or menu entry the probe actually saw, with its postcondition proven). Presence in a shipped file never promotes."""
    from core_organs import organ_48_app_behavior_model as bm
    key = bm._app_key(app_name)
    want = {_canon(x) for x in observed_labels if x}
    promoted: List[str] = []
    for r in model._conn.execute("SELECT cmd_id, name, origin, source FROM bm_commands WHERE app_key=? AND origin LIKE 'preload:%' AND source='archetype'", (key,)):
        if _canon(r["name"]) in want:
            model.command_outcome(r["cmd_id"], "PASS", evidence=f"{evidence}; matched a shipped preload entry", promote=True)
            promoted.append(r["name"])
    return promoted
