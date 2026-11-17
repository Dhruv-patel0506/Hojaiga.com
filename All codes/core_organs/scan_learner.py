"""
scan_learner.py — the BACKGROUND half of the tiered deep scan.

`fast_scan.deep_scan` answers "what is on screen and where" within its budget and returns; THIS module
is what keeps working after the return: a per-app background job that opens the unknown surfaces one by
one (organ_63's persisted frontier: ranked by expected information gain, every probe with a verified
unwind, E2 never touched, invisible via BackgroundSession) until the app is mapped or the budget runs
out. Learning status is persisted in `bm_learn_state` (organ_48) so ANY later caller — the brain, the
capability card, another process — knows how much of this app is actually learned, instead of guessing.

Honest by construction:
  * the status is written from the REAL run outcome: complete only when organ_63 says the frontier
    converged; anything else is partial; a crash is kept as failed:<type>: <msg>, never swallowed;
  * a "learning" row whose thread is not alive in THIS process is reported as stale, not as running;
  * it never launches anything the scan did not already touch by name: organ_63.master owns the
    invisible-launch/close policy exactly as it does when a user asks for mastery directly;
  * it waits for the user to stop giving input (bounded) before pressing anything, AND pauses between probes
    if the user returns mid-run (bounded, then stops politely - the persisted frontier makes it resumable):
    probes are invisible, but a key that landed on the user's window while they typed would not be.

Opt out entirely: HOJAIGA_SCAN_LEARN=0.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.scan_learner")

ENABLED = os.environ.get("HOJAIGA_SCAN_LEARN", "1") != "0"
BUDGET_S = float(os.environ.get("HOJAIGA_LEARN_BUDGET_S", "120"))
RUNS = int(os.environ.get("HOJAIGA_LEARN_RUNS", "2"))          # 2 passes: frontier continues where pass 1 stopped
IDLE_S = float(os.environ.get("HOJAIGA_LEARN_IDLE_S", "4"))    # user input this quiet before probes may start
IDLE_WAIT_MAX_S = float(os.environ.get("HOJAIGA_LEARN_IDLE_WAIT_S", "45"))
RESUME_WAIT_S = float(os.environ.get("HOJAIGA_LEARN_RESUME_WAIT_S", "20"))   # per-probe pause cap once a human returns

_THREADS: Dict[str, threading.Thread] = {}     # app_key -> live learner thread (this process)
_LOCK = threading.Lock()


def _idle_seconds() -> float:
    """Seconds since the LAST physical user input (keyboard/mouse) on this machine."""
    try:
        class _INFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32), ("dwTime", ctypes.c_uint32)]
        info = _INFO()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)
    except Exception:  # noqa: BLE001
        return IDLE_S          # unmeasurable: treat as "quiet enough", the probes themselves are invisible


def _version_hash(bm, hwnd: int) -> str:
    try:
        return bm.app_version_hash(bm._exe_of_hwnd(hwnd))
    except Exception:  # noqa: BLE001
        return ""


def status(app_key: str, *, model=None) -> Dict[str, Any]:
    """The honest learning state of one app, as the card/brain sees it: what the DB says, corrected by
    whether the thread that claimed to be learning is actually alive in THIS process."""
    from core_organs import organ_48_app_behavior_model as bm
    model = model or bm.get_model()
    row = model.get_learn_state(app_key)
    if not row:
        return {"status": "none", "why": "never scanned/learned on this machine"}
    st, out = row["status"], dict(row)
    if st == "learning":
        thr = _THREADS.get(app_key)
        if thr is None or not thr.is_alive():
            age = time.time() - float(row.get("updated_ts") or 0)
            out["status"] = "stale"
            out["why"] = (f"a learner marked this app 'learning' {int(age)} s ago but no such thread is running "
                          "(the process that started it is gone); the knowledge gathered before that point stands")
    return out


def learn_in_background(target: str, hwnd: int, *, model=None, budget_s: Optional[float] = None) -> Dict[str, Any]:
    """Kick off (or decline) background learning for `target` after a scan. Never blocks; never raises.
    Returns {'started': bool, 'status': ..., 'why': ...} for the scan report."""
    if not ENABLED:
        return {"started": False, "status": "disabled", "why": "HOJAIGA_SCAN_LEARN=0"}
    if not hwnd:
        return {"started": False, "status": "none", "why": "the scan has no window to learn from"}
    from core_organs import organ_48_app_behavior_model as bm
    model = model or bm.get_model()
    key = bm._app_key(target)
    budget = float(budget_s if budget_s is not None else BUDGET_S)
    vh = _version_hash(bm, hwnd)
    with _LOCK:
        thr = _THREADS.get(key)
        if thr is not None and thr.is_alive():
            return {"started": False, "status": "learning", "why": "a learner is already running for this app"}
        cur = status(key, model=model)
        if cur.get("status") == "complete" and cur.get("version_hash") == vh and vh:
            return {"started": False, "status": "complete",
                    "why": "the frontier for this app version already converged"}
        t = threading.Thread(target=_run, args=(target, int(hwnd), key, vh, budget),
                             daemon=True, name=f"scan-learner-{key}")
        _THREADS[key] = t
        try:
            model.set_learn_state(key, vh, "pending", budget_s=budget)
        except Exception:  # noqa: BLE001
            pass
        t.start()
    return {"started": True, "status": "pending", "why": "background learner queued (invisible, resumable)",
            "budget_s": budget}


def _clear_startup_modals(bm, model, m63, hwnd: int, key: str, stats: Dict[str, Any]) -> None:
    """Apps often open a MODAL first (crash prompt, updater, license). Measured production bug on OBS
    Studio: the learner's frontier snapshot saw ONLY the dialog's OK button (1 row) and learning
    'converged' on almost nothing. Capture whatever is already open AS KNOWLEDGE (its schema is real
    knowledge), then dismiss it with Escape/WM_CLOSE - never by pressing its buttons - so the app
    underneath can be learned. Covers classic OWNED popups AND same-process UNOWNED top-levels:
    Qt shows startup 'Error'/'Welcome' modals with owner=0, which owner-based detection misses (measured)."""
    base = list(bm._open_popups(hwnd))
    try:
        import win32gui, win32process
        r = win32gui.GetWindowRect(hwnd)
        main_area = max(1, (r[2] - r[0]) * (r[3] - r[1]))
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        rejected: List[str] = []

        def _cb(h, acc):
            if h == hwnd:
                return
            try:
                if win32process.GetWindowThreadProcessId(h)[1] != pid:
                    return
                rr = win32gui.GetWindowRect(h)
                area = (rr[2] - rr[0]) * (rr[3] - rr[1])
                if area <= 0 or area >= main_area:               # nothing as big as the app itself
                    return
                vis = bool(win32gui.IsWindowVisible(h))
                ttl = win32gui.GetWindowText(h) or ""
                cls = win32gui.GetClassName(h) or ""
                # a dialog to capture/close: visible and NAMED, or an unmistakable dialog class.
                # (measured: OBS's startup QMessageBox was missed by a visible+title filter)
                if not (vis and ttl) and cls not in ("#32770", "#32768") and "messagebox" not in cls.lower():
                    if len(rejected) < 12:                        # honest breadcrumb of what we waved past
                        rejected.append(f"{cls[:26]}|'{ttl[:16]}'|vis={int(vis)}|a={area}")
                    return
                acc.append(h)
            except Exception:  # noqa: BLE001
                pass
        sib: List[int] = []
        win32gui.EnumWindows(_cb, sib)
        if rejected:
            stats["sib_rejected"] = rejected
        for w in sib:
            if w not in base:
                base.append(w)
    except Exception:  # noqa: BLE001
        pass
    if not base:
        return
    try:
        got = m63.capture_dialogs(model, key, base, via="(already open when learning began)")
        stats["pre_modals"] = [g["title"] for g in got] or [bm._win_title(w) or bm._win_class(w) for w in base]
    except Exception as exc:  # noqa: BLE001
        stats["pre_modals"] = f"{bm._win_title(base[0]) or bm._win_class(base[0])} (capture error: {type(exc).__name__})"
    from core_organs import headless_input as hin
    import ctypes
    deadline = time.time() + 3.0
    alive, first = list(base), True
    while alive and time.time() < deadline:
        for w in alive:
            try:
                if first:
                    hin.post_key_combo(w, "escape")
                else:
                    ctypes.windll.user32.PostMessageW(w, 0x0010, 0, 0)     # WM_CLOSE
            except Exception:  # noqa: BLE001
                pass
        first = False
        time.sleep(0.5)
        try:
            import win32gui
            alive = [w for w in alive if win32gui.IsWindow(w)]
        except Exception:  # noqa: BLE001
            alive = []
    stats["pre_modals_closed"] = not alive
    if not alive:
        time.sleep(0.6)          # let the app underneath lay out


def _run(target: str, hwnd: int, key: str, vh: str, budget_s: float) -> None:
    from core_organs import organ_48_app_behavior_model as bm
    model = bm.BehaviorModel(bm.DB_PATH)          # own sqlite connection: this is another thread
    stats: Dict[str, Any] = {"budget_s": budget_s}
    try:
        # wait for a quiet machine, bounded: an unattended box passes instantly, a busy one starts
        # after the cap anyway (probes are parked invisible; only delivery order is at stake)
        waited = 0.0
        while waited < IDLE_WAIT_MAX_S and _idle_seconds() < IDLE_S:
            time.sleep(0.5)
            waited += 0.5
        stats["idle_wait_s"] = round(waited, 1)
        model.set_learn_state(key, vh, "learning", budget_s=budget_s, stats=stats)
        from core_organs import organ_63_app_mastery as m63
        # ---- startup-modal hygiene (measured on OBS Studio 2026-10-07): see _clear_startup_modals.
        # Repeated as a short watch: measured, OBS's crash prompt appears ~5 s AFTER the scan returns,
        # so a one-shot check at learner start sees nothing (sib_rejected breadcrumb proved the race) and
        # the poisoned snapshot follows. Three passes, 4 s apart; a pass with nothing open costs ~ms.
        try:
            for _hp in range(3):
                _clear_startup_modals(bm, model, m63, hwnd, key, stats)
                if _hp < 2:
                    time.sleep(4.0)
        except Exception as exc:  # noqa: BLE001
            stats["pre_modals"] = f"error: {type(exc).__name__}: {str(exc)[:100]}"
        # cooperative pause gate handed to the prober: between EVERY probe, if a human has taken over the
        # machine we wait (bounded) for quiet and, if they keep it busy past the cap, stop THIS run politely.
        # The frontier is persisted, so the next pass resumes exactly where we stopped. This closes the gap the
        # audit flagged: idle was checked ONCE before starting, never DURING probing.
        _p = {"n": 0}

        def _gate() -> bool:
            w = 0.0
            while _idle_seconds() < IDLE_S and w < RESUME_WAIT_S:
                time.sleep(0.5)
                w += 0.5
            if w > 0:
                _p["n"] += 1
            return _idle_seconds() >= IDLE_S

        out = m63.master(target, model=model, budget_s=budget_s, runs=RUNS, fresh=False,
                         close_if_launched=True, gate=_gate)
        known = out.get("known") or {}
        runs = out.get("runs") or []
        stats["pause_points"] = _p["n"]
        stats["paused_for_user"] = any((r.get("explore") or {}).get("stopped") == "user-active" for r in runs)
        errors = [r.get("error") or r.get("error_live") for r in runs if (r.get("error") or r.get("error_live"))]
        stats.update(converged=bool(out.get("converged")), n_runs=len(runs),
                     commands=known.get("commands"), learned=known.get("commands_learned"),
                     transitions=known.get("transitions"), regions=known.get("regions"),
                     frontier=known.get("frontier"))
        if errors:
            stats["run_errors"] = [str(e)[:160] for e in errors][:3]
        # what HALTED each pass, honestly (budget / exhausted / user-active / circuit: the explore()
        # unwind-failure rail): a stopped run says WHY in the persisted state, not just "partial".
        stats["stopped"] = [((r.get("explore") or {}).get("stopped") or r.get("stopped") or "") for r in runs][:RUNS + 1]
        stats["unwind_failures"] = [((r.get("explore") or {}).get("unwind_failures") or {}) for r in runs][:RUNS + 1]
        # ---- paths & recipes: join the dialogs THIS learning actually observed into reachable step-paths
        # (organ_48.compose_paths reads ONLY observed rows; nothing is invented), then record the scorecard.
        try:
            comp = bm.compose_paths(model, key)
            stats["paths_composed"] = comp.get("composed")
            if comp.get("skipped"):
                stats["paths_skipped"] = comp["skipped"][:4]
        except Exception as exc:  # noqa: BLE001
            stats["paths_composed"] = f"error: {type(exc).__name__}: {str(exc)[:100]}"
        try:
            stats["quality"] = bm.knowledge_quality(model, key).get("one_line")
        except Exception as exc:  # noqa: BLE001
            stats["quality"] = f"error: {type(exc).__name__}"
        # A pass blocked by a startup modal we could not dismiss (organ_63's guard) says nothing about the
        # APP - its snapshot was the dialog's - so the state must stay resumable: 'complete' would make
        # learn_in_background decline this version forever (measured on OBS: 1-row poisoned frontier).
        blocked = [str(r.get("exploration_blocked")) for r in runs if r.get("exploration_blocked")]
        if blocked:
            stats["exploration_blocked"] = blocked[:2]
        status_txt = "complete" if (out.get("converged") and not blocked) else "partial"
        model.set_learn_state(key, vh, status_txt, budget_s=budget_s, stats=stats)
        logger.info("[scan-learner] %s: %s (%s)", key, status_txt, stats.get("quality"))
    except Exception as exc:  # noqa: BLE001
        stats["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        try:
            model.set_learn_state(key, vh, "failed", budget_s=budget_s, stats=stats)
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[scan-learner] %s failed: %s", key, stats["error"])
    finally:
        with _LOCK:
            if _THREADS.get(key) is threading.current_thread():
                _THREADS.pop(key, None)
        model.close()


def join_all(timeout_s: float = 0.0) -> int:
    """Test/boundary helper: wait up to timeout_s for every learner this process started. Returns how
    many were still running when it returned."""
    with _LOCK:
        threads = [t for t in _THREADS.values() if t.is_alive()]
    still = 0
    end = time.time() + timeout_s if timeout_s > 0 else None
    for t in threads:
        left = None if end is None else max(0.0, end - time.time())
        t.join(timeout=left)
        still += 1 if t.is_alive() else 0
    return still
