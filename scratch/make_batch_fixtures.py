"""Create the two batch inputs the harvester accepts, for a cheap end-to-end batch test."""
from pathlib import Path

import openpyxl

root = Path(r"D:\new_automation\scratch")
(root / "vid_links.txt").write_text(
    "# comment lines are skipped\n"
    "Microsoft Excel::https://www.youtube.com/watch?v=wbJcJCkBcMg\n"
    "https://www.youtube.com/watch?v=OKA4y7WoNHU\n", encoding="utf-8")

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "App_Guides"
ws.append(["App Name", "Publisher", "Target URL", "YouTube Tutorial Link"])
ws.append(["Microsoft Excel", "Microsoft", "https://excel.example",
           "https://www.youtube.com/watch?v=wbJcJCkBcMg"])
ws.append(["GIMP", "GNU", "https://gimp.org", "https://www.youtube.com/watch?v=rUKbD1hhEEM"])
ws.append(["Empty row", "n/a", "", ""])
wb.save(root / "vid_master.xlsx")
print("wrote", root / "vid_links.txt", "and", root / "vid_master.xlsx")
