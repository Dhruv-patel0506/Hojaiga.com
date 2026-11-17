import sys, time, traceback
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.adapters import cdp, chromium
from core_organs.professor.harvest import Catalog
from core_organs.atlas import scanner as SC
from core_organs import background_window as bw
spec = AR.SPECS["chrome"]; prep = AR._Prep(spec.prep); prep.before()
info = AR.launch(spec, prep); h = int(info.get("hwnd") or 0)
br = cdp.CdpBrowser(info["cdp_port"])
try:
    bg = bw.BackgroundSession(h); bg.__enter__()
    print("alive", br.wait(15))
    ad = chromium.ChromiumAdapter(br, log=print)
    cat = Catalog(app_key="chrome")
    try:
        print(ad.harvest_destinations(cat))
    except Exception:
        traceback.print_exc()
    print("alive after:", br.alive(), [(t["url"], t["title"]) for t in br.targets()][:5])
finally:
    br.close(); bg.__exit__(None, None, None); SC.close_owned(h); prep.after()
