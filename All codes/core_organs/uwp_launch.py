"""
uwp_launch -- visible launch of packaged (UWP / WinUI) apps, then (only then) parking.

A packaged app that is started and parked off-screen straight away stays CLOAKED (its splash never finishes: Sticky Notes
never starts). So: activate it through the shell, wait on the screen until DWM says it is not cloaked and its frame has a
UIA body, and after that the window stays on screen, never activated (a parked packaged app stops drawing - measured), and is operated through UIA
patterns only. `park=True` is an opt-in: it parks, re-checks, and brings the window back if parking cloaked it.

    aumid_for(name)            -> 'Package.Family!App' | ''   looked up in Get-StartApps (cached in data/uwp_aumids.json), nothing hard-coded
    launch_visible(name)       -> {'hwnd','pid','aumid','seconds','cloaked','parked','error'}
    own_pids / kill_launched   only the processes this module started are ever ended (by PID)
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Set

from core_organs import headless_input as hin

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
CACHE = os.path.join(DATA, "uwp_aumids.json")
_user32 = ctypes.windll.user32
_STARTED: Set[int] = set()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _load() -> Dict[str, str]:
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {}


def _start_apps() -> Dict[str, str]:
    """{display name: AppID} from Get-StartApps (the shell's own list of launchable apps)."""
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                             capture_output=True, text=True, timeout=40).stdout
        rows = json.loads(out or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        return {r["Name"]: r["AppID"] for r in rows if r.get("Name") and r.get("AppID")}
    except Exception:
        return {}


def aumid_for(name: str) -> str:
    """The AppUserModelID of an installed app named like `name` (exact name first, then whole-word containment); '' when none."""
    if "!" in name:
        return name
    cache = _load()
    n = _norm(name)
    if n in cache:
        return cache[n]
    apps = _start_apps()
    best = ""
    for disp, aid in apps.items():
        if _norm(disp) == n:
            best = aid
            break
    if not best:
        hits = [(len(_norm(d)), aid) for d, aid in apps.items() if n and (f" {n} " in f" {_norm(d)} " or f" {_norm(d)} " in f" {n} ")]
        best = min(hits)[1] if hits else ""
    if best and "!" in best:
        cache[n] = best
        os.makedirs(DATA, exist_ok=True)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=1)
    return best if "!" in best else ""


def _frames() -> Dict[int, str]:
    out: Dict[int, str] = {}
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def each(h, _l):
        if hin._class_name(h) == "ApplicationFrameWindow":
            out[int(h)] = hin.safe_window_text(h)
        return True
    _user32.EnumWindows(cb(each), 0)
    return out


def _has_body(hwnd: int) -> bool:
    """The frame's UIA tree holds more than the title bar (the app's content has been created)."""
    try:
        import uiautomation as auto
        c = auto.ControlFromHandle(hwnd)
        n = 0
        for _ctl, depth in auto.WalkControl(c, maxDepth=4):
            n += 1
            if n > 8:
                return True
        return False
    except Exception:
        return True


def launch_visible(name: str, timeout_s: float = 30.0, park: bool = False) -> Dict[str, Any]:
    t0 = time.time()
    res: Dict[str, Any] = {"hwnd": 0, "pid": 0, "aumid": "", "seconds": 0.0, "cloaked": True, "parked": False, "error": ""}
    aumid = aumid_for(name)
    res["aumid"] = aumid
    if not aumid:
        res["error"] = f"no installed packaged app named '{name}'"
        return res
    before = _frames()
    existing = {h for h, t in before.items() if _norm(name) in _norm(t)}
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aumid}"])
    end = t0 + timeout_s
    target = 0
    while time.time() < end:
        now = _frames()
        cands = [h for h, t in now.items() if _norm(name) in _norm(t) and hin.is_alive(h)]
        fresh = [h for h in cands if h not in existing] or cands
        for h in fresh:
            if not hin.is_cloaked(h) and _has_body(h):
                target = h
                break
        if target:
            break
        time.sleep(0.5)
    if not target:
        res["error"] = "window never became visible (still cloaked or empty)"
        res["seconds"] = round(time.time() - t0, 1)
        return res
    res.update(hwnd=target, pid=hin.window_pid(target), cloaked=False)
    _STARTED.add(res["pid"])
    if park and hin.offscreen_enabled():
        hin.park_offscreen(target)
        time.sleep(0.6)
        if hin.is_cloaked(target):                       # parking cloaked it: bring it back rather than lose the app
            hin.release_isolation(target)
            _user32.ShowWindow(target, 4)                # SW_SHOWNOACTIVATE
            res["parked"] = False
        else:
            res["parked"] = True
    res["seconds"] = round(time.time() - t0, 1)
    return res


def kill_launched() -> List[int]:
    """End the processes this module started (by PID only)."""
    done: List[int] = []
    for pid in list(_STARTED):
        try:
            import psutil
            psutil.Process(pid).kill()
            done.append(pid)
        except Exception:
            pass
        _STARTED.discard(pid)
    return done
