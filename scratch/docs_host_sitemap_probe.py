"""Is there an environment-independent door into a documentation host we cannot crawl from its root? robots.txt's Sitemap: line and /sitemap.xml are universal. Measure it on the hosts that ended with an empty guide."""
import re
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF

HOSTS = ["help.autodesk.com", "help.tableau.com", "docs.videolan.org", "learn.microsoft.com", "docs.blender.org", "obsproject.com", "support.discord.com"]
for h in HOSTS:
    for path in ("/robots.txt", "/sitemap.xml", "/sitemap_index.xml"):
        url = f"https://{h}{path}"
        st, ct, body, _f = GF.default_fetch(url)
        text = (body or b"").decode("utf-8", "replace")
        sm = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", text)
        locs = re.findall(r"<loc>\s*([^<\s]{10,300})\s*</loc>", text)[:6]
        note = f"{st} {ct[:22]:<22} {len(body or b''):>8} B"
        if sm:
            note += "  SITEMAP LINES: " + ", ".join(sm[:4])
        if locs:
            note += "  ENTRIES: " + " | ".join(locs[:3])
        print(f"{url:<44} {note[:300]}")
    print()
