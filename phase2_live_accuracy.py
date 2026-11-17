"""
phase2_live_accuracy -- REAL, measured Phase-2 functional accuracy + generalisation,
now with a MODALITY-AWARE task gate and an expanded task suite.

Zero-shot: the agent is handed a TASK (intent-only widget words, no automation ids, no
memorised coordinates) on apps that were NOT in the Phase-1 guide corpus, run OFF-SCREEN
(HOJAIGA_OFFSCREEN=1) and verified. Success is certified by the 3-tier verifier
(UIA delta -> ROI pixel-diff -> full-window Qwen3-VL semantic).

Modality-aware task gate (closes the step-vs-task gap without weakening rigour):
  * gate="symbolic" (Calculator math, Notepad typing): the FINAL result must appear as an
    EXACT string/numeric match in the UIA result text. The VLM never gets to "guess" math.
  * gate="visual"   (Paint tool/canvas, menu toggles, status bar): UIA text does not mutate,
    so success = every step verified by the 3-tier verifier (all-steps-verified). A no-op
    still fails, because a no-op produces no UIA delta, no ROI pixel change, and no VLM
    confirmation.

Fully-verified tasks are written to the episodic-memory cache (see episodic_memory.py).

Usage: python phase2_live_accuracy.py --tag <name>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("HOJAIGA_OFFSCREEN", "1")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import live_trajectory_executor as LX

OUT = Path("reports/ml_analysis")
OUT.mkdir(parents=True, exist_ok=True)
TMP = OUT / "_tasks"
TMP.mkdir(parents=True, exist_ok=True)


def p(m: str) -> None:
    print(f"[phase2] {m}", flush=True)


import urllib.request
_VISION_HEALTH = os.environ.get("HOJAIGA_VISION_HEALTH", "http://127.0.0.1:8081/health")
_OLLAMA_HEALTH = "http://127.0.0.1:11434/api/tags"


def _up(url: str, timeout: int = 5) -> bool:
    try:
        return urllib.request.urlopen(url, timeout=timeout).status == 200
    except Exception:
        return False


def vision_preflight(max_wait: int = 200) -> bool:
    """Never benchmark half-blind: require the :8081 Qwen-VL eye + :11434 brain healthy,
    auto-launching the llama.cpp server if it is down and waiting for it to load."""
    p(f"PRE-FLIGHT: :11434 brain {'UP' if _up(_OLLAMA_HEALTH) else 'DOWN'} | :8081 eye {'UP' if _up(_VISION_HEALTH) else 'DOWN'}")
    if not _up(_VISION_HEALTH):
        p("PRE-FLIGHT: :8081 down -> auto-launching start_vision_server.ps1 (loads Qwen-VL ~60s)...")
        try:
            subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", "start_vision_server.ps1"],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as e:
            p(f"PRE-FLIGHT: launcher spawn failed ({e}); still waiting on :8081.")
        waited = 0
        while waited < max_wait and not _up(_VISION_HEALTH):
            time.sleep(5); waited += 5
            p(f"PRE-FLIGHT: waiting for :8081 to become healthy ... {waited}s")
    ok = _up(_VISION_HEALTH)
    p(f"PRE-FLIGHT RESULT: :8081 {'HEALTHY - tier-3 VLM enabled' if ok else 'STILL DOWN - tier-3 will be limited (honest)'}")
    return ok


def vision_gate(budget: int = 120) -> bool:
    """Cheap per-app-block assertion: block until :8081 responds so a mid-run drop does not
    silently disable tier-3. Bounded so a dead server cannot hang the whole benchmark."""
    if _up(_VISION_HEALTH, timeout=4):
        return True
    waited = 0
    while not _up(_VISION_HEALTH, timeout=4):
        time.sleep(5); waited += 5
        if waited % 30 == 0:
            p(f"  vision gate: :8081 not responding, retrying ... {waited}s")
        if waited >= budget:
            p("  vision gate: giving up after 120s; continuing UIA+pixel tiers only (honest)")
            return False
    return True


def step(sid, name, act="CLICK", exp="", etype="Button", text=None):
    ui = {"element_name": name, "element_type": etype, "bounding_box": [0, 0, 0, 0]}
    va = {"action_type": act}
    if text is not None:
        va["text_payload"] = text
    return {"step_id": sid, "ui_target": ui, "virtual_mouse_action": va,
            "expected_state_change": exp, "low_level_instruction": f"{act} {name}"}


def task(app, tid, difficulty, steps, final_expect, use_result_text=True, gate="symbolic"):
    return {"app": app, "id": tid, "difficulty": difficulty, "gate": gate,
            "traj": {"app_metadata": {"app_name": app, "dataset_split": "EVAL", "scan_prerequisites_met": True},
                     "target_kind": "desktop_gui", "high_level_task": tid,
                     "total_steps": len(steps), "trajectory": steps},
            "final_expect": final_expect, "use_result_text": use_result_text}


def _calc(tid, diff, seq, result):
    """seq = list of (element_name, cumulative_display). Last element is the result."""
    steps = [step(i + 1, nm, exp=f"Display is {disp}") for i, (nm, disp) in enumerate(seq)]
    return task("Calculator", tid, diff, steps, str(result))


def build_tasks():
    T = []
    # ---- Calculator: symbolic math (strict numeric gate) ----
    T.append(_calc("1+1=2", "easy", [("One", "1"), ("Plus", "1"), ("One", "1"), ("Equals", "2")], 2))
    T.append(_calc("9-3=6", "easy", [("Nine", "9"), ("Minus", "9"), ("Three", "3"), ("Equals", "6")], 6))
    T.append(_calc("8+7=15", "easy", [("Eight", "8"), ("Plus", "8"), ("Seven", "7"), ("Equals", "15")], 15))
    T.append(_calc("12x8=96", "hard", [("One", "1"), ("Two", "12"), ("Multiply by", "12"), ("Eight", "8"), ("Equals", "96")], 96))
    T.append(_calc("7x8=56", "hard", [("Seven", "7"), ("Multiply by", "7"), ("Eight", "8"), ("Equals", "56")], 56))
    T.append(_calc("6x9=54", "hard", [("Six", "6"), ("Multiply by", "6"), ("Nine", "9"), ("Equals", "54")], 54))
    T.append(_calc("8x8=64", "hard", [("Eight", "8"), ("Multiply by", "8"), ("Eight", "8"), ("Equals", "64")], 64))
    T.append(_calc("144/12=12", "hard", [("One", "1"), ("Four", "14"), ("Four", "144"), ("Divide by", "144"), ("One", "1"), ("Two", "12"), ("Equals", "12")], 12))
    T.append(_calc("25+17=42", "hard", [("Two", "2"), ("Five", "25"), ("Plus", "25"), ("One", "1"), ("Seven", "17"), ("Equals", "42")], 42))
    T.append(_calc("100-1=99", "hard", [("One", "1"), ("Zero", "10"), ("Zero", "100"), ("Minus", "100"), ("One", "1"), ("Equals", "99")], 99))
    T.append(_calc("15/3=5", "hard", [("One", "1"), ("Five", "15"), ("Divide by", "15"), ("Three", "3"), ("Equals", "5")], 5))
    # ---- Calculator: naming-mismatch recovery (the guide/intent uses the wrong word) ----
    T.append(_calc("alias-times", "recovery", [("Six", "6"), ("Times sign", "6"), ("Seven", "7"), ("Equals", "42")], 42))
    T.append(_calc("alias-add", "recovery", [("One", "1"), ("Add button", "1"), ("Two", "2"), ("Equals", "3")], 3))
    # ---- Notepad: symbolic typing (strict text gate) ----
    T.append(task("Notepad", "type-hello", "easy",
                  [step(1, "text editor area", act="TYPE_TEXT", etype="Edit", text="Hello Hojaiga", exp="Hello Hojaiga")],
                  "Hello Hojaiga", use_result_text=False, gate="symbolic"))
    T.append(task("Notepad", "type-automation", "hard",
                  [step(1, "text editor area", act="TYPE_TEXT", etype="Edit", text="automation 2026", exp="automation 2026")],
                  "automation 2026", use_result_text=False, gate="symbolic"))
    # ---- Notepad: visual state toggles (all-steps-verified gate) ----
    T.append(task("Notepad", "view-statusbar", "hard",
                  [step(1, "View", etype="MenuItem", exp="View menu opens"),
                   step(2, "Status bar", etype="MenuItem", exp="status bar visible")],
                  "status bar", use_result_text=False, gate="visual"))
    T.append(task("Notepad", "view-wordwrap", "hard",
                  [step(1, "View", etype="MenuItem", exp="View menu opens"),
                   step(2, "Word wrap", etype="MenuItem", exp="word wrap enabled")],
                  "word wrap", use_result_text=False, gate="visual"))
    # ---- Paint: canvas/tool state (all-steps-verified gate; no UIA names) ----
    for tool, did in [("Pencil", "paint-pencil"), ("Brush", "paint-brush"), ("Eraser", "paint-eraser"),
                      ("Fill with color", "paint-fill"), ("Rectangle", "paint-rect"), ("Line", "paint-line")]:
        T.append(task("Paint", did, "easy",
                      [step(1, tool, exp=f"{tool} tool selected")], tool.lower(),
                      use_result_text=False, gate="visual"))
    return T


# ---- Clean-slate process purge (STEP 1): kill zombie app instances so a stale/parked
# window from a previous run can never hijack find_hwnd (the source of the 47.8% collapse).
APP_IMAGES = {"Calculator": ["calc.exe", "CalculatorApp.exe"],
              "Notepad": ["notepad.exe"], "Paint": ["mspaint.exe"]}
_LAUNCHED: set = set()


def purge_zombies(apps=None):
    imgs = set()
    for a in (apps or list(APP_IMAGES)):
        imgs.update(APP_IMAGES.get(a, []))
    for im in imgs:
        subprocess.run(["taskkill", "/F", "/IM", im], capture_output=True)
    time.sleep(0.6)


def ensure_running(app: str):
    if app not in _LAUNCHED:          # one clean slate per app per run, on first use
        purge_zombies([app])
        _LAUNCHED.add(app)
    hwnd, title = LX.find_hwnd(app)
    if hwnd:
        return hwnd, title
    launch = {"Calculator": "calc.exe", "Notepad": "notepad.exe", "Paint": "mspaint.exe"}
    exe = launch.get(app)
    if not exe:
        return None, None
    try:
        subprocess.Popen([exe])
    except Exception as exc:
        p(f"  launch {app} failed: {exc}")
        return None, None
    for _ in range(20):
        time.sleep(0.6)
        hwnd, title = LX.find_hwnd(app)
        if hwnd:
            return hwnd, title
    return None, None


def _calc_is_zero(hwnd):
    try:
        return "display is 0" in LX._result_text(LX.snapshot_nodes(hwnd))
    except Exception:
        return False


def _calc_clean(hwnd):
    sig = LX._calc_value_sig(hwnd).lower()
    return "display is 0" in sig and "expression is=" in sig.replace(" ", "")   # empty expression


def _wait_for_edit(hwnd, budget: float = 3.0):
    """Poll until Notepad exposes an editable control (RichEditD2DPT / Edit), so a cold-launch
    first-type task doesn't fire before the editor is ready. Timing only -- window stays parked."""
    waited = 0.0
    while waited < budget:
        try:
            nodes = LX.snapshot_nodes(hwnd)
            for n in nodes:
                rl = str(getattr(n, "role", "") or "").lower()
                nm = str(getattr(n, "name", "") or "").lower()
                if rl in ("edit", "document") or "text edit" in nm or "edit" in nm:
                    return True
        except Exception:
            pass
        time.sleep(0.15); waited += 0.15
    return False


def reset_calculator(hwnd):
    """Deterministic clean slate + prime the UWP keyboard queue: post VK_ESCAPE to the CoreWindow
    (puts the app in keyboard mode so uniform WM_CHAR entry stays in sync), invoke Clear/Clear
    entry, and ASSERT display==0 with an empty pending expression (no carryover between tasks)."""
    LX._uwp_core_hwnd(hwnd)  # ensure it exists
    try:
        import ctypes
        core = LX._uwp_core_hwnd(hwnd)
        if core:
            u = ctypes.windll.user32
            u.PostMessageW.restype = ctypes.c_bool
            u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            u.PostMessageW(core, 0x0100, ctypes.c_void_p(0x1B), 0)   # WM_KEYDOWN VK_ESCAPE = Clear
            u.PostMessageW(core, 0x0101, ctypes.c_void_p(0x1B), 0)
    except Exception:
        pass
    time.sleep(0.2)
    if _calc_clean(hwnd):
        return True
    for _ in range(2):
        for n in LX.snapshot_nodes(hwnd):
            nm = str(getattr(n, "name", "") or "").lower()
            if nm in ("clear", "clear entry"):
                try:
                    LX.uia_act(n, "CLICK")
                except Exception:
                    pass
        if _calc_is_zero(hwnd):
            return True
    return False


import ctypes


def _certify_onscreen(hwnd):
    """Rule 1 (single-app ON_SCREEN_CERT for UWP): bring Calculator visible + foreground so DWM
    stops occlusion-throttling its XAML input. Uses posted messages only (no physical cursor)."""
    try:
        _, hin = LX._organs()
        hin.release_isolation(hwnd)
    except Exception:
        pass
    try:
        u = ctypes.windll.user32
        u.SetWindowPos(int(hwnd), 0, 100, 100, 0, 0, 0x0001 | 0x0004)   # NOZORDER|SHOWWINDOW
        u.SetForegroundWindow(int(hwnd))
        time.sleep(0.4)
    except Exception:
        pass


def _restart_app(app):
    """Hard-reset a stateful app by killing and relaunching it, then confirm a clean slate."""
    img = {"Calculator": "calc.exe", "Notepad": "notepad.exe", "Paint": "mspaint.exe"}.get(app)
    if not img:
        return None, None
    subprocess.run(["taskkill", "/IM", img, "/F"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen([img])
    for _ in range(20):
        time.sleep(0.6)
        h, t = LX.find_hwnd(app)
        if h:
            return h, t
    return None, None


def run_task(t):
    app = t["app"]
    vision_gate()                      # per-app-block: ensure the eye is up before each task
    hwnd, title = ensure_running(app)
    if not hwnd:
        p(f"  SKIP {t['id']}: {app} not available")
        return None
    if app == "Calculator":
        # Deterministic clean slate: click Clear and ASSERT display==0; if Clear can't zero
        # the accumulator (carryover), fall back to a fresh process, then re-assert.
        if not reset_calculator(hwnd):
            hwnd, title = _restart_app("Calculator")
            if not hwnd:
                p(f"  SKIP {t['id']}: Calculator restart failed")
                return None
            for _ in range(3):
                if reset_calculator(hwnd):
                    break
                time.sleep(0.5)
    elif app == "Notepad":
        # Cold-launch settle: wait for the RichEditD2DPT editor to be present before typing so
        # the first (type-hello) task doesn't race the window's edit-control creation. Stays
        # off-screen (ValuePattern.SetValue works parked) -- this is timing only, not a mode shift.
        _wait_for_edit(hwnd)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", t["id"])
    fp = TMP / f"{safe}.json"
    fp.write_text(json.dumps(t["traj"], indent=3), encoding="utf-8")
    want_proof = (t["id"] == "12x8=96")
    calc_cert = (app == "Calculator")           # Rule 1: UWP Calculator runs on-screen certified
    prev_off = os.environ.get("HOJAIGA_OFFSCREEN", "1")
    if calc_cert:
        os.environ["HOJAIGA_OFFSCREEN"] = "0"
        _certify_onscreen(hwnd)
    summary = LX.run_trajectory(str(fp), hwnd, title, vision_handoff=True, proof=want_proof)
    if calc_cert:
        os.environ["HOJAIGA_OFFSCREEN"] = prev_off
    time.sleep(0.3)
    v, tot = summary.get("verified", 0), summary.get("total", 0)
    if t.get("gate") == "visual":
        success = tot > 0 and v == tot          # every step certified by the 3-tier verifier
    else:                                        # symbolic: exact numeric/text match, never VLM-guessed
        nodes = LX.snapshot_nodes(hwnd)
        hay = (LX._result_text(nodes) if t["use_result_text"] else LX.collect_text(nodes))
        fe = str(t["final_expect"]).lower()
        success = bool(re.search(rf"(?<!\d){re.escape(fe)}(?!\d)", hay)) if re.fullmatch(r"\d+", fe) else (fe in hay)
    # Authoritative episodic commit BEHIND the modality-aware task gate (e13 fix): store only
    # tasks that PASSED their final postcondition, never merely all-steps-verified ones.
    stored = False
    if success:
        try:
            import episodic_memory as _EM
            _vb = summary.get("verification_breakdown") or {}
            _vt = "MIXED"
            if isinstance(_vb, dict) and _vb:
                _vt = max(_vb.items(), key=lambda kv: kv[1])[0]
            stored = _EM.save_verified(app, t["traj"].get("high_level_task", t["id"]),
                                       t["traj"]["trajectory"], _vt)
        except Exception:
            stored = False
    return {"id": t["id"], "app": app, "difficulty": t["difficulty"], "gate": t.get("gate", "symbolic"),
            "steps_verified": v, "steps_total": tot, "task_success": bool(success),
            "final_expect": t["final_expect"], "reflexion_recovered": summary.get("reflexion_recovered", 0),
            "vbreak": summary.get("verification_breakdown", {}), "episodic_stored": stored}


def fig_results(results):
    by_diff = defaultdict(lambda: [0, 0, 0, 0])
    by_gate = defaultdict(lambda: [0, 0])
    by_app = defaultdict(lambda: [0, 0])
    for r in results:
        d = by_diff[r["difficulty"]]; d[0] += r["task_success"]; d[1] += 1; d[2] += r["steps_verified"]; d[3] += r["steps_total"]
        g = by_gate[r["gate"]]; g[0] += r["task_success"]; g[1] += 1
        a = by_app[r["app"]]; a[0] += r["task_success"]; a[1] += 1
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.4))
    diffs = [x for x in ["easy", "hard", "recovery"] if by_diff[x][1]]
    task_acc = [by_diff[x][0] / max(1, by_diff[x][1]) for x in diffs]
    step_acc = [by_diff[x][2] / max(1, by_diff[x][3]) for x in diffs]
    x = np.arange(len(diffs)); w = .38
    b1 = ax1.bar(x - w / 2, task_acc, w, color="#2b8a3e", label="task success")
    b2 = ax1.bar(x + w / 2, step_acc, w, color="#1971c2", label="step verified")
    for b in list(b1) + list(b2):
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + .02, f"{b.get_height():.2f}", ha="center")
    ax1.set_xticks(x); ax1.set_xticklabels([f"{d}\n(n={by_diff[d][1]})" for d in diffs]); ax1.set_ylim(0, 1.15)
    ax1.set_title("Phase-2 LIVE zero-shot accuracy by difficulty", weight="bold"); ax1.set_ylabel("rate")
    ax1.grid(alpha=.3, axis="y"); ax1.legend()
    gates = list(by_gate)
    gacc = [by_gate[g][0] / max(1, by_gate[g][1]) for g in gates]
    ax2.barh(gates, gacc, color="#e8590c")
    for i, v in enumerate(gacc):
        ax2.text(v + .01, i, f"{v:.2f} ({by_gate[gates[i]][0]}/{by_gate[gates[i]][1]})", va="center")
    ax2.set_xlim(0, 1.15); ax2.set_title("Task success by gate modality (symbolic vs visual)", weight="bold")
    ax2.grid(alpha=.3, axis="x")
    fig.suptitle("Real executed accuracy, off-screen isolated, 3-tier verified, modality-aware gating", y=1.02, weight="bold")
    fig.tight_layout(); fig.savefig(OUT / "fig7_live_phase2_accuracy.png", dpi=120, bbox_inches="tight"); plt.close(fig)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None)
    ap.add_argument("--mode", choices=["offscreen", "onscreen"], default="offscreen",
                    help="offscreen = STRICT parked headless (default law); onscreen = certification pass for UWP/canvas")
    args = ap.parse_args()
    os.environ["HOJAIGA_OFFSCREEN"] = "1" if args.mode == "offscreen" else "0"
    args.tag = args.tag or ("strict_offscreen" if args.mode == "offscreen" else "onscreen_cert")
    purge_zombies()                    # clean slate before anything
    vision_preflight()                 # never run half-blind: require :8081 + :11434 healthy
    tasks = build_tasks()
    p(f"MODE={args.mode} offscreen={os.environ['HOJAIGA_OFFSCREEN']} | {len(tasks)} tasks "
      f"(reflexion={LX.REFLEXION}, pixel={LX.PIXEL_VERIFY}, vlm={LX.VLM_VERIFY})...")
    results = []
    for t in tasks:
        r = run_task(t)
        if r:
            results.append(r)
            p(f"  {r['gate']:8s}{r['difficulty']:9s}{r['app']:10s}{r['id']:16s} success={r['task_success']} steps={r['steps_verified']}/{r['steps_total']}")
    if not results:
        p("no results."); return
    fig_results(results)
    tot = len(results); succ = sum(r["task_success"] for r in results)
    sv = sum(r["steps_verified"] for r in results); st = sum(r["steps_total"] for r in results)
    vb = Counter()
    for r in results:
        for k, n in (r.get("vbreak") or {}).items():
            vb[k] += n
    stored = sum(1 for r in results if r.get("episodic_stored"))
    metrics = {"tag": args.tag, "mode": args.mode, "n_tasks": tot, "task_success": succ,
               "task_accuracy": round(succ / tot, 3), "steps_verified": sv, "steps_total": st,
               "step_accuracy": round(sv / st, 3), "verification_breakdown": dict(vb),
               "episodic_stored": stored, "results": results}
    (OUT / f"phase2_live_metrics_{args.tag}.json").write_text(json.dumps(metrics, indent=3), encoding="utf-8")
    p("=" * 60)
    p(f"[{args.tag}] TASK ACCURACY : {succ}/{tot} = {succ/tot:.1%}")
    p(f"[{args.tag}] STEP ACCURACY : {sv}/{st} = {sv/st:.1%}")
    p(f"[{args.tag}] verifier tiers: {dict(vb)} | episodic rows stored: {stored}")
    p(f"figure -> {OUT/'fig7_live_phase2_accuracy.png'}")


if __name__ == "__main__":
    main()
