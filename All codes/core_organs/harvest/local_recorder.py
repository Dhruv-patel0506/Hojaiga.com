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
                     r"recent|browse|email|send|delete|remove|erase|reset|clear history|license|privacy|update|window|sign(ed)?|log ?(in|out)|profile|hide|copy|cut|paste|focus|spotify|microsoft to do|bing|online|web)\b", re.I)
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
        t = LN.resolve(self.name)
        self.guard = SPT.StateGuard(self.name, t.appid)
        self.guard.before()
        last = ""
        for attempt in range(1):                                    # ONE attempt, 8 s wall clock: a window still on its splash screen is killed and the app skipped. A UWP window parked off-screen sometimes never leaves its splash (measured: Calculator, Clock): end it and start over
            info = LN.launch_owned(t, self.guard)
            self.hwnd = int(info.get("hwnd") or 0)
            self.notes = list(info.get("notes") or [])
            if not (info.get("launched") and self.hwnd):
                last = f"could not start: {info.get('trace') or self.notes}"
                print(f"[local_recorder] {self.name}: attempt {attempt + 1} did not start: {last[:300]}", file=sys.stderr, flush=True)
                continue
            self.bg = bw.BackgroundSession(self.hwnd)
            self.bg.__enter__()
            self.bg.lay_out()
            self.mode = self.bg.mode
            time.sleep(1.0)
            if self._ready(8.0):
                return self
            last = f"the window never showed a usable interface (a splash screen; mode={self.mode})"
            self._close_window()
            restarted = self._restart_idle_frame_host()
            print(f"[local_recorder] {self.name}: attempt {attempt + 1} stayed on its splash screen; frame host restarted={restarted}", file=sys.stderr, flush=True)
        self.__exit__(None, None, None)
        raise RuntimeError(f"{self.name}: {last}")

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
        import uiautomation as auto
        for pid, meth in ((auto.PatternId.InvokePattern, "Invoke"), (auto.PatternId.SelectionItemPattern, "Select"), (auto.PatternId.TogglePattern, "Toggle"),
                          (auto.PatternId.ExpandCollapsePattern, "Expand")):
            try:
                pat = ctl.GetPattern(pid)
                if pat is None:
                    continue
                getattr(pat, meth)()
                return meth
            except Exception:
                continue
        return ""

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


def record_app(app_key: str, max_actions: int = 30, budget_s: float = 600.0, root: str = "", out_jsonl: str = "", som_fn: Optional[Callable[..., Dict[str, Any]]] = None,
               app: Optional[Any] = None, settle_s: float = 0.45, scan_delta: bool = True, nav_items: Optional[List[str]] = None, base_pass: bool = True,
               per_pass_actions: int = 0) -> Dict[str, Any]:
    """Drive one owned app and write pairs. `app` may be a stand-in with the OwnedApp interface (tests). Returns a report with every reason an action did NOT become a pair."""
    from . import video_explain as VE, video_pipeline as VP
    from core_organs import safety_guard as SG
    spec = APPS[app_key]
    som_fn = som_fn or VP.som_of_frame
    extra_deny = re.compile(spec["deny"], re.I) if spec.get("deny") else None

    def unsafe(name: str) -> bool:
        return (not SG.is_safe(name)) or bool(DENY_RX.search(name)) or _personal(name) or volatile(name) or bool(extra_deny and extra_deny.search(name))

    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    seen_ids = _existing_pair_ids(out_jsonl)
    rep: Dict[str, Any] = {"app": app_key, "actions": 0, "pairs": 0, "no_change": 0, "not_delivered": 0, "no_grounding": 0, "skipped_unsafe": 0, "duplicates": 0, "popups_closed": 0,
                           "by_action": {"click": 0, "hotkey": 0, "type": 0}, "seconds": 0.0, "errors": []}
    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    done_keys: set = set()
    own = app is None
    ctx = OwnedApp(spec["launch"]) if own else contextlib.nullcontext(app)
    with ctx as a:
        rep["mode"] = getattr(a, "mode", "")
        n_frame = [0]

        def snap(tag: str):
            return a.grab(popups=True)                                  # what is open (a menu, a dialog) is part of the picture, before and after

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
            return True

        def settle_and_tidy(extra: float = 0.0):
            time.sleep(settle_s + extra)
            rep["popups_closed"] += a.close_popups()

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
        def click_control(c: Dict[str, Any], tidy: bool = True, keep_open: bool = False) -> bool:
            """Operate one control through its UIA pattern; a pair when the picture changed. Returns True when it did."""
            rep["actions"] += 1
            pre, _origin = snap("pre")
            a.anchor = c["box"]                                         # a menu this control opens is pasted just under it
            how = a.act(c["ctl"])
            if pre is None or not how:
                rep["not_delivered"] += 1
                return False
            keep = keep_open or c["name"] in spec.get("stay", ())       # a control that REVEALS more interface (a menu header, Paint's 'Show toolbar'): what it opened stays open
            if keep:
                time.sleep(settle_s + 0.6)
            else:
                settle_and_tidy()
            post, _o = snap("post")
            if post is None or not changed(pre, post)[0]:
                rep["no_change"] += 1
                return False
            emit(pre, post, "click", goal_for(c["name"], c["type"]), c["box"],
                 lambda tid, exp: [{"step": 1, "action": "click", "target_id": tid, "hotkey": None, "text": None, "verify_expectation": exp}],
                 {"uia_name": c["name"], "uia_type": c["type"], "pattern": how})
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
            stalls = 0
            while rep["actions"] < stop_at and time.time() - t0 < budget_s and stalls < 3:
                pre, origin = snap("pre")
                if pre is None:
                    rep["errors"].append("no frame")
                    break
                pick = None
                for c in a.controls(origin, pre.size):
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
                click_control(pick)

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

        for opener in spec.get("menus", []):
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
    if rows:
        with open(out_jsonl, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rep["jsonl"] = out_jsonl
    return rep


def run_local(apps: Optional[List[str]] = None, max_actions: int = 30, budget_s: float = 600.0, **kw: Any) -> Dict[str, Any]:
    """Record every listed app in turn. A failure to start one app is reported and the rest still run."""
    out: Dict[str, Any] = {"apps": {}}
    for k in (apps or list(APPS)):
        if k not in APPS:
            out["apps"][k] = {"error": "unknown app (known: " + ", ".join(APPS) + ")"}
            continue
        try:
            out["apps"][k] = record_app(k, max_actions=max_actions, budget_s=budget_s, **kw)
        except Exception as exc:
            out["apps"][k] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    out["pairs"] = sum(v.get("pairs", 0) for v in out["apps"].values())
    return out
