"""overnight_effect_probe_runner — unattended, multi-app Law-0 knowledge harvest.

Runs the organ_64 effect prober across several apps while nobody is watching,
writes per-app evidence + a single morning summary, and can be stopped at any
moment by creating the STOP file. It NEVER kills a target app and NEVER fakes a
pass: an app that is not found is recorded honestly as "skipped", and any probe
error is captured per-app so one failure cannot abort the whole night.

Morning report lands in:  D:\\new_automation\\overnight_results\\
"""
import os, sys, time, json, glob, subprocess, traceback

sys.path.insert(0, r"D:\new_automation\All codes\core_organs")
import organ_64_effect_prober as P

ROOT = r"D:\new_automation"
OUT_ROOT = os.path.join(ROOT, "overnight_results")
STOP_FILE = os.path.join(ROOT, "STOP_OVERNIGHT.txt")
BLENDER_EXE = r"D:\blender.exe"

# Per-app plan. `launch` may be a callable that (re)opens the app if it is not
# already running; Blender is user-owned so we only probe it if present.
APPS = [
    {"label": "calculator", "proc": "", "title": "Calculator", "vision": False,
     "budget": 600.0, "launch": lambda: subprocess.Popen(
         ["cmd", "/c", "start", "calculator:"], shell=False)},
    {"label": "fileexplorer", "proc": "explorer.exe", "title": "", "vision": False,
     "budget": 480.0, "launch": lambda: subprocess.Popen(
         ["explorer", os.path.join(OUT_ROOT)])},
    {"label": "blender", "proc": "blender", "title": "", "vision": True,
     "budget": 900.0, "launch": None},   # only if the user left it open
]


def _log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    return line


def stopped():
    return os.path.exists(STOP_FILE)


def ensure_running(spec):
    """Return a found target dict, launching once if needed. Honest None if absent."""
    t = P.find_window(spec["proc"], spec["title"])
    if t:
        return t, "already-running"
    if spec.get("launch"):
        try:
            spec["launch"]()
        except Exception:
            return None, "launch-failed"
        for _ in range(6):
            time.sleep(3.0)
            t = P.find_window(spec["proc"], spec["title"])
            if t:
                return t, "launched"
    return None, "not-found"


def count_evidence(outdir):
    return len(glob.glob(os.path.join(outdir, "ev_*.png")))


def run_one(spec, ts):
    outdir = os.path.join(OUT_ROOT, "probe_%s_%s" % (spec["label"], ts))
    target, how = ensure_running(spec)
    headline = {"label": spec["label"], "outdir": outdir, "launch_status": how}
    if not target:
        headline.update(status="skipped", reason="app not running / not launchable",
                        probed=0)
        _log("SKIP %s (%s)" % (spec["label"], how))
        return headline
    _log("PROBE %s (%s) hwnd=%s proc=%s title=%r vision=%s budget=%.0fs"
         % (spec["label"], how, target["hwnd"], target["proc"],
            target["title"][:40], spec["vision"], spec["budget"]))
    try:
        r = P.probe_app(target, outdir, budget_s=spec["budget"],
                        vision=spec["vision"], stop_file=STOP_FILE)
        headline.update(status="ok", probed=r["probed"], effects=r["effects"],
                        exhausted=r["exhausted"], dialogs=len(r["dialogs"]),
                        reverted_ok=r["reverted_ok"],
                        revert_unverified=r.get("revert_unverified", 0),
                        revert_failed=r["revert_failed"],
                        passes=r.get("passes"), elapsed_s=r.get("elapsed_s"),
                        evidence_pngs=count_evidence(outdir),
                        notes=r.get("notes", []))
    except Exception:
        headline.update(status="error", reason=traceback.format_exc()[-300:],
                        probed=0)
    _log("  -> %s" % json.dumps({k: headline[k] for k in
           ("status", "probed", "exhausted", "reverted_ok", "revert_failed")
           if k in headline}))
    return headline


def main():
    os.makedirs(OUT_ROOT, exist_ok=True)
    if stopped():
        _log("STOP file present at start; aborting.")
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    _log("=== Overnight effect-probe run %s ===" % ts)
    _log("Stop any time by creating: %s" % STOP_FILE)

    results = []
    for spec in APPS:
        if stopped():
            _log("STOP file detected; ending before %s." % spec["label"])
            results.append({"label": spec["label"], "status": "stopped"})
            continue
        results.append(run_one(spec, ts))

    summary = {"run_id": ts, "started": started,
               "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
               "stopped_early": stopped(), "apps": results}
    jpath = os.path.join(OUT_ROOT, "overnight_summary_%s.json" % ts)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    md = ["# Overnight App-Knowledge Report", "",
          "Run `%s`  started %s  finished %s%s" % (
              ts, started, summary["finished"],
              "  **(stopped early)**" if summary["stopped_early"] else ""),
          "", "Every claim below is measured causality (open-then-cancel probes on the",
          "live app). `unverified` revert means a control changed state in a way we",
          "could not safely auto-undo; `no-effect`/`no-change` are honest negatives.",
          "", "| App | Status | Found window | Probed | Exhausted | Dialogs | Reverted | Unverified | Failed | Evidence |",
          "|-----|--------|--------------|--------|-----------|---------|----------|------------|----------|----------|"]
    for r in results:
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r.get("label", ""), r.get("status", ""),
            r.get("launch_status", ""), r.get("probed", ""),
            r.get("exhausted", ""), r.get("dialogs", ""),
            r.get("reverted_ok", ""), r.get("revert_unverified", ""),
            r.get("revert_failed", ""), r.get("evidence_pngs", "")))
    md += ["", "Per-app `report.json`, `trace.jsonl` and evidence PNGs live under:",
           "```", "\n".join(r["outdir"] for r in results if r.get("outdir")), "```", ""]
    mpath = os.path.join(OUT_ROOT, "overnight_summary_%s.md" % ts)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    _log("SUMMARY json: %s" % jpath)
    _log("SUMMARY md  : %s" % mpath)
    _log("=== done ===")


if __name__ == "__main__":
    main()
