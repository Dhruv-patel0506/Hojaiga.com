"""cdp_blacktab_probe.py -- prove the CDP web automation + the floating capsule /
'black tab' HITL overlay actually work on a LIVE page.

It does NOT trust any in-process shortcut: it launches the SAME isolated automation
Chrome organ_40 uses (temp profile, --remote-debugging-port=9222), opens a real page
over the CDP HTTP endpoint, then talks to that tab over a raw DevTools websocket,
injects organ_19's real _OVERLAY_SOURCE + _BLACK_TAB_SOURCE, and reads the DOM back to
confirm (1) the capsule node exists, (2) window.__hojaigaSetCapsule is defined and
shows the capsule, and (3) the __HITL_PAUSED / __HITL_STOP flags are set. Cleans up the
Chrome instance it started. Read-only w.r.t. the rest of the machine.
"""
import os, sys, json, time, urllib.request, subprocess, tempfile, glob

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_19_chrome_cdp_runtime import AutomationOverlayEngine as OVE

PORT = 9222
PROFILE = os.path.join(tempfile.gettempdir(), "chrome_automation_9222")


def _chrome_exe():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            return p
    g = glob.glob(os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"))
    return g[0] if g else None


def _http(path, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method)
    return urllib.request.urlopen(req, timeout=5).read().decode()


def main():
    exe = _chrome_exe()
    assert exe, "chrome.exe not found"
    proc = subprocess.Popen([
        exe, f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "--profile-directory=Default", "--no-first-run", "--no-default-browser-check",
        "--disable-extensions", "--disable-sync", "--mute-audio",
        "about:blank",
    ])
    new = None
    try:
        # wait for the DevTools endpoint
        tabs = None
        for _ in range(40):
            try:
                tabs = json.loads(_http("/json/version")); break
            except Exception:
                time.sleep(0.5)
        assert tabs and tabs.get("Browser"), f"CDP endpoint never answered: {tabs}"
        print("CDP browser:", tabs.get("Browser"), "| Protocol:", tabs.get("Protocol-Version"))

        # open a real page in its own tab
        new = json.loads(_http("/json/new?https://example.com", method="PUT"))
        ws_url = new["webSocketDebuggerUrl"]
        print("opened tab:", new.get("url") or new.get("title"), "->", ws_url[:60], "...")

        import websocket
        ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
        _id = 0

        def send(method, params=None):
            nonlocal _id
            _id += 1
            ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == _id:
                    return msg

        def ev(expr):
            r = send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
            return r.get("result", {}).get("result", {}).get("value")

        time.sleep(1.5)  # let example.com load
        send("Page.enable"); send("Runtime.enable")

        # inject organ_19's REAL overlay + black-tab sources exactly as the runtime does
        send("Runtime.evaluate", {"expression": OVE._OVERLAY_SOURCE})
        send("Runtime.evaluate", {"expression": OVE._BLACK_TAB_SOURCE})

        checks = {
            "capsule_node_present": ev("!!document.getElementById('hojaiga-capsule')"),
            "setCapsule_defined": ev("typeof window.__hojaigaSetCapsule"),
            "hitl_paused_defined": ev("typeof window.__HITL_PAUSED"),
            "hitl_stop_defined": ev("typeof window.__HITL_STOP"),
        }
        # drive the capsule into its 'working' state and confirm it becomes visible
        ev("window.__hojaigaSetCapsule && window.__hojaigaSetCapsule('working','CDP black-tab probe')")
        checks["capsule_shown"] = ev(
            "document.getElementById('hojaiga-capsule').classList.contains('hj-show')")
        checks["capsule_text"] = ev(
            "(document.getElementById('hojaiga-capsule-text')||{}).textContent")

        print("\n===== CDP OVERLAY / BLACK-TAB RESULT =====")
        ok = True
        for k, v in checks.items():
            print(f"  {k:22s} = {v}")
            if k == "setCapsule_defined" and v != "function": ok = False
            if k == "capsule_node_present" and not v: ok = False
            if k == "capsule_shown" and not v: ok = False
            if k in ("hitl_paused_defined", "hitl_stop_defined") and v != "boolean": ok = False
        # confirm the HITL stop control actually flips the flags (the black-tab contract)
        ev("document.querySelector('#hojaiga-capsule .hj-stop').click()")
        stopped = ev("window.__HITL_STOP===true && window.__HITL_PAUSED===true")
        print(f"  {'stop_btn_sets_hitl':22s} = {stopped}")
        ok = ok and bool(stopped)
        print("\nVERDICT:", "CDP + capsule/black-tab WORK on a live page" if ok else "CHECK ABOVE")
        ws.close()
        return 0 if ok else 1
    finally:
        # close only the Chrome we started (isolated profile), leaving the user's browser untouched
        try:
            if new:
                _http("/json/close/" + new["id"])
        except Exception:
            pass
        try:
            proc.terminate(); proc.wait(timeout=6)
        except Exception:
            try: proc.kill()
            except Exception: pass


if __name__ == "__main__":
    sys.exit(main())
