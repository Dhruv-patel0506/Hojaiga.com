import sys, time
sys.path[:0] = ["D:/new_automation/scratch"]
from probe_bing2 import bing
for q in ("site:docs.blender.org manual", "site:obsproject.com documentation guide", "blender manual filetype:pdf", "site:github.com inurl:wiki obs-studio"):
    code, res = bing(q)
    print(f"== {q[:50]:50s} HTTP {code}: {len(res)} results")
    for t, u in res[:6]:
        print("    ", t[:50].ljust(50), u[:90])
    time.sleep(2.0)
