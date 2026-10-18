"""
professor.launcher -- START AN OWNED INSTANCE OF ANY APPLICATION, from its name alone.

Nothing in here knows an application. The name is resolved the way the system resolves it (Start-menu entry -> launch id or program path), the program is classified from what is on disk
(a Chromium browser, an Electron app, anything else), and the launch recipe follows from that CLASS:

  packaged / classic app   professor.state_protect guards the application's own session state, then the engine's hidden launcher starts it minimized and unfocused
  Chromium browser         a throw-away profile directory + a debugging port on 127.0.0.1 (the DevTools route, professor.adapters) + accessibility on; opens one blank window
  Electron app             the same flags without the browser-only ones (an Electron shell is a Chromium page host)
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import state_protect as SPT

CHROMIUM_BROWSER_EXES = ("chrome", "msedge", "brave", "vivaldi", "opera", "chromium", "arc", "yandex")


@dataclass
class Target:
    name: str
    display: str = ""
    appid: str = ""
    exe: str = ""
    packaged: bool = False
    chromium: str = ""                       # '' | 'browser' | 'electron'
    notes: List[str] = field(default_factory=list)


def chromium_kind(exe: str) -> str:
    """'browser' / 'electron' / '' from the program on disk: a browser by its image name; an Electron shell by its resources (app.asar) or its Chromium runtime files beside it."""
    if not exe or not os.path.isfile(exe):
        return ""
    base = os.path.splitext(os.path.basename(exe))[0].lower()
    if any(base.startswith(b) for b in CHROMIUM_BROWSER_EXES):
        return "browser"
    d = os.path.dirname(exe)
    names = {n.lower() for n in os.listdir(d)} if os.path.isdir(d) else set()

    def _has_app(root: str) -> bool:
        return os.path.isfile(os.path.join(root, "resources", "app.asar")) or os.path.isdir(os.path.join(root, "resources", "app"))
    if "resources" in names and _has_app(d):
        return "electron"
    # some shells keep their resources one versioned folder below the exe (<exe dir>\<hash or version>\resources\app); only a folder NAMED like a build hash / version
    # counts - an exe sitting in a general folder (a drive root) has other applications' folders beside it
    if os.path.isdir(d) and any(re.fullmatch(r"[0-9a-f]{7,40}|v?\d+(\.\d+){1,3}", n, re.I) and os.path.isdir(os.path.join(d, n)) and _has_app(os.path.join(d, n)) for n in os.listdir(d)):
        return "electron"
    if {"chrome_100_percent.pak", "icudtl.dat"} <= names or "libcef.dll" in names:
        return "electron"
    return ""


def resolve(name: str, exe_hint: str = "") -> Target:
    from core_organs import universal_scan as us
    from core_organs.atlas import scanner as SC
    t = Target(name=name)
    app = us.resolve_app(name)
    if app:
        t.display, t.appid = app
    exe = exe_hint
    if not exe and t.appid and re.search(r"\.exe$", t.appid, re.I) and os.path.isfile(t.appid):
        exe = t.appid
    if not exe:
        exe = SC.resolve_installed(t.display or name)
    t.exe = exe or ""
    t.packaged = bool(SPT.package_family_of(t.appid))
    t.chromium = chromium_kind(t.exe)
    return t


def _chromium_args(t: Target, user_dir: str, port: int) -> List[str]:
    args = [t.exe, f"--user-data-dir={user_dir}", f"--remote-debugging-port={port}", "--remote-allow-origins=*", "--force-renderer-accessibility", "--disable-features=CalculateNativeWinOcclusion"]
    if t.chromium == "browser":
        args += ["--no-first-run", "--no-default-browser-check", "--disable-sync", "--new-window", "about:blank"]
    return args


def launch_owned(t: Target, guard: SPT.StateGuard, timeout_s: float = 40.0, exe: str = "", args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Start an instance and return {launched, hwnd, title, notes, cdp_port?}. Windows that existed before the launch are never adopted."""
    from core_organs import universal_scan as us, background_window as bw
    if t.chromium:
        from .adapters.cdp import free_port
        port = free_port()
        user_dir = guard.new_temp_dir("hojaiga_profile_")
        before = us._top_windows()
        fg_before = bw.last_user_window() or us._u32.GetForegroundWindow()
        si = subprocess.STARTUPINFO()
        si.dwFlags = 1
        si.wShowWindow = 7
        si.lpDesktop = "WinSta0\\Default"
        proc = subprocess.Popen(_chromium_args(t, user_dir, port), startupinfo=si)
        mine = {proc.pid}
        try:
            import psutil
            def family() -> set:
                try:
                    return {proc.pid} | {c.pid for c in psutil.Process(proc.pid).children(recursive=True)}
                except Exception:
                    return {proc.pid}
        except Exception:
            family = lambda: mine                                                   # noqa: E731
        t0 = time.time()
        hwnd = 0
        seen: Dict[int, float] = {}
        while time.time() - t0 < timeout_s and not hwnd:
            now = us._top_windows()
            fam = family()
            for h, (pid, cls, title) in now.items():
                if h in before or not cls.startswith("Chrome_WidgetWin"):
                    continue
                if pid not in fam and len(fam) > 1:
                    continue
                seen.setdefault(h, time.time())
                if not us._u32.IsIconic(h):
                    us._u32.ShowWindow(h, 7)
                if time.time() - seen[h] > 1.0 and title:
                    hwnd = h
            time.sleep(0.2)
        info: Dict[str, Any] = {"launched": bool(hwnd), "hwnd": hwnd, "notes": [f"{t.chromium} launched with a throw-away profile"], "launch_s": round(time.time() - t0, 2), "cdp_port": port, "pid": proc.pid}
        if hwnd:
            info["notes"].append(bw.stabilize_minimized(hwnd, fg_before, 3.0, quiet_s=0.6) or "stable")
            bw.mark_ours(hwnd)
            info["title"] = us._top_windows().get(hwnd, (0, "", ""))[2]
        return info
    # a heavy application (a 3D suite compiling shaders, an IDE indexing) can take more than 40 s before its main window exists: measured 45-60 s for Blender 5.2's first window
    if exe and args:                                                          # the program that hosts a scripting bridge (professor.adapters.script_bridge), started with it
        return us.launch_hidden(exe, timeout_s=max(timeout_s, float(os.environ.get("HOJAIGA_LAUNCH_S", 90))), fast=True, args=list(args))
    # the Start-menu entry (what a person searches for and opens) is the ground truth; a program path GUESSED from the name can be another program (MEASURED: IDLE resolved to the Python console)
    return us.launch_hidden((t.display or t.name) if t.appid else (t.exe if (t.exe and not t.packaged) else t.name), timeout_s=max(timeout_s, float(os.environ.get("HOJAIGA_LAUNCH_S", 90))), fast=True)
