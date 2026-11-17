import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs import headless_input as hin
from core_organs.professor import capture as CAP
rows = []
for h, t in hin.top_level_titles(visible_only=True):
    try:
        wi = CAP.window_info(h)
        rows.append((wi.process, wi.cls, t[:60], h, wi.minimized))
    except Exception:
        pass
for p, c, t, h, mn in sorted(rows):
    if t.strip():
        print(f"{p:26s} {c[:28]:28s} {'(min) ' if mn else ''}{t}")
