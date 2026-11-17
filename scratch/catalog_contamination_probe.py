"""Find the FOREIGN verbs in a catalog and show where they came from.

Word's failed run chose 'Address and search bar' as its search box - a Chrome control.
This dumps every entry that does not read like the window under study, with all its
provenance fields, so the writing code path can be identified from the data itself.
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # labels carry RTL marks a cp1252 console cannot print
except Exception:
    pass

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    "d:", os.sep, "new_automation", "data", "professor", "catalogs", "winword.json")

d = json.load(open(PATH, encoding="utf-8"))
verbs = d.get("verbs") or []
print(f"{PATH}\n{len(verbs)} verbs. top-level keys: {sorted(d.keys())}")
meta = {k: v for k, v in d.items() if k not in ("verbs", "regions", "screens")}
print("meta:", json.dumps(meta, ensure_ascii=False)[:900])

OTHER_APP = re.compile(r"(?i)(google chrome|- Firefox|edge\b|notepad\+\+)")
by_src: dict = {}
for v in verbs:
    by_src.setdefault(tuple(sorted(v.get("sources") or ([v["source"]] if v.get("source") else []))), []).append(v)
for k, vs in sorted(by_src.items(), key=lambda x: -len(x[1])):
    print(f"  sources={str(list(k)):<44} n={len(vs)}")

print("\n--- entries naming another application (path or label) ---")
n = 0
for v in verbs:
    blob = json.dumps(v, ensure_ascii=False)
    if OTHER_APP.search(blob):
        n += 1
        if n <= 25:
            print(json.dumps(v, ensure_ascii=False)[:600])
print(f"total foreign-named: {n}")

print("\n--- trust / confidence spread ---")
tz: dict = {}
for v in verbs:
    tz[str(v.get("trust"))] = tz.get(str(v.get("trust")), 0) + 1
print(tz)
print("inferred sample:")
for v in verbs:
    if v.get("trust") == "inferred":
        print(json.dumps(v, ensure_ascii=False)[:400])
        break
