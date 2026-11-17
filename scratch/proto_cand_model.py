import sys, time
import numpy as np
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import candidates as CD, synth
from core_organs.professor.schema import Box
from core_organs.professor.ml import candidates as MC

scenes = [("light", 1.0), ("dark", 1.0), ("light", 1.5), ("dark", 1.25)]
data = []
t0 = time.time()
for theme, scale in scenes:
    img, truth, _ = synth.render_app(theme, scale)
    cs = CD.detect(img, scale, ocr=True, budget_s=30)
    ink = CD.ink_mask(np.asarray(img.convert("L")), scale)
    tb = [Box(*t["box"]) for t in truth]
    data.append((theme, scale, cs.candidates, img.size, ink, tb))
    y = MC.match_labels(cs.candidates, tb)
    print(f"{theme}@{scale}: {len(cs.candidates)} candidates, {sum(y)} match a truth control ({sum(y)/max(1,len(y)):.2f})  [{time.time()-t0:.0f}s]")

m = MC.CandidateModel(None)
for ep in range(6):
    for theme, scale, cands, size, ink, tb in data[:3]:
        m.observe_scan(cands, size, ink, tb, epochs=2)
held = data[3]
print("held-out", held[0], held[1], m.evaluate(held[2], held[3], held[4], held[5], 0.5))
for thr in (0.2, 0.3, 0.4):
    print(" thr", thr, m.evaluate(held[2], held[3], held[4], held[5], thr))
# untrained baseline
m0 = MC.CandidateModel(None)
print("untrained", m0.evaluate(held[2], held[3], held[4], held[5], 0.5))
print("metrics", m.metrics())
