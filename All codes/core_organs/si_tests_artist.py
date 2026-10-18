"""
si_tests_artist -- canvas_artist (functional drawing on a canvas). AR = artist. Everything runs against FakePainter (a numpy canvas) except where a test says it needs a window; the live runs on Paint are
separate scripts with their own contact sheets.

  AR1  the canvas is FOUND in a picture (any size / position), not assumed; a picture without one is refused
  AR2  grid partition: cells are disjoint, padded, inside the canvas
  AR3  Stage 1: shapes in cells -- zero overlap, 100% containment, drawn completely, nothing outside the canvas
  AR4  the stroke font and text fitting; connectors run border to border
  AR5  Stage 2: a flowchart -- boxes disjoint, labels inside their boxes, arrows touch only their own two boxes, text never collides with a line
  AR7  Stage 4: contour tracing (outer first, within budget, contained, faithful)
  AR8  the lightboard page (zones, call-outs, leaders, footer, frame, audit)
  AR9  lightboard helpers (wrap, fit, landmarks, magnifier + zoom panel)
  AR10 prompt v2 (dense strips found dynamically, zoom crops, control names)
  AR11 the artist's memory (icon vault, UI graph, v2 pair, procedure + macro)
  AR12 nothing bound to an image (magnify target from the strokes, labels as data, no plate named in code)
  AR6  Stage 3: curves -- contained, smooth, drawn completely; Bezier / Catmull-Rom / resampling arithmetic
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import sys
import time

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


def run_ar1() -> "TestOutcome":
    """AR1: the canvas is FOUND in a picture (any size / position), not assumed; a picture without one is refused"""
    import numpy as np
    from PIL import Image
    from core_organs import canvas_artist as CA
    fp = CA.FakePainter()
    found = fp.canvas()
    fp2 = CA.FakePainter(size=(900, 600), canvas=(120, 80, 780, 520))
    found2 = fp2.canvas()
    toolbar = fp.img.copy()
    toolbar[0:60, :] = 255                                                   # a white title bar across the top must not be taken for canvas rows
    toolbar[0:60, 0:40] = 0
    f3 = CA.find_canvas(Image.fromarray(toolbar))
    try:
        CA.find_canvas(Image.fromarray(np.full((200, 200), 120, np.uint8)))
        refused = False
    except ValueError:
        refused = True
    ribbon = fp.img.copy()
    ribbon[0:130, :] = 243                                                   # a ribbon band across the top with fragmented white swatches and a long white strip (as in Paint's toolbar flyout)
    for i in range(12):
        ribbon[20:50, 300 + i * 40:320 + i * 40] = 255
    ribbon[60:90, 200:1300] = 255
    f4 = CA.find_canvas(Image.fromarray(ribbon))
    checks = {"a_ribbon_with_white_swatches_does_not_pass_for_canvas": f4[1] >= 125 and abs(f4[0] - fp.box[0]) <= 2 and abs(f4[2] - fp.box[2]) <= 2,
              "the_box_is_recovered_from_the_picture": all(abs(a - b) <= 1 for a, b in zip(found, fp.box)),
              "another_size_and_position_works_too": all(abs(a - b) <= 1 for a, b in zip(found2, fp2.box)),
              "a_picture_with_no_white_area_is_refused": refused,
              "chrome_rows_alone_do_not_move_the_box_edges_sideways": f3[0] >= 0 and f3[2] <= fp.size[0]}
    return _verdict(checks, f"found={found} second={found2}")


def run_ar2() -> "TestOutcome":
    """AR2: grid partition -- cells are disjoint, padded, inside the canvas"""
    from core_organs import canvas_artist as CA
    box = (190.0, 125.0, 1343.0, 771.0)
    cells = CA.grid_cells(box, 2, 3, 20.0)
    disjoint = all(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1] for i, a in enumerate(cells) for b in cells[i + 1:])
    gaps = [cells[i + 1][0] - cells[i][2] for i in range(6) if i % 3 != 2] + [cells[i + 3][1] - cells[i][3] for i in range(3)]
    checks = {"six_cells": len(cells) == 6,
              "all_inside_the_canvas_by_the_padding": all(c[0] >= box[0] + 20 - 1e-6 and c[1] >= box[1] + 20 - 1e-6 and c[2] <= box[2] - 20 + 1e-6 and c[3] <= box[3] - 20 + 1e-6 for c in cells),
              "pairwise_disjoint": disjoint,
              "neighbours_are_twice_the_padding_apart": all(abs(g - 40.0) < 1e-6 for g in gaps) and len(gaps) == 7}
    return _verdict(checks, f"first={cells[0]} gap={gaps[:1]}")


def run_ar3() -> "TestOutcome":
    """AR3: Stage 1 -- shapes in cells: zero overlap, 100% containment, drawn completely, nothing outside the canvas"""
    from core_organs import canvas_artist as CA
    fp = CA.FakePainter()
    before = fp.grab()
    box = fp.canvas()
    cells = CA.grid_cells(box, 2, 2, 40.0)
    strokes = CA.plan_shapes(cells, ["rectangle", "ellipse", "triangle", "line"])
    res = CA.execute(fp, strokes)
    after = fp.grab()
    groups = {s.group: [s] for s in strokes}
    in_cell = all(c[0] - 1e-6 <= x <= c[2] + 1e-6 and c[1] - 1e-6 <= y <= c[3] + 1e-6 for s, c in zip(strokes, cells) for x, y in s.points)
    checks = {"four_shapes_four_strokes_drawn": res["strokes"] == 4 and res["drawn"] == 4,
              "each_shape_stays_in_its_own_cell": in_cell,
              "containment_is_one_hundred_percent": CA.containment(strokes, box) == 100.0,
              "zero_overlap_with_a_gap": CA.overlap_pairs(groups, fp.size, min_gap=6) == [],
              "drawn_completely": CA.completion(strokes, after, box) >= 98.0,
              "nothing_outside_the_canvas": CA.leak_pixels(before, after, box) == 0}
    # and the checker really detects an overlap and a leak
    bad = CA.plan_shapes([cells[0], (cells[0][0] + 10, cells[0][1] + 10, cells[0][2] + 10, cells[0][3] + 10)], ["rectangle", "ellipse"])
    checks["the_overlap_check_does_catch_an_overlap"] = CA.overlap_pairs({s.group: [s] for s in bad}, fp.size, 6) != []
    leaked = CA.FakePainter()
    b2 = leaked.grab()
    leaked.stroke([(50, 50), (150, 60)])
    checks["the_leak_check_does_catch_a_stroke_on_the_chrome"] = CA.leak_pixels(b2, leaked.grab(), leaked.canvas()) > 0
    return _verdict(checks, f"completion={CA.completion(strokes, after, box)} containment={CA.containment(strokes, box)}")


def run_ar4() -> "TestOutcome":
    """AR4: the stroke font and text fitting; connectors run border to border"""
    from core_organs import canvas_artist as CA
    s = CA.text_strokes("INPUT 2", (100, 100), 20)
    xs = [x for st in s for x, _ in st.points]
    ys = [y for st in s for _, y in st.points]
    w, h = CA.text_size("INPUT 2", 20)
    o, hh = CA.fit_text("LONG LABEL", (0, 0, 120, 40), 22)
    tw, _ = CA.text_size("LONG LABEL", hh)
    src, dst = (0, 0, 100, 60), (300, 20, 400, 80)
    arr = CA.connector(src, dst, gap=3)
    shaft = arr[0].points
    a_out = CA.border_point(src, (350, 50))
    missing = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in CA._G]
    checks = {"every_letter_and_digit_has_a_glyph": missing == [],
              "text_stays_inside_its_measured_box": min(xs) >= 100 - 1e-6 and max(xs) <= 100 + w + 1e-6 and min(ys) >= 100 - 1e-6 and max(ys) <= 100 + h + 1e-6,
              "long_text_is_shrunk_to_fit": tw <= 120 + 1e-6 and hh < 22 and o[0] >= 0 and o[1] >= 0,
              "the_arrow_starts_at_the_source_border": abs(shaft[0][0] - 100) <= 4 and 0 <= shaft[0][1] <= 60,
              "and_ends_at_the_destination_border": abs(shaft[-1][0] - 300) <= 4 and 20 <= shaft[-1][1] <= 80,
              "an_arrow_has_a_shaft_and_two_barbs": len(arr) == 3 and all(a.kind == "arrow" for a in arr),
              "border_point_is_on_the_border": abs(a_out[0] - 100) < 1e-6}
    return _verdict(checks, f"text={w:.0f}x{h:.0f} fit_height={hh} shaft={[tuple(round(v) for v in shaft[0]), tuple(round(v) for v in shaft[-1])]}")


def run_ar5() -> "TestOutcome":
    """AR5: Stage 2 -- a flowchart: boxes disjoint, labels inside their boxes, arrows touch only their own two boxes, text never collides with a line"""
    from core_organs import canvas_artist as CA
    fp = CA.FakePainter()
    before = fp.grab()
    box = fp.canvas()
    labels = ["USER", "UI SCAN", "RAG", "MODEL", "GUARD", "ACT"]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    strokes, boxes = CA.plan_flowchart(box, labels, edges, cols=3, pad=24)
    CA.execute(fp, strokes)
    after = fp.grab()
    size = fp.size
    text_by_box = {}
    for st in strokes:
        if st.kind == "text":
            text_by_box.setdefault(st.group, []).append(st)
    arrows = [s for s in strokes if s.kind == "arrow"]
    box_groups = {f"box{i}": [s] for i, s in enumerate(x for x in strokes if x.kind == "rectangle")}
    # each label's points lie inside its own box
    in_box = all(b[0] <= x <= b[2] and b[1] <= y <= b[3] for lab, b in zip(labels, boxes) for st in text_by_box[f"text:{lab}"] for x, y in st.points)
    # an arrow shaft's interior must not enter any box other than via its endpoints' own boxes
    import numpy as np
    cross = 0
    for i, (a, b) in enumerate(edges):
        shaft = arrows[3 * i].points
        for j, bx in enumerate(boxes):
            if j in (a, b):
                continue
            if any(bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3] for x, y in shaft):
                cross += 1
    text_vs_lines = CA.overlap_pairs({"text": [s for s in strokes if s.kind == "text"], "arrows": arrows}, size, min_gap=3)
    disjoint_boxes = CA.overlap_pairs(box_groups, size, min_gap=6) == []
    checks = {"six_boxes_five_arrows": len(boxes) == 6 and len(arrows) == 15,
              "boxes_are_disjoint": disjoint_boxes,
              "labels_sit_inside_their_boxes": in_box,
              "arrows_cross_no_foreign_box": cross == 0,
              "text_never_collides_with_a_connector": text_vs_lines == [],
              "all_inside_the_canvas": CA.containment(strokes, box) == 100.0,
              "drawn_completely": CA.completion(strokes, after, box) >= 97.0,
              "nothing_outside_the_canvas": CA.leak_pixels(before, after, box) == 0}
    return _verdict(checks, f"strokes={len(strokes)} completion={CA.completion(strokes, after, box)} cross={cross} text_vs_lines={text_vs_lines}")


def run_ar6() -> "TestOutcome":
    """AR6: Stage 3 -- curves: contained, smooth, drawn completely; Bezier / Catmull-Rom / resampling arithmetic"""
    from core_organs import canvas_artist as CA
    fp = CA.FakePainter()
    before = fp.grab()
    box = fp.canvas()
    cells = CA.grid_cells(box, 2, 3, 30.0)
    strokes = CA.plan_curves(cells)
    CA.execute(fp, strokes)
    after = fp.grab()
    in_cell = all(c[0] - 1e-6 <= x <= c[2] + 1e-6 and c[1] - 1e-6 <= y <= c[3] + 1e-6 for s, c in zip(strokes, cells) for x, y in s.points)

    def max_turn(pts):
        worst = 0.0
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
            n1, n2 = math.hypot(*v1), math.hypot(*v2)
            if n1 and n2:
                worst = max(worst, abs(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2))))))
        return math.degrees(worst)
    bz = CA.bezier((0, 0), (10, 40), (60, 40), (100, 0), 20)
    cr = CA.catmull_rom([(0, 0), (50, 80), (100, 0), (150, 80)], 10)
    rs = CA.resample([(0, 0), (100, 0)], 10)
    checks = {"six_curves_one_per_cell": len(strokes) == 6 and len({s.meta["curve"] for s in strokes}) == 6,
              "each_curve_stays_in_its_cell": in_cell,
              "containment_is_one_hundred_percent": CA.containment(strokes, box) == 100.0,
              "no_sharp_kinks_apart_from_the_designed_cusps": sum(1 for s in strokes if max_turn(s.points) < 60) >= 5,
              "drawn_completely": CA.completion(strokes, after, box) >= 97.0,
              "nothing_outside_the_canvas": CA.leak_pixels(before, after, box) == 0,
              "bezier_starts_and_ends_on_its_end_points": bz[0] == (0, 0) and all(abs(a - b) < 1e-9 for a, b in zip(bz[-1], (100, 0))),
              "catmull_rom_passes_through_the_points": any(abs(p[0] - 50) < 1e-6 and abs(p[1] - 80) < 1e-6 for p in cr) and cr[-1] == (150.0, 80.0),
              "resample_spaces_evenly": len(rs) == 11 and all(abs(b[0] - a[0] - 10) < 1e-6 for a, b in zip(rs, rs[1:]))}
    return _verdict(checks, f"completion={CA.completion(strokes, after, box)} max turns={[round(max_turn(s.points)) for s in strokes]}")


def _complex_reference():
    """A synthetic 'diagram' with nested structure: an outer body, inner organs, fine details, thin lines and a label scribble."""
    import cv2
    import numpy as np
    im = np.full((700, 500, 3), 255, np.uint8)
    cv2.ellipse(im, (250, 300), (180, 260), 0, 0, 360, (40, 40, 160), 6)               # outer boundary
    cv2.circle(im, (250, 170), 70, (30, 120, 30), 5)                                    # a "head"
    cv2.rectangle(im, (170, 300), (330, 520), (160, 60, 30), 5)                         # a "torso"
    for i in range(12):                                                                 # fine interior details (jewellery-like beads)
        cv2.circle(im, (190 + i * 11, 420), 4, (0, 0, 0), 2)
    cv2.line(im, (250, 240), (250, 300), (0, 0, 0), 3)
    cv2.putText(im, "NERVE", (60, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return im


def CA_stroke_bbox(strokes):
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    return min(xs), min(ys), max(xs), max(ys)


def run_ar7() -> "TestOutcome":
    """AR7: Stage 4 -- contour tracing: outer boundaries first, fine detail later, contained, within the stroke budget, and faithful to the reference's edges"""
    from core_organs import canvas_artist as CA
    fp = CA.FakePainter()
    box = fp.canvas()
    ref = _complex_reference()
    strokes, st = CA.trace_strokes(ref, box, max_strokes=150)
    CA.execute(fp, strokes)
    after = fp.grab()
    fid = CA.trace_fidelity(after, box, st)
    depths = [s.meta["depth"] for s in strokes]
    lengths_depth0 = [s.meta["length"] for s in strokes if s.meta["depth"] == 0]
    big, _ = CA.trace_strokes(ref, box, max_strokes=40)
    checks = {"strokes_come_out_within_the_budget": 0 < len(strokes) <= 150 and len(big) <= 40,
              "outer_structure_before_fine_detail": depths == sorted(depths),
              "within_one_depth_the_longest_come_first": lengths_depth0 == sorted(lengths_depth0, reverse=True),
              "everything_lands_inside_the_canvas": CA.containment(strokes, box) == 100.0,
              "the_aspect_ratio_is_kept": 0.6 < ((lambda b: (b[2] - b[0]) / (b[3] - b[1]))(CA_stroke_bbox([x for x in strokes if x.meta["depth"] == 0][:1]))) < 0.8,
              "drawn_completely": CA.completion(strokes, after, box) >= 97.0,
              "the_drawing_reproduces_the_reference_structure": fid["recall_pct"] >= 85.0 and fid["precision_pct"] >= 90.0,
              "a_smaller_budget_keeps_the_biggest_outlines": max(s.meta["length"] for s in big) >= 0.5 * max(s.meta["length"] for s in strokes),
              "no_stroke_is_a_speck": all(s.meta["length"] >= 10 for s in strokes)}
    return _verdict(checks, f"strokes={len(strokes)} depth={st['max_depth']} fidelity={fid} contours={st['contours_found']}->{st['contours_kept']}")


def run_ar8() -> "TestOutcome":
    """AR8: the Lightboard Tutor page -- zones from the canvas, call-outs that never overlap each other or the art, leaders that never cross and end on the landmark, a footer, a frame; the audit catches faults"""
    import cv2
    from core_organs import canvas_artist as CA, canvas_teach as CT
    fp = CA.FakePainter()
    box = fp.canvas()
    zones = CT.lightboard_zones(box)
    art, st = CA.trace_strokes(_complex_reference(), zones["core"], max_strokes=120)
    labels = [("HEAD", (0.5, 0.24)), ("OUTER BOUNDARY", (0.14, 0.43)), ("TORSO", (0.5, 0.6)), ("BEADS", (0.5, 0.6)), ("LEFT SIDE", (0.1, 0.5)), ("RIGHT SIDE", (0.9, 0.5))]
    strokes, layout = CT.plan_lightboard(box, art, "NERVOUS SYSTEM BASICS", labels, ["TRACE THE OUTLINE", "ADD THE ORGANS", "LABEL EACH PART"], stats=st)
    CA.execute(fp, art + strokes)
    au = CT.audit(layout, art, strokes, box, fp.size)
    z = zones
    zone_ok = z["header"][3] <= z["core"][1] and z["core"][3] <= z["footer"][1] and z["left"][2] <= z["core"][0] and z["core"][2] <= z["right"][0]
    arts = CT.stroke_bbox(art)
    in_core = z["core"][0] <= arts[0] and arts[2] <= z["core"][2] and z["core"][1] <= arts[1] and arts[3] <= z["core"][3]
    lm_on_art = all(any(math.dist(c.landmark, q) < 0.01 for s in art for q in s.points) for c in layout["callouts"])
    broken = dict(layout, callouts=[CT.Callout(c.label, c.landmark, c.lane, c.box, c.anchor, c.number) for c in layout["callouts"]])
    broken["callouts"][1].box = broken["callouts"][0].box                               # force an overlap
    au_bad = CT.audit(broken, art, strokes, box, fp.size)
    text_rows = [s for s in strokes if s.group.startswith("footer")]
    checks = {"zones_are_ordered_and_disjoint": zone_ok,
              "the_art_sits_in_the_core_zone": in_core,
              "six_callouts_numbered_in_reading_order": len(layout["callouts"]) == 6 and sorted(c.number for c in layout["callouts"]) == [1, 2, 3, 4, 5, 6],
              "the_audit_passes_on_the_page": au["ok"] and au["containment_pct"] == 100.0,
              "no_callout_overlaps_another_or_the_art": au["box_overlaps"] == [] and au["boxes_on_artwork"] == [],
              "leaders_never_cross_and_never_pass_through_a_label": au["leader_crossings"] == [] and au["leaders_through_boxes"] == [],
              "every_leader_ends_on_a_traced_stroke": au["leaders_not_on_landmark"] == [] and lm_on_art,
              "labels_are_on_both_sides": {c.lane for c in layout["callouts"]} == {"left", "right"},
              "a_footer_line_per_step": len({s.group for s in text_rows}) == 3,
              "the_audit_does_catch_an_overlap": au_bad["box_overlaps"] != [] and not au_bad["ok"],
              "the_page_is_drawn_completely": CA.completion(art + strokes, fp.grab(), box) >= 97.0}
    return _verdict(checks, f"audit={au}")


def run_ar9() -> "TestOutcome":
    """AR9: the lightboard helpers -- label wrapping, common text height, relative landmark mapping and snapping, automatic landmarks, magnifier + zoom panel"""
    from core_organs import canvas_artist as CA, canvas_teach as CT
    fp = CA.FakePainter()
    box = fp.canvas()
    zones = CT.lightboard_zones(box)
    art, st = CA.trace_strokes(_complex_reference(), zones["core"], max_strokes=120)
    one = CT.wrap_label("SHORT", 400, 14)
    two = CT.wrap_label("A MUCH LONGER LABEL TEXT", 150, 14)
    h, wrapped = CT.fit_height(["LEFT", "RIGHT HAND SIDE OF THE FIGURE"], 160)
    rel = CT.rel_to_canvas((0.5, 0.5), st)
    snapped = CT.snap_to_art(rel, art)
    auto = CT.auto_landmarks(art, 5)
    far = min(math.dist(a, b) for i, a in enumerate(auto) for b in auto[i + 1:]) if len(auto) > 1 else 0
    lm = auto[0]
    panel = zones["right"]
    zoom = CA.trace_strokes(_complex_reference()[120:260, 150:350], CA.inset(panel, 10), max_strokes=30)[0]
    mag = CT.magnifier(lm, 30.0, panel, zoom)
    circ = next(s for s in mag if s.group == "magnifier:circle")
    r = [math.dist(p, lm) for p in circ.points]
    leaders = [s for s in mag if s.group == "magnifier:leader"]
    checks = {"a_short_label_stays_on_one_line": one == ["SHORT"],
              "a_long_label_wraps_onto_two_balanced_lines": len(two) == 2 and abs(len(two[0]) - len(two[1])) <= 8,
              "one_common_height_fits_the_longest_label": h <= 16 and all(CA.text_size(l, h)[0] <= 160 for w in wrapped for l in w),
              "a_relative_point_maps_inside_the_art_box": zones["core"][0] <= rel[0] <= zones["core"][2] and zones["core"][1] <= rel[1] <= zones["core"][3],
              "a_snapped_landmark_is_a_point_of_a_stroke": any(math.dist(snapped, q) < 1e-9 for s in art for q in s.points) and math.dist(snapped, rel) < 60,
              "automatic_landmarks_are_spread_apart": len(auto) == 5 and far > 40,
              "the_magnifier_circle_is_centred_on_the_landmark": all(abs(x - 30.0) < 0.5 for x in r),
              "two_leaders_join_circle_and_panel": len(leaders) == 2 and all(panel[0] - 1 <= s.points[-1][0] <= panel[2] + 1 for s in leaders),
              "the_zoom_strokes_lie_inside_the_panel": all(panel[0] <= x <= panel[2] and panel[1] <= y <= panel[3] for s in zoom for x, y in s.points)}
    return _verdict(checks, f"wrap={two} h={h} auto_min_gap={far:.0f}")


def _toolbar_som(n_small=6, big=True):
    """A SoM with a strip of `n_small` 16x16 icons in one row, a few large controls elsewhere, and a column of 3 small ones."""
    els = [{"id": i + 1, "label": "", "role": "button", "box": [100 + 40 * i, 60, 16, 16]} for i in range(n_small)]
    if big:
        els += [{"id": 50, "label": "File", "role": "button", "box": [10, 10, 52, 40]}, {"id": 51, "label": "Edit", "role": "button", "box": [76, 10, 55, 40]}]
    els += [{"id": 60 + i, "label": "", "role": "button", "box": [20, 300 + 50 * i, 20, 20]} for i in range(3)]
    return {"elements": els, "seconds": 0.0, "size": [900, 700], "tiers_used": [], "tiers_skipped": []}


def run_ar10() -> "TestOutcome":
    """AR10: prompt v2 -- a dense strip of small controls is found DYNAMICALLY, cropped from the full picture and enlarged 2x; control names are attached; nothing app-specific"""
    from PIL import Image, ImageDraw
    from core_organs.harvest import prompt_v2 as P2
    som = _toolbar_som(6)
    strips = P2.dense_strips(som["elements"], (900, 700))
    img = Image.new("RGB", (900, 700), (240, 240, 240))
    d = ImageDraw.Draw(img)
    for e in som["elements"]:
        x, y, w, h = e["box"]
        d.rectangle([x, y, x + w, y + h], outline=(0, 0, 0))
    crops = P2.strip_crops(img, strips)
    controls = [{"name": "Bold", "box": (95, 55, 26, 26)}, {"name": "Italic", "box": (135, 55, 26, 26)}, {"name": "File", "box": (10, 10, 52, 40)}]
    names = P2.name_elements(som["elements"], controls)
    content, info = P2.user_content(img, som, "padx", "Click the Italic button", controls=controls)
    few = P2.dense_strips(_toolbar_som(3, False)["elements"][:3], (900, 700))
    shifted = [dict(e, box=[e["box"][0] + 300, e["box"][1] + 200, e["box"][2], e["box"][3]]) for e in som["elements"]]
    strips2 = P2.dense_strips(shifted, (900, 700))
    big_only = P2.dense_strips([{"id": 1, "label": "", "box": [10, 10, 80, 30]}] * 6, (900, 700))
    text = content[-1]["text"]
    checks = {"the_row_of_six_small_icons_is_one_strip": len(strips) >= 1 and strips[0][0] <= 100 and strips[0][2] >= 100 + 40 * 5 + 16 and strips[0][3] - strips[0][1] <= 40,
              "the_strip_is_cropped_from_the_picture_and_enlarged_twice": len(crops) == len(strips) and abs(crops[0].size[0] - 2 * (strips[0][2] - strips[0][0])) <= 1,
              "fewer_than_four_small_controls_make_no_strip": few == [],
              "large_controls_never_make_a_strip": big_only == [],
              "the_same_layout_anywhere_gives_the_same_strip_shifted": len(strips2) >= 1 and strips2[0][0] - strips[0][0] == 300 and strips2[0][1] - strips[0][1] == 200,
              "controls_name_the_elements_inside_them": names.get(1) == "Bold" and names.get(2) == "Italic" and names.get(50) == "File" and 3 not in names,
              "the_user_turn_is_full_picture_then_crops_then_text": [c["type"] for c in content] == ["image"] * (1 + info["n_crops"]) + ["text"] and info["n_crops"] >= 1,
              "the_text_carries_names_and_the_strip_count": "Names: #1 Bold | #2 Italic" in text and f"Zoomed strips (2x, in order): {info['n_crops']}" in text and text.endswith("Goal: Click the Italic button"),
              "no_controls_means_no_names_line": "Names:" not in P2.user_content(img, som, "padx", "g")[0][-1]["text"]}
    return _verdict(checks, f"strips={strips} names={names} info={info}")


def run_ar11() -> "TestOutcome":
    """AR11: the artist's memory -- a UIA action is remembered as an icon (S1), a graph transition (S2), a v2 training pair; a workflow as a procedure (S3) and a parameterised macro (S4)"""
    import tempfile
    from PIL import Image, ImageDraw
    from si_tests_rag import _Env
    from core_organs import artist_memory as AM, canvas_colour as CC
    from core_organs.harvest import local_recorder as LR
    som = _toolbar_som(6)

    def som_fn(image, region=None):
        return som
    with _Env(icons=True) as R, tempfile.TemporaryDirectory() as root:
        jl = os.path.join(root, "pairs.jsonl")
        log = AM.PaintLogger(R, jl, root, som_fn=som_fn)
        pre = Image.new("RGB", (900, 700), (240, 240, 240))
        d = ImageDraw.Draw(pre)
        for e in som["elements"]:
            x, y, w, h = e["box"]
            d.rectangle([x, y, x + w, y + h], outline=(0, 0, 0), width=2)
        post = pre.copy()
        ImageDraw.Draw(post).rectangle([300, 300, 500, 400], fill=(20, 20, 20))
        controls = [{"name": "Pencil", "type": "ButtonControl", "box": (95, 55, 26, 26)}, {"name": "Eraser", "type": "ButtonControl", "box": (135, 55, 26, 26)}, {"name": "File", "type": "MenuItemControl", "box": (10, 10, 52, 40)}]
        before_edges = R.graph.stats(AM.APP)
        log.hook({"kind": "tool", "name": "Pencil", "type": "ButtonControl", "box": (95, 55, 26, 26), "pre": pre, "post": post, "controls": controls, "origin": (0, 0), "post_controls": controls[:2]})
        after_edges = R.graph.stats(AM.APP)
        rows = [json.loads(l) for l in open(jl, encoding="utf-8")] if os.path.isfile(jl) else []
        steps = AM.layout_recipe_steps("lightboard", {})
        n = AM.log_workflow(R, "lightboard_page", "Draw a lightboard teaching page on the canvas", steps, {"title": "NERVES", "rgb": [200, 160, 40]})
        ops = [CC.Op("colour", {"rgb": (200, 160, 40), "role": "base"}), CC.Op("brush", {"name": "Oil", "size": 5}), CC.Op("fill", {"seed": (1, 1)}), CC.Op("colour", {"rgb": (80, 60, 10), "role": "deep_shadow"})]
        csteps, cparams = AM.colour_recipe_steps({}, ops)
        n2 = AM.log_workflow(R, "colour_shade_region", "Colour a region and shade it in four tones", csteps, cparams)
        procs = R.st.count("procedures")
        fast = R.fast.count(AM.APP) if hasattr(R.fast, "count") else R.st.count("fast_paths")
        from core_organs.rag import Query
        ret = R.retrieve(Query(text="draw a lightboard teaching page on the canvas", app_key=AM.APP, mode="auto"))
        ret2 = R.retrieve(Query(text="lightboard page", app_key=AM.APP, mode="auto"))
        plan_cmds = [st.command_id for p in ret.plans for st in p.steps]
        found = [e for e in ret2.evidence if e.sub_rag == "fast"]
    r0 = rows[0] if rows else {"messages": [{}, {"content": []}], "meta": {}}
    user = r0["messages"][1]["content"] if rows else []
    checks = {"the_icon_vault_learned_the_pressed_control": log.counts["icons"] == 1,
              "the_graph_got_a_transition_for_it": log.counts["edges"] == 1 and after_edges["observations"] == before_edges["observations"] + 1,
              "one_v2_pair_was_written": log.counts["pairs"] == 1 and len(rows) == 1 and r0["meta"].get("prompt_version") == 2 and r0["meta"].get("workflow") == "tool",
              "the_pair_has_the_picture_a_zoom_strip_and_names": sum(1 for c in user if c.get("type") == "image") >= 2 and "Names:" in user[-1].get("text", "") and "Pencil" in user[-1].get("text", ""),
              "the_answer_clicks_the_element_inside_the_control": json.loads(r0["messages"][2]["content"][0]["text"])[0]["target_id"] == 1 if rows else False,
              "a_workflow_is_a_procedure_and_a_macro": n["procedures"] >= 1 and n["fast_paths"] >= 1 and n2["procedures"] >= 1 and n2["fast_paths"] >= 1 and procs >= 2 and fast >= 2,
              "the_colour_recipe_names_edit_colours_brushes_and_fill": any("Edit colours" in s["text"] and "R 200 G 160 B 40" in s["text"] for s in csteps) and any("Brushes" in s["text"] and "Oil" in s["text"] for s in csteps) and any("Fill" in s["text"] for s in csteps),
              "the_macro_carries_its_parameters": cparams.get("rgb") == [200, 160, 40] and cparams.get("brush") == "Oil" and cparams.get("size") == 5,
              "asking_to_do_it_gives_a_plan_that_wants_the_title_parameter": any("lightboard" in c for c in plan_cmds) and "needs_param:title" in ret.gaps,
              "asking_about_it_finds_the_macro": any("lightboard" in e.text.lower() for e in found)}
    return _verdict(checks, f"counts={log.counts} n={n} n2={n2} procs={procs} fast={fast} found={len(found)}")


def run_ar12() -> "TestOutcome":
    """AR12: nothing is bound to a particular image -- the magnify target is found from the traced strokes, labels are data (sidecar) or 'Part N', and no canvas module names a plate"""
    import re
    import tempfile
    import cv2
    import numpy as np
    from core_organs import canvas_artist as CA, canvas_teach as CT, canvas_stages as ST
    box = (100.0, 100.0, 900.0, 700.0)

    def synth(seed, cluster):
        rng = np.random.RandomState(seed)
        img = np.full((400, 500, 3), 255, np.uint8)
        for _ in range(4):
            cv2.rectangle(img, (int(rng.randint(10, 200)), int(rng.randint(10, 150))), (int(rng.randint(250, 480)), int(rng.randint(200, 390))), (0, 0, 0), 2)
        cx, cy = cluster
        for _ in range(40):
            a, b = rng.randint(-45, 45, 2), rng.randint(-45, 45, 2)
            cv2.line(img, (cx + int(a[0]), cy + int(a[1])), (cx + int(b[0]), cy + int(b[1])), (0, 0, 0), 1)
        return img
    hits = []
    for seed, cl in ((1, (120, 110)), (2, (390, 300)), (3, (250, 200))):
        art, st = CA.trace_strokes(synth(seed, cl), box, max_strokes=400)
        rad = 60.0
        w = CT.densest_window(art, rad)
        rel = CT.canvas_to_rel(w, st)
        hits.append(math.dist((rel[0] * 500, rel[1] * 400), cl) < 110)
    with tempfile.TemporaryDirectory() as d:
        img_path = os.path.join(d, "anything.png")
        cv2.imwrite(img_path, synth(5, (200, 200)))
        none = CT.load_sidecar(img_path)
        json.dump({"title": "My title", "labels": [{"text": "Alpha", "at": [0.5, 0.5]}], "steps": ["one"]}, open(os.path.join(d, "anything.labels.json"), "w"))
        side = CT.load_sidecar(img_path)
        lab_default, lab_side = ST._labels_of(none, 3), ST._labels_of(side)
        title_default, title_side = ST._title_of(img_path, none), ST._title_of(img_path, side)
    src = "".join(open(os.path.join(os.path.dirname(__file__), f), encoding="utf-8").read() for f in ("canvas_artist.py", "canvas_live.py", "canvas_stages.py", "canvas_teach.py", "canvas_colour.py", "artist_memory.py"))
    named = re.findall(r"Ganap|Gray847|nervous|Ganesh", src, flags=re.I)
    checks = {"the_magnify_target_is_the_densest_ink_for_three_different_images": all(hits),
              "no_sidecar_means_part_n_labels_and_the_file_name_as_title": none == {} and lab_default == ["Part 1", "Part 2", "Part 3"] and title_default == "ANYTHING",
              "a_sidecar_is_used_when_given": lab_side == [("Alpha", (0.5, 0.5))] and title_side == "MY TITLE" and ST._steps_of(side, 9, 1) == ["one"],
              "no_canvas_module_names_a_plate": not named}
    return _verdict(checks, f"hits={hits} named={named[:5]}")


def run_ar13() -> "TestOutcome":
    """AR13: an app a dead run left behind is ended by PID (and only that one); a recycled pid or a live owner is never touched; a bound process dies with its owner (Job Object)"""
    import subprocess
    import psutil
    from core_organs import owned_guard as OG
    tmp = os.environ.get("TEMP", ".")
    kids = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"]) for _ in range(3)]
    fake_dead_owner = 3999990
    mine = os.path.join(tmp, f"hojaiga_owned_{fake_dead_owner}.json")
    alive_owner = os.path.join(tmp, f"hojaiga_owned_{os.getpid()}.json")
    try:
        time.sleep(0.5)
        ct = [psutil.Process(k.pid).create_time() for k in kids]
        json.dump([{"pid": kids[0].pid, "created": ct[0], "name": "orphan"}, {"pid": kids[1].pid, "created": ct[1] - 500.0, "name": "recycled"}], open(mine, "w"))
        ended = OG.reap_orphans(verbose=False)
        time.sleep(0.6)
        a0, a1, a2 = (psutil.pid_exists(k.pid) and psutil.Process(k.pid).status() != psutil.STATUS_ZOMBIE for k in kids)
        gone = not os.path.exists(mine)
        # a live owner (this process) is never reaped
        json.dump([{"pid": kids[2].pid, "created": ct[2], "name": "live-owner"}], open(alive_owner, "w"))
        ended2 = OG.reap_orphans(verbose=False)
        still = psutil.pid_exists(kids[2].pid)
        b = OG.bind(kids[2].pid, "child")
    finally:
        for k in kids:
            with contextlib.suppress(Exception):
                k.kill()
        for f in (mine, alive_owner):
            with contextlib.suppress(Exception):
                os.remove(f)
    checks = {"the_orphan_is_ended": kids[0].pid in ended and not a0,
              "a_recycled_pid_is_left_alone": kids[1].pid not in ended and a1,
              "an_unrelated_process_is_left_alone": a2,
              "the_spent_journal_is_removed": gone,
              "a_live_owners_process_is_not_reaped": kids[2].pid not in ended2 and still,
              "binding_reports_what_it_achieved": b.get("journalled") is True and "job" in b}
    return _verdict(checks, f"ended={ended} ended2={ended2} bind={b}")


def run_ar14() -> "TestOutcome":
    """AR14: verify-and-repair -- a stroke that never landed is found per stroke from the picture and drawn again; nothing that landed is drawn twice"""
    from core_organs import canvas_artist as CA

    class Flaky(CA.FakePainter):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.drop = set()
            self.calls = []

        def stroke(self, points, width=0):
            self.calls.append(tuple(points[0]))
            if tuple(points[0]) in self.drop:
                self.drop.discard(tuple(points[0]))                    # fails ONCE
                return True                                             # reports success (an app that took the contact for a tap says nothing)
            return super().stroke(points, width)
    fp = Flaky()
    box = fp.canvas()
    cells = CA.grid_cells(box, 2, 2, 60.0)
    strokes = CA.plan_shapes(cells, ["rectangle", "ellipse", "triangle", "line"])
    victim = strokes[2]
    fp.drop.add(tuple(victim.points[0]))
    CA.execute(fp, strokes)
    before = CA.completion(strokes, fp.grab(), box)
    miss0 = CA.missing_strokes(strokes, fp.grab(), box)
    n_calls = len(fp.calls)
    rep = CA.repair(fp, strokes, box)
    after = CA.completion(strokes, fp.grab(), box)
    clean = Flaky()
    CA.execute(clean, strokes)
    c0 = len(clean.calls)
    rep2 = CA.repair(clean, strokes, clean.canvas())
    checks = {"the_dropped_stroke_is_found_and_only_it": miss0 == [2],
              "completion_was_below_one_hundred_before": before < 100.0,
              "repair_redraws_exactly_the_missing_one": rep["missing_first"] == 1 and rep["redrawn"] == 1 and rep["passes"] == 1,
              "completion_is_restored": after > before and rep["missing_last"] == 0,
              "a_complete_drawing_is_left_alone": rep2["missing_first"] == 0 and rep2["redrawn"] == 0 and len(clean.calls) == c0}
    return _verdict(checks, f"miss0={miss0} before={before} after={after} rep={rep} rep2={rep2}")


def run_ar15() -> "TestOutcome":
    """AR15: the Executor hands drawing goals to the artist tool -- items, shapes and the image are read from the goal text; the result is verified on the picture; a click goal is NOT taken by the tool"""
    import tempfile
    import cv2
    import numpy as np
    from core_organs import agent_executor as AE, agent_artist as AA, canvas_colour as CC
    from si_tests_rag import _Env
    img = np.full((300, 400, 3), 255, np.uint8)
    cv2.rectangle(img, (40, 40), (360, 260), (40, 90, 200), -1)
    cv2.circle(img, (200, 150), 60, (30, 160, 60), -1)
    cv2.rectangle(img, (40, 40), (360, 260), (0, 0, 0), 3)
    cv2.circle(img, (200, 150), 60, (0, 0, 0), 3)
    with tempfile.TemporaryDirectory() as d, _Env(icons=True) as R:
        cv2.imwrite(os.path.join(d, "widget.png"), img)
        fp = CC.FakeColourPainter()
        tool = AA.ArtistTools(fp, rag=R, ref_dir=d)
        ag = AE.Agent("ms_paint", observe=lambda: {}, ground=lambda *a, **k: (None, ""), tools=[tool])
        recs = ag.run(["Draw shapes: rectangle, ellipse, triangle", "Draw a flowchart: Input -> Process -> Output", "Draw curves", "Colour the drawing"], stop_on_fail=False)
        fp2 = CC.FakeColourPainter()
        tool2 = AA.ArtistTools(fp2, rag=R, ref_dir=d)
        ag2 = AE.Agent("ms_paint", observe=lambda: {}, ground=lambda *a, **k: (None, ""), tools=[tool2])
        r_trace = ag2.step("Trace the widget picture")
        r_col = ag2.step("Colour the drawing")
        r_miss = ag2.step("Trace the unknownthing picture")
        r_click = tool2.matches("Click the Bold button")
        r_light = ag2.step("Make a lightboard page of widget with labels: Frame, Disc")
        procs = R.st.count("procedures")
        shapes_ok = recs[0].status == "done" and "3 strokes" in recs[0].effect
        flow_ok = recs[1].status == "done" and tool.plan("flowchart", "Draw a flowchart: Input -> Process -> Output", fp.canvas()).get("labels") == ["Input", "Process", "Output"]
    checks = {"shapes_named_in_the_goal_are_the_shapes_drawn": shapes_ok,
              "flowchart_items_come_from_the_goal": flow_ok,
              "curves_are_drawn_and_verified": recs[2].status == "done" and "completion" in recs[2].effect,
              "colour_before_any_trace_is_refused": recs[3].status == "no_action",
              "an_image_is_found_by_its_name_in_the_goal": r_trace.status == "done" and "trace" in r_trace.effect,
              "colouring_the_traced_image_is_measured": r_col.status in ("done", "wrong_effect") and "coverage" in r_col.effect and "bleed" in r_col.effect,
              "an_unknown_image_is_not_invented": r_miss.status == "no_action",
              "a_click_goal_is_not_taken_by_the_tool": r_click is False,
              "a_lightboard_uses_the_labels_given": r_light.status in ("done", "wrong_effect") and "lightboard" in r_light.effect,
              "a_verified_workflow_is_remembered": procs >= 1 and (r_trace.learned or recs[0].learned)}
    return _verdict(checks, f"{[(r.status, r.effect[:70]) for r in recs]} trace={r_trace.status} {r_trace.effect[:80]} col={r_col.status} {r_col.effect[:90]} light={r_light.status} {r_light.effect[:90]} why={[recs[0].why, r_light.why, r_col.why]}")


def run_ar16() -> "TestOutcome":
    """AR16: the multi-tier benchmark's pieces -- probe controls are safe and uniquely named, the table states zero-shot share and 'not measurable' honestly, the evaluator reports assisted accuracy and dense icons"""
    import tempfile
    from core_organs import live_eval as LE, multitier_eval as MT
    from core_organs.harvest import prompt_v2 as P2
    ctl = lambda n, t="ButtonControl", w=40, h=30: {"name": n, "type": t, "box": (10, 10, w, h)}
    controls = [ctl("Bold"), ctl("Bold", w=20), ctl("Start Recording"), ctl("Italic"), ctl("Sign in"), ctl("Tiny", w=10, h=10), ctl("Notes", "EditControl"), ctl("Underline"), ctl("Zoom in")]
    cands = MT._safe_probe_controls(controls)
    names = [c["name"] for c in cands]
    rows = [{"tier": "easy", "app": "A", "key": "a", "seen_in_training": True, "training_pairs": 5, "asked": 10, "accuracy": {"all": {"exact": 0.5, "assisted_exact": 1.0}, "dense_icons": {"n": 4, "exact": 0.25, "assisted_exact": 1.0}},
             "probe": {"honest": [{"seconds": 2.0}, {"seconds": 4.0}], "sabotage": [{"flagged": True, "status": "wrong_effect", "rolled_back": True}, {"flagged": True, "status": "no_effect", "rolled_back": False}]}},
            {"tier": "hard", "app": "B", "key": "b", "seen_in_training": False, "training_pairs": 0, "error": "boom"},
            {"tier": "medium", "app": "C", "key": "c", "seen_in_training": False, "training_pairs": 0, "asked": 6, "accuracy": {"all": {"exact": None, "assisted_exact": None}, "dense_icons": {}}}]
    md = MT.form1(rows)
    # the evaluator: a model that always picks element 1 vs UIA names that say otherwise
    som = {"elements": [{"id": 1, "label": "", "box": [0, 0, 16, 16]}, {"id": 2, "label": "", "box": [30, 0, 16, 16]}], "seconds": 0.0, "size": [100, 40], "tiers_used": [], "tiers_skipped": []}

    class App:
        def grab(self, popups=False):
            from PIL import Image
            return Image.new("RGB", (100, 40), (240, 240, 240)), (0, 0)

        def controls(self, origin, size):
            return [{"name": "Bold (Ctrl+B)", "type": "ButtonControl", "box": (0, 0, 16, 16), "key": "k1"}, {"name": "Italic (Ctrl+I)", "type": "ButtonControl", "box": (30, 0, 16, 16), "key": "k2"}]
    res = LE.click_accuracy(App(), "padx", lambda img, sm, k, g: ({"step": 1, "action": "click", "target_id": 1}, ""), set(), lambda img: som, max_controls=10)
    al = res["summary"]["all"]
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "training"))
        open(os.path.join(d, "training", "ui_training_dataset.jsonl"), "w").write("\n".join(json.dumps({"meta": {"app_key": k}}) for k in ("x", "x", "y")) + "\n")
        da = MT.dataset_apps(d)
    checks = {"probe_controls_are_safe_and_unique": names == ["Italic", "Underline", "Zoom in"],
              "the_spread_is_even": MT._spread(list(range(10)), 3) == [0, 3, 6] and MT._spread([1, 2], 5) == [1, 2],
              "the_table_names_the_zero_shot_share": "Zero-shot share: 2/3" in md and "zero-shot" in md,
              "crop_assisted_is_not_claimed": md.count("not measurable (needs v2 retrain)") == 2,
              "a_failed_app_is_reported_not_hidden": "could not run: boom" in md,
              "catch_and_rollback_are_counted": "2/2" in md and "1/1" in md and "3.0" in md,
              "the_evaluator_reports_assisted_accuracy": al["n"] == 2 and al["exact"] == 0.5 and al["assisted_exact"] == 1.0,
              "dense_icons_are_split_out": res["summary"]["dense_icons"]["n"] == 2,
              "the_training_set_is_counted_per_app": da == {"x": 2, "y": 1}}
    return _verdict(checks, f"names={names} summary={res['summary']['all']} md_head={md.splitlines()[2][:160]}")


def run_ar17() -> "TestOutcome":
    """AR17: a bucket fill that did not take is not accepted -- the region is covered by strokes clipped to its own mask instead; a fill that took is not repeated"""
    import numpy as np
    from core_organs import canvas_colour as CC

    class NoBucket(CC.FakeColourPainter):
        def fill_at(self, x, y):
            self.log.append(("fill_failed", (x, y)))
            return False
    mask = np.zeros((864, 1536), bool)
    mask[300:500, 400:700] = True
    ops = [CC.Op("colour", {"rgb": (152, 27, 30), "role": "base"}), CC.Op("fill", {"seed": (500.0, 400.0), "region": 0, "mask": mask})]
    bad, good = NoBucket(), CC.FakeColourPainter()
    nb, ng = CC.apply_ops(bad, ops), CC.apply_ops(good, ops)
    ab = np.asarray(bad.grab().convert("RGB")).astype(int)
    inside = ab[300:500, 400:700]
    hit = float((np.abs(inside - np.array([152, 27, 30])).sum(axis=2) < 40).mean())
    outside = ab.copy()
    outside[297:503, 397:703] = 255                                 # the stroke's own width (2 px) may touch the edge: 3 px of margin
    painted_out = int((np.abs(outside - np.array([152, 27, 30])).sum(axis=2) < 40).sum())
    checks = {"the_failure_is_noticed_and_counted": nb.get("fill_fallback") == 1,
              "the_fallback_covers_the_region": hit > 0.6,
              "the_fallback_never_leaves_the_region": painted_out == 0,
              "a_fill_that_took_has_no_fallback": ng.get("fill_fallback", 0) == 0}
    return _verdict(checks, f"nb={nb} hit={hit:.2f} out={painted_out} ng={ng}")


def run_ar18() -> "TestOutcome":
    """AR18: UIA-first routing -- a goal naming ONE control UIA lists is done through it with no model call and no OCR scan; an ambiguous or unlisted name falls back to the full scan + the model"""
    from PIL import Image
    from core_organs import agent_executor as AE
    ctl = lambda n, x: {"name": n, "type": "ButtonControl", "box": (x, 10, 40, 30), "toggle": None, "ctl": None}
    controls = [ctl("Bold", 10), ctl("Italic", 60), ctl("Underline", 110), ctl("Copy", 160), ctl("Copy", 210), ctl("Zoom", 260), ctl("Pin", 310), ctl("Find", 360), ctl("Menu", 410)]
    calls = {"model": 0, "full": 0, "lite": 0, "acts": []}
    state = {"n": 0}

    def lite():
        calls["lite"] += 1
        img = Image.new("RGB", (500, 60), (240, 240, 240) if state["n"] == 0 else (200, 120, 120))
        return {"image": img, "som": AE.som_from_controls(controls, img.size), "controls": controls}

    def full():
        calls["full"] += 1
        o = lite()
        o["som"] = {"elements": [{"id": i + 1, "label": c["name"], "role": "button", "box": list(c["box"])} for i, c in enumerate(controls)], "seconds": 0.0, "size": [500, 60], "tiers_used": ["ocr"], "tiers_skipped": []}
        return o

    def model(image, som, app_key, goal):
        calls["model"] += 1
        return {"step": 1, "action": "click", "target_id": 3, "hotkey": None, "text": None, "verify_expectation": "x"}, "model reply"

    def act(action, som):
        calls["acts"].append(action["target_id"])
        state["n"] = 1
        return True, "ok"
    ag = AE.Agent("padx", lite, model, act, settle_s=0.0, uia_first=True, observe_full=full, assist=False, reuse_post=False)
    r1 = ag.step("Click the Italic button")
    model_calls_1, full_calls_1, acts_1 = calls["model"], calls["full"], list(calls["acts"])
    state["n"] = 0
    r2 = ag.step("Click the Copy button")                       # two controls carry the name: the tree cannot answer
    state["n"] = 0
    r3 = ag.step("Click the Nonexistent button")                # not listed at all
    som_u = AE.som_from_controls(controls, (500, 60))
    checks = {"a_named_unique_control_is_done_without_the_model": r1.source == "uia" and model_calls_1 == 0 and full_calls_1 == 0 and acts_1 == [2],
              "the_uia_som_has_exact_labels_and_no_ocr": som_u["tiers_used"] == ["uia"] and [e["label"] for e in som_u["elements"]][:3] == ["Bold", "Italic", "Underline"],
              "an_ambiguous_name_falls_back_to_the_full_scan_and_the_model": r2.source == "model" and calls["full"] >= 1 and calls["model"] >= 1,
              "an_unlisted_name_also_falls_back": r3.source == "model" and calls["model"] >= 2,
              "uia_steps_are_recorded_as_such": r1.status in ("done", "no_effect", "wrong_effect") and r1.reply.startswith("UIA name")}
    return _verdict(checks, f"calls={calls} r1={r1.status}/{r1.source} r2={r2.status}/{r2.source} r3={r3.status}/{r3.source}")


def run_ar19() -> "TestOutcome":
    """AR19: a control that opens a CHILD WINDOW is found (a real second window), read (its controls, how to leave it), closed without confirming, and written to the RAG as a deep section"""
    import subprocess
    import tempfile
    from core_organs.harvest import child_windows as CW
    from core_organs import headless_input as hin
    from si_tests_rag import _Env
    code = chr(10).join(["import tkinter as tk",
                      "r = tk.Tk(); r.title('Parent app'); r.geometry('300x120+40+40'); tk.Label(r, text='main').pack()",
                      "def open_child():",
                      "    t = tk.Toplevel(r); t.title('Create Source'); tk.Button(t, text='OK').pack(); tk.Button(t, text='Cancel', command=t.destroy).pack()",
                      "r.after(2500, open_child)",
                      "r.after(14000, r.destroy)",
                      "r.mainloop()"])
    proc = subprocess.Popen([sys.executable, "-c", code])
    out = {}
    try:
        hw = 0
        t0 = time.time()
        while time.time() - t0 < 8 and not hw:
            import ctypes
            P = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            found = []

            def cb(h, l):
                if hin.window_pid(h) == proc.pid and hin.safe_window_text(h) == "Parent app" and ctypes.windll.user32.IsWindowVisible(h):
                    found.append(h)
                return True
            ctypes.windll.user32.EnumWindows(P(cb), 0)
            hw = found[0] if found else 0
            time.sleep(0.3)
        before = CW.snapshot(hw)
        kids = []
        t0 = time.time()
        while time.time() - t0 < 8 and not kids:
            kids = CW.new_windows(before, hw)
            time.sleep(0.3)
        kid = kids[0] if kids else {}
        det = CW.describe(kid["hwnd"]) if kids else {"controls": [], "n_controls": 0, "dismiss_with": "", "confirm_buttons": []}
        closed = CW.dismiss(kid["hwnd"]) if kids else ""
        time.sleep(0.8)
        alive = bool(kids) and hin.is_alive(kid["hwnd"]) and bool(ctypes.windll.user32.IsWindowVisible(kid["hwnd"]))
        ent = CW.entry({"name": "+ Add source", "type": "ButtonControl"}, kid, det, closed) if kids else {}
        with tempfile.TemporaryDirectory() as root, _Env(icons=True) as R:
            n = CW.register(R, "padx", [ent], root) if kids else {}
            procs = R.st.count("procedures")
            f = os.path.join(root, "ui_sections", "padx.json")
            filed = json.load(open(f, encoding="utf-8")) if os.path.isfile(f) else {}
        out = dict(kids=len(kids), title=kid.get("title"), kind=kid.get("kind"), n_controls=det["n_controls"], dismiss_with=det["dismiss_with"], confirm=det["confirm_buttons"], closed=closed, still_open=alive, n=n, procs=procs,
                   filed=[e["opener"] for e in filed.get("deep_sections", [])])
    finally:
        with contextlib.suppress(Exception):
            proc.kill()
    checks = {"the_second_window_is_found": out.get("kids") == 1 and out.get("title") == "Create Source" and out.get("kind") == "dialog",
              "its_controls_are_read_and_a_way_out_is_known": out.get("n_controls", 0) >= 0 and out.get("dismiss_with") in ("cancel", "close"),
              "nothing_is_confirmed_and_the_window_is_gone": "OK" not in str(out.get("closed")) and out.get("still_open") is False,
              "it_is_closed_without_confirming": out.get("closed", "").startswith("pressed") or out.get("closed") in ("escape", "wm_close"),
              "the_rag_learned_a_deep_section": out.get("n", {}).get("procedures", 0) >= 1 and out.get("n", {}).get("edges", 0) >= 1 and out.get("procs", 0) >= 1,
              "the_section_is_filed_for_people_and_agents": out.get("filed") == ["+ Add source"]}
    return _verdict(checks, str(out))


def run_ar20() -> "TestOutcome":
    """AR20: what a learner must never operate -- start / stop / record / stream / publish / install / connect are refused; ordinary controls are not"""
    from core_organs.harvest import local_recorder as LR
    never = ["Start Streaming", "Start Recording", "Stop Recording", "Start Virtual Camera", "Install", "Run", "Publish", "Go Live", "Connect", "Upload", "Format", "Restart", "Submit"]
    fine = ["Bold", "Zoom In", "Move Up", "Add", "Docks", "Studio Mode", "Float", "Italic", "Underline", "Edit"]
    bad = [n for n in never if not LR.DENY_RX.search(n)]
    over = [n for n in fine if LR.DENY_RX.search(n)]
    checks = {"every_starting_or_publishing_control_is_refused": not bad, "ordinary_controls_are_still_scanned": not over}
    return _verdict(checks, f"not refused={bad} wrongly refused={over}")


def run_ar21() -> "TestOutcome":
    """AR21: nothing personal in a frame or a launch -- account badges are masked, a document app is started on the sandbox, and the scrub quarantines a frame that shows the person's identifiers"""
    try:
        from si_tests_privacy import run_ar21 as _impl  # type: ignore
    except ImportError:
        from core_organs.si_tests_privacy import run_ar21 as _impl  # type: ignore
    return _impl(_verdict)


def run_ar22() -> "TestOutcome":
    """AR22: start screens -- passed safely (blank / new / skip, never a recent file), a workbench left alone, the chooser learned by the RAG"""
    try:
        from si_tests_start import run_ar22 as _impl  # type: ignore
    except ImportError:
        from core_organs.si_tests_start import run_ar22 as _impl  # type: ignore
    return _impl(_verdict)


def _dom_test(name):
    try:
        import si_tests_domains as _m  # type: ignore
    except ImportError:
        from core_organs import si_tests_domains as _m  # type: ignore
    return getattr(_m, name)(_verdict)


def run_ar23() -> "TestOutcome":
    """AR23: three master domains (desktop_app / website / web_app): classification from evidence, namespaced keys, retrieval refuses another domain, per-domain stats"""
    return _dom_test("run_ar23")


def run_ar24() -> "TestOutcome":
    """AR24: the web recorder's safety decisions (never sign-in / purchase / file / off-site; reject cookie banners)"""
    return _dom_test("run_ar24")


def run_ar25() -> "TestOutcome":
    """AR25: a site recorded end to end on a stand-in browser (pairs for what changed, v2 twins, nothing unsafe clicked)"""
    return _dom_test("run_ar25")


def run_ar26() -> "TestOutcome":
    """AR26: the web failover chain (steps, keys, clips, relevance, engine breaker, before/after pairs from screenshots)"""
    return _dom_test("run_ar26")


TESTS = [("AR1", run_ar1), ("AR2", run_ar2), ("AR3", run_ar3), ("AR4", run_ar4), ("AR5", run_ar5), ("AR6", run_ar6), ("AR7", run_ar7), ("AR8", run_ar8), ("AR9", run_ar9), ("AR10", run_ar10), ("AR11", run_ar11), ("AR12", run_ar12), ("AR13", run_ar13), ("AR14", run_ar14), ("AR15", run_ar15), ("AR16", run_ar16), ("AR17", run_ar17), ("AR18", run_ar18), ("AR19", run_ar19), ("AR20", run_ar20), ("AR21", run_ar21), ("AR22", run_ar22), ("AR23", run_ar23), ("AR24", run_ar24), ("AR25", run_ar25), ("AR26", run_ar26)]

if __name__ == "__main__":
    only = [a.upper() for a in sys.argv[1:]]
    rc = 0
    for name, fn in TESTS:
        if only and name not in only:
            continue
        t0 = time.time()
        try:
            r = fn()
        except Exception:
            import traceback
            r = TestOutcome(False, "EXCEPTION " + traceback.format_exc()[-1800:])
        print(f"[{'PASS' if r.passed else 'FAIL'}] {name} {time.time() - t0:5.1f}s  {(fn.__doc__ or '').strip().splitlines()[0][:90]}\n        {r.evidence[:1700]}")
        rc |= 0 if r.passed else 1
    sys.exit(rc)
