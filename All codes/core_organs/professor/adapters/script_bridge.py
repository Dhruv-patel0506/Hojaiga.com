"""
professor.adapters.script_bridge -- AN APPLICATION'S OWN SCRIPTING ENGINE AS A ROUTE: commands, gestures and its whole command registry without a pointer.

Some applications embed a scripting language and accept a start-up script on their command line (detected from the program's OWN --help text, never from its name). Started with a
tiny bridge script, the application answers on a localhost socket (127.0.0.1, a random port, a one-time token): the Professor sends a short request, the application runs it on its
own main thread and replies. Through that route:
  registry()          every command the application declares (its label, description, where it lives) -> catalog verbs (source 'script-registry', aid 'script:<id>')
  execute(aid)        a catalogued command, run by the application itself (the reroute when the UI cannot be reached)
  gesture(kind)       what a pointer gesture is FOR, done by the application's own view / edit functions: orbit, pan, zoom the 3D view
Family 'python-startup' (an embedded Python with a --python start-up flag): the bridge uses that Python's own operator registry and view functions. A family is recognised by its
help text; adding another family is a new bridge text, not per-application logic. Input only to the run's OWNED instance (the effector is asked first by the executor).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

BRIDGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pybridge_startup.py")      # runs INSIDE the application; read as text, never imported


def _help(exe: str) -> str:
    try:
        return subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=40, creationflags=0x08000000).stdout or ""
    except Exception:
        return ""


def scripting_exe(exe: str) -> Tuple[str, str]:
    """(family, the program to start) when the program - or, for a launcher stub, the program beside it that it starts ('x-launcher.exe' -> 'x.exe') - offers a start-up
    Python script flag in its OWN --help text. ('', '') otherwise. Runs '<exe> --help' (a few seconds, no window)."""
    if not exe or not os.path.isfile(exe):
        return "", ""
    cands = [exe]
    base, ext = os.path.splitext(os.path.basename(exe))
    stripped = re.sub(r"(?i)[-_ ]?launcher$", "", base)
    if stripped != base:
        sib = os.path.join(os.path.dirname(exe), stripped + ext)
        if os.path.isfile(sib):
            cands.insert(0, sib)
    for c in cands:
        out = _help(c)
        if re.search(r"--python\b", out) and re.search(r"--python-expr\b|--python-text\b", out):
            return "python-startup", c
    return "", ""


def capability(exe: str) -> str:
    return scripting_exe(exe)[0]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ScriptBridge:
    name = "script-bridge"

    def __init__(self, port: int, token: str, script_path: str):
        self.port, self.token, self.script_path = port, token, script_path
        self.calls: List[Dict[str, Any]] = []
        self.sandbox = ""
        self.panel_errors: List[str] = []
        self.last_changed: Optional[bool] = None

    @staticmethod
    def prepare(folder: str, family: str = "python-startup", sandbox: str = "") -> Tuple["ScriptBridge", List[str]]:
        """Write the bridge into the run's sandbox folder; return (bridge, the extra command-line arguments the application is started with). `sandbox` is the only folder the application may be
        told to read from or write to through this bridge (file commands, saved copies): the bridge itself refuses any other path."""
        port, token = free_port(), secrets.token_hex(16)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "hojaiga_bridge.py")
        with open(BRIDGE_FILE, encoding="utf-8") as fh:
            src = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src.replace("__PORT__", str(port)).replace("__TOKEN__", token).replace("__SANDBOX__", (sandbox or "").replace('"', "")))
        br = ScriptBridge(port, token, path)
        br.sandbox = sandbox or ""
        return br, ["--python", path]

    def request(self, what: str, timeout: float = 20.0, **kw: Any) -> Dict[str, Any]:
        msg = json.dumps({"token": self.token, "what": what, **kw}).encode("utf-8")
        end = time.time() + timeout
        last = ""
        while time.time() < end:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=5.0) as s:
                    s.sendall(msg)
                    s.shutdown(socket.SHUT_WR)
                    buf = b""
                    while True:
                        chunk = s.recv(1 << 16)
                        if not chunk:
                            break
                        buf += chunk
                return json.loads(buf.decode("utf-8") or "{}")
            except (ConnectionRefusedError, socket.timeout, OSError) as exc:
                last = type(exc).__name__
                time.sleep(0.5)
        return {"ok": False, "error": f"the application's bridge did not answer ({last})"}

    def alive(self) -> bool:
        return bool(self.request("ping", timeout=8.0).get("ok"))

    def registry(self) -> List[Dict[str, Any]]:
        r = self.request("registry", timeout=60.0)
        return r.get("items", []) if r.get("ok") else []

    def gesture(self, kind: str, why: str = "") -> Tuple[bool, str]:
        before = self.request("state", timeout=8.0)
        r = self.request("gesture", kind=kind)
        after = self.request("state", timeout=8.0)
        self.calls.append({"gesture": kind, "res": r})
        if not r.get("ok"):
            return False, f"scripting: {r.get('note') or r.get('error')}"
        changed = before.get("view") != after.get("view")
        return changed, f"scripting: {r.get('note')} (view {'changed' if changed else 'did NOT change'})"

    def digest(self) -> Optional[str]:
        """The application's own account of what a pointer gesture can change (view, selection, mode, object positions), as one comparable string; None when it cannot answer."""
        r = self.request("state", timeout=8.0)
        if not r.get("ok"):
            return None
        return json.dumps({k: r.get(k) for k in ("view", "pan", "selected", "active", "mode", "locations")}, sort_keys=True)

    def execute(self, script_id: str, props: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """Run a catalogued command ('script:<id>' without the prefix) or set a property ('rna:<key>' with the value in props['value']); the bridge says when the state forbids it."""
        if script_id.startswith("rna:"):
            return self.rna_set(script_id[4:], (props or {}).get("value"))
        r = self.request("execute", id=script_id, props=props or {})
        self.calls.append({"execute": script_id, "props": props, "res": r})
        if r.get("refused"):
            return False, str(r.get("note"))                                           # begins with 'refused:' - the executor treats it as a policy refusal, not a failed attempt
        if r.get("needs_path"):
            return False, f"scripting: {script_id} needs a file (called without one it opens the application's own file browser)"
        if r.get("precondition"):
            return False, f"scripting: {script_id} -> precondition not met: {r.get('note')}"
        note = r.get("note") or r.get("error")
        return bool(r.get("ok")) and "CANCELLED" not in str(note), f"scripting: {script_id} -> {note}"

    def select_object(self, kind: str) -> Tuple[bool, str]:
        """One of the document's own objects of that kind selected and active (all elements inside edit mode); 'needs_object: ...' when the document has none of that kind."""
        r = self.request("select_object", kind=kind, timeout=10.0)
        self.calls.append({"select_object": kind, "res": r})
        if r.get("needs_object"):
            return False, f"needs_object: {r.get('note')}"
        return bool(r.get("ok")), f"scripting: {r.get('note') or r.get('error')}"

    def key_resolve(self, chord: str) -> Dict[str, Any]:
        """Which command the application's ACTIVE keymaps bind to this chord in its current state (mode, editor): {id, props, keymap, kind: command | menu | interactive}; ok False when none."""
        r = self.request("key_resolve", chord=chord, timeout=10.0)
        self.calls.append({"key_resolve": chord, "res": r})
        return r

    def fileinfo(self, script_id: str) -> Dict[str, Any]:
        """Does the command take a file (so that, run without one, it would open the application's own file browser)? {path_props, exts, direction}."""
        r = self.request("fileinfo", id=script_id, timeout=10.0)
        return r if r.get("ok") else {"path_props": []}

    def execute_file(self, script_id: str, path: str) -> Tuple[bool, str]:
        """A file command with a path inside the run's sandbox (the bridge refuses anything else): the application's own file browser is never needed."""
        info = self.fileinfo(script_id)
        pp = info.get("path_props") or ["filepath"]
        key = "filepath" if "filepath" in pp else pp[0]
        return self.execute(script_id, {key: path})

    def save_copy(self, path: str) -> Tuple[bool, str]:
        """Write a copy of the current document into the sandbox (a fixture to open later without touching the document in the window)."""
        r = self.request("save_copy", path=path, timeout=30.0)
        return bool(r.get("ok")), str(r.get("note") or r.get("error"))

    def props(self) -> List[Dict[str, Any]]:
        """Every setting the application's panels draw, with where they are drawn (editor > tab > panel > section): a guide names settings, not commands."""
        r = self.request("panels", timeout=240.0)
        self.panel_errors = r.get("errors", [])
        return r.get("props", []) if r.get("ok") else []

    def polls(self, ids: List[str]) -> Dict[str, bool]:
        """Which of these commands can run in the application's current state."""
        out: Dict[str, bool] = {}
        for i in range(0, len(ids), 800):
            r = self.request("polls", ids=ids[i:i + 800], timeout=30.0)
            out.update(r.get("polls", {}) if r.get("ok") else {})
        return out

    def apply_setting(self, spec: str, value: str = "") -> Tuple[bool, str]:
        """Set a setting a guide names: spec = '<key>' or '<key>=<choice>' (one choice of a list), value = what the step says ('on', 'off', '1.5', 'English'; empty = flip a yes / no setting)."""
        key, _eq, choice = spec.partition("=")
        val: Any = choice if choice else value
        if val in ("", None):
            cur = self.request("rna_get", key=key, timeout=10.0)
            if not cur.get("ok"):
                return False, f"scripting: could not read the setting ({cur.get('error')})"
            if isinstance(cur.get("value"), bool):
                val = not cur["value"]
            else:
                return False, "scripting: the step names a setting but no value to give it"
        return self.rna_set(key, val)

    def scene(self) -> Dict[str, Any]:
        """The document's contents as measurements: objects, kinds, transforms, sizes, mesh counts, bounding boxes."""
        r = self.request("scene", timeout=15.0)
        return r if r.get("ok") else {"objects": [], "error": r.get("error")}

    def scene_restore(self, prior: Dict[str, Any]) -> Dict[str, Any]:
        """Roll the document back to an earlier scene() dump (extra objects removed, transforms and modifiers restored)."""
        return self.request("scene_restore", prior=prior, timeout=20.0)

    def batch_add(self, items: List[Dict[str, Any]], chunk: int = 120) -> Dict[str, Any]:
        """Many parts in a few requests (the application's own add commands, run back to back inside it): {made, failed, materials}."""
        made: List[str] = []
        failed: List[Any] = []
        mats = 0
        for i in range(0, len(items), chunk):
            r = self.request("batch_add", items=items[i:i + chunk], timeout=240.0)
            made += r.get("made", [])
            failed += r.get("failed", []) if r.get("ok") else [["batch", str(r.get("error"))]]
            mats += int(r.get("materials", 0))
        self.calls.append({"batch_add": len(items), "made": len(made), "failed": len(failed)})
        return {"made": made, "failed": failed, "materials": mats}

    def view_shot(self, path: str, hide: Optional[List[str]] = None, view: str = "iso", frame: Optional[List[str]] = None, only: Optional[List[str]] = None) -> bool:
        """A picture of the 3D view with the named collections hidden, seen from 'iso' / 'south' / 'top', framed on the named collections."""
        r = self.request("view_shot", path=path, hide=hide or [], view=view, frame=frame or [], only=only or [], timeout=60.0)
        self.calls.append({"view_shot": path, "res": r})
        return bool(r.get("ok"))

    def open_file(self, path: str) -> Tuple[bool, str]:
        """Open a document that lies inside the run's sandbox (the one door through which a saved document comes back; any other path is refused by the bridge)."""
        r = self.request("open_file", path=path, timeout=60.0)
        self.calls.append({"open_file": path, "res": r})
        return bool(r.get("ok")) and "FINISHED" in str(r.get("note")), str(r.get("note") or r.get("error"))

    def shot(self, path: str, names: Optional[List[str]] = None) -> bool:
        """The 3D view as a PNG in the sandbox, framed on the named objects when given."""
        r = self.request("shot", path=path, names=names or [], timeout=40.0)
        self.calls.append({"shot": path, "res": r})
        return bool(r.get("ok"))

    def paint(self, name: str, rgba: List[float], rename: str = "") -> str:
        """A colour (a material) for one mesh object and, optionally, a new name; returns the object's name afterwards ('' when it failed)."""
        r = self.request("paint", name=name, rgba=rgba, rename=rename, timeout=10.0)
        self.calls.append({"paint": name, "res": r})
        return str(r.get("name") or "") if r.get("ok") else ""

    def menus(self) -> Dict[str, Any]:
        r = self.request("menus", timeout=90.0)
        return r.get("menus", {}) if r.get("ok") else {}

    def keymap(self) -> Dict[str, Any]:
        r = self.request("keymap", timeout=60.0)
        return r.get("keys", {}) if r.get("ok") else {}

    def op_props(self, script_id: str) -> List[Dict[str, Any]]:
        """The settings a command takes (name, type, default, choices): what a plan may pass to it."""
        r = self.request("op_props", id=script_id, timeout=10.0)
        return r.get("props", []) if r.get("ok") else []

    def rna_set(self, key: str, value: Any) -> Tuple[bool, str]:
        r = self.request("rna_set", key=key, value=value, timeout=15.0)
        self.last_changed = r.get("changed") if r.get("ok") else None
        self.calls.append({"rna_set": key, "value": value, "res": r})
        return bool(r.get("ok")), f"scripting: set {r.get('note') or r.get('error')}"


def menu_verbs(menus: Dict[str, Dict[str, Any]], max_depth: int = 3) -> List[Any]:
    """The application's OWN menu structure (as its menus' draw() lists them) as catalog verbs with real paths: 'Edit > Preferences' -> script:screen.userpref_show.
    Top-level menus are the ones no other menu contains; submenus are followed to max_depth."""
    from ..harvest import Verb, verb_id
    from .. import safety
    from ..menus import PRIVATE_RX
    from ..privacy import looks_private
    contained = {it["id"] for m in menus.values() for it in m["items"] if it["kind"] == "menu"}
    roots = [k for k in menus if k not in contained]
    out: List[Any] = []
    seen = set()
    file_like = re.compile(r"[\\/]|\.[A-Za-z0-9]{2,5}$")

    def editor_of(key: str) -> List[str]:
        """'VIEW3D_MT_object' -> ['View3D']: a menu of one editor is filed under that editor, so the many 'Edit' / 'View' menus of different editors stay apart (the top bar's need no prefix)."""
        pre = key.split("_MT_")[0] if "_MT_" in key else ""
        return [] if (not pre or pre.upper() in ("TOPBAR", "INFO")) else [pre.replace("_", " ").title()]

    def walk(key: str, path: List[str], depth: int) -> None:
        m = menus.get(key)
        if m is None or depth > max_depth or PRIVATE_RX.search(key) or PRIVATE_RX.search(m.get("label", "")):
            return                                                    # recent files / history menus list the person's own files: never read
        for it in m["items"]:
            lab = re.sub(r"(\.\.\.|…)\s*$", "", (it.get("label") or "")).strip()
            if not lab or len(lab) > 80 or file_like.search(lab) or looks_private(lab) or PRIVATE_RX.search(lab) or re.fullmatch(r"[A-Z0-9]+_MT_\w+", lab):
                continue
            k = (tuple(path), lab.lower(), it["id"])
            if k in seen:
                continue
            seen.add(k)
            if it["kind"] == "op":
                out.append(Verb(verb_id(path, lab), lab, list(path), "", "", True, False, "opens a dialog" if (it.get("label") or "").rstrip().endswith(("...", "…")) else "", 0,
                                "script:" + it["id"], "menu_item", ["script-menus"], "app-registry", safety.classify(lab, " ".join(path))))
            else:
                out.append(Verb(verb_id(path, lab), lab, list(path), "", "", True, False, "opens a submenu", 0, "", "menu_item", ["script-menus"], "app-registry", "safe"))
                walk(it["id"], path + [lab], depth + 1)

    for r in roots:
        walk(r, editor_of(r) + [menus[r]["label"]], 1)
    return out


def prop_verbs(items: List[Dict[str, Any]], max_items: int = 60) -> List[Any]:
    """The application's own SETTINGS as catalog verbs, at the path its panels draw them ('Preferences > Interface > Translation' + 'Language'), aid 'script:rna:<key>'. A choice (enum) also
    gets one verb per choice under the setting's name, aid 'script:rna:<key>=<choice>'. Settings that name the person's files / identity are not listed."""
    from ..harvest import Verb, verb_id
    from .. import safety
    from ..privacy import looks_private
    out: List[Any] = []
    for it in items:
        if it.get("readonly") or it.get("type") not in ("BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"):
            continue
        label = re.sub(r"(\.\.\.|…)\s*$", "", (it.get("label") or it.get("ui_name") or "")).strip()
        path = [str(p).strip() for p in it.get("path", []) if str(p).strip()]
        if not label or len(label) > 80 or looks_private(label) or it.get("type") == "STRING" and re.search(r"path|dir|file|name|key|token|user|account|mail", label, re.I):
            continue
        base = f"script:rna:{it['key']}"
        role = {"BOOLEAN": "checkbox", "ENUM": "dropdown", "INT": "field", "FLOAT": "field", "STRING": "field"}[it["type"]]
        out.append(Verb(verb_id(path, label), label, list(path), "", it.get("desc", ""), True, False, "", 0, base, role, ["script-properties"], "app-registry", safety.classify(label, " ".join(path))))
        for ch in (it.get("items") or [])[:max_items]:
            cl = (ch.get("label") or "").strip()
            if cl and len(cl) <= 60 and not looks_private(cl):
                out.append(Verb(verb_id(path + [label], cl), cl, path + [label], "", "", True, False, "", 0, f"{base}={ch['id']}", "menu_item", ["script-properties"], "app-registry", "safe"))
    return out


def registry_verbs(items: List[Dict[str, Any]]) -> List[Any]:
    """The application's own command registry as catalog verbs: label = its UI name, path = ['Commands', <module>], aid = 'script:<id>'."""
    from ..harvest import Verb, verb_id
    from .. import safety
    out = []
    seen = set()
    for it in items:
        lab = (it.get("label") or "").strip()
        if not lab or len(lab) > 80:
            continue
        path = ["Commands", it.get("module", "")]
        key = (tuple(path), lab.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(Verb(verb_id(path, lab), lab, path, "", it.get("desc", ""), True, False, "", 0, "script:" + it["id"], "button", ["script-registry"], "app-registry",
                        safety.classify(lab, " ".join(path))))
    return out
