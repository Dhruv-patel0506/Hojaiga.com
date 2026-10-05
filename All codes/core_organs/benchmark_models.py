"""
benchmark_models.py -- which local Brain / vision model gives the best accuracy per second on THIS box
(6 GB laptop GPU, shared by llama-server + Ollama)?

Self-grading from a real app's own UIA tree (no hand-written answers):
  Brain  : judge must pick the control we name ('click the <name> control'); score = valid% / correct% / ms
  Vision : model must locate one named control as a box; hit = box overlaps the UIA box (IoU>0.3 or centre inside)

  python benchmark_models.py --app notepad --brain qwen2.5:7b,qwen2.5:3b,llama3.1 \
         --vision llamacpp,ollama:qwen2.5vl:3b,ollama:minicpm-v
"""

import argparse
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import headless_input as hin
from core_organs import app_scan, qwen_vl_scanner as qv
from core_organs.desktop_grounding import ConstrainedJudge, DesktopGrounding, GroundedElement
from core_organs.organ_40_app_launcher import resolve_and_launch


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="notepad")
    ap.add_argument("--brain", default="qwen2.5:7b,qwen2.5:3b,llama3.1")
    ap.add_argument("--vision", default="llamacpp,ollama:qwen2.5vl:3b,ollama:minicpm-v")
    ap.add_argument("--n-brain", type=int, default=5)
    ap.add_argument("--n-vision", type=int, default=2)
    a = ap.parse_args()
    g = DesktopGrounding()
    pre = g.find_window(a.app) is not None
    if not pre:
        resolve_and_launch(a.app)
        time.sleep(7)
    hwnd = g.find_window(a.app)
    scan = app_scan.scan_desktop(hwnd)
    named = {}
    for e in scan.elements:
        nm = (e["name"] or "").strip()
        if 3 <= len(nm) <= 24 and nm.lower() not in named and e["bbox"][2] - e["bbox"][0] > 8 and e["hwnd"] == hwnd:
            named[nm.lower()] = e
    targets = list(named.values())
    lines = [f"Model benchmark on '{a.app}' ({scan.summary()})", ""]
    els = [GroundedElement(id=str(i), name=e["name"] or e["role"], role=e["role"], bbox=e["bbox"], tier="uia",
                           confidence=0.9, hwnd=hwnd) for i, e in enumerate(scan.elements)]
    pick = targets[:: max(1, len(targets) // a.n_brain)][: a.n_brain]
    lines.append("BRAIN (judge picks the named control; decisive shortcut OFF)")
    for model in [m for m in a.brain.split(",") if m]:
        j = ConstrainedJudge()
        j.model = model
        valid = ok = 0
        lat = []
        for tgt in pick:
            t0 = time.perf_counter()
            d = j.decide(f"click the '{tgt['name']}' control", els, use_decisive=False)
            lat.append((time.perf_counter() - t0) * 1000)
            if d and not d.get("invalid"):
                valid += 1
                ok += int(els[d["element_index"]].name.lower() == tgt["name"].lower())
        n = max(1, len(pick))
        lines.append(f"  {model:<22} valid {valid/n*100:3.0f}%  correct {ok/n*100:3.0f}%  {sum(lat)/max(1,len(lat)):7.0f} ms/decision")
        print(lines[-1], flush=True)
    img, why = hin.capture_window(hwnd)
    lines.append("")
    lines.append("VISION (locate one named control; hit = IoU>0.3 or centre inside the real box)")
    if img is None:
        lines.append(f"  capture failed: {why}")
    else:
        off = g._window_origin(hwnd)
        vt = targets[:: max(1, len(targets) // a.n_vision)][: a.n_vision]
        for backend in [b for b in a.vision.split(",") if b]:
            hits, ms, errs = 0, [], 0
            for tgt in vt:
                rb = (tgt["bbox"][0] - off[0], tgt["bbox"][1] - off[1], tgt["bbox"][2] - off[0], tgt["bbox"][3] - off[1])
                box, meta = qv.locate(img, tgt["name"], backend=backend, timeout_s=120)
                ms.append(meta["ms"])
                errs += int(bool(meta["error"]))
                if box:
                    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
                    if iou(box, rb) > 0.3 or (rb[0] <= cx <= rb[2] and rb[1] <= cy <= rb[3]):
                        hits += 1
            n = max(1, len(vt))
            lines.append(f"  {backend:<26} hit {hits}/{len(vt)} ({hits/n*100:.0f}%)  {sum(ms)/max(1,len(ms)):8.0f} ms/locate  errors={errs}")
            print(lines[-1], flush=True)
    text = "\n".join(lines)
    print("\n" + text)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_benchmark_results.txt"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n\n")
    if not pre and hwnd:
        hin._u32.PostMessageW(hwnd, 0x0010, 0, 0)


if __name__ == "__main__":
    main()
