"""Is GetExtendedTcpTable working, and WHO owns the Chrome debug socket? Print every listener on the port and
the process tree of the launched browser."""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import cef_devtools as c                                       # noqa: E402


def all_listeners():
    class Row(ctypes.Structure):
        _fields_ = [("state", wt.DWORD), ("local_addr", wt.DWORD), ("local_port", wt.DWORD),
                    ("remote_addr", wt.DWORD), ("remote_port", wt.DWORD), ("pid", wt.DWORD)]
    size = wt.DWORD(0)
    r0 = ctypes.windll.iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 3, 0)
    buf = ctypes.create_string_buffer(size.value)
    size2 = wt.DWORD(size.value)
    r1 = ctypes.windll.iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size2), False, 2, 3, 0)
    n = ctypes.cast(buf, ctypes.POINTER(wt.DWORD)).contents.value
    rows = ctypes.cast(buf, ctypes.POINTER(Row * max(1, n))).contents
    return r0, r1, n, [(socket_ntohs(rows[i].local_port), rows[i].pid, hex(rows[i].local_addr)) for i in range(n)]


def socket_ntohs(v):
    return int(ctypes.c_ushort(((v & 0xFF) << 8) | ((v >> 8) & 0xFF)).value)


def tree(pid):
    """(pid, ppid, name) for every process, so the browser root and its children are visible."""
    class Entry32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("th32ProcessID", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32PriorityRank", wt.DWORD), ("th32ParentPID", wt.DWORD),
                    ("th32ThreadID", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e = Entry32()
    e.dwSize = ctypes.sizeof(Entry32)
    out = []
    if k32.Process32First(snap, ctypes.byref(e)):
        while True:
            out.append((int(e.th32ProcessID), int(e.th32ParentPID), e.szExeFile.decode("utf8", "replace")))
            if not k32.Process32Next(snap, ctypes.byref(e)):
                break
    k32.CloseHandle(snap)
    return out


page = tempfile.mktemp(suffix=".html")
open(page, "w").write("<html><body><button>hi</button></body></html>")
exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
port = c._free_port()
profile = tempfile.mkdtemp(prefix="hj_cef_")
p = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                      "--no-first-run", "--disable-gpu", page],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
time.sleep(4)
r0, r1, n, rows = all_listeners()
print(f"GetExtendedTcpTable: first={r0} second={r1} rows={n} poll={p.poll()}")
print("rows on our port:", [r for r in rows if r[0] == port])
print("all listener pids:", sorted({r[1] for r in rows})[:12])
print("module says:", c.listening_ports(p.pid), "for launched pid", p.pid)
procs = tree(p.pid)
print("process count seen:", len(procs))
mine = [t for t in procs if "chrome" in t[2].lower()]
print("chrome processes (pid,ppid) sample:", mine[:8])
roots = [t for t in mine if t[0] == p.pid or t[1] == p.pid]
print("ours:", roots)
for cand in [p.pid] + [t[0] for t in mine if t[1] == p.pid or t[0] == p.pid]:
    print("  pid", cand, "listeners ->", c.listening_ports(cand), "port_owner" if port in c.listening_ports(cand) else "")
print("any pid owning our port:", [r for r in rows if r[0] == port])
print("DevToolsActivePort in profile?", os.path.exists(os.path.join(profile, "DevToolsActivePort")),
      open(os.path.join(profile, "DevToolsActivePort")).read().replace("\n", "|") if os.path.exists(os.path.join(profile, "DevToolsActivePort")) else "")
subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
time.sleep(1)
import shutil                                                                # noqa: E402
shutil.rmtree(profile, ignore_errors=True)
