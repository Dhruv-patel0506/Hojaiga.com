"""Measure (or with --write, clean) the foreign controls stored in the saved catalogs."""
import json
import os
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor import harvest as HV

WRITE = "--write" in sys.argv
DR = r"d:\new_automation\data\professor\catalogs"
rows = []
for fn in sorted(os.listdir(DR)):
    if not fn.endswith(".json"):
        continue
    raw = json.load(open(os.path.join(DR, fn), encoding="utf-8"))
    cat = HV.Catalog.from_dict(raw)                              # from_dict: the file exactly as saved, no load-time scrub
    titles = HV.foreign_titles(cat.process)
    if not titles:
        continue
    gone = HV.drop_foreign_verbs(cat, titles)
    if not gone:
        continue
    rows.append((cat.app_key, cat.process, gone, len(raw.get("verbs") or []), len(cat.verbs), sorted(titles)[:2]))
    if WRITE:
        cat.save(os.path.join(DR, fn))

print(f"{len(rows)} catalog(s) stored controls of another application's window")
for r in sorted(rows, key=lambda x: -x[2]):
    print(f"  {r[0]:<22} {str(r[1]):<18} dropped={r[2]:<5} was={r[3]:<6} now={r[4]:<6} foreign titles: {str(r[5])[:64]}")
print("dry run" if not WRITE else "files rewritten")
