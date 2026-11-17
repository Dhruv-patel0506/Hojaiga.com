"""Who wrote the foreign verbs? Group them by path / provenance and show the catalog's own source ledger."""
import json
import os
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

P = r"d:\new_automation\data\professor\catalogs\winword.json"
d = json.load(open(P, encoding="utf-8"))
print("catalog sources ledger:", json.dumps(d.get("sources"), ensure_ascii=False)[:1200])
print("notes:", json.dumps(d.get("notes"), ensure_ascii=False)[:800])
print("status_texts:", json.dumps(d.get("status_texts"), ensure_ascii=False)[:300])
print("created:", d.get("created"), "seconds:", d.get("seconds"))

FOREIGN = re.compile(r"(?i)(google chrome|- Firefox| - Microsoft Edge|notepad\+\+)")
forie = [v for v in d["verbs"] if FOREIGN.search(json.dumps(v, ensure_ascii=False))]
print(f"\n{len(forie)} foreign entries")
print("paths:", Counter(tuple(str(x)[:40] for x in v.get("path") or []) for v in forie).most_common(8))
print("roles:", Counter(v.get("role") for v in forie).most_common())
print("trust:", Counter(v.get("trust") for v in forie).most_common())
print("shortcuts present:", sum(1 for v in forie if v.get("shortcut")))
print("aids sample:", [v.get("aid") for v in forie[:12]])

# the two legit Word search fields vs the foreign one, in catalog ORDER (order decides the pick)
SRX = re.compile(r"(?i)\bsearch\b")
FLD = ("edit", "document", "combo", "combobox", "dropdown", "search", "text", "spinbutton", "field", "text_field")
print("\nsearch-named entries in catalog order (first field-role one wins the pick):")
for i, v in enumerate(d["verbs"]):
    if v.get("enabled") and SRX.search(v.get("label") or "") and (
            (v.get("role") or "").lower() in FLD or "search" in " ".join(v.get("path") or []).lower()
            or (v.get("role") or "").lower() in ("button", "dropdown")):
        print(f"  #{i} role={v.get('role'):<10} src={v.get('sources')} trust={v.get('trust'):<20} "
              f"path={' > '.join(str(x)[:34] for x in (v.get('path') or []))} | {(v.get('label') or '')[:46]}")
