"""
harvest.local_recorder -- training pairs from apps WE OWN, driven in the background, with the answer known by construction.

The YouTube route is limited by captions, rate limits and ~0.55 usable pairs per video. This route needs none of them: an owned instance of an application (the same guarded launch the Professor's app-run
harness uses: state backup, minimized/parked, never the person's focus) is read through UI Automation, and each control is exercised the way the live agent would exercise it:

    frame BEFORE (PrintWindow of the parked window)  ->  the action, delivered through a UIA pattern or posted window messages (never physical input)  ->  frame AFTER

A pair is kept only when the picture really changed. Because UIA names the control and gives its rectangle, the target is not guessed from a caption: the numbered element the training prompt shows is the one
whose box overlaps the UIA rectangle (IoU), found on the SAME Set-of-Marks the live model reads (Tesseract/icon tiers through professor.sweeper), so the prompt the model trains on is the prompt it will see.
Frames are real captures of a real interface, so `ui_frames` is true by construction (no VLM gate is needed). Rows are written with harvest.video_explain.build_row, the exact format of the video route.

Safety: safety_guard on every control name, a deny-list for controls that open file dialogs or leave the app, popups the app opens are closed again, state is restored by the StateGuard, and the window is only
ever ended through the scanner's close_owned (never by image name).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import child_windows as CW
from .paths import harvest_dir

# What may be exercised per application. `chords` = (keys, what it does, keys that undo it). Everything here was chosen because it is local, reversible and opens nothing outside the window.
APPS: Dict[str, Dict[str, Any]] = {
    "calculator": {"launch": "calculator", "nav": {"open": "Open Navigation", "items": ["Scientific Calculator", "Programmer Calculator", "Date calculation Calculator", "Volume Converter", "Length Converter", "Weight and mass Converter",
                                                                                                    "Temperature Converter", "Energy Converter", "Area Converter", "Speed Converter", "Time Converter", "Power Converter", "Data Converter",
                                                                                                    "Pressure Converter", "Angle Converter"], "home": "Standard Calculator"}, "type": None,
                   "chords": [("alt+2", "Switch the calculator to Scientific mode", "alt+1"), ("alt+4", "Switch the calculator to Programmer mode", "alt+1"),
                              ("alt+5", "Switch the calculator to Date calculation mode", "alt+1")]},
    "notepad": {"launch": "notepad", "chords": [], "type": "Meeting notes for Monday", "menus": ["File", "Edit", "View"]},
    "clock": {"launch": "clock", "chords": [], "type": None},
    "sticky_notes": {"launch": "Sticky Notes", "chords": [], "type": None},
    # `deny` (optional, per app) = words that make a control unsafe in THAT app on top of the global list. TRIED AND DROPPED on this machine: ODBC Data Sources (asks for elevation: never launched), XPS Viewer
    # (an empty viewer has < 5 controls), System Information (its first page shows the machine name = the person's name). File Explorer, Command Prompt, Task Manager, 7-Zip and Office were NOT driven: they
    # show or act on the person's own files and processes.
    "ms_paint": {"launch": "paint", "chords": [], "type": None, "menus": ["File", "Edit", "View", "Show toolbar"]},
}
# MEASURED (Windows 11 Calculator / Notepad, parked): shortcuts posted as window messages reach an app only through its Alt accelerators -- Calculator's Alt+<n> modes switch, but F9, R, Ctrl+P, Delete and Esc
# (Calculator) and Ctrl+F / Ctrl+H (Notepad) are delivered and ignored by the XAML input stack. Physical keystrokes are not allowed here, so those apps yield click and type pairs, and hotkey pairs only
# where a shortcut is measured to land. A classic Win32 app (accelerator table) takes any chord: list it in `chords` and the picture-changed test keeps only the ones that work.

# controls that leave the window, open a file dialog or change something outside the app
DENY_RX = re.compile(r"\b(open|save|print|page setup|exit|close|quit|new|share|settings|feedback|help|about|import|export|upload|download|sign|account|extension|store|copilot|camera|scan|"
                     r"recent|browse|email|send|delete|remove|erase|reset|clear history|license|privacy|update|window|sign(ed)?|log ?(in|out)|profile|hide|copy|cut|paste|focus|spotify|microsoft to do|bing|online|web|"
                     # MEASURED (OBS Studio): a scanner clicked 'Start Streaming' and 'Start Recording' because nothing here knew those words; only OBS's own 'No Sources' dialog stopped them. Anything that starts, stops,
                     # broadcasts, publishes, installs, connects or erases something is never operated by a learner.
                     r"start|stop|record(ing)?|stream(ing)?|broadcast|go live|publish|virtual camera|begin|run|execute|install|deploy|flash|burn|format|wipe|shutdown|restart|power|connect|pair|"
                     r"post|tweet|submit|buy|purchase|subscribe|join|invite|mic(rophone)?)\b", re.I)
CHROME_RX = re.compile(r"^(minimi[sz]e|maximi[sz]e|restore|close)\b|^system$", re.I)
ACTIONABLE = ("ButtonControl", "MenuItemControl", "TabItemControl", "SplitButtonControl", "CheckBoxControl", "RadioButtonControl", "ListItemControl", "TreeItemControl")
NOUN = {"ButtonControl": "button", "MenuItemControl": "menu item", "TabItemControl": "tab", "SplitButtonControl": "button", "CheckBoxControl": "checkbox", "RadioButtonControl": "option", "ListItemControl": "item", "TreeItemControl": "tree item"}


def iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw_, bh = b
    ix, iy = max(ax, bx), max(ay, by)
    ox, oy = min(ax + aw, bx + bw_), min(ay + ah, by + bh)
    inter = max(0.0, ox - ix) * max(0.0, oy - iy)
    union = aw * ah + bw_ * bh - inter
    return inter / union if union > 0 else 0.0


def element_at(som: Dict[str, Any], box: Tuple[float, float, float, float], min_cover: float = 0.6) -> Optional[Dict[str, Any]]:
    """The numbered element that IS the control UIA reported. The Set-of-Marks boxes the scanner finds are the glyph or text INSIDE a control (a '%' in a 215x104 key), so the match is containment, not
    IoU: an element whose centre lies in the control's rectangle and which lies >= min_cover inside it. A labelled element beats an unlabelled one; then the one nearest the centre. None when nothing is
    inside (an icon the scanner missed is not guessed)."""
    bx, by, bw_, bh = box
    cx, cy = bx + bw_ / 2, by + bh / 2
    best, best_key = None, None
    for e in som.get("elements", []):
        if not e.get("box"):
            continue
        ex, ey, ew, eh = e["box"]
        ecx, ecy = ex + ew / 2, ey + eh / 2
        if not (bx <= ecx <= bx + bw_ and by <= ecy <= by + bh) or ew * eh <= 0:
            continue
        inter = max(0.0, min(ex + ew, bx + bw_) - max(ex, bx)) * max(0.0, min(ey + eh, by + bh) - max(ey, by))
        if inter / (ew * eh) < min_cover:
            continue
        key = (0 if (e.get("label") or "").strip() else 1, (ecx - cx) ** 2 + (ecy - cy) ** 2)
        if best_key is None or key < best_key:
            best, best_key = e, key
    return best


def _personal(name: str) -> bool:
    """A control that carries the signed-in person's name ('Signed in as ...', an account button) is never recorded: the dataset must not contain who the person is."""
    import getpass
    low = (name or "").lower()
    try:
        user = getpass.getuser().lower()
    except Exception:
        user = ""
    return bool(user and len(user) >= 3 and user in low)


def volatile(name: str) -> bool:
    """A control named by live data (a clock face, a timestamp, a long generated label) is not a stable instruction: the same control will have another name next time."""
    clean = re.sub(r"[‎‏]", "", name or "")
    return len(clean) > 50 or bool(re.search(r"\d{1,2}\s*:\s*\d{2}|\d{4}", clean))


def goal_for(name: str, control_type: str) -> str:
    name = re.sub(r"[‎‏]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return f"Click the {name} {NOUN.get(control_type, 'button')}"


def changed(before, after, threshold: int = 24, min_px: int = 60) -> Tuple[bool, Optional[Tuple[int, int, int, int]]]:
    """Did the picture change (>= min_px pixels moved by more than `threshold` gray levels)? And where (x, y, w, h)?"""
    import numpy as np
    if before is None or after is None or before.size != after.size:
        return False, None
    d = np.abs(np.asarray(before.convert("L"), dtype=np.int16) - np.asarray(after.convert("L"), dtype=np.int16)) > threshold
    n = int(d.sum())
    if n < min_px:
        return False, None
    ys, xs = np.where(d)
    return True, (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


class OwnedApp:
    VISIBLE_FALLBACK = False                                        # when the quiet start fails: open the app normally, wait for its interface, then park it and hand the focus back (a brief visible start)
    READY_S = 8.0                                                    # how long a freshly started window gets to show a usable interface (a cold UWP / Electron start can need much longer)
    """An owned, parked instance: `with OwnedApp('calculator') as app:` -> app.hwnd, app.grab(), app.controls(), app.act(), app.chord(), app.type()."""

    def __init__(self, launch_name: str):
        self.name = launch_name
        self.hwnd = 0
        self.notes: List[str] = []
        self.bg = None
        self.guard = None

    def __enter__(self) -> "OwnedApp":
        from core_organs import env_guard as _eg
        _orig = _eg.check_runtime_pins                              # the OmniParser pin check guards a model we do not load here; the training environment legitimately differs
        _eg.check_runtime_pins = lambda *a, **k: _orig(*a, **dict(k, strict=False))
        from core_organs import background_window as bw, headless_input as hin
        from core_organs.professor import launcher as LN, state_protect as SPT
        hin.ensure_input_desktop()
        from core_organs import owned_guard as OG
        OG.reap_orphans()                                           # an app a dead run left behind is ended (by PID) before a new one starts
        t = LN.resolve(self.name)
        self.guard = SPT.StateGuard(self.name, t.appid)
        self.guard.before()
        last = ""
        for attempt in range(1):                                    # ONE attempt, 8 s wall clock: a window still on its splash screen is killed and the app skipped. A UWP window parked off-screen sometimes never leaves its splash (measured: Calculator, Clock): end it and start over
            info = LN.launch_owned(t, self.guard)
            self.hwnd = int(info.get("hwnd") or 0)
            self.info = info                                        # kept: a browser's DevTools port (info['cdp_port']) is how a page is navigated
            self.notes = list(info.get("notes") or [])
            if not (info.get("launched") and self.hwnd):
                last = f"could not start: {info.get('trace') or self.notes}"
                print(f"[local_recorder] {self.name}: attempt {attempt + 1} did not start: {last[:300]}", file=sys.stderr, flush=True)
                continue
            with contextlib.suppress(Exception):
                import ctypes
                _pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(self.hwnd, ctypes.byref(_pid))
                self.owned_pid = int(_pid.value)
                self.owned_bind = OG.bind(self.owned_pid, self.name)   # dies with this process, however this process ends
            self.bg = bw.BackgroundSession(self.hwnd)
            self.bg.__enter__()
            self.bg.lay_out()
            self.mode = self.bg.mode
            time.sleep(1.0)
            if self._ready(self.READY_S):
                return self
            if self._start_dialog():                                # the first window was a start-up question ('launch in safe mode?', 'restore the session?'): answered safely, the real window adopted
                return self
            last = f"the window never showed a usable interface (a splash screen; mode={self.mode})"
            self._close_window()
            restarted = self._restart_idle_frame_host()
            print(f"[local_recorder] {self.name}: attempt {attempt + 1} stayed on its splash screen; frame host restarted={restarted}", file=sys.stderr, flush=True)
        if self.VISIBLE_FALLBACK and not getattr(t, "chromium", ""):
            if self._visible_start(t):
                return self
            last += " | the visible start did not produce a usable window either"
        self.__exit__(None, None, None)
        raise RuntimeError(f"{self.name}: {last}")

    # in order of preference: carry on normally first, then decline, then dismiss. Never Yes / OK / Accept / Sign in / Continue (they confirm something), never a 'safe mode' (it changes what is scanned).
    START_DIALOG_ANSWERS = ("run in normal mode", "launch normally", "start normally", "normal mode", "no", "not now", "skip", "later", "maybe later", "don't save", "cancel", "dismiss", "close")

    def _start_dialog(self) -> bool:
        """A freshly started app that stops at a small dialog (OBS after a crash: 'launch in safe mode?') is not on a splash screen, it is asking something. Only a SAFE answer is ever pressed (No / Not now /
        Skip / Later / Cancel / Close: never Yes / OK / Accept / Sign in); then the app's own main window is looked for and adopted exactly like a normal start."""
        import ctypes
        import uiautomation as auto
        from core_organs import background_window as bw, headless_input as hin, universal_scan as us
        if not self.hwnd or not hin.is_alive(self.hwnd):
            return False
        old = self.hwnd
        pid = hin.window_pid(old)
        btn = None
        n = 0
        t_end = time.time() + 4.0
        with contextlib.suppress(Exception):
            for c, _d in auto.WalkControl(auto.ControlFromHandle(old), maxDepth=8):
                n += 1
                if n > 150 or time.time() > t_end:
                    break
                if c.ControlTypeName == "ButtonControl" and (c.Name or "").strip().lower() in self.START_DIALOG_ANSWERS:
                    rank = self.START_DIALOG_ANSWERS.index((c.Name or "").strip().lower())
                    if btn is None or rank < btn[0]:
                        btn = (rank, c)
        if btn is None:
            return False
        label = (btn[1].Name or "").strip()                         # read BEFORE pressing: the button is gone afterwards
        how = self.act(btn[1])
        self.notes.append(f"start-up dialog answered: {label!r} ({how or 'no pattern'})")
        t0 = time.time()
        while time.time() - t0 < 25.0:
            time.sleep(1.0)
            for h, (p, cls, title) in us._top_windows().items():
                if p != pid or h == old or not title:
                    continue
                self.hwnd = h
                if self.bg is not None:
                    with contextlib.suppress(Exception):
                        self.bg.__exit__(None, None, None)
                self.bg = bw.BackgroundSession(h)
                self.bg.__enter__()
                self.bg.lay_out()
                self.mode = self.bg.mode
                time.sleep(1.0)
                if self._ready(self.READY_S):
                    return True
        self.hwnd = old
        return False

    def _visible_start(self, t: Any, timeout_s: float = 45.0) -> bool:
        """The 'search it and open it' route: the app is started the way the Start menu starts it (shell:AppsFolder for a packaged app, the program for a classic one) WITHOUT being minimized -- a minimized
        packaged app never draws its interface (MEASURED: it stays on its splash screen). Once its window shows >= 5 controls it is parked off-screen like any owned app and the focus goes back to what the person
        was using. The person may see the window for a few seconds."""
        import subprocess
        from core_organs import background_window as bw, headless_input as hin, universal_scan as us
        before = us._top_windows()
        fg0 = bw.last_user_window() or us._u32.GetForegroundWindow()
        try:
            if t.exe and not t.packaged and os.path.isfile(t.exe):
                subprocess.Popen([t.exe], cwd=os.path.dirname(t.exe))
            elif t.appid:
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{t.appid}"], creationflags=0x08000000)
            else:
                return False
        except Exception as exc:
            self.notes.append(f"visible start failed: {type(exc).__name__}")
            return False
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            now = us._top_windows()
            for h, (pid, cls, title) in now.items():
                if not title or cls in ("Windows.UI.Core.CoreWindow",):
                    continue
                leftover = h in before and bool(us._u32.IsIconic(h)) and (title.lower() == (t.display or self.name).lower() or title.lower() == self.name.lower())
                if h in before and not leftover:                         # a window that was there before and is on screen may be the PERSON'S own: never adopted. A minimized one with this app's name is what our own failed quiet start left behind.
                    continue
                if leftover:
                    us._u32.ShowWindow(h, 4)                             # SW_SHOWNOACTIVATE: a minimized packaged window never draws
                self.hwnd = h
                self.bg = None
                with contextlib.suppress(Exception):
                    img, origin = self.grab(stable=False)
                    if os.environ.get("HOJAIGA_DEBUG_LAUNCH"):
                        print(f"[visible_start] {h} {cls!r} {title!r} img={img.size if img is not None else None} controls={len(self.controls(origin, img.size)) if img is not None else 0}", file=sys.stderr, flush=True)
                    if img is not None and len([c for c in self.controls(origin, img.size) if not CHROME_RX.search(c["name"])]) >= 2:         # a narrow window collapses its navigation; once parked at the owned size it shows the rest
                        with contextlib.suppress(Exception):
                            import ctypes
                            _pid = ctypes.c_ulong()
                            ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(_pid))
                            from core_organs import owned_guard as OG
                            self.owned_pid = int(_pid.value)
                            self.owned_bind = OG.bind(self.owned_pid, self.name)
                        self.bg = bw.BackgroundSession(h)
                        self.bg.__enter__()                                # parked: off-screen, with its 1-px sliver so it keeps drawing
                        self.bg.lay_out()
                        self.mode = self.bg.mode
                        with contextlib.suppress(Exception):
                            if fg0 and us._u32.GetForegroundWindow() != fg0:
                                hin._hand_back_focus(int(fg0))
                        time.sleep(1.0)
                        if not self._ready(self.READY_S):
                            return False
                        self.notes.append("started visibly, then parked")
                        return True
            time.sleep(0.5)
        self.hwnd = 0
        return False

    @staticmethod
    def _restart_idle_frame_host() -> bool:
        """MEASURED: after a few launches the UWP frame host (ApplicationFrameHost.exe) can stay wedged and every packaged app parks on its splash screen; ending that one helper process (it restarts on demand)
        clears it. Only when NO window it hosts is on the person's screen: a user's own UWP window is never taken down. Ended by PID, never by image name."""
        try:
            import ctypes
            import psutil
            from core_organs import background_window as bw
            hosts = [p.pid for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() == "applicationframehost.exe"]
            u = ctypes.windll.user32
            hosted = []

            def cb(h, _l):
                if u.IsWindowVisible(h) or u.IsIconic(h):
                    buf = ctypes.create_unicode_buffer(256)
                    u.GetClassNameW(h, buf, 256)
                    pid = ctypes.c_ulong()
                    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    title = ctypes.create_unicode_buffer(256)
                    u.GetWindowTextW(h, title, 256)
                    if buf.value == "ApplicationFrameWindow" and pid.value in hosts and title.value.strip() and not bw.is_parked(h):
                        hosted.append(h)
                return True
            proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            u.EnumWindows(proto(cb), 0)
            if hosted:
                return False
            for pid in hosts:
                psutil.Process(pid).terminate()
            time.sleep(2.5)
            return bool(hosts)
        except Exception:
            return False

    def _close_window(self) -> None:
        with contextlib.suppress(Exception):
            if self.bg is not None:
                self.bg.__exit__(None, None, None)
            self.bg = None
        if self.hwnd:
            with contextlib.suppress(Exception):
                from core_organs.atlas import scanner as SC
                SC.close_owned(self.hwnd)
                time.sleep(2.0)
        self.hwnd = 0

    def _ready(self, timeout_s: float) -> bool:
        """True once the window shows several real controls (not just the title-bar buttons of a splash screen), read exactly as the recorder reads them."""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            with contextlib.suppress(Exception):
                img, origin = self.grab(stable=False)
                if img is not None and len([c for c in self.controls(origin, img.size) if not CHROME_RX.search(c["name"])]) >= 5:
                    return True
            if self.bg is not None and 2.5 < time.time() - t0 < 4.0:
                with contextlib.suppress(Exception):
                    self.bg.lay_out(settle_s=0.4)                   # one nudge at ~3 s                   # re-nudge the 1-px sliver: a window that has not laid itself out yet often does after another one
            time.sleep(1.0)
        return False

    def __exit__(self, *exc) -> bool:
        with contextlib.suppress(Exception):
            if self.bg is not None:
                self.bg.__exit__(None, None, None)
        if self.hwnd:
            with contextlib.suppress(Exception):
                from core_organs.atlas import scanner as SC
                SC.close_owned(self.hwnd)
                time.sleep(1.2)
        with contextlib.suppress(Exception):
            from core_organs import owned_guard as OG
            if getattr(self, "owned_pid", 0):
                OG.release(self.owned_pid)
        with contextlib.suppress(Exception):
            if self.guard is not None:
                self.guard.after()
        return False

    # ---------------------------------------------------------------- reading
    def grab(self, popups: bool = False, stable: bool = True):
        """(PIL image, screen origin) of the window's own surface, or (None, None). stable: grab again until two pictures 0.25 s apart agree (a first frame can be half painted: Notepad's editor came back
        black). popups: compose the app's open menus / flyouts / dialogs into the picture. A menu of a PARKED window opens at the nearest real-screen position, so it is first moved off-screen
        (background_window.keep_hidden), read from its own surface, and pasted under the control that opened it -- where the person would see it. Self.layers remembers where each one went."""
        from core_organs import background_window as bw, headless_input as hin
        from core_organs.professor import capture as CAP
        prev, out_origin = None, None
        for i in range(5 if stable else 1):
            main = CAP.grab_window(self.hwnd, isolated=True)
            if main is None:
                return None, None
            img = main.image.convert("RGB")
            self.layers = []
            if popups:
                with contextlib.suppress(Exception):
                    bw.keep_hidden(self.hwnd)
                for pw in hin.popup_windows(self.hwnd)[:4]:
                    pf = CAP.grab_window(pw, isolated=True)
                    if pf is None or pf.image.size[0] < 8 or pf.image.size[1] < 8:
                        continue
                    pimg = pf.image.convert("RGB")
                    px, py = pf.origin[0] - main.origin[0], pf.origin[1] - main.origin[1]
                    if not (0 <= px < img.width and 0 <= py < img.height):
                        ax, ay, aw, ah = getattr(self, "anchor", None) or (0, 0, 0, 0)
                        px, py = ax, ay + ah
                    px = max(0, min(px, img.width - pimg.width))
                    py = max(0, min(py, img.height - pimg.height))
                    img.paste(pimg, (px, py))
                    self.layers.append({"hwnd": pw, "origin": pf.origin, "paste": (px, py), "size": pimg.size})
            out_origin = main.origin
            if prev is not None and prev.size == img.size and not changed(prev, img, threshold=12, min_px=20)[0]:
                return img, out_origin
            prev = img
            time.sleep(0.25)
        return (prev, out_origin) if prev is not None else (None, None)

    def controls(self, origin: Tuple[int, int], size: Tuple[int, int], budget_s: float = 8.0) -> List[Dict[str, Any]]:
        """Actionable controls now on screen: {key, name, type, box (image pixels), ctl, popup}. Controls inside a composed popup are mapped through where it was pasted. Wall-clock capped (a UIA
        walk that has not finished in `budget_s` returns what it has: a hung app must not hang the recorder)."""
        import uiautomation as auto
        out, seen = [], set()
        t_end = time.time() + budget_s
        covered = [(l["paste"][0], l["paste"][1], l["size"][0], l["size"][1]) for l in getattr(self, "layers", [])]

        def take(c, ox: int, oy: int, popup: bool) -> None:
            if c.ControlTypeName not in ACTIONABLE:
                return
            name = (c.Name or "").strip()
            r = c.BoundingRectangle
            x, y, w, h = r.left - ox, r.top - oy, r.width(), r.height()
            if not name or w < 8 or h < 8 or x < 0 or y < 0 or x + w > size[0] or y + h > size[1]:
                return
            if c.IsOffscreen or not c.IsEnabled:                      # a greyed-out key does nothing: no change, no pair
                return
            if not popup and any(cx <= x + w / 2 <= cx + cw and cy <= y + h / 2 <= cy + ch for cx, cy, cw, ch in covered):
                return                                                # under a pasted menu: not reachable
            key = (c.ControlTypeName, name, round(x / 4), round(y / 4))
            if key in seen:
                return
            seen.add(key)
            out.append({"key": f"{c.ControlTypeName}|{name}", "name": name, "type": c.ControlTypeName, "box": (x, y, w, h), "ctl": c, "popup": popup})

        def walk(hwnd: int, ox: int, oy: int, popup: bool) -> None:
            try:                                               # a COMError mid-walk (a ribbon re-laying itself out) keeps what was read so far; the next pass reads again
                for c, _depth in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=9):
                    if time.time() > t_end:
                        return
                    try:
                        take(c, ox, oy, popup)
                    except Exception:
                        continue
            except Exception:
                pass
        walk(self.hwnd, origin[0], origin[1], False)
        for l in getattr(self, "layers", []):
            walk(l["hwnd"], l["origin"][0] - l["paste"][0], l["origin"][1] - l["paste"][1], True)
        return out

    # ---------------------------------------------------------------- acting (UIA patterns / posted messages; never physical input)
    @staticmethod
    def act(ctl) -> str:
        """Operate one control the way its own pattern says. Returns the pattern used, '' when none worked."""
        import threading
        import uiautomation as auto
        out = {"how": ""}

        def work() -> None:
            try:
                with auto.UIAutomationInitializerInThread():
                    for pid, meth in ((auto.PatternId.InvokePattern, "Invoke"), (auto.PatternId.SelectionItemPattern, "Select"), (auto.PatternId.TogglePattern, "Toggle"),
                                      (auto.PatternId.ExpandCollapsePattern, "Expand")):
                        try:
                            pat = ctl.GetPattern(pid)
                            if pat is None:
                                continue
                            getattr(pat, meth)()
                            out["how"] = meth
                            return
                        except Exception:
                            continue
            except Exception:
                return
        # MEASURED (OBS Studio): an Invoke on a button that opens a MODAL window does not return until that window is closed, so a plain call hangs the whole scan. The call runs on its own thread; if it is still
        # running after a moment the command was dispatched and opened something (the caller reads and closes that window, which also lets the thread finish).
        th = threading.Thread(target=work, daemon=True)
        th.start()
        th.join(2.5)
        if th.is_alive():
            return "Invoke (opened a modal window)"
        return out["how"]

    def chord(self, combo: str) -> bool:
        from core_organs import headless_input as hin
        ok, _note = hin.post_key_combo(self.hwnd, combo)
        return bool(ok)

    def _editor(self):
        """The main editing surface (a document, or an edit big enough to hold text) with a writable value, or None."""
        import uiautomation as auto
        best, area = None, 0
        for c, _d in auto.WalkControl(auto.ControlFromHandle(self.hwnd), maxDepth=9):
            try:
                if c.ControlTypeName not in ("DocumentControl", "EditControl") or c.IsOffscreen or not c.IsEnabled:
                    continue
                r = c.BoundingRectangle
                if r.width() * r.height() >= 40000 and r.height() >= 60 and r.width() * r.height() > area and c.GetValuePattern() is not None:
                    best, area = c, r.width() * r.height()
            except Exception:
                continue
        return best

    def type_text(self, text: str) -> bool:
        """Type into the editor through UIA's ValuePattern (XAML/WinUI apps ignore posted characters: measured on Notepad), then READ IT BACK: delivered is not the same as landed."""
        try:
            ed = self._editor()
            if ed is None:
                return False
            vp = ed.GetValuePattern()
            if vp.IsReadOnly:
                return False
            vp.SetValue((vp.Value or "") + text)
            return text in (ed.GetValuePattern().Value or "")
        except Exception:
            return False

    def clear_text(self) -> None:
        with contextlib.suppress(Exception):
            ed = self._editor()
            if ed is not None:
                ed.GetValuePattern().SetValue("")

    def close_popups(self) -> int:
        """Anything the app opened outside its main window (dialogs, flyouts) is closed again; returns how many windows were asked."""
        import ctypes
        from core_organs import headless_input as hin
        n = 0
        for w in hin.popup_windows(self.hwnd):
            ctypes.windll.user32.PostMessageW(w, 0x0010, 0, 0)
            n += 1
        return n


def _save_frame(img, root: str, app_key: str, tag: str) -> str:
    d = os.path.join(root, "frames", f"local_{app_key}")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{tag}.jpg")
    img.save(p, "JPEG", quality=90)
    return p


def _existing_pair_ids(out_jsonl: str) -> set:
    seen = set()
    if os.path.isfile(out_jsonl):
        for l in open(out_jsonl, encoding="utf-8"):
            with contextlib.suppress(Exception):
                seen.add(json.loads(l).get("meta", {}).get("pair_id"))
    return seen


def _v2_row(v1: Dict[str, Any], pre: Any, som: Dict[str, Any], controls: List[Dict[str, Any]], root: str, ppre: str) -> Dict[str, Any]:
    """A v1 pair re-issued in prompt format v2 (harvest.prompt_v2): the same picture, the same answer, plus zoomed crops of dense toolbar strips and a `Names:` line from the UIA control list."""
    import copy
    from . import prompt_v2 as P2
    names = P2.name_elements(som["elements"], controls)
    rel = os.path.relpath(ppre, root).replace("\\", "/")
    strips = P2.dense_strips(som["elements"], pre.size)
    refs = []
    for i, c in enumerate(P2.strip_crops(pre, strips)):
        p = ppre.replace("_pre.jpg", f"_strip{i}.jpg")
        c.save(p, "JPEG", quality=90)
        refs.append(os.path.relpath(p, root).replace("\\", "/"))
    goal = re.search(r"Goal: (.*)$", v1["messages"][1]["content"][-1]["text"], re.S).group(1)
    content, info = P2.user_content(pre, som, v1["meta"]["app_key"], goal, names=names, image_ref=rel, crop_refs=refs)
    row = copy.deepcopy(v1)
    row["messages"][1]["content"] = content
    row["meta"].update({"prompt_version": 2, "strips": info["n_crops"], "names": info["n_names"]})
    row["meta"].pop("controls_at_pre", None)
    return row


class AppCrashed(Exception):
    """The app under scan died while a control was being operated: the control is remembered (never operated again) and the scan can be resumed in a fresh instance."""

    def __init__(self, control: str, rep: Dict[str, Any]):
        super().__init__(f"the application ended when '{control}' was operated")
        self.control, self.rep = control, rep


def record_app(app_key: str, max_actions: int = 30, budget_s: float = 600.0, root: str = "", out_jsonl: str = "", som_fn: Optional[Callable[..., Dict[str, Any]]] = None,
               app: Optional[Any] = None, settle_s: float = 0.45, scan_delta: bool = True, nav_items: Optional[List[str]] = None, base_pass: bool = True,
               per_pass_actions: int = 0, spec_override: Optional[Dict[str, Any]] = None, rag_sink: bool = True, progress_path: str = "") -> Dict[str, Any]:
    """Drive one owned app and write pairs. `app` may be a stand-in with the OwnedApp interface (tests). Returns a report with every reason an action did NOT become a pair."""
    from . import video_explain as VE, video_pipeline as VP
    from core_organs import safety_guard as SG
    spec = spec_override or APPS[app_key]                              # a catalogue app has no hand-written entry: {'launch': <name>} is enough, its menus are found on the screen
    som_fn = som_fn or VP.som_of_frame
    extra_deny = re.compile(spec["deny"], re.I) if spec.get("deny") else None

    persist: Dict[str, Any] = {"done": [], "blocked": []}
    if progress_path and os.path.isfile(progress_path):
        with contextlib.suppress(Exception):
            persist = json.load(open(progress_path, encoding="utf-8"))
    done_before, blocked = set(persist.get("done", [])), set(persist.get("blocked", []))     # done_before = what EARLIER runs finished (skipped now); this run's own later passes (typed text, other layouts) repeat controls on purpose
    persist_done = set(done_before)

    def save_progress() -> None:
        if progress_path:
            with contextlib.suppress(Exception):
                os.makedirs(os.path.dirname(progress_path), exist_ok=True)
                json.dump({"done": sorted(persist_done), "blocked": sorted(blocked)}, open(progress_path, "w", encoding="utf-8"))

    def unsafe(name: str) -> bool:
        if name in blocked:                                              # operating it ended the app once: never again
            return True
        return (not SG.is_safe(name)) or bool(DENY_RX.search(name)) or _personal(name) or volatile(name) or bool(extra_deny and extra_deny.search(name))

    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    seen_ids = _existing_pair_ids(out_jsonl)
    rep: Dict[str, Any] = {"app": app_key, "actions": 0, "pairs": 0, "no_change": 0, "not_delivered": 0, "no_grounding": 0, "skipped_unsafe": 0, "duplicates": 0, "popups_closed": 0, "child_windows": [],
                           "by_action": {"click": 0, "hotkey": 0, "type": 0}, "seconds": 0.0, "errors": []}
    plog = None
    if rag_sink:                                                         # what is scanned fills the RAG as it is scanned: icon vault (Sub-RAG 1), UI graph (2), lexicon -- not only the training file
        with contextlib.suppress(Exception):
            from core_organs import artist_memory as AM, rag as _RAG
            plog = AM.PaintLogger(_RAG.get_rag(), app_key=app_key, write_pairs=False, run_id=f"scan-{app_key}-{int(time.time())}")
    rows: List[Dict[str, Any]] = []
    v2_rows: List[Dict[str, Any]] = []
    t0 = time.time()
    done_keys: set = set()
    own = app is None
    ctx = OwnedApp(spec["launch"]) if own else contextlib.nullcontext(app)
    tmr: Dict[str, float] = {}

    def timed(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def w(*args: Any, **kw: Any) -> Any:
            t_ = time.time()
            try:
                return fn(*args, **kw)
            finally:
                tmr[name] = tmr.get(name, 0.0) + time.time() - t_
        return w
    som_fn = timed("som_scan", som_fn)
    _real_sleep = time.sleep

    def _counting_sleep(sec: float) -> None:                          # every deliberate wait is counted: a scan's time is either work or waiting, and both are reported
        tmr["sleep"] = tmr.get("sleep", 0.0) + max(0.0, float(sec))
        _real_sleep(sec)
    time.sleep = _counting_sleep
    _cw_orig = {n: getattr(CW, n) for n in ("snapshot", "new_windows", "describe", "dismiss", "probe_items")}
    for _n, _f in _cw_orig.items():
        setattr(CW, _n, timed("child_windows." + _n, _f))
    with ctx as a:
        for _m in ("controls", "grab", "act", "close_popups", "chord"):         # where the time goes: every phase of a scan is timed and reported (rep['timing_s'])
            if hasattr(a, _m):
                setattr(a, _m, timed(_m, getattr(a, _m)))
        rep["mode"] = getattr(a, "mode", "")
        n_frame = [0]

        last_origin: List[Any] = [None]

        def snap(tag: str):
            img_, org_ = a.grab(popups=True)                            # what is open (a menu, a dialog) is part of the picture, before and after
            last_origin[0] = org_
            return img_, org_

        def emit(pre, post, kind: str, goal: str, target_box, actions_fn, meta: Dict[str, Any]) -> bool:
            """Write one pair: SoM on the pre frame, the target by overlap, the delta from the pictures. Returns True when a row was kept."""
            n_frame[0] += 1
            stamp = hashlib.sha1((app_key + goal + str(n_frame[0]) + str(time.time())).encode()).hexdigest()[:10]
            ppre, ppost = _save_frame(pre, root, app_key, f"{stamp}_pre"), _save_frame(post, root, app_key, f"{stamp}_post")
            ok_change, bbox = changed(pre, post)
            som = som_fn(ppre)
            el = element_at(som, target_box) if target_box else None
            if target_box and el is None:
                rep["no_grounding"] += 1
                for p in (ppre, ppost):
                    with contextlib.suppress(Exception):
                        os.remove(p)
                return False
            expectation = f"the screen changes in the region {list(bbox)}" if bbox else "the screen changes"
            if scan_delta and bbox:
                names_pre = {x["name"] for x in (meta.get("controls_at_pre") or [])}
                done_by_uia = False
                if names_pre and last_origin[0] is not None:             # what is new on screen, read from the UIA control names (exact, ~0.2 s) instead of a second OCR scan of the picture (~5 s)
                    with contextlib.suppress(Exception):
                        post_names = [c["name"] for c in a.controls(last_origin[0], post.size) if c["name"] not in names_pre and not CHROME_RX.search(c["name"])]
                        if post_names:
                            expectation = "new on screen: " + ", ".join(dict.fromkeys(post_names[:8]))
                        done_by_uia = True
                if not done_by_uia:
                    sub = som_fn(ppost, region=bbox)
                    names = VE.clean_labels(sub["elements"])
                    if names:
                        expectation = "new on screen: " + ", ".join(names)
            pair_id = hashlib.sha1(f"{app_key}|{goal}|{hashlib.sha1(pre.tobytes()).hexdigest()}".encode()).hexdigest()[:16]
            if pair_id in seen_ids:
                rep["duplicates"] += 1
                return False
            seen_ids.add(pair_id)
            ev = {"t": round(time.time() - t0, 2), "pre": ppre, "post": ppost, "bbox": list(bbox) if bbox else None}
            rows.append(VE.build_row(root, app_key, f"local_{app_key}", ev, som, goal, actions_fn(el["id"] if el else None, expectation), pair_id, True, True,
                                     dict(meta, source="local_uia", source_ref=f"local_{app_key}@{stamp}")))
            rep["pairs"] += 1
            rep["by_action"][kind] += 1
            with contextlib.suppress(Exception):                        # written NOW: a scan that is cut off later keeps everything it has learned so far
                with open(out_jsonl, "a", encoding="utf-8") as _f:
                    _row = dict(rows[-1])
                    _row["meta"] = {k: v for k, v in rows[-1]["meta"].items() if k != "controls_at_pre"}
                    _f.write(json.dumps(_row, ensure_ascii=False) + "\n")
            if plog is not None:
                with contextlib.suppress(Exception):
                    cb = target_box
                    if cb and meta.get("uia_name"):
                        plog.hook({"kind": kind, "name": meta["uia_name"], "type": meta.get("uia_type", "ButtonControl"), "box": tuple(cb), "pre": pre, "post": post,
                                   "controls": [{"name": x["name"], "type": "ButtonControl"} for x in (meta.get("controls_at_pre") or [])], "origin": (0, 0)})
            if meta.get("controls_at_pre"):
                with contextlib.suppress(Exception):
                    _v2 = _v2_row(rows[-1], pre, som, meta["controls_at_pre"], root, ppre)      # the same pair in prompt format v2: zoomed strips + the control names UIA gave
                    with open(out_jsonl.replace(".jsonl", "_v2.jsonl"), "a", encoding="utf-8") as _f2:
                        _f2.write(json.dumps(_v2, ensure_ascii=False) + "\n")
                    rep["pairs_v2"] = rep.get("pairs_v2", 0) + 1
                rows[-1]["meta"].pop("controls_at_pre", None)                                                # the v1 row stays as it was: no control list in it
            return True

        def settle_and_tidy(extra: float = 0.0):
            time.sleep(settle_s + extra)
            rep["popups_closed"] += a.close_popups()
            if rep["actions"] % 10 == 0 and rep.get("_last_print") != rep["actions"]:
                rep["_last_print"] = rep["actions"]
                print(f"[scan] {app_key}: actions={rep['actions']} pairs={rep['pairs']} t={time.time() - t0:.0f}s timing={ {k: round(v) for k, v in tmr.items()} }", file=sys.stderr, flush=True)

        # ---------------------------------------------------------------- hotkeys FIRST, from the app's fresh state (measured: Calculator's Alt+2 stopped landing after a UIA click), each chord then its undo
        for entry in spec["chords"]:
            keys, desc, undo = entry
            if time.time() - t0 >= budget_s:
                break
            pre, origin = snap("pre")
            if pre is None or not a.chord(keys):
                rep["not_delivered"] += 1
                continue
            rep["actions"] += 1
            settle_and_tidy(0.9)                                        # a mode switch animates: the picture is only the "after" once it has stopped moving
            post, _o = snap("post")
            if not changed(pre, post)[0]:
                rep["no_change"] += 1
            else:
                emit(pre, post, "hotkey", desc, None,
                     lambda tid, exp, k=keys: [{"step": 1, "action": "hotkey", "target_id": None, "hotkey": k, "text": None, "verify_expectation": exp}],
                     {"uia_name": keys, "uia_type": "hotkey", "pattern": "posted_keys"})
            a.chord(undo)
            settle_and_tidy()

        # ---------------------------------------------------------------- clicks: every safe control, once each, in every mode the app has (a Scientific or Programmer layout is a different picture)
        def click_control(c: Dict[str, Any], tidy: bool = True, keep_open: bool = False, ctrls: Optional[List[Dict[str, Any]]] = None) -> bool:
            """Operate one control through its UIA pattern; a pair when the picture changed. Returns True when it did."""
            rep["actions"] += 1
            pre, _origin = snap("pre")
            a.anchor = c["box"]                                         # a menu this control opens is pasted just under it
            with contextlib.suppress(Exception):
                kids_before = CW.snapshot(a.hwnd)
            how = a.act(c["ctl"])
            if pre is None or not how:
                rep["not_delivered"] += 1
                return False
            keep = keep_open or c["name"] in spec.get("stay", ())       # a control that REVEALS more interface (a menu header, Paint's 'Show toolbar'): what it opened stays open
            if keep:
                time.sleep(settle_s + 0.6)
            else:
                settle_and_tidy()
            if getattr(a, "hwnd", 0):
                import ctypes as _ct
                if not _ct.windll.user32.IsWindow(a.hwnd):               # the window is gone: operating this control ended the application (MEASURED: OBS's audio mixer control crashes it through UI Automation)
                    blocked.add(c["name"])
                    save_progress()
                    rep["crashed_on"] = rep.get("crashed_on", []) + [c["name"]]
                    raise AppCrashed(c["name"], rep)
            kid_info = None
            crash_hit = None
            with contextlib.suppress(Exception):                        # did this control open another WINDOW? (a deep section: its own controls, its own way out)
                for kid in CW.new_windows(kids_before, a.hwnd):
                    if re.search(r"crash|has stopped|stopped working|stopped responding|unhandled|fatal", kid["title"], re.I):
                        crash_hit = kid                                 # the app's own crash reporter: it keeps the main window alive while it shows
                        break
                    detail = CW.describe(kid["hwnd"])
                    generic = kid["title"].strip().lower() in ("", "pop-uphost", "pop-up", "popup")
                    if detail["n_controls"] == 0 and (generic or kid["kind"] != "dialog"):
                        continue                                        # an empty popup host (WinUI keeps them around) is not a window with content; a titled dialog whose controls UIA cannot read still is
                    if (not keep and kid["kind"] in ("menu", "window") and detail["n_controls"] >= 1 and rep.get("deep_probes", 0) < 40 and time.time() - t0 < budget_s * 0.8
                            and not any(e["opener"].startswith(c["name"] + " >") for e in rep["child_windows"])):
                        sub_entries = CW.probe_items(a, c["ctl"], c["name"], kid, detail, unsafe, max_items=8)       # one level deeper: the dialogs this menu's items open
                        rep["deep_probes"] = rep.get("deep_probes", 0) + len(sub_entries)
                        for se in sub_entries:
                            if not any(e["opener"] == se["opener"] and e["child_title"] == se["child_title"] for e in rep["child_windows"]):
                                rep["child_windows"].append(se)
                    closed = "left open" if keep else CW.dismiss(kid["hwnd"], a) if kid["kind"] != "menu" else "menu"
                    ent = CW.entry(c, kid, detail, closed)
                    if not any(e["opener"] == ent["opener"] and e["child_title"] == ent["child_title"] for e in rep["child_windows"]):
                        rep["child_windows"].append(ent)
                        with contextlib.suppress(Exception):             # registered the moment it is found, not at the end of the scan
                            from core_organs import rag as _R2
                            CW.register(_R2.get_rag(), app_key, [ent], root)
                    kid_info = kid_info or {"title": kid["title"], "kind": kid["kind"], "n_controls": detail["n_controls"]}
            if crash_hit is not None:
                with contextlib.suppress(Exception):
                    CW.dismiss(crash_hit["hwnd"], a)
                blocked.add(c["name"])
                save_progress()
                rep["crashed_on"] = rep.get("crashed_on", []) + [c["name"]]
                raise AppCrashed(c["name"], rep)
            post, _o = snap("post")
            if post is None or not changed(pre, post)[0]:
                if kid_info is not None:
                    rep["no_change_but_child_window"] = rep.get("no_change_but_child_window", 0) + 1
                rep["no_change"] += 1
                return False
            emit(pre, post, "click", goal_for(c["name"], c["type"]), c["box"],
                 lambda tid, exp: [{"step": 1, "action": "click", "target_id": tid, "hotkey": None, "text": None, "verify_expectation": exp}],
                 dict({"uia_name": c["name"], "uia_type": c["type"], "pattern": how}, **({"opens_child_window": kid_info} if kid_info else {}), **({"controls_at_pre": [{"name": x["name"], "box": list(x["box"])} for x in ctrls[:400]]} if ctrls else {})))
            if tidy and not keep:
                a.chord("esc")                                          # a menu/flyout this click opened is closed again so the next control is reachable from a known state
                settle_and_tidy()
            return True

        def find_control(name: str) -> Optional[Dict[str, Any]]:
            img, origin = snap("pre")
            if img is None:
                return None
            return next((c for c in a.controls(origin, img.size) if c["name"].lower() == name.lower()), None)

        def click_pass(limit: int) -> None:
            stop_at = rep["actions"] + limit
            done_keys.clear()
            done_keys.update(done_before)                                # controls an earlier run (or the run before a crash) already did are not done again
            stalls = 0
            while rep["actions"] < stop_at and time.time() - t0 < budget_s and stalls < 3:
                pre, origin = snap("pre")
                if pre is None:
                    rep["errors"].append("no frame")
                    break
                pick = None
                ctrls = a.controls(origin, pre.size)                    # every control UIA names on this very screen: the 'Names:' line of a v2 prompt
                for c in ctrls:
                    if c["key"] in done_keys or CHROME_RX.search(c["name"]):
                        continue
                    if unsafe(c["name"]):
                        done_keys.add(c["key"])
                        rep["skipped_unsafe"] += 1
                        continue
                    pick = c
                    break
                if pick is None:
                    stalls += 1
                    a.chord("esc")
                    time.sleep(settle_s)
                    continue
                stalls = 0
                done_keys.add(pick["key"])
                persist_done.add(pick["key"])
                if len(persist_done) % 5 == 0:
                    save_progress()
                click_control(pick, ctrls=ctrls)

        def navigate(opener: str, item: str) -> bool:
            """The app's own navigation, as the person would use it: open the pane, pick the entry. Both clicks are pairs."""
            o = find_control(opener)
            if o is None or not click_control(o, tidy=False):
                return False
            it = find_control(item)
            return it is not None and click_control(it, tidy=False)

        def menu_pass(opener: str, limit: int) -> None:
            """Open a menu / flyout, click each safe item in it (re-opening the menu for the next one): the header, every item, and the dialog an item opens are all pairs."""
            tried: set = set()
            for _ in range(limit):
                if time.time() - t0 >= budget_s:
                    return
                head = find_control(opener)
                if head is None or head.get("popup"):
                    return
                if not click_control(head, tidy=False, keep_open=True):
                    return
                img, origin = snap("pre")
                if img is None:
                    return
                items = [c for c in a.controls(origin, img.size) if c.get("popup") and c["key"] not in tried and not CHROME_RX.search(c["name"])]
                pick = None
                for c in items:
                    if unsafe(c["name"]):
                        tried.add(c["key"])
                        rep["skipped_unsafe"] += 1
                        continue
                    pick = c
                    break
                if pick is None:
                    a.chord("esc")
                    settle_and_tidy()
                    return
                tried.add(pick["key"])
                click_control(pick, tidy=False)
                settle_and_tidy()                                       # an item that opened a dialog: closed again; a menu that stayed open: closed

        menus = list(spec.get("menus") or [])
        if not menus:                                                    # the menu bar of an unknown app: the menu items in the top strip of the window
            with contextlib.suppress(Exception):
                img0, org0 = snap("pre")
                if img0 is not None:
                    menus = [c["name"] for c in a.controls(org0, img0.size) if c["type"] == "MenuItemControl" and c["box"][1] < 90 and not unsafe(c["name"]) and not CHROME_RX.search(c["name"])][:8]
            rep["menus_found"] = menus
        for opener in menus:
            if time.time() - t0 < budget_s:
                menu_pass(opener, max(3, max_actions // 2))
        nav = dict(spec["nav"]) if spec.get("nav") else None
        if nav and nav_items is not None:
            nav["items"] = list(nav_items)                              # a run can take a slice of the app's modes (one foreground run must stay under the tool's time limit)
        per_pass = per_pass_actions or max(1, max_actions // ((1 if base_pass else 0) + (len(nav["items"]) if nav else 0) or 1))
        if base_pass:
            click_pass(per_pass)
        for item in (nav["items"] if nav else []):
            if time.time() - t0 >= budget_s:
                break
            if navigate(nav["open"], item):
                settle_and_tidy(1.0)
                click_pass(per_pass)
            else:
                rep["mode_not_entered"] = rep.get("mode_not_entered", 0) + 1
            navigate(nav["open"], nav["home"])                          # back to the layout the next entry starts from
            settle_and_tidy(1.0)

        # ---------------------------------------------------------------- typing into the document
        if spec.get("type"):
            pre, origin = snap("pre")
            text = spec["type"]
            if pre is not None and a.type_text(text):
                rep["actions"] += 1
                settle_and_tidy()
                post, _o = snap("post")
                if not changed(pre, post)[0]:
                    rep["no_change"] += 1
                else:
                    emit(pre, post, "type", f"Type '{text}'", None,
                         lambda tid, exp: [{"step": 1, "action": "type", "target_id": tid, "hotkey": None, "text": text, "verify_expectation": exp}],
                         {"uia_name": "document", "uia_type": "type", "pattern": "posted_chars"})
                if time.time() - t0 < budget_s and rep["actions"] < max_actions * 2:
                    click_pass(max(1, max_actions // 3))                # a document WITH text is another state: controls that were inert on an empty page now act
                a.clear_text()                                          # the throw-away document is emptied again
                settle_and_tidy()
        rep["seconds"] = round(time.time() - t0, 1)
        save_progress()
        rep["timing_s"] = {k: round(v, 1) for k, v in tmr.items()}
        time.sleep = _real_sleep
        for _n, _f in _cw_orig.items():
            setattr(CW, _n, _f)
    if rep["child_windows"]:
        with contextlib.suppress(Exception):
            try:
                from core_organs import rag as _RAG
                _rg = _RAG.get_rag()
            except Exception:
                _rg = None
            rep["child_windows_registered"] = CW.register(_rg, app_key, rep["child_windows"], root)
    rep.pop("_last_print", None)
    rep["jsonl_v2"] = out_jsonl.replace(".jsonl", "_v2.jsonl")
    rep["jsonl"] = out_jsonl
    return rep


def run_local(apps: Optional[List[str]] = None, max_actions: int = 30, budget_s: float = 600.0, sizes: Optional[List[Tuple[int, int]]] = None, **kw: Any) -> Dict[str, Any]:
    """Record every listed app in turn. A failure to start one app is reported and the rest still run. `sizes` = window sizes to lay each app out at (responsive layouts move and re-style every control, so
    each size is a set of NEW pictures of the same controls; pair ids hash the picture, so nothing is counted twice)."""
    from core_organs import background_window as bw
    out: Dict[str, Any] = {"apps": {}}
    for sz in (sizes or [None]):
        bw.PARK_SIZE = tuple(sz) if sz else None
        for k in (apps or list(APPS)):
            tag = k if not sz else f"{k}@{sz[0]}x{sz[1]}"
            if k not in APPS:
                out["apps"][tag] = {"error": "unknown app (known: " + ", ".join(APPS) + ")"}
                continue
            try:
                out["apps"][tag] = record_app(k, max_actions=max_actions, budget_s=budget_s, **kw)
            except Exception as exc:
                out["apps"][tag] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            print("[local_scale]", tag, {a: b for a, b in out["apps"][tag].items() if a in ("pairs", "actions", "seconds", "error")}, flush=True)
    bw.PARK_SIZE = None
    out["pairs"] = sum(v.get("pairs", 0) for v in out["apps"].values())
    return out
