"""
live_tutor -- the interactive, visible product flow on top of app_teaching_automation:

    scan (visible, streamed)  ->  ask the person  ->  live on-screen tutorial  ->  questions / take over and automate

    s = TutorSession()
    s.start("Notepad")                 # opens the real app on screen and scans it, step by step (events stream to whoever listens)
    s.chat("yes, teach me the app")    # a spotlight + callout card + optional voice walk through every section on the real window
    s.chat("where is Find?")           # the control is found on the live window, spotlighted, and described
    s.chat("type hello for me")        # delegate: the same engine does the job on the same window

Everything shown comes from the live window (UI Automation: names, help text, accelerator keys, menus read by opening them) and from what the RAG already holds (shortcuts, learned procedures). Nothing is written
by hand per application. Menus are only OPENED to be read (never an item invoked); a control whose name is unsafe (save / delete / send / exit ...) is described, never operated.

Events (dicts with `id`, `t`, `kind`, ...) go to a list the frontend follows: status, progress, counters, curriculum, say, ask, step, answer, delegate, error.
"""
from __future__ import annotations

import contextlib
import ctypes
import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import brain_planner as BP

SECTIONS = [("overview", "Workspace Overview"), ("menus", "Primary Menus & Navigation"), ("tools", "Core Action Tools"), ("dialogs", "Dialogs & Advanced Features"), ("shortcuts", "Keyboard Shortcuts")]
TYPE_HELP = {"Button": "click it to run {n}", "SplitButton": "click it to run {n}; its arrow opens more choices", "ToggleButton": "switches {n} on or off", "CheckBox": "ticks or unticks {n}",
             "RadioButton": "chooses {n} from a group", "ComboBox": "a drop-down: choose a value for {n}", "TabItem": "switches to the {n} tab", "MenuItem": "opens the {n} menu",
             "Edit": "a text box for {n}", "Hyperlink": "a link: {n}", "ListItem": "an item in a list: {n}", "TreeItem": "an item in a tree: {n}", "Slider": "drag to set {n}", "Spinner": "step the value of {n}"}
REGION_TEXT = {"menu": "the menu bar: every command of the program is somewhere under these menus", "toolbar": "the toolbar / ribbon: the commands you use most, one click away",
               "content": "the work area: this is where the document, canvas or content you work on lives", "status": "the status bar: information about what you are doing",
               "side": "a side panel: extra tools and options", "title": "the title bar: the window's name and its buttons"}


def _dpi_aware() -> None:
    with contextlib.suppress(Exception):
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    with contextlib.suppress(Exception):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)


class Narrator:
    """Windows SAPI voice (pyttsx3) on its own thread; text is always shown on screen too, so the voice is optional."""

    def __init__(self) -> None:
        self.enabled = False
        self._q: "list[str]" = []
        self._cv = threading.Condition()
        self._t: Optional[threading.Thread] = None
        self.busy = False

    def say(self, text: str) -> None:
        if not self.enabled or not text:
            return
        with self._cv:
            self._q.append(text)
            self._cv.notify()
        if self._t is None or not self._t.is_alive():
            self._t = threading.Thread(target=self._run, daemon=True, name="narrator")
            self._t.start()

    def _run(self) -> None:
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import pyttsx3
            eng = pyttsx3.init()
            eng.setProperty("rate", 175)
        except Exception:
            return
        while True:
            with self._cv:
                while not self._q:
                    self._cv.wait(timeout=30)
                    if not self._q and not self.enabled:
                        return
                text = self._q.pop(0)
            self.busy = True
            with contextlib.suppress(Exception):
                eng.say(text)
                eng.runAndWait()
            self.busy = False

    def stop(self) -> None:
        with self._cv:
            self._q.clear()


def region_of(c: Dict[str, Any], win: Tuple[int, int, int, int]) -> str:
    """Which part of the window a control sits in, from its type and place (not from the application)."""
    x, y, w, h = c["box"]
    wx, wy, ww, wh = win
    ry = (y - wy) / max(wh, 1)
    rx = (x - wx) / max(ww, 1)
    t = c["type"]
    if t in ("MenuItem", "MenuBar", "Menu") and ry < 0.16:
        return "menu"
    if t == "Text":
        return "status" if ry > 0.9 else "content"
    if ry < 0.04:
        return "title"
    if ry > 0.93:
        return "status"
    if t in ("Edit", "Document", "Pane", "Custom", "Image", "Table", "DataGrid") and w > 0.4 * ww and h > 0.25 * wh:
        return "content"
    if ry < 0.30:
        return "toolbar"
    if rx < 0.18 or rx > 0.82:
        return "side"
    return "tools"


def explain(c: Dict[str, Any]) -> str:
    n = c["name"]
    base = (c.get("help") or "").strip() or TYPE_HELP.get(c["type"], "{n}").format(n=n)
    out = f"{n}: {base}"
    if c.get("key"):
        out += f". Shortcut: {c['key']}"
    return out + "."


class TutorSession:
    def __init__(self, engine: Any = None, voice: bool = False) -> None:
        _dpi_aware()
        self.events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.state = "idle"
        self.app_name = ""
        self.app_key = ""
        self.counts = {"regions": 0, "controls": 0, "menus": 0, "shortcuts": 0, "dialogs": 0}
        self.scan: Dict[str, Any] = {}
        self.curriculum: List[Dict[str, Any]] = []
        self.engine = engine
        self.narrator = Narrator()
        self.narrator.enabled = voice
        self.overlay: Any = None
        self.live: Any = None                                      # the LiveSession around the visible window
        self._ctx: Any = None
        self._stop = threading.Event()
        self._advance = threading.Event()
        self._pos = (0, 0)                                         # (section index, step index) of the tour
        self.autoplay = False
        self.window: Tuple[int, int, int, int] = (0, 0, 0, 0)

    # ------------------------------------------------------------------------------------------------------------------ events
    def emit(self, kind: str, **kw: Any) -> Dict[str, Any]:
        with self._lock:
            ev = {**kw, "id": len(self.events), "t": time.strftime("%H:%M:%S"), "kind": kind}          # the counters of the stream can never be overridden by a payload field
            self.events.append(ev)
        return ev

    def since(self, i: int) -> List[Dict[str, Any]]:
        with self._lock:
            return self.events[i:]

    def snapshot(self) -> Dict[str, Any]:
        return {"state": self.state, "app": self.app_name, "counts": self.counts, "sections": [{"id": s["id"], "title": s["title"], "steps": len(s["steps"])} for s in self.curriculum], "pos": list(self._pos),
                "voice": self.narrator.enabled, "autoplay": self.autoplay}

    def _set(self, state: str) -> None:
        self.state = state
        self.emit("status", state=state, counts=self.counts)

    def say(self, text: str, **kw: Any) -> None:
        self.emit("say", text=text, **kw)
        self.narrator.say(text)

    # ------------------------------------------------------------------------------------------------------------------ the pieces everything shares
    def _engine(self) -> Any:
        if self.engine is None:
            from core_organs import app_teaching_automation as ATA
            self.engine = ATA.AppIntelligenceEngine(log=lambda s: self.emit("log", text=str(s)))
        return self.engine

    def _overlay(self) -> Any:
        if self.overlay is None:
            from core_organs.professor.overlay import make_overlay
            self.overlay = make_overlay("auto")
        return self.overlay

    def point(self, box: Optional[Tuple[float, float, float, float]], label: str, n: Optional[int] = None, text: str = "", spotlight: bool = False, hotkey: str = "") -> None:
        """A spotlight box, a numbered callout and the flying pointer over the REAL window (screen pixels)."""
        if box is None:
            return
        from core_organs.professor.schema import Box
        ov = self._overlay()
        with contextlib.suppress(Exception):
            ov.point(Box.xywh(*box), label, n, "look", True, text or label, spotlight, True, hotkey)

    def clear_overlay(self) -> None:
        with contextlib.suppress(Exception):
            if self.overlay is not None:
                self.overlay.clear()

    # ------------------------------------------------------------------------------------------------------------------ Phase 1: visible scan
    def start(self, target: str) -> None:
        if self.state in ("scanning", "touring", "delegating"):
            self.emit("error", text="A session is already running; stop it first.")
            return
        self._stop.clear()
        self.app_name = target.strip()
        threading.Thread(target=self._scan_thread, args=(target.strip(),), daemon=True, name="tutor-scan").start()

    def _scan_thread(self, target: str) -> None:
        import uiautomation as auto
        t0 = time.time()
        try:
            with auto.UIAutomationInitializerInThread():
                self._scan(target)
        except Exception as exc:
            self.emit("error", text=f"{type(exc).__name__}: {str(exc)[:200]}")
            self._set("idle")
        self.emit("progress", text=f"scan finished in {time.time() - t0:.0f}s", done=True)

    def _open_visible(self, target: str) -> None:
        """Start an OWNED instance and put it on the screen (left part of the monitor), leaving the right edge for the companion window."""
        from core_organs import agent_executor as AE
        from core_organs.harvest import local_recorder as LR
        LR.OwnedApp.READY_S = 25.0
        LR.OwnedApp.VISIBLE_FALLBACK = True
        self.live = AE.LiveSession(target, uia_first=True)
        self.live.__enter__()
        app = self.live.app
        with contextlib.suppress(Exception):                       # un-park: the window goes where the person can see it
            if app.bg is not None:
                app.bg.__exit__(None, None, None)
                app.bg = None
        u = ctypes.windll.user32
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        w, h = max(700, sw - 520), max(500, sh - 120)
        for _ in range(8):                                          # the window was started minimised and unfocused: restore it, put it on top of what is on screen, leave it a normal window
            if u.IsIconic(app.hwnd):
                u.ShowWindow(app.hwnd, 9)                           # SW_RESTORE
            u.SetWindowPos(app.hwnd, -1, 16, 16, w, h, 0x0040)      # HWND_TOPMOST + SWP_SHOWWINDOW: in front of everything
            time.sleep(0.4)
            if not u.IsIconic(app.hwnd) and u.IsWindowVisible(app.hwnd):
                break
        u.SetWindowPos(app.hwnd, -2, 16, 16, w, h, 0x0040)          # HWND_NOTOPMOST: it stays where it is, no longer pinned
        time.sleep(1.2)
        self.window = (16, 16, w, h)

    def _controls(self) -> List[Dict[str, Any]]:
        """Controls on screen NOW, in screen pixels (origin 0,0), with help text and accelerator key read from the control. Type names are the short ones (Button, MenuItem ...); the work area and the
        status-bar texts, which are not 'actionable', are added so the tour can show the whole window."""
        import uiautomation as auto
        app = self.live.app
        u = ctypes.windll.user32
        size = (u.GetSystemMetrics(0), u.GetSystemMetrics(1))
        rows = app.controls((0, 0), size, budget_s=10.0)
        for r in rows:
            r["type"] = re.sub(r"Control$", "", r["type"])
            with contextlib.suppress(Exception):
                r["help"] = (r["ctl"].HelpText or "").strip()
                r["key"] = (r["ctl"].AcceleratorKey or r["ctl"].AccessKey or "").strip()
        wx, wy, ww, wh = self.window
        with contextlib.suppress(Exception):
            for c, _d in auto.WalkControl(auto.ControlFromHandle(app.hwnd), maxDepth=7):
                t = re.sub(r"Control$", "", c.ControlTypeName)
                r = c.BoundingRectangle
                nm = (c.Name or "").strip()
                if r.width() < 8 or r.height() < 8 or c.IsOffscreen:
                    continue
                if t in ("Document", "Edit") and r.width() > 0.4 * ww and r.height() > 0.25 * wh:
                    rows.append({"key": f"{t}|{nm}", "name": nm or "Work area", "type": t, "box": (r.left, r.top, r.width(), r.height()), "ctl": c, "popup": False, "help": "", "key": ""})
                elif t == "Text" and len(nm) > 1 and not (0xE000 <= ord(nm[0]) <= 0xF8FF) and (r.top - wy) / max(wh, 1) > 0.93:
                    rows.append({"key": f"Text|{nm}", "name": nm.replace("\n", " "), "type": "Text", "box": (r.left, r.top, r.width(), r.height()), "ctl": c, "popup": False, "help": "", "key": ""})
        out: List[Dict[str, Any]] = []
        for r in sorted(rows, key=lambda r: {"MenuItem": 0, "TabItem": 0}.get(r["type"], 1)):          # the same control often shows up twice (a MenuItem wrapping a Button): keep the more specific one
            x, y, w, h = r["box"]
            from core_organs import chrome_filter as CF
            if CF.is_window_chrome(r["name"], r["type"], (x - wx, y - wy, w, h), (ww, wh)):          # the window frame (Minimize / Maximize / Restore / Close / system menu) is not part of the lesson
                continue
            if any(o["name"] == r["name"] and abs(o["box"][0] - x) < 12 and abs(o["box"][1] - y) < 12 for o in out):
                continue
            r.setdefault("key", "")
            out.append(r)
        return out

    def _menu_items_now(self) -> List[Any]:
        """Every menu-item control the program exposes at this moment (its own window tree and any popup window)."""
        import uiautomation as auto
        from core_organs import headless_input as hin
        app = self.live.app
        roots = [app.hwnd]
        with contextlib.suppress(Exception):
            roots += list(hin.popup_windows(app.hwnd))[:3]
        out = []
        for h in roots:
            with contextlib.suppress(Exception):
                for c, _d in auto.WalkControl(auto.ControlFromHandle(h), maxDepth=12):
                    if c.ControlTypeName == "MenuItemControl" and (c.Name or "").strip():
                        out.append(c)
        return out

    def _read_menu(self, opener: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Open one menu and read its items through UI Automation (names, accelerator keys, whether it opens a dialog), then close it. The items are the menu-item controls that were NOT there before the
        menu opened. Nothing is ever clicked."""
        from core_organs import headless_input as hin
        app = self.live.app
        pre = {(c.Name.strip(), c.BoundingRectangle.left, c.BoundingRectangle.top) for c in self._menu_items_now()}
        pre_names = {n for n, _l, _t in pre}
        for _ in range(2):                                                   # a menu left open by the one before would swallow this one
            with contextlib.suppress(Exception):
                hin.post_key_combo(app.hwnd, "esc")
            time.sleep(0.3)
        app.act(opener["ctl"])
        fresh: List[Any] = []
        for _ in range(6):                                                   # the items appear a moment after the menu opens
            time.sleep(0.5)
            fresh = [c for c in self._menu_items_now() if (c.Name.strip(), c.BoundingRectangle.left, c.BoundingRectangle.top) not in pre and c.Name.strip() not in pre_names]
            if fresh:
                break
        items: List[Dict[str, Any]] = []
        seen = set()
        for c in fresh:
            nm = c.Name.strip()
            r = c.BoundingRectangle
            if (nm, r.left, r.top) in pre or nm in pre_names or nm in seen or r.width() < 8 or c.IsOffscreen:
                continue
            seen.add(nm)
            key = ""
            with contextlib.suppress(Exception):
                key = (c.AcceleratorKey or "").strip()
            if not key:
                m = re.search(r"\s+((?:Ctrl|Alt|Shift)(?:\+[A-Za-z0-9]+)+)\s*$", nm)
                if m:
                    key, nm = m.group(1), nm[:m.start()].strip()
            sub = False
            with contextlib.suppress(Exception):
                sub = c.GetExpandCollapsePattern() is not None
            items.append({"name": nm, "type": "MenuItem", "box": (r.left, r.top, r.width(), r.height()), "key": key, "dialog": nm.endswith(("...", "\u2026")), "help": (getattr(c, "HelpText", "") or "").strip(), "sub": sub})
        self._collapse(opener)
        return items

    def _collapse(self, opener: Dict[str, Any]) -> None:
        """Close the menu the way the menu itself offers (its expand / collapse pattern); a posted Escape is ignored by a XAML menu, and the next menu's Invoke would then only close this one."""
        from core_organs import headless_input as hin
        app = self.live.app
        for _ in range(3):
            state = None
            with contextlib.suppress(Exception):
                state = opener["ctl"].GetExpandCollapsePattern().ExpandCollapseState
            if state not in (1, 2):                                       # 1 = expanded, 2 = partially expanded
                break
            with contextlib.suppress(Exception):
                opener["ctl"].GetExpandCollapsePattern().Collapse()
            time.sleep(0.4)
        with contextlib.suppress(Exception):
            hin.post_key_combo(app.hwnd, "esc")
        time.sleep(0.3)
        with contextlib.suppress(Exception):
            app.close_popups()

    def _scan(self, target: str) -> None:
        from core_organs.professor import apprun as AR
        E = self._engine()
        self._set("scanning")
        self.emit("progress", text=f"Opening {target} on your screen ...", pct=3)
        self._open_visible(target)
        self.app_key = E.key_of(self.live.app.name if hasattr(self.live.app, "name") else target)
        before = E.coverage(self.app_key)
        self.emit("progress", text="Scanning top-level workspace ...", pct=15)
        rows = self._controls()
        for _ in range(8):                                           # a window that has just opened may not have drawn its interface yet: read again until it has
            if len(rows) >= 8 or self._stop.is_set():
                break
            self.emit("progress", text=f"The window is still drawing its interface ({len(rows)} controls so far) ...")
            time.sleep(2.0)
            rows = self._controls()
        regions: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            r["region"] = region_of(r, self.window)
            regions.setdefault(r["region"], []).append(r)
        self.counts.update(regions=len(regions), controls=len(rows))
        self.emit("counters", counts=self.counts)
        self.emit("progress", text=f"Found {len(regions)} regions and {len(rows)} controls: " + ", ".join(f"{k} ({len(v)})" for k, v in regions.items()), pct=30)
        menus: Dict[str, List[Dict[str, Any]]] = {}
        openers = [r for r in regions.get("menu", []) if r["type"] == "MenuItem" and r["name"].lower() != "system" and not AR.safety_blocked(r["name"])]
        tabs = [r for r in rows if r["type"] == "TabItem"]
        self.emit("progress", text=f"Discovering menus: {len(openers)} to open and read ...", pct=40)
        t_end = time.time() + 70
        for i, op in enumerate(openers[:10]):
            if time.time() > t_end or self._stop.is_set():
                break
            items = self._read_menu(op)
            menus[op["name"]] = items
            self.counts["menus"] = len(menus)
            self.counts["controls"] += len(items)
            self.counts["shortcuts"] += sum(1 for it in items if it["key"])
            self.counts["dialogs"] += sum(1 for it in items if it["dialog"])
            self.emit("counters", counts=self.counts)
            self.emit("progress", text=f"Menu '{op['name']}': {len(items)} commands, {sum(1 for it in items if it['key'])} shortcuts, {sum(1 for it in items if it['dialog'])} open dialogs", pct=40 + int(35 * (i + 1) / max(len(openers), 1)))
        for r in rows:
            if r.get("key"):
                self.counts["shortcuts"] += 1
        self.emit("counters", counts=self.counts)
        self.emit("progress", text="Indexing shortcuts and what I already know about this app ...", pct=80)
        known = self._rag_shortcuts()
        self.scan = {"rows": rows, "regions": regions, "menus": menus, "tabs": tabs, "known_keys": known}
        self.emit("progress", text="Building the full-app curriculum ...", pct=90)
        self.curriculum = self._build_curriculum()
        threading.Thread(target=self._remember, args=(menus, before), daemon=True, name="tutor-remember").start()
        self.emit("curriculum", sections=[{"id": s["id"], "title": s["title"], "steps": [st["title"] for st in s["steps"]]} for s in self.curriculum])
        self.emit("progress", text="Scan complete.", pct=100)
        self._set("ready")
        self.emit("ask", text=(f"I've finished learning {self.app_name} (mapped {self.counts['regions']} workspaces, {self.counts['controls']} controls, {self.counts['menus']} menus and "
                               f"{self.counts['shortcuts']} shortcuts). Do you want me to give you a full live step-by-step tutorial of the entire app, answer a specific question, or delegate a task to me?"),
                  options=["Yes, teach me the whole app", "Answer a question", "Do a task for me"])

    def _rag_shortcuts(self) -> List[str]:
        try:
            rows = self._engine().get_rag().fast.query(self.app_key) if hasattr(self._engine().get_rag().fast, "query") else []
            return [str(r.get("payload", "")) for r in rows][:50]
        except Exception:
            return []

    def _remember(self, menus: Dict[str, List[Dict[str, Any]]], before: Dict[str, int]) -> None:
        """What was read goes back into the RAG (menu paths as procedures, accelerator keys as shortcuts), so the next session starts from it."""
        with contextlib.suppress(Exception):
            rag = self._engine().get_rag()
            from core_organs.rag import domains as DM
            from core_organs.harvest import bridge as BR
            DM.register(rag, self.app_key, DM.DESKTOP, {"why": "scanned live through its accessibility tree by the tutor"})
            n = 0
            for top, items in menus.items():
                for it in items:
                    steps = [{"text": f"Open the {top} menu", "target": top, "route_hint": "control_click"}, {"text": f"Choose {it['name']}" + (f" (shortcut {it['key']})" if it["key"] else ""), "target": it["name"], "route_hint": "control_click"}]
                    rag.proc.ingest_procedure(self.app_key, f"{self.app_name}: {top} > {it['name']}", steps, "live-scan", trust="learned")
                    n += 1
                    if it["key"]:
                        BR.ingest_hotkeys(rag, [{"app_name": self.app_name, "app_key": self.app_key, "action": f"{top} > {it['name']}", "shortcut": it["key"], "source": "keymap_file", "url": ""}])
            self.emit("log", text=f"remembered {n} menu commands in the RAG (before: {before})")

    # ------------------------------------------------------------------------------------------------------------------ the curriculum
    def _build_curriculum(self) -> List[Dict[str, Any]]:
        sc = self.scan
        win = self.window
        regions, menus, rows = sc["regions"], sc["menus"], sc["rows"]
        out: List[Dict[str, Any]] = []

        def union(cs: Sequence[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
            if not cs:
                return None
            x1 = min(c["box"][0] for c in cs)
            y1 = min(c["box"][1] for c in cs)
            x2 = max(c["box"][0] + c["box"][2] for c in cs)
            y2 = max(c["box"][1] + c["box"][3] for c in cs)
            return (x1 - 4, y1 - 4, x2 - x1 + 8, y2 - y1 + 8)
        steps = []
        for name, cs in sorted(regions.items(), key=lambda kv: ["title", "menu", "toolbar", "tools", "side", "content", "status"].index(kv[0]) if kv[0] in ["title", "menu", "toolbar", "tools", "side", "content", "status"] else 9):
            box = union(cs) if name != "content" else union(cs) or win
            steps.append({"title": name.capitalize() if name != "tools" else "Tools", "say": f"This is {REGION_TEXT.get(name, 'part of the window')}. It holds {len(cs)} controls.", "box": box, "demo": None})
        out.append({"id": "overview", "title": SECTIONS[0][1], "steps": steps or [{"title": "Window", "say": f"This is {self.app_name}.", "box": win, "demo": None}]})
        # menus & navigation
        steps = []
        for top, items in menus.items():
            op = next((r for r in regions.get("menu", []) if r["name"] == top), None)
            steps.append({"title": f"{top} menu", "say": f"The {top} menu has {len(items)} commands" + (": " + ", ".join(i["name"] for i in items[:6]) + ("..." if len(items) > 6 else "") if items else "."), "box": op["box"] if op else None, "demo": ("menu", top)})
        for t in sc["tabs"][:8]:
            steps.append({"title": f"{t['name']} tab", "say": explain(t), "box": t["box"], "demo": None})
        out.append({"id": "menus", "title": SECTIONS[1][1], "steps": steps})
        # core tools: the named buttons outside the menu bar, the ones with help or a shortcut first
        tools = [r for r in rows if r["region"] in ("toolbar", "tools", "side") and r["type"] not in ("TabItem", "MenuItem") and r["name"]]
        tools.sort(key=lambda r: (not r.get("help"), not r.get("key"), r["box"][1], r["box"][0]))
        out.append({"id": "tools", "title": SECTIONS[2][1], "steps": [{"title": r["name"], "say": explain(r), "box": r["box"], "demo": None} for r in tools[:24]]})
        # dialogs and advanced
        steps = []
        for top, items in menus.items():
            op = next((r for r in regions.get("menu", []) if r["name"] == top), None)
            for it in items:
                if it["dialog"]:
                    steps.append({"title": it["name"], "say": f"{it['name']} (in the {top} menu) opens a dialog window with more options" + (f". Shortcut: {it['key']}" if it["key"] else "") + ".", "box": op["box"] if op else None, "demo": ("menu", top)})
        content = regions.get("content", [])
        if content:
            steps.append({"title": "Work area", "say": "Everything you create happens in the work area; the menus and tools around it act on what is here.", "box": union(content), "demo": ("type", "")})
        out.append({"id": "dialogs", "title": SECTIONS[3][1], "steps": steps[:16] or [{"title": "Advanced", "say": "This program keeps its advanced features in its menus.", "box": None, "demo": None}]})
        # shortcuts
        keys = []
        for top, items in menus.items():
            for it in items:
                if it["key"]:
                    keys.append({"title": f"{it['key']}: {it['name']}", "say": f"Press {it['key']} to {it['name'].lower()} (also in the {top} menu).", "box": None, "demo": None})
        for r in rows:
            if r.get("key"):
                keys.append({"title": f"{r['key']}: {r['name']}", "say": f"Press {r['key']} to use {r['name']}.", "box": r["box"], "demo": None})
        out.append({"id": "shortcuts", "title": SECTIONS[4][1], "steps": keys[:30] or [{"title": "Shortcuts", "say": "This program does not publish its shortcuts in its menus; ask me about a specific command and I will look it up.", "box": None, "demo": None}]})
        return out

    # ------------------------------------------------------------------------------------------------------------------ Phase 3: the live tutorial
    def chat(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.emit("user", text=text)
        low = text.lower()
        if self.state == "ready" and re.search(r"\b(yes|teach|tutorial|whole app|full|start|show me the app|tour)\b", low) and not re.search(r"\b(for me|build|draw|type|write|make)\b", low):
            self.tour()
            return
        if self.state == "touring" and re.search(r"^(next|continue|go on|skip)\b", low):
            self.control("next")
            return
        if self.state == "touring" and re.search(r"^(repeat|again|back)\b", low):
            self.control("repeat")
            return
        if self.state in ("scanning", "delegating"):
            self.emit("say", text="I'm busy with the last request; one moment.")
            return
        threading.Thread(target=self._answer_thread, args=(text,), daemon=True, name="tutor-answer").start()

    def tour(self, autoplay: bool = False) -> None:
        if not self.curriculum:
            self.emit("error", text="Nothing scanned yet.")
            return
        self.autoplay = autoplay
        self._stop.clear()
        threading.Thread(target=self._tour_thread, daemon=True, name="tutor-tour").start()

    def control(self, action: str) -> None:
        if action == "next":
            self._advance.set()
        elif action == "repeat":
            self._pos = (self._pos[0], max(0, self._pos[1] - 1))
            self._advance.set()
        elif action == "stop":
            self._stop.set()
            self._advance.set()
            self.clear_overlay()
            self.narrator.stop()
        elif action == "voice":
            self.narrator.enabled = not self.narrator.enabled
            self.emit("status", state=self.state, voice=self.narrator.enabled, counts=self.counts)
        elif action == "autoplay":
            self.autoplay = not self.autoplay
            self._advance.set()
        elif action == "close":
            self.close()

    def _tour_thread(self) -> None:
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            self._set("touring")
            self.say(f"Let's walk through {self.app_name} together, section by section. Press Next whenever you are ready.")
            si, sj = self._pos if self._pos != (0, 0) and self.state == "touring" else (0, 0)
            si, sj = 0, 0
            while si < len(self.curriculum) and not self._stop.is_set():
                sec = self.curriculum[si]
                if sj == 0:
                    self.emit("section", index=si, key=sec["id"], title=sec["title"], total=len(self.curriculum))
                    self.say(f"Section {si + 1} of {len(self.curriculum)}: {sec['title']}.")
                while sj < len(sec["steps"]) and not self._stop.is_set():
                    st = sec["steps"][sj]
                    self._pos = (si, sj)
                    self.emit("step", section=sec["title"], index=sj, total=len(sec["steps"]), title=st["title"], text=st["say"])
                    self.point(st["box"], st["title"], sj + 1, st["say"][:140], spotlight=(sec["id"] == "overview"), hotkey=self._first_key(st["say"]))
                    self.narrator.say(st["say"])
                    self._demo(st)
                    self._advance.clear()
                    waited = 0.0
                    while not self._advance.wait(0.25) and not self._stop.is_set():
                        waited += 0.25
                        if self.autoplay and waited >= max(4.0, len(st["say"]) / 14.0) and not self.narrator.busy:
                            break
                    if self._pos[1] < sj:                       # 'repeat' moved the position back
                        sj = self._pos[1]
                        continue
                    sj += 1
                si, sj = si + 1, 0
            self.clear_overlay()
            if not self._stop.is_set():
                self.say("That was the whole tour. You can ask me where anything is, how to do something, or tell me a task and I will do it for you.")
            self._set("ready")
            self.emit("ask", text="What next? Ask a question, replay a section, or hand me a task.", options=["Do a task for me", "Answer a question"])

    @staticmethod
    def _first_key(text: str) -> str:
        m = re.search(r"((?:Ctrl|Alt|Shift)(?:\+[A-Za-z0-9]+)+)", text)
        return m.group(1) if m else ""

    def _demo(self, st: Dict[str, Any]) -> None:
        """Show it, safely: open the menu so the person sees its items; type a sample line in a text area of the owned throw-away instance."""
        d = st.get("demo")
        if not d or self.live is None:
            return
        with contextlib.suppress(Exception):
            if d[0] == "menu":
                op = next((r for r in self.scan["regions"].get("menu", []) if r["name"] == d[1]), None)
                if op is not None:
                    self.live.app.act(op["ctl"])
                    time.sleep(1.6)
                    self._advance.wait(0.1)
            elif d[0] == "type":
                self.live.app.type_text("Hello! This line was typed by HoJaiga to show the work area.")

    def _close_menus(self) -> None:
        with contextlib.suppress(Exception):
            from core_organs import headless_input as hin
            hin.post_key_combo(self.live.app.hwnd, "esc")

    # ------------------------------------------------------------------------------------------------------------------ questions and delegation
    def _answer_thread(self, text: str) -> None:
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            intent = BP.classify_intent(text)
            if intent["mode"] == "delegate" or re.search(r"\b(for me|take over|automate)\b", text.lower()):
                self.delegate(re.sub(r"^(please\s+)?(can you\s+)?", "", text, flags=re.I))
                return
            self.answer(text)

    def answer(self, text: str) -> None:
        """Find what the question is about ON the live window; spotlight it and say what it is, where it is and how to reach it by keyboard."""
        best = self._find(text)
        E = self._engine()
        pw = {}
        with contextlib.suppress(Exception):
            pw = E.pathways(text, self.app_key)
        lines: List[str] = []
        box = None
        if best:
            c = best[0]
            where = f"in the {c.get('where', 'window')}"
            lines.append(f"{explain(c)} It is {where}.")
            if c.get("menu"):
                lines[-1] = f"{c['name']} is in the {c['menu']} menu" + (f" (shortcut {c['key']})" if c.get("key") else "") + "."
                box = next((r["box"] for r in self.scan["regions"].get("menu", []) if r["name"] == c["menu"]), None)
                self._demo({"demo": ("menu", c["menu"])})
            else:
                box = c["box"]
            if len(best) > 1:
                lines.append("Also related: " + ", ".join(b["name"] for b in best[1:3]) + ".")
        for p in (pw.get("plans") or [])[:1]:
            if p.get("steps"):
                lines.append("From what I've learned: " + " -> ".join(p["steps"]))
        if not lines:
            lines.append("I could not find anything on this window that matches that. Try the menu names, or tell me what you want done and I will do it.")
        self.point(box, best[0]["name"] if best else "", None, lines[0][:140])
        self.say(" ".join(lines))
        self.emit("answer", text=" ".join(lines), box=box)

    def _find(self, text: str) -> List[Dict[str, Any]]:
        words = {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in {"the", "where", "how", "can", "find", "what", "does", "show", "open", "button", "tool", "menu", "use", "which", "for", "with", "and", "this", "that"}}
        if not words:
            return []
        cands: List[Dict[str, Any]] = []
        for r in self.scan.get("rows", []):
            cands.append(dict(r, where=r["region"]))
        for top, items in self.scan.get("menus", {}).items():
            for it in items:
                cands.append(dict(it, menu=top, where=f"{top} menu", region="menu"))
        scored = []
        for c in cands:
            have = {w for w in re.findall(r"[a-z0-9]+", (c["name"] + " " + (c.get("help") or "")).lower())}
            hit = len(words & have)
            if hit:
                bonus = 0.5 if c.get("menu") else (-0.5 if c.get("region") == "menu" else 0.0)
                scored.append((hit + bonus - 0.01 * len(have), c))
        scored.sort(key=lambda x: -x[0])
        out, seen = [], set()
        for _s, c in scored:
            if c["name"] not in seen:
                seen.add(c["name"])
                out.append(c)
        return out[:4]

    def delegate(self, task: str) -> None:
        """Take over: the same engine does the job on the same window (goals planned by the CPU brain, UIA-first actions, goal-aware verification, rollback)."""
        from core_organs import app_teaching_automation as ATA
        self._set("delegating")
        self.clear_overlay()
        self.say(f"On it: {task}")
        flow = ATA.Flow(lambda s: self.emit("log", text=s))
        try:
            sec = ATA.AppTeachingAutomationSection(engine=self._engine(), log=lambda s: self.emit("log", text=str(s)))
            out = sec._uia(task, self.app_name, self.app_key, "delegate", flow, False, False, session=self.live)
            v = out.get("verification") or {}
            self.emit("delegate", task=task, steps=out.get("steps", []), verification=v, read_back=(out.get("final_text") or "")[:300], flow=flow.states)
            ok = v.get("total") and v.get("done") == v.get("total")
            self.say(("Done: " if ok else "I did what I could: ") + f"{v.get('done', 0)} of {v.get('total', 0)} steps verified" + (f", {v.get('rollbacks')} undone." if v.get("rollbacks") else "."))
        except Exception as exc:
            self.emit("error", text=f"{type(exc).__name__}: {str(exc)[:200]}")
        self._set("ready")

    # ------------------------------------------------------------------------------------------------------------------ end
    def close(self) -> None:
        self._stop.set()
        self._advance.set()
        self.clear_overlay()
        with contextlib.suppress(Exception):
            if self.live is not None:
                self.live.__exit__(None, None, None)
        self.live = None
        self._set("idle")
