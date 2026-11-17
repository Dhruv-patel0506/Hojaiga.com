"""Promote the VERIFIED shortcuts of one verification run in the RAG and show the rows before and after (read through the store's own API)."""
import sys, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import rag as R
from core_organs.harvest import shortcut_verify as SV

results = sys.argv[1]
rep = json.load(open(results, encoding="utf-8"))
key = rep["app_key"]
r = R.get_rag()
goals = sorted({x["action"] for x in rep["results"]} | {"Bring to front"})


def snapshot():
    rows = {}
    for g in goals:
        for e in r.fast.by_goal(key, g, limit=8):
            pl = e.payload or {}
            rows[pl.get("fast_id") or (g, pl.get("payload"))] = (e.text, pl.get("payload"), pl.get("verified"), e.trust, getattr(e, "citation", ""))
    return rows


before = snapshot()
print("fast rows for", key, ": count", r.fast.count(key), "| visible via goals:", len(before))
out = SV.promote(results, r)
print("promote ->", json.dumps(out))
after = snapshot()
print("fast rows for", key, ": count", r.fast.count(key), "| visible via goals:", len(after))
print()
print(f"{'action':<26}{'payload':<16}{'verified':<10}{'trust':<7}")
for fid, (text, payload, ver, trust, cit) in sorted(after.items(), key=lambda kv: (kv[1][0], kv[1][1])):
    mark = "" if fid in before and before[fid][2] == ver else "   <- changed" if fid in before else "   <- new"
    print(f"{str(text)[:25]:<26}{str(payload):<16}{str(ver):<10}{str(trust):<7}{mark}")
print()
for g in ("zen mode", "bring to front", "bring forward", "copy", "flip horizontal"):
    ev = r.fast.by_goal(key, g, limit=3)
    print(g, "->", [(e.payload.get("payload"), e.payload.get("verified"), (e.payload.get("context") or "")[:60]) for e in ev[:3]])
