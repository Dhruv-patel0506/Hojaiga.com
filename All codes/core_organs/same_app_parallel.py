"""
same_app_parallel.py -- LC2: SAME-APP parallel/disjoint cursors (P1-I, the harder half).

Cross-app parallelism already exists (operate_app(isolated=True): one DAP loop, one virtual cursor
sprite, one app per child). This module extends that to TWO concurrent workers inside the SAME
top-level window, each driving a region no other worker may touch.

Two facts decide what is safe, and both are ENFORCED here rather than guessed:

  1. REGION OWNERSHIP. A worker must ``claim`` a screen rectangle on the shared window before it can
     act there. An overlapping claim is refused at claim time; an out-of-region action is refused at
     action time. Two workers can never be steered into the same spot by optimism - the first one to
     own a pixel owns it exclusively.

  2. ONE LOGICAL MOUSE PER CHILD WINDOW. PostMessage mouse input shares a per-window button/capture
     state: two interleaved DOWN...UP sequences on the SAME child window corrupt each other no matter
     how far apart their coordinates are. So the real unit of concurrency is the CHILD window under
     the point (headless_input.child_at). Actions landing on DIFFERENT children run truly concurrent;
     actions on the SAME child serialize on a per-child lock. That is an honest degradation, measured
     (serialized_wait_ms) and reported with its reason by parallelism_report() - never hidden behind a
     blanket "parallel" claim.

Every action leaves through headless_input's PostMessage route only (PURE1 purity: this module never
reaches for a physical pointer or keyboard). Each owner gets its own input context: its own
virtual-cursor sprite (visual_cursor.for_agent) and its own recorded trace.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as _wt
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from core_organs import headless_input as hin

Rect = Tuple[int, int, int, int]  # SCREEN (left, top, right, bottom)

SAME_CHILD_REASON = ("one logical mouse per child window: posted DOWN...UP sequences to the same "
                     "child corrupt each other, so same-child actions serialize")

_lock = threading.Lock()
_claims: Dict[int, List[Dict[str, Any]]] = {}          # top hwnd -> [{owner, rects}]
_child_locks: Dict[int, threading.Lock] = {}           # child hwnd -> its single logical-mouse lock
_timeline: List[Dict[str, Any]] = []                   # every executed action, for the report


def _norm(rect: Any) -> Rect:
    vals = [int(v) for v in rect]
    l, t, r, b = vals[0], vals[1], vals[2], vals[3]
    return (min(l, r), min(t, b), max(l, r), max(t, b))


def child_rect_screen(child_hwnd: int) -> Rect:
    """Screen rect of a (child) window - the region posted input under it actually covers."""
    rc = _wt.RECT()
    ctypes.windll.user32.GetWindowRect(int(child_hwnd), ctypes.byref(rc))
    return (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))


def claim(top_hwnd: int, owner_id: str, *rects: Any) -> Tuple[bool, str]:
    """Own ``rects`` (screen coords) on ``top_hwnd`` for concurrent worker ``owner_id``.
    Refused when a rect overlaps a region another owner already claimed - disjointness is decided
    here, at claim time, not by hoping the workers happen to stay apart."""
    normed = [_norm(r) for r in rects]
    if not normed:
        return False, "no region given"
    with _lock:
        for other in _claims.get(int(top_hwnd), []):
            if other["owner"] == owner_id:
                continue
            for (al, at, ar, ab) in normed:
                for (bl, bt, br, bb) in other["rects"]:
                    if al < br and bl < ar and at < bb and bt < ab:
                        return False, (f"region ({al},{at},{ar},{ab}) overlaps owner "
                                       f"'{other['owner']}'s claim - LC2 refuses shared space")
        mine = next((c for c in _claims.get(int(top_hwnd), []) if c["owner"] == owner_id), None)
        if mine is None:
            _claims.setdefault(int(top_hwnd), []).append({"owner": owner_id, "rects": list(normed)})
        else:
            mine["rects"] = mine["rects"] + list(normed)
    return True, f"claimed {len(normed)} region(s) for '{owner_id}'"


def release(top_hwnd: int, owner_id: str = "") -> None:
    """Drop one owner's claims (or every claim on ``top_hwnd`` when owner_id is blank)."""
    with _lock:
        if owner_id:
            _claims[int(top_hwnd)] = [c for c in _claims.get(int(top_hwnd), [])
                                      if c["owner"] != owner_id]
        else:
            _claims.pop(int(top_hwnd), None)


def owns_point(owner_id: str, sx: int, sy: int) -> Tuple[bool, Optional[Rect]]:
    """Is (sx, sy) inside one of this owner's claimed regions? (Returns the region for reports.)"""
    with _lock:
        for entries in _claims.values():
            for c in entries:
                if c["owner"] != owner_id:
                    continue
                for r in c["rects"]:
                    if r[0] <= sx <= r[2] and r[1] <= sy <= r[3]:
                        return True, r
    return False, None


def claims_of(top_hwnd: int) -> List[str]:
    with _lock:
        return [c["owner"] for c in _claims.get(int(top_hwnd), [])]


def child_lock(child_hwnd: int) -> threading.Lock:
    with _lock:
        lk = _child_locks.get(int(child_hwnd))
        if lk is None:
            lk = _child_locks[int(child_hwnd)] = threading.Lock()
        return lk


def reset() -> None:
    """Clear all claims, locks and the action timeline (test isolation between runs)."""
    with _lock:
        _claims.clear()
        _child_locks.clear()
        _timeline.clear()


class InputContext:
    """One concurrent worker's private input world inside a shared window: its own cursor sprite, its
    own claimed regions, its own trace. Coordinates are SCREEN pixels; every action is checked against
    THIS context's claims and takes only the lock of the child window it actually lands on."""

    def __init__(self, top_hwnd: int, owner_id: str, agent_name: str = ""):
        self.top = int(top_hwnd)
        self.owner_id = owner_id
        self.cursor_id = f"child:{owner_id}:{self.top}"
        self.sprite = None
        try:
            from core_organs import visual_cursor as vc
            self.sprite = vc.for_agent(self.cursor_id, agent_name or owner_id)
        except Exception:  # noqa: BLE001 - no overlay (headless CI): still drives, minus the sprite
            pass
        self.trace: List[Tuple[int, int]] = []
        self.actions: List[Dict[str, Any]] = []

    def _validate(self, pts: List[Tuple[int, int]]) -> Tuple[bool, str, Optional[Rect]]:
        first_rect: Optional[Rect] = None
        for (sx, sy) in pts:
            ok, r = owns_point(self.owner_id, sx, sy)
            if not ok:
                return False, (f"action refused: ({sx},{sy}) is outside '{self.owner_id}'s claimed "
                               f"regions (window claims: {claims_of(self.top) or 'none'})"), None
            first_rect = first_rect or r
        return True, "", first_rect

    def click(self, sx: int, sy: int, *, right: bool = False, double: bool = False) -> Dict[str, Any]:
        return self._run("click",
                         lambda: hin.post_click(self.top, sx, sy, right=right, double=double),
                         [(sx, sy)])

    def stroke(self, pts: List[Tuple[int, int]], *, duration_s: float = 0.6, button: str = "left") -> Dict[str, Any]:
        pts = [(int(x), int(y)) for x, y in pts]
        if len(pts) < 2:
            return {"ok": False, "note": "a stroke needs >= 2 points", "owner": self.owner_id}
        return self._run(
            "stroke",
            lambda: hin.post_drag(self.top, pts[0][0], pts[0][1], pts[-1][0], pts[-1][1],
                                  path=pts, duration_s=duration_s, button=button,
                                  on_point=lambda x, y: self.trace.append((int(x), int(y)))),
            pts)

    def _run(self, kind: str, call, pts: List[Tuple[int, int]]) -> Dict[str, Any]:
        ok_v, why, region = self._validate(pts)
        entry: Dict[str, Any] = {"action": kind, "owner": self.owner_id, "top": self.top, "points": len(pts)}
        if not ok_v:
            entry.update({"ok": False, "refused": True, "wait_ms": 0, "t_hold_start": time.perf_counter(),
                          "t_hold_end": time.perf_counter()})
            self._record(entry, why)
            return entry
        child = hin.child_at(self.top, pts[0][0], pts[0][1])
        entry["child"] = int(child)
        lk = child_lock(child)
        t_request = time.perf_counter()
        with lk:
            t_hold_start = time.perf_counter()
            # re-check under the lock: another owner could have claimed the space while we waited
            ok_v2, why2, _ = self._validate(pts)
            if not ok_v2:
                entry.update({"ok": False, "refused": True, "wait_ms": 0,
                              "t_hold_start": t_hold_start, "t_hold_end": time.perf_counter()})
                self._record(entry, why2)
                return entry
            ok, note = call()
        entry.update({"ok": bool(ok), "note": note, "region": list(region or []),
                      "t_hold_start": t_hold_start, "t_hold_end": time.perf_counter(),
                      "wait_ms": int((t_hold_start - t_request) * 1000)})
        self._record(entry, note)
        return entry

    def _record(self, entry: Dict[str, Any], note: str) -> None:
        entry["note"] = note
        self.actions.append(entry)
        with _lock:
            _timeline.append(dict(entry))

    def describe(self) -> Dict[str, Any]:
        return {"owner": self.owner_id, "cursor_id": self.cursor_id, "sprite": self.sprite is not None,
                "actions": len(self.actions), "trace_points": len(self.trace),
                "refused": sum(1 for a in self.actions if a.get("refused"))}

    def close(self) -> None:
        try:
            from core_organs import visual_cursor as vc
            vc.release_agent(self.cursor_id)
        except Exception:  # noqa: BLE001
            pass
        release(self.top, self.owner_id)


def parallelism_report(top_hwnd: int, owner_ids: List[str]) -> Dict[str, Any]:
    """Measured concurrency from the action timeline: time windows where two owners held DIFFERENT
    child windows at once (real parallelism) versus time an owner spent waiting on another owner's
    child lock (the honest serialized cost, with its reason)."""
    with _lock:
        acts = [a for a in _timeline
                if a.get("top") == int(top_hwnd) and a.get("owner") in owner_ids and not a.get("refused")]
    concurrent_ms = 0.0
    pairs: List[str] = []
    held = [a for a in acts if "t_hold_start" in a and "t_hold_end" in a]
    for i in range(len(held)):
        for j in range(i + 1, len(held)):
            a, b = held[i], held[j]
            if a["owner"] == b["owner"]:
                continue
            if int(a.get("child") or 0) == int(b.get("child") or 0):
                continue  # same child = serialized by the lock, not concurrency
            lo = max(a["t_hold_start"], b["t_hold_start"])
            hi = min(a["t_hold_end"], b["t_hold_end"])
            if hi > lo:
                concurrent_ms += (hi - lo) * 1000.0
                pairs.append(f"{a['owner']}+{b['owner']} on children {a.get('child')}/{b.get('child')}")
    serialized_ms = sum(max(0, a.get("wait_ms", 0)) for a in acts)
    degraded = bool(serialized_ms) and concurrent_ms == 0.0
    return {
        "owners": list(owner_ids),
        "actions": len(acts),
        "refused": sum(1 for a in _timeline if a.get("top") == int(top_hwnd)
                       and a.get("owner") in owner_ids and a.get("refused")),
        "concurrent_ms": round(concurrent_ms, 1),
        "serialized_wait_ms": int(serialized_ms),
        "concurrency": ("parallel" if concurrent_ms > 0 else
                        ("serialized" if degraded else "no overlap measured")),
        "reason_when_serialized": SAME_CHILD_REASON if degraded else "",
        "concurrent_pairs": pairs[:4],
    }
