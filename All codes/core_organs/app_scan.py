"""
app_scan.py -- fast, adaptive, headless app scanning (desktop UIA + web via CDP).

Desktop (scan_desktop)
  * time-budgeted breadth-first UIA walk (default 1.2 s) instead of fixed depth/node caps, so a tiny
    app finishes in ms and a huge one is cut by TIME, never by a depth guess;
  * adaptive sampling: a container with dozens of same-role children (lists, grids, file cells) is
    sampled (first/last few) and counted, not exhaustively expanded;
  * popups/menus/dialogs of the same process are scanned too (headless_input.popup_windows);
  * measured stats -> a DYNAMIC difficulty score (depth, node count, unnamed/custom-control ratio,
    sparsity). There is no per-app list anywhere: Electron/custom-drawn apps score hard because
    their UIA tree IS sparse, and the scan then says needs_vision=True.

Web (scan_web_tab / WebAppWatcher)
  * attaches to Chrome's CDP port (9222), enumerates interactive elements + DOM depth with one
    Runtime.evaluate (no screenshot, no clicking);
  * WebAppWatcher polls the tab list; the first time an ORIGIN is seen it is scanned and stored in
    a sqlite registry (new web apps are learned automatically; known origins are not re-scanned
    until stale).
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from core_organs import headless_input as hin

logger = logging.getLogger("hojaiga.app_scan")

try:
    import uiautomation as auto
except Exception:  # pragma: no cover
    auto = None

ACTIONABLE = {"button", "edit", "combobox", "dropdownbutton", "splitbutton", "menuitem", "checkbox",
              "radiobutton", "tabitem", "listitem", "treeitem", "hyperlink", "slider", "spinner",
              "document", "thumb", "toolbarbutton"}
MIN_NODES = 120        # floor walked regardless of budget
HARD_EXTRA_S = 4.0     # absolute cap past the budget
_SAMPLE_OVER = 30   # containers with more same-role children than this are sampled
_SAMPLE_HEAD, _SAMPLE_TAIL = 8, 2


@dataclass
class ScanResult:
    kind: str                       # "desktop" | "web"
    target: str
    elements: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        s = self.stats
        return (f"{self.kind}:{self.target[:28]} nodes={s.get('nodes')} actionable={s.get('actionable')} "
                f"depth={s.get('max_depth')} {s.get('ms')}ms diff={s.get('difficulty')}"
                f"({s.get('difficulty_score')}) vision={s.get('needs_vision')} trunc={s.get('truncated')}")


def _difficulty(nodes: int, depth: int, named_ratio: float, custom_ratio: float, actionable: int) -> Tuple[float, str, bool]:
    sparse = actionable < 8 or (nodes > 30 and named_ratio < 0.15)
    score = (min(nodes / 400.0, 1.0) * 30 + min(depth / 20.0, 1.0) * 20
             + (1.0 - named_ratio) * 25 + custom_ratio * 15 + (25 if sparse else 0))
    label = "easy" if score < 35 else "medium" if score < 65 else "hard"
    if sparse:
        label = "hard"   # a UIA-sparse app (Electron/custom-drawn) cannot be driven structurally
    return round(score, 1), label, sparse


# ---------------------------------------------------------------------------
# Desktop
# ---------------------------------------------------------------------------

def _walk(root, hwnd: int, budget_deadline: float, max_nodes: int, acc: Dict[str, Any]) -> None:
    queue: List[Tuple[Any, int]] = [(root, 0)]
    while queue:
        if (time.perf_counter() > budget_deadline and acc["nodes"] >= MIN_NODES) or acc["nodes"] >= max_nodes                 or time.perf_counter() > budget_deadline + HARD_EXTRA_S:
            acc["truncated"] = True
            return
        c, depth = queue.pop(0)
        try:
            role = (c.ControlTypeName or "").lower().replace("control", "")
            name = (c.Name or "").strip()
            acc["nodes"] += 1
            acc["max_depth"] = max(acc["max_depth"], depth)
            if name:
                acc["named"] += 1
            if role in ("custom", "pane", "group", "image"):
                acc["custom"] += 1
            if role in ACTIONABLE and (name or role in ("edit", "document")):
                try:
                    r = c.BoundingRectangle
                    bbox = (r.left, r.top, r.right, r.bottom)
                except Exception:
                    bbox = (0, 0, 0, 0)
                acc["elements"].append({"name": name, "role": role, "bbox": bbox, "hwnd": hwnd,
                                        "aid": str(getattr(c, "AutomationId", "") or "")})
            kids = c.GetChildren()
        except Exception:
            continue
        if len(kids) > _SAMPLE_OVER:
            acc["sampled_containers"] += 1
            acc["skipped"] += len(kids) - (_SAMPLE_HEAD + _SAMPLE_TAIL)
            kids = kids[:_SAMPLE_HEAD] + kids[-_SAMPLE_TAIL:]
        for k in kids:
            queue.append((k, depth + 1))


def scan_desktop(hwnd: int, budget_ms: int = 1200, max_nodes: int = 3000) -> ScanResult:
    """Headless, time-budgeted UIA scan of a window and its popups."""
    t0 = time.perf_counter()
    acc: Dict[str, Any] = {"nodes": 0, "named": 0, "custom": 0, "max_depth": 0, "elements": [],
                           "truncated": False, "sampled_containers": 0, "skipped": 0}
    state = hin.window_state(hwnd)
    title = ""
    if auto is None or not hin.is_alive(hwnd):
        return ScanResult("desktop", str(hwnd), [], {"error": "no-uia-or-window", "ms": 0})
    try:
        root = auto.ControlFromHandle(hwnd)
        # the budget starts AFTER the root is acquired (UWP/Electron roots can take >1 s cold),
        # and a floor of MIN_NODES is always walked so a slow first touch never yields an empty scan
        deadline = time.perf_counter() + budget_ms / 1000.0
        title = (root.Name or "")[:40] if root else ""
        if root is not None:
            _walk(root, hwnd, deadline, max_nodes, acc)
        for ph in hin.popup_windows(hwnd)[:6]:
            if time.perf_counter() > deadline:
                acc["truncated"] = True
                break
            pr = auto.ControlFromHandle(ph)
            if pr is not None:
                _walk(pr, ph, deadline, max_nodes, acc)
    except Exception as exc:  # noqa: BLE001
        acc["error"] = f"{type(exc).__name__}: {exc}"
    n = max(1, acc["nodes"])
    named_ratio, custom_ratio = acc["named"] / n, acc["custom"] / n
    score, label, sparse = _difficulty(n, acc["max_depth"], named_ratio, custom_ratio, len(acc["elements"]))
    stats = {"nodes": acc["nodes"], "actionable": len(acc["elements"]), "max_depth": acc["max_depth"],
             "ms": int((time.perf_counter() - t0) * 1000), "truncated": acc["truncated"],
             "sampled_containers": acc["sampled_containers"], "skipped_nodes": acc["skipped"],
             "named_ratio": round(named_ratio, 2), "custom_ratio": round(custom_ratio, 2),
             "difficulty": label, "difficulty_score": score, "needs_vision": sparse,
             "window_state": state.get("state"), "error": acc.get("error", "")}
    return ScanResult("desktop", title or str(hwnd), acc["elements"], stats)


# ---------------------------------------------------------------------------
# Web (CDP)
# ---------------------------------------------------------------------------

CDP_PORTS = (9222, 9223, 9224)

_WEB_JS = r"""(()=>{
 const sel='a[href],button,input,textarea,select,[role=button],[role=link],[role=menuitem],[role=tab],[role=textbox],[role=searchbox],[role=checkbox],[contenteditable=true]';
 const out=[]; let hidden=0;
 document.querySelectorAll(sel).forEach(e=>{const r=e.getBoundingClientRect();
   if(r.width<2||r.height<2){hidden++;return;}
   const name=(e.getAttribute('aria-label')||e.innerText||e.value||e.placeholder||e.title||'').trim().replace(/\s+/g,' ').slice(0,80);
   out.push({name:name,role:e.getAttribute('role')||e.tagName.toLowerCase(),bbox:[r.left|0,r.top|0,r.right|0,r.bottom|0],type:e.type||''});});
 let depth=0; const all=document.getElementsByTagName('*'); const step=Math.max(1,(all.length/1500)|0);
 for(let i=0;i<all.length;i+=step){let d=0,e=all[i];while(e.parentElement){e=e.parentElement;d++;} if(d>depth)depth=d;}
 return {url:location.href,title:document.title,nodes:all.length,depth:depth,iframes:document.querySelectorAll('iframe').length,
         shadow:[...all].slice(0,2000).filter(e=>e.shadowRoot).length,hidden:hidden,els:out.slice(0,500),total:out.length};})()"""


def cdp_tabs(port: int = 9222, timeout: float = 2.0) -> List[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=timeout) as r:
            return [t for t in json.loads(r.read().decode()) if t.get("type") == "page"]
    except Exception:
        return []


def _cdp_eval(ws_url: str, expression: str, timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    import websocket  # websocket-client
    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expression, "returnByValue": True}}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return (msg.get("result", {}).get("result", {}) or {}).get("value")
    finally:
        ws.close()
    return None


def scan_web_tab(tab: Dict[str, Any]) -> ScanResult:
    t0 = time.perf_counter()
    url = tab.get("url", "")
    try:
        data = _cdp_eval(tab["webSocketDebuggerUrl"], _WEB_JS)
    except Exception as exc:  # noqa: BLE001
        return ScanResult("web", url, [], {"error": f"{type(exc).__name__}: {exc}",
                                           "ms": int((time.perf_counter() - t0) * 1000)})
    if not data:
        return ScanResult("web", url, [], {"error": "no-data", "ms": int((time.perf_counter() - t0) * 1000)})
    els = data.get("els", [])
    named = sum(1 for e in els if e.get("name"))
    named_ratio = named / max(1, len(els))
    score, label, sparse = _difficulty(data.get("nodes", 0), data.get("depth", 0), named_ratio,
                                       min(1.0, (data.get("iframes", 0) + data.get("shadow", 0)) / 10.0), len(els))
    stats = {"nodes": data.get("nodes"), "actionable": data.get("total"), "max_depth": data.get("depth"),
             "ms": int((time.perf_counter() - t0) * 1000), "truncated": data.get("total", 0) > len(els),
             "iframes": data.get("iframes"), "shadow_roots": data.get("shadow"), "named_ratio": round(named_ratio, 2),
             "difficulty": label, "difficulty_score": score, "needs_vision": sparse,
             "title": data.get("title", "")[:60], "url": data.get("url", url)[:120]}
    return ScanResult("web", data.get("url", url), els, stats)


# ---------------------------------------------------------------------------
# Web app registry + watcher: new origin detected -> scanned once, learned
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("HOJAIGA_WEBAPP_DB", r"D:\new_automation\webapps.db")
_STALE_S = float(os.environ.get("HOJAIGA_WEBAPP_RESCAN_S", "900"))


class WebAppRegistry:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS webapps(
                origin TEXT PRIMARY KEY, title TEXT, first_seen REAL, last_scan REAL, scans INTEGER,
                nodes INTEGER, actionable INTEGER, depth INTEGER, difficulty TEXT, needs_vision INTEGER)""")

    def _c(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def origin(url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}" if p.scheme in ("http", "https") and p.netloc else ""

    def known(self, origin: str) -> Optional[Tuple[float, int]]:
        with self._c() as c:
            r = c.execute("SELECT last_scan, scans FROM webapps WHERE origin=?", (origin,)).fetchone()
        return (r[0], r[1]) if r else None

    def record(self, origin: str, res: ScanResult) -> None:
        s, now = res.stats, time.time()
        with self._c() as c:
            c.execute("""INSERT INTO webapps(origin,title,first_seen,last_scan,scans,nodes,actionable,depth,difficulty,needs_vision)
                         VALUES(?,?,?,?,1,?,?,?,?,?)
                         ON CONFLICT(origin) DO UPDATE SET title=excluded.title,last_scan=excluded.last_scan,
                           scans=scans+1,nodes=excluded.nodes,actionable=excluded.actionable,depth=excluded.depth,
                           difficulty=excluded.difficulty,needs_vision=excluded.needs_vision""",
                      (origin, s.get("title", ""), now, now, s.get("nodes") or 0, s.get("actionable") or 0,
                       s.get("max_depth") or 0, s.get("difficulty"), int(bool(s.get("needs_vision")))))

    def all(self) -> List[Tuple]:
        with self._c() as c:
            return c.execute("SELECT origin,title,scans,nodes,actionable,depth,difficulty,needs_vision FROM webapps ORDER BY last_scan DESC").fetchall()


class WebAppWatcher:
    """Polls Chrome's tab list; scans each NEW origin once (and stale ones occasionally)."""

    def __init__(self, registry: Optional[WebAppRegistry] = None, interval_s: float = 3.0, on_new=None):
        self.reg = registry or WebAppRegistry()
        self.interval_s = interval_s
        self.on_new = on_new
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.detected: List[str] = []

    def poll_once(self) -> List[ScanResult]:
        done: List[ScanResult] = []
        for port in CDP_PORTS:
            for tab in cdp_tabs(port):
                origin = self.reg.origin(tab.get("url", ""))
                if not origin:
                    continue
                seen = self.reg.known(origin)
                if seen and (time.time() - seen[0]) < _STALE_S:
                    continue
                res = scan_web_tab(tab)
                if res.stats.get("error"):
                    continue
                is_new = seen is None
                self.reg.record(origin, res)
                if is_new:
                    self.detected.append(origin)
                    logger.info("[webapp] NEW web app detected + scanned: %s -> %s", origin, res.summary())
                    if self.on_new:
                        try:
                            self.on_new(origin, res)
                        except Exception:
                            pass
                done.append(res)
        return done

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def _run():
            while not self._stop.is_set():
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("webapp watcher: %s", exc)
                self._stop.wait(self.interval_s)

        self._thread = threading.Thread(target=_run, daemon=True, name="webapp-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
