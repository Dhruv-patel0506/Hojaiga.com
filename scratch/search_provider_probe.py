"""Why did the host-scoped search find 0 pages? Ask each provider directly and print what came back (results, blocked providers, the reason)."""
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF

for q in ['"AutoCAD" manual help.autodesk.com', "AutoCAD user guide manual documentation", '"AutoCAD" manual site:help.autodesk.com',
          'Tableau Desktop manual help.tableau.com', "Tableau Desktop user guide manual documentation"]:
    res = GF.search_web(q, GF.default_fetch, 8)
    print(f"\nQ: {q}\n   provider now={GF.LAST_PROVIDER!r} blocked={sorted(GF.BLOCKED_PROVIDERS)} results={len(res)}")
    for r in res[:6]:
        print("     -", str(r.get("url", ""))[:110], "|", str(r.get("title", ""))[:60])
