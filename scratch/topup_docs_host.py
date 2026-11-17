"""Do the applications whose vendor REFUSES a reader now get a guide, after the documentation-host route? Runs beside the live runs: internet only, no window."""
import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor.knowledge import guide_corpus as GC

CANDIDATES = ["acad", "studio64", "tableau", "sharex", "matlab", "vlc", "skype", "taskmgr"]
rep = GC.build(apps=CANDIDATES, budget_per_app=200.0, pages_tier=30, pages_other=15, top_up=1, log=print)
print("totals:", rep.get("totals"))
