r"""
state_keeper.py — the RESTORE-APP-UI-TO-ORIGINAL-STATE law (work order [6]).

The law: after the automation has changed and saved what the task asked for, the app must
be left in the interface the USER had before we touched it. Not "closed", not "reset" -
returned. Specifically we undo OUR side effects and never the user's:

  * dialogs/popups/flyouts that did NOT exist when we started  -> closed (ours only)
  * menus/expanders we opened                                  -> collapsed
  * scroll positions we moved                                  -> put back
  * active tab / selected item we switched                     -> re-selected
  * window show-state (minimized/normal) and placement         -> exactly as found
  * foreground focus                                           -> handed back to its prior owner
  * document content                                           -> NOT reverted (the saved change is the point)
  * anything that was already there when we started            -> NOT touched, and said so in the report

Every window is snapshotted at FIRST SIGHT (`observe`), so a snapshot cost is paid once per
window per task, and `close_sessions()` runs the restore on the completion path AND on the
abort path (organ_01 calls it in a finally). The report is honest: `refused` lists what we
deliberately left alone, `degraded` lists what we tried and could not put back. Nothing in
this module knows any app's name.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_u32 = ctypes.windll.user32

_LOCK = threading.Lock()
# hwnd -> pre-state snapshot; the ONE record of "what the user left us with"
_sessions: Dict[int, Dict[str, Any]] = {}

MAX_SCROLL_NODES = 12


def _class_name(hwnd: int) -> str:
    b = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(hwnd, b, 256)
    return b.value


def _title(hwnd: int) -> str:
    b = ctypes.create_unicode_buffer(200)
    _u32.GetWindowTextW(hwnd, b, 200)
    return b.value


def _root_owner(hwnd: int) -> int:
    try:
        return int(_u32.GetAncestor(hwnd, 3) or 0) or int(hwnd)   # GA_ROOTOWNER
    except Exception:  # noqa: BLE001
        return int(hwnd)


def _node_key(ctype: str, aid: str, name: str) -> str:
    """A stable identity for a UIA node that survives a re-scan (no index, which drifts)."""
    return f"{ctype}|{aid or ''}|{(name or '')[:36]}"


class _WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT),
                ("ptMinPos", wt.POINT), ("ptMaxPos", wt.POINT), ("rcNormalPosition", wt.RECT)]


def _placement_rect(hwnd: int) -> Optional[Tuple[Tuple[int, int, int, int], int]]:
    """((normal rect), showCmd) as Windows keeps them; None when the call fails."""
    p = _WINDOWPLACEMENT()
    p.length = ctypes.sizeof(_WINDOWPLACEMENT)
    if not _u32.GetWindowPlacement(hwnd, ctypes.byref(p)):
        return None
    r = p.rcNormalPosition
    return ((r.left, r.top, r.right, r.bottom), int(p.showCmd))


def snapshot(hwnd: int, *, with_uia: bool = True) -> Dict[str, Any]:
    """Everything the law cares about, as it is RIGHT NOW. Cheap and side-effect free."""
    hwnd = int(hwnd)
    snap: Dict[str, Any] = {
        "hwnd": hwnd, "at": time.time(),
        "alive": bool(_u32.IsWindow(hwnd)),
        "iconic": bool(_u32.IsIconic(hwnd)),
        "visible": bool(_u32.IsWindowVisible(hwnd)),
        "placement": _placement_rect(hwnd),
        "popups": [], "selected": [], "expanded": [], "scroll": {},
        "uia": "skipped",
    }
    fg = int(_u32.GetForegroundWindow() or 0)
    snap["foreground_root"] = _root_owner(fg) if fg else 0
    snap["was_foreground"] = bool(fg) and _root_owner(fg) == _root_owner(hwnd)
    # who exactly held the user's focus at first sight (class+title ride along, so a failed hand-back at
    # the end of a task can be READ, not guessed): the honest report names the window we could not return to
    try:
        from core_organs import headless_input as hin
        snap["foreground"] = {"hwnd": fg, "cls": _class_name(fg) if fg else "",
                              "title": hin.safe_window_text(fg) if fg else ""}
    except Exception:  # noqa: BLE001
        snap["foreground"] = {"hwnd": fg, "cls": "", "title": ""}
    try:
        from core_organs import headless_input as hin
        snap["popups"] = [{"hwnd": int(w), "cls": _class_name(w), "title": _title(w)}
                          for w in hin.popup_windows(hwnd)]
    except Exception as exc:  # noqa: BLE001
        snap["popups_error"] = f"{type(exc).__name__}: {exc}"
    if with_uia:
        try:
            from core_organs import fast_uia
            rows = fast_uia.snapshot(hwnd) or []
            sel, exp, scr = [], [], {}
            for n in rows:
                k = _node_key(n.ctype, n.aid, n.name)
                if n.selected is True:
                    sel.append(k)
                if int(n.expand_state or -1) == 1:            # ExpandCollapseState.Expanded
                    exp.append(k)
                if "scroll" in (n.pats or []) and len(scr) < MAX_SCROLL_NODES:
                    try:
                        pat = n.ctrl.GetScrollPattern()
                        if pat is not None:
                            scr[k] = (round(float(pat.CurrentHorizontalScrollPercent), 1),
                                      round(float(pat.CurrentVerticalScrollPercent), 1))
                    except Exception:  # noqa: BLE001 - one unreadable scroller must not lose the snapshot
                        continue
            snap["selected"] = sorted(sel)
            snap["expanded"] = sorted(exp)
            snap["scroll"] = scr
            snap["nodes"] = len(rows)
            snap["uia"] = "ok" if rows else "empty"
        except Exception as exc:  # noqa: BLE001
            snap["uia"] = f"error: {type(exc).__name__}: {str(exc)[:60]}"
    return snap


def observe(hwnd: int) -> Dict[str, Any]:
    """Record the user's state for this window at FIRST SIGHT; later calls return the stored record."""
    hwnd = int(hwnd or 0)
    if not hwnd:
        return {}
    with _LOCK:
        existing = _sessions.get(hwnd)
        if existing and existing.get("alive", False):
            return existing
        snap = snapshot(hwnd)
        _sessions[hwnd] = snap
        return snap


def is_observed(hwnd: int) -> bool:
    with _LOCK:
        return int(hwnd or 0) in _sessions


def diff(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    """What the automation changed, dimension by dimension (content is deliberately excluded)."""
    base = {h["hwnd"] for h in pre.get("popups") or []}
    now = {h["hwnd"] for h in post.get("popups") or []}
    scroll_pre, scroll_post = pre.get("scroll") or {}, post.get("scroll") or {}
    scroll_moved = {k: (scroll_pre.get(k), scroll_post.get(k))
                    for k in set(scroll_pre) | set(scroll_post)
                    if scroll_pre.get(k) != scroll_post.get(k)}
    return {
        "new_popups": sorted(now - base),
        "gone_popups": sorted(base - now),
        "expanded_new": sorted(set(post.get("expanded") or []) - set(pre.get("expanded") or [])),
        "selected_changed": (sorted(pre.get("selected") or []) != sorted(post.get("selected") or [])),
        "scroll_moved": scroll_moved,
        "iconic_changed": bool(pre.get("iconic")) != bool(post.get("iconic")),
        "placement_changed": pre.get("placement") != post.get("placement"),
        "foreground_taken": bool(post.get("was_foreground")) and not bool(pre.get("was_foreground")),
    }


def _close_our_popups(hwnd: int, pre: Dict[str, Any]) -> Tuple[List[int], List[str]]:
    """Close ONLY windows that appeared after the snapshot. Degraded note when a close raises a
    save/discard prompt: the non-destructive branch (Cancel) is taken and the dialog is left open -
    user data is never discarded to make a report look clean."""
    base = [h["hwnd"] for h in pre.get("popups") or []]
    notes: List[str] = []
    try:
        from core_organs import organ_48_app_behavior_model as bm
        clean = bm._close_new_windows(hwnd, base, timeout_s=2.5)
    except Exception as exc:  # noqa: BLE001
        return [], [f"popup unwind unavailable: {type(exc).__name__}: {exc}"]
    from core_organs import headless_input as hin
    for w in [int(x) for x in hin.popup_windows(hwnd) if int(x) not in base]:
        # a confirmation prompt raised by OUR close is answered on the NON-DESTRUCTIVE branch,
        # so a "save changes?" dialog never costs the user their data
        try:
            import uiautomation as auto
            el = auto.ControlFromHandle(w)
            kids = list(el.GetChildren() or []) if el else []
            flat = " ".join((c.Name or "") for c in kids).lower()
            if any(k in flat for k in ("save", "discard", "don't save", "unsaved")):
                for c in kids:
                    nm = (c.Name or "").strip().lower()
                    if nm in ("cancel", "no", "close") and hasattr(c, "GetInvokePattern"):
                        pat = c.GetInvokePattern()
                        if pat is not None:
                            pat.Invoke()
                            notes.append(f"confirmation dialog {w}: answered the non-destructive branch")
                        break
        except Exception:  # noqa: BLE001
            pass
    still = [int(w) for w in hin.popup_windows(hwnd) if int(w) not in base]
    if not clean or still:
        notes.append(f"popups still open after unwind: {still} (reported, not left silently)")
    return still, notes


def _collapse_menus_we_opened(post: Dict[str, Any], pre_expanded: List[str]) -> Tuple[int, List[str]]:
    opened = sorted(set(post.get("expanded") or []) - set(pre_expanded or []))
    if not opened:
        return 0, []
    collapsed, notes = 0, []
    try:
        from core_organs import fast_uia
        rows = post.get("_rows") or []
        if not rows:
            hwnd = int(post.get("hwnd") or 0)
            rows = fast_uia.snapshot(hwnd) or []
        for n in reversed(rows):
            k = _node_key(n.ctype, n.aid, n.name)
            if k in opened:
                try:
                    n.ctrl.GetExpandCollapsePattern().Collapse()
                    collapsed += 1
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"could not collapse '{k[:40]}': {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"menu unwind unavailable: {type(exc).__name__}: {exc}")
    return collapsed, notes


def _restore_scroll(post: Dict[str, Any], pre_scroll: Dict[str, Any]) -> Tuple[int, List[str]]:
    restored, notes = 0, []
    try:
        from core_organs import fast_uia
        hwnd = int(post.get("hwnd") or 0)
        rows = fast_uia.snapshot(hwnd) or []
        for n in rows:
            k = _node_key(n.ctype, n.aid, n.name)
            if k in pre_scroll and (post.get("scroll") or {}).get(k) != pre_scroll[k]:
                want = pre_scroll[k]
                if want is None or any(v == -1.0 for v in want):
                    continue                      # UIA scroll percent unknown/offscreen: nothing honest to set
                try:
                    pat = n.ctrl.GetScrollPattern()
                    if pat is not None:
                        pat.SetScrollPercent(float(want[0]), float(want[1]))
                        restored += 1
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"scroll '{k[:40]}' not restored: {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"scroll unwind unavailable: {type(exc).__name__}: {exc}")
    return restored, notes


def _restore_tab(post: Dict[str, Any], pre_selected: List[str]) -> Tuple[Optional[str], bool, List[str]]:
    """Re-select the tab/list item the user had active when we started (if we moved it).
    Returns (restored_key, pre_item_still_exists_in_tree, notes)."""
    notes: List[str] = []
    now_selected = sorted(post.get("selected") or [])
    if not pre_selected or now_selected == sorted(pre_selected):
        return None, False, notes
    try:
        from core_organs import fast_uia
        hwnd = int(post.get("hwnd") or 0)
        rows = fast_uia.snapshot(hwnd) or []
        tree_keys = {_node_key(n.ctype, n.aid, n.name) for n in rows}
        found_pre = any(k in tree_keys for k in pre_selected)
        if not found_pre:
            return None, False, notes          # renamed away (e.g. by the saved change): nothing to re-select
        for n in rows:
            k = _node_key(n.ctype, n.aid, n.name)
            if k in set(pre_selected):
                try:
                    n.ctrl.GetSelectionItemPattern().Select()
                    return k, True, notes
                except Exception as exc:  # noqa: BLE001
                    try:
                        n.ctrl.GetInvokePattern().Invoke()
                        return k, True, notes
                    except Exception as exc2:  # noqa: BLE001
                        notes.append(f"tab '{k[:40]}' not restored: {type(exc2).__name__}")
                        return None, True, notes
        notes.append(f"pre-active item {pre_selected[0][:40]} not found in the current tree")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"tab unwind unavailable: {type(exc).__name__}: {exc}")
    return None, False, notes


def _restore_window_state(hwnd: int, pre: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Show-state, placement and focus exactly as found. No-ops in the common case."""
    notes: List[str] = []
    out = {"iconic": bool(pre.get("iconic")), "placement": pre.get("placement"), "focus": None}
    if not _u32.IsWindow(hwnd):
        return out, ["window gone - nothing to restore (reported, not faked)"]
    want_iconic = bool(pre.get("iconic"))
    now_iconic = bool(_u32.IsIconic(hwnd))
    if want_iconic and not now_iconic:
        _u32.ShowWindow(hwnd, 7)                       # SW_SHOWMINNOACTIVE: never steals focus
        time.sleep(0.2)
        now_iconic = bool(_u32.IsIconic(hwnd))
    elif not want_iconic and now_iconic:
        _u32.ShowWindow(hwnd, 4)                       # SW_SHOWNOACTIVATE: show without borrowing focus
        time.sleep(0.2)
        now_iconic = bool(_u32.IsIconic(hwnd))
    if now_iconic != want_iconic:
        notes.append(f"show-state stuck at iconic={now_iconic}, wanted {want_iconic}")
    place = _placement_rect(hwnd)
    if pre.get("placement") and place and tuple(place[0]) != tuple(pre["placement"][0]) and not want_iconic:
        try:
            p = _WINDOWPLACEMENT()
            p.length = ctypes.sizeof(_WINDOWPLACEMENT)
            _u32.GetWindowPlacement(hwnd, ctypes.byref(p))
            l, t, r, b = pre["placement"][0]
            p.rcNormalPosition = wt.RECT(l, t, r, b)
            p.showCmd = pre["placement"][1]
            _u32.SetWindowPlacement(hwnd, ctypes.byref(p))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"placement not restored: {type(exc).__name__}")
    # focus: give it back to whoever held it when we started (only if we are holding it now)
    fg = int(_u32.GetForegroundWindow() or 0)
    pre_fg = int(pre.get("foreground_root") or 0)
    if fg and _root_owner(fg) == _root_owner(hwnd) and pre_fg and pre_fg != _root_owner(hwnd):
        if _u32.IsWindow(pre_fg):
            from core_organs import headless_input as hin
            hin._hand_back_focus(pre_fg)
            out["focus"] = f"handed back to {pre_fg}"
        else:
            _pre_info = pre.get("foreground") or {}
            notes.append(f"prior foreground {pre_fg} ('{str(_pre_info.get('title', ''))[:40]}|{_pre_info.get('cls', '')}') "
                         f"no longer exists (nothing to hand back to)")
    return out, notes


def restore(hwnd: int, *, drop: bool = True) -> Dict[str, Any]:
    """Run the law on one window: undo our side effects, leave the user's alone, report honestly."""
    hwnd = int(hwnd)
    with _LOCK:
        pre = _sessions.get(hwnd)
    if not pre:
        return {"hwnd": hwnd, "status": "not-observed",
                "note": "no pre-state was ever recorded for this window; refusing to guess a state to restore"}
    if not _u32.IsWindow(hwnd):
        # the window died during the task (app quit / user closed it): nothing to return to, said plainly
        with _LOCK:
            _sessions.pop(hwnd, None)
        return {"hwnd": hwnd, "status": "window-gone",
                "note": "the window no longer exists; there is no UI left to restore (reported, not faked)"}
    post = snapshot(hwnd)
    d = diff(pre, post)
    report: Dict[str, Any] = {"hwnd": hwnd, "aborted_snapshot": dict(d), "restored": {}, "degraded": [],
                              "refused": [f"left pre-existing dialog {h['hwnd']} ('{h['title'][:30]}')"
                                          for h in pre.get("popups") or []],
                              "content_note": "document content was NOT reverted (the saved change is the task)"}

    still_open, n1 = _close_our_popups(hwnd, pre)
    report["restored"]["popups_closed_to_baseline"] = max(0, len(d["new_popups"]) - len(still_open))
    if still_open:
        report["restored"]["popups_still_open"] = still_open
    report["degraded"] += n1

    collapsed, n2 = _collapse_menus_we_opened(post, pre.get("expanded") or [])
    report["restored"]["menus_collapsed"] = collapsed
    report["degraded"] += n2

    scrolled, n3 = _restore_scroll(post, pre.get("scroll") or {})
    report["restored"]["scroll_positions_put_back"] = scrolled
    report["degraded"] += n3

    tab, found_pre, n4 = _restore_tab(post, pre.get("selected") or [])
    if tab:
        report["restored"]["active_tab"] = tab
    # a pre-active item that NO LONGER EXISTS in the tree was renamed by the intended (saved) change - the
    # law never treats our own saved edit as a UI violation. A pre-active item that still EXISTS but is
    # not selected means WE switched it: that must come back, and a failed restore stays a degraded note.
    if not tab and pre.get("selected") and not found_pre:
        report["restored"]["active_tab_renamed_by_saved_change"] = (pre.get("selected") or [""])[0][:60]
    report["selected_violation"] = bool(found_pre) and sorted(post.get("selected") or []) != sorted(pre.get("selected") or [])
    report["degraded"] += n4

    win_state, n5 = _restore_window_state(hwnd, pre)
    report["restored"]["window_state"] = win_state
    report["degraded"] += n5

    final = snapshot(hwnd)
    d2 = diff(pre, final)
    # what focus looks like at the very end, named (so 'foreground_taken' is never an anonymous flag)
    try:
        report["focus_final"] = {"now": final.get("foreground"), "we_hold_it": bool(final.get("was_foreground")),
                                 "at_first_sight": pre.get("foreground")}
    except Exception:  # noqa: BLE001
        pass
    report["matches_pre_state"] = not (d2["new_popups"] or d2["expanded_new"] or d2["scroll_moved"]
                                       or d2["iconic_changed"] or d2["foreground_taken"]
                                       or report.get("selected_violation"))
    report["residual"] = {k: v for k, v in d2.items() if v}
    report["status"] = "restored" if report["matches_pre_state"] else "partially-restored"
    if drop:
        with _LOCK:
            _sessions.pop(hwnd, None)
    return report


def close_sessions() -> Dict[int, Dict[str, Any]]:
    """The end-of-task (and end-of-abort) hook: restore every window we observed this session."""
    with _LOCK:
        targets = list(_sessions.keys())
    out: Dict[int, Dict[str, Any]] = {}
    for h in targets:
        try:
            out[h] = restore(h)
        except Exception as exc:  # noqa: BLE001 - one bad window must not skip the rest of the law
            out[h] = {"hwnd": h, "status": "error", "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return out


@contextlib.contextmanager
def preserve(hwnd: int, *, label: str = ""):
    """`with preserve(hwnd): actuate()` - the law as a wrapper: the pre-state is recorded on entry and
    the restore runs on exit WHETHER the body finished or raised, so an abort is held to the same bar
    as a success. The restore's own failure never masks the body's exception."""
    pre = observe(hwnd)
    keeper = {"hwnd": int(hwnd), "label": label, "pre": pre, "report": None, "aborted": False}
    try:
        yield keeper
    except BaseException:
        keeper["aborted"] = True
        raise
    finally:
        try:
            keeper["report"] = restore(int(hwnd))
        except Exception as exc:  # noqa: BLE001
            keeper["report"] = {"hwnd": int(hwnd), "status": "error",
                                 "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
        if keeper["aborted"] and isinstance(keeper["report"], dict):
            keeper["report"]["aborted"] = True


def reset() -> None:
    with _LOCK:
        _sessions.clear()


def session_ledger() -> List[int]:
    with _LOCK:
        return sorted(_sessions.keys())
