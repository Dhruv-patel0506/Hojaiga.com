"""
vision_gate.py -- the local vision model (Qwen2.5-VL-7B on llama-server :8081) must be UP while testing, and every use of it is LOGGED.

A test run with the vision rung silently off reads as 'the loop is stuck / the app is broken' when the truth is 'the eyes were closed'.
ensure_up() starts the server the same way start_hojaiga.bat does when it is down (free, local, bounded wait); install() wraps
qwen_vl_scanner.locate / parse_image so each call is counted and appended to data/vision_log.jsonl; summary() is printed with the results.
Nothing here is a verdict: a missing server is reported (ENV), never faked.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from typing import Any, Dict, Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOG = os.path.join(_ROOT, "data", "vision_log.jsonl")
BASE = os.environ.get("HOJAIGA_QWEN_VL_URL", "http://127.0.0.1:8081")
_LLAMA = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe")
_MODEL = os.path.join(_ROOT, "models", "Qwen_Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf")
_MMPROJ = os.path.join(_ROOT, "models", "mmproj-Qwen_Qwen2.5-VL-7B-Instruct-f16.gguf")

_lock = threading.Lock()
_stats: Dict[str, Any] = {"calls": 0, "found": 0, "errors": 0, "ms_total": 0, "by_fn": {}, "installed": False, "server": "unknown"}


def healthy(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=timeout) as r:
            return b"ok" in r.read().lower()
    except Exception:  # noqa: BLE001
        return False


def ensure_up(wait_s: float = 90.0) -> Dict[str, Any]:
    """Make sure the vision server answers; start it when it does not. Returns {'up', 'started', 'why'}."""
    if healthy():
        _stats["server"] = "up"
        return {"up": True, "started": False, "why": "already running"}
    missing = [p for p in (_LLAMA, _MODEL, _MMPROJ) if not os.path.isfile(p)]
    if missing:
        _stats["server"] = "missing-files"
        return {"up": False, "started": False, "why": "ENV: not installed (" + ", ".join(os.path.basename(m) for m in missing) + ")"}
    subprocess.Popen([_LLAMA, "--model", _MODEL, "--mmproj", _MMPROJ, "--port", "8081", "--ctx-size", "4096", "-ngl", "24", "-t", "8", "-tb", "8",
                      "-fa", "on", "-np", "1", "--host", "127.0.0.1"], creationflags=0x08000000 | 0x00000008,   # no window, detached
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if healthy():
            _stats["server"] = "up"
            return {"up": True, "started": True, "why": f"started in {time.time() - t0:.0f}s"}
        time.sleep(2)
    _stats["server"] = "down"
    return {"up": False, "started": True, "why": f"ENV: started but not healthy after {wait_s:.0f}s"}


def _record(fn: str, args_desc: str, ms: int, found: Optional[bool], err: str = "") -> None:
    with _lock:
        _stats["calls"] += 1
        _stats["ms_total"] += ms
        _stats["by_fn"][fn] = _stats["by_fn"].get(fn, 0) + 1
        if found:
            _stats["found"] += 1
        if err:
            _stats["errors"] += 1
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "fn": fn, "what": args_desc[:80], "ms": ms, "found": found, "error": err[:80]}) + "\n")
        except Exception:  # noqa: BLE001
            pass


def install() -> bool:
    """Wrap qwen_vl_scanner so every vision call is counted and logged (idempotent)."""
    if _stats["installed"]:
        return True
    try:
        from core_organs import qwen_vl_scanner as qv
    except Exception:  # noqa: BLE001
        return False
    real_locate, real_parse = qv.locate, qv.parse_image

    def locate(img, description, *a, **k):
        t0 = time.perf_counter()
        res, meta = real_locate(img, description, *a, **k)
        _record("locate", description, int((time.perf_counter() - t0) * 1000), res is not None, (meta or {}).get("error", ""))
        return res, meta

    def parse_image(img, *a, **k):
        t0 = time.perf_counter()
        res, meta = real_parse(img, *a, **k)
        _record("parse_image", "full-screen parse", int((time.perf_counter() - t0) * 1000), bool(res), (meta or {}).get("error", ""))
        return res, meta

    qv.locate, qv.parse_image = locate, parse_image
    _stats["installed"] = True
    return True


def summary() -> str:
    s = _stats
    avg = (s["ms_total"] // s["calls"]) if s["calls"] else 0
    return (f"vision(Qwen2.5-VL-7B :8081) server={s['server']} calls={s['calls']} found={s['found']} errors={s['errors']} avg={avg}ms by_fn={s['by_fn']}"
            f" log={os.path.relpath(LOG, _ROOT)}")
