"""Offline check of the new deterministic routes (no app running, no model needed for the pick itself).

Questions it answers, all from measured shortlists of the real spreadsheet run:
  * a save goal on the document screen   -> does decisive() take 'File Tab' instead of leaving it to the 7B judge?
  * a save goal on the backstage screen  -> does it take 'Save As', then 'Browse', not the format combo?
  * a goal that NAMES the search box     -> must stay with the judge (it is the right target there)
  * the utility-strip test               -> what it recognises, and what it must not touch
"""
import sys
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.desktop_grounding import ConstrainedJudge as CJ, GroundedElement


def el(name, role, bbox=(0, 0, 100, 30), conf=1.0):
    return GroundedElement(id=name, name=name, role=role, bbox=bbox, tier="uia", confidence=conf, hwnd=1)


SAVE = "save the workbook as D:\\new_automation\\_e2e_tmp\\hj_xls1.xlsx"

doc_screen = [
    el("File Tab", "button", (3, 5, 61, 33)),
    el("Microsoft search", "edit", (1000, 5, 1200, 33)),
    el("Ribbon", "pane"),
    el("\u206aBook1\u206c  -  Excel", "button"),
    el("Customize Quick Access Toolbar", "menuitem"),
    el("Save", "button", (12, 5, 32, 25)),
    el("Grid", "datagrid", (9, 271, 1245, 944)),
    el("A1", "dataitem", (9, 271, 110, 291)),
]

backstage = [
    el("Save As", "listitem", (30, 200, 220, 240)),
    el("Save", "text"),
    el("save", "text"),
    el("Save As", "group"),
    el("Browse", "button", (60, 400, 180, 430)),
]

after_save_as = [
    el("Browse", "button", (60, 400, 180, 430)),
    el("Save", "text"),
    el("save", "text"),
    el("Save as type", "combobox", (300, 500, 600, 530)),
    el("save", "text"),
]

for label, goal, els in (
        ("doc screen  ", SAVE, doc_screen),
        ("backstage   ", SAVE, backstage),
        ("after SaveAs", SAVE, after_save_as),
):
    ranked = CJ.rank_scored(goal, els)
    top3 = [round(r[0], 1) for r in ranked[:3]]
    d = CJ().decisive(goal, els)
    pick = (d or {}).get("element", {}).get("name")
    why = (d or {}).get("why", "-> judge")
    print(f"{label} ranked_top={top3} {[ (r[2].name or '')[:14] for r in ranked[:3] ]}  decisive={pick!r} {why}")

# goals that NAME the strip must not be treated as a wrong turn
for goal in ("type gmail.com in the address bar", "click the Search button",
             "search for pdf in the file explorer search box"):
    hits = [e.name for e in [el("Microsoft search", "edit"), el("Address and search bar", "edit")]
            if CJ._is_utility_strip(goal, e)]
    print(f"strip? {goal[:44]!r} -> {hits}")
