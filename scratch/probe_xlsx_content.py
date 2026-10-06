"""What is actually inside the workbook the loop saved? (existence is not the whole truth)"""
import glob, os, re, zipfile

p = max(glob.glob(r"D:\new_automation\_excel_e2e_tmp\*.xlsx"), key=os.path.getmtime)
z = zipfile.ZipFile(p)
sheets = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
print("file:", p, os.path.getsize(p), "bytes; zip parts:", len(z.namelist()), "sheets:", sheets)
CELL = re.compile(r'<c r="([A-Z]+\d+)"[^>]*>(?:<v>([^<]*)</v>)?', re.S)
for s in sheets:
    x = z.read(s).decode("utf8", "ignore")
    cells = [(r, v) for r, v in CELL.findall(x) if v]
    print(f"  {s}: {len(cells)} non-empty cell(s) -> {cells[:6]}")
    print(f"  contains '42' as a value: {any(v == '42' for _r, v in cells)}")
