import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.adapters import cdp
from core_organs.atlas import scanner as SC
from core_organs import background_window as bw

spec = AR.SPECS["chrome"]
prep = AR._Prep(spec.prep)
print(prep.before())
info = AR.launch(spec, prep)
h = int(info.get("hwnd") or 0)
print({k: v for k, v in info.items() if k != "trace"})
br = cdp.CdpBrowser(info["cdp_port"])
try:
    bg = bw.BackgroundSession(h); bg.__enter__()
    print("alive:", br.wait(15), br.version().get("Browser"))
    print("targets:", [(t["id"][:6], t["url"], t["title"]) for t in br.targets()])
    ok, how = br.new_tab("chrome://settings/manageProfile"); print("new tab:", ok, how)
    time.sleep(1.5)
    print("targets:", [(t["id"][:6], t["url"][:50], t["title"][:30]) for t in br.targets()])
    pg = br.page(match="manageProfile")
    print("page:", pg.title_url())
    vs = pg.verbs()
    print(len(vs), "verbs")
    for v in vs[:40]:
        print("   ", v["role"].ljust(10), repr(v["label"])[:60], v["state"], v["node"])
    sig0 = pg.ax_signature()
    t0 = time.time()
    ok, how = br.new_tab("chrome://settings/", new_window=False); print("another tab:", ok, how)
    print("close:", br.close_tab())
    print("signature", sig0)
finally:
    br.close()
    bg.__exit__(None, None, None)
    print("close", SC.close_owned(h))
    print("prep after", prep.after())
