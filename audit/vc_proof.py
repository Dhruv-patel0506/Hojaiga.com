"""Proof pack for a consolidated graph: the shared edges with their frames from each video, and a random sample of single-video events, with the detected changed box drawn on the post frame."""
import sys, os, json, random, collections
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np, cv2
from core_organs.harvest import consolidate as C

app = sys.argv[1] if len(sys.argv) > 1 else "webapp:excalidraw.com"
out_dir = r"D:\new_automation\reports"
g = C.AppGraph.load(app)
TH = (320, 180)


def tile(path, box, label):
    im = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        im = np.zeros((TH[1], TH[0], 3), np.uint8)
    h, w = im.shape[:2]
    im = cv2.resize(im, TH)
    if box:
        x0, y0, x1, y1 = [int(v) for v in (box[0] * TH[0], box[1] * TH[1], box[2] * TH[0], box[3] * TH[1])]
        cv2.rectangle(im, (x0, y0), (x1, y1), (0, 0, 255), 2)
    cv2.rectangle(im, (0, 0), (TH[0], 16), (0, 0, 0), -1)
    cv2.putText(im, label[:48], (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    return im


def sheet(rows, path):
    if not rows:
        return
    W = max(len(r) for r in rows)
    canvas = np.zeros((len(rows) * TH[1], W * TH[0], 3), np.uint8)
    for i, r in enumerate(rows):
        for j, t in enumerate(r):
            canvas[i * TH[1]:(i + 1) * TH[1], j * TH[0]:(j + 1) * TH[0]] = t
    cv2.imencode(".png", canvas)[1].tofile(path)
    print("wrote", path, canvas.shape)


MINSUP = int(os.environ.get("MINSUP", "2"))
shared = sorted([e for e in g.edges if g.support(e) >= MINSUP], key=lambda e: -g.support(e))[:int(os.environ.get("MAXEDGES", "6"))]
rows = []
for e in shared:
    byv = {}
    for o in e["obs"]:
        byv.setdefault(o["video"], o)
    for v, o in list(byv.items())[:3]:
        rows.append([tile(o["pre"], None, f"edge{e['id']} {v} t={o['t']} PRE"), tile(o["post"], e["rep"]["primary"], f"edge{e['id']} {v} POST")])
sheet(rows, os.path.join(out_dir, "vc_proof_shared_edges.png"))

random.seed(3)
uniq = [e for e in g.edges if g.support(e) == 1]
sample = random.sample(uniq, min(14, len(uniq)))
rows = []
for e in sample:
    o = e["obs"][0]
    rows.append([tile(o["pre"], None, f"e{e['id']} {o['video'][:6]} t={o['t']} PRE"), tile(o["post"], e["rep"]["primary"], f"POST n_obs={len(e['obs'])}")])
sheet([r for r in rows[:7]], os.path.join(out_dir, "vc_proof_unique_sample_a.png"))
sheet([r for r in rows[7:]], os.path.join(out_dir, "vc_proof_unique_sample_b.png"))

# statistics on what the events are
ch, area, per_video = [], [], collections.Counter()
for e in g.edges:
    for o in e["obs"]:
        per_video[o["video"]] += 1
        p = e["rep"]["primary"]
        area.append((p[2] - p[0]) * (p[3] - p[1]))
print("observations per video:", dict(per_video))
a = np.array(area)
print("primary changed-box area share of frame: median %.3f, p10 %.3f, p90 %.3f; <2%%: %.0f%%, >40%%: %.0f%%" % (np.median(a), np.percentile(a, 10), np.percentile(a, 90), 100 * (a < 0.02).mean(), 100 * (a > 0.4).mean()))
mult = collections.Counter(len(e["obs"]) for e in g.edges)
print("observations per edge histogram:", dict(sorted(mult.items())))
within = sum(1 for e in g.edges if len(e["obs"]) > 1 and g.support(e) == 1)
print("single-video edges that merged >=2 events of the SAME video:", within)
