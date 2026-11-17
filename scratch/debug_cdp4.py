import sys, time, traceback, re
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.adapters import cdp, chromium
from core_organs.atlas import scanner as SC
from core_organs import background_window as bw
spec = AR.SPECS["chrome"]; prep = AR._Prep(spec.prep); prep.before()
info = AR.launch(spec, prep); h = int(info.get("hwnd") or 0)
br = cdp.CdpBrowser(info["cdp_port"])
try:
    bg = bw.BackgroundSession(h); bg.__enter__()
    br.wait(15)
    br.new_tab("chrome://chrome-urls/"); time.sleep(1.5)
    tg = next(x for x in br.targets() if "chrome-urls" in x["url"])
    pg = cdp.CdpPage(tg); br.pages[tg["id"]] = pg
    time.sleep(1.0)
    urls = sorted({v["label"].split("#")[0].rstrip("/") + "/" for v in pg.verbs(limit=500) if v["ax_role"] == "link" and v["label"].startswith("chrome://")})
    br.close_tab(tg["id"])
    urls = [u for u in urls if not chromium.DANGEROUS_PAGES.search(u) and not re.search(r"internals|-debug", u) and u.count("/") <= 3]
    print(len(urls), "urls")
    for u in urls:
        if not br.alive():
            print("BROWSER DIED before", u); break
        print("open", u, flush=True)
        ok, how = br.new_tab(u); time.sleep(0.5)
        tg = next((x for x in br.targets() if x["url"].rstrip("/") == u.rstrip("/")), None)
        if tg: br.close_tab(tg["id"])
finally:
    br.close(); bg.__exit__(None, None, None); SC.close_owned(h); prep.after()
