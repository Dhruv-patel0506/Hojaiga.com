"""
cef_devtools.py -- the Chromium / CEF / Electron route (backlog 2.4).

Why a route of its own: an Electron or CEF app hands the desktop ONE window and a page inside it. There are no
per-control HWNDs to post messages to, its UIA tree exists only after somebody asks for it, and a GPU-composited
page reads back BLANK through a GDI PrintWindow (the family of failure that has been reported as "the app did not
render"). The page itself, though, speaks a protocol: the browser process listens on a loopback port and will
report and mutate its own DOM. Driving that port is the difference between "I cannot see this app" and "I can read
every element, click the exact box, and take a screenshot that cannot be blank" -- and every event dispatched this
way enters through the browser, so it is headless by construction: no cursor, no keyboard driver, no foreground.

Nothing in this module knows the name of an application. A window belongs to this family because the executable
beside it carries Chromium's own resource files (icudtl.dat, resources.pak, libcef.dll ...), and it is reachable
because its PROCESS is listening on a loopback port that answers /json/version. Both are structural tests, so a
Chromium app nobody has heard of gets the same treatment as one the acceptance list names.

Scope of this transport, deliberately: read the page (elements, values, screenshot) and act on the page (click a
box, type text, press a key). It is NOT a browser automation framework -- no navigation, no cookies, no waits for
page loads. Those live in organ_19 / organ_51, which drive tabs; this drives a DESKTOP APP's window.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import glob
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    import websocket as _ws_mod                      # websocket-client
    HAS_WEBSOCKET = True
except Exception:  # pragma: no cover - optional dependency
    _ws_mod = None
    HAS_WEBSOCKET = False

# Chromium ships these next to its executable whatever it is packaged as (Electron, CEF, WebView2 runtime,
# a-branded-browser). Two of them together is the family signature; no app name is consulted.
CHROMIUM_MARKERS = ("icudtl.dat", "resources.pak", "v8_context_snapshot.bin", "chrome_100_percent.pak",
                    "chrome_200_percent.pak", "libcef.dll", "electron.dll", "chrome_elf.dll",
                    "snapshot_blob.bin")

_DEVTOOLS_FILE = "DevToolsActivePort"


# -------------------------------------------------------------------------------------------------- family test

def chromium_markers(exe_path: str) -> List[str]:
    """Chromium's own resource files reachable from this executable: beside it, or in the version folder under it.

    Both layouts exist and neither is an app name: Electron/CEF ship the pak files next to the exe, while Chrome
    keeps a thin launcher in `Application\\` and the engine (icudtl.dat, resources.pak) one level down in a
    version-named folder."""
    if not exe_path:
        return []
    d = os.path.dirname(os.path.abspath(exe_path))
    dirs = [d]
    try:
        dirs += [os.path.join(d, s) for s in sorted(os.listdir(d), reverse=True)
                 if os.path.isdir(os.path.join(d, s))][:8]
    except Exception:  # noqa: BLE001
        pass
    found = set()
    for dd in dirs:
        try:
            for m in CHROMIUM_MARKERS:
                if os.path.exists(os.path.join(dd, m)):
                    found.add(m)
        except Exception:  # noqa: BLE001
            continue
    return sorted(found)


def is_chromium_exe(exe_path: str) -> bool:
    """Structurally a Chromium/CEF/Electron binary: it ships at least TWO of the engine's own resource files."""
    return len(chromium_markers(exe_path)) >= 2


def resolve_chromium_exe(exe_path: str) -> str:
    """The REAL Chromium binary behind a launcher shortcut, '' when this exe is not the family.

    Installers hide the engine a level down: Squirrel (Discord, VS Code's own updater layout) keeps the app in
    `app-<version>\\<Name>.exe` beside an `Update.exe` that carries nothing, and an Inno root can hold only a stub
    over a version-named folder. Looking for the same file NAME one level down is a layout test, not an app list.
    """
    if exe_path and is_chromium_exe(exe_path):
        return exe_path
    if not exe_path:
        return ""
    base = os.path.basename(exe_path)
    d = os.path.dirname(os.path.abspath(exe_path))
    roots = [os.path.join(d, "*", base)]
    if not os.path.isdir(d):            # the catalogued version folder was replaced by an update: look sideways
        roots.insert(0, os.path.join(os.path.dirname(d), "*", base))
    for root in roots:
        for cand in sorted(glob.glob(root), reverse=True)[:12]:
            if is_chromium_exe(cand):
                return cand
    return ""


def exe_of_pid(pid: int) -> str:
    """Full image path of a process (QueryOnlyProcessImage), '' when it is not ours to ask."""
    if not pid:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32, k = ctypes.windll.kernel32, ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not k:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(4096)
        size = wt.DWORD(4096)
        if not k32.QueryFullProcessImageNameW(k, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    except Exception:  # noqa: BLE001
        return ""
    finally:
        k32.CloseHandle(k)


def installed_chromium_apps() -> List[Dict[str, Any]]:
    """Every app the host catalog knows about that is STRUCTURALLY a Chromium-family binary.

    The catalog (organ_40) is discovered data -- start-menu shortcuts and winget -- so this enumerates whatever is
    installed here, naming no app. Each row: {name, exe, markers}.
    """
    out: List[Dict[str, Any]] = []
    try:
        from core_organs.organ_40_app_launcher import AppCatalog
        import sqlite3
        cat = AppCatalog()
        cat.ensure_scanned()
        with sqlite3.connect(cat.db) as c:
            rows = [{"name": n, "launcher_path": p} for n, p in
                    c.execute("SELECT name, launcher_path FROM app_catalog")]
    except Exception:  # noqa: BLE001 - an un-catalogued host is not an error, it is an empty list
        return out
    for r in rows:
        exe = (r.get("launcher_path") or "").strip('"') if isinstance(r, dict) else ""
        real = resolve_chromium_exe(exe)
        if real:
            out.append({"name": r.get("name") or os.path.basename(real), "exe": real,
                        "launcher": exe, "markers": chromium_markers(real)})
    return out


# ------------------------------------------------------------------------------------------- endpoint discovery

def _http_json(url: str, timeout: float = 1.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:     # noqa: S310 - loopback only, port from below
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None


def already_running(exe_path: str) -> bool:
    """Is an instance of THIS executable already on the machine?

    Two reasons the route cares: a single-instance app hands a second launch over to the window that is
    already open and exits, so we would own nothing to drive; and even if it did answer, the session we
    would then reach through DevTools is somebody else's working document, which is not ours to touch.
    Compared by resolved path, never by name. Unreadable processes are treated as not-running (a missed
    hint costs time, a wrong exclusion would cost capability).
    """
    try:
        import psutil
        want = os.path.normcase(os.path.realpath(exe_path))
        me = os.getpid()
        for proc in psutil.process_iter(["pid"]):
            try:
                if proc.info["pid"] == me:
                    continue
                if os.path.normcase(os.path.realpath(proc.exe())) == want:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                continue
    except Exception:  # noqa: BLE001
        return False
    return False


def listening_ports(pid: int) -> List[int]:
    """Loopback ports this process -- or any process BELOW it in its own tree -- is LISTENing on.

    The tree matters: `chrome.exe` in the Application folder is a stub that starts the real browser as a child, so
    the socket belongs to a pid nobody asked for. psutil walks both; without it the launch hint and the
    DevToolsActivePort file below still find an app WE started, and a human-started one is honestly reported as
    unreachable rather than guessed at."""
    if not pid:
        return []
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return []
    pids = [pid]
    try:
        pids += [c.pid for c in psutil.Process(pid).children(recursive=True)]
    except Exception:  # noqa: BLE001
        pass
    out = set()
    for q in pids:
        try:
            pr = psutil.Process(q)
            conns = pr.net_connections(kind="listen") if hasattr(pr, "net_connections") else pr.connections(kind="listen")
            for c in conns:
                ip = getattr(c.laddr, "ip", "") or ""
                if ip in ("127.0.0.1", "0.0.0.0", "::1", "::"):
                    out.add(int(c.laddr.port))
        except Exception:  # noqa: BLE001 - a process that vanished mid-walk is not an error
            continue
    return sorted(out)


def _devtools_file_ports(pid: int) -> List[int]:
    """Ports named by a DevToolsActivePort file inside a data directory this process could own.

    A Chromium app started with a debugging port writes that file in its own user-data dir. The dirs an app of
    this pid could own are the profile WE gave it, its exe directory, and the per-user app-data folder named after
    that directory -- all DERIVED from the process's own paths, never from a table of application names."""
    ports: List[int] = []
    seen_dirs: List[str] = []
    rec = _LAUNCHED.get(pid)
    if rec and rec[1]:
        seen_dirs.append(rec[1])
    exe = exe_of_pid(pid)
    if exe:
        d = os.path.dirname(exe)
        bases = [d]
        for env in ("LOCALAPPDATA", "APPDATA"):
            root = os.environ.get(env, "")
            if root:
                bases.append(os.path.join(root, os.path.basename(d)))
        seen_dirs += bases
    for b in seen_dirs:
        for cand in (os.path.join(b, _DEVTOOLS_FILE), os.path.join(b, "User Data", _DEVTOOLS_FILE)):
            try:
                if os.path.exists(cand):
                    with open(cand, "r", encoding="utf-8", errors="replace") as fh:
                        ports.append(int(fh.readline().strip()))
            except Exception:  # noqa: BLE001
                continue
    return ports


def devtools_port(pid: int, timeout: float = 0.0, hint_port: int = 0) -> int:
    """The DevTools port a process is serving, 0 when it serves none. Proof is /json/version answering with a
    browser identity -- a loopback listener that is not DevTools is simply not chosen."""
    deadline = time.time() + timeout
    while True:
        for p in _candidates(pid, hint_port):
            v = _http_json(f"http://127.0.0.1:{p}/json/version")
            if v and v.get("Browser"):
                return p
        if time.time() >= deadline:
            return 0
        time.sleep(0.4)


def _candidates(pid: int, hint_port: int = 0) -> List[int]:
    """Ports worth PROBING, cheapest first: the port we launched with, the file the app wrote, the sockets the
    process tree owns. De-duplicated, order kept."""
    out: List[int] = []
    for p in [hint_port] + ([_LAUNCHED[pid][0]] if pid in _LAUNCHED else []) + _devtools_file_ports(pid) + listening_ports(pid):
        if p and p not in out:
            out.append(int(p))
    return out


# -------------------------------------------------------------------------------------------------- transport

# Ports and profile dirs of the Chromium apps THIS process started: (pid -> (port, user_data_dir)). A hint we
# already have is worth more than a discovery scan, and it is what makes an app that refuses to be found (a stub
# launcher whose child owns the socket, an app that writes its file elsewhere) still reachable.
_LAUNCHED: Dict[int, Tuple[int, str]] = {}


class DevTools:
    """One synchronous CDP session attached to a Chromium-family app's PAGE target.

    `close()` must run: a socket left open against somebody else's app is a leak with a side effect."""

    def __init__(self, ws_url: str, port: int, target: dict):
        self.ws = _ws_mod.create_connection(ws_url, timeout=20, suppress_origin=True, max_size=32 * 1024 * 1024)
        self.port, self.target = port, target
        self._id = 0
        self.last_error = ""

    # -- lifecycle ---------------------------------------------------------------
    last_attach_error: str = ""        # why the LAST attach failed: 'no port', 'no page target', 'ws connect: ...'

    @classmethod
    def attach(cls, pid: int, timeout: float = 20.0, page_hint: str = "", hint_port: int = 0) -> Optional["DevTools"]:
        cls.last_attach_error = ""
        if not HAS_WEBSOCKET:
            cls.last_attach_error = "websocket-client not installed"
            return None
        if not pid:
            cls.last_attach_error = "no pid"
            return None
        port = devtools_port(pid, timeout=timeout, hint_port=hint_port or (_LAUNCHED.get(pid) or (0, ""))[0])
        if not port:
            cls.last_attach_error = f"no DevTools endpoint for pid {pid} in {timeout:.0f}s"
            return None
        tabs = _http_json(f"http://127.0.0.1:{port}/json/list") or []
        pages = [t for t in tabs if t.get("webSocketDebuggerUrl")
                 and t.get("type") in ("page", "webview", "app", "other")]
        if not pages:
            cls.last_attach_error = f"port {port} serves no page target ({len(tabs)} targets, types " \
                                    f"{sorted({str(t.get('type')) for t in tabs})})"
            return None
        if page_hint:
            pages.sort(key=lambda t: page_hint.lower() not in (str(t.get("title", "")) + str(t.get("url", ""))).lower())
        tgt = pages[0]
        try:
            self = cls(tgt["webSocketDebuggerUrl"], port, tgt)
        except Exception as exc:  # noqa: BLE001
            cls.last_attach_error = f"ws connect: {exc}"[:160]
            return None
        self.send("Page.enable")
        self.send("Runtime.enable")
        return self

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "DevTools":
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # -- wire --------------------------------------------------------------------
    def send(self, method: str, params: Optional[dict] = None, timeout: float = 15.0) -> Optional[dict]:
        self._id += 1
        mid = self._id
        try:
            self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            self.ws.settimeout(timeout)
            end = time.time() + timeout
            while time.time() < end:
                msg = json.loads(self.ws.recv())
                if msg.get("id") == mid:
                    if "error" in msg:
                        self.last_error = f"{method}: {msg['error'].get('message')}"[:200]
                        return None
                    return msg.get("result", {})
            self.last_error = f"{method}: timeout"
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{method}: {exc}"[:200]
        return None

    def evaluate(self, expression: str, timeout: float = 15.0) -> Tuple[bool, Any]:
        """Runtime.evaluate with a by-value result. Returns (ok, value) -- ok=False means the page said no,
        which is an ANSWER about the surface, not a silent zero."""
        r = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                           "awaitPromise": True, "timeout": int(timeout * 1000)}, timeout=timeout + 5)
        if r is None:
            return (False, self.last_error)
        if r.get("exceptionDetails"):
            return (False, str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
        return (True, (r.get("result") or {}).get("value"))


# -------------------------------------------------------------------------------------------- page perception

# The selectors a person would call "the things I can use": anything clickable, anything typeable, anything with
# an explicit role or label. Kept to ONE evaluate() so a 1000-element page costs one round trip.
_ELEMENTS_JS = r"""
(() => {
  const sel = 'a,button,input,textarea,select,[role],[contenteditable="true"],[tabindex]:not([tabindex="-1"]),'
            + '[onclick],[class*="btn"],[id]';
  const out = [];
  const els = [];
  const seen = new Set();
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity) < 0.05) continue;
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder
                   || el.title || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const key = el.tagName + '|' + (el.id || '') + '|' + Math.round(r.left) + ',' + Math.round(r.top);
    if (seen.has(key)) continue;
    seen.add(key);
    els.push(el);
    out.push({
      idx: els.length - 1,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      id: el.id || '',
      name: label,
      cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 80),
      type: el.getAttribute('type') || '',
      editable: !!el.isContentEditable || /^(input|textarea|select)$/i.test(el.tagName),
      x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height,
    });
    if (out.length >= 900) break;
  }
  // The element HANDLES stay on the page in one array, so a later read/write names the SAME node this
  // snapshot described -- without stamping a data-attribute into somebody else's DOM.
  window.__hjEls = els;
  return {elements: out, vw: innerWidth, vh: innerHeight, title: document.title, url: location.href};
})()
"""

# Read/write by the index this snapshot handed out. `contenteditable` and inputs both answer through value or
# innerText, which is what a person sees in the box.
_READ_JS = "(() => { const e = (window.__hjEls || [])[%d]; if (!e) return null; return e.value !== undefined ? String(e.value) : (e.innerText || '').trim(); })()"
_FOCUS_JS = "(() => { const e = (window.__hjEls || [])[%d]; if (!e) return false; e.focus(); return document.activeElement === e; })()"


def page_elements(dt: DevTools) -> Dict[str, Any]:
    """Everything usable on the page, in CSS pixels of the layout viewport (screen mapping is the caller's
    business: `viewport_screen_map`). {} when the page refused or the socket is gone."""
    ok, val = dt.evaluate(_ELEMENTS_JS)
    return val if ok and isinstance(val, dict) else {}


def wait_for_elements(dt: DevTools, timeout: float = 20.0, min_count: int = 1,
                     poll: float = 0.5) -> Dict[str, Any]:
    """Poll until the page really has something addressable, and record how long that took.

    A cold Electron app lives on a splash screen or an update bar for its first seconds (measured:
    Discord's window answered with zero elements while it was still booting, VS Code's workbench went
    0 -> 110 nodes after the UI settled). Zero at that moment means 'not yet', not 'nothing here' --
    an agent that acts on the first read reports a real window as an empty one. Empty after the whole
    timeout is the honest answer.
    """
    t0 = time.time()
    end = t0 + timeout
    els: Dict[str, Any] = {}
    while time.time() < end:
        els = page_elements(dt)
        if len(els.get("elements") or []) >= min_count:
            els["settled_s"] = round(time.time() - t0, 2)
            return els
        time.sleep(poll)
    els["settled_s"] = round(time.time() - t0, 2)
    return els


def viewport_screen_map(hwnd: int, css_w: float, css_h: float) -> Tuple[float, float, int, int]:
    """(sx, sy, offset_x, offset_y) turning a CSS px point inside the layout viewport into a screen point:
    the client area is Chromium's page, so the scale is client_width / viewport_width and the origin is the
    client's own top-left. Measured scale of a maximised Electron app is 1.0 at 100 % DPI and the device-pixel
    ratio otherwise; taking the ratio of two sizes keeps it correct on either."""
    u = ctypes.windll.user32
    try:
        r = wt.RECT()
        u.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        tl, br = wt.POINT(0, 0), wt.POINT(r.right, r.bottom)
        u.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(tl))
        u.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(br))
        w, h = max(1, br.x - tl.x), max(1, br.y - tl.y)
        sx = w / float(css_w or 1)
        sy = h / float(css_h or 1)
        return (sx, sy, tl.x, tl.y)
    except Exception:  # noqa: BLE001
        return (1.0, 1.0, 0, 0)


def to_screen(pt: Tuple[float, float], css: Tuple[float, float, int, int]) -> Tuple[int, int]:
    sx, sy, ox, oy = css
    return (int(ox + pt[0] * sx), int(oy + pt[1] * sy))


# ----------------------------------------------------------------------------------------------- page action

def click_at(dt: DevTools, css_x: float, css_y: float) -> bool:
    """A real mouse press/release INTO the renderer at a page coordinate. The browser synthesises it, so the
    physical pointer never moves and the window never needs focus."""
    for typ in ("mousePressed", "mouseReleased"):
        r = dt.send("Input.dispatchMouseEvent", {"type": typ, "x": css_x, "y": css_y, "button": "left",
                                                 "clickCount": 1, "buttons": 1 if typ == "mousePressed" else 0})
        if r is None:
            return False
    return True


def type_text(dt: DevTools, text: str) -> bool:
    """Insert text at the page's focused element (Input.insertText: goes through the same path as an IME, so the
    app's own change handlers fire). Falls back to per-character key events, which a React-style controlled input
    needs in order to update its model."""
    if dt.send("Input.insertText", {"text": text}) is not None:
        return True
    ok = True
    for ch in text:
        r = dt.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch, "key": ch, "unmodifiedText": ch})
        ok = r is not None and ok
        dt.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch})
    return ok


# (DOM key, DOM code, Windows virtual-key code). The VK is not decoration: Input.dispatchKeyEvent only
# fills KeyboardEvent.keyCode when windowsVirtualKeyCode travels, and an app's keybinding service matches
# on it. Measured on a real Electron workbench: Escape closed a modal but every Ctrl+<key> chord was
# ignored while keyCode was 0 - the event reached the page and the app could not recognise it.
_VK_NAMED = {
    "enter": ("Enter", "Enter", 0x0D), "return": ("Enter", "Enter", 0x0D),
    "escape": ("Escape", "Escape", 0x1B), "esc": ("Escape", "Escape", 0x1B),
    "tab": ("Tab", "Tab", 0x09), "backspace": ("Backspace", "Backspace", 0x08),
    "delete": ("Delete", "Delete", 0x2E), "insert": ("Insert", "Insert", 0x2D),
    "space": (" ", "Space", 0x20), "home": ("Home", "Home", 0x24), "end": ("End", "End", 0x23),
    "pageup": ("PageUp", "PageUp", 0x21), "pagedown": ("PageDown", "PageDown", 0x22),
    "arrowleft": ("ArrowLeft", "ArrowLeft", 0x25), "arrowup": ("ArrowUp", "ArrowUp", 0x26),
    "arrowright": ("ArrowRight", "ArrowRight", 0x27), "arrowdown": ("ArrowDown", "ArrowDown", 0x28),
    ";": (";", "Semicolon", 0xBA), ",": (",", "Comma", 0xBC), ".": (".", "Period", 0xBE),
    "/": ("/", "Slash", 0xBF), "\\": ("\\", "Backslash", 0xDC), "'": ("'", "Quote", 0xDE),
    "`": ("`", "Backquote", 0xC0), "-": ("-", "Minus", 0xBD), "=": ("=", "Equal", 0xBB),
}


def key_fields(key: str) -> Dict[str, Any]:
    """The three fields one key needs so a real app recognises it: key, code, windowsVirtualKeyCode."""
    k = (key or "").strip()
    low = k.lower()
    if len(k) == 1:
        up = k.upper()
        if "A" <= up <= "Z":
            return {"key": k, "code": "Key" + up, "vk": ord(up)}
        if "0" <= k <= "9":
            return {"key": k, "code": "Digit" + k, "vk": ord(k)}
        if low in _VK_NAMED:
            dom, code, vk = _VK_NAMED[low]
            return {"key": dom, "code": code, "vk": vk}
        return {"key": k, "code": "", "vk": 0}
    if low in _VK_NAMED:
        dom, code, vk = _VK_NAMED[low]
        return {"key": dom, "code": code, "vk": vk}
    if low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 12:
        n = int(low[1:])
        return {"key": "F%d" % n, "code": "F%d" % n, "vk": 0x70 + n - 1}
    return {"key": k, "code": k, "vk": 0}


def press_key(dt: DevTools, key: str) -> bool:
    """One named key (Enter, Escape, Tab, ArrowDown ...) or one character, sent the way the DOM listens for
    it: a printable key carries its text, a named key carries key/code/VK."""
    f = key_fields(key)
    printable = len(f["key"]) == 1
    text = f["key"] if printable else ""
    base = {"key": f["key"], "code": f["code"],
            "windowsVirtualKeyCode": f["vk"], "nativeVirtualKeyCode": f["vk"]}
    down = dt.send("Input.dispatchKeyEvent", dict(base, type="keyDown" if printable else "rawKeyDown",
                                                  text=text, unmodifiedText=text))
    up = dt.send("Input.dispatchKeyEvent", dict(base, type="keyUp"))
    return down is not None and up is not None


def shortcut(dt: DevTools, combo: str) -> bool:
    """A chord the APP interprets (Ctrl+P, Ctrl+S ...): modifiers travel on the key event, so the app's own
    keybinding service fires -- the same path a physical chord takes, without touching the keyboard driver."""
    _MODS = {"ctrl": 2, "control": 2, "shift": 1, "alt": 4, "meta": 8, "cmd": 8, "win": 8}
    parts = [p.strip().lower() for p in (combo or "").split("+") if p.strip()]
    if not parts:
        return False
    mask = sum(_MODS.get(p, 0) for p in parts[:-1])
    f = key_fields(parts[-1])
    text = f["key"] if (mask == 0 and len(f["key"]) == 1) else ""
    base = {"key": f["key"], "code": f["code"], "modifiers": mask,
            "windowsVirtualKeyCode": f["vk"], "nativeVirtualKeyCode": f["vk"]}
    down = dt.send("Input.dispatchKeyEvent", dict(base, type="keyDown" if text else "rawKeyDown",
                                                  text=text, unmodifiedText=text))
    up = dt.send("Input.dispatchKeyEvent", dict(base, type="keyUp"))
    return down is not None and up is not None


# ------------------------------------------------------------------------------------ read / write one element

def read_index(dt: DevTools, idx: int) -> Optional[str]:
    """What the page itself says this box holds, by the index of the last `page_elements` snapshot.
    None = the node is gone (the page re-rendered), which is a fact about the surface, not an empty string."""
    ok, val = dt.evaluate(_READ_JS % int(idx))
    if not ok:
        return None
    return val if isinstance(val, str) else ("" if val is None else str(val))


def focus_index(dt: DevTools, idx: int) -> bool:
    """Ask the page to focus the node, and take the page's word for it (document.activeElement)."""
    ok, val = dt.evaluate(_FOCUS_JS % int(idx))
    return bool(ok and val is True)


def write_into(dt: DevTools, element: Dict[str, Any], text: str, timeout: float = 4.0) -> Tuple[bool, str]:
    """Put text into one element and only then claim it: click its own box (a click also focuses it and fires the
    handlers a controlled input needs), type, and read the box back. Returns (landed, note) -- a page that accepts
    the keystrokes but shows something else is reported as NOT landed, because 'the send() worked' is not proof.
    """
    idx = int(element.get("idx", -1))
    clicked = click_at(dt, float(element.get("x", 0)), float(element.get("y", 0)))
    if not clicked:
        focus_index(dt, idx)
    before = read_index(dt, idx)
    if not type_text(dt, text):
        return (False, "insert and key events both refused")
    end = time.time() + timeout
    while time.time() < end:
        now = read_index(dt, idx)
        if now is None:
            return (False, f"node {idx} vanished after typing (the page re-rendered)")
        if text in now or (before is not None and now.endswith(text)):
            return (True, f"read back {now[:40]!r} via {'click' if clicked else 'focus'}+insertText")
        time.sleep(0.3)
    return (False, f"typed but the box still reads {(read_index(dt, idx) or '')[:40]!r}")


# ------------------------------------------------------------------------------------------ page screenshot

def screenshot_png(dt: DevTools) -> bytes:
    """The page's own pixels, base64 PNG from Page.captureScreenshot. This is the answer to a GPU-composited
    surface that PrintWindow reads as blank: the compositor is asked, not the window DC. b"" when refused."""
    r = dt.send("Page.captureScreenshot", {"format": "png"}, timeout=25)
    if not r or not r.get("data"):
        return b""
    import base64
    try:
        return base64.b64decode(r["data"])
    except Exception:  # noqa: BLE001
        return b""


# --------------------------------------------------------------------------------------------- launch helper

def launch_with_devtools(exe: str, extra_args: Optional[List[str]] = None,
                        isolated_profile: bool = True) -> Tuple[int, int, str]:
    """Start a Chromium-family app with a debugging port and return (pid, port, profile_dir).

    The profile is OURS unless the app is being driven as the user left it: an isolated --user-data-dir means a
    second instance, so a test never hijacks (or is hijacked by) the window the human already has. Not every
    Chromium app honours the switch (some refuse remote debugging outright); the caller checks with
    `devtools_port` and reports honestly when nothing answered."""
    port = _free_port()
    args = [exe, f"--remote-debugging-port={port}"]
    profile = ""
    if isolated_profile:
        profile = tempfile.mkdtemp(prefix="hj_cef_")
        args.append(f"--user-data-dir={profile}")
    args.extend(extra_args or [])
    try:
        p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x08000000)              # CREATE_NO_WINDOW
        _LAUNCHED[p.pid] = (port, profile)
        return p.pid, port, profile
    except Exception:  # noqa: BLE001
        return 0, 0, ""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_window(pid: int, timeout: float = 25.0, class_prefix: str = "chrome_widgetwin") -> int:
    """The app's own Chromium content window (largest Chrome_WidgetWin_* / class_prefix owned by this pid)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _biggest_window_of(pid, class_prefix)
        if hwnd:
            return hwnd
        time.sleep(0.4)
    return 0


def _biggest_window_of(pid: int, class_prefix: str) -> int:
    u = ctypes.windll.user32
    found: List[Tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, wt.HWND, wt.LPARAM)
    def _cb(h, _l):
        if not u.IsWindowVisible(h):
            return 1
        p = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid:
            return 1
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        if not buf.value.lower().startswith(class_prefix):
            return 1
        r = wt.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        found.append((int(h), max(0, (r.right - r.left) * (r.bottom - r.top))))
        return 1

    u.EnumWindows(_cb, 0)
    return max(found, key=lambda t: t[1])[0] if found else 0
