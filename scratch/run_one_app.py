import sys, json, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_corpus as GC, guide_finder as GF, manual_rag as MR

key = sys.argv[1]
pages = int(sys.argv[2]) if len(sys.argv) > 2 else 60
a = GC.find_app(key)
ix = MR.ManualIndex()
# start clean for this application (a previous bad crawl must not linger)
ix.db.execute("DELETE FROM chunks WHERE doc IN (SELECT id FROM docs WHERE app=?)", (a["key"],))
ix.db.execute("DELETE FROM docs WHERE app=?", (a["key"],))
ix.db.commit()
ident = GF.AppIdentity(app_key=a["key"], product=a["name"], company=a.get("company", ""), process=(a.get("processes") or [""])[0])
t0 = time.time()
rep = GF.discover(ident, ix, web=True, budget_s=300, force=True, delay_s=0.4, max_pages=pages, max_depth=2, embed_small=False, seeds=a.get("seeds", []), max_queries=3)
print(f"{a['name']}: {GF.indexed_docs(ix, a['key'])} docs in {time.time()-t0:.0f}s; coverage: {rep['coverage']}")
for t in rep["tiers"]:
    print(" tier:", json.dumps(t, default=str)[:900])
print(" ingested:", len(rep["ingested"]), [i["source"][:80] for i in rep["ingested"][:6]])
sk = {}
for u, w in rep["skipped"]:
    sk[w[:48]] = sk.get(w[:48], 0) + 1
print(" skipped reasons:", sk)
