"""
vision_accuracy.py -- how accurately do OUR vision models find real controls? (OmniParser in-process vs Qwen2.5-VL-7B on the
llama.cpp server that start_hojaiga.bat boots on :8081).

A real app window is launched hidden, parked off-screen, captured with PrintWindow (the same capture the product's
vision tier uses), and graded against an INDEPENDENT UIA read of that window (names + boxes):
  OmniParser   one full-window parse, then per control:  localized = a detected box contains the control's centre,
               labelled = that box's caption shares a word with the control's name
  Qwen2.5-VL   one 'locate <control>' request per control; hit = IoU > 0.3 or the box contains the control's centre
Latency is wall time on THIS machine (CPU torch for OmniParser, GPU-offload llama.cpp for Qwen). Honest: tiny samples,
real numbers.   python vision_accuracy.py [--apps notepad,paint] [--n 10]
"""
import json
import os
import random
import re
import sys
import tempfile
import time

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]


def toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 1}


def main():
    a = sys.argv[1:]
    apps = a[a.index("--apps") + 1].split(",") if "--apps" in a else ["notepad", "paint"]
    n = int(a[a.index("--n") + 1]) if "--n" in a else 10
    import uiautomation as auto
    from core_organs import background_window as bw
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    from core_organs import qwen_vl_scanner as qv
    from core_organs import universal_scan as us
    USER = {"notepad": "Notepad", "paint": "MSPaintApp"}
    rng = random.Random(11)
    out = []
    t_omni = time.time()
    omni = dg.DesktopGrounding._get_vision_parser()
    omni_load_s = round(time.time() - t_omni, 1)
    for app in apps:
        row = {"app": app, "omni_load_s": omni_load_s}
        if any(hin._class_name(h) == USER.get(app, "?") for h, _t in hin.top_level_titles(False)):
            row["skipped"] = "the user's window is open"
            out.append(row)
            continue
        info = us.launch_hidden(app, timeout_s=30.0)
        h = info.get("hwnd")
        try:
            g = dg.DesktopGrounding()
            with bw.BackgroundSession(h):
                g._await_paint(h)
                time.sleep(0.8)
                img, why = hin.capture_window(h)
                if img is None:
                    row["error"] = f"no capture: {why}"
                    out.append(row)
                    continue
                rc = hin.wt.RECT()
                hin._u32.GetWindowRect(h, hin.ctypes.byref(rc))
                gt = {}
                for c, _d in auto.WalkControl(auto.ControlFromHandle(h), maxDepth=18):
                    nm = (c.Name or "").strip()
                    r = c.BoundingRectangle
                    if (c.ControlTypeName in ("ButtonControl", "MenuItemControl", "TabItemControl", "ListItemControl", "CheckBoxControl")
                            and 3 <= len(nm) <= 24 and r.right - r.left > 8 and r.bottom - r.top > 8 and nm.lower() not in gt):
                        gt[nm.lower()] = (nm, (r.left - rc.left, r.top - rc.top, r.right - rc.left, r.bottom - rc.top))
                row["image"] = f"{img.size[0]}x{img.size[1]}"
                row["gt_pool"] = len(gt)
                sample = rng.sample(list(gt.values()), min(n, len(gt)))
                # ---- OmniParser
                path = os.path.join(tempfile.gettempdir(), f"hj_va_{os.getpid()}.png")
                img.save(path)
                t = time.time()
                els = omni.parse_screenshot(path)
                row["omni_parse_s"] = round(time.time() - t, 1)
                row["omni_detections"] = len(els)
                loc = lab = 0
                for nm, (x0, y0, x1, y1) in sample:
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    inside = [e for e in els if e.bounds[0] <= cx <= e.bounds[2] and e.bounds[1] <= cy <= e.bounds[3]]
                    loc += bool(inside)
                    lab += any(toks(nm) & toks(e.text) for e in inside)
                row["omni_localized"] = round(loc / len(sample), 2)
                row["omni_labelled"] = round(lab / len(sample), 2)
                os.remove(path)
                # ---- Qwen2.5-VL (llama.cpp :8081)
                if qv.available():
                    hits, ms = 0, []
                    for nm, (x0, y0, x1, y1) in sample:
                        box, meta = qv.locate(img, nm, backend="llamacpp", timeout_s=100)
                        ms.append(meta["ms"])
                        if box:
                            bx, by = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
                            ix = max(0, min(box[2], x1) - max(box[0], x0)) * max(0, min(box[3], y1) - max(box[1], y0))
                            un = (box[2] - box[0]) * (box[3] - box[1]) + (x1 - x0) * (y1 - y0) - ix
                            hits += bool((un and ix / un > 0.3) or (x0 <= bx <= x1 and y0 <= by <= y1))
                    row["qwen_hit"] = round(hits / len(sample), 2)
                    row["qwen_mean_ms"] = int(sum(ms) / len(ms))
                else:
                    row["qwen"] = "server :8081 not reachable"
                row["sampled"] = len(sample)
        finally:
            if h:
                us.close_window(h, discard_unsaved=True, timeout_s=8)
        out.append(row)
        print(json.dumps(row), flush=True)
    with open(r"D:\new_automation\data\vision_accuracy_results.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
