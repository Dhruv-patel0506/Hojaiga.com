"""Does the parent host of a dead documentation sub-domain actually publish its index? Measured: docs.videolan.org does not resolve at all, while www.videolan.org answers a reader 200
and its robots.txt names a sitemap. This prints what that sitemap holds before any rule is written, so the walk-up door is built on what the host really offers."""
import re
import sys
import urllib.parse

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF

for root in ("https://www.videolan.org", "https://videolan.org"):
    st, ct, body, fin = GF.default_fetch(root + "/robots.txt")
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", body.decode("utf-8", "replace")) if st == 200 else []
    print(f"\n{root} robots -> {st}  sitemap lines: {maps}")
    for m in (maps or [root + "/sitemap.xml"]):
        st2, ct2, b2, _f2 = GF.default_fetch(m, max_bytes=6_000_000)
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", b2.decode("utf-8", "replace"))
        docish = [l for l in locs if GF._DOCISH_PATH.search(urllib.parse.urlsplit(l).path)]
        print(f"  {m} -> {st2}  {len(locs)} <loc>, docish {len(docish)}")
        for l in docish[:12]:
            print("      ", l)
