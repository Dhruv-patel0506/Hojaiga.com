"""What is REALLY inside the two workbooks the last suite run saved (the honest witness, read raw)."""
import re
import sys
import zipfile

for p in sys.argv[1:]:
    z = zipfile.ZipFile(p)
    names = z.namelist()
    ss = z.read("xl/sharedStrings.xml").decode("utf8") if "xl/sharedStrings.xml" in names else ""
    sheet = next((n for n in names if n.startswith("xl/worksheets/sheet")), "")
    sh = z.read(sheet).decode("utf8") if sheet else ""
    print(p)
    print("  shared strings :", re.findall(r"<t[^>]*>(.*?)</t>", ss)[:10])
    print("  cell records   :", re.findall(r"<c r=\"([A-Z]+[0-9]+)\"[^/>]*>(.*?)</c>", sh)[:10])
    print("  raw <v> values :", re.findall(r"<v>(.*?)</v>", sh)[:10])
