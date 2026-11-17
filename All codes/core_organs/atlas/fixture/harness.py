"""Launch / observe / close the Atlas fixture. Launched minimized without activation; closed by PID only."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from . import build

_u32 = ctypes.windll.user32
SW_SHOWMINNOACTIVE = 7


def _windows_of(pid: int) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(h, _):
        p = wt.DWORD()
        _u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            n = _u32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 2)
            _u32.GetWindowTextW(h, buf, n + 2)
            out.append((int(h), buf.value))
        return True
    _u32.EnumWindows(cb_t(cb), 0)
    return out


def launch(timeout_s: float = 20.0, minimized: bool = True) -> Dict[str, Any]:
    b = build.build()
    if not b["ok"]:
        raise RuntimeError(f"fixture build failed: {b}")
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = SW_SHOWMINNOACTIVE if minimized else 1
    p = subprocess.Popen([build.exe_path()], startupinfo=si, cwd=os.path.dirname(build.exe_path()))
    end = time.time() + timeout_s
    hwnd = 0
    while time.time() < end and not hwnd:
        for h, title in _windows_of(p.pid):
            if title == "Atlas Fixture":
                hwnd = h
        time.sleep(0.1)
    if not hwnd:
        p.kill()
        raise RuntimeError("fixture window did not appear")
    return {"proc": p, "pid": p.pid, "hwnd": hwnd}


def close(h: Dict[str, Any]) -> None:
    p = h.get("proc")
    if p is not None and p.poll() is None:
        try:
            _u32.PostMessageW(h["hwnd"], 0x10, 0, 0)         # WM_CLOSE
            p.wait(timeout=3)
        except Exception:
            try:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/F"], capture_output=True, timeout=10)
            except Exception:
                pass


def read_state_text(hwnd: int) -> str:
    from core_organs import fast_uia
    nodes = fast_uia.snapshot(hwnd, timeout_ms=4000) or []
    for n in nodes:
        if n.aid == "stateLabel" or (n.name or "").startswith("zoom="):
            return n.name
    return ""


def parse_state(text: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, v in re.findall(r"(\w+)=([-\d.,]+)", text or ""):
        if "," in v:
            a, b = v.split(",")
            out[k + "_x"], out[k + "_y"] = float(a), float(b)
        else:
            try:
                out[k] = float(v)
            except ValueError:
                pass
    return out


def read_state(hwnd: int) -> Dict[str, float]:
    return parse_state(read_state_text(hwnd))
