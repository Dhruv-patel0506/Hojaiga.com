"""WHY DOES A SEED URL THAT A PERSON WROTE DOWN DIE SILENTLY? Read every seed in the catalog, fetch it, and print what the web actually answered.
A seed is the one source a human vouched for, so when discover ingests nothing the first question is whether the URL is dead, redirected, or refused by a rule of ours."""
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF
from core_organs.professor.knowledge import guide_corpus as GC

CAT = GC.load_catalog()
wanted = [w.lower() for w in (sys.argv[1:] or [])]
for a in CAT:
    seeds = a.get("seeds") or []
    if not seeds or (wanted and not any(w in a["name"].lower() or a["key"].lower() == w for w in wanted)):
        continue
    print(f"\n===== {a['name']} ({a['key']})")
    for s in seeds:
        url = s if isinstance(s, str) else str(s)
        status, ct, body, final = GF.default_fetch(url)
        gate = GF.not_a_user_guide(url)
        ok, why = GF.allowed_host(url)
        print(f"  {url}\n    -> status={status} ct={ct!r} bytes={len(body)} final={final}")
        print(f"    not_a_user_guide={gate}  allowed_host={ok} ({why if isinstance(why, str) else ''})"[:220])
