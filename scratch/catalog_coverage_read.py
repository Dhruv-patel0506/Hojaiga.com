"""Honest coverage read on the saved catalogs: how many verbs, how many are NAMED (a label a guide could refer to) vs unnamed, and which sources produced them. Answers 'is the app scanned deeply and fully - all buttons and symbols recognized?'."""
import json
import os
import sys
import collections

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

D = r"d:\new_automation\data\professor\catalogs"
for fn in sorted(os.listdir(D)):
    if not fn.endswith(".json"):
        continue
    d = json.load(open(os.path.join(D, fn), encoding="utf-8"))
    vs = d.get("verbs") or []
    named = [v for v in vs if str(v.get("label") or "").strip()]
    srcs = collections.Counter()
    roles = collections.Counter()
    trust = collections.Counter()
    for v in vs:
        for s in (v.get("sources") or []):
            srcs[s] += 1
        roles[v.get("role") or "?"] += 1
        trust[v.get("trust") or "?"] += 1
    notes = [n for n in (d.get("notes") or []) if str(n).startswith(("uia:", "foreign-window", "symbols", "vision", "ocr"))]
    print(f"\n=== {fn} | verbs={len(vs)} named={len(named)} unnamed={len(vs) - len(named)}")
    print("   sources:", dict(srcs.most_common(10)))
    print("   roles  :", dict(roles.most_common(10)))
    print("   trust  :", dict(trust.most_common(6)))
    print("   notes  :", [str(n)[:90] for n in notes[:6]])
