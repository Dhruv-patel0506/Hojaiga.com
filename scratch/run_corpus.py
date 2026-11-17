import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_corpus as GC
from core_organs.professor import history as HS

tiers = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 and sys.argv[1] != "all" else None
force = "--force" in sys.argv
t0 = time.time()
out = GC.build(tiers=tiers, force=force, history=HS.library(), log=lambda s: print(time.strftime("%H:%M:%S"), s, flush=True))
print("DONE", out["totals"], "blocked providers:", out["blocked_providers"], f"{time.time()-t0:.0f}s", flush=True)
