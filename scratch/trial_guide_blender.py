import sys, json, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR

t0 = time.time()
ident = GF.AppIdentity(app_key="blender", product="Blender", company="Blender Foundation", process="blender.exe")
ix = MR.ManualIndex()
rep = GF.discover(ident, ix, web=True, budget_s=150, max_pages=20, max_depth=2, delay_s=0.4, embed_small=False, max_queries=3)
print("seconds", round(time.time() - t0, 1), "web", rep["web"], "provider", GF.LAST_PROVIDER, "blocked", GF.BLOCKED_PROVIDERS)
for t in rep["tiers"]:
    print(" tier", json.dumps(t, default=str)[:600])
print("ingested", len(rep["ingested"]), "documents; coverage:", rep["coverage"])
for i in rep["ingested"][:6]:
    print("   ", i["chunks"], i["source"][:100])
print("skipped (first 6):", rep["skipped"][:6])
hits = ix.search("how do I add a cube to the scene", "blender", 3)
for h in hits:
    print("search ->", h.cite, "|", h.text[:90].replace("\n", " "))
