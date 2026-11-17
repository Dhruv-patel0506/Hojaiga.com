import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_steps as GS
from core_organs.professor.harvest import Catalog, Verb
def V(l, path, role="button"): return Verb(l, l, list(path), "", "", True, False, "", 0, "", role, ["uia"], "measured", "safe")
cat = Catalog(app_key="d", verbs=[V("Black", ["Colours"]), V("Red", ["Colours"]), V("Pencil", ["Tools"]), V("Size", ["Selection"], "field")])
t = "1. Select the **Pencil** tool.\n2. Choose a color from the color palette.\n3. Choose a line size if needed.\n4. Draw on the canvas."
for g in GS.ground(GS.parse_steps(t), cat): print(g.step.raw[:45].ljust(46), g.how, g.verb.label if g.verb else "", "|", g.note[:90])
