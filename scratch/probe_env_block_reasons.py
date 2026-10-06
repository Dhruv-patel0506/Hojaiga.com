"""Evidence lines for the ENV-BLOCKED rows in the newest appended suite section."""
import io, re

path = r"d:\new_automation\All codes\core_organs\system_intelligence_results.txt"
raw = io.open(path, "r", encoding="utf-8", errors="replace").read()
sec = raw[raw.rindex("System Intelligence Suite"):]
for m in re.finditer(r"\[ENV-BLOCKED\].*?(?=\n\[|\Z)", sec, re.S):
    print(m.group(0)[:700].rstrip())
    print("-" * 70)
