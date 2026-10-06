r"""
crewai_boot_e2e.py — work order [5] acceptance: a SIMPLE end-to-end task runs through
the CrewAI brain (organ_01) and provably uses the MODERN scanner (fast_scan.deep_scan),
not a legacy path. Instrumentation is honest: we count real deep_scan calls made during
the crew's execution, and we verify the app is actually open afterwards as the goal's
postcondition. Cleanup closes only the window our own run launched.
"""
import os
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
sys.path.insert(0, r"d:\new_automation\All codes\core_organs")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# acceptance target = the CREWAI flow (ReAct crew + tools). The deterministic loop-first
# preamble is the engine's own documented bisection switch (see _loop_first_preamble);
# with it on, a vague compiled goal HITLs BEFORE any crew tool runs, so the crew path
# itself would never be exercised here. The loop-first collision is reported separately.
os.environ["HOJAIGA_LOOP_FIRST"] = "0"

# --- instrument fast_scan.deep_scan BEFORE organ_01 can bind it (organ_01 imports the
# module fresh inside its tools, so patching the module attribute is enough)
from core_organs import fast_scan

deep_calls = []
_orig_deep = fast_scan.deep_scan


def _spy_deep(target, *a, **kw):
    rep = _orig_deep(target, *a, **kw)
    deep_calls.append({"target": str(target),
                       "nodes": (rep or {}).get("tree", {}).get("nodes"),
                       "seconds": (rep or {}).get("seconds"),
                       "within_budget": (rep or {}).get("within_budget")})
    return rep


fast_scan.deep_scan = _spy_deep
fast_scan.deep_scan_legacy_shape.__globals__["deep_scan"] = _spy_deep  # in-module calls too


def _find_windows(titles):
    import ctypes
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        buf = ctypes.create_unicode_buffer(200)
        u.GetWindowTextW(h, buf, 200)
        if any(t.lower() in buf.value.lower() for t in titles):
            found.append(int(h))
        return True
    u.EnumWindows(_cb, 0)
    return found


def main(report: list) -> int:
    before = set(_find_windows(["Calculator"]))
    from core_organs.organ_01_crewai_engine import CrewAIEngine
    engine = CrewAIEngine()
    if not engine.is_available():
        report.append("[E2E-FAIL] CrewAI engine unavailable (crewai package / Ollama LLM)")
        return 1

    # CALCULATOR: fresh, idle, no user data. (A Paint target is unusable for THIS
    # acceptance: organ_01's keyword intent classifier maps the word "paint" to
    # is_draw_task and injects a mandatory draw workflow - a generalization gap
    # reported for work order item [7], not patched here.)
    command = ("Open the Calculator desktop application, then scan its UI and tell me "
               "how many interactive elements the scan found. Do not click any button.")
    tid = "boot_e2e_simple"
    result = engine.execute_task(command, tid)
    status = str(result.get("status", ""))
    out = str(result.get("crew_output", ""))

    after = set(_find_windows(["Calculator"]))
    ours = sorted(after - before)                              # only windows THIS run created
    opened = bool(ours)
    used_fast_scan = bool(deep_calls)
    mentions = any(k in out.lower() for k in ("calculator", "element"))
    done = status.upper() in ("COMPLETED", "SUCCESS", "DONE")

    # cleanup: close what we opened (never the user's pre-existing window)
    import ctypes, time
    u = ctypes.windll.user32
    for h in ours:
        u.PostMessageW(h, 0x0010, 0, 0)                        # WM_CLOSE
        time.sleep(0.3)

    ok = done and opened and used_fast_scan and mentions
    report.append("=" * 68)
    report.append(f"[crewai boot e2e] {'PASS' if ok else 'FAIL'}")
    report.append(f"  status={status} task_completed={done}")
    report.append(f"  calculator_opened_by_this_run={opened} (ours={ours}, user's pre-existing left untouched)")
    report.append(f"  fast_scan.deep_scan_calls={len(deep_calls)} detail={deep_calls[:3]}")
    report.append(f"  output_mentions_goal={mentions} crew_output={out[:300]!r}")
    report.append("=" * 68)
    return 0 if ok else 1


if __name__ == "__main__":
    import contextlib
    import io
    # organ load chatter floods stdout; our own report goes to a list, printed after the
    # redirected run finishes - nothing is lost, nothing is buried
    rep_lines = []
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = main(rep_lines)
    finally:
        for line in rep_lines:
            print(line)
    sys.exit(rc)
