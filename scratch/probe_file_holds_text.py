"""file_holds_text against real bytes: the empty workbook, a synthetic workbook that HAS the value,
a plain text file, a picture. Expect: False / True / True / None."""
import io, os, sys, zipfile
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.desktop_grounding import file_holds_text

tmp = r"D:\new_automation\_e2e_tmp"
os.makedirs(tmp, exist_ok=True)

# 1) the real workbook the loop saved earlier this evening (file exists, sheet is empty)
prev = max([f for f in os.listdir(r"D:\new_automation\_excel_e2e_tmp") if f.endswith(".xlsx")],
           key=lambda f: os.path.getmtime(os.path.join(r"D:\new_automation\_excel_e2e_tmp", f)),
           default=None)
if prev:
    p = os.path.join(r"D:\new_automation\_excel_e2e_tmp", prev)
    print("empty workbook :", file_holds_text(p, "42"))

# 2) a workbook that really holds 42 in A1 (built by hand: sheet1 carries <c r="A1"><v>42</v>)
wb = os.path.join(tmp, "holds42.xlsx")
with zipfile.ZipFile(wb, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
    z.writestr("xl/worksheets/sheet1.xml",
               '<worksheet><sheetData><row r="1"><c r="A1"><v>42</v></c></row></sheetData></worksheet>')
print("workbook with 42:", file_holds_text(wb, "42"))

# 3) a text file, with the value on its own line and in a sentence
tx = os.path.join(tmp, "holds.txt")
io.open(tx, "w", encoding="utf-8").write("hello world\n")
print("text hit        :", file_holds_text(tx, "hello world"))
print("text miss       :", file_holds_text(tx, "42"))

# 4) a picture: no text form at all -> the check reports it did not run
pn = os.path.join(tmp, "pic.png")
open(pn, "wb").write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
print("png             :", file_holds_text(pn, "42"))

# 5) a number must not be satisfied by a longer number sitting in the same cell
wb2 = os.path.join(tmp, "holds1422.xlsx")
with zipfile.ZipFile(wb2, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("xl/worksheets/sheet1.xml", '<row r="1"><c r="A1"><v>1422</v></c></row>')
print("'42' vs '1422'  :", file_holds_text(wb2, "42"), "(whole-piece rule: exact match, or a >2-char word inside a piece)")
