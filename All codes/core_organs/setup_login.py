"""
setup_login.py — Hojaiga isolated login, runs ONLY when Chrome needed and no session cookie in DB.
Uses CDP directly (no undetected_chromedriver dependency).
Usage: from core_organs.setup_login import ensure_login
       ensure_login(app="gmail.com", profile_path=r"C:\automation_profile")
"""
import os
import time
import json
import sys
import subprocess
import socket
import struct

try:
    from core_organs.database_manager import DatabaseManager
    _HAS_DB = True
except Exception:
    _HAS_DB = False

def _has_session_cookie(site: str) -> bool:
    if not _HAS_DB:
        return False
    db = DatabaseManager()
    def _q(conn):
        cur = conn.cursor()
        cur.execute("SELECT cookies_json FROM session_cookies WHERE site=?", (site.lower(),))
        row = cur.fetchone()
        return row is not None and row[0]
    res = db._safe_call(_q)
    return bool(res)

def _store_session_cookies(site: str, cookies: list):
    if not _HAS_DB:
        return
    db = DatabaseManager()
    db.store_session_cookies(site.lower(), cookies)

def _cdp_send(ws_conn, opcode, payload, cmd_id=1):
    """Send a CDP command via IPC socket to organ_19 CDP runtime."""
    b = json.dumps(payload).encode()
    f = struct.pack('>H', opcode) + b
    ws_conn.sendall(struct.pack('>I', len(f)) + f)
    hdr = ws_conn.recv(4)
    tot = struct.unpack('>I', hdr)[0]
    d = b''
    while len(d) < tot:
        d += ws_conn.recv(tot - len(d))
    return json.loads(d[2:].decode())

def _extract_cookies_via_cdp(chrome_port: int) -> list:
    """Extract cookies from running Chrome via CDP websocket."""
    import urllib.request
    try:
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{chrome_port}/json").read())
    except Exception:
        return []
    page_tabs = [t for t in tabs if t.get('type') == 'page']
    if not page_tabs:
        return []
    ws_url = page_tabs[0]['webSocketDebuggerUrl']
    import websocket
    ws = websocket.create_connection(ws_url, timeout=15)
    msg = {"id": 1, "method": "Storage.getCookies", "params": {}}
    ws.send(json.dumps(msg))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == 1:
            ws.close()
            return resp.get('result', {}).get('cookies', [])
    ws.close()
    return []

def ensure_login(app: str, profile_path: str = r"C:\automation_profile", login_url: str = None):
    """
    Per-app login via CDP. Only runs when Chrome needed and no session cookie in DB.
    app: e.g. "linkedin.com", "gmail.com"
    profile_path: base dir; per-app dir becomes <base>/<app>
    login_url: override start URL, else https://<app>
    """
    app_norm = app.lower().strip()
    per_app_profile = os.path.join(profile_path, app_norm)

    if _has_session_cookie(app_norm):
        print(f"[setup_login] session cookie for {app_norm} found in DB — bypassing manual login")
        return True

    print(f"[setup_login] no session cookie for {app_norm} — launching Chrome for one-time manual login")
    os.makedirs(per_app_profile, exist_ok=True)

    # Find free port
    import random
    chrome_port = random.randint(9800, 9999)

    # Launch Chrome with CDP
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    subprocess.Popen([
        chrome_exe,
        f"--remote-debugging-port={chrome_port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={per_app_profile}",
        "--no-first-run", "--no-default-browser-check",
        "--window-size=1280,900",
        login_url or (f"https://{app_norm}" if "google" not in app_norm else "https://google.com")
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Check if manual login is bypassed in automated runs
    if os.environ.get("HOJAIGA_REQUIRE_LOGIN", "0") != "1":
        print(f"[setup_login] automated mode: quick cookie check for {app_norm} (no 120s block)")
        # Quick 3s poll for existing cookies without blocking automation
        for _ in range(3):
            time.sleep(1)
            try:
                cookies = _extract_cookies_via_cdp(chrome_port)
                matched = [c for c in cookies if app_norm.replace('.com', '') in c.get('domain', '') or 'google' in c.get('domain', '')]
                if matched:
                    _store_session_cookies(app_norm, matched)
                    print(f"[setup_login] captured {len(matched)} cookies for {app_norm}")
                    break
            except Exception:
                pass
        return True

    print(f"[setup_login] Chrome launched on port {chrome_port} — waiting up to 30s for login...")
    for _ in range(15):
        time.sleep(2)
        try:
            cookies = _extract_cookies_via_cdp(chrome_port)
            matched = [c for c in cookies if app_norm.replace('.com', '') in c.get('domain', '') or 'google' in c.get('domain', '')]
            if matched:
                _store_session_cookies(app_norm, matched)
                print(f"[setup_login] stored {len(matched)} cookies for {app_norm} to DB")
                break
        except Exception:
            pass

    return True

if __name__ == "__main__":
    ensure_login("linkedin.com")
