"""
hojaiga_ui -- launch the HoJaiga companion.

    python hojaiga_ui.py                 # starts the local server and opens the companion docked at the right edge of the screen
    python hojaiga_ui.py --no-window     # server only (open http://127.0.0.1:8765 yourself)
    python hojaiga_ui.py --port 8800

The companion talks to the program you pick: it opens it on the left of the screen, scans it where you can watch, asks what you want, and teaches it live with a spotlight on the real window.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def edge_path() -> str:
    for p in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if p and os.path.isfile(p):
            return p
    return ""


def open_window(url: str) -> bool:
    """The companion as its own app-style window on the right edge (a throw-away browser profile: the person's own browser is untouched)."""
    exe = edge_path()
    if not exe:
        import webbrowser
        return webbrowser.open(url)
    u = ctypes.windll.user32
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    w = 500
    subprocess.Popen([exe, f"--app={url}", f"--window-size={w},{sh - 80}", f"--window-position={sw - w - 8},8", f"--user-data-dir={os.path.join(tempfile.gettempdir(), 'hojaiga_ui_profile')}",
                      "--no-first-run", "--no-default-browser-check"], creationflags=0x00000008)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-window", action="store_true")
    a = ap.parse_args(argv)
    import uvicorn
    url = f"http://127.0.0.1:{a.port}"
    if not a.no_window:
        threading.Timer(1.8, open_window, args=(url,)).start()
    print(f"HoJaiga companion on {url}  (Ctrl+C to stop)", flush=True)
    uvicorn.run("ui.server:app", host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
