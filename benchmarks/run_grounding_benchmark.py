"""Grounding benchmark: runs DesktopGrounding.ground() on real apps and saves each ladder report.

Per app: (A) plain ground (default max_tier=2), (B) forced escalation with a target text that
cannot exist, max_tier=4 (measures OCR + vision cost), plus a PrintWindow black-frame check.
Reports land in benchmarks/grounding_reports/<app>.json. Nothing here is edited by hand.
"""
import json, os, subprocess, sys, time, statistics

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.desktop_grounding import DesktopGrounding  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "grounding_reports")
os.makedirs(OUT, exist_ok=True)

APPS = {
    # name: (app_hint for find_window, launch command or None)
    "settings": ("Settings", ["cmd", "/c", "start", "ms-settings:"]),
    "notepad": ("Notepad", ["notepad.exe"]),
    "chrome": ("Chrome", None),  # already running; never relaunched
    "vscode": ("Visual Studio Code", [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")]),
    "claude_electron": ("Claude", None),  # Electron app; VS Code is excluded by find_window's 'visual studio' title filter
    "paint_canvas": ("Paint", ["mspaint.exe"]),  # stand-in canvas app: Blender is not installed
}
FORCED_TARGET = "zz_nonexistent_target_qq"


def black_frame_check(g, hwnd):
    """PrintWindow sanity: returns stats of the captured PNG, flags an all-black frame."""
    try:
        from PIL import Image
        p = g._window_png(hwnd)
        if not p:
            return {"captured": False}
        im = Image.open(p).convert("L")
        px = list(im.resize((64, 64)).getdata())
        return {"captured": True, "size": im.size, "mean": round(statistics.mean(px), 1),
                "stdev": round(statistics.pstdev(px), 1),
                "all_black": max(px) < 8}
    except Exception as e:  # report, never hide
        return {"captured": False, "error": repr(e)}


def summarize(elements):
    by = {}
    for e in elements:
        by.setdefault(e.tier, []).append(e.confidence)
    return {k: {"n": len(v), "conf_min": round(min(v), 2), "conf_mean": round(statistics.mean(v), 2),
                "conf_max": round(max(v), 2)} for k, v in by.items()}


def run(name, hint, launch):
    g = DesktopGrounding()
    rec = {"app": name, "hint": hint, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if g.find_window(hint) is None and launch:
        try:
            subprocess.Popen(launch)
            rec["launched"] = True
        except Exception as e:
            rec["launch_error"] = repr(e)
        for _ in range(40):
            time.sleep(0.5)
            if g.find_window(hint):
                time.sleep(2.0)
                break
    t = time.perf_counter()
    hwnd, els, rep = g.ground(hint, max_tier=2)
    rec["plain"] = {"wall_ms": round((time.perf_counter() - t) * 1000, 1), "report": rep,
                    "by_tier": summarize(els), "sample": [e.as_dict() for e in els[:5]]}
    if hwnd:
        rec["black_frame"] = black_frame_check(g, hwnd)
        g.reset_vision_budget()
        t = time.perf_counter()
        _, els2, rep2 = g.ground(hint, target_text=FORCED_TARGET, max_tier=4)
        rec["forced"] = {"wall_ms": round((time.perf_counter() - t) * 1000, 1), "report": rep2,
                         "by_tier": summarize(els2), "sample": [e.as_dict() for e in els2[:5]]}
    with open(os.path.join(OUT, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, default=str)
    print(name, "hwnd", hwnd, "plain", rec["plain"]["report"].get("tier_ms"),
          "forced", rec.get("forced", {}).get("report", {}).get("tier_ms"),
          "skipped", rec.get("forced", {}).get("report", {}).get("tiers_skipped"), flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(APPS)
    # Vision tier loads OmniParser weights in the background; without waiting, it reports
    # 'vision:warming-up' and we would measure nothing.
    print("warmup:", DesktopGrounding.start_warmup(), flush=True)
    print("vision ready:", DesktopGrounding.wait_vision_ready(300.0), flush=True)
    for n in only:
        try:
            run(n, *APPS[n])
        except Exception as e:
            print(n, "FAILED", repr(e), flush=True)
