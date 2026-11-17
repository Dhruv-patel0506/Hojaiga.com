"""PR40 fails only on 'test_never_reached_the_internet'. Reproduce the discovery call and print WHICH url tried to leave the local test site, plus the new tiers."""
import json
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import core_organs.si_tests_professor as S
from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR

site = S._DocSite()
old = (GF.GUIDE_DIR, GF.FETCH_LOG)
GF.GUIDE_DIR, GF.FETCH_LOG = S._tmp("guides_dbg"), S._tmp("fetchlog_dbg") + ".tsv"
ix = MR.ManualIndex(S._tmp("dork_ix_dbg") + ".db")
try:
    ident = GF.AppIdentity(app_key="atlasapp3", product='Atlas "App"', company="127", process="AtlasApp.exe", description="Atlas App Desktop")

    def stub(q):
        if "filetype:pdf" in q:
            return [{"url": site.base + "/docs/guide.pdf", "title": "Atlas App User Manual"}, {"url": "https://www.youtube.com/watch?v=1", "title": "Atlas App tutorial"}]
        if "inurl:docs" in q:
            return [{"url": site.base + "/docs/index.html", "title": "Atlas App documentation"}, {"url": site.base + "/docs/guide.pdf", "title": "Atlas App User Manual"}]
        if "site:github.com" in q:
            return [{"url": "https://github.com/acme/atlas/wiki/Home", "title": "Home - acme/atlas wiki"}, {"url": "https://reddit.com/r/x", "title": "atlas help?"}]
        print("  stub saw a NEW query shape:", q[:120])
        return []

    external = []

    def local_only(url):
        if "127.0.0.1" not in url:
            external.append(url)
            return 0, "", b"", url
        return GF.default_fetch(url)

    rep = GF.discover(ident, ix, web=True, fetch=local_only, search=stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)
    print("EXTERNAL ATTEMPTS:", json.dumps(external[:12]))
    for t in rep["tiers"]:
        print("  tier:", json.dumps(t, ensure_ascii=False)[:300])
    print("  skipped:", [str(x)[:120] for x in (rep.get("skipped") or [])][:12])
finally:
    site.close()
    GF.GUIDE_DIR, GF.FETCH_LOG = old
    ix.close()
