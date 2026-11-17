"""Undo the first promotion's duplicates (rows it INSERTED: context 'verified live <stamp>' / 'REFUTED live <stamp>'), then promote again IN PLACE. Refuses to delete unless exactly the expected 17 rows match."""
import sys, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import rag as R
from core_organs.rag import lt
from core_organs.harvest import shortcut_verify as SV

results = r"D:\new_automation\reports\shortcut_verify\20261026_000357\results.json"
rep = json.load(open(results, encoding="utf-8"))
key, stamp = rep["app_key"], rep["when"]
r = R.get_rag()
rows = lt.fetch(r.fast.st, "fast_paths", lt.where_app(key), 1000)
print("rows for", key, "before:", len(rows))
dups = [x for x in rows if str(x.get("context", "")).startswith((f"verified live {stamp}", f"REFUTED live {stamp}"))]
print("rows inserted by the first promotion:", len(dups))
assert len(dups) == 17, "unexpected number of rows: refusing to delete"
print("forgot", r.fast.forget_rows([x["fast_id"] for x in dups]), "rows; now", r.fast.count(key))
out = SV.promote(results, r)
print("promote ->", json.dumps(out))
print("rows for", key, "after:", r.fast.count(key))
final = lt.fetch(r.fast.st, "fast_paths", lt.where_app(key), 1000)
print()
print(f"{'action':<26}{'payload':<15}{'verified':<9}{'trust':<10}context")
for x in sorted(r.fast._overlay(final), key=lambda x: (x["task_pattern"], x["payload"])):
    print(f"{x['task_pattern'][:25]:<26}{x['payload']:<15}{str(x['verified']):<9}{x['trust']:<10}{(x.get('context') or '')[:70]}")
