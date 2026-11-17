import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_steps as GS

text = """To place a marker:
1. Click **Add Marker** on the toolbar.
2. Choose **View** > **Zoom In**.
3. Open the Options tab.
4. Press **Ctrl**+**B** to make the text bold.
5. Type "Chapter one" in the **Title** field.
6. Select File > Export > PDF.
7. Tick the "Show Grid" checkbox.
8. Adjust the Cropping Ratio in the Inspector.
"""
for s in GS.parse_steps(text, "demo"):
    print(f"{s.n}. {s.action:12s} target={s.target!r:18} path={s.path} text={s.text!r} chord={s.chord!r}  <- {s.raw[:55]!r}")
print()
para = "Open the Edit menu, then choose Preferences. Click the Advanced tab and press Apply."
for s in GS.parse_steps(para, "para"):
    print(f"{s.n}. {s.action:12s} target={s.target!r:18} path={s.path} <- {s.raw[:55]!r}")
