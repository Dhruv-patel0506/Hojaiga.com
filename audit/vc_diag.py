"""Diagnostic for the consolidation thresholds: similarity of observations that are the SAME true transition (different videos) vs DIFFERENT true transitions."""
import sys, os, tempfile, itertools, collections
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np
from core_organs import si_tests_consolidate as T
from core_organs.harvest import consolidate as C
from core_organs.harvest import video_pipeline as VP

tmp = tempfile.mkdtemp(prefix="vcd_")
vids = T.make_videos(tmp)
plans = {"v1": T.V1, "v2": T.V2, "v3": T.V3}
obs_all = []
for vid, path in vids.items():
    kdir = os.path.join(tmp, "k_" + vid)
    kfs = VP.extract_keyframes(path, kdir, video_id=vid, sample_fps=2.0, diff_thresh=12)
    obs, rej = C.observations_from_keyframes(kfs, vid, os.path.join(tmp, "crops"))
    # ground truth boundaries
    off = 2.0 if T.STYLE[vid]["card"] else 0.0
    t = off
    bounds = []
    prev = None
    for state, secs, via in plans[vid]:
        if prev is not None:
            bounds.append((t, f"{prev}->{state}"))
        t += secs
        prev = state
    print(vid, "events", len(kfs), "kept", len(obs), "rejected", rej, "bounds", [(round(b, 1), n) for b, n in bounds])
    for o in obs:
        nb = min(bounds, key=lambda b: abs(b[0] - o["t"])) if bounds else (0, "?")
        o["truth"] = nb[1] if abs(nb[0] - o["t"]) < 1.6 else "spurious"
        print("   t=%.1f truth=%s union=%s ncomp=%d changed=%.3f" % (o["t"], o["truth"], [round(x, 2) for x in o["union"]], len(o["comps"]), o["changed"]))
        obs_all.append(o)

same, diff = [], []
for a, b in itertools.combinations(obs_all, 2):
    if a["video"] == b["video"]:
        continue
    sim = C.obs_similarity(a, b)
    rec = (round(sim, 3), round(C.box_iou(a["primary"], b["primary"]), 2), round(C.cos(a["delta_sig"], b["delta_sig"]), 2), a["dir"], b["dir"], a["truth"], b["truth"])
    (same if a["truth"] == b["truth"] and a["truth"] != "spurious" else diff).append(rec)
print("SAME-transition pairs (sim, iou, delta, dirA, dirB):")
for r in sorted(same, reverse=True):
    print("  ", r)
print("DIFFERENT-transition pairs, top 12 by sim:")
for r in sorted(diff, reverse=True)[:12]:
    print("  ", r)
