"""Per changed blob: same-object similarity (pre vs post edge pattern) with the truth of what the blob is."""
import sys, os, tempfile
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np
from core_organs import si_tests_consolidate as T
from core_organs.harvest import consolidate as C, video_pipeline as VP

tmp = tempfile.mkdtemp(prefix="vcc_")
vids = T.make_videos(tmp)
for vid, path in vids.items():
    kfs = VP.extract_keyframes(path, os.path.join(tmp, "k_" + vid), video_id=vid, sample_fps=2.0, diff_thresh=12)
    for ev in kfs:
        g_pre, g_post = C._to_gray(ev["pre"]), C._to_gray(ev["post"])
        box = C.crop_box(g_pre)
        a, b = C._canvas(g_pre, box, C.LOC_NORM), C._canvas(g_post, box, C.LOC_NORM)
        dc = C.delta_components(C._canvas(g_pre, box), C._canvas(g_post, box))
        tr = T.truth_of(vid, ev["t"])
        big = dc["comps"][0]["area"] if dc["comps"] else 0
        row = []
        for c in dc["comps"]:
            bx = c["box"]
            sim = C.cos(C.crop_signature(a, bx), C.crop_signature(b, bx))
            row.append((round(c["area"] / big, 2), [round(x, 2) for x in bx], round(sim, 2)))
        print(vid, "t=%.1f" % ev["t"], tr, row)
