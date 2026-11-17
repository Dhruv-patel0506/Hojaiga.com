import sys, os, tempfile, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import si_tests_consolidate as T
from core_organs.harvest import consolidate as C, video_graph_live as L

tmp = tempfile.mkdtemp(prefix="vcd51_")
g, reps, vids = T.build_graph(tmp)
for e in g.edges:
    votes = {}
    for o in e["obs"]:
        tr = T.truth_of(o["video"], o["t"])
        if tr and tr[2] in T.CONTROL_LABEL and tr[1] != "home":
            k = T.CONTROL_LABEL[tr[2]].lower()
            votes[k] = votes.get(k, 0) + 1
    if votes:
        e["labels"] = votes
g.save()
os.environ["HOJAIGA_VIDEO_GRAPH"] = "1"
live = T.frame_of(T.render("home", "light", (600, 400)), 1100, 620, (0, 0), False)
truth = {e["id"]: sorted({str(T.truth_of(o["video"], o["t"])) for o in e["obs"]}) for e in g.edges}
for e in g.edges:
    print("edge", e["id"], truth[e["id"]], "label", repr(g.best_label(e)), "support", g.support(e), "crops", [(round(c["box"][0], 2), round(c["box"][1], 2)) for c in e["opener_crops"]], "localize", L.localize(live, e))
print("candidates:", [(g.best_label(e), box, round(s, 2)) for e, box, s in L.candidates(g, live, "open the file menu", limit=6)])
print("hint:", L.hint_text("synthetic_daw", live, "open the file menu", root=g.root))
