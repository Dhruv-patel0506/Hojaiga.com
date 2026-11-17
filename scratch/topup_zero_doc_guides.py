"""Top up the guide book of the applications that still have no document in the corpus folder (data/professor/guides).
Run alongside the app runs: it only reads the internet, never a window."""
import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor.knowledge import guide_corpus as GC

STRAGGLERS = ["skype", "vlc", "taskmgr", "studio64", "acad", "sharex", "matlab", "tableau"]
rep = GC.build(apps=STRAGGLERS, budget_per_app=150.0, pages_tier=25, pages_other=15, top_up=1, log=print)
print("totals:", rep.get("totals"))
