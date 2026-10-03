"""bench_universal.py — the tiered benchmark: the SAME scan() on apps and websites of very different
weight. The tier labels below exist ONLY for reporting; nothing in the code under test sees them.

    python bench_universal.py [--only name1,name2] [--timeout 420] [--out results.json]

Per target: COLD scan (empty knowledge) then WARM scan (knowledge from the cold scan), each in its own
subprocess with a hard timeout. Desktop targets are monitored for focus theft and on-screen exposure.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

PY = r"D:\new_automation\hojaiga_env\Scripts\python.exe"
ONE = r"D:\new_automation\All codes\core_organs\bench_one.py"

TARGETS = [
    # tier,        kind,      target
    ("T1 easy",      "desktop", "Notepad"),
    ("T1 easy",      "desktop", "Calculator"),
    ("T2 moderate",  "desktop", "Paint"),
    ("T2 moderate",  "desktop", "Sticky Notes"),
    ("T3 medium",    "desktop", "File Explorer"),
    ("T3 medium",    "desktop", "Settings|existing"),
    ("T4 hard",      "desktop", "Visual Studio Code"),
    ("T4 hard",      "desktop", "OBS Studio"),
    ("T5 complex",   "desktop", "Word"),
    ("T5 complex",   "desktop", "Excel"),
    ("T5 complex",   "desktop", "PowerPoint"),
    ("T6 deep",      "desktop", "Visual Studio 2022"),
    ("W1 easy",      "web",     "https://example.org"),
    ("W2 moderate",  "web",     "https://news.ycombinator.com"),
    ("W3 medium",    "web",     "https://en.wikipedia.org/wiki/Notepad"),
    ("W4 hard",      "web",     "https://github.com/microsoft/vscode"),
    ("W4 hard",      "web",     "https://www.youtube.com"),
    ("W5 complex",   "web",     "https://excalidraw.com"),
    ("W6 deep",      "web",     "https://app.diagrams.net"),
    ("W7 logged-in", "web",     "https://mail.google.com/mail/u/0/|gmail"),
    ("W7 logged-in", "web",     "https://www.youtube.com|gmail"),
]


def run_one(target: str, db: str, timeout: int, extra=()) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run([PY, "-X", "utf8", ONE, target, db, *extra], capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, PYTHONPATH=r"D:\new_automation;D:\new_automation\All codes",
                                    HOJAIGA_WEBAPP_WATCH="0"))
        for line in reversed((p.stdout or "").splitlines()):
            if line.startswith("BENCH_JSON "):
                return json.loads(line[len("BENCH_JSON "):])
        return {"error": "no result line", "stderr": (p.stderr or "")[-400:], "wall_s": round(time.time() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"error": f"TIMEOUT after {timeout}s", "wall_s": timeout}


def main() -> None:
    only = None
    timeout = 420
    out = os.path.join(r"D:\new_automation\data", "bench_universal_results.json")
    a = sys.argv[1:]
    if "--only" in a:
        only = [s.strip().lower() for s in a[a.index("--only") + 1].split(",")]
    if "--timeout" in a:
        timeout = int(a[a.index("--timeout") + 1])
    if "--out" in a:
        out = a[a.index("--out") + 1]
    results = []
    for tier, kind, target in TARGETS:
        if only and not any(o in target.lower() for o in only):
            continue
        db = os.path.join(tempfile.gettempdir(), "hj_bench_" + str(abs(hash(target)))[:8] + ".db")
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(db + suf)
            except Exception:
                pass
        print(f"\n### {tier:12} {kind:7} {target}", flush=True)
        cold = run_one(target, db, timeout)
        print(f"   cold: {cold.get('wall_s')}s err={cold.get('error')} controls={cold.get('layout', {}).get('controls', cold.get('controls'))} "
              f"cmds={cold.get('known_commands', cold.get('commands_recorded'))}", flush=True)
        warm = {}
        if not cold.get("error"):
            warm = run_one(target, db, timeout)
            print(f"   warm: {warm.get('wall_s')}s err={warm.get('error')}", flush=True)
        results.append({"tier": tier, "kind": kind, "target": target, "cold": cold, "warm": warm})
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1, default=str)
    print("\nwritten:", out)


if __name__ == "__main__":
    main()
