"""task_bench.py - end-to-end task benchmark: give a natural-language task to the system, walk away, and
check the RESULT against independent ground truth (never the system's own claim).

    python task_bench.py [--only name1,name2] [--timeout 240] [--entry loop|template|auto]

Each task runs in its own subprocess with a hard timeout. Output: data/task_bench_results.json + a table.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

PY = r"D:\new_automation\hojaiga_env\Scripts\python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.gettempdir()


def _tmp(ext):
    return os.path.join(TMP, "hj_task_" + uuid.uuid4().hex[:6] + ext)


TXT, TXT2, TXT3, PNG = _tmp(".txt"), _tmp(".txt"), _tmp(".txt"), _tmp(".png")
CSV = _tmp(".csv")

# name, app, natural-language task, truth spec
TASKS = [
    ("notepad-write-save", "Notepad", f"type hello world; save the file as {TXT}", {"file_has": (TXT, "hello world")}),
    ("calculator-25x4", "Calculator", "press 2; press 5; press multiply; press 4; press equals; expect Display is 100", {"calc_display": "100"}),
    ("paint-save-png", "Paint", f"save the image as {PNG}", {"png": PNG}),
    ("settings-bluetooth", "Settings", "open the Bluetooth & devices page; expect Add device", {"window_text": "bluetooth"}),
    ("notepad-template", "Notepad", f"write text and save as file|{TXT2}|templated text", {"file_has": (TXT2, "templated text")}),
    ("explorer-documents", "File Explorer", "click Documents; expect Documents", {"window_text": "documents"}),
    ("excel-cell-csv", "Excel", f"click Blank workbook; type 42; save the file as {CSV}", {"file_has": (CSV, "42")}),
    ("notepad-unverifiable", "Notepad", "type just a note", {"window_text": "just a note"}),   # typed text is verifiable in the control, so DONE is legitimate
]


# window class that identifies each app's own top-level windows (apps whose class is shared with other apps are not guarded)
_GUARD_CLASS = {"notepad": "Notepad", "paint": "MSPaintApp", "file explorer": "CabinetWClass", "excel": "XLMAIN"}


def _users_window(app: str) -> str:
    cls = _GUARD_CLASS.get((app or "").lower())
    if not cls:
        return ""
    sys.path[:0] = [r"D:\new_automation\All codes", r"D:\new_automation"]
    from core_organs import headless_input as hin
    for h, t in hin.top_level_titles(visible_only=False):
        if hin._class_name(h) == cls:
            return t
    return ""


def main():
    only = None
    timeout = 240
    entry = "auto"
    a = sys.argv[1:]
    if "--only" in a:
        only = [s.strip().lower() for s in a[a.index("--only") + 1].split(",")]
    if "--timeout" in a:
        timeout = int(a[a.index("--timeout") + 1])
    if "--entry" in a:
        entry = a[a.index("--entry") + 1]
    results = []
    for name, app, task, truth in TASKS:
        if only and not any(o in name for o in only):
            continue
        print(f"\n### {name}: {app}: {task[:70]}", flush=True)
        t0 = time.time()
        owned = _users_window(app)
        if owned:
            # the run would attach to a window that already exists (a single-instance launcher never opens a second
            # one): that is the USER'S window, and a bench must never drive it
            res = {"skipped": f"the user's {app} window is open ({owned[:40]!r}); not driving it", "truth_ok": None,
                   "claimed_done": None, "name": name, "app": app, "task": task, "wall_s": 0}
            results.append(res)
            print(f"   SKIPPED: {res['skipped']}", flush=True)
            continue
        try:
            p = subprocess.run([PY, "-X", "utf8", os.path.join(HERE, "task_one.py"), name, app, task, json.dumps(truth), entry],
                               capture_output=True, text=True, timeout=timeout,
                               env=dict(os.environ, PYTHONPATH=r"D:\new_automation;D:\new_automation\All codes", HOJAIGA_WEBAPP_WATCH="0"))
            res = None
            for line in reversed((p.stdout or "").splitlines()):
                if line.startswith("TASK_JSON "):
                    res = json.loads(line[10:])
                    break
            res = res or {"error": "no result", "stderr": (p.stderr or "")[-300:]}
        except subprocess.TimeoutExpired:
            res = {"error": f"TIMEOUT after {timeout}s", "truth_ok": False}
        res.update(name=name, app=app, task=task, wall_s=round(time.time() - t0, 1))
        results.append(res)
        print(f"   truth_ok={res.get('truth_ok')} claimed_done={res.get('claimed_done')} {res.get('wall_s')}s "
              f"steps={res.get('steps')} err={str(res.get('error'))[:70]}", flush=True)
        os.makedirs(r"D:\new_automation\data", exist_ok=True)
        with open(r"D:\new_automation\data\task_bench_results.json", "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1, default=str)
    print("\nwritten")


if __name__ == "__main__":
    main()
