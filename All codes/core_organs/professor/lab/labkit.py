"""professor.lab.labkit -- helpers to launch the pointer-lab targets, read what they received, and WATCH the person's cursor while a route delivers input."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "bin")
_u = ctypes.WinDLL("user32", use_last_error=True)
_u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
_u.WindowFromPoint.argtypes = [wt.POINT]
_u.WindowFromPoint.restype = wt.HWND
_u.GetAncestor.argtypes = [wt.HWND, wt.UINT]
_u.GetAncestor.restype = wt.HWND


def cursor_pos() -> Tuple[int, int]:
    p = wt.POINT()
    _u.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


class _LII(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def idle_ms() -> int:
    """Milliseconds since the last REAL input event (keyboard / mouse / touch / pen) reached the desktop."""
    lii = _LII(ctypes.sizeof(_LII), 0)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    return int((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF)


class CursorWatch:
    """Samples GetCursorPos every ~2 ms; .moved is True when the cursor ever left where it started. Used to PROVE a route does not move the person's cursor."""
    def __init__(self):
        self.start = cursor_pos()
        self.t0 = time.time()
        self.max_dev = 0
        self.samples = 0
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop:
            x, y = cursor_pos()
            self.max_dev = max(self.max_dev, abs(x - self.start[0]) + abs(y - self.start[1]))
            self.samples += 1
            time.sleep(0.002)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop = True
        self._t.join(1)

    @property
    def moved(self) -> bool:
        return self.max_dev > 0

    @property
    def person_moved_it(self) -> bool:
        """True when real input arrived during the watch (the PERSON used the mouse / keyboard: any movement is theirs, not the route's)."""
        return idle_ms() < (time.time() - self.t0) * 1000 + 50


class Lab:
    def __init__(self, name: str, x: int = -20000, y: int = -20000):
        self.name = name
        self.log_path = os.path.join(HERE, f"{name}.log")
        try:
            os.remove(self.log_path)
        except OSError:
            pass
        self.proc = subprocess.Popen([os.path.join(BIN, f"lab_{name}.exe"), self.log_path, str(x), str(y)])
        self.hwnd = 0
        end = time.time() + 20
        while time.time() < end and not self.hwnd:
            for r in self.events():
                if r.get("kind") == "ready":
                    self.hwnd = int(r["hwnd"])
            time.sleep(0.1)

    def events(self) -> List[Dict[str, Any]]:
        out = []
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    try:
                        out.append(json.loads(ln))
                    except Exception:
                        pass
        except Exception:
            pass
        return out

    def mark(self) -> int:
        return len(self.events())

    def since(self, m: int) -> List[Dict[str, Any]]:
        return self.events()[m:]

    def rect(self) -> Tuple[int, int, int, int]:
        r = wt.RECT()
        _u.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    def move_to(self, x: int, y: int, topmost: bool = False) -> None:
        flags = 0x0001 | 0x0010                         # NOSIZE | NOACTIVATE
        _u.SetWindowPos(self.hwnd, -1 if topmost else 0, x, y, 0, 0, flags | (0 if topmost else 0x0004))

    def close(self) -> None:
        try:
            self.proc.kill()
        except Exception:
            pass


def client_origin(hwnd: int) -> Tuple[int, int]:
    p = wt.POINT(0, 0)
    _u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
    _u.ClientToScreen(hwnd, ctypes.byref(p))
    return p.x, p.y


def ensure_built(names: Sequence[str] = ("winforms", "winforms_aware", "wpf")) -> Tuple[bool, str]:
    """Compile the lab targets with the .NET Framework C# compiler that ships with Windows when a binary is missing. (ok, why-not)."""
    csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    wpf = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\WPF"
    os.makedirs(BIN, exist_ok=True)
    for n in names:
        out = os.path.join(BIN, f"lab_{n}.exe")
        if os.path.isfile(out):
            continue
        if not os.path.isfile(csc):
            return False, "the .NET Framework C# compiler (csc.exe) is not on this machine"
        base = "wpf" if n == "wpf" else "winforms"
        cmd = [csc, "-nologo", "-target:winexe", f"-out:{out}", os.path.join(HERE, f"lab_{base}.cs"), "-r:System.Windows.Forms.dll", "-r:System.Drawing.dll"]
        if n == "winforms_aware":
            cmd.append("-win32manifest:" + os.path.join(HERE, "aware.manifest"))
        if base == "wpf":
            cmd += ["-r:" + os.path.join(wpf, d) for d in ("PresentationFramework.dll", "PresentationCore.dll", "WindowsBase.dll")] + ["-r:System.Xaml.dll"]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
        if not os.path.isfile(out):
            return False, "compiling the lab target failed: " + (r.stdout + r.stderr)[-200:]
    return True, ""
