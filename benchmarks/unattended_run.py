"""Medium unattended desktop run (Notepad), plus a dry-run precheck mode.

  precheck: python benchmarks/unattended_run.py --precheck   # no desktop actions
  run:      python benchmarks/unattended_run.py

The precheck follows the project convention of verifying launcher/routing logic before any
heavy execution: pure app-resolution (plan_task_app), judge-model reachability, the target
window, and the goal/expectation plan. The run then drives ONE medium multi-goal task through
the real closed loop and writes the full ground -> act -> verdict trace to
grounding_reports/unattended_notepad.json. Nothing here is edited by hand afterwards.
"""
import ctypes, ctypes.wintypes as wt, json, os, shutil, sys, time
from typing import Any, Dict

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
os.environ.setdefault("HOJAIGA_KNOWLEDGE_ROOT", os.path.join(r"D:\new_automation", "organ_04_knowledge"))

OUT_DIR = os.path.join(r"D:\new_automation", "_unattended_tmp")
TARGET = os.path.join(OUT_DIR, "atlas_status.txt")
OUT = os.path.join(os.path.dirname(__file__), "grounding_reports", "unattended_notepad.json")
MARK1, MARK2, MARK3 = "ATLASLINE1", "ATLASLINE2", "ATLASLINE3"
APP = "notepad"

GOALS = [
    f'type "{MARK1} verifier hardening landed with four measured cases" into the text area',
    f'type "{MARK2} grounding measured on five apps" into the text area',
    f"save the document as {TARGET}",
    f'type "{MARK3} medium unattended task running" into the text area',
    f"save the document as {TARGET}",
]
EXPECT_MAP = {2: {"file_created": TARGET}, 4: {"title_contains": "atlas_status"}}


def cursor_pos():
    p = wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def window_state(hwnd):
    if not hwnd:
        return "no-window"
    u = ctypes.windll.user32
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return {"hwnd": hwnd, "title": buf.value, "minimized": bool(u.IsIconic(hwnd)),
            "visible": bool(u.IsWindowVisible(hwnd))}


def open_file_dialogs():
    """Every visible Save/Open picker on the desktop, with its owning process. The first run wrote
    its file into ANOTHER app's picker, so the run now records the crowd around it."""
    u = ctypes.windll.user32
    from core_organs.desktop_grounding import DesktopGrounding
    g = DesktopGrounding()
    found = []
    import ctypes as ct

    @ct.WINFUNCTYPE(ct.c_bool, ct.c_void_p, ct.c_void_p)
    def _cb(hwnd, _l):
        cls = ct.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        if cls.value != "#32770" or not u.IsWindowVisible(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        buf = ct.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        t = buf.value.lower()
        if any(w in t for w in ("save", "open", "export", "browse")):
            found.append({"hwnd": hwnd, "title": buf.value,
                          "proc": g._process_stem_cached(hwnd)})
        return True

    u.EnumWindows(_cb, 0)
    return found


def precheck():
    """Decide everything the run will do WITHOUT touching the OS."""
    from core_organs.organ_40_app_launcher import plan_task_app
    from core_organs.desktop_grounding import BRAINS_CHAT_URL, JUDGE_MODEL, DesktopGrounding
    report = {}
    plan = plan_task_app("type a note in Notepad and save it as a text file")
    report["app_resolution"] = plan
    resolved = f"{plan.get('desired_app', '')} {plan.get('target_app', '')}".lower()
    report["app_matches_this_run"] = "notepad" in resolved
    # A search-bar launch is the known-risky path (it can land in the Windows search UI instead of
    # the app), so say up front whether this run would need it: it does not if the window is open.
    report["launch_would_use_search_bar"] = bool(plan.get("would_type_in_search_bar"))

    report["target_window"] = window_state(DesktopGrounding().find_window(APP))
    report["open_file_dialogs_at_precheck"] = open_file_dialogs()

    t = time.perf_counter()
    try:
        import urllib.request
        payload = {"model": JUDGE_MODEL, "stream": False,
                   "messages": [{"role": "user", "content": 'Reply with the word OK only'}],
                   "options": {"temperature": 0, "num_predict": 4}}
        req = urllib.request.Request(BRAINS_CHAT_URL, data=json.dumps(payload).encode(),
                                    headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        report["judge"] = {"model": JUDGE_MODEL, "reachable": True,
                           "reply": ((body.get("message", {}) or {}).get("content", "") or "").strip()[:24],
                           "ms": round((time.perf_counter() - t) * 1000)}
    except Exception as exc:
        report["judge"] = {"model": JUDGE_MODEL, "reachable": False, "error": repr(exc),
                           "ms": round((time.perf_counter() - t) * 1000)}

    report["goals"] = GOALS
    report["expect_map"] = {str(k): v for k, v in EXPECT_MAP.items()}
    # Vision stays off (max_tier 2): measured 62-410 s per pass on CPU makes it a learning step,
    # not a per-step tier, so a grounding-tier-1/2 run is the honest configuration here.
    report["perception_tiers_used"] = ["uia", "win32"]
    report["target_path_prefixed_dir_exists"] = os.path.isdir(os.path.dirname(TARGET))
    print(json.dumps(report, indent=2)[:2200])
    return report


def run():
    from core_organs import headless_input as hin
    from core_organs.desktop_grounding import operate_app, get_loop, DesktopGrounding

    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(TARGET):
        os.remove(TARGET)

    # The first run drove a MINIMIZED Notepad left over from the grounding benchmark, so Windows
    # rendered no pixels and the pixel tier could only report 'window-minimized'. This harness
    # restores it (our own leftover window) so both verification signals are live.
    g = DesktopGrounding()
    hwnd0 = g.find_window(APP)
    was_minimized = bool(hwnd0 and ctypes.windll.user32.IsIconic(hwnd0))
    if was_minimized:
        ctypes.windll.user32.ShowWindow(hwnd0, 9)   # SW_RESTORE
        time.sleep(1.0)
    dialogs_before = open_file_dialogs()

    viol0 = len(hin.VIOLATIONS)
    pointer0 = cursor_pos()
    capsule_log = []
    t0 = time.perf_counter()
    result = operate_app(APP, GOALS, capsule_cb=lambda state, text: (
        capsule_log.append(f"{state}: {text}"), print(f"[{state}] {text}", flush=True)),
        max_steps_per_goal=7, expect_map=EXPECT_MAP)
    elapsed = round(time.perf_counter() - t0, 2)

    content = ""
    try:
        with open(TARGET, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        content = f"<unreadable: {exc!r}>"

    verdict_counts: Dict[str, int] = {}
    for st in result.get("trace", []):
        verdict_counts[st.get("verdict", "?")] = verdict_counts.get(st.get("verdict", "?"), 0) + 1

    exists = os.path.exists(TARGET)
    file_check: Dict[str, Any] = {
        "exists": exists,
        "bytes": os.path.getsize(TARGET) if exists else 0,
        "has_line1": MARK1 in content, "has_line2": MARK2 in content,
        "has_line3_after_resave": MARK3 in content,
        "content_preview": content[:400],
    }
    cursor_after = cursor_pos()
    guard_check: Dict[str, Any] = {
        "input_guard_violations_new": len(hin.VIOLATIONS) - viol0,
        "physical_cursor_untouched": cursor_after == pointer0,
        "cursor_before": pointer0, "cursor_after": cursor_after,
    }

    report = {
        "app": APP, "goals": GOALS, "expect_map": {str(k): v for k, v in EXPECT_MAP.items()},
        "target_window_before": window_state(hwnd0),
        "target_window_after": window_state(g.find_window(APP)),
        "restored_from_minimized": was_minimized,
        "file_dialogs_open_before_run": dialogs_before,
        "file_dialogs_open_after_run": open_file_dialogs(),
        "completed": result.get("completed"), "steps": result.get("steps"),
        "awaiting_human": result.get("awaiting_human"), "blocked_at_goal": result.get("blocked_at_goal"),
        "launched_by_us": result.get("launched"), "recipe": result.get("recipe", ""),
        "recipe_ingested": result.get("recipe_ingested", False),
        "elapsed_s": elapsed, "wall_s_including_setup": round(time.perf_counter() - t0, 2),
        "verdict_counts": verdict_counts,
        "file": file_check,
        "guards": guard_check,
        "capsule": capsule_log,
        "trace": result.get("trace", []),
        "checkpoint_file": os.path.join(os.environ.get("TEMP", "."), "hojaiga_desktop_checkpoints",
                                        f"{get_loop().session_id}.json"),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    shown = [(st.get("goal", "")[:26], st.get("verb"), (st.get("element") or "")[:16],
              st.get("verdict"), st.get("method"), st.get("tiers")) for st in report["trace"]]
    for row in shown:
        print(row, flush=True)
    print(json.dumps({k: report[k] for k in
                      ("completed", "steps", "awaiting_human", "blocked_at_goal", "verdict_counts",
                       "file", "guards", "recipe", "elapsed_s")}, indent=2), flush=True)
    ok = (bool(report["completed"]) and file_check["exists"] and file_check["has_line1"]
          and file_check["has_line2"] and file_check["has_line3_after_resave"]
          and guard_check["input_guard_violations_new"] == 0)
    print("UNATTENDED RUN:", "ALL VERIFIED" if ok else "INCOMPLETE — see trace above", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--precheck" in sys.argv:
        precheck()
        sys.exit(0)
    sys.exit(run())
