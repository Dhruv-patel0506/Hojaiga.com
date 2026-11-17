import sys, ctypes, ctypes.wintypes as W
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import fast_uia
u=ctypes.windll.user32
res=[]
def cb(h,_):
    if u.IsWindowVisible(h) or True:
        pid=W.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
        c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
        t=ctypes.create_unicode_buffer(256); u.GetWindowTextW(h,t,256)
        if c.value=="PPTFrameClass": res.append((h,t.value))
    return True
P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
u.EnumWindows(P(cb),0)
print(res)
h=res[0][0]
nodes=fast_uia.snapshot(h,timeout_ms=8000)
print(len(nodes))
for n in nodes[:400]:
    print("  "*min(n.depth,12), n.idx, n.ctype.replace("Control",""), ascii(n.name)[:40], n.aid[:24], sorted(n.pats))
