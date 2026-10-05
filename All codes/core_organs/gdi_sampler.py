"""
gdi_sampler.py -- WHO is running while the process's GDI handle count climbs? (diagnostic, HOJAIGA_GDI_SAMPLE=1)

gdi_budget_trace.py wraps every allocator and answers 'which call site allocated this handle' - but wrapping changes what it measures
(measured 2026-10-05: with the wrappers installed the suite process stayed at ~24 GDI objects, without them it climbed to the 10,000 cap
by test UP1). This sampler changes nothing: a daemon thread reads GetGuiResources every 0.25 s and, whenever the count grew by >= `step`
since the previous sample, records the CURRENT stack of every other thread (sys._current_frames). Growth-weighted, the stacks that are
active during growth name the code path that leaks, and the report is grouped per test id so the leaking TEST is named too.

    s = gdi_sampler.start(); gdi_sampler.set_test("UP1"); ...; print(gdi_sampler.report())
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Tuple

ENABLE_ENV = "HOJAIGA_GDI_SAMPLE"
_state: Dict[str, Any] = {"test": "-", "stop": threading.Event(), "thread": None, "events": []}


def enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "") == "1"


def set_test(test_id: str) -> None:
    _state["test"] = test_id


def _gdi() -> int:
    try:
        from core_organs import headless_input as hin
        return hin._gui_objects()[0]
    except Exception:  # noqa: BLE001
        return -1


def _loop(step: int, period: float) -> None:
    last = _gdi()
    me = threading.get_ident()
    while not _state["stop"].is_set():
        time.sleep(period)
        now = _gdi()
        grew = now - last
        last = now
        if grew >= step:
            stacks: List[str] = []
            names = {t.ident: t.name for t in threading.enumerate()}
            for tid, fr in sys._current_frames().items():
                if tid == me:
                    continue
                frames = traceback.extract_stack(fr, limit=6)
                # skip idle waits: a thread parked in threading/queue/selectors waiting is not the allocator
                top = frames[-1] if frames else None
                if top and os.path.basename(top.filename) in ("threading.py", "queue.py", "selectors.py") and top.name in ("wait", "get", "select", "_wait_for_tstate_lock"):
                    continue
                stacks.append(f"[{names.get(tid, tid)}] " + " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}" for f in reversed(frames)))
            _state["events"].append({"test": _state["test"], "grew": grew, "at": round(time.time(), 2), "count": now, "stacks": stacks})


def start(step: int = 6, period: float = 0.25) -> bool:
    if _state["thread"] is not None:
        return False
    _state["stop"].clear()
    t = threading.Thread(target=_loop, args=(step, period), daemon=True, name="gdi-sampler")
    _state["thread"] = t
    t.start()
    return True


def stop() -> None:
    _state["stop"].set()


def report(top: int = 14) -> str:
    ev = _state["events"]
    if not ev:
        return "GDI SAMPLER: no growth of >= step observed"
    per_test: Dict[str, int] = {}
    per_stack: Dict[str, Dict[str, int]] = {}
    for e in ev:
        per_test[e["test"]] = per_test.get(e["test"], 0) + e["grew"]
        for s in e["stacks"]:
            d = per_stack.setdefault(e["test"], {})
            d[s] = d.get(s, 0) + e["grew"]
    lines = ["GDI SAMPLER: growth observed per test (handles) = " + ", ".join(f"{k}:+{v}" for k, v in sorted(per_test.items(), key=lambda kv: -kv[1])[:12])]
    for test, _tot in sorted(per_test.items(), key=lambda kv: -kv[1])[:5]:
        lines.append(f"  --- {test}: stacks active while the count grew (weighted by growth)")
        for s, w in sorted(per_stack.get(test, {}).items(), key=lambda kv: -kv[1])[:top // 2]:
            lines.append(f"      {w:>6}  {s[:330]}")
    return "\n".join(lines)
