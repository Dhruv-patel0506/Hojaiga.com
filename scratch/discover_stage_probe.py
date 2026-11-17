"""Run the finder for the apps that still have no guide and print EVERY stage: sources tried, the reason each was skipped, the doc-host probe result."""
import json
import sys
import time

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF
from core_organs.professor.knowledge import manual_rag as MR

from core_organs.professor.knowledge import guide_corpus as GC
CAT = GC.load_catalog()
names = sys.argv[1:] or ["AutoCAD", "Tableau Desktop"]
ix = MR.ManualIndex()

for name in names:
    a = next((x for x in CAT if x["name"].lower() == name.lower() or name.lower() in x["name"].lower()), None)
    if a is None:
        print(f"{name}: not in the catalog")
        continue
    ident = GF.AppIdentity(app_key=a["key"], product=a["name"], company=a.get("company", ""), process=(a.get("processes") or [""])[0])
    fch = GF.default_fetch
    rob = GF.Robots(fch)
    srcs, note = GF.official_sources(ident, fch, rob, seeds=a.get("seeds", []))
    print(f"\n===== {a['name']} ({a['key']}) | company={a.get('company')!r} | seeds={a.get('seeds')}")
    print(f"official_sources -> {len(srcs)}  note={json.dumps(note, ensure_ascii=False)[:300]}")
    for s in srcs[:10]:
        print("   ", json.dumps(s, ensure_ascii=False)[:170])
    r = GF.discover(ident, ix, web=True, budget_s=180.0, force=True, max_pages=25, max_depth=2,
                    seeds=a.get("seeds", []), max_queries=3, sources_wanted=4, want_docs=12)
    print(f"discover: {len(r.get('ingested') or [])} ingested, error={r.get('error')!r}, coverage={str(r.get('coverage'))[:120]}")
    for t in r.get("tiers") or []:
        fnd = t.get("found")
        cands = fnd if isinstance(fnd, list) else (t.get("candidates") or [])
        n = fnd if isinstance(fnd, int) else len(cands)
        print(f"  tier {t.get('did')}: found={n} " +
              json.dumps([{k: v for k, v in f.items() if k in ('url', 'kind', 'ok', 'why', 'status')} for f in cands][:6], ensure_ascii=False)[:700])
    print("  skipped:")
    for s in (r.get("skipped") or [])[:14]:
        print("     -", str(s)[:220])
