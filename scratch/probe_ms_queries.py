import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.knowledge import guide_finder as GF
for q in ('Microsoft Notepad user guide', 'Windows 11 Notepad help and support', '"Notepad" Microsoft user manual', 'how to use Notepad in Windows 11 microsoft support', 'Paint app Windows 11 microsoft support'):
    res = GF.search_web(q, GF.default_fetch, 8)
    print("==", q, "->", GF.LAST_PROVIDER, len(res))
    for r in res[:6]:
        print("    ", r["title"][:60].ljust(60), r["url"][:90])
    time.sleep(2)
