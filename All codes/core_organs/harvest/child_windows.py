"""
harvest.child_windows -- controls that OPEN A CHILD WINDOW are a section of their own.

A button like OBS Studio's '+' under Sources does not change the screen, it opens another window (a menu, a dialog, a properties window) with its own controls, its own buttons to dismiss it and, often, further
controls that open still deeper windows. A scan that only reads the main window never learns that. The recorder calls `snapshot` before it operates a control and `new_windows` after: any visible top-level window
of the same process that was not there before is the control's child. `describe` reads that window's own control tree (a capped UIA walk) and `dismiss` closes it again by the safest means (its Cancel / Close
button, then Escape, then WM_CLOSE: never OK / Create / Save). `register` writes what was learned to the RAG so the agent knows, BEFORE it clicks, that this control leads to a deep section it has to handle:

  Sub-RAG 3  a procedure 'Open the <child> window from <opener>' with the child's controls and how to leave it, tagged DEEP SECTION
  Sub-RAG 2  a graph transition (the opener's screen -> the child window's state) so localisation knows the child window is a state
  lexicon    the opener as a command
  file       <harvest root>/ui_sections/<app>.json, readable by people and by other agents
Nothing here knows an application.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

POPUP_HINTS = ("popup", "menu", "#32768", "flyout", "tooltip")
_CHROME = re.compile(r"^(minimi[sz]e|maximi[sz]e|restore|system|close)$", re.I)
SAFE_DISMISS = ("cancel", "close", "no", "not now", "dismiss", "later")
NEVER = ("ok", "yes", "create", "save", "apply", "delete", "remove", "install", "accept", "agree", "continue", "finish", "start", "connect", "sign in", "log in")
TYPES = ("ButtonControl", "MenuItemControl", "TabItemControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "EditControl", "ListItemControl", "SplitButtonControl", "HyperlinkControl")


def snapshot(app_hwnd: int) -> Dict[int, Dict[str, Any]]:
    """Every visible, uncloaked top-level window of the app's process other than the main one."""
    from core_organs import headless_input as hin
    out: Dict[int, Dict[str, Any]] = {}
    for w in hin.process_windows(app_hwnd, include_hidden=False):
        if w == app_hwnd or hin.is_cloaked(w):
            continue
        out[w] = {"class": hin._class_name(w), "title": hin.safe_window_text(w)}
    return out


def new_windows(before: Dict[int, Dict[str, Any]], app_hwnd: int) -> List[Dict[str, Any]]:
    now = snapshot(app_hwnd)
    out = []
    for h, info in now.items():
        if h in before:
            continue
        cls = info["class"].lower()
        kind = "menu" if any(k in cls for k in POPUP_HINTS) else ("dialog" if ("#32770" in cls or info["title"]) else "window")
        out.append({"hwnd": h, "class": info["class"], "title": info["title"], "kind": kind})
    return out


_DESCRIBED: Dict[Any, Dict[str, Any]] = {}


def describe(hwnd: int, max_nodes: int = 200, budget_s: float = 2.5, hard_s: float = 5.0) -> Dict[str, Any]:
    """`_describe` on its own thread with a HARD limit (MEASURED on OBS: a single UIA call into a Qt window can block for ~20 s and the node/clock checks between calls cannot help), and remembered per window
    class + title: the same dialog opened again is not read again."""
    import threading
    from core_organs import headless_input as hin
    key = (hin._class_name(hwnd), hin.safe_window_text(hwnd))
    if key in _DESCRIBED and key[1].strip().lower() not in ("", "pop-uphost", "pop-up", "popup"):
        return dict(_DESCRIBED[key], cached=True)
    box: Dict[str, Any] = {}
    th = threading.Thread(target=lambda: box.update(_describe(hwnd, max_nodes, budget_s)), daemon=True)
    th.start()
    th.join(hard_s)
    if th.is_alive():
        return {"controls": [], "n_controls": 0, "dismiss_with": "", "confirm_buttons": [], "nodes_read": 0, "timed_out": True}
    _DESCRIBED[key] = dict(box)
    return box


def _describe(hwnd: int, max_nodes: int = 200, budget_s: float = 2.5) -> Dict[str, Any]:
    """The child window's own controls (names + types), the buttons that leave it, and the controls that look like openers themselves. Bounded by node count AND wall clock (MEASURED: an uncapped walk
    of a Qt window cost ~8 s per child window and was 25% of a heavy app's scan)."""
    import uiautomation as auto
    controls: List[Dict[str, str]] = []
    n = 0
    t_end = time.time() + budget_s
    with contextlib.suppress(Exception), auto.UIAutomationInitializerInThread():
        for c, _d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=8):
            n += 1
            if n > max_nodes or time.time() > t_end:
                break
            with contextlib.suppress(Exception):
                if c.ControlTypeName in TYPES and (c.Name or "").strip():
                    controls.append({"name": c.Name.strip()[:60], "type": c.ControlTypeName.replace("Control", "")})
    names = [c["name"].lower() for c in controls]
    dismiss = next((nm for nm in SAFE_DISMISS if nm in names), "")
    controls = [c for c in controls if not _CHROME.match(c["name"])]            # the title bar's own buttons are not the window's controls
    confirm = [c["name"] for c in controls if c["name"].lower() in NEVER]
    seen, uniq = set(), []
    for c in controls:
        if (c["name"], c["type"]) not in seen:
            seen.add((c["name"], c["type"]))
            uniq.append(c)
    return {"controls": uniq[:60], "n_controls": len(uniq), "dismiss_with": dismiss, "confirm_buttons": confirm[:6], "nodes_read": n}


def dismiss(hwnd: int, app: Any = None) -> str:
    """Close a child window without confirming anything. Returns how."""
    import ctypes
    import uiautomation as auto
    from core_organs import headless_input as hin
    if not hin.is_alive(hwnd):
        return "already closed"

    def gone() -> bool:
        return not hin.is_alive(hwnd) or not ctypes.windll.user32.IsWindowVisible(hwnd)
    with contextlib.suppress(Exception):                                          # Escape first: one posted key, no UIA walk, never confirms anything
        hin.post_key_combo(hwnd, "esc")
        t_end = time.time() + 0.7
        while time.time() < t_end:
            if gone():
                return "escape"
            time.sleep(0.1)
    with contextlib.suppress(Exception):
        t_end = time.time() + 2.0
        n = 0
        for c, _d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=8):
            n += 1
            if n > 200 or time.time() > t_end:
                break
            if c.ControlTypeName == "ButtonControl" and (c.Name or "").strip().lower() in SAFE_DISMISS:
                pat = c.GetInvokePattern()
                if pat is not None:
                    pat.Invoke()
                    time.sleep(0.5)
                    if gone():
                        return f"pressed {c.Name}"
                    break
    with contextlib.suppress(Exception):
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)                  # WM_CLOSE: the window is a child of an owned instance
        time.sleep(0.8)
        return "wm_close"
    return "could not close"


def entry(opener: Dict[str, Any], kid: Dict[str, Any], detail: Dict[str, Any], closed_by: str) -> Dict[str, Any]:
    return {"opener": opener["name"], "opener_type": str(opener.get("type", "")).replace("Control", ""), "child_title": kid["title"] or "(untitled)", "child_kind": kid["kind"], "child_class": kid["class"],
            "controls": detail["controls"], "n_controls": detail["n_controls"], "dismiss_with": detail["dismiss_with"], "confirm_buttons": detail["confirm_buttons"], "closed_by": closed_by}


def register(rag: Any, app_key: str, entries: List[Dict[str, Any]], root: str = "") -> Dict[str, int]:
    """Write the deep sections to the RAG (procedures, graph, lexicon) and to <root>/ui_sections/<app>.json."""
    n = {"procedures": 0, "edges": 0, "commands": 0, "file": 0}
    if not entries:
        return n
    if root:
        with contextlib.suppress(Exception):
            d = os.path.join(root, "ui_sections")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"{app_key}.json")
            prev = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {"app": app_key, "deep_sections": []}
            have = {(e["opener"], e["child_title"]) for e in prev["deep_sections"]}
            prev["deep_sections"] += [e for e in entries if (e["opener"], e["child_title"]) not in have]
            json.dump(prev, open(p, "w", encoding="utf-8"), indent=1)
            n["file"] = 1
    if rag is None:
        return n
    from core_organs.rag import Outcome, PlanStep
    from core_organs.rag.lexicon import command_id
    for e in entries:
        label = f"{e['opener']} ({e['child_kind']} '{e['child_title']}')"
        with contextlib.suppress(Exception):
            ctl_names = ", ".join(c["name"] for c in e["controls"][:18])
            leave = f"leave it with '{e['dismiss_with']}'" if e["dismiss_with"] else "leave it with Escape"
            warn = f" Buttons that CONFIRM or CREATE ({', '.join(e['confirm_buttons'])}) change the app's state: do not press them unless the task asks." if e["confirm_buttons"] else ""
            deep = "DEEP SECTION: it opens " if e["child_kind"] != "menu" else "It opens "
            steps = [{"text": f"Click '{e['opener']}' (a {e['opener_type'].lower() or 'control'}). {deep}a {e['child_kind']} titled '{e['child_title']}' that must be handled before continuing.", "target": e["opener"], "route_hint": "uia_invoke"},
                     {"text": f"The {e['child_kind']} lists: {ctl_names or '(no named controls read)'}.", "route_hint": "observe"},
                     {"text": f"Do what the task needs inside it, then {leave}.{warn}", "route_hint": "uia_invoke"}]
            r = rag.proc.ingest_procedure(app_key, f"Open the '{e['child_title']}' window from '{e['opener']}' (deep section)", steps, "local_recorder:child_window", trust="learned")
            n["procedures"] += r.inserted + r.updated
        with contextlib.suppress(Exception):
            rag.lex.add_command(app_key, e["opener"], source="executor", trust="learned")
            n["commands"] += 1
        with contextlib.suppress(Exception):
            from core_organs.artist_memory import uia_snapshot
            child_snap = uia_snapshot([{"name": c["name"], "type": c["type"] + "Control"} for c in e["controls"]] + [{"name": f"[window] {e['child_title']}", "type": "WindowControl"}])
            src = rag.localize(app_key, {"nodes": [{"name": e["opener"], "ctype": "button", "offscreen": False}], "role": "main"}).state_id
            cid = command_id(app_key, e["opener"])
            rag.observe(Outcome(f"childwin-{int(time.time())}", app_key, PlanStep(cid, "uia_invoke", {"label": e["opener"], "kind": "opens_child_window"}, None, "", 0.6, "allow"), src_state=src,
                                observed_snapshot=child_snap, ok=True, effect=f"opens a {e['child_kind']} '{e['child_title']}'" + (" (deep section)" if e["child_kind"] != "menu" else ""), latency_ms=0.0, failure_code=""))
            n["edges"] += 1
    return n


def _find_item(hwnd: int, name: str, max_nodes: int = 500) -> Any:
    import uiautomation as auto
    n = 0
    with contextlib.suppress(Exception):
        for c, _d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=10):
            n += 1
            if n > max_nodes:
                break
            with contextlib.suppress(Exception):
                if (c.Name or "").strip() == name and c.ControlTypeName in TYPES:
                    return c
    return None


def probe_items(app: Any, opener_ctl: Any, opener_name: str, kid: Dict[str, Any], detail: Dict[str, Any], unsafe: Any, max_items: int = 8, settle: float = 1.0) -> List[Dict[str, Any]]:
    """ONE LEVEL DEEPER: a control that opens a menu / list (OBS's '+' under Sources) usually has items that open dialogs themselves. Each safe item is operated, the window it opens is read and closed
    (Cancel / Close / Escape -- never OK / Create), and the menu is opened again for the next item. Returns the entries found; `opener` reads 'Sources + > Image'."""
    from core_organs import headless_input as hin
    found: List[Dict[str, Any]] = []
    items = [it for it in detail.get("controls", []) if it["type"] in ("MenuItem", "ListItem", "Button", "SplitButton", "Hyperlink") and not unsafe(it["name"])][:max_items]
    cur = kid
    for it in items:
        if not hin.is_alive(cur["hwnd"]):                                   # the previous item closed the menu: open it again
            before0 = snapshot(app.hwnd)
            app.act(opener_ctl)
            time.sleep(settle)
            again = new_windows(before0, app.hwnd)
            if not again:
                break
            cur = again[0]
        ctl = _find_item(cur["hwnd"], it["name"])
        if ctl is None:
            continue
        before = snapshot(app.hwnd)
        if not app.act(ctl):
            continue
        time.sleep(settle)
        for sub in new_windows(before, app.hwnd):
            d = describe(sub["hwnd"])
            if d["n_controls"] == 0 and (sub["title"].strip().lower() in ("", "pop-uphost", "pop-up", "popup") or sub["kind"] != "dialog"):
                continue                                                      # an empty popup host is not a window with content
            closed = dismiss(sub["hwnd"], app) if sub["kind"] != "menu" else "menu"
            found.append(entry({"name": f"{opener_name} > {it['name']}", "type": it["type"] + "Control"}, sub, d, closed))
        with contextlib.suppress(Exception):
            hin.post_key_combo(app.hwnd, "esc")
        time.sleep(0.4)
    with contextlib.suppress(Exception):
        if hin.is_alive(cur["hwnd"]):
            dismiss(cur["hwnd"], app)
    return found
