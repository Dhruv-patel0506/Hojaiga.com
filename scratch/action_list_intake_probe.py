"""Can a hand-written action list be fed in? Reads a sample list through the NEW intake (AppRun._person_procs), then grounds every step against Word's REAL saved catalog - offline, nothing is launched and no cursor moves."""
import json
import os
import sys
import types

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor import apprun as AR, harvest as HV
from core_organs.professor.knowledge import guide_steps as GS

SAMPLE = [
    {"goal": "Bold a word and check the ruler", "steps": [
        "Click the Bold button in the Home tab.",
        "Type 'Hojaiga sample' in the document.",
        "Press Ctrl+A.",
        "Click View > Ruler."]},
    {"goal": "A step that names nothing real", "steps": [
        "Click the FlarBST icon on the imaginary toolbar."]},
]
path = r"d:\new_automation\scratch\_sample_actions.json"
json.dump(SAMPLE, open(path, "w", encoding="utf-8"), ensure_ascii=True, indent=3)

stub = types.SimpleNamespace(actions=path, report={}, say=lambda s: print("  say:", s),
                             ui=types.SimpleNamespace(phase=lambda *a: print("  phase:", " | ".join(str(x)[:110] for x in a))))
procs = AR.AppRun._person_procs(stub)
print(f"intake read {len(procs)} task(s) from {os.path.basename(path)}")
for p in procs:
    print(f"\n- {p['goal']}  [source={p['source']}, {len(p['steps'])} parsed step(s)]")
    for st in p["steps"]:
        print(f"    action={st.action:<12} target={st.target!r:<28} path={st.path} chord={st.chord!r} text={st.text!r}")

cat = HV.Catalog.load("winword")
print(f"\nWord catalog loaded for grounding: {len(cat.verbs)} verbs")
for p in procs:
    g = GS.ground(p["steps"], cat)
    n_ok, n_app = GS.coverage(g)
    print(f"\n== {p['goal']} -> grounded {n_ok}/{n_app}")
    for x in g:
        v = x.verb
        print(f"   [{x.how:<10}] {x.step.raw[:58]!r:<62} -> " + (f"{v.label} @ {' > '.join(str(s) for s in (v.path or [])[-3:])}" if v is not None else (x.note or "")[:78]))
