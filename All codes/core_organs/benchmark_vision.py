"""
benchmark_vision.py -- OmniParser vs Qwen2.5-VL-7B on the SAME real screens.

Ground truth = the app's own UIA tree (names + boxes). For each GT control we ask:
  localized : does any detected box contain the GT control's centre?
  labelled  : is that detection's text/caption word-overlapping the GT name?
Reports recall + latency per engine and a verdict. Run:
  python benchmark_vision.py            (launches/uses Paint, closes it if it launched it)
Needs: llama-server on :8081 (start_hojaiga.bat) for the Qwen side; OmniParser warms in-process.
"""

import os
import re
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import headless_input as hin
from core_organs import qwen_vl_scanner as qv
from core_organs.desktop_grounding import DesktopGrounding, get_loop, _act_on_element
from core_organs.organ_40_app_launcher import resolve_and_launch


def toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 1}


def score(gt, dets, off):
    """gt: [(name,(x1,y1,x2,y2) screen)]; dets: [(text,(x1,y1,x2,y2) image-relative)]."""
    loc = lab = 0
    for name, (a, b, c, d) in gt:
        cx, cy = (a + c) // 2 - off[0], (b + d) // 2 - off[1]
        near = [t for t, (x1, y1, x2, y2) in dets if x1 <= cx <= x2 and y1 <= cy <= y2]
        if near:
            loc += 1
            if any(toks(name) & toks(t) for t in near):
                lab += 1
    n = max(1, len(gt))
    return loc / n, lab / n


def main():
    g = DesktopGrounding()
    launched = False
    if not g.find_window("mspaint"):
        resolve_and_launch("mspaint")
        launched = True
        time.sleep(6)
    loop = get_loop()
    results = []
    omni = DesktopGrounding._get_vision_parser()          # blocking cold load is fine in a benchmark
    for screen in ("main-window", "file-menu-open"):
        hwnd = g.find_window("mspaint")
        if screen == "file-menu-open":
            h, els, _ = g.ground("mspaint")
            f = next((e for e in els if e.name == "File"), None)
            if f:
                _act_on_element(f, "click")
                loop._settle(hwnd)
        img, why = hin.capture_window(hwnd)
        if img is None:
            results.append((screen, "capture failed: " + why))
            continue
        off = g._window_origin(hwnd)
        h, els, _ = g.ground("mspaint")
        gt = [(e.name, e.bbox) for e in els if e.tier == "uia" and len(e.name) > 1
              and e.bbox[2] - e.bbox[0] > 4 and e.hwnd == hwnd]
        # OmniParser
        path = os.path.join(os.environ["TEMP"], "bench_screen.png")
        img.save(path)
        t0 = time.perf_counter()
        oels = omni.parse_screenshot(path) if omni else []
        o_ms = (time.perf_counter() - t0) * 1000
        o_det = [(e.text, e.bounds) for e in oels]
        # Qwen-VL
        t0 = time.perf_counter()
        qels, meta = qv.parse_image(img)
        q_ms = (time.perf_counter() - t0) * 1000
        q_det = [(e["name"], e["bbox"]) for e in qels]
        ol, ob = score(gt, o_det, off)
        ql, qb = score(gt, q_det, off)
        results.append((screen, len(gt), (len(o_det), o_ms, ol, ob), (len(q_det), q_ms, ql, qb, meta.get("error", ""))))
    lines = ["Vision benchmark - OmniParser vs Qwen2.5-VL-7B (same Paint screens, UIA ground truth)", ""]
    tot = {"o": [0, 0, 0.0], "q": [0, 0, 0.0]}
    for r in results:
        if isinstance(r[1], str):
            lines.append(f"{r[0]}: {r[1]}")
            continue
        screen, n, o, q = r
        lines.append(f"[{screen}] GT controls={n}")
        lines.append(f"  OmniParser : {o[0]:3d} dets {o[1]:8.0f} ms  localized {o[2]*100:5.1f}%  labelled {o[3]*100:5.1f}%")
        lines.append(f"  Qwen2.5-VL : {q[0]:3d} dets {q[1]:8.0f} ms  localized {q[2]*100:5.1f}%  labelled {q[3]*100:5.1f}% {q[4]}")
        tot["o"][0] += o[2]; tot["o"][1] += o[3]; tot["o"][2] += o[1]
        tot["q"][0] += q[2]; tot["q"][1] += q[3]; tot["q"][2] += q[1]
    k = max(1, sum(1 for r in results if not isinstance(r[1], str)))
    lines.append("")
    lines.append(f"MEAN  OmniParser: localized {tot['o'][0]/k*100:.1f}% labelled {tot['o'][1]/k*100:.1f}% {tot['o'][2]/k:.0f} ms")
    lines.append(f"MEAN  Qwen2.5-VL: localized {tot['q'][0]/k*100:.1f}% labelled {tot['q'][1]/k*100:.1f}% {tot['q'][2]/k:.0f} ms")
    wins = (tot["q"][1] / k > tot["o"][1] / k + 0.10) and (tot["q"][2] / k < tot["o"][2] / k * 2)
    lines.append("VERDICT: " + ("Qwen-VL measurably wins (label recall +10pts, <2x latency) -> may be promoted"
                               if wins else "OmniParser stays primary; Qwen-VL stays behind HOJAIGA_QWEN_VL=1"))
    text = "\n".join(lines)
    print(text)
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vision_benchmark_results.txt"), "w",
         encoding="utf-8").write(text + "\n")
    if launched:
        h = g.find_window("mspaint")
        if h:
            hin._u32.PostMessageW(h, 0x0010, 0, 0)


if __name__ == "__main__":
    main()
