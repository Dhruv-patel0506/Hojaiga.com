import sys, re
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_finder as GF

url = sys.argv[1]
st, ct, body, final = GF.default_fetch(url)
print("status", st, ct, len(body or b""), "final", final)
txt = body.decode("utf-8", "ignore") if isinstance(body, bytes) else (body or "")
links = GF.extract_links(txt, final or url) if hasattr(GF, "extract_links") else []
print("links:", len(links))
for l in links[:40]:
    print("  ", l if isinstance(l, str) else l)
print([n for n in dir(GF) if "link" in n.lower() or "crawl" in n.lower() or "rx" in n.lower()][:30])
