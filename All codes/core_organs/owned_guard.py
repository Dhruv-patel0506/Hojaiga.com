"""
owned_guard -- an application WE launched must never outlive the process that launched it.

MEASURED failure (2026-10-17): a Claude session was torn down while a live Paint run was drawing; the parked Paint windows it owned stayed alive (the python process was ended without running atexit) and sat over the
left part of the person's screen -- invisible, but taking their clicks -- until they were found and closed by hand.

Two independent safeguards, both by PID (never by image name; the person's own copies of an app are untouched):
  1. `bind(pid)`   puts the owned process into a Windows Job Object with KILL_ON_JOB_CLOSE held by THIS python process: when this process ends in ANY way (crash, kill, session teardown) the OS closes the job
                   and ends the owned process. No cooperation from the dying process is needed.
  2. `reap_orphans()` at the next start: every owned pid journalled by a python process that is no longer alive (and whose pid still has the same creation time, so a recycled pid is never hit) is ended.
"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import json
import os
import time
from typing import Any, Dict, List

_JOB = None
_journal_path = os.path.join(os.environ.get("TEMP", "."), f"hojaiga_owned_{os.getpid()}.json")
_PROCESS_SET_QUOTA, _PROCESS_TERMINATE, _PROCESS_QUERY = 0x0100, 0x0001, 0x1000
_KILL_ON_CLOSE = 0x2000
_INFO_CLASS = 9                                                       # JobObjectExtendedLimitInformation


class _BASIC(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]


class _IO(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _EXT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _job() -> Any:
    global _JOB
    if _JOB is None:
        k = ctypes.windll.kernel32
        k.CreateJobObjectW.restype = wt.HANDLE
        h = k.CreateJobObjectW(None, None)
        info = _EXT()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_CLOSE
        k.SetInformationJobObject(wt.HANDLE(h), _INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info))
        _JOB = h
    return _JOB


def _created(pid: int) -> float:
    with contextlib.suppress(Exception):
        import psutil
        return float(psutil.Process(pid).create_time())
    return 0.0


def _owner_alive(pid: int) -> bool:
    with contextlib.suppress(Exception):
        import psutil
        return psutil.pid_exists(pid) and "python" in (psutil.Process(pid).name() or "").lower()
    return True                                                       # cannot tell: leave it alone


def _write(entries: List[Dict[str, Any]]) -> None:
    with contextlib.suppress(Exception):
        json.dump(entries, open(_journal_path, "w", encoding="utf-8"))


_entries: List[Dict[str, Any]] = []


def bind(pid: int, name: str = "") -> Dict[str, Any]:
    """Journal `pid` and bind it to this process's kill-on-close job. Never binds a SHARED host (ApplicationFrameHost, explorer, svchost...). Returns what was achieved."""
    out = {"pid": pid, "journalled": False, "job": False}
    if not pid or pid == os.getpid():
        return out
    with contextlib.suppress(Exception):
        import psutil
        nm = (psutil.Process(pid).name() or "").lower()
        if nm in ("applicationframehost.exe", "explorer.exe", "svchost.exe", "runtimebroker.exe", "sihost.exe", "dwm.exe", "claude.exe"):
            out["why"] = "shared host: not bound"
            return out
    _entries.append({"pid": pid, "created": _created(pid), "name": name})
    _write(_entries)
    out["journalled"] = True
    with contextlib.suppress(Exception):
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = wt.HANDLE
        hp = k.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE | _PROCESS_QUERY, False, pid)
        if hp:
            out["job"] = bool(k.AssignProcessToJobObject(wt.HANDLE(_job()), wt.HANDLE(hp)))
            if not out["job"]:
                out["why"] = f"AssignProcessToJobObject error {ctypes.get_last_error() or ctypes.GetLastError()}"
            k.CloseHandle(wt.HANDLE(hp))
    return out


def release(pid: int) -> None:
    """The owned process was ended properly: drop it from the journal."""
    global _entries
    _entries = [e for e in _entries if e["pid"] != pid]
    if _entries:
        _write(_entries)
    else:
        with contextlib.suppress(Exception):
            os.remove(_journal_path)


def reap_orphans(verbose: bool = True) -> List[int]:
    """End (by PID) every owned process left behind by a python process that has died. A pid whose creation time differs from the journal (recycled) is never touched."""
    ended: List[int] = []
    tmp = os.environ.get("TEMP", ".")
    for fn in os.listdir(tmp):
        if not (fn.startswith("hojaiga_owned_") and fn.endswith(".json")):
            continue
        try:
            owner = int(fn[len("hojaiga_owned_"):-len(".json")])
        except ValueError:
            continue
        if owner == os.getpid() or _owner_alive(owner):
            continue
        path = os.path.join(tmp, fn)
        try:
            entries = json.load(open(path, encoding="utf-8"))
        except Exception:
            entries = []
        for e in entries:
            pid, created = int(e.get("pid", 0)), float(e.get("created", 0))
            with contextlib.suppress(Exception):
                import psutil
                if pid and psutil.pid_exists(pid) and abs(psutil.Process(pid).create_time() - created) < 2.0:
                    psutil.Process(pid).terminate()
                    ended.append(pid)
                    if verbose:
                        print(f"[owned_guard] ended orphaned owned process {pid} ({e.get('name', '')}) left by dead owner {owner}", flush=True)
        with contextlib.suppress(Exception):
            os.remove(path)
    return ended
