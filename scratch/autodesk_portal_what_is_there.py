"""AutoCAD's docs host has no robots.txt and no sitemap (measured 404). What IS on the page the run did fetch, and does it link anywhere followable?"""
import re
import sys
import urllib.parse

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs.professor.knowledge import guide_finder as GF

for url in ["https://help.autodesk.com/", "https://help.autodesk.com/view/ENU/1", "https://help.autodesk.com/view/AUTOCAD/ENU/"]:
    st, ct, body, fin = GF.default_fetch(url)
    text = (body or b"").decode("utf-8", "replace")
    hrefs = re.findall(r"""href=["']([^"']{2,200})["']""", text, re.I)
    print(f"\n=== {url} -> {st} {ct} {len(body or b'')} B (final {fin})")
    print("   text length after strip:", len(re.sub(r"<[^>]+>", " ", text)))
    print(f"   {len(hrefs)} href(s):")
    for h in hrefs[:18]:
        print("     -", h[:120])
    ids = re.findall(r"(?:data-(?:href|url|id)|productId)\s*=\s*[\"']([^\"']{3,80})[\"']", text, re.I)[:10]
    if ids:
        print("   data-* targets:", ids)
