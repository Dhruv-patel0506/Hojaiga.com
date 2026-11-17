import re
import subprocess
import sys

PY = sys.executable
for mod in (sys.argv[1:] or ["core_organs.si_tests_gaps"]):
    r = subprocess.run([PY, "-m", mod], cwd=r"d:\new_automation\All codes", capture_output=True, text=True, encoding="utf-8", errors="replace")
    t = (r.stdout or "") + (r.stderr or "")
    print(mod, "| rc:", r.returncode, "| PASS:", len(re.findall(r"\[PASS", t)), "| FAIL:", len(re.findall(r"\[FAIL", t)),
          "| env-blocked:", len(re.findall(r"ENV-BLOCKED", t)))
    fails = [l[:120] for l in t.splitlines() if "[FAIL" in l]
    for f in fails[:5]:
        print("   fail:", f)
