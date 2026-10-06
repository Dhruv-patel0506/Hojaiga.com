"""gdi_budget_trace.py — find WHICH call site consumes the process's GDI handles (diagnostic, off by default).

Why this exists (measured, 2026-10-05): the suite's own process climbs to the Windows per-process
cap of 10,000 GDI objects — 1 → 6888 within the first 39 tests, never coming back down — and a
capped process cannot create a device context. EVERY PrintWindow capture after that comes back
blank and reads as "the app did not render", which is a lie: the app was fine, OUR process was
out of budget. That is the whole "capture cluster" (MIN1 / E2E-2 / ES1 / S2 and escalation
screenshots) in one sentence, and it is exactly the failure that bites long unattended sessions.

Micro-probes of the obvious suspects showed +0 handles per 40 calls, so guessing had already failed.
This file measures instead: it wraps the GDI allocators/freeers on the shared ctypes library
instances and keeps the allocation stack of every handle that was never freed.

Enable with HOJAIGA_GDI_TRACE=1 (nothing changes when it is off):
    from core_organs import gdi_budget_trace as gbt
    gbt.install()            # honouring the env flag
    ... work ...
    print(gbt.report())      # per call site: how many handles are still live

Known trap this is expected to catch: deleting an object that is still selected into a DC fails
silently (the handle stays alive), and DeleteDC does not free it — the site shows up as never
freed even though the code "looks" balanced.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from typing import Any, Dict, List, Set, Tuple

ENABLE_ENV = "HOJAIGA_GDI_TRACE"

# (library, function) -> kind. kind "create" records the handle; "delete" removes it.
CREATE_FUNCS: List[Tuple[str, str, str]] = [
    ("gdi32", "CreateCompatibleDC", "dc"),
    ("gdi32", "CreateDCW", "dc"),
    ("gdi32", "CreateCompatibleBitmap", "bitmap"),
    ("gdi32", "CreateBitmap", "bitmap"),
    ("gdi32", "CreateDIBSection", "bitmap"),
    ("gdi32", "CreateFontW", "font"),
    ("gdi32", "CreateFontIndirectW", "font"),
    ("gdi32", "CreatePen", "pen"),
    ("gdi32", "CreateSolidBrush", "brush"),
    ("gdi32", "CreatePalette", "palette"),
    ("user32", "GetDC", "screen-dc"),
    ("user32", "GetWindowDC", "window-dc"),
]
DELETE_FUNCS: List[Tuple[str, str, str]] = [
    ("gdi32", "DeleteDC", "dc"),
    ("gdi32", "DeleteObject", "any"),
    ("user32", "ReleaseDC", "dc-release"),
]

_installed = False
_lock = threading.Lock()
_live: Dict[int, Dict[str, Any]] = {}        # handle -> {api, kind, where, at}
_created = 0
_originals: Dict[Tuple[str, str], Any] = {}
_wrapped_threads: Set[int] = set()             # thread ids that already have the wrappers installed


def enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "") == "1"


def _site(depth: int = 4) -> str:
    """Caller stack, nearest first, as 'file:line' pairs — the answer to 'who allocated this'.
    Walks frames directly instead of traceback.extract_stack(): this runs on EVERY GDI allocation,
    and extract_stack (which re-reads source lines) costs ~40x more and slows the suite enough to
    change timeout-sensitive test outcomes."""
    try:
        parts = []
        fr = sys._getframe(2)                        # 0=_site, 1=the wrapper, 2=the real caller
        while fr is not None and len(parts) < depth:
            parts.append(f"{os.path.basename(fr.f_code.co_filename)}:{fr.f_lineno}")
            fr = fr.f_back
        return " <- ".join(parts)
    except Exception:  # noqa: BLE001
        return "?"


def _as_handle(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _wrap(libs, lib_name: str, fname: str, kind: str, creating: bool) -> None:
    if creating:
        original = getattr(libs[lib_name], fname)
        _originals[(lib_name, fname)] = original        # uninstall() only restores the calling thread

        def wrapper(*a, **k):
            global _created
            out = original(*a, **k)
            h = _as_handle(out)
            where = _site()
            with _lock:
                _created += 1
                if h:
                    # A DC/bitmap handle can be reused after free; last writer wins, which is what
                    # we want: the report shows handles that are LIVE now and where they came from.
                    _live[h] = {"api": f"{lib_name}.{fname}", "kind": kind, "where": where,
                                "at": round(time.time(), 3), "thread": threading.get_ident()}
            return out
    else:
        original = getattr(libs[lib_name], fname)
        _originals[(lib_name, fname)] = original

        def wrapper(*a, **k):
            # ReleaseDC(hwnd, hdc) and DeleteDC(hdc) differ in argument order; drop by value:
            # any argument that names a live handle is considered freed by the call that succeeded.
            out = original(*a, **k)
            try:
                ok = int(out or 0) != 0          # all three return nonzero on success
            except (TypeError, ValueError):
                ok = False
            if ok:
                with _lock:
                    for arg in a:
                        h = _as_handle(arg)
                        if h and h in _live:
                            # GDI handles are arbitrary 32-bit values; match on identity only.
                            _live.pop(h, None)
            elif fname == "DeleteObject":
                # The silent failure worth knowing about: a still-selected object is NOT deleted.
                with _lock:
                    for arg in a:
                        h = _as_handle(arg)
                        if h and h in _live:
                            _live[h] = dict(_live[h], delete_refused=1)
            return out
    setattr(libs[lib_name], fname, wrapper)


def _install_on_this_thread(force: bool) -> int:
    """Wrap the allocators on THIS thread's ctypes.windll instances. Measured reason this matters:
    since Python 3.3 the windll loader objects are thread-local, so a wrapper installed on the main
    thread is invisible to the VisualCursor/worker threads -- which is exactly where a continuous
    leaker lives. Returns how many entry points got wrapped here."""
    libs = {"gdi32": ctypes.windll.gdi32, "user32": ctypes.windll.user32}
    tid = threading.get_ident()
    if tid in _wrapped_threads:
        return 0
    _wrapped_threads.add(tid)
    n = 0
    for lib_name, fname, kind in CREATE_FUNCS:
        try:
            _wrap(libs, lib_name, fname, kind, True)
            n += 1
        except Exception:  # noqa: BLE001
            pass
    for lib_name, fname, kind in DELETE_FUNCS:
        try:
            _wrap(libs, lib_name, fname, kind, False)
            n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def install(force: bool = False) -> bool:
    """Wrap the allocators. Idempotent, and a no-op unless HOJAIGA_GDI_TRACE=1 (or force).
    Also hooks threading so every thread created AFTER this call gets its own wrappers."""
    global _installed
    if _installed or not (force or enabled()):
        return False
    _installed = True
    _install_on_this_thread(force)
    _patch_threading()
    return True


def _patch_threading() -> None:
    """Install the wrappers at the top of every thread body (see _install_on_this_thread)."""
    try:
        orig_init = threading.Thread.__init__
        if getattr(orig_init, "_gbt_wrapped", False):
            return

        def __init__(self, *a, **k):
            target = k.get("target", a[0] if a else None)
            if callable(target):
                def traced(*ta, **tk):
                    _install_on_this_thread(True)
                    return target(*ta, **tk)
                if a:
                    a = (traced,) + tuple(a[1:])
                else:
                    k["target"] = traced
            orig_init(self, *a, **k)                     # type: ignore[arg-type]

        __init__._gbt_wrapped = True                    # type: ignore[attr-defined]
        threading.Thread.__init__ = __init__            # type: ignore[method-assign]
    except Exception:  # noqa: BLE001
        pass


def live_count() -> int:
    with _lock:
        return len(_live)


def report(limit: int = 14) -> str:
    """The live handles grouped by (api, call site), biggest first. Nothing here was ever freed."""
    with _lock:
        items = list(_live.values())
        created = _created
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for it in items:
        groups.setdefault((it["api"], it["where"]), []).append(it)
    rows = sorted(((len(v), k[0], k[1], sum(1 for x in v if x.get("delete_refused")),
                    {x.get("thread") for x in v})
                   for k, v in groups.items()), reverse=True)
    head = f"GDI TRACE: {created} allocations seen, {len(items)} handles still live " \
           f"(wrapped threads: {len(_wrapped_threads)})"
    if not rows:
        return head + " — nothing outstanding"
    lines = [head]
    for n, api, where, refused, tids in rows[:limit]:
        tag = (f" [delete refused {refused}x: still selected into a DC]" if refused else "")
        lines.append(f"  {n:>5} live  {api:<28} threads={len(tids)}  {where}{tag}")
    return "\n".join(lines)


def uninstall() -> None:
    """Put the original functions back (used by a test that must not affect later tests)."""
    global _installed
    libs = {"gdi32": ctypes.windll.gdi32, "user32": ctypes.windll.user32}
    for (lib_name, fname), original in list(_originals.items()):
        try:
            setattr(libs[lib_name], fname, original)
        except Exception:  # noqa: BLE001
            pass
    _originals.clear()
    _live.clear()
    _installed = False
