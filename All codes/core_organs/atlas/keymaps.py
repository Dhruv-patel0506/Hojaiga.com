"""
atlas.keymaps -- an application's SHIPPED input grammar, read from its own published keymap / shortcut files.

An application's keymap is the authoritative statement of how it wants to be driven: which key, mouse button, drag or wheel does what, in which
editor/context. This module reads the shapes keymaps commonly take (no per-app code; each parser recognises a FORMAT):

    python-tuples     ("view3d.rotate", {"type": 'MIDDLEMOUSE', "value": 'PRESS', "shift": True}, ...)      (operator keymaps)
    json-bindings     [{"key": "ctrl+shift+p", "command": "workbench.action.showCommands", "when": "..."}]    (editor keybindings)
    ini-bindings      action=Key lines under [Group] headers                                               (DJ / media apps)
    xml-bindings      <binding key="..." action="..."/> or <key>..</key><action>..</action>
    text-tables       'Ctrl+S | Save', 'Save: Ctrl+S', 'Ctrl+S    Save the file'                                (manuals, READMEs)

`extract(text, hint)` -> list of bindings {input, kind, action, context, source_format}; `gestures_of(bindings)` keeps the pointer ones
(drag / wheel / click with modifiers) so they can be compared with what the live gesture atlas MEASURED.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from . import common as C

MOUSE_NAMES = {"LEFTMOUSE": "left", "MIDDLEMOUSE": "middle", "RIGHTMOUSE": "right", "WHEELUPMOUSE": "wheel-up", "WHEELDOWNMOUSE": "wheel-down",
               "WHEELINMOUSE": "wheel-in", "WHEELOUTMOUSE": "wheel-out", "MOUSEMOVE": "mouse-move", "INBETWEEN_MOUSEMOVE": "mouse-move",
               "TRACKPADPAN": "trackpad-pan", "TRACKPADZOOM": "trackpad-zoom", "MOUSEROTATE": "trackpad-rotate", "BUTTON4MOUSE": "button4", "BUTTON5MOUSE": "button5"}
VALUE_WORDS = {"PRESS": "press", "RELEASE": "release", "CLICK": "click", "DOUBLE_CLICK": "double-click", "CLICK_DRAG": "drag", "NOTHING": "", "ANY": "any"}
CHORD_RX = re.compile(r"\b((?:(?:Ctrl|Control|Alt|Option|Shift|Cmd|Command|Meta|Win|Super)\s*[+\-]\s*)+(?:F\d{1,2}|[A-Za-z0-9]|Enter|Return|Esc(?:ape)?|Tab|Space|Del(?:ete)?|Backspace|Home|End|PgUp|PgDn|Page\s?Up|Page\s?Down|Up|Down|Left|Right|Insert|Plus|Minus|Comma|Period|Slash|Num\s?\w+|\[|\]|\\|;|'|,|\.|/|`|=|-))\b", re.I)
FKEY_RX = re.compile(r"\b(F(?:1[0-2]|[1-9]))\b")


def _norm_chord(s: str) -> str:
    parts = [p.strip() for p in re.split(r"\s*[+\-]\s*", s.strip()) if p.strip()]
    alias = {"control": "Ctrl", "ctrl": "Ctrl", "alt": "Alt", "option": "Alt", "shift": "Shift", "cmd": "Cmd", "command": "Cmd", "meta": "Meta", "win": "Win", "super": "Win"}
    out = [alias.get(p.lower(), p.upper() if len(p) == 1 else p.capitalize()) for p in parts]
    return "+".join(out)


# --------------------------------------------------------------------------------------------------
# parsers
# --------------------------------------------------------------------------------------------------

_PY_ITEM = re.compile(r"\(\s*[\"']([\w.]+)[\"']\s*,\s*\{([^{}]*)\}")
_KM_DEF = re.compile(r"^\s*def\s+km_(\w+)\s*\(", re.M)


def parse_python_tuples(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    defs = [(m.start(), m.group(1)) for m in _KM_DEF.finditer(text)]
    for m in _PY_ITEM.finditer(text):
        op, body = m.group(1), m.group(2)
        t = re.search(r"[\"']type[\"']\s*:\s*[\"'](\w+)[\"']", body)
        if not t:
            continue
        v = re.search(r"[\"']value[\"']\s*:\s*[\"'](\w+)[\"']", body)
        mods = [k for k in ("ctrl", "shift", "alt", "oskey") if re.search(rf"[\"']{k}[\"']\s*:\s*True", body)]
        if re.search(r"[\"']any[\"']\s*:\s*True", body):
            mods.append("any")
        ctx = ""
        for pos, name in defs:
            if pos < m.start():
                ctx = name
            else:
                break
        typ = t.group(1)
        val = (v.group(1) if v else "PRESS")
        mouse = typ in MOUSE_NAMES
        label_mods = "+".join(x.capitalize() if x != "oskey" else "Cmd" for x in mods)
        if mouse:
            base = f"{MOUSE_NAMES[typ]}-mouse"
            word = VALUE_WORDS.get(val, val.lower())
            inp = (label_mods + "+" if label_mods else "") + base + (f" {word}" if word else "")
        else:
            key = typ.replace("NUMPAD_", "Numpad ").replace("_", " ").title()
            inp = (label_mods + "+" if label_mods else "") + key + (f" ({VALUE_WORDS.get(val, val.lower())})" if val not in ("PRESS", "") else "")
        out.append({"input": inp, "kind": "mouse" if mouse else "key", "action": op, "context": ctx, "mods": mods, "button": MOUSE_NAMES.get(typ, ""), "value": val.lower(), "source_format": "python-tuples"})
    return out


def parse_json_bindings(text: str) -> List[Dict[str, Any]]:
    cleaned = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
    try:
        data = json.loads(cleaned)
    except Exception:
        data = None
    out: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        for k in ("keybindings", "bindings", "keymap", "shortcuts"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if isinstance(data, list):
        for it in data:
            if isinstance(it, dict) and (it.get("key") or it.get("keys")) and (it.get("command") or it.get("action")):
                key = it.get("key") or it.get("keys")
                if isinstance(key, list):
                    key = "+".join(map(str, key))
                out.append({"input": _norm_chord(str(key)), "kind": "key", "action": str(it.get("command") or it.get("action")), "context": str(it.get("when") or it.get("context") or ""),
                            "mods": [], "button": "", "value": "press", "source_format": "json-bindings"})
    return out


def parse_ini_bindings(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    group = ""
    for ln in text.splitlines()[:5000]:
        s = ln.strip()
        if not s or s.startswith((";", "#", "//")):
            continue
        if s.startswith("[") and s.endswith("]"):
            group = s[1:-1]
            continue
        m = re.match(r"^([A-Za-z_][\w.\-/ ]{1,60}?)\s*[=:]\s*([^=]{1,30})$", s)
        if not m:
            continue
        act, key = m.group(1).strip(), m.group(2).strip().strip("\"'")
        if re.fullmatch(r"(?:(?:Ctrl|Alt|Shift|Meta|Cmd|Num|Win)\s*[+\-]\s*)*(?:F\d{1,2}|[A-Za-z0-9]|Enter|Return|Esc|Escape|Tab|Space|Del|Delete|Backspace|Home|End|PgUp|PgDown|Up|Down|Left|Right|Insert|Plus|Minus|Comma|Period|Slash|\[|\]|;|'|,|\.|/|=|-|\w{1,10})", key, re.I) and len(key) <= 24:
            out.append({"input": _norm_chord(key), "kind": "key", "action": act, "context": group, "mods": [], "button": "", "value": "press", "source_format": "ini-bindings"})
    return out if len(out) >= 4 else []


def parse_xml_bindings(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in re.finditer(r"<\s*(?:binding|key|shortcut|keybinding)\b[^>]*?\b(?:key|keys|shortcut|sequence)\s*=\s*[\"']([^\"']+)[\"'][^>]*?\b(?:action|command|name)\s*=\s*[\"']([^\"']+)[\"']", text, re.I):
        out.append({"input": _norm_chord(m.group(1)), "kind": "key", "action": m.group(2), "context": "", "mods": [], "button": "", "value": "press", "source_format": "xml-bindings"})
    for m in re.finditer(r"<\s*(?:action|command)\s*>\s*([^<]+?)\s*<\s*/\s*(?:action|command)\s*>\s*<\s*(?:key|keys|shortcut)\s*>\s*([^<]+?)\s*<", text, re.I):
        out.append({"input": _norm_chord(m.group(2)), "kind": "key", "action": m.group(1), "context": "", "mods": [], "button": "", "value": "press", "source_format": "xml-bindings"})
    return out


def parse_text_tables(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in text.splitlines()[:6000]:
        if len(ln) > 260:
            continue
        m = CHORD_RX.search(ln) or None
        if not m:
            continue
        chord = _norm_chord(m.group(1))
        rest = (ln[:m.start()] + " " + ln[m.end():])
        rest = re.sub(r"[|`*_\[\]()]+", " ", rest)
        rest = re.sub(r"\s+", " ", rest).strip(" :-–—\t")
        if 3 <= len(rest) <= 90 and re.search(r"[A-Za-z]{3}", rest):
            out.append({"input": chord, "kind": "key", "action": rest, "context": "", "mods": [], "button": "", "value": "press", "source_format": "text-tables"})
    return out


def extract(text: str, hint: str = "") -> List[Dict[str, Any]]:
    """All bindings found, trying every format; duplicates (same input+action+context) removed."""
    cands: List[Dict[str, Any]] = []
    low = (hint or "").lower()
    if "_PY_ITEM" and (low.endswith(".py") or "type\"" in text[:200000]):
        cands += parse_python_tuples(text)
    if low.endswith((".json", ".jsonc")) or text.lstrip().startswith(("[", "{")):
        cands += parse_json_bindings(text)
    if low.endswith((".xml", ".kbd", ".keymap")) or "<" in text[:400]:
        cands += parse_xml_bindings(text)
    if low.endswith((".cfg", ".ini", ".conf", ".kbd", ".toml", ".txt")) or re.search(r"^\[[\w ]+\]\s*$", text[:2000], re.M):
        cands += parse_ini_bindings(text)
    if low.endswith((".md", ".rst", ".txt", ".html")) or not cands:
        cands += parse_text_tables(text)
    seen, out = set(), []
    for b in cands:
        k = (b["input"], b["action"], b["context"])
        if k in seen:
            continue
        seen.add(k)
        out.append(b)
    return out


def gestures_of(bindings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [b for b in bindings if b.get("kind") == "mouse" and b.get("button") not in ("mouse-move", "")]


def to_claims(app_key: str, bindings: List[Dict[str, Any]], url: str, *, max_claims: int = 160) -> List[C.Claim]:
    out: List[C.Claim] = []
    ev = lambda b: [C.Evidence("url", url, f"{b['input']} -> {b['action']}" + (f" [{b['context']}]" if b['context'] else ""))]
    pointer = gestures_of(bindings)
    for b in pointer[:max_claims // 2]:
        out.append(C.Claim(app_key, "gesture.shipped", f"{b['input']} -> {b['action']}" + (f" in {b['context']}" if b["context"] else ""), "published", 0.85, ev(b), b, "atlas.keymaps"))
    keys = [b for b in bindings if b.get("kind") == "key"]
    for b in keys[:max_claims - len(out)]:
        out.append(C.Claim(app_key, "ui.shortcut.published", f"{b['input']} -> {b['action']}" + (f" in {b['context']}" if b["context"] else ""), "published", 0.8, ev(b), b, "atlas.keymaps"))
    return out
