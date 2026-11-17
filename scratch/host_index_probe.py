"""What does a host that refused us actually offer? Ask robots.txt and the sitemap paths with BOTH reader identities and print the raw answer.
The gate that killed the empty-guide applications was never "this application has no manual" - it was one page not answering. This checks whether the host index exists at all,
so the decision (sitemap door / seed walk-up / give up honestly) is made on a measurement and not on a guess."""
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF

URLS = [
    "https://getsharex.com/robots.txt",
    "https://getsharex.com/sitemap.xml",
    "https://www.mathworks.com/robots.txt",
    "https://www.mathworks.com/sitemap.xml",
    "https://www.mathworks.com/help/matlab/",
    "https://docs.videolan.org/",
    "https://www.videolan.org/robots.txt",
    "https://www.videolan.org/doc/",
    "https://help.autodesk.com/robots.txt",
    "https://skype.com",
]
for u in URLS:
    a = GF._fetch_once(u, GF.UA, 15.0, 2_000_000)
    b = GF._fetch_once(u, GF.UA_READER, 15.0, 2_000_000)
    txt = (b[2] or a[2]).decode("utf-8", "replace")
    print(f"\n{u}\n  declared-agent -> {a[0]} {a[1]!r} {len(a[2])} B   |  reader -> {b[0]} {b[1]!r} {len(b[2])} B")
    print("  first 300 chars: " + " ".join(txt.split())[:300])
