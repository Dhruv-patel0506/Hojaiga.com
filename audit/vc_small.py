import sys, random
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\audit")
import numpy as np, cv2
from core_organs.harvest import consolidate as C
import vc_proof as P  # reuses tile()/sheet() and the loaded graph

g = P.g
small = []
for e in g.edges:
    if len(e["obs"]) == 1:
        p = e["rep"]["primary"]
        a = (p[2] - p[0]) * (p[3] - p[1])
        if a < 0.03:
            small.append(e)
print("single-observation edges with a small changed box (<3% of frame):", len(small))
random.seed(5)
pick = random.sample(small, min(14, len(small)))
rows = [[P.tile(e["obs"][0]["pre"], None, f"e{e['id']} {e['obs'][0]['video'][:6]} t={e['obs'][0]['t']} PRE"), P.tile(e["obs"][0]["post"], e["rep"]["primary"], "POST")] for e in pick]
P.sheet(rows[:7], r"D:\new_automation\reports\vc_proof_small_a.png")
P.sheet(rows[7:], r"D:\new_automation\reports\vc_proof_small_b.png")
