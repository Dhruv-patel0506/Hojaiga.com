"""
professor.adapters.cdp -- the Chrome DevTools Protocol as an INTERACTION ROUTE for Chromium / Electron / WebView2 applications.

Why: UI Automation sees a Chromium window's toolbar, but opening its menus and bubbles needs real activation, and everything INSIDE a page (settings pages, web apps, Electron UIs) is a web document
the OS accessibility tree only mirrors lazily. The DevTools protocol, spoken to a browser WE launched with a remote-debugging port, reads a page's accessibility tree (every control with its role
and name, shadow DOM included) and acts on it (click, type, navigate) without the window being visible, focused or even on a monitor - the same 'headless, never touches the user's mouse /
keyboard' contract as the other effectors.  It is only ever used on an instance this run launched (the debugging port is bound to 127.0.0.1 and exists only for that process).

  CdpBrowser(port)                    connection to one browser instance (HTTP discovery + a WebSocket per page)
    .targets()                        the pages / tabs
    .page(i)                          a CdpPage for one of them
  CdpPage.verbs()                     the interactive controls of the page as plain dicts {label, role, node, state}
  CdpPage.act(node, text=None)        click / type into one of them
  CAPABILITIES                        what the protocol can do to a tabbed window (open / close / switch a tab, reload, history) - named in the GUIDE's words by the adapter
"""

from __future__ import annotations

import json
import socket
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

INTERACTIVE_ROLES = {"button", "link", "textbox", "searchbox", "checkbox", "radio", "switch", "tab", "menuitem", "menuitemcheckbox", "menuitemradio", "combobox", "option", "slider", "spinbutton",
                     "treeitem", "listitem", "listbox", "toggle button", "popupbutton", "disclosuretriangle"}
ROLE_MAP = {"button": "button", "link": "link", "textbox": "field", "searchbox": "field", "checkbox": "checkbox", "radio": "radio", "switch": "toggle", "tab": "tab", "menuitem": "menu_item",
            "menuitemcheckbox": "menu_item", "menuitemradio": "menu_item", "combobox": "dropdown", "option": "list_item", "slider": "field", "spinbutton": "field", "treeitem": "tree_item",
            "listitem": "list_item", "listbox": "list_item", "popupbutton": "dropdown", "disclosuretriangle": "button", "toggle button": "toggle"}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _http_json(url: str, timeout: float = 3.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as r:                       # 127.0.0.1 only
        return json.loads(r.read().decode("utf-8", "replace"))


class CdpError(Exception):
    pass


class CdpPage:
    def __init__(self, info: Dict[str, Any], timeout: float = 8.0):
        import websocket
        self.info = info
        self.id = info.get("id", "")
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], timeout=timeout, suppress_origin=True)
        self._n = 0
        self.events: List[Dict[str, Any]] = []

    def call(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 8.0) -> Dict[str, Any]:
        self._n += 1
        i = self._n
        self.ws.settimeout(timeout)
        self.ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv())
            except Exception as exc:
                raise CdpError(f"{method}: {type(exc).__name__}")
            if msg.get("id") == i:
                if "error" in msg:
                    raise CdpError(f"{method}: {msg['error'].get('message', msg['error'])}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
                if len(self.events) > 200:
                    del self.events[:100]
        raise CdpError(f"{method}: timed out")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    # ---- reading
    def title_url(self) -> Tuple[str, str]:
        try:
            r = self.call("Runtime.evaluate", {"expression": "[document.title, location.href]", "returnByValue": True})
            v = r.get("result", {}).get("value") or ["", ""]
            return str(v[0]), str(v[1])
        except CdpError:
            return self.info.get("title", ""), self.info.get("url", "")

    def verbs(self, limit: int = 400) -> List[Dict[str, Any]]:
        """Every interactive control of the page, from the browser's own accessibility tree (shadow DOM included)."""
        try:
            self.call("Accessibility.enable")
        except CdpError:
            pass
        tree = self.call("Accessibility.getFullAXTree", timeout=15.0).get("nodes", [])
        out: List[Dict[str, Any]] = []
        seen: Dict[Tuple[str, str], int] = {}
        for n in tree:
            if n.get("ignored"):
                continue
            role = ((n.get("role") or {}).get("value") or "").lower()
            name = ((n.get("name") or {}).get("value") or "").strip()
            if role not in INTERACTIVE_ROLES or not name or len(name) > 90 or "backendDOMNodeId" not in n:
                continue
            props = {p.get("name"): (p.get("value") or {}).get("value") for p in n.get("properties", [])}
            if props.get("disabled") is True and role not in ("button",):
                continue
            key = (role, name.lower())
            seen[key] = seen.get(key, 0) + 1
            state = {k: props[k] for k in ("checked", "expanded", "selected", "pressed", "focused", "disabled") if k in props}
            val = (n.get("value") or {}).get("value")
            out.append({"label": name, "role": ROLE_MAP.get(role, role), "ax_role": role, "node": n["backendDOMNodeId"], "ordinal": seen[key], "state": state, "value": val, "enabled": props.get("disabled") is not True})
            if len(out) >= limit:
                break
        return out

    def ax_signature(self) -> str:
        """A short fingerprint of what the page shows (names of interactive controls + their states): a click that changed the page changes it."""
        import hashlib
        try:
            vs = self.verbs(limit=300)
        except CdpError:
            return ""
        return hashlib.sha1(json.dumps([(v["label"], v["role"], sorted(v["state"].items(), key=str), str(v["value"])[:40]) for v in vs], default=str).encode()).hexdigest()[:12]

    # ---- acting
    def _object(self, backend_node: int) -> str:
        return self.call("DOM.resolveNode", {"backendNodeId": backend_node}).get("object", {}).get("objectId", "")

    def click(self, backend_node: int) -> Tuple[bool, str]:
        """Scroll the element into view and click it with a real pointer sequence at its centre (works for custom widgets that ignore element.click()); falls back to element.click()."""
        try:
            self.call("DOM.scrollIntoViewIfNeeded", {"backendNodeId": backend_node})
        except CdpError:
            pass
        try:
            box = self.call("DOM.getBoxModel", {"backendNodeId": backend_node}).get("model", {})
            q = box.get("content") or box.get("border") or []
            if len(q) >= 8:
                x = (q[0] + q[2] + q[4] + q[6]) / 4.0
                y = (q[1] + q[3] + q[5] + q[7]) / 4.0
                for typ, extra in (("mouseMoved", {}), ("mousePressed", {"button": "left", "clickCount": 1}), ("mouseReleased", {"button": "left", "clickCount": 1})):
                    self.call("Input.dispatchMouseEvent", {"type": typ, "x": x, "y": y, **extra})
                return True, f"CDP pointer click at ({int(x)},{int(y)})"
        except CdpError:
            pass
        try:
            oid = self._object(backend_node)
            self.call("Runtime.callFunctionOn", {"objectId": oid, "functionDeclaration": "function(){ this.click(); }"})
            return True, "CDP element.click()"
        except CdpError as exc:
            return False, f"CDP click failed: {exc}"

    def type_into(self, backend_node: int, text: str, replace: bool = True) -> Tuple[bool, str]:
        try:
            self.call("DOM.focus", {"backendNodeId": backend_node})
            if replace:
                oid = self._object(backend_node)
                self.call("Runtime.callFunctionOn", {"objectId": oid, "functionDeclaration": "function(){ if (this.select) this.select(); else if (this.setSelectionRange) this.setSelectionRange(0, (this.value||'').length); }"})
            self.call("Input.insertText", {"text": text})
            return True, f"CDP insertText ({len(text)} chars)"
        except CdpError as exc:
            return False, f"CDP type failed: {exc}"

    def key(self, key: str) -> Tuple[bool, str]:
        codes = {"enter": ("Enter", 13), "tab": ("Tab", 9), "escape": ("Escape", 27), "backspace": ("Backspace", 8), "delete": ("Delete", 46), "space": (" ", 32), "up": ("ArrowUp", 38),
                 "down": ("ArrowDown", 40), "left": ("ArrowLeft", 37), "right": ("ArrowRight", 39), "home": ("Home", 36), "end": ("End", 35), "pageup": ("PageUp", 33), "pagedown": ("PageDown", 34)}
        k, vk = codes.get(key.lower(), (key, 0))
        try:
            for typ in ("keyDown", "keyUp"):
                p: Dict[str, Any] = {"type": typ, "key": k, "code": {"Enter": "Enter", " ": "Space"}.get(k, k), "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}       # sites read event.code as well as event.key
                if typ == "keyDown" and key.lower() == "enter":
                    p["text"] = "\r"
                self.call("Input.dispatchKeyEvent", p)
            return True, f"CDP key {k}"
        except CdpError as exc:
            return False, f"CDP key failed: {exc}"

    def navigate(self, url: str) -> Tuple[bool, str]:
        try:
            self.call("Page.navigate", {"url": url})
            time.sleep(0.8)
            return True, f"CDP navigate {url}"
        except CdpError as exc:
            return False, str(exc)

    def reload(self) -> Tuple[bool, str]:
        try:
            self.call("Page.reload", {})
            return True, "CDP Page.reload"
        except CdpError as exc:
            return False, str(exc)

    def history(self, delta: int) -> Tuple[bool, str]:
        try:
            h = self.call("Page.getNavigationHistory")
            i = h.get("currentIndex", 0) + delta
            entries = h.get("entries", [])
            if not (0 <= i < len(entries)):
                return False, "no such history entry"
            self.call("Page.navigateToHistoryEntry", {"entryId": entries[i]["id"]})
            return True, f"CDP history {'back' if delta < 0 else 'forward'}"
        except CdpError as exc:
            return False, str(exc)


class CdpBrowser:
    def __init__(self, port: int):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.pages: Dict[str, CdpPage] = {}
        self._bws: Any = None
        self._bn = 0

    def alive(self) -> bool:
        try:
            _http_json(self.base + "/json/version", 1.5)
            return True
        except Exception:
            return False

    def wait(self, seconds: float = 20.0) -> bool:
        end = time.time() + seconds
        while time.time() < end:
            if self.alive():
                return True
            time.sleep(0.3)
        return False

    def version(self) -> Dict[str, Any]:
        return _http_json(self.base + "/json/version")

    def targets(self) -> List[Dict[str, Any]]:
        """The pages (tabs) of the browser, in the order the protocol lists them."""
        return [t for t in _http_json(self.base + "/json/list") if t.get("type") == "page"]

    def page(self, index: int = 0, match: str = "") -> Optional[CdpPage]:
        ts = self.targets()
        if match:
            ts = [t for t in ts if match.lower() in (t.get("url", "") + " " + t.get("title", "")).lower()] or ts
        if not ts or index >= len(ts):
            return None
        t = ts[index]
        pg = self.pages.get(t["id"])
        if pg is None:
            pg = CdpPage(t)
            self.pages[t["id"]] = pg
        return pg

    # ---- browser-level commands (the outcome of the shortcut the guide names)
    def _browser_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import websocket
        if self._bws is None:
            self._bws = websocket.create_connection(self.version()["webSocketDebuggerUrl"], timeout=8, suppress_origin=True)
        self._bn += 1
        i = self._bn
        self._bws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        end = time.time() + 8
        while time.time() < end:
            msg = json.loads(self._bws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise CdpError(f"{method}: {msg['error'].get('message', msg['error'])}")
                return msg.get("result", {})
        raise CdpError(f"{method}: timed out")

    def new_tab(self, url: str = "about:blank", new_window: bool = False) -> Tuple[bool, str]:
        try:
            r = self._browser_call("Target.createTarget", {"url": url, "newWindow": new_window})
            time.sleep(0.6)
            return True, f"CDP Target.createTarget {'(new window) ' if new_window else ''}-> {r.get('targetId', '')[:8]}"
        except Exception as exc:
            return False, str(exc)

    def close_tab(self, target_id: str = "") -> Tuple[bool, str]:
        try:
            ts = self.targets()
            if len(ts) <= 1 and not target_id:
                return False, "the only tab: closing it would close the browser"
            tid = target_id or ts[-1]["id"]
            self._browser_call("Target.closeTarget", {"targetId": tid})
            self.pages.pop(tid, None)
            time.sleep(0.5)
            return True, f"CDP Target.closeTarget {tid[:8]}"
        except Exception as exc:
            return False, str(exc)

    def activate(self, index: int) -> Tuple[bool, str]:
        try:
            ts = self.targets()
            if not (0 <= index < len(ts)):
                return False, "no such tab"
            self._browser_call("Target.activateTarget", {"targetId": ts[index]["id"]})
            return True, f"CDP Target.activateTarget #{index + 1}"
        except Exception as exc:
            return False, str(exc)

    def close(self) -> None:
        for p in list(self.pages.values()):
            p.close()
        self.pages.clear()
        try:
            if self._bws is not None:
                self._bws.close()
        except Exception:
            pass
        self._bws = None


# What the PROTOCOL can do to a tabbed Chromium window - an ability list of the toolkit, not of any application. `intent` finds the guide's own name for it (its shortcut table:
# 'Ctrl+T  Open a new tab'); `label` is the neutral name used when the guide has none.
CAPABILITIES: List[Dict[str, Any]] = [
    {"kind": "new_tab", "intent": r"\bnew tab\b|\bopen a (?:new )?tab\b", "label": "New tab", "desc": "opens a new tab"},
    {"kind": "new_window", "intent": r"\bnew window\b|\bopen a (?:new )?window\b", "label": "New window", "desc": "opens a new window"},
    {"kind": "close_tab", "intent": r"\bclose (?:the |a |this |current )?tab\b", "label": "Close tab", "desc": "closes the current tab"},
    {"kind": "reload", "intent": r"\breload\b|\brefresh\b", "label": "Reload", "desc": "reloads the page"},
    {"kind": "back", "intent": r"\bgo back\b|\bprevious page\b|^back$", "label": "Back", "desc": "goes back one page"},
    {"kind": "forward", "intent": r"\bgo forward\b|\bnext page\b|^forward$", "label": "Forward", "desc": "goes forward one page"},
    {"kind": "next_tab", "intent": r"\bnext tab\b|\bswitch to the next tab\b", "label": "Next tab", "desc": "switches to the next tab"},
    {"kind": "prev_tab", "intent": r"\bprevious tab\b|\bswitch to the previous tab\b", "label": "Previous tab", "desc": "switches to the previous tab"},
]
