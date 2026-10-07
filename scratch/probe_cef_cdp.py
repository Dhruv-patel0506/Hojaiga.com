"""Prove the CDP transport end-to-end on a page we control (headless, so nothing lands on the desktop):
discover the port, attach, perceive elements, click, type, screenshot, and read the page back."""
import os
import sys
import tempfile
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import cef_devtools as c                                       # noqa: E402

HTML = """<!doctype html><html><body style="margin:0">
<h1 id=t>count 0</h1>
<button id=b onclick="window.n=(window.n||0)+1;document.getElementById('t').textContent='count '+window.n">Bump</button>
<input id=i placeholder="type here" style="width:220px;height:34px">
<div id=echo></div>
<script>document.getElementById('i').addEventListener('input',e=>{document.getElementById('echo').textContent='echo '+e.target.value});</script>
</body></html>"""

page = os.path.join(tempfile.gettempdir(), "hj_cef_page.html")
with open(page, "w", encoding="utf-8") as fh:
    fh.write(HTML)

exe = c.resolve_chromium_exe(r"C:\Program Files\Google\Chrome\Application\chrome.exe") or \
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
print("exe", exe, "family:", c.is_chromium_exe(exe))
pid, port, profile = c.launch_with_devtools(exe, ["--headless=new", "--disable-gpu", page])
print("launched pid", pid, "port", port)
try:
    t0 = time.time()
    found = c.devtools_port(pid, timeout=25)
    print(f"devtools_port(pid) -> {found} (same as launch port: {found == port}) in {time.time()-t0:.1f}s")
    dt = c.DevTools.attach(pid, timeout=5)
    print("attach:", "OK" if dt else "NONE", getattr(dt, "target", {}).get("url", "")[:60] if dt else c.DevTools.last_attach_error if hasattr(c.DevTools, "last_attach_error") else "")
    if dt:
        els = c.page_elements(dt)
        print("title:", els.get("title"), "| viewport:", els.get("vw"), els.get("vh"), "| elements:", len(els.get("elements", [])))
        for e in els.get("elements", [])[:6]:
            print(f"   {e['tag']:<8} id={e['id']:<6} name={e['name'][:22]!r:<24} box=({e['x']:.0f},{e['y']:.0f}) {e['w']:.0f}x{e['h']:.0f} editable={e['editable']}")
        btn = next((e for e in els.get("elements", []) if e["id"] == "b"), None)
        fld = next((e for e in els.get("elements", []) if e["id"] == "i"), None)
        if btn:
            print("click_at ->", c.click_at(dt, btn["x"], btn["y"]))
            print("read back h1:", dt.evaluate("document.getElementById('t').textContent"))
        if fld:
            c.click_at(dt, fld["x"], fld["y"])
            print("type_text ->", c.type_text(dt, "hello cef"))
            print("field value:", dt.evaluate("document.getElementById('i').value"))
            print("page reacted:", dt.evaluate("document.getElementById('echo').textContent"))
        print("press Enter ->", c.press_key(dt, "enter"))
        png = c.screenshot_png(dt)
        print("screenshot bytes:", len(png), "png magic:", png[:4] == b"\x89PNG")
        if png:
            with open(r"D:\new_automation\_cef_shot.png", "wb") as fh:
                fh.write(png)
        print("last_error:", dt.last_error)
        dt.close()
finally:
    try:
        import subprocess
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    except Exception as e:
        print("kill failed", e)
    if profile:
        import shutil
        shutil.rmtree(profile, ignore_errors=True)
print("done")
