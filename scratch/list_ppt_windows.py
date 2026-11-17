import ctypes, ctypes.wintypes as W
u=ctypes.windll.user32
pid_target=None
out=[]
def cb(h,_):
    pid=W.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    c=ctypes.create_unicode_buffer(128); u.GetClassNameW(h,c,128)
    t=ctypes.create_unicode_buffer(256); u.GetWindowTextW(h,t,256)
    r=W.RECT(); u.GetWindowRect(h,ctypes.byref(r))
    out.append((h,pid.value,c.value,t.value,(r.left,r.top,r.right,r.bottom),bool(u.IsWindowVisible(h)),bool(u.IsIconic(h))))
    return True
P=ctypes.WINFUNCTYPE(ctypes.c_bool,W.HWND,W.LPARAM)
u.EnumWindows(P(cb),0)
import subprocess
pids={int(x) for x in subprocess.run(["powershell","-NoProfile","-Command","(Get-Process POWERPNT -ErrorAction SilentlyContinue).Id"],capture_output=True,text=True).stdout.split()}
for o in out:
    if o[1] in pids: print(o)
