import sys, time
import numpy as np
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import candidates as CD, synth
from core_organs.professor.schema import Box
from core_organs.professor.ml import candidates as MC


def scene(kind, theme="light", scale=1.0):
    if kind == "app":
        img, truth, _ = synth.render_app(theme, scale)
    elif kind == "dialog":
        img, truth, _ = synth.render_dialog(theme, scale)
    else:
        img, truth, _ = synth.render_editor(scale)
    cs = CD.detect(img, scale, ocr=True, budget_s=30)
    ink = CD.ink_mask(np.asarray(img.convert("L")), scale)
    return cs.candidates, img.size, ink, [Box(*t["box"]) for t in truth if t.get("label") is not None]


t0 = time.time()
train = [scene("app", "light", 1.0), scene("app", "dark", 1.0), scene("app", "light", 1.5), scene("app", "dark", 1.25)]
tests = {"dialog": scene("dialog", "light", 1.0), "dialog-dark": scene("dialog", "dark", 1.0), "editor": scene("editor", "light", 1.0)}
print("scenes built in %.0fs" % (time.time() - t0))
# train on the application layout only; evaluate on layouts never seen
m = MC.CandidateModel(None)
for ep in range(6):
    for c, size, ink, tb in train:
        m.observe_scan(c, size, ink, tb, epochs=2)
m0 = MC.CandidateModel(None)
for name, (c, size, ink, tb) in tests.items():
    e = m.evaluate(c, size, ink, tb, 0.5)
    e0 = m0.evaluate(c, size, ink, tb, 0.5)
    print(f"{name:12s} trained: auc {e['auc']} prec {e['precision']} rec {e['recall']} (base prec {e['base_precision']}, n {e['n']})  | untrained auc {e0['auc']}")
# add one dialog + the editor to training (the 'constantly learning' case) and re-test on the OTHER ones
for ep in range(6):
    for c, size, ink, tb in [tests["dialog"], tests["editor"]]:
        m.observe_scan(c, size, ink, tb, epochs=2)
c, size, ink, tb = tests["dialog-dark"]
print("after learning from a dialog and the editor, held-out dark dialog:", m.evaluate(c, size, ink, tb, 0.5))
