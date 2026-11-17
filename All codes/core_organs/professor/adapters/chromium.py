"""
professor.adapters.chromium -- the DevTools-protocol ROUTE of the Executor for a Chromium-family window the Professor owns (a browser, an Electron shell, a WebView2 host).

Everything it knows it LEARNS from the application it is attached to, nothing is a list of one application's pages or commands:

  commands      what the protocol CAN do to a tabbed Chromium window (open / close / switch a tab, reload, history: adapters.cdp.CAPABILITIES) named in the words the application's own GUIDE uses
                (its shortcut table: 'Ctrl+T - Open a new tab') and filed under the menus the guide names ('More > ...')
  pages         the application's internal pages: the page list the browser itself publishes is filtered by what the guide talks about, each relevant page is opened once and its controls are
                read from the browser's accessibility tree; links and navigation controls found on a page lead to more pages (breadth-first, depth and time bounded). Page titles become destinations
                ('Settings', 'History'): the words a guide uses for them
  hazards       a page that makes the browser exit is written down BEFORE it is opened; the next run reads the note and never opens it again (learnt, not listed)
  routes        verbs of kind 'adapter': a command or a page control is performed through the protocol; a control that lives on another page first navigates there
  state         tab list, current URL / title and a fingerprint of the page's controls, merged into the before/after snapshot so the executor's delta SEES what a protocol action did
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from .. import config as CFG
from ..harvest import Catalog, Verb, verb_id
from ..schema import fold
from .cdp import CAPABILITIES, CdpBrowser, CdpError, CdpPage

CACHE_PATH = os.path.join(CFG.DATA_DIR, "adapters", "chromium_pages.json")
# classes of internal page that are not pages a person reads: crash tests, diagnostics, tracing, dialogs / side panels / first-run flows. (Token CLASSES of the Chromium family, not names of one
# application's pages; whatever else turns out to kill the browser is learnt and remembered.)
HAZARD_TOKENS = re.compile(r"crash|kill|hang|quit|restart|dino|internals|debug|trac(?:e|ing)|sandbox|gpu|memory|inducebrowser|net-export|top-chrome|side-panel|optin|signin|sync|dialog|promo|intro|welcome|"
                           r"feedback|policy|enterprise|reset-password|inspect|devtools|safe-browsing|serviceworker|discards|webrtc", re.I)


class BrowserGone(Exception):
    def __init__(self, url: str):
        super().__init__(f"the browser exited while opening {url}")
        self.url = url


def _words(text: str) -> Set[str]:
    return {(w[:-1] if len(w) > 3 and w.endswith("s") else w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


class ChromiumAdapter:
    name = "cdp"

    def __init__(self, browser: CdpBrowser, log: Callable[[str], None] = lambda s: None, guide_shortcuts: Optional[Dict[str, List[Dict[str, str]]]] = None, guide_terms: Optional[Sequence[str]] = None,
                 guide_menus: Optional[Dict[str, Any]] = None, cache_path: str = CACHE_PATH):
        self.b = browser
        self.log = log
        self.current_id = ""
        self.cache_path = cache_path
        self.guide_shortcuts = guide_shortcuts or {}
        self.guide_vocab: Set[str] = set()
        for t in (guide_terms or []):
            self.guide_vocab |= _words(t)
        self.guide_menus = guide_menus or {}
        self._ver = ""
        self.scheme = ""
        self.harvested: Dict[str, int] = {}
        self.hazards: Set[str] = set()

    # ------------------------------------------------------------------------------------------------------------------ cache + hazards
    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, c: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                json.dump(c, fh, indent=1, ensure_ascii=False)
        except Exception:
            pass

    def _mark_inflight(self, url: str) -> None:
        c = self._load()
        c["inflight"] = url
        self._save(c)

    def _clear_inflight(self) -> None:
        c = self._load()
        c.pop("inflight", None)
        self._save(c)

    # ------------------------------------------------------------------------------------------------------------------ pages
    def _target(self) -> Optional[Dict[str, Any]]:
        ts = self.b.targets()
        if not ts:
            return None
        t = next((x for x in ts if x["id"] == self.current_id), None)
        if t is None:
            t = ts[0]
            self.current_id = t["id"]
        return t

    def current(self) -> Optional[CdpPage]:
        t = self._target()
        if t is None:                                                      # every tab is gone (a step closed them): the browser needs one to live - open a blank one
            try:
                self.b.new_tab("about:blank")
                t = self._target()
            except Exception:
                t = None
        if t is None:
            return None
        return self._page_of(t)

    def _wait_loaded(self, pg: CdpPage, seconds: float = 6.0) -> None:
        end = time.time() + seconds
        while time.time() < end:
            try:
                r = pg.call("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True}, timeout=3.0)
                if r.get("result", {}).get("value") == "complete":
                    time.sleep(0.5)
                    return
            except CdpError:
                pass
            time.sleep(0.3)

    def _await_target(self, url_part: str, need_title: bool = False, seconds: float = 5.0) -> Optional[Dict[str, Any]]:
        """The tab whose URL contains `url_part` (a new tab lists as about:blank for a moment before its navigation commits)."""
        end = time.time() + seconds
        last = None
        while time.time() < end:
            try:
                targets = self.b.targets()
            except Exception:
                return last                                                # the browser stopped answering: the caller decides whether it is gone
            for x in targets:
                if url_part in x.get("url", ""):
                    last = x
                    if not need_title or (x.get("title") and x.get("title") != x.get("url")):
                        return x
            time.sleep(0.25)
        return last

    def _page_of(self, tg: Dict[str, Any]) -> CdpPage:
        pg = self.b.pages.get(tg["id"]) or CdpPage(tg)
        self.b.pages[tg["id"]] = pg
        return pg

    def _links(self, pg: CdpPage) -> List[str]:
        """Same-scheme links on the page, pierced through shadow roots (a settings page is nothing but web components)."""
        js = ("(function(){var out=[];function walk(n){ if(n.querySelectorAll){ n.querySelectorAll('a[href]').forEach(a=>out.push(a.href)); "
              "n.querySelectorAll('*').forEach(e=>{ if(e.shadowRoot) walk(e.shadowRoot); }); } } walk(document); return out;})()")
        try:
            r = pg.call("Runtime.evaluate", {"expression": js, "returnByValue": True})
            return sorted({u.split("#")[0] for u in (r.get("result", {}).get("value") or []) if u.startswith(self.scheme + "://")})
        except CdpError:
            return []

    # ------------------------------------------------------------------------------------------------------------------ the guide's words
    def _guide_label_for(self, intent: "re.Pattern", default: str) -> Tuple[str, str]:
        """(label, shortcut) for a capability: the guide's own shortcut table names it ('Ctrl+T' - 'Open a new tab'); otherwise the neutral default label."""
        for chord, ents in self.guide_shortcuts.items():
            for e in ents:
                if intent.search(e.get("label", "")):
                    lab = re.sub(r"\s+", " ", e["label"]).strip(" .:-")
                    return (lab if 2 <= len(lab) <= 40 else default), chord
        return default, ""

    def _menu_heads_for(self, label: str) -> List[str]:
        """The menus the guide files a command under ('More > Settings'): every head whose nested items name this label."""
        want = fold(label)
        heads: List[str] = []

        def walk(node: Dict[str, Any]) -> bool:
            for k, sub in node.items():
                if fold(k) == want:
                    return True
                if isinstance(sub, dict) and walk(sub):
                    return True
            return False
        for h, sub in self.guide_menus.items():
            if isinstance(sub, dict) and walk(sub):
                heads.append(h)
        return heads

    def _add(self, cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], path: List[str], label: str, aid: str, role: str, desc: str, shortcut: str = "", source: str = "cdp", enabled: bool = True,
             checked: bool = False) -> bool:
        key = (tuple(path), fold(label))
        if key in have:
            return False
        have.add(key)
        cat.verbs.append(Verb(verb_id(path, label + ("" if source == "cdp" else "#" + aid[-8:])), label, list(path), shortcut, desc, enabled, checked, "", 0, aid, role, [source], "measured", "safe"))
        return True

    # ------------------------------------------------------------------------------------------------------------------ harvest
    def harvest_all(self, cat: Catalog, budget_s: float = 150.0) -> Dict[str, Any]:
        t0 = time.time()
        c = self._load()
        if c.get("inflight"):                                              # the previous run died while opening this page: never again
            self.hazards.add(c["inflight"])
            c.setdefault("hazards", [])
            if c["inflight"] not in c["hazards"]:
                c["hazards"].append(c["inflight"])
            c.pop("inflight", None)
            self._save(c)
        self.hazards |= set(c.get("hazards", []))
        ver = self.b.version()
        self._ver = ver.get("Browser", "")
        m = re.match(r"(?i)(edg|chrome|headlesschrome|brave|vivaldi|opera)", self._ver)
        self.scheme = "edge" if (m and m.group(1).lower() == "edg") else ("chrome" if m else "")
        have = {(tuple(v.path), fold(v.label)) for v in cat.verbs}
        n_cmd = self.harvest_commands(cat, have)
        rep: Dict[str, Any] = {"browser": self._ver, "commands": n_cmd, "hazards_known": len(self.hazards), "pages": 0, "page_verbs": 0, "edges": 0}
        if self.scheme:
            try:
                rep.update(self.crawl(cat, have, budget_s - (time.time() - t0)))
            except BrowserGone as gone:
                rep["browser_gone_at"] = gone.url
                c = self._load()
                c.setdefault("hazards", [])
                if gone.url not in c["hazards"]:
                    c["hazards"].append(gone.url)
                c.pop("inflight", None)
                self._save(c)
                raise
        cat.sources["cdp"] = cat.sources.get("cdp", 0) + n_cmd
        cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))
        rep["seconds"] = round(time.time() - t0, 1)
        return rep

    def harvest_commands(self, cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]]) -> int:
        n = 0
        for cap in CAPABILITIES:
            label, chord = self._guide_label_for(re.compile(cap["intent"], re.I), cap["label"])
            aid = f"cdp-browser:{cap['kind']}"
            for path in (["Browser"], *[[h] for h in self._menu_heads_for(label)]):
                n += 1 if self._add(cat, have, path, label, aid, "menu_item", cap["desc"], chord) else 0
            if fold(label) != fold(cap["label"]):
                n += 1 if self._add(cat, have, ["Browser"], cap["label"], aid, "menu_item", cap["desc"], chord) else 0
        return n

    def _relevant(self, url: str) -> bool:
        if HAZARD_TOKENS.search(url) or url in self.hazards:
            return False
        if not self.guide_vocab:
            return True
        return bool(_words(re.sub(r"^\w+://", "", url)) & self.guide_vocab)

    def crawl(self, cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], budget_s: float, max_pages: int = 40, max_depth: int = 2, max_clicks: int = 10) -> Dict[str, Any]:
        """Open the application's own pages the guide talks about, read each one's controls, follow what they link to."""
        t0 = time.time()
        queue: List[Tuple[str, int]] = []
        seen: Set[str] = set()
        # the page list the browser publishes about itself
        self.b.new_tab(f"{self.scheme}://chrome-urls/")
        tg = self._await_target("chrome-urls")
        if tg is None:
            self.b.new_tab(f"{self.scheme}://about/")
            tg = self._await_target("about")
        listed: List[str] = []
        if tg is not None:
            pg = self._page_of(tg)
            self._wait_loaded(pg)
            for _try in range(4):
                try:
                    listed = sorted({v["label"].split("#")[0].rstrip("/") + "/" for v in pg.verbs(limit=600) if v["ax_role"] == "link" and v["label"].startswith(self.scheme + "://")})
                except CdpError:
                    listed = []
                if len(listed) >= 10:
                    break
                time.sleep(1.0)
            self.b.close_tab(tg["id"])
        for u in listed:
            if self._relevant(u):
                queue.append((u, 0))
        n_pages = n_verbs = n_edges = 0
        titles: Dict[str, str] = {}
        while queue and n_pages < max_pages and time.time() - t0 < budget_s:
            url, depth = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            self._mark_inflight(url)
            ok, _h = self.b.new_tab(url)
            if not ok:
                if not self.b.alive():
                    raise BrowserGone(url)
                continue
            tg = self._await_target(url.rstrip("/"), need_title=True, seconds=4.0)
            if not self.b.alive():
                raise BrowserGone(url)
            if tg is None:
                continue
            title = (tg.get("title") or "").strip()
            titles[url] = title
            try:
                pg = self._page_of(tg)
                self._wait_loaded(pg)
                vs = pg.verbs()
                links = self._links(pg) if depth < max_depth else []
            except CdpError as exc:
                self.log(f"page {url}: {exc}")
                pg, vs, links = None, [], []
            ptitle = re.sub(r"^\w+://", "", title) or url
            path = [f"page: {ptitle[:40]}"]
            for v in vs:
                if self._add(cat, have, path, v["label"], f"cdp:{url}|{v['role']}|{v['ordinal']}", v["role"], f"page:{url}", "", "cdp-page", bool(v["enabled"]), v["state"].get("checked") in (True, "true")):
                    n_verbs += 1
            # destinations: the page's own title is what a guide calls it ('Settings'), specific tail first
            parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", title) if p.strip()]
            for lab in (parts[-1:] + (parts[:1] if len(parts) > 1 else [])):
                lab = re.sub(r"^\w+://", "", lab)
                if 2 <= len(lab) <= 40 and fold(lab) not in ("google chrome", "chrome", "new tab"):
                    aid = f"cdp-browser:goto:{url}"
                    for hp in (["Browser"], *[[h] for h in self._menu_heads_for(lab)]):
                        self._add(cat, have, hp, lab, aid, "menu_item", f"opens {url}")
            # navigation controls without a link (menu items, tabs): click, see where the URL goes, come back
            clicks = 0
            if depth < max_depth and pg is not None:
                for v in vs:
                    if clicks >= max_clicks or time.time() - t0 > budget_s:
                        break
                    if v["role"] not in ("menu_item", "tab", "link") or fold(v["label"]) in {fold(p) for p in parts}:
                        continue
                    before = pg.title_url()[1]
                    pg.click(v["node"])
                    clicks += 1
                    time.sleep(0.6)
                    after = pg.title_url()[1]
                    if after != before:
                        if after.startswith(self.scheme + "://") and after.split("#")[0].rstrip("/") != url.rstrip("/"):
                            n_edges += 1
                            a2 = after.split("#")[0]
                            links.append(a2)
                            self._add(cat, have, ["Browser"], v["label"], f"cdp-browser:goto:{a2}", "menu_item", f"opens {a2}")
                        pg.navigate(url)
                        self._wait_loaded(pg)
            for l in links:
                if l not in seen and self._relevant(l) and l.startswith(self.scheme + "://"):
                    queue.append((l, depth + 1))
            n_pages += 1
            self.harvested[url] = len(vs)
            self._clear_inflight()
            try:
                self.b.close_tab(tg["id"])
            except Exception:
                pass
            if not self.b.alive():
                raise BrowserGone(url)
        c = self._load()
        c["titles"] = {**c.get("titles", {}), **titles}
        c["when"] = time.time()
        c["browser"] = self._ver
        self._save(c)
        self.current_id = ""
        return {"pages": n_pages, "page_verbs": n_verbs, "edges": n_edges, "listed": len(listed), "relevant": sum(1 for u in listed if self._relevant(u)), "by_page": dict(list(self.harvested.items())[:30])}

    # ------------------------------------------------------------------------------------------------------------------ acting
    def owns(self, v: Verb) -> bool:
        return "cdp" in (v.sources or []) or "cdp-page" in (v.sources or [])

    def act(self, v: Verb, text: str = "") -> Tuple[bool, str]:
        try:
            if "cdp" in v.sources:
                return self._browser_command(v)
            return self._page_control(v, text)
        except CdpError as exc:
            return False, f"CDP: {exc}"

    def _browser_command(self, v: Verb) -> Tuple[bool, str]:
        kind = (v.aid or "").split(":", 1)[-1]
        if kind.startswith("goto:"):
            pg = self.current()
            if pg is None:
                return False, "no page"
            ok, how = pg.navigate(kind[5:])
            self._wait_loaded(pg)
            return ok, how
        ts = self.b.targets()
        idx = next((i for i, t in enumerate(ts) if t["id"] == self.current_id), 0)
        if kind == "new_tab":
            ok, how = self.b.new_tab()
            ts2 = self.b.targets()
            self.current_id = ts2[0]["id"] if ts2 else ""                  # the browser lists the newest tab first
            return ok, how
        if kind == "new_window":
            ok, how = self.b.new_tab(new_window=True)
            ts2 = self.b.targets()
            self.current_id = ts2[0]["id"] if ts2 else ""
            return ok, how
        if kind == "close_tab":
            cur = self._target()
            ok, how = self.b.close_tab(cur["id"] if cur else "")
            self.current_id = ""
            return ok, how
        if kind == "reload":
            pg = self.current()
            return pg.reload() if pg else (False, "no page")
        if kind in ("back", "forward"):
            pg = self.current()
            return pg.history(-1 if kind == "back" else 1) if pg else (False, "no page")
        if kind in ("next_tab", "prev_tab") and ts:
            j = (idx + (1 if kind == "next_tab" else -1)) % len(ts)
            ok, how = self.b.activate(j)
            self.current_id = ts[j]["id"]
            return ok, how
        return False, f"unknown browser command {kind}"

    def _page_control(self, v: Verb, text: str) -> Tuple[bool, str]:
        m = re.match(r"cdp:(.+?)\|([^|]*)\|(\d+)$", v.aid or "")
        if not m:
            return False, "not a page control"
        url, role, ordinal = m.group(1), m.group(2), int(m.group(3))
        pg = self.current()
        if pg is None:
            return False, "no page"
        _t, cur = pg.title_url()

        def here() -> List[Dict[str, Any]]:
            return [x for x in pg.verbs() if fold(x["label"]) == fold(v.label) and x["role"] == role]
        vs = here()                                                           # a navigation entry ('Appearance') exists on every settings page: act on the page we are ON when it is there
        if not vs and not cur.startswith(url.rstrip("/")):
            ok, how = pg.navigate(url)
            if not ok:
                return False, how
            self._wait_loaded(pg)
            for _ in range(5):                                                # the page's accessibility tree is built lazily after the load
                vs = here()
                if vs:
                    break
                time.sleep(0.8)
        if not vs:
            return False, f"'{v.label}' is not on the current page ({cur[:50]}) nor on {url}"
        tgt = next((x for x in vs if x["ordinal"] == ordinal), vs[0])
        if text and tgt["role"] in ("field", "dropdown"):
            return pg.type_into(tgt["node"], text)
        if tgt["role"] == "field":
            return pg.type_into(tgt["node"], text or "Hojaiga test")
        return pg.click(tgt["node"])

    def insert_text(self, text: str) -> Tuple[bool, str]:
        pg = self.current()
        if pg is None:
            return False, "no page"
        try:
            pg.call("Input.insertText", {"text": text})
            return True, f"CDP insertText ({len(text)} chars)"
        except CdpError as exc:
            return False, str(exc)

    def key(self, key: str) -> Tuple[bool, str]:
        pg = self.current()
        return pg.key(key) if pg else (False, "no page")

    def reset(self) -> None:
        """One blank tab: what the next procedure starts from."""
        ts = self.b.targets()
        for t in ts[:-1]:
            self.b.close_tab(t["id"])
        self.current_id = ""
        pg = self.current()
        if pg is not None and not pg.title_url()[1].startswith("about:blank"):
            pg.navigate("about:blank")

    # ------------------------------------------------------------------------------------------------------------------ state for before/after
    def state_texts(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        try:
            ts = self.b.targets()
            out["cdp|tabs"] = " || ".join(f"{t.get('title', '')[:30]} <{t.get('url', '')[:50]}>" for t in ts)
            t = next((x for x in ts if x["id"] == self.current_id), ts[0] if ts else None)
            if t is not None:
                pg = self._page_of(t)
                out["cdp|current"] = f"{t.get('title', '')[:40]} <{t.get('url', '')[:60]}>"
                out["cdp|page"] = pg.ax_signature()
        except Exception:
            pass
        return out

    def close(self) -> None:
        self.b.close()
