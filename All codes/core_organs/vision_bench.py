"""
vision_bench.py -- honest, REAL latency measurements for the vision tier (OmniParser). No mocks, no stand-ins.

  python vision_bench.py cold   --mode A|B [--work-s 8]    one COLD process (fresh interpreter), JSON on the last line
  python vision_bench.py h2h    [--work-s 8] [--rounds 2]  A/B/A/B cold starts head to head, JSON summary

Why it exists: the first G2 numbers ("28 ms hit / 76 ms miss", "warmup 4883 ms") came from a fake parser and from a
process whose models were already resident. The real cost of the first vision need is the COLD model load (20-257 s on
this class of machine), so that is what is timed here, in fresh processes, with the real parser.

Mode A = the product's behaviour: the warmup thread starts at t0 (get_loop()), the goal path keeps working on UIA, and the
first goal that needs pixels finds the models loaded (or waits for the remainder).
Mode B = no eager warmup: nothing is loaded until the first goal that needs pixels asks for it.
Both run the SAME non-vision goal-path workload for --work-s seconds first (real UIA grounding of a hidden Notepad), then
make the SAME vision request and wait for a real OmniParser result.

Reported per run (ms from process start unless noted): torch import, model construction, first parse, second parse,
time the goal WAITED for vision after it asked for it, and the per-tier ms of the ground() report that finally contained
vision.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, r"D:\new_automation")

PY = sys.executable


def _cold(mode: str, work_s: float) -> dict:
    t0 = time.perf_counter()
    os.environ["HOJAIGA_WEBAPP_WATCH"] = "0"
    out = {"mode": mode, "work_s": work_s}
    from core_organs import desktop_grounding as dg
    from core_organs import universal_scan as us, background_window as bw, headless_input as hin
    out["import_grounding_ms"] = round((time.perf_counter() - t0) * 1000)
    info = us.launch_hidden("notepad")
    hwnd = int(info.get("hwnd") or 0)
    if not hwnd:
        out["error"] = f"no hidden Notepad: {info.get('notes')}"
        return out
    g = dg.DesktopGrounding()
    try:
        with bw.BackgroundSession(hwnd):
            time.sleep(1.0)
            t_launch_done = time.perf_counter()
            if mode == "A":
                out["warmup_started_at_ms"] = round((time.perf_counter() - t0) * 1000)
                dg.DesktopGrounding.start_warmup()                       # what get_loop() does at the first task
            # ---- the goal path, UIA only, for work_s seconds
            end = time.perf_counter() + work_s
            n = 0
            while time.perf_counter() < end:
                g.ground("notepad")
                n += 1
            out["goal_path_grounds"] = n
            # ---- the first goal that needs pixels
            t_need = time.perf_counter()
            out["vision_needed_at_ms"] = round((t_need - t0) * 1000)
            report = {}
            waited_polls = 0
            while time.perf_counter() - t_need < 400:
                _h, _els, report = g.ground("notepad", target_text="zz_absent_widget_zz", max_tier=4)
                if "vision" in report.get("tiers_ran", []):
                    break
                waited_polls += 1
                time.sleep(0.5)
            t_vis = time.perf_counter()
            out["vision_result_at_ms"] = round((t_vis - t0) * 1000)
            out["goal_waited_for_vision_ms"] = round((t_vis - t_need) * 1000)
            out["vision_ran"] = "vision" in report.get("tiers_ran", [])
            out["ground_report_tier_ms"] = report.get("tier_ms")
            out["tiers_ran"] = report.get("tiers_ran")
            out["tiers_skipped_last"] = report.get("tiers_skipped")
            out["warm_state"] = dict(dg.DesktopGrounding._warm).get("state")
            wres = (dg.DesktopGrounding._warm.get("result") or {})
            out["warmup_result_ms"] = wres.get("ms")
            # ---- a second, identical parse on the now-warm parser (the resident cost)
            if out["vision_ran"]:
                g.reset_vision_budget()
                g._vision_cache.clear()
                t1 = time.perf_counter()
                _h, _e, rep2 = g.ground("notepad", target_text="zz_absent_widget_zz", max_tier=4)
                out["second_ground_ms"] = round((time.perf_counter() - t1) * 1000)
                out["second_vision_ms"] = (rep2.get("tier_ms") or {}).get("vision")
    finally:
        us.close_window(hwnd, discard_unsaved=True)
    out["total_ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def _run_cold(mode: str, work_s: float) -> dict:
    t0 = time.perf_counter()
    p = subprocess.run([PY, "-X", "utf8", os.path.abspath(__file__), "cold", "--mode", mode, "--work-s", str(work_s)],
                       capture_output=True, text=True, timeout=900,
                       env=dict(os.environ, PYTHONPATH=r"D:\new_automation;D:\new_automation\All codes"))
    for line in reversed((p.stdout or "").splitlines()):
        if line.startswith("BENCH_JSON "):
            res = json.loads(line[len("BENCH_JSON "):])
            res["wall_ms"] = round((time.perf_counter() - t0) * 1000)
            return res
    return {"mode": mode, "error": "no result", "stderr_tail": (p.stderr or "")[-400:], "rc": p.returncode}


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "h2h"
    work_s = float(args[args.index("--work-s") + 1]) if "--work-s" in args else 8.0
    if cmd == "cold":
        mode = args[args.index("--mode") + 1] if "--mode" in args else "A"
        res = _cold(mode, work_s)
        print("BENCH_JSON " + json.dumps(res))
        return 0
    rounds = int(args[args.index("--rounds") + 1]) if "--rounds" in args else 2
    runs = []
    for i in range(rounds):
        for mode in (("A", "B") if i % 2 == 0 else ("B", "A")):          # alternate the order: cache warmth must not favour one arm
            r = _run_cold(mode, work_s)
            runs.append(r)
            print(f"[{len(runs)}] mode {mode}: vision at {r.get('vision_result_at_ms')} ms, goal waited "
                  f"{r.get('goal_waited_for_vision_ms')} ms, second parse {r.get('second_vision_ms')} ms "
                  f"{'ERR ' + str(r.get('error')) if r.get('error') else ''}", flush=True)
    a = [r for r in runs if r.get("mode") == "A" and r.get("vision_ran")]
    b = [r for r in runs if r.get("mode") == "B" and r.get("vision_ran")]
    summary = {"work_s": work_s, "runs": runs}
    if a and b:
        ma = sum(r["goal_waited_for_vision_ms"] for r in a) / len(a)
        mb = sum(r["goal_waited_for_vision_ms"] for r in b) / len(b)
        va = sum(r["vision_result_at_ms"] for r in a) / len(a)
        vb = sum(r["vision_result_at_ms"] for r in b) / len(b)
        summary.update(mean_goal_wait_A_ms=round(ma), mean_goal_wait_B_ms=round(mb),
                       mean_vision_ready_A_ms=round(va), mean_vision_ready_B_ms=round(vb),
                       warmup_thread_saved_ms=round(mb - ma))
    print("H2H_JSON " + json.dumps(summary))
    out = os.path.join(os.path.dirname(HERE), os.pardir, "data", "vision_bench_results.json")
    try:
        out = os.path.abspath(out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=1)
        print("written", out)
    except Exception as exc:  # noqa: BLE001
        print("could not write results:", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
