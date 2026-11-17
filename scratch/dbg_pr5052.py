import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
from core_organs.professor.knowledge import guide_steps as GS
from core_organs.professor.harvest import Catalog
c = Catalog(app_key="d")
for t in ("3. Choose an image from your PC.", "2. Press Windows + Shift + S.", "1. Click and drag on the canvas to draw."):
    for s in GS.parse_steps(t):
        print(t, "->", s.action, s.target, s.chord, GS.ground_step(s, c).how)
