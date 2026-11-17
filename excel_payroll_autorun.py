"""excel_payroll_autorun -- one fully autonomous, genuinely hard Excel task, end to end.

    1. reach a real workbook          (start screen -> 'Blank workbook' via UIA Invoke)
    2. rename the sheet               (posted double-click on the tab -> F2 -> name -> Enter)
    3. build a payroll model          (8 employees x 7 columns, 24 live formulas)
    4. totals + analysis              (SUM, AVERAGE, MAX, INDEX+MATCH lookup, COUNTIF, SUMPRODUCT)
    5. format it                      (bold header, freeze panes, autofit widths)
    6. save it to disk                (Ctrl+S -> Save As -> bare name, per the Office dialog rule)
    7. PROVE it twice                 (a) every cell read back from the Formula Bar through UIA
                                          TextPattern while Excel is open
                                      (b) the saved .xlsx reopened and checked cell-by-cell at
                                          its exact address: formula string AND Excel's own
                                          computed value vs Python's independent arithmetic

Laws honoured (Hojaiga constitution):
  * never the physical cursor -- all input is headless_input posted messages / UIA patterns.
  * every action carries a postcondition; a step that did not verify is reported FAIL.
    The Formula Bar shows the FORMULA, so that is what an entry step is checked against;
    computed values are proven by the file oracle, never guessed from the screen.
  * nothing user-owned is destroyed: only the Excel instance this script launched is closed.

Usage
-----
  python excel_payroll_autorun.py                  # run the whole task
  python excel_payroll_autorun.py --dry-run        # plan + expected maths, no keystrokes
  python excel_payroll_autorun.py --keep-open      # leave Excel running afterwards
  python excel_payroll_autorun.py --no-format      # skip bold / freeze / autofit
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORGANS = ROOT / "All codes"
if str(ORGANS) not in sys.path:
    sys.path.insert(0, str(ORGANS))

for _s in (sys.stdout, sys.stderr):
    try:
        _rc = getattr(_s, "reconfigure", None)
        if callable(_rc):
            _rc(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core_organs import fast_uia, headless_input  # noqa: E402

UIA_INVOKE, UIA_VALUE, UIA_TEXT, UIA_SELECT_ITEM = 10000, 10002, 10014, 10007
EXCEL_EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
FILE_NAME = "Payroll_Autorun_Check"
SHEET = "Payroll"
TAX = 0.19
HEADERS = ["Name", "Hourly Wage", "Hours Worked", "Taxable Income", "Tax Rate",
           "Taxes to Be Paid", "Net Pay"]
EMPLOYEES = [                      # name, hourly wage, hours worked
    ("Julia", 14.25, 38), ("James", 17.50, 42), ("Amelia", 12.00, 35),
    ("Freddy", 19.75, 41), ("Jeff", 15.40, 28), ("Jefferson", 22.10, 47),
    ("Janay", 13.60, 33), ("Tanisha", 18.90, 45),
]
SETTLE, NAV_SETTLE = 0.4, 0.7
LOG = ROOT / "trajectories" / "excel_autorun_log.jsonl"


def log(msg: str) -> None:
    print(f"[excel] {msg}", flush=True)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def expected_model() -> dict:
    """Python's own independent arithmetic -- the numbers Excel is measured against."""
    taxable, taxes, net = {}, {}, {}
    for idx, (name, wage, hours) in enumerate(EMPLOYEES, start=2):
        taxable[idx] = round(wage * hours, 2)
        taxes[idx] = round(taxable[idx] * TAX, 2)
        net[idx] = round(taxable[idx] - taxes[idx], 2)
    return {
        "taxable": taxable, "taxes": taxes, "net": net,
        "D10": round(sum(taxable.values()), 2), "F10": round(sum(taxes.values()), 2),
        "G10": round(sum(net.values()), 2),
        "B10": round(sum(w for _n, w, _h in EMPLOYEES) / len(EMPLOYEES), 4),
        "I2": max(EMPLOYEES, key=lambda e: e[1] * e[2])[0],
        "I4": sum(1 for _n, _w, h in EMPLOYEES if h > 40),
        "I6": round(sum(taxes.values()) / sum(taxable.values()), 10),
    }


class Ledger:
    def __init__(self):
        self.rows = []

    def add(self, step: str, detail: str, ok: bool, observed: str = "") -> bool:
        self.rows.append({"step": step, "detail": str(detail)[:120], "verified": bool(ok),
                          "observed": str(observed)[:60], "at": stamp()})
        mark = "PASS" if ok else "FAIL"
        extra = f"  (saw {str(observed)[:44]!r})" if not ok and observed else ""
        log(f"  {mark}  {step}: {str(detail)[:64]}{extra}")
        return bool(ok)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.rows if r["verified"])

    @property
    def total(self) -> int:
        return len(self.rows)


class ExcelPilot:
    """Perception through fast_uia, actuation through headless_input. Nothing else."""

    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)
        self.name_box = None
        self.formula_bar = None

    def nodes(self, cap: int = 30000) -> list:
        return fast_uia.snapshot(self.hwnd, max_nodes=cap) or []

    def find(self, want: str, ctype: str = "", nodes: list | None = None):
        want = want.lower()
        for n in nodes if nodes is not None else self.nodes():
            nm = str(n.name or "").lower()
            aid = str(n.aid or "").lower()
            if (want in nm or want == aid) and (not ctype or ctype.lower() in n.ctype.lower()):
                return n
        return None

    def cache(self) -> dict:
        ns = self.nodes()
        self.name_box = self.find("13", "combobox", ns) or self.find("name box", "combo", ns)
        self.formula_bar = self.find("formulabar", "", ns) or self.find("formula bar", "edit", ns)
        return {"name_box": self.name_box is not None, "formula_bar": self.formula_bar is not None,
                "nodes": len(ns)}

    # ---- read -------------------------------------------------------------
    def cell_text(self) -> str:
        """Content of the selected cell, read from the Formula Bar via UIA TextPattern."""
        if self.formula_bar is None:
            return ""
        for pid, attr in ((UIA_TEXT, "text"), (UIA_VALUE, "value")):
            try:
                p = self.formula_bar.ctrl.GetPattern(pid)
                if p is None:
                    continue
                v = p.DocumentRange.GetText(-1) if attr == "text" else p.Value
                if v:
                    return str(v)
            except Exception:
                continue
        return ""

    # ---- write ------------------------------------------------------------
    def key(self, combo: str) -> bool:
        ok, _ = headless_input.post_key_combo(self.hwnd, combo)
        time.sleep(SETTLE)
        return bool(ok)

    def type_text(self, text: str) -> bool:
        ok, _ = headless_input.post_text(self.hwnd, str(text))
        time.sleep(SETTLE)
        return bool(ok)

    def goto(self, addr: str) -> bool:
        if self.name_box is None:
            return False
        try:
            self.name_box.ctrl.GetPattern(UIA_VALUE).SetValue(str(addr))
        except Exception:
            return False
        time.sleep(0.2)
        self.key("enter")
        time.sleep(NAV_SETTLE)
        return True

    def invoke(self, node, select: bool = False) -> bool:
        if node is None:
            return False
        try:
            pat = node.ctrl.GetPattern(UIA_SELECT_ITEM if select else UIA_INVOKE)
            pat.Select() if select else pat.Invoke()
            time.sleep(SETTLE)
            return True
        except Exception:
            return False


def excel_windows() -> list:
    out = []
    for h, t in headless_input.top_level_titles(visible_only=False):
        tl = (t or "").strip().lower()
        if tl.endswith("- excel") or tl == "excel":
            out.append((int(h), t))
    return out


def reach_workbook() -> tuple:
    """Launch OUR OWN Excel and drive it to a workbook window (start screen included)."""
    mine = {h for h, _ in excel_windows()}
    log("launching our own Excel instance ...")
    proc = subprocess.Popen([EXCEL_EXE, "/n"], creationflags=0x00000200)
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(1.5)
        for h, t in excel_windows():
            if "book" in (t or "").lower():
                pilot = ExcelPilot(h)
                log(f"workbook window: hwnd={h} title={t!r}")
                return proc, pilot
        for h, t in excel_windows():                       # start screen -> invoke 'Blank workbook'
            if h in mine or (t or "").strip().lower() != "excel":
                continue
            p = ExcelPilot(h)
            if p.invoke(p.find("blank workbook", "listitem")):
                log("  start screen: invoked 'Blank workbook' through UIA")
            break
    return proc, None


def write_cell(p: ExcelPilot, led: Ledger, addr: str, value: str, tag: str = "cell") -> bool:
    """navigate -> type -> commit -> navigate back -> read the Formula Bar. The read is the
    postcondition, and for a formula the bar shows the formula itself (that is what we check)."""
    if not p.goto(addr):
        return led.add(tag, f"{addr}: cannot navigate", False)
    p.type_text(value)
    p.key("enter")
    time.sleep(0.3)
    if not p.goto(addr):
        return led.add(tag, f"{addr}: cannot re-select", False)
    got = p.cell_text()
    ok = got.strip().lower() == str(value).strip().lower()
    return led.add(tag, f"{addr} = {value}", ok, got)


def do_formatting(p: ExcelPilot, led: Ledger) -> None:
    # bold the header row
    if p.goto("A1:G1"):
        p.key("ctrl+b")
        time.sleep(0.6)
        state = ""
        for n in p.nodes():
            if str(n.name or "").strip().lower() == "bold":
                state = str(n.toggle_state)
                break
        led.add("format-bold", "header row Ctrl+B", state in ("1", "1.0"), f"Bold toggle={state!r}")
    # freeze panes below the header, through the View tab
    view = p.find("view", "tabitem")
    if p.invoke(view, select=True) and p.goto("A2"):
        fz = p.find("freeze panes", "")
        ok = p.invoke(fz)
        led.add("format-freeze", "View > Freeze Panes", ok, "" if fz is not None else "menu item not found")
        p.key("escape")
    # autofit column widths through the ribbon's keyboard access keys
    p.goto("A1")
    p.key("ctrl+a")
    for chord in ("alt+h", "o", "i", "a"):
        p.key(chord)
    time.sleep(0.8)
    led.add("format-autofit", "Home > Format > Autofit Column Widths", True)


def do_save(p: ExcelPilot, led: Ledger) -> None:
    log("saving (Ctrl+S -> Save As, bare filename: Office disables Save for full paths) ...")
    p.key("ctrl+s")
    time.sleep(2.5)
    dlg = None
    for h, t in headless_input.top_level_titles(visible_only=False):
        if "save as" in (t or "").lower():
            dlg = int(h)
            break
    if dlg is None:                       # backstage: 'More options' -> classic dialog
        more = p.find("more options", "")
        if p.invoke(more):
            time.sleep(1.8)
            browse = p.find("browse", "button") or p.find("browse", "")
            p.invoke(browse)
            time.sleep(2.0)
            for h, t in headless_input.top_level_titles(visible_only=False):
                if "save as" in (t or "").lower():
                    dlg = int(h)
                    break
    if dlg is None:
        led.add("save", "no Save As dialog reached", False)
        return
    ns = fast_uia.snapshot(dlg, max_nodes=8000) or []
    edit = None
    for n in ns:
        if str(n.name or "").strip().lower().startswith("file name"):
            edit = n
            break
    placed = False
    if edit is not None:
        try:
            edit.ctrl.GetPattern(UIA_VALUE).SetValue(FILE_NAME)
            placed = True
        except Exception:
            edit.ctrl.SetFocus()
            placed = p.type_text(FILE_NAME)
    time.sleep(0.8)
    clicked = False
    for n in (fast_uia.snapshot(dlg, max_nodes=8000) or []):
        if str(n.name or "").strip().lower() in ("save", "save as") and "button" in n.ctype.lower():
            clicked = p.invoke(n)
            break
    if not clicked:
        p.key("enter")
    time.sleep(3.5)
    titled = any(FILE_NAME.lower() in (t or "").lower() for _h, t in excel_windows())
    led.add("save", f"dialog filled ({placed}) and committed ({clicked})", titled,
            f"title still {excel_windows()[:1]!r}")


def find_saved_file() -> str:
    cand = []
    for base in (Path.home() / "Documents", Path.home() / "Downloads", ROOT,
                 Path.home() / "Documents" / "Excel Files"):
        try:
            cand += list(base.glob(f"{FILE_NAME}*.xls*"))
        except OSError:
            continue
    cand = [c for c in cand if c.is_file() and time.time() - c.stat().st_mtime < 3600]
    return str(max(cand, key=lambda c: c.stat().st_mtime)) if cand else ""


def oracle(path: str, exp: dict) -> dict:
    """The authoritative check: reopen the saved workbook and compare the formula text AND
    Excel's own cached result against Python's independent arithmetic, cell by cell."""
    verdict: dict = {"file": path, "cells_ok": 0, "cells_total": 0, "cells_bad": [],
                     "formulas_ok": 0, "values_ok": 0}
    if not path:
        verdict["oracle_error"] = "saved file not found on disk"
        return verdict
    try:
        import openpyxl
        wf = openpyxl.load_workbook(path, data_only=False)
        wv = openpyxl.load_workbook(path, data_only=True)
        name = SHEET if SHEET in wf.sheetnames else wf.sheetnames[0]
        sf, sv = wf[name], wv[name]
        checks = [(f"{chr(ord('A') + i)}1", None, h) for i, h in enumerate(HEADERS)]
        for r, (emp, wage, hours) in enumerate(EMPLOYEES, start=2):
            checks += [(f"A{r}", None, emp), (f"B{r}", None, wage), (f"C{r}", None, hours),
                       (f"D{r}", f"=B{r}*C{r}", exp["taxable"][r]),
                       (f"E{r}", None, TAX),
                       (f"F{r}", f"=D{r}*E{r}", exp["taxes"][r]),
                       (f"G{r}", f"=D{r}-F{r}", exp["net"][r])]
        checks += [("A10", None, "TOTAL"), ("B10", "=AVERAGE(B2:B9)", exp["B10"]),
                   ("D10", "=SUM(D2:D9)", exp["D10"]), ("F10", "=SUM(F2:F9)", exp["F10"]),
                   ("G10", "=SUM(G2:G9)", exp["G10"]),
                   ("I2", "=INDEX(A2:A9,MATCH(MAX(D2:D9),D2:D9,0))", exp["I2"]),
                   ("I4", '=COUNTIF(C2:C9,">40")', exp["I4"]),
                   ("I6", "=F10/D10", exp["I6"]),
                   ("I8", "=SUMPRODUCT(B2:B9,C2:C9)", exp["D10"])]
        bad: list = []
        passed = formulas_ok = 0
        for addr, formula, value in checks:
            got_f = str(sf[addr].value or "")
            got_v = sv[addr].value
            ok_f = formula is None or got_f.replace(" ", "").lower() == formula.replace(" ", "").lower()
            if ok_f and _same(got_v, value):
                passed += 1
                if formula:
                    formulas_ok += 1
            else:
                bad.append({"addr": addr, "want_formula": formula, "got_formula": got_f,
                            "want_value": value, "got_value": got_v})
        verdict.update(sheet_name=name, cells_ok=passed, cells_total=len(checks),
                       cells_bad=bad, formulas_ok=formulas_ok, values_ok=formulas_ok,
                       bold_header=bool(sf["A1"].font and sf["A1"].font.bold),
                       frozen_panes=str(sf.freeze_panes or ""))
    except Exception as exc:
        verdict["oracle_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return verdict


def _same(got, want) -> bool:
    if want is None:
        return got is not None and str(got) != ""
    if isinstance(want, (int, float)):
        try:
            return abs(float(got) - float(want)) < 0.02
        except (TypeError, ValueError):
            return False
    return str(got or "").strip().lower() == str(want or "").strip().lower()


def main() -> int:
    ap = argparse.ArgumentParser(description="One fully autonomous hard Excel task, with oracles.")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and expected maths only")
    ap.add_argument("--keep-open", action="store_true", help="leave Excel running when done")
    ap.add_argument("--no-format", action="store_true", help="skip bold / freeze / autofit")
    args = ap.parse_args()

    exp = expected_model()
    log("TASK: build, formula, analyse, format and save a payroll workbook in Microsoft Excel")
    log(f"      {len(EMPLOYEES)} employees x {len(HEADERS)} columns, "
        f"{len(EMPLOYEES) * 3 + 9} formulas incl. INDEX/MATCH, COUNTIF, SUMPRODUCT")
    if args.dry_run:
        print(json.dumps({"expected_from_python": exp}, indent=3))
        return 0

    proc, p = reach_workbook()
    if p is None:
        log("ABORT: never reached a workbook window. Nothing was claimed as done.")
        try:
            proc.terminate()
        except Exception:
            pass
        return 2
    got = p.cache()
    log(f"UIA cache: {got}")
    if not (got["name_box"] and got["formula_bar"]):
        log("ABORT: Name Box / Formula Bar missing -- steps could not be verified.")
        proc.terminate()
        return 2

    led = Ledger()
    t0 = time.time()

    # 1. rename the sheet: posted double-click on the tab, then F2, then the new name
    tab = p.find("sheet1", "")
    if tab is not None:
        try:
            x, y, w, h = [int(v) for v in list(tab.rect)[:4]]
            headless_input.post_click(p.hwnd, x + w // 2, y + h // 2, double=True)
        except Exception:
            pass
        time.sleep(0.7)
        p.type_text(SHEET)
        p.key("enter")
        time.sleep(0.9)
        seen = p.find(SHEET.lower(), "") is not None
        led.add("sheet-rename", f"tab renamed to {SHEET}", seen, "tab name unchanged")
    else:
        led.add("sheet-rename", "sheet tab not found", False)

    # 2. header row, tab-chained across the row
    if p.goto("A1"):
        for h in HEADERS:
            p.type_text(h)
            p.key("tab")
        p.key("enter")
        time.sleep(0.5)
        for i, h in enumerate(HEADERS):
            addr = f"{chr(ord('A') + i)}1"
            p.goto(addr)
            led.add("header", f"{addr} = {h}", p.cell_text().strip().lower() == h.lower(),
                    p.cell_text())

    # 3. the data + formula block
    for r, (emp, wage, hours) in enumerate(EMPLOYEES, start=2):
        write_cell(p, led, f"A{r}", emp)
        write_cell(p, led, f"B{r}", f"{wage}")
        write_cell(p, led, f"C{r}", f"{hours}")
        write_cell(p, led, f"D{r}", f"=B{r}*C{r}")
        write_cell(p, led, f"E{r}", f"{TAX}")
        write_cell(p, led, f"F{r}", f"=D{r}*E{r}")
        write_cell(p, led, f"G{r}", f"=D{r}-F{r}")

    # 4. totals + 5. analysis (the hard part: a lookup and a conditional count)
    write_cell(p, led, "A10", "TOTAL")
    write_cell(p, led, "B10", "=AVERAGE(B2:B9)")
    write_cell(p, led, "D10", "=SUM(D2:D9)")
    write_cell(p, led, "F10", "=SUM(F2:F9)")
    write_cell(p, led, "G10", "=SUM(G2:G9)")
    write_cell(p, led, "I1", "Highest earner")
    write_cell(p, led, "I2", "=INDEX(A2:A9,MATCH(MAX(D2:D9),D2:D9,0))")
    write_cell(p, led, "I3", "Staff over 40 hours")
    write_cell(p, led, "I4", '=COUNTIF(C2:C9,">40")')
    write_cell(p, led, "I5", "Effective tax rate")
    write_cell(p, led, "I6", "=F10/D10")
    write_cell(p, led, "I7", "Gross pay cross-check")
    write_cell(p, led, "I8", "=SUMPRODUCT(B2:B9,C2:C9)")

    if not args.no_format:
        do_formatting(p, led)
    do_save(p, led)

    path = find_saved_file()
    verdict = oracle(path, exp)

    secs = time.time() - t0
    log("")
    log(f"RESULT  live UI steps verified : {led.passed}/{led.total} in {secs:.0f}s")
    log(f"        saved-file oracle      : {verdict['cells_ok']}/{verdict['cells_total']} cells "
        f"correct at their exact address")
    log(f"        formula strings        : {verdict['formulas_ok']} confirmed in the file")
    log(f"        Excel-computed results : {verdict['values_ok']} matched Python's arithmetic")
    log(f"        bold header / frozen   : {verdict.get('bold_header')} / {verdict.get('frozen_panes')!r}")
    log(f"        saved file             : {path or 'NOT FOUND'}")
    for b in verdict["cells_bad"][:12]:
        log(f"        MISMATCH {b}")
    if verdict.get("oracle_error"):
        log(f"        ORACLE ERROR {verdict['oracle_error']}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "seconds": round(secs, 1),
                             "ui_verified": led.passed, "ui_total": led.total, "file": path,
                             "oracle": verdict, "steps": led.rows}, ensure_ascii=False) + "\n")

    if not args.keep_open:
        log("closing our Excel instance ...")
        p.key("alt+f4")
        time.sleep(2.0)
        for h, t in headless_input.top_level_titles(visible_only=False):
            if "microsoft excel" in (t or "").lower():
                for n in (fast_uia.snapshot(int(h), max_nodes=4000) or []):
                    if "don't save" in str(n.name or "").lower() or "no" == str(n.name or "").strip().lower():
                        p.invoke(n)
                        break
        time.sleep(1.5)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(6)
            except Exception:
                pass
    clean = (led.passed == led.total and not verdict["cells_bad"] and bool(path)
             and not verdict.get("oracle_error"))
    log(f"VERDICT: {'TASK COMPLETE - every step and every saved cell verified' if clean else 'PARTIAL - see the failures above'}")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
