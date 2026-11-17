import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
from core_organs.professor import history as HS
import tempfile, os
h = HS.History(os.path.join(tempfile.gettempdir(), "x_hist.db"))
h.log("demo", "menu-expand", "expand", "File", "uia-expand", "a", "n", "b", "s", "state_change", True, None, "", {"how": "x"}, toolkit="winui", role="menu_item", safety="safe")
print(h.stats("demo"), len(h.rows("demo")))
