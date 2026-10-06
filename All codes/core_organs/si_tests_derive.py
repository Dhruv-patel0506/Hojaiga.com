"""
si_tests_derive.py -- DE1: goals carry their own machine-checkable postconditions (offline, no desktop needed).

A task bench on real apps measured the failure this guards: "save the file as <path>" was reported PASS after only the File
menu was clicked (the default postcondition is 'the UI changed'), and a Paint "Save as project" file named x.png was
accepted as the PNG that was asked for. Kept out of run_system_intelligence_tests.py like the other si_tests_* modules.
"""

import os
import tempfile
import time
import uuid


def run_de1(TestOutcome):
    from core_organs import desktop_grounding as dg

    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    # 1. a saving goal that names a path gets 'file exists' (+ the signature of its format when it is a binary one)
    cases = {
        r"save the file as C:\Users\x\Temp\a.txt": {"file_created": r"C:\Users\x\Temp\a.txt"},
        r"save the image as C:\Users\x\my pics\a b.png": {"file_created": r"C:\Users\x\my pics\a b.png", "file_format": "png"},
        r"save the file as C:\t\a.txt and close it": {"file_created": r"C:\t\a.txt"},
        r"export to D:/out/report.pdf": {"file_created": "D:/out/report.pdf", "file_format": "pdf"},
        "save as notes": {},
        r"open C:\x\a.txt": {},
        r"save C:\Users\x\folder": {},
        "type hello world": {"text_contains": "hello world"},
        "type a haiku about autumn": {},
    }
    bad = [(g, dg.derive_expectation(g), want) for g, want in cases.items() if dg.derive_expectation(g) != want]
    check("saving-goals-derive-file-exists-and-format", not bad, f"{len(cases) - len(bad)}/{len(cases)} goals derived correctly" + (f"; WRONG: {bad[:2]}" if bad else ""))

    # 2. assertion goals ("expect X") are recognised, with the filler words removed; ordinary goals are not
    acases = {"expect Display is 100": "Display is 100", "Expect that 'Add device' is shown": "Add device",
              "verify Bluetooth page is visible": "Bluetooth page", "press 5": None, "checkout the cart": None,
              "type just a note": None}
    abad = [(g, dg.assertion_text(g), w) for g, w in acases.items() if dg.assertion_text(g) != w]
    check("assertion-goals-need-no-action", not abad, f"{len(acases) - len(abad)}/{len(acases)} read correctly" + (f"; WRONG: {abad[:2]}" if abad else ""))

    # 3. the requested FORMAT beats a learned/lexical "Save as ..." (Paint's submenu lists formats next to 'Save as project')
    def el(n, role="menuitem"):
        return dg.GroundedElement(id=n, name=n, role=role, bbox=(0, 0, 10, 10), tier="uia", confidence=0.9, hwnd=1)
    els = [el("Save"), el("Save as"), el("Save as project"), el("PNG picture"), el("JPEG picture"), el("BMP picture"), el("Other format")]
    picks = {}
    for ext, want in (("png", "PNG picture"), ("jpg", "JPEG picture"), ("bmp", "BMP picture")):
        top = dg.ConstrainedJudge.rank_scored(rf"save the image as C:\x\a.{ext}", els)[0][2].name
        picks[ext] = top
    top_txt = dg.ConstrainedJudge.rank_scored(r"save the file as C:\x\a.txt", els)[0][2].name
    check("requested-format-outranks-save-as-project",
          picks == {"png": "PNG picture", "jpg": "JPEG picture", "bmp": "BMP picture"} and top_txt.startswith("Save as"),
          f"top picks {picks}; .txt keeps '{top_txt}'")

    # 4. the verifier: the file must exist AND be the format its name claims
    v = dg.DesktopVerifier()
    snap = None          # file checks never read a snapshot
    tmp = os.path.join(tempfile.gettempdir(), "hj_de1_" + uuid.uuid4().hex[:6] + ".png")
    try:
        with open(tmp, "wb") as fh:
            fh.write(b"PK\x03\x04 a project file named .png")
        ok_bad, ev_bad = v.check_expect({"file_created": tmp, "file_format": "png"}, snap, snap, [])
        with open(tmp, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        ok_good, ev_good = v.check_expect({"file_created": tmp, "file_format": "png"}, snap, snap, [])
        check("a-non-png-named-png-is-not-a-pass", (not ok_bad) and ok_good, f"fake: {ev_bad}; real: {ev_good}")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    ok_missing, ev_missing = v.check_expect({"file_created": os.path.join(tempfile.gettempdir(), "hj_de1_never_" + uuid.uuid4().hex[:6] + ".png"),
                                             "file_format": "png"}, snap, snap, [])
    check("a-missing-file-is-not-a-pass", not ok_missing, ev_missing)

    # 5. existence is not the proof of a save. Measured: a stale e1.xlsx left by a killed run made an Excel
    # task that had written nothing report success, so the goal stamps when it began and the file must be
    # WRITTEN after that moment (and not be empty).
    stale = os.path.join(tempfile.gettempdir(), "hj_de1_stale_" + uuid.uuid4().hex[:6] + ".txt")
    try:
        with open(stale, "wb") as fh:
            fh.write(b"left behind by an earlier run")
        ok_stale, ev_stale = v.check_expect(
            {"file_created": stale, "file_fresh_since": time.time() + 60.0}, snap, snap, [])
        check("a-stale-file-is-not-proof-of-a-save", (not ok_stale) and "ALREADY on disk" in ev_stale, ev_stale)
        open(stale, "wb").close()                       # the app 'saved' an empty file
        ok_empty, ev_empty = v.check_expect({"file_created": stale}, snap, snap, [])
        check("a-zero-byte-file-is-not-a-save", (not ok_empty) and "0 bytes" in ev_empty, ev_empty)
        with open(stale, "wb") as fh:                   # and now it really wrote, after the goal began
            fh.write(b"42")
        ok_fresh, ev_fresh = v.check_expect(
            {"file_created": stale, "file_fresh_since": time.time() - 5.0}, snap, snap, [])
        check("a-write_after_goal_start_is_a-pass", ok_fresh, ev_fresh)
    finally:
        try:
            os.remove(stale)
        except OSError:
            pass

    # 6. bytes on disk are still not the content. Measured: the workbook was saved to the exact path it was
    # given, 8440 bytes, and its only sheet was EMPTY - the goal read DONE because nothing looked inside the
    # file. So a literal the run was told to write is searched for IN the file, and an empty document is a
    # FAIL (never "unreadable, so let it pass").
    import zipfile
    wb_dir = tempfile.gettempdir()
    wb_empty = os.path.join(wb_dir, "hj_de1_empty_" + uuid.uuid4().hex[:6] + ".xlsx")
    wb_42 = os.path.join(wb_dir, "hj_de1_42_" + uuid.uuid4().hex[:6] + ".xlsx")
    try:
        with zipfile.ZipFile(wb_empty, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "<?xml version='1.0'?><Types/>")
            z.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData/></worksheet>")
        with zipfile.ZipFile(wb_42, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "<?xml version='1.0'?><Types/>")
            z.writestr("xl/worksheets/sheet1.xml",
                       "<row r=\"1\"><c r=\"A1\"><v>42</v></c></row>")
        exp_empty = {"file_created": wb_empty, "file_fresh_since": time.time() - 5.0, "file_text_contains": "42"}
        ok_we, ev_we = v.check_expect(exp_empty, snap, snap, [])
        exp_full = dict(exp_empty, file_created=wb_42)
        ok_wf, ev_wf = v.check_expect(exp_full, snap, snap, [])
        # and the literal must actually reach the save goal: it comes from a DIFFERENT goal in the same run
        lit = dg.literal_typed_text("type 42 in cell A1")
        check("a-file-that-holds-nothing-is-not-a-save",
              (not ok_we) and ok_wf and lit == "42",
              f"empty: {ev_we} | filled: {ev_wf} | literal from 'type 42 in cell A1' = {lit!r}")
    finally:
        for pth in (wb_empty, wb_42):
            try:
                os.remove(pth)
            except OSError:
                pass

    failed = [c for c in checks if not c[1]]
    return TestOutcome(passed=not failed,
                       evidence="; ".join(f"{n}={'OK' if ok else 'FAIL'}({d})" for n, ok, d in checks),
                       metrics={"checks": len(checks), "failed": len(failed)})
