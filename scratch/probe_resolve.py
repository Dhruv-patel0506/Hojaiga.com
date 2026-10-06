import sys, os, json
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import universal_scan as l
for n in sys.argv[1:]:
    try:
        r = l.resolve_app(n) if hasattr(l, "resolve_app") else None
    except Exception as e:
        r = repr(e)
    print(n, "->", str(r)[:300])
print([x for x in dir(l) if "resolve" in x.lower() or "find" in x.lower()][:20])
