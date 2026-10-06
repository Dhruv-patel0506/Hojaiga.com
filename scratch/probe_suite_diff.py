"""Compare the last N appended suite sections, test by test."""
import re, io

path = r"d:\new_automation\All codes\core_organs\system_intelligence_results.txt"
lines = io.open(path, "r", encoding="utf-8", errors="replace").read().splitlines()
heads = [i for i, ln in enumerate(lines) if "System Intelligence Suite" in ln]
runs = []
for a, b in zip(heads, heads[1:] + [len(lines)]):
    chunk = "\n".join(lines[a:b])
    verdicts = {}
    for m in re.finditer(r"\[(PASS|FAIL|ENV-BLOCKED)\]\s+([A-Z][A-Z0-9\-]{1,9})\s", chunk):
        verdicts.setdefault(m.group(2), m.group(1))
    sm = re.search(r"SUMMARY[^\n]*", chunk)
    runs.append((lines[a].strip()[-19:], verdicts, sm.group(0) if sm else "(no summary yet)"))

for stamp, v, sm in runs[-3:]:
    print(f"=== section {stamp}  tests={len(v)}  PASS={sum(1 for x in v.values() if x=='PASS')} "
          f"FAIL={sum(1 for x in v.values() if x=='FAIL')} ENV={sum(1 for x in v.values() if x=='ENV-BLOCKED')}")
    print("    " + sm)
    print("    FAIL/ENV: " + ", ".join(f"{k}={x}" for k, x in sorted(v.items()) if x != "PASS"))

if len(runs) >= 2:
    prev, cur = runs[-2][1], runs[-1][1]
    print("\n--- newest vs previous section, test by test")
    print("PASS -> FAIL:  ", sorted(k for k in cur if prev.get(k) == "PASS" and cur[k] == "FAIL") or "none")
    print("PASS -> ENV:   ", sorted(k for k in cur if prev.get(k) == "PASS" and cur[k] == "ENV-BLOCKED") or "none")
    print("-> PASS again: ", sorted(k for k in cur if prev.get(k) != "PASS" and cur[k] == "PASS") or "none")
    print("new tests:     ", sorted(k for k in cur if k not in prev) or "none")
