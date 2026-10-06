"""Probe 15: the judge's spreadsheet pick with NO model available (compose must be deterministic).

Synthetic element list shaped like the measured spreadsheet screen, plus the compose goals the suite really
uses, so the new literal rule is checked for both directions: a spelled-out payload is taken from the words,
a generated one still goes to the composer.
"""
import os
import sys

os.environ["HOJAIGA_BRAIN_URL"] = "http://127.0.0.1:1/api/chat"   # no model: the literal path must carry the pick
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.desktop_grounding import ConstrainedJudge, GroundedElement  # noqa: E402

els = [
    GroundedElement(id="e1", name="Microsoft search", role="edit", bbox=(555, 18, 828, 45), tier="uia",
                    confidence=0.9, hwnd=1),
    GroundedElement(id="e2", name="Formula Bar", role="edit", bbox=(283, 223, 1271, 271), tier="uia",
                    confidence=0.9, hwnd=1),
    GroundedElement(id="e3", name="Grid", role="datagrid", bbox=(9, 271, 1245, 944), tier="uia",
                    confidence=0.55, hwnd=1),
    GroundedElement(id="e4", name="A1", role="dataitem", bbox=(43, 295, 123, 319), tier="uia",
                    confidence=0.9, hwnd=1),
    GroundedElement(id="e5", name="B1", role="dataitem", bbox=(123, 295, 203, 319), tier="uia",
                    confidence=0.9, hwnd=1),
    GroundedElement(id="e6", name="File Tab", role="button", bbox=(10, 10, 60, 40), tier="uia",
                    confidence=0.9, hwnd=1),
    GroundedElement(id="e7", name="Save As", role="listitem", bbox=(60, 200, 200, 240), tier="uia",
                    confidence=0.9, hwnd=1),
    GroundedElement(id="e8", name="Browse", role="button", bbox=(60, 300, 200, 340), tier="uia",
                    confidence=0.9, hwnd=1),
]
judge = ConstrainedJudge()

d = judge.decisive("type 42 in cell A1", els)
print("cell goal ->", None if d is None else (d["why"], d["element"]["name"], repr(d["text"])))
d2 = judge.decisive("type 7 in cell B1", els)
print("named B1  ->", None if d2 is None else (d2["why"], d2["element"]["name"], repr(d2["text"])))
print("no-cell   ->", judge.decisive("type 99", els) is not None)   # composer needed, model unreachable
top_save = judge.rank_scored(r"save the workbook as D:\new_automation\_e2e_tmp\hj_x.xlsx", els, None)[:4]
print("save top  ->", [(round(s, 1), e.name, e.role) for s, _i, e in top_save])
print("literal checks:")
for goal in ("type the current date", "type a haiku into the text area", "type my password into the login form",
             r"type 42 in cell A1", "type John Smith into the Name field"):
    print("   ", repr(goal), "->", repr(judge._literal_payload(goal)))
