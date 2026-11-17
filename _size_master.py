import os
os.environ["HOJAIGA_GUIDES_XLSX"] = "app_guides_master.xlsx"
os.environ["HOJAIGA_TRAJ_DIR"] = "trajectories"
os.environ["HOJAIGA_BRAIN_DIR"] = "brain"
from pathlib import Path
import decompose_guides as d

rows = d.load_rows()
mf = d.build_split(rows)
split = {k: v.get("split") for k, v in mf["apps"].items()}

gui_rows = train_pass = existing = model_calls = 0
for r in rows:
    passes = d.is_desktop_gui(r["markdown"]) and r["action_score"] >= d.ACTION_FLOOR
    if not passes:
        continue
    gui_rows += 1
    sp = split.get(r["app_key"], "TRAIN")
    if sp == "TRAIN":
        train_pass += 1
    base = d.slug_of(r["guide_title"] or Path(r["md_path"]).stem or r["app_name"])
    of = Path(d.TRAJ_DIR) / sp / r["app_key"] / f"{base}__{d.content_hash(r['markdown'])}.json"
    if of.exists():
        existing += 1
    else:
        model_calls += 1

print("total guide rows        :", len(rows))
print("distinct apps           :", len(split))
print("TRAIN apps              :", sum(1 for v in split.values() if v == "TRAIN"))
print("GUI+procedural rows     :", gui_rows)
print("  of those TRAIN split  :", train_pass)
print("already on disk (cached):", existing)
print("MODEL CALLS needed      :", model_calls)
print("~hours @ 20s/call       :", round(model_calls * 20 / 3600, 1))
