"""Drop throw-away test rows from the harvested corpus (videos probed with stages switched off),
keeping the real Excel harvest intact."""
import csv
import json
import random
import shutil
from pathlib import Path

ROOT = Path(r"D:\new_automation")
VIDS = {"OKA4y7WoNHU", "rUKbD1hhEEM"}
APPS = {"blender", "gimp"}

ts = ROOT / "brain" / "train_samples.jsonl"
rows = [l for l in ts.read_text(encoding="utf-8").splitlines() if l.strip()]
keep = [l for l in rows if not (any(f'"{v}"' in l for v in VIDS) and '"video_harvest"' in l)]
ts.write_text("\n".join(keep) + "\n", encoding="utf-8")
print(f"train_samples: {len(rows)} -> {len(keep)}")

ds = ROOT / "video_dataset" / "dataset.jsonl"
if ds.is_file():
    recs = [json.loads(l) for l in ds.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = [r for r in recs if r.get("video_id") not in VIDS]
    ds.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    print(f"dataset.jsonl: {len(recs)} -> {len(kept)}")

idx = ROOT / "video_dataset" / "index.csv"
if idx.is_file():
    with open(idx, encoding="utf-8", newline="") as fh:
        rd = list(csv.DictReader(fh))
        cols = list(rd[0].keys()) if rd else []
    rd = [r for r in rd if r.get("video_id") not in VIDS]
    with open(idx, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rd)
    print(f"index.csv: {len(rd)} rows left")

sp = ROOT / "video_dataset" / "split.json"
if sp.is_file():
    m = json.loads(sp.read_text(encoding="utf-8"))
    for a in APPS:
        m.get("apps", {}).pop(a, None)
    order = sorted(m.get("apps", {}))
    random.Random(m.get("seed", 7)).shuffle(order)
    n = int(round(len(order) * m.get("train_ratio", 0.7)))
    for i, k in enumerate(order):
        m["apps"][k]["split"] = "TRAIN" if i < n else "EVAL"
    m["counts"] = {"TRAIN": n, "EVAL": len(order) - n}
    sp.write_text(json.dumps(m, ensure_ascii=False, indent=3), encoding="utf-8")
    print(f"split.json: {n} TRAIN / {len(order) - n} EVAL")

for v in VIDS:
    shutil.rmtree(ROOT / "video_dataset" / v, ignore_errors=True)
    (ROOT / "video_dataset" / "corpus" / f"{v}.jsonl").unlink(missing_ok=True)
for a in APPS:
    for half in ("TRAIN", "EVAL"):
        shutil.rmtree(ROOT / "trajectories" / half / a, ignore_errors=True)
print("test artifacts removed")
