import sys, time, ctypes, ctypes.wintypes as W, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw, fast_uia
from core_organs.atlas import explorer as X
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
print("hwnd",h,"min",bw.is_minimized(h),"rect",bw._rect(h))
with bw.BackgroundSession(h) as bg:
    print("mode",bg.mode, bw._rect(h))
    # widen
    r=bw._rect(h); print("rect parked",r)
    u.SetWindowPos(h,0,0,0,2400,900,0x0002|0x0004|0x0010)  # NOMOVE|NOZORDER|NOACTIVATE
    time.sleep(1.0)
    bg.lay_out(0.8)
    print("after widen", bw._rect(h))
    ex=X.Explorer(h,"powerpoint","powerpoint",bm.get_model(),budget_s=120)
    nodes=ex.snap()
    print("nodes",len(nodes))
    groups=[n for n in nodes if n.ctype=="GroupControl" and n.name]
    print([g.name for g in groups])
    # try to expand 'Paste' split button
    tgt=next(n for n in nodes if n.name=="Paste" and n.ctype=="SplitButtonControl")
    base=ex.popups()
    t=time.time()
    print(ex.uia(tgt,"GetExpandCollapsePattern","Expand",wait=1.5))
    for i in range(10):
        time.sleep(0.15)
        new=[w for w in ex.popups() if w not in base]
        if new: break
    print("popups",new,time.time()-t)
    for w in new:
        ns=ex.snap(w,ms=3000)
        print("popup",w,bm._win_class(w),len(ns))
        for n in ns[:60]:
            print("   ",n.ctype.replace("Control",""),repr(n.name)[:40],n.aid[:25],sorted(n.pats),n.accel)
    if not new:
        ns=ex.snap(); 
        idx=[n for n in ns if n.name=="Paste" and n.ctype=="SplitButtonControl"]
        print("inline? children:",[ (c.ctype,c.name) for c in ns if idx and c.parent==idx[0].idx])
        print([ (n.ctype,n.name) for n in ns if n.ctype in("MenuItemControl","ListItemControl") and n.rect!=(0,0,0,0)][:40])
    print("closed:",ex.close_surfaces(base))
