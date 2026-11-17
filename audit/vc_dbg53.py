import sys, os, tempfile
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import si_tests_consolidate as T
from core_organs.harvest import consolidate as C

tmp = tempfile.mkdtemp(prefix="vcd53_")
g, reps, vids = T.build_graph(tmp)
screens = {"v1": "New project\nSave Ctrl+S\nQuit Ctrl+Q\nOpen Ctrl+O", "v2": "New project\nSave Cmd+S\nQuit Cmd+Q\nOpn Ctrl+X", "v3": "New project\nSave Ctrl+S\nQuit Ctrl+Q"}
seen = []


def fake(post_path, primary, crop_px):
    for v, txt in screens.items():
        if os.sep + v + os.sep in post_path or "/" + v + "/" in post_path:
            seen.append(v)
            return txt
    seen.append("NONE:" + post_path[-40:])
    return ""


rep = C.ocr_edges(g, ocr=fake)
print("calls", rep["ocr_calls"], "seen", seen)
for e in g.edges:
    if g.support(e) >= 2:
        print("edge", e["id"], "videos", e["videos"], "obs per video", {v: sum(1 for o in e["obs"] if o["video"] == v) for v in e["videos"]}, "facts", [(f["windows"], f["videos"]) for f in (e.get("ocr") or {}).get("facts", [])])
