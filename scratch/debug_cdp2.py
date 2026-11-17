import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.adapters import cdp
from core_organs.atlas import scanner as SC
from core_organs import background_window as bw
spec = AR.SPECS["chrome"]; prep = AR._Prep(spec.prep); prep.before()
info = AR.launch(spec, prep); h = int(info.get("hwnd") or 0)
br = cdp.CdpBrowser(info["cdp_port"])
try:
    bg = bw.BackgroundSession(h); bg.__enter__()
    br.wait(15)
    ok, how = br.new_tab("chrome://chrome-urls/"); time.sleep(2)
    print([(t["url"], t["title"]) for t in br.targets()])
    pg = br.page(match="chrome-urls")
    vs = pg.verbs(); print(len(vs), [(v["role"], v["label"]) for v in vs][:30])
    r = pg.call("Runtime.evaluate", {"expression": "document.body ? document.body.innerText.slice(0,400) : 'nobody'", "returnByValue": True}); print(r.get("result", {}).get("value"))
    r = pg.call("Runtime.evaluate", {"expression": "(function(){var out=[];function walk(n){ if(n.querySelectorAll){ n.querySelectorAll('a').forEach(a=>out.push(a.href)); n.querySelectorAll('*').forEach(e=>{ if(e.shadowRoot) walk(e.shadowRoot); }); } } walk(document); return out;})()", "returnByValue": True}); print(r.get("result", {}).get("value")[:15] if r.get("result", {}).get("value") else r)
finally:
    br.close(); bg.__exit__(None, None, None); SC.close_owned(h); prep.after()
