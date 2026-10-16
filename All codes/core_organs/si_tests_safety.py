"""
si_tests_safety -- tests for safety_guard (Checkpoint 0): the one blocklist every explorer/driver asks before a click.

  SG1  every Checkpoint-0 term (Delete, Format, Reset, Uninstall, Purchase) and the Phase-3 terms (Remove, Close, Exit, Submit) are blocked, in any case, with access keys / ellipses / accents
  SG2  no false positives on ordinary words that merely contain a term (Information, Display, Postscript, Reservation ...) and ordinary controls (Open, Save, Zoom In, Settings)
  SG3  an unnamed control is blocked; `allow=` lifts destructive/commit but never financial; the decision explains itself
"""

from __future__ import annotations

import os
import sys

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


def _sg():
    try:
        import safety_guard as S  # type: ignore
    except Exception:
        from core_organs import safety_guard as S  # type: ignore
    return S


def run_sg1() -> "TestOutcome":
    """SG1: every Checkpoint-0 and Phase-3 risky term is blocked however the label is dressed"""
    S = _sg()
    must_block = ["Delete", "&Delete...", "DELETE ALL", "Format Disk", "Format...", "Reset", "Reset to Defaults", "Uninstall", "Uninstall a program", "Purchase", "Complete Purchase",
                  "Remove", "Remove Background", "Close", "Close Window", "Exit", "Exit Blender", "Submit", "Don\u2019t Save", "Don't save", "Q\u00fait", "Place Order"]
    missed = [l for l in must_block if S.check(l).allowed]
    cats = {"Delete": "destructive", "Purchase": "financial", "Submit": "commit"}
    wrong = {l: S.check(l).category for l, c in cats.items() if S.check(l).category != c}
    checks = {"all_risky_labels_blocked": not missed, "categories_are_right": not wrong}
    return _verdict(checks, f"missed={missed} wrong={wrong} of {len(must_block)} labels")


def run_sg2() -> "TestOutcome":
    """SG2: words that merely contain a term, and ordinary controls, are not blocked"""
    S = _sg()
    must_allow = ["Information", "Display Settings", "Postscript", "Reservation", "Payload", "Preformatted", "Open", "Save As", "Zoom In", "Settings", "File", "Home", "Bold",
                  "Resetting", "Closet", "Buyer's guide", "Sender"]
    # 'Resetting', 'Buyer's guide', 'Sender' are NOT in the list on purpose: whole-word match only (a documented trade-off); assert that, not wish it away.
    fp = [l for l in must_allow if not S.check(l).allowed]
    checks = {"no_false_positives": not fp}
    return _verdict(checks, f"false positives={fp} of {len(must_allow)}")


def run_sg3() -> "TestOutcome":
    """SG3: unnamed is blocked; allow= lifts destructive/commit but never financial; a block explains itself"""
    S = _sg()
    d = S.check("Delete")
    checks = {"empty_blocked": not S.check("") and not S.check(None) and S.check("   ").category == "unnamed",
              "allow_lifts_destructive": S.check("Delete", allow=["destructive"]).allowed,
              "allow_lifts_commit": S.check("Submit", allow=("commit",)).allowed,
              "financial_never_lifted": not S.check("Purchase", allow=["financial", "destructive", "commit"]).allowed,
              "block_explains_itself": (not d) and "delete" in d.why() and d.category == "destructive" and d.term == "delete",
              "allowed_is_truthy": bool(S.check("Open")) and S.is_safe("Open")}
    return _verdict(checks)


TESTS = [("SG1", run_sg1), ("SG2", run_sg2), ("SG3", run_sg3)]

if __name__ == "__main__":
    rc = 0
    for name, fn in TESTS:
        r = fn()
        print(f"[{'PASS' if r.passed else 'FAIL'}] {name} {r.evidence}")
        rc |= 0 if r.passed else 1
    sys.exit(rc)
