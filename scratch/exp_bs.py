import sys, time, ctypes, ctypes.wintypes as W, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw, fast_uia
from core_organs.atlas import explorer as X, uimap
from core_organs import organ_48_app_behavior_model as bm
u=ctypes.windll.user32
res=[]
def cb(h,_):
    c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
    if c.value=="PPTFrameClass": res.append(h)
    return True
P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
u.EnumWindows(P(cb),0)
h=res[0]
m=json.load(open(r"D:\new_automation\data\atlas\uimap\app.json",encoding="utf-8"))
ins=[s for s in m["surfaces"] if s["id"]=="tab:Insert"][0]
for g in ins["groups"]:
    for c in g["controls"]:
        if c["name"] in("Shapes","Screenshot","3D Models"): print(c["name"],"enabled",c["enabled"],"offscreen",c["offscreen"])
with bw.BackgroundSession(h) as bg:
    ex=X.Explorer(h,"app","app",bm.get_model(),budget_s=200)
    ca=uimap.Cartographer(ex,budget_s=200)
    ca.widen()
    nodes=ca.settle(3)
    strip,items=ca.tab_strips(nodes)[0]
    ins_t=next(i for i in items if i.name=="Insert")
    print("select",ex.uia(ins_t,"GetSelectionItemPattern","Select",wait=1.2)); time.sleep(0.6)
    nodes=ca.settle(3)
    sm=next(n for n in nodes if n.name=="SmartArt..." )
    print("smartart node",sm.rect,sm.enabled,sm.offscreen,sm.pats)
    rec=ex.probe_opener(sm)
    print("REC",rec)
    # backstage
    fb=ca.file_button(nodes,strip)
    print("file button",fb.name,fb.aid,fb.pats)
    wins_before=set(ex.hin.process_windows(h,include_hidden=True))
    before=ex.snap()
    print(ex.uia(fb,"GetInvokePattern","Invoke",wait=1.5)); time.sleep(1.5)
    wins_after=set(ex.hin.process_windows(h,include_hidden=True))
    print("new windows",[(w,bm._win_class(w),bm._win_title(w)) for w in wins_after-wins_before])
    after=ex.snap()
    new=ca._new_nodes(before,after)
    print("new nodes",len(new))
    for n in new[:50]: print("  ",n.depth,n.ctype.replace("Control",""),repr(n.name)[:40],n.aid[:25],sorted(n.pats),n.rect)
    # leave
    back=next((n for n in after if n.name=="Back"),None)
    print("back",back is not None, ex.uia(back,"GetInvokePattern","Invoke",wait=1.5) if back else None)
