import sys, time, ctypes, ctypes.wintypes as W
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import fast_uia
import uiautomation as auto
u=ctypes.windll.user32
res=[]
def cb(h,_):
    c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
    if c.value=="PPTFrameClass": res.append(h)
    return True
P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
u.EnumWindows(P(cb),0)
print(res)
for h in res:
    nodes=fast_uia.snapshot(h,timeout_ms=8000) or []
    btn=[n for n in nodes if n.ctype=="ButtonControl" and n.name=="Yes"]
    print("yes buttons",len(btn))
    if btn:
        pat=btn[0].ctrl.GetInvokePattern(); pat.Invoke()
        time.sleep(2)
print("alive",[bool(u.IsWindow(h)) for h in res])
