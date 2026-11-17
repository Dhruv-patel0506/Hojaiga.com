import sys, time, ctypes, ctypes.wintypes as W, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw, fast_uia
from core_organs.atlas import explorer as X
from core_organs import organ_48_app_behavior_model as bm
import uiautomation as auto
u=ctypes.windll.user32
res=[]
def cb(h,_):
    c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
    if c.value=="PPTFrameClass": res.append(h)
    return True
P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
u.EnumWindows(P(cb),0)
h=res[0]
with bw.BackgroundSession(h) as bg:
    u.SetWindowPos(h,0,0,0,2400,900,0x0002|0x0004|0x0010)
    time.sleep(1.0); bg.lay_out(0.8)
    ex=X.Explorer(h,"powerpoint","powerpoint",bm.get_model(),budget_s=120)
    nodes=ex.snap()
    tgt=next(n for n in nodes if n.name=="Paste" and n.ctype=="SplitButtonControl")
    base=ex.popups()
    print(ex.uia(tgt,"GetExpandCollapsePattern","Expand",wait=1.5))
    time.sleep(0.8)
    new=[w for w in ex.popups() if w not in base]
    print("popups",new)
    # 1) main-window tree
    ns=ex.snap()
    items=[n for n in ns if n.ctype in("MenuItemControl","MenuControl") and n.name and n.rect!=(0,0,0,0)]
    print("main tree menu-ish:",len(ns),[(n.ctype[:8],n.name) for n in ns if n.ctype=="MenuControl"])
    # 2) uiautomation walk of the popup
    for w in new:
        c=auto.ControlFromHandle(w)
        print("popup ctrl",c.ControlTypeName,c.Name)
        def walk(ct,d=0):
            if d>5: return
            for k in ct.GetChildren():
                print("  "*d,k.ControlTypeName,repr(k.Name)[:40],k.AutomationId[:25], k.AcceleratorKey)
                walk(k,d+1)
        walk(c)
    # 3) collapse via pattern
    print("collapse",ex.uia(tgt,"GetExpandCollapsePattern","Collapse",wait=1.0))
    time.sleep(0.5)
    print("remaining popups",[w for w in ex.popups() if w not in base])
