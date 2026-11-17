import sys, time, ctypes, ctypes.wintypes as W, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw
from core_organs.atlas import explorer as X, uimap
from core_organs import organ_48_app_behavior_model as bm
u=ctypes.windll.user32
cls=sys.argv[1]; budget=float(sys.argv[2]); only=sys.argv[3] if len(sys.argv)>3 else ""
res=[]
def cb(h,_):
    c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
    if c.value==cls: res.append(h)
    return True
P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
u.EnumWindows(P(cb),0)
h=res[0]
t=time.time()
with bw.BackgroundSession(h) as bg:
    ex=X.Explorer(h,"app","app",bm.get_model(),budget_s=budget)
    ca=uimap.Cartographer(ex,budget_s=budget,log=print)
    m=ca.run()
    p=ca.save()
print("seconds",round(time.time()-t,1),"applicable",m.get("applicable"),"widen",m.get("widen"))
print(ca.stats)
for s in m["surfaces"]:
    n=sum(len(g["controls"]) for g in s["groups"])
    print(s["id"],"groups",len(s["groups"]),"controls",n)
print(p)
