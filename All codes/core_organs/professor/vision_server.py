"""
professor.vision_server -- lifecycle of the local vision model server (llama.cpp `llama-server`, GGUF + mmproj), without ever showing a window.

  status()  who is listening on the vision port, which model, which llama-server processes exist (ours vs started by start_hojaiga.bat)
  ensure()  start it when nothing answers (hidden, bound to 127.0.0.1) and wait for /health -- reuse a running server untouched
  stop()    stop ONLY a server this module started
  tune()    measure generation speed for several GPU-layer counts on this machine and remember the fastest that loads (6 GB laptop GPU: it matters)

Model choice lives in config.PROFILES (Qwen3-VL-8B default; HOJAIGA_PROF_GGUF/MMPROJ drop in a GUI-grounding specialist).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from . import config as CFG

try:
    import requests
except Exception:                                                                       # pragma: no cover
    requests = None

_PID_FILE = os.path.join(CFG.DATA_DIR, "server.pid")
_HELP_CACHE: Dict[str, str] = {}


def _port() -> int:
    try:
        return int(CFG.VISION_URL.rsplit(":", 1)[1].split("/")[0])
    except Exception:
        return 8081


def _health(timeout: float = 1.5) -> Dict[str, Any]:
    if requests is None:
        return {"up": False}
    try:
        r = requests.get(CFG.VISION_URL + "/health", timeout=timeout)
        if r.status_code == 200:
            return {"up": True, "state": r.json().get("status", "ok")}
        return {"up": False, "state": f"HTTP {r.status_code}"}           # 503 while the model is still loading
    except Exception:
        return {"up": False}


def llama_processes() -> List[Dict[str, Any]]:
    out = []
    try:
        import psutil
        ours = _read_pid()
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            if (p.info["name"] or "").lower() == "llama-server.exe":
                cmd = " ".join(p.info["cmdline"] or [])
                out.append({"pid": p.info["pid"], "ours": p.info["pid"] == ours, "cmd": cmd[:240]})
    except Exception:
        pass
    return out


def _read_pid() -> int:
    try:
        with open(_PID_FILE, "r") as fh:
            return int(fh.read().strip())
    except Exception:
        return 0


def status() -> Dict[str, Any]:
    h = _health()
    prof = CFG.active_profile()
    model = ""
    if h.get("up") and requests is not None:
        try:
            model = (requests.get(CFG.VISION_URL + "/v1/models", timeout=2).json().get("data") or [{}])[0].get("id", "")
        except Exception:
            pass
    return {"up": bool(h.get("up")), "state": h.get("state", ""), "url": CFG.VISION_URL, "model_loaded": model,
            "profile": prof.name if prof else None, "profile_files_present": bool(prof and prof.files_present()),
            "binary": CFG.llama_server_binary(), "processes": llama_processes()}


def _supports(binary: str, flag: str) -> bool:
    if binary not in _HELP_CACHE:
        try:
            _HELP_CACHE[binary] = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=20,
                                                 creationflags=0x08000000).stdout
        except Exception:
            _HELP_CACHE[binary] = ""
    return flag in _HELP_CACHE[binary]


def tuned_ngl(profile: CFG.ModelProfile) -> int:
    try:
        with open(CFG.PROFILE_FILE, "r", encoding="utf-8") as fh:
            return int(json.load(fh).get(profile.name, {}).get("ngl", profile.ngl))
    except Exception:
        return profile.ngl


def build_command(profile: CFG.ModelProfile, ngl: Optional[int] = None, ctx: Optional[int] = None) -> List[str]:
    binary = CFG.llama_server_binary()
    if not binary:
        raise FileNotFoundError("llama-server.exe not found (set HOJAIGA_LLAMA_SERVER)")
    cmd = [binary, "--model", profile.gguf, "--port", str(_port()), "--host", "127.0.0.1", "--ctx-size", str(ctx or profile.ctx),
           "-ngl", str(profile.ngl if ngl is None else ngl), "-t", "8", "-tb", "8", "-np", "1"]
    if profile.mmproj:
        cmd += ["--mmproj", profile.mmproj]
    if _supports(binary, "-fa"):
        cmd += ["-fa", "on"]
    if _supports(binary, "--image-min-tokens"):
        cmd += ["--image-min-tokens", str(profile.image_min_tokens)]
    if _supports(binary, "--image-max-tokens"):
        cmd += ["--image-max-tokens", str(profile.image_tokens_budget + 400)]
    return cmd


def start(profile: Optional[CFG.ModelProfile] = None, ngl: Optional[int] = None) -> Dict[str, Any]:
    prof = profile or CFG.active_profile()
    if prof is None or not prof.files_present():
        return {"ok": False, "error": "no vision model files found (see config.PROFILES)", "profile": getattr(prof, "name", None)}
    try:
        cmd = build_command(prof, ngl if ngl is not None else tuned_ngl(prof))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    CFG.ensure_dirs()
    log = open(os.path.join(CFG.LOG_DIR, "llama-server.log"), "ab")
    flags = 0x08000000 | 0x00000008 | 0x00000200            # CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: no window, no focus
    try:
        p = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags | 0x01000000, close_fds=True)
    except Exception:
        p = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    with open(_PID_FILE, "w") as fh:
        fh.write(str(p.pid))
    return {"ok": True, "pid": p.pid, "cmd": cmd}


def ensure(wait_s: float = 240.0, profile: Optional[CFG.ModelProfile] = None, ngl: Optional[int] = None) -> Dict[str, Any]:
    """Make sure a vision server answers. Reuses a running one (never restarts it); otherwise starts one hidden and waits (bounded)."""
    t0 = time.time()
    h = _health()
    if h.get("up"):
        return {"ok": True, "started": False, "seconds": 0.0, **status()}
    procs = llama_processes()
    started = None
    if not procs:
        started = start(profile, ngl)
        if not started.get("ok"):
            return {"ok": False, "started": False, **started}
    deadline = t0 + wait_s
    stuck_after = t0 + 90.0 if (procs and not started) else None                     # a server that is loading answers within about a minute; a process that does not answer is stuck
    while time.time() < deadline:
        if _health().get("up"):
            return {"ok": True, "started": bool(started), "seconds": round(time.time() - t0, 1), **status()}
        if stuck_after is not None and not started and time.time() > stuck_after:
            stop()
            time.sleep(2.0)
            started = start(profile, ngl)
            if not started.get("ok"):
                return {"ok": False, "started": False, **started}
        if started and started.get("pid"):
            try:
                import psutil
                if not psutil.pid_exists(started["pid"]):
                    return {"ok": False, "started": True, "error": "llama-server exited while loading (see logs/llama-server.log; out of GPU memory? lower ngl)",
                            "seconds": round(time.time() - t0, 1)}
            except Exception:
                pass
        time.sleep(1.5)
    return {"ok": False, "started": bool(started), "error": f"vision server did not become healthy in {wait_s:.0f}s", "seconds": round(time.time() - t0, 1)}


def stop() -> Dict[str, Any]:
    """Stop only the server THIS module launched (a server from start_hojaiga.bat belongs to the user's stack)."""
    pid = _read_pid()
    if not pid:
        return {"ok": True, "stopped": False, "why": "no server of ours"}
    try:
        import psutil
        if psutil.pid_exists(pid):
            p = psutil.Process(pid)
            if (p.name() or "").lower() == "llama-server.exe":
                p.terminate()
                try:
                    p.wait(10)
                except Exception:
                    p.kill()
                try:
                    os.remove(_PID_FILE)
                except OSError:
                    pass
                return {"ok": True, "stopped": True, "pid": pid}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "stopped": False}


def tune(candidates: Optional[List[int]] = None, per_try_s: float = 150.0) -> Dict[str, Any]:
    """Restart OUR server with each GPU-layer count, time a fixed 60-token generation, keep the fastest that loads. Refuses to touch a server we did not start."""
    prof = CFG.active_profile()
    if prof is None:
        return {"ok": False, "error": "no profile"}
    if _health().get("up") and not _read_pid():
        return {"ok": False, "error": "a vision server is running that this tool did not start; stop it first or tune manually"}
    from .vlm import VisionClient
    results = []
    best = None
    for n in (candidates or [28, 20, 16, 12, 8]):
        stop()
        time.sleep(1.0)
        s = start(prof, n)
        if not s.get("ok"):
            results.append({"ngl": n, "error": s.get("error")})
            continue
        t0 = time.time()
        up = False
        while time.time() - t0 < per_try_s:
            if _health().get("up"):
                up = True
                break
            try:
                import psutil
                if not psutil.pid_exists(s["pid"]):
                    break
            except Exception:
                pass
            time.sleep(1.5)
        if not up:
            results.append({"ngl": n, "error": "did not load (likely out of GPU memory)"})
            continue
        vc = VisionClient(profile=prof)
        r = vc.chat("Count from one to twenty in words, separated by commas.", max_tokens=60, timeout=90)
        if r.ok and r.completion_tokens:
            tps = r.completion_tokens / max(0.1, r.seconds)
            results.append({"ngl": n, "tok_per_s": round(tps, 2), "load_s": round(time.time() - t0, 1)})
            if best is None or tps > best["tok_per_s"]:
                best = results[-1]
        else:
            results.append({"ngl": n, "error": r.error})
    if best:
        CFG.ensure_dirs()
        try:
            with open(CFG.PROFILE_FILE, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            d = {}
        d[prof.name] = {"ngl": best["ngl"], "tok_per_s": best["tok_per_s"], "measured": time.time()}
        with open(CFG.PROFILE_FILE, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
    stop()
    return {"ok": bool(best), "best": best, "tried": results}
