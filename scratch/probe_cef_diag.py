"""Why did discovery miss? Watch the process, its sockets, and the raw HTTP endpoint."""
import ctypes
import ctypes.wintypes as wt
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import cef_devtools as c                                       # noqa: E402


def _ok(p):
    try:
        s = socket.create_connection(("127.0.0.1", p), 0.5)
        s.close()
        return True
    except Exception:
        return False

page = os.path.join(tempfile.gettempdir(), "hj_cef_page.html")
exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
port = c._free_port()
profile = tempfile.mkdtemp(prefix="hj_cef_")
p = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                      "--no-first-run", "--disable-gpu", page],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
print("pid", p.pid, "port", port)
try:
    for step in range(1, 11):
        time.sleep(2.0)
        rc = p.poll()
        direct = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read().decode() \
            if _ok(port) else ""
        print(f"step{step} poll={rc} alive={rc is None} direct_http={direct[:80]!r}")
        print(f"     listening_ports(pid)={c.listening_ports(p.pid)}")
        if direct:
            tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2).read().decode())
            print("     targets:", [(x.get('type'), (x.get('title') or '')[:24], x.get('url', '')[:40]) for x in tabs][:4])
            break
finally:
    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    time.sleep(1)
    import shutil
    shutil.rmtree(profile, ignore_errors=True)
