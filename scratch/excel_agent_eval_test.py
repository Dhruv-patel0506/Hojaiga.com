"""Offline test of the agent's independent formula evaluator + its sandbox guard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"D:\new_automation")))
import excel_agent_autorun as A  # noqa: E402

sheet = {
    "name": "T", "headers": ["Name", "Wage", "Hours", "Taxable"],
    "rows": [["Ann", 10.0, 40], ["Bob", 20.0, 50], ["Cy", 15.0, 30]],
    "formulas": [
        {"cell": "D2", "formula": "=B2*C2"}, {"cell": "D3", "formula": "=B3*C3"},
        {"cell": "D4", "formula": "=B4*C4"}, {"cell": "D5", "formula": "=SUM(D2:D4)"},
        {"cell": "F2", "formula": "=AVERAGE(B2:B4)"},
        {"cell": "F3", "formula": "=INDEX(A2:A4,MATCH(MAX(D2:D4),D2:D4,0))"},
        {"cell": "F4", "formula": '=COUNTIF(C2:C4,">40")'},
        {"cell": "F5", "formula": "=ROUND(D5*0.19,2)"},
        {"cell": "F6", "formula": "=SUMPRODUCT(B2:B4,C2:C4)"},
        {"cell": "F7", "formula": '=IF(D5>1000,"high","low")'},
    ],
}
want = {"D2": 400.0, "D3": 1000.0, "D4": 450.0, "D5": 1850.0, "F2": 15.0, "F3": "Bob",
        "F4": 1, "F5": 351.5, "F6": 1850.0, "F7": "high"}
got = A.evaluate_sheet(sheet)
fails = []
for k, exp in want.items():
    ok = abs(float(got.get(k, -1)) - float(exp)) < 0.01 if not isinstance(exp, str) else got.get(k) == exp
    print(("  PASS  " if ok else "  FAIL  ") + f"{k} = {got.get(k)!r} (expected {exp!r})")
    if not ok:
        fails.append(k)

print("\nsandbox guard (model-authored text must not execute):")
for label, expr in (("attribute access", "(1).__class__"), ("import", "__import__('os').system('x')"),
                    ("open", "open('x')"), ("comprehension", "[y for y in (1,2)]"),
                    ("subscript-of-name", "FUNCS['SUM']([1,2])"), ("lambda", "(lambda: 1)()")):
    res = A.safe_eval(expr)
    allowed_call = label.startswith("subscript")
    ok = (res is not None) if allowed_call else (res is None)
    print(("  PASS  " if ok else "  FAIL  ") + f"{label}: {res!r}")
    if not ok:
        fails.append(label)
print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
