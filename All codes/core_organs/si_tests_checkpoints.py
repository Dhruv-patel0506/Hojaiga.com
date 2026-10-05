"""
si_tests_checkpoints.py -- tests for the lifecycle checkpoints that were GAPS in the audit (skill 14):

  ES1  C2  a dialog that needs a human saves a screenshot of it as evidence (and says so in the run result)
  B2X  B2  a launch target whose executable is gone is reported and NOT retried (nothing else gets launched)
  C3X  C3  mode indicators (selected tab / open menu) are read with the snapshot and noticed by the default postcondition
  A3X  A3  a ticket a template covers runs template-first (no LLM planning); the chain says so
  G2L  G2  the app's window vanishes mid-run: relaunched ONCE, the run resumes and completes; vanishing again fails with evidence
"""

import os
import tempfile
import time
import uuid
from typing import List, Tuple


def run_es1(TestOutcome):
    from core_organs import desktop_grounding as dg
    from core_organs import si_test_support as sup
    from core_organs import si_tests_extra as ex
    from core_organs import headless_input as hin
    root = sup.NativeButtonWindow(title="HJ-ES1-Root").start()
    loop = dg.DesktopAutonomyLoop(grounding=dg.DesktopGrounding())
    loop.grounding.find_window = lambda hint, all_candidates=False: root.hwnd
    t, res = ex.show_messagebox("Do you want to allow this app to make changes to your device?", "User Account Control", 0x1 | 0x30)
    try:
        before = len(os.listdir(os.path.join(r"D:\new_automation\data", "escalations"))) if os.path.isdir(os.path.join(r"D:\new_automation\data", "escalations")) else 0
        loop._triage_popups("hj-es1")
        shots = list(loop.escalation_shots)
        ok_path = bool(shots) and os.path.exists(shots[0]["path"]) and os.path.getsize(shots[0]["path"]) > 2000
        valid_png = False
        if ok_path:
            with open(shots[0]["path"], "rb") as fh:
                valid_png = fh.read(8) == b"\x89PNG\r\n\x1a\n"
        checks = [("popup-engine-asked-for-a-human", loop.awaiting_human, f"awaiting_human={loop.awaiting_human}"),
                  ("screenshot-saved-as-a-real-png", ok_path and valid_png, f"{shots[0]['path'].rsplit(chr(92), 1)[-1] if shots else None}, "
                                                                           f"{os.path.getsize(shots[0]['path']) if ok_path else 0} bytes, png={valid_png}"),
                  ("dialog-left-open-for-the-human", any(hin.is_alive(d) for d in __import__('core_organs.popup_policy', fromlist=['x']).blocking_dialogs(root.hwnd)),
                   "no button was pressed")]
    finally:
        for d in __import__('core_organs.popup_policy', fromlist=['x']).blocking_dialogs(root.hwnd):
            hin._u32.PostMessageW(d, 0x0010, 0, 0)
        t.join(timeout=2)
        root.stop()
    failed = [n for n, ok, _d in checks if not ok]
    return TestOutcome(passed=not failed, evidence="; ".join(f"{n}={'OK' if ok else 'FAIL'}({d})" for n, ok, d in checks), metrics={"failed": len(failed)})


def run_b2x(TestOutcome):
    from core_organs import desktop_grounding as dg
    from core_organs import universal_scan as us
    from core_organs import headless_input as hin
    before = {h for h, _t in hin.top_level_titles(visible_only=False)}
    orig = us.start_apps
    launched_calls = []
    orig_launch = us.launch_hidden
    us.start_apps = lambda: [("HJ Ghost App", r"C:\hj_no_such_dir\ghost.exe")]
    us.launch_hidden = lambda *a, **k: launched_calls.append(a) or {"hwnd": 0, "notes": []}
    try:
        tgt = us.launch_target_status("HJ Ghost App")
        r = dg.operate_app("HJ Ghost App", ['type "x"'], max_steps_per_goal=1)
    finally:
        us.start_apps, us.launch_hidden = orig, orig_launch
    after = {h for h, _t in hin.top_level_titles(visible_only=False)}
    checks = [("target-checked-on-disk", tgt.get("kind") == "path" and tgt.get("exists") is False, str(tgt)),
              ("missing-exe-is-reported", "MISSING" in str(r.get("launch_note", "")), f"launch_note={r.get('launch_note')!r}"),
              ("no-launch-or-retry-attempted", not launched_calls and not r.get("launched"), f"launch_hidden calls={len(launched_calls)} launched={r.get('launched')}"),
              ("nothing-else-got-started", not (after - before), f"new windows={len(after - before)}"),
              ("task-not-reported-done", not r.get("completed"), f"completed={r.get('completed')}")]
    failed = [n for n, ok, _d in checks if not ok]
    return TestOutcome(passed=not failed, evidence="; ".join(f"{n}={'OK' if ok else 'FAIL'}({d[:120]})" for n, ok, d in checks), metrics={"failed": len(failed)})


def run_c3x(TestOutcome):
    from core_organs import desktop_grounding as dg
    from core_organs import universal_scan as us
    from core_organs import background_window as bw
    from core_organs import headless_input as hin
    checks: List[Tuple[str, bool, str]] = []
    v = dg.DesktopVerifier()
    a = dg.Snapshot(title="t", element_ids=["1"], names=["tab one", "tab two"], modes=["tab one|selected"])
    b = dg.Snapshot(title="t", element_ids=["1"], names=["tab one", "tab two"], modes=["tab two|selected"])
    ok, ev = v.check_expect({}, a, b, [])
    checks.append(("mode-only-change-is-noticed", ok and "modes" in ev, ev[:110]))
    ok_on, ev_on = v.check_expect({"mode_on": "tab two"}, a, b, [])
    ok_off, _ = v.check_expect({"mode_on": "tab one"}, a, b, [])
    checks.append(("mode_on-expectation", ok_on and not ok_off, ev_on))
    # live: a real window's selected tab / open menu is read with the names
    if any(hin._class_name(h) == "Notepad" for h, _t in hin.top_level_titles(visible_only=False)):
        checks.append(("live-modes-read", True, "SKIPPED: the user's Notepad is open; not touched"))
    else:
        info = us.launch_hidden("notepad", timeout_s=25.0)
        h = info.get("hwnd")
        try:
            loop = dg.DesktopAutonomyLoop(grounding=dg.DesktopGrounding())
            with bw.BackgroundSession(h):
                time.sleep(1.0)
                loop._all_names(h)
                modes = list(loop._last_modes)
            checks.append(("live-modes-read", any(m.endswith("|selected") for m in modes), f"{len(modes)} indicator(s): {modes[:3]}"))
        finally:
            us.close_window(h, discard_unsaved=True, timeout_s=8)
    failed = [n for n, ok, _d in checks if not ok]
    return TestOutcome(passed=not failed, evidence="; ".join(f"{n}={'OK' if ok else 'FAIL'}({d})" for n, ok, d in checks), metrics={"failed": len(failed)})


def run_a3x(TestOutcome):
    from core_organs import task_lifecycle as tl
    from core_organs import headless_input as hin
    from core_organs import si_tests_fixes as sf
    if not sf._judge_up():
        return TestOutcome(passed=False, env_blocked=True, evidence="local judge model (Ollama :11434) is not reachable (environment)")
    if any(hin._class_name(h) == "Notepad" for h, _t in hin.top_level_titles(visible_only=False)):
        return TestOutcome(passed=False, env_blocked=True, evidence="the user's Notepad is open; A3X will not drive it")
    before = sf._top_hwnds()
    path = os.path.join(tempfile.gettempdir(), "hj_a3x_" + uuid.uuid4().hex[:6] + ".txt")
    t0 = time.perf_counter()
    r = tl.run_lifecycle(f"open notepad, type template first works and save it as {path}")
    dt = time.perf_counter() - t0
    body = ""
    try:
        end = time.time() + 3
        while time.time() < end and not os.path.exists(path):
            time.sleep(0.3)
        body = open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""
    except OSError:
        pass
    a3 = next((c for c in r["checkpoints"] if c["id"] == "A3.template"), {})
    checks = [("template-ran-first", a3.get("status") == "PASS", f"A3.template={a3.get('status')}: {a3.get('evidence', '')[:130]}"),
              ("file-has-the-typed-words (independent read)", "template first works" in body.lower(), f"{body[:50]!r}"),
              ("ticket-done", r["status"] == "DONE", f"status={r['status']}")]
    try:
        os.remove(path)
    except OSError:
        pass
    closed = sf._close_new_windows(before)
    failed = [n for n, ok, _d in checks if not ok]
    return TestOutcome(passed=not failed, evidence="; ".join(f"{n}={'OK' if ok else 'FAIL'}({d})" for n, ok, d in checks) + f"; {dt:.1f}s; closed {closed}",
                       metrics={"seconds": round(dt, 1)})


def run_g2l(TestOutcome):
    import psutil
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    from core_organs import si_tests_fixes as sf
    if not sf._judge_up():
        return TestOutcome(passed=False, env_blocked=True, evidence="local judge model (Ollama :11434) is not reachable (environment)")
    if any(hin._class_name(h) == "Notepad" for h, _t in hin.top_level_titles(visible_only=False)):
        return TestOutcome(passed=False, env_blocked=True, evidence="the user's Notepad is open; G2L will not drive or kill anything")
    before = sf._top_hwnds()
    ours_pids = set()
    checks: List[Tuple[str, bool, str]] = []

    def killer_for(n_kills):
        state = {"kills": 0}
        orig = dg.DesktopAutonomyLoop.step

        def step(self, goal, app_hint, *a, **k):
            res = orig(self, goal, app_hint, *a, **k)
            if state["kills"] < n_kills and res.get("verdict") == "PASS":
                h = self.grounding.find_window(app_hint)
                if h:
                    pid = hin.window_pid(h)
                    if pid not in ours_pids:
                        ours_pids.add(pid)
                    try:
                        psutil.Process(pid).kill()                    # OUR instance (nothing of the user's Notepad was open)
                        state["kills"] += 1
                        time.sleep(1.5)
                    except Exception:
                        pass
            return res
        return orig, step, state

    # ---- scenario 1: the window vanishes once -> relaunch once, finish
    orig, patched, st = killer_for(1)
    dg.DesktopAutonomyLoop.step = patched
    try:
        t0 = time.perf_counter()
        r1 = dg.operate_app("notepad", ['type "crash-one"', 'type "crash-two"'], max_steps_per_goal=5)
        dt1 = time.perf_counter() - t0
    finally:
        dg.DesktopAutonomyLoop.step = orig
    text = ""
    try:
        h = r1.get("hwnd")
        if h and hin.is_alive(h):
            text = sf._read_notepad_text(h)
    except Exception:
        pass
    checks.append(("killed-our-instance-once", st["kills"] == 1, f"kills={st['kills']}"))
    checks.append(("relaunched-once-and-completed", r1.get("completed") and r1.get("relaunches") == 1, f"completed={r1.get('completed')} relaunches={r1.get('relaunches')} in {dt1:.0f}s"))
    checks.append(("second-goal-landed-after-the-relaunch (independent read)", "crash-two" in text.lower(), f"document={text[:50]!r}"))
    sf._close_new_windows(before)
    time.sleep(1.0)
    # ---- scenario 2: it vanishes again after the relaunch -> fail with evidence, no relaunch loop
    orig, patched, st2 = killer_for(99)
    dg.DesktopAutonomyLoop.step = patched
    try:
        r2 = dg.operate_app("notepad", ['type "again-one"', 'type "again-two"', 'type "again-three"'], max_steps_per_goal=4)
    finally:
        dg.DesktopAutonomyLoop.step = orig
    crash_trace = [t for t in (r2.get("trace") or []) if t.get("method") == "crash-recovery"]
    checks.append(("second-loss-fails-with-evidence", (not r2.get("completed")) and r2.get("crashed") and r2.get("relaunches") == 1,
                   f"completed={r2.get('completed')} crashed={r2.get('crashed')} relaunches={r2.get('relaunches')} evidence={[t['evidence'][:60] for t in crash_trace][-1:]}"))
    closed = sf._close_new_windows(before)
    failed = [n for n, ok, _d in checks if not ok]
    return TestOutcome(passed=not failed, evidence="; ".join(f"{n}={'OK' if ok else 'FAIL'}({d[:150]})" for n, ok, d in checks) + f"; closed {closed}",
                       metrics={"failed": len(failed)})


def run_vq1(TestOutcome):
    """VQ1: the product's targeted vision tier (Qwen2.5-VL 'locate') finds real controls on a real parked window, graded against UIA."""
    import uiautomation as auto
    from core_organs import background_window as bw
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    from core_organs import qwen_vl_scanner as qv
    from core_organs import universal_scan as us
    os.environ["HOJAIGA_QWEN_VL"] = "1"        # G2 switches the targeted locator off for itself; this test is about it
    if not qv.available():
        return TestOutcome(passed=False, env_blocked=True, evidence="llama.cpp vision server :8081 is not reachable (start_hojaiga.bat boots it)")
    if any(hin._class_name(h) == "Notepad" for h, _t in hin.top_level_titles(visible_only=False)):
        return TestOutcome(passed=False, env_blocked=True, evidence="the user's Notepad is open; VQ1 will not touch it")
    info = us.launch_hidden("notepad", timeout_s=30.0)
    h = info.get("hwnd")
    rows, ms = [], []
    try:
        g = dg.DesktopGrounding()
        with bw.BackgroundSession(h):
            g._await_paint(h)
            time.sleep(0.8)
            rc = hin.wt.RECT()
            hin._u32.GetWindowRect(h, hin.ctypes.byref(rc))
            gt = []
            for c, _d in auto.WalkControl(auto.ControlFromHandle(h), maxDepth=18):
                nm = (c.Name or "").strip()
                r = c.BoundingRectangle
                if c.ControlTypeName in ("ButtonControl", "MenuItemControl", "TabItemControl") and 3 <= len(nm) <= 20 and r.right - r.left > 12:
                    gt.append((nm, (r.left, r.top, r.right, r.bottom)))
            seen, picks = set(), []
            for nm, rect in gt:
                if nm.lower() not in seen:
                    seen.add(nm.lower())
                    picks.append((nm, rect))
            picks = picks[:: max(1, len(picks) // 4)][:4]
            hits = 0
            for nm, (l, t, r_, b) in picks:
                rep = {}
                t0 = time.perf_counter()
                els = g._qwen_locate(h, nm, rep)
                dt = (time.perf_counter() - t0) * 1000
                ms.append(dt)
                ok = False
                if els:
                    x0, y0, x1, y1 = els[0].bbox
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    ix = max(0, min(x1, r_) - max(x0, l)) * max(0, min(y1, b) - max(y0, t))
                    un = (x1 - x0) * (y1 - y0) + (r_ - l) * (b - t) - ix
                    ok = bool((un and ix / un > 0.3) or (l <= cx <= r_ and t <= cy <= b))
                hits += ok
                rows.append(f"{nm}:{'hit' if ok else 'miss'}({dt / 1000:.1f}s)")
    finally:
        if h:
            us.close_window(h, discard_unsaved=True, timeout_s=8)
    n = len(rows)
    return TestOutcome(passed=n >= 3 and hits / n >= 0.5 and max(ms) < 40000,
                       evidence=f"{hits}/{n} controls located by Qwen2.5-VL (>=50% needed); mean {sum(ms) / max(n, 1) / 1000:.1f}s each; " + ", ".join(rows),
                       metrics={"hits": hits, "n": n, "mean_ms": int(sum(ms) / max(n, 1))})
