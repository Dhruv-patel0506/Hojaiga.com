import sys, time, ctypes, ctypes.wintypes as W
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw, fast_uia
from core_organs.atlas import explorer as X, uimap
from core_organs import organ_48_app_behavior_model as bm
u=ctypes.windll.user32
def frames():
    res=[]
    def cb(h,_):
        c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
        if c.value=="PPTFrameClass":
            t=ctypes.create_unicode_buffer(256); u.GetWindowTextW(h,t,256)
            r=W.RECT(); u.GetWindowRect(h,ctypes.byref(r))
            res.append((h,t.value,(r.left,r.top,r.right,r.bottom),bool(u.IsWindowVisible(h)),bool(u.IsIconic(h))))
        return True
    P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
    u.EnumWindows(P(cb),0)
    return res
print(frames())
h=frames()[0][0]
with bw.BackgroundSession(h) as bg:
    ex=X.Explorer(h,"app","app",bm.get_model(),budget_s=100)
    nodes=ex.snap()
    print("nodes",len(nodes),[n.name for n in nodes if n.ctype=="ListItemControl"][:3])
    tgt=next((n for n in nodes if n.name=="Blank Presentation"),None)
    print("blank?",tgt is not None)
    if tgt:
        print(ex.uia(tgt,"GetInvokePattern","Invoke",wait=1.5))
        t0=time.time()
        last=None
        while time.time()-t0<8:
            f=frames()
            if f!=last: print(round(time.time()-t0,1),f); last=f
            time.sleep(0.25)
