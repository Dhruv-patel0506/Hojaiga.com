"""
canvas_stages -- run Stage 1 (shapes), Stage 2 (flowchart), Stage 3 (curves) on an owned Paint and write the measured report + contact sheets.

    python -m core_organs.canvas_stages 1 2 3         # each stage in a fresh Paint (blank canvas), results in data/canvas_runs/<stamp>/
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

from core_organs import canvas_artist as CA

OUT = r"D:\new_automation\data\canvas_runs"


def _measure(tag: str, painter: Any, strokes: List[CA.Stroke], before: Any, groups: Dict[str, List[CA.Stroke]], sheet_dir: str, execs: Dict[str, Any], reference: Any = None, trace_stats: Any = None, box: Any = None) -> Dict[str, Any]:
    from core_organs import canvas_live as CL
    time.sleep(0.8)
    after = painter.grab()
    box = box or painter.canvas()           # the box found BEFORE drawing: after heavy drawing the white area is split by ink into pieces and 'the largest white block' is no longer the canvas
    size = before.size
    res = {"stage": tag, **execs, "strokes": len(strokes), "containment_pct": CA.containment(strokes, box), "completion_pct": CA.completion(strokes, after, box),
           "leak_px": CA.leak_pixels(before, after, box), "leak_bbox": CA.leak_bbox(before, after, box), "overlap_pairs": CA.overlap_pairs(groups, size, 6) if groups else [], "canvas": [round(v) for v in box]}
    if trace_stats is not None:
        res.update(CA.trace_fidelity(after, box, trace_stats))
        res["contours_kept"], res["max_depth"], res["ink_length_px"] = trace_stats["contours_kept"], trace_stats["max_depth"], trace_stats["ink_length_px"]
        res["strokes_planned"] = trace_stats["strokes"]
    res["sheet"] = CL.contact_sheet(before, after, box, strokes, os.path.join(sheet_dir, f"{tag}.jpg"), tag, reference)
    return res


REF_DIR = r"D:\new_automation\data\reference_art"


def references() -> List[str]:
    """Every image in data/reference_art (the downloaded public-domain plates and anything else the person puts there)."""
    return sorted(os.path.join(REF_DIR, f) for f in os.listdir(REF_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp"))) if os.path.isdir(REF_DIR) else []


def _title_of(ref: str, side: Dict[str, Any]) -> str:
    return str(side.get("title") or os.path.splitext(os.path.basename(ref))[0]).upper()[:28]


def _labels_of(side: Dict[str, Any], n: int = 6) -> List[Any]:
    """Labels from the optional sidecar data, else 'Part N' (placed on landmarks that CT.auto_landmarks finds from the traced strokes)."""
    lab = [(x["text"], tuple(x["at"])) for x in side.get("labels", []) if "text" in x and "at" in x]
    return lab or [f"Part {i + 1}" for i in range(n)]


def _steps_of(side: Dict[str, Any], n_art: int, n_labels: int) -> List[str]:
    return list(side.get("steps") or [f"Traced {n_art} strokes from the outside in", f"Marked {n_labels} parts with leaders", "Every label sits outside the drawing"])


def stage_colour(p: Any, ref: str, box: Any, max_strokes: int = 170) -> Dict[str, Any]:
    """Stage 5: trace the plate, then colour it: exact RGB from Edit colours, bucket fills where the outline is closed (simulated first), clipped hatch elsewhere, then 4-band shading on the largest regions."""
    import cv2
    import numpy as np
    from core_organs import canvas_colour as CC
    refimg = cv2.imread(ref)
    strokes, tstats = CA.trace_strokes(refimg, box, max_strokes=0, coverage=0.97, time_budget_s=900)
    p.select("Pencil")
    ex = CA.execute(p, strokes)
    ex["repair"] = CA.repair(p, strokes, box)
    time.sleep(0.8)
    after_line = p.grab()
    size = after_line.size
    outline = CA.raster(strokes, size, 3)
    ops, info = CC.plan_colouring(refimg, tstats, size, outline, k=5, max_regions=4, shade_top=1)
    t0 = time.time()
    counts = CC.apply_ops(p, ops)
    secs = time.time() - t0
    time.sleep(0.8)
    after_col = p.grab()
    met = CC.colour_metrics(after_line, after_col, ops, info, box, info.get("masks", {}))
    exact = []
    arr = np.asarray(after_col.convert("RGB"))
    for r in info["regions"]:
        if r["bucket"]:
            sx, sy = int(r["seed"][0]), int(r["seed"][1])
            got = arr[sy, sx].tolist()
            exact.append({"region": r["region"], "wanted": list(r["base"]), "got": got, "delta": int(np.abs(np.array(got) - np.array(r["base"])).max())})
    return {"outline": ex, "ops": counts, "colour_seconds": round(secs, 1), "regions": [{k: v for k, v in r.items()} for r in info["regions"]], "bucket": info["bucket"], "hatched": info["hatched"],
            **met, "exact_rgb_checks": exact, "outline_strokes": strokes, "after_line": after_line, "after_col": after_col, "refimg": refimg}


def stage_lightboard(p: Any, ref: str, box: Any, max_strokes: int = 140) -> Dict[str, Any]:
    """Stage 6: a lightboard page -- the plate in the core zone, numbered call-outs with leaders to the traced parts, a title, a numbered step footer."""
    import cv2
    from core_organs import canvas_teach as CT
    zones = CT.lightboard_zones(box)
    refimg = cv2.imread(ref)
    art, tstats = CA.trace_strokes(refimg, CA.inset(zones["core"], 8), max_strokes=0, coverage=0.97, time_budget_s=900)
    side = CT.load_sidecar(ref)
    labels = _labels_of(side)
    lb, layout = CT.plan_lightboard(box, art, _title_of(ref, side), labels, _steps_of(side, len(art), len(labels)), stats=tstats)
    strokes = art + lb
    ex = CA.execute(p, strokes)
    ex["repair"] = CA.repair(p, strokes, box)
    return {"exec": ex, "strokes": strokes, "art": art, "layout": layout, "tstats": tstats, "refimg": refimg}


def stage_hybrid(p: Any, ref: str, box: Any, max_strokes: int = 120) -> Dict[str, Any]:
    """Stage 7: a hybrid composition -- traced plate (left), a flowchart of the method (top right), a magnified detail (circle on the plate, leader lines, framed zoom panel bottom right), a lightboard frame
    with call-outs, title and numbered steps. Every part is placed by the planner; the measured checks are in `audit` + overlap pairs."""
    import cv2
    from core_organs import canvas_teach as CT
    zones = CT.lightboard_zones(box)
    core = CA.inset(zones["core"], 8)
    cw = core[2] - core[0]
    art_box = (core[0], core[1], core[0] + 0.58 * cw, core[3])
    right = (core[0] + 0.62 * cw, core[1], core[2], core[3])
    mid = right[1] + 0.58 * (right[3] - right[1])
    flow_box, zoom_box = (right[0], right[1], right[2], mid - 10), (right[0] + 10, mid + 10, right[2] - 10, right[3] - 6)
    refimg = cv2.imread(ref)
    art, tstats = CA.trace_strokes(refimg, art_box, max_strokes=0, coverage=0.97, time_budget_s=900)
    side = CT.load_sidecar(ref)
    flow_labels = list(side.get("flow") or ["IMAGE", "EDGES", "STROKES"])        # names of the pipeline's own stages (overridable data)
    flow, boxes = CA.plan_flowchart(flow_box, flow_labels, [(i, i + 1) for i in range(len(flow_labels) - 1)], cols=1, pad=12)
    radius = 0.07 * min(art_box[2] - art_box[0], art_box[3] - art_box[1])
    lm = CT.snap_to_art(CT.densest_window(art, radius), art)         # the detail to magnify is the densest ink of the traced art, found from the strokes
    h, w = refimg.shape[:2]
    fx, fy = CT.canvas_to_rel(lm, tstats)                              # the same place on the REFERENCE, for the zoom panel's re-trace at higher resolution
    half = radius / max(tstats["map"]["scale"], 1e-6)
    crop = refimg[int(max(0, fy * h - half)):int(min(h, fy * h + half)), int(max(0, fx * w - half)):int(min(w, fx * w + half))]
    zoom_strokes, _zs = CA.trace_strokes(crop, CA.inset(zoom_box, 8), max_strokes=60)
    mag = CT.magnifier(lm, radius, zoom_box, zoom_strokes)
    labels = _labels_of(side, 3)[:3]
    lb, layout = CT.plan_lightboard(box, art + flow + mag, _title_of(ref, side), labels, _steps_of(side, len(art), len(labels)) + ["Magnified the densest detail"], stats=tstats)
    strokes = art + flow + mag + lb
    groups = {"art": art, "flow": flow, "zoompanel": [x for x in mag if x.group in ("magnifier:panel",)] + zoom_strokes}
    ex = CA.execute(p, strokes)
    ex["repair"] = CA.repair(p, strokes, box)
    leaders = [x for x in mag if x.group == "magnifier:leader"]
    crossing_flow = sum(1 for ld in leaders for b in boxes if CT._seg_hits_box(ld.meta["from"], ld.meta["to"], b, 0.0))
    return {"exec": ex, "strokes": strokes, "groups": groups, "layout": layout, "audit_layout": CT.audit(layout, art + flow + mag, strokes, box, p.grab().size), "leaders_crossing_flowchart": crossing_flow,
            "magnifier_landmark": lm, "refimg": refimg}


def _run_composed(p: Any, st: int, ref: str, report: Dict[str, Any], sheet_dir: str, max_strokes: int) -> None:
    """Stages 5-7 on a fresh Paint: the plan is built from the box found before drawing; the metrics use that same box."""
    from core_organs import canvas_live as CL
    p.select("Pencil")
    time.sleep(0.6)
    before = p.grab()
    box = p.canvas()
    out: Dict[str, Any]
    if st == 5:
        r = stage_colour(p, ref, box)
        tag = "stage5_colour_" + os.path.splitext(os.path.basename(ref))[0]
        met = _measure(tag, p, r.pop("outline_strokes"), before, {}, sheet_dir, {"outline_exec": r.pop("outline")}, reference=r.pop("refimg"), box=box)
        r.pop("after_line"), r.pop("after_col")
        met.update(r)
    elif st == 6:
        r = stage_lightboard(p, ref, box, max_strokes=min(max_strokes, 140))
        tag = "stage6_lightboard_" + os.path.splitext(os.path.basename(ref))[0]
        from core_organs import canvas_teach as CT
        aud = CT.audit(r["layout"], r["art"], r["strokes"], box, before.size)
        met = _measure(tag, p, r["strokes"], before, {}, sheet_dir, {**r["exec"]}, reference=r["refimg"], box=box)
        met["audit"] = {k: v for k, v in aud.items()}
        met["callouts"] = [c.label for c in r["layout"]["callouts"]]
    else:
        r = stage_hybrid(p, ref, box)
        tag = "stage7_hybrid_" + os.path.splitext(os.path.basename(ref))[0]
        met = _measure(tag, p, r["strokes"], before, r["groups"], sheet_dir, {**r["exec"]}, reference=r["refimg"], box=box)
        met["audit"] = r["audit_layout"]
        met["leaders_crossing_flowchart"] = r["leaders_crossing_flowchart"]
    met["stroke_seconds"] = round(p.stroke_seconds, 1)
    met["failures"] = p.fails[:6]
    met["waited_for_the_person_s"] = round(p.waited_s, 1)
    report["stages"].append(met)
    print("STAGE", json.dumps({k: v for k, v in met.items() if k != "sheet"}, default=str), flush=True)


def run(stages: List[Any], max_strokes: int = 300) -> Dict[str, Any]:
    from core_organs import agent_executor as AE, canvas_live as CL
    stamp = time.strftime("%Y%m%d_%H%M%S")
    sheet_dir = os.path.join(OUT, stamp)
    report: Dict[str, Any] = {"stamp": stamp, "stages": []}
    jobs: List[Any] = []
    for st in stages:
        if st == 4:
            jobs.extend((4, r) for r in references())
        elif st in (5, 6, 7):
            jobs.extend((st, r) for r in references())
        else:
            jobs.append((st, ""))
    for st, ref in jobs:
        with AE.LiveSession("paint") as s:
            p = CL.LivePainter(s)
            if st in (5, 6, 7):
                _run_composed(p, st, ref, report, sheet_dir, max_strokes)
                continue
            p.select("Pencil")                                          # opens the toolbar flyout, picks the tool, closes it again: same layout before and after
            time.sleep(0.6)
            before = p.grab()
            box = p.canvas()
            if st == 1:
                cells = CA.grid_cells(box, 2, 2, 60.0)
                strokes = CA.plan_shapes(cells, ["rectangle", "ellipse", "triangle", "line"])
                groups = {x.group: [x] for x in strokes}
                tag = "stage1_shapes"
            elif st == 2:
                strokes, boxes = CA.plan_flowchart(box, ["USER", "SCAN", "RAG", "MODEL", "GUARD", "ACT"], [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)], cols=3, pad=30)
                groups = {f"box{i}": [x] for i, x in enumerate(y for y in strokes if y.kind == "rectangle")}
                tag = "stage2_flowchart"
            elif st == 3:
                cells = CA.grid_cells(box, 2, 3, 40.0)
                strokes = CA.plan_curves(cells)
                groups = {x.group: [x] for x in strokes}
                tag = "stage3_curves"
            else:
                import cv2
                refimg = cv2.imread(ref)
                strokes, tstats = CA.trace_strokes(refimg, box, max_strokes=0, coverage=0.97, time_budget_s=900)
                groups = {}
                tag = "stage4_trace_" + os.path.splitext(os.path.basename(ref))[0]
            ex = CA.execute(p, strokes)
            ex["repair"] = CA.repair(p, strokes, box)
            ex["stroke_seconds"] = round(p.stroke_seconds, 1)
            ex["failures"] = p.fails[:6]
            ex["waited_for_the_person_s"] = round(p.waited_s, 1)
            report["stages"].append(_measure(tag, p, strokes, before, groups, sheet_dir, ex, reference=(refimg if st == 4 else None), trace_stats=(tstats if st == 4 else None), box=box))
            print("STAGE", json.dumps({k: v for k, v in report["stages"][-1].items() if k != "sheet"}), flush=True)
    os.makedirs(sheet_dir, exist_ok=True)
    json.dump(report, open(os.path.join(sheet_dir, "report.json"), "w"), indent=1)
    print("DONE", sheet_dir, flush=True)
    return report


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(900, repeat=True, file=sys.stderr)         # a run that stops moving shows WHERE it stands in the log (every 15 min)
    run([int(a) for a in sys.argv[1:]] or [1, 2, 3])
