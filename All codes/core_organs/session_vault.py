"""
session_vault -- keep logged-in sessions (cookies / storage state) so a site can be used without logging in again.

    python -m core_organs.session_vault capture linkedin.com        a VISIBLE browser opens on the site; YOU log in; press Enter in this window; the session is saved (encrypted)
    python -m core_organs.session_vault import linkedin.com C:\\path\\cookies.json     a cookie export you saved yourself (Cookie-Editor JSON, a Playwright storage state, or a Netscape cookies.txt)
    python -m core_organs.session_vault list                        which sessions are kept, when saved, when they expire (never the values)
    python -m core_organs.session_vault check linkedin.com          is it still valid (not expired)
    python -m core_organs.session_vault delete linkedin.com         forget it
    hojaiga.bat --session linkedin.com "<task>"                     a web task that starts already signed in

    from core_organs import session_vault as SV
    state = SV.get("linkedin.com")            # a Playwright storage_state dict, decrypted in memory only (None if absent / expired)
    ctx = browser.new_context(**SV.context_kwargs("linkedin.com"))

How it is kept safe (what this does and does not promise):
  * ENCRYPTED AT REST with Windows DPAPI (CryptProtectData) bound to THIS Windows user, plus an application entropy: the file cannot be read by another account or another machine, and no plaintext cookie is ever written.
  * The tool never types a password and never asks for one: a session comes from a login the PERSON did in a window they can see, or from a cookie export they saved themselves.
  * `list` and every log show site, dates and counts only; values never leave memory. An imported plain file is not deleted for you: the import tells you to delete it (or use --shred to overwrite it).
  * A session expires: a site may end it, rotate it, or flag an automated one. Expired sessions are reported, not used; sites' terms about automation are the person's to check.
  * Anything a session is used FOR still goes through the consequence gate: posting, sending and paying ask first.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import json
import os
import re
import sys
import time
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

DEFAULT_DIR = os.path.join("D:" + os.sep, "new_automation", "data", "vault")
_ENTROPY = b"hojaiga.session_vault.v1"


def _dir() -> str:
    d = os.environ.get("HOJAIGA_VAULT_DIR", DEFAULT_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _path() -> str:
    return os.path.join(_dir(), "sessions.json")


# ---- DPAPI ---------------------------------------------------------------------------------------------------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(b: bytes) -> "_Blob":
    buf = ctypes.create_string_buffer(b, len(b))
    return _Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf  # type: ignore[return-value]


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("the session vault needs Windows DPAPI; it refuses to store sessions unencrypted")
    (inb, k1), (ent, k2) = _to_blob(data), _to_blob(_ENTROPY)
    out = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inb), "hojaiga session", ctypes.byref(ent), None, None, 0, ctypes.byref(out)):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _unprotect(blob: bytes) -> bytes:
    (inb, k1), (ent, k2) = _to_blob(blob), _to_blob(_ENTROPY)
    out = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inb), None, ctypes.byref(ent), None, None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData failed (another user, another machine, or a damaged entry)")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# ---- the index (no secrets in it) ---------------------------------------------------------------------------------------------------------------------
def host_of(site: str) -> str:
    s = (site or "").strip().lower()
    if "://" not in s:
        s = "https://" + s
    h = urlparse(s).netloc.split("@")[-1].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _load() -> Dict[str, Any]:
    try:
        return json.load(open(_path(), encoding="utf-8"))
    except Exception:
        return {"version": 1, "sessions": {}}


def _save(idx: Dict[str, Any]) -> None:
    tmp = _path() + ".tmp"
    json.dump(idx, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, _path())


def _expiry(state: Dict[str, Any]) -> Optional[float]:
    """The moment the LAST persistent cookie dies (None: only session cookies, which end with the browser unless the site keeps them server-side)."""
    ex = [c.get("expires") for c in state.get("cookies", []) if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0]
    return max(ex) if ex else None


def normalise(raw: Any) -> Dict[str, Any]:
    """Cookie-Editor / EditThisCookie JSON (a list), a Playwright storage_state (a dict) or Netscape cookies.txt (text) -> a Playwright storage_state."""
    if isinstance(raw, str):
        cookies = []
        for ln in raw.splitlines():
            ln = ln.strip()
            http_only = ln.startswith("#HttpOnly_")
            if http_only:
                ln = ln[len("#HttpOnly_"):]
            if not ln or ln.startswith("#"):
                continue
            p = ln.split("\t")
            if len(p) >= 7:
                cookies.append({"name": p[5], "value": p[6], "domain": p[0], "path": p[2], "expires": float(p[4]) if p[4].isdigit() and float(p[4]) > 0 else -1, "httpOnly": http_only, "secure": p[3].upper() == "TRUE", "sameSite": "Lax"})
        return {"cookies": cookies, "origins": []}
    if isinstance(raw, dict) and isinstance(raw.get("cookies"), list):
        return {"cookies": list(raw["cookies"]), "origins": list(raw.get("origins", []))}
    if isinstance(raw, list):
        ss = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict", "unspecified": "Lax", "": "Lax"}
        out = []
        for c in raw:
            if not isinstance(c, dict) or "name" not in c or "value" not in c:
                continue
            exp = c.get("expirationDate", c.get("expires", -1))
            out.append({"name": c["name"], "value": c["value"], "domain": c.get("domain", ""), "path": c.get("path", "/"), "expires": float(exp) if isinstance(exp, (int, float)) and not c.get("session") else -1,
                        "httpOnly": bool(c.get("httpOnly", False)), "secure": bool(c.get("secure", False)), "sameSite": ss.get(str(c.get("sameSite", "")).lower(), "Lax")})
        return {"cookies": out, "origins": []}
    raise ValueError("not a cookie export I can read (expected Cookie-Editor JSON, a Playwright storage state, or Netscape cookies.txt)")


# ---- the API ------------------------------------------------------------------------------------------------------------------------------------------------
def put(site: str, state: Any, label: str = "") -> Dict[str, Any]:
    st = normalise(state)
    if not st["cookies"] and not st["origins"]:
        raise ValueError("nothing to keep: the session has no cookies and no stored data")
    h = host_of(site)
    blob = _protect(json.dumps(st).encode("utf-8"))
    idx = _load()
    ex = _expiry(st)
    idx["sessions"][h] = {"blob": base64.b64encode(blob).decode("ascii"), "saved": time.time(), "expires": ex, "cookies": len(st["cookies"]), "origins": len(st["origins"]), "label": label, "last_used": None}
    _save(idx)
    return meta(h)


def get(site: str, allow_expired: bool = False) -> Optional[Dict[str, Any]]:
    h = host_of(site)
    ent = _load()["sessions"].get(h)
    if not ent:
        return None
    if ent.get("expires") and ent["expires"] < time.time() and not allow_expired:
        return None
    try:
        st = json.loads(_unprotect(base64.b64decode(ent["blob"])).decode("utf-8"))
    except Exception:
        return None
    idx = _load()
    if h in idx["sessions"]:
        idx["sessions"][h]["last_used"] = time.time()
        _save(idx)
    return st


def meta(site: str) -> Dict[str, Any]:
    h = host_of(site)
    e = _load()["sessions"].get(h)
    if not e:
        return {"site": h, "present": False}
    now = time.time()
    left = (e["expires"] - now) / 86400.0 if e.get("expires") else None
    return {"site": h, "present": True, "saved": time.strftime("%Y-%m-%d %H:%M", time.localtime(e["saved"])), "cookies": e["cookies"], "origins": e["origins"], "label": e.get("label", ""),
            "expires_in_days": round(left, 1) if left is not None else None, "valid": (left is None or left > 0),
            "last_used": time.strftime("%Y-%m-%d %H:%M", time.localtime(e["last_used"])) if e.get("last_used") else None}


def status() -> List[Dict[str, Any]]:
    return [meta(h) for h in sorted(_load()["sessions"])]


def delete(site: str) -> bool:
    idx = _load()
    ok = idx["sessions"].pop(host_of(site), None) is not None
    _save(idx)
    return ok


def purge_expired() -> List[str]:
    idx, gone = _load(), []
    for h, e in list(idx["sessions"].items()):
        if e.get("expires") and e["expires"] < time.time():
            idx["sessions"].pop(h)
            gone.append(h)
    _save(idx)
    return gone


def context_kwargs(site: str) -> Dict[str, Any]:
    """Keyword arguments for browser.new_context(): the stored session, or nothing when there is none (the run then starts signed out, and says so)."""
    st = get(site)
    return {"storage_state": st} if st else {}


# ---- getting a session in WITHOUT handling a password ---------------------------------------------------------------------------------------------------
def capture(site: str, url: str = "", wait_for_enter: bool = True, timeout_min: float = 15.0, browser_factory: Any = None) -> Dict[str, Any]:
    """Open a VISIBLE browser on the site. The person signs in (any method, 2-step checks included); pressing Enter here saves the resulting session. Nothing is typed by this program."""
    from playwright.sync_api import sync_playwright
    h = host_of(site)
    with sync_playwright() as pw:
        if browser_factory:
            br = browser_factory(pw)
        else:
            from core_organs.try_app import launch_browser
            br = launch_browser(pw, headless=False, args=["--window-position=60,40", "--window-size=1280,860"])
        try:
            ctx = br.new_context(no_viewport=True)
            page = ctx.new_page()
            page.goto(url or ("https://" + h), wait_until="domcontentloaded", timeout=60000)
            if wait_for_enter:
                print(f"A browser window is open on {h}. Sign in there yourself. When you are signed in, come back to this window and press Enter (or wait {timeout_min:.0f} min).", flush=True)
                end = time.time() + timeout_min * 60
                import threading
                ev = threading.Event()
                threading.Thread(target=lambda: (sys.stdin.readline(), ev.set()), daemon=True).start()
                while time.time() < end and not ev.is_set():
                    time.sleep(0.5)
            state = ctx.storage_state()
        finally:
            with contextlib.suppress(Exception):
                br.close()
    return put(h, state, label="captured from a login the person did")


def import_file(site: str, path: str, shred: bool = False) -> Dict[str, Any]:
    raw_text = open(path, encoding="utf-8", errors="replace").read()
    try:
        raw: Any = json.loads(raw_text)
    except Exception:
        raw = raw_text
    m = put(site, raw, label="imported from a file the person saved")
    if shred:
        with contextlib.suppress(Exception):
            n = os.path.getsize(path)
            with open(path, "r+b") as f:
                f.write(os.urandom(n))
                f.flush()
                os.fsync(f.fileno())
            os.remove(path)
        m["source_file"] = "overwritten and deleted"
    else:
        m["source_file"] = "STILL ON DISK in plain text: delete it (or import again with --shred)"
    return m


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="session_vault")
    ap.add_argument("cmd", choices=["capture", "import", "list", "check", "delete", "purge"])
    ap.add_argument("site", nargs="?", default="")
    ap.add_argument("file", nargs="?", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--shred", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for m in status():
            print(json.dumps(m))
        return 0
    if a.cmd == "purge":
        print("expired and removed:", purge_expired())
        return 0
    if not a.site:
        ap.error("a site is needed")
    if a.cmd == "capture":
        print(json.dumps(capture(a.site, a.url)))
    elif a.cmd == "import":
        if not a.file:
            ap.error("import needs a file")
        print(json.dumps(import_file(a.site, a.file, a.shred)))
    elif a.cmd == "check":
        print(json.dumps(meta(a.site)))
    elif a.cmd == "delete":
        print("deleted" if delete(a.site) else "not found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
