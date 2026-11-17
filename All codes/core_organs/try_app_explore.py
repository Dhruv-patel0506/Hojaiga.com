"""
try_app_explore -- DEEP exploration of a web app: click what opens, click what is inside it, keep going until there is nothing new, then come back.

    home page
     |- opener (menu / dropdown / tab / button)   -> click it -> NEW controls appear  -> each of those is clicked in turn
     |     |- item that opens a sub-menu          -> click it -> more controls         -> and so on, down to `max_depth`
     |     |- item that opens a DIALOG / panel    -> read what is in it, click what is in THAT, close it again
     |     |- item that opens ANOTHER PAGE        -> that page is explored as a state of its own: its side bar, its dropdowns, its tabs, everything on it
     |     `- item that opens a NEW WINDOW / tab  -> read it, close it
     |- control that only opens when the pointer RESTS on it (hover menus) -> found by hovering when the click showed nothing
     `- list that only shows more when scrolled (side bars, long menus)    -> scrolled, the new rows are explored too

ORDER: breadth first by level (everything at level 1, then everything revealed by those, ...), so a limited budget is spread over the whole app instead of spent in the first corner. Siblings are
kept together, so a menu that stays open is not reopened for each of its items.

COVERAGE is reported honestly: how many distinct clickable controls were SEEN, how many were CLICKED, and for each one left over WHY (budget ran out / risky / leads to another site / duplicate).

Safety (same rules as the rest of --show): the throw-away browser profile only; never types; never submits a form; never follows a link to another site (listed as 'external'); anything whose name or
address suggests an irreversible or account action (delete, sign out, pay, buy, send, publish, save, share, install, subscribe, ...) is skipped and listed. Hard budgets on clicks, depth, pages and seconds.
"""
from __future__ import annotations

import contextlib
import heapq
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

RISKY_HREF = re.compile(r"(logout|signout|sign-out|log-out|delete|remove|checkout|cart|payment|billing|unsubscribe|download|\.(zip|exe|msi|dmg|pdf|csv|xlsx?|docx?|pptx?|apk)(\?|$))", re.I)
SKIP_TAGS = {"input", "textarea", "select"}
SKIP_ROLES = {"option", "checkbox input", "text input", "password input", "email input", "search input", "number input", "radio input", "file input", "submit input", "textarea", "select", "slider"}

CONTAINERS_JS = """() => {
  const sc = [...document.querySelectorAll('*')].filter(e => { const s = getComputedStyle(e); const r = e.getBoundingClientRect();
     return (s.overflowY === 'auto' || s.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 60 && r.width > 120 && r.height > 120 && r.bottom > 0 && r.top < innerHeight; })
     .sort((a, b) => (b.clientHeight * b.clientWidth) - (a.clientHeight * a.clientWidth)).slice(0, 5);
  sc.forEach((e, i) => e.setAttribute('data-hj-sc', String(i)));
  return sc.map(e => ({h: e.scrollHeight, c: e.clientHeight}));
}"""
SCROLL_STEP_JS = """([i, y]) => { const e = document.querySelector('[data-hj-sc="' + i + '"]'); if (e) e.scrollTop = y; }"""


def ckey(c: Dict[str, Any]) -> Tuple[str, str]:
    return (c["role"], c["label"])


def goto_step(url: str, label: str) -> Dict[str, Any]:
    return {"role": "@page", "label": label, "url": url, "x": 0, "y": 0, "tag": "", "id": ""}


class Explorer:
    def __init__(self, page: Any, ctx: Any, home_url: str, collect: Callable[[], Dict[str, Any]], point: Callable[..., None], hud: Callable[[str, List[str]], None],
                 danger: Any, finder: Optional[Callable[..., Optional[Dict[str, Any]]]] = None, pace: float = 0.35, max_clicks: int = 400, max_depth: int = 6, max_pages: int = 25, budget_s: float = 900.0, max_kids: int = 80,
                 say: Callable[[str], None] = print, max_links: int = -1, media_cb: Optional[Callable[[], Optional[Dict[str, Any]]]] = None, max_media: int = 3) -> None:
        self.page, self.ctx, self.home, self.collect, self.point, self.hud, self.danger = page, ctx, home_url, collect, point, hud, danger
        self.pace, self.max_clicks, self.max_depth, self.max_pages, self.deadline, self.say, self.max_kids = pace, max_clicks, max_depth, max_pages, time.monotonic() + budget_s, say, max_kids
        self.origin = "{0.scheme}://{0.netloc}".format(urlparse(home_url))
        self.done: set = set()
        self.queued: set = set()
        self.nodes: List[Dict[str, Any]] = []
        self.skipped: List[str] = []
        self.external: List[str] = []
        self.pages_seen: Dict[str, str] = {}
        self.clicks = 0
        self.seq = 0
        self.heap: List[Tuple[int, int, List[Dict[str, Any]]]] = []
        self.log: List[str] = []
        self.all_controls: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self.seen_state: Dict[Tuple[str, str], str] = {}
        self.max_depth_reached = 0
        self.finder = finder
        self.why: str = ""
        self.t: Dict[str, float] = {}
        # BUTTONS (anything that is not a plain link) and LINKS have budgets of their own: a docs site with 5,000 links must not use up the clicks the app's own buttons and menus need
        self.max_links = max_links if max_links >= 0 else max(30, max_clicks // 4)
        self.ui_clicks = 0
        self.link_clicks = 0
        self.kind_of: Dict[Tuple[str, str], str] = {}
        self.media_cb, self.max_media = media_cb, max_media
        self.media: List[Dict[str, Any]] = []
        self.media_seen: set = set()

    def tick(self, name: str, t0: float) -> float:
        now = time.perf_counter()
        self.t[name] = self.t.get(name, 0.0) + (now - t0)
        return now

    # ------------------------------------------------------------------ helpers
    def out_of_budget(self) -> bool:
        return (self.ui_clicks >= self.max_clicks and self.link_clicks >= self.max_links) or time.monotonic() > self.deadline

    def maybe_media(self, node: Optional[Dict[str, Any]] = None) -> None:
        """If the page in front of us has a player, find out what it shows and says (web_media). At most `max_media` per site, each only once."""
        if self.media_cb is None or len(self.media) >= self.max_media:
            return
        try:
            rec = self.media_cb()
        except Exception as e:
            self.log.append(f"media read failed: {type(e).__name__}")
            return
        if not rec:
            return
        key = rec.get("title", "") or rec.get("url", "").split("#")[0]                     # the same video seen again (another route to the same page) is read once
        if key in self.media_seen or not rec.get("frames"):
            return
        self.media_seen.add(key)
        self.media.append(rec)
        self.log.append(f"VIDEO read: {rec.get('summary', '')[:90]}")
        if node is not None:
            node["media"] = rec.get("summary", "")[:300]

    def clickable(self, c: Dict[str, Any]) -> Tuple[bool, str]:
        name = c.get("label") or c.get("title") or ""
        if c["tag"] in SKIP_TAGS or c["role"] in SKIP_ROLES:
            return False, ""
        if not name.strip():
            return False, ""
        if self.danger.search(name):
            return False, "risky"
        href = c.get("href") or ""
        if c["tag"] == "a" and href:
            if href.startswith(("mailto:", "tel:", "javascript:")) or RISKY_HREF.search(href):
                return False, "risky"
            if href.startswith("http") and not href.startswith(self.origin):
                self.external.append(f"{name[:30]} -> {urlparse(href).netloc}")
                return False, "external"
        return True, ""

    def note(self, c: Dict[str, Any]) -> None:
        """Register a control as SEEN (for the coverage report)."""
        k = ckey(c)
        ok, why = self.clickable(c)
        if ok or why:
            self.seen_state.setdefault(k, "pending" if ok else why)
            self.kind_of.setdefault(k, "link" if self.klass(c) > 0 else "button")
        self.all_controls.setdefault((c["role"], c["label"], c["x"] // 8, c["y"] // 8), c)

    def find_live(self, desc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.finder is not None:                                                               # cheap targeted read: no rectangles for the controls that do not match
            return self.finder(desc["role"], desc["label"], desc["x"], desc["y"])
        best, bd = None, 1e9
        for c in self.collect()["controls"]:
            if ckey(c) == (desc["role"], desc["label"]):
                d = abs(c["x"] - desc["x"]) + abs(c["y"] - desc["y"])
                if d < bd:
                    best, bd = c, d
        return best if best is not None and bd < 600 else None

    DIALOGS_JS = """() => [...document.querySelectorAll('[role=dialog], [aria-modal=true], dialog[open]')].filter(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
        return r.width > 20 && r.height > 20 && s.visibility !== 'hidden' && s.display !== 'none'; }).length"""

    def dialogs(self) -> int:
        with contextlib.suppress(Exception):
            return int(self.page.evaluate(self.DIALOGS_JS))
        return 0

    def settle(self, quick: float = 0.45) -> None:
        time.sleep(quick)
        with contextlib.suppress(Exception):
            self.page.wait_for_load_state("domcontentloaded", timeout=1500)

    def goto(self, url: str) -> None:
        with contextlib.suppress(Exception):
            for p in list(self.ctx.pages):
                if p is not self.page:
                    p.close()
        with contextlib.suppress(Exception):
            self.page.keyboard.press("Escape")
        if self.page.url.split("#")[0].rstrip("/") != url.split("#")[0].rstrip("/"):
            with contextlib.suppress(Exception):
                self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                with contextlib.suppress(Exception):
                    self.page.wait_for_load_state("networkidle", timeout=4000)
        time.sleep(0.25)

    def to_home(self) -> None:
        self.goto(self.home)

    def wait_for(self, desc: Dict[str, Any], tries: int = 2) -> Optional[Dict[str, Any]]:
        for _ in range(tries):
            el = self.find_live(desc)
            if el is not None:
                return el
            time.sleep(0.4)
        self.why = f"'{desc['label'][:30]}' not on screen"
        return None

    def reach(self, path: List[Dict[str, Any]]) -> bool:
        """Get to the state where the last element of `path` can be clicked: it may already be there (siblings of a menu that stayed open); otherwise start from the last PAGE step in the path
        (or home) and replay the clicks after it."""
        if self.find_live(path[-1]) is not None:
            return True
        for hard in (False, True):                                                              # second try: a full reload, because a dialog left in some other state hides the first step
            start = max((i for i, s in enumerate(path[:-1]) if s["role"] == "@page"), default=-1)
            url = path[start]["url"] if start >= 0 else self.home
            steps = path[start + 1:-1] if start >= 0 else path[:-1]
            if hard:
                with contextlib.suppress(Exception):
                    self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    with contextlib.suppress(Exception):
                        self.page.wait_for_load_state("networkidle", timeout=4000)
                    time.sleep(0.4)
            else:
                self.goto(url)
            ok = True
            for step in steps:
                el = self.wait_for(step)
                if el is None:
                    ok = False
                    break
                if not self.act(el, step.get("via", "click")):
                    self.why = f"could not click '{step['label'][:30]}'"
                    ok = False
                    break
                self.settle(0.9)                                                               # menus fade in; a second look finds what the first one missed
            if ok and self.wait_for(path[-1]) is not None:
                return True
        return False

    def act(self, el: Dict[str, Any], via: str = "click") -> bool:
        loc = self.page.locator(f"[data-hj-id='{el['id']}']").first
        with contextlib.suppress(Exception):
            loc.scroll_into_view_if_needed(timeout=900)                                              # the cursor should point at where the control IS on screen
            r = loc.evaluate("e => { const b = e.getBoundingClientRect(); return [b.left + scrollX, b.top + scrollY, b.width, b.height]; }", timeout=900)
            el = dict(el, x=int(r[0]), y=int(r[1]), w=int(r[2]), h=int(r[3]))
        try:
            self.point(el, "#ff9d00")
            time.sleep(self.pace * 0.6)
            if via == "hover":
                loc.hover(timeout=2000)
            else:
                loc.click(timeout=1200)
            return True
        except Exception:
            pass
        if via != "hover":
            with contextlib.suppress(Exception):                                                # covered / moving: the element's own click()
                loc.evaluate("e => e.click()", timeout=1000)
                return True
        return False

    def breadcrumb(self, path: List[Dict[str, Any]]) -> str:
        return " > ".join((p["label"] or p["role"])[:60] for p in path if p["role"] != "@page")

    def reveal_scroll(self) -> List[Dict[str, Any]]:
        """Scroll every scrollable panel (side bars, long menus) in steps and collect what appears; rows that only exist once scrolled to are controls too."""
        found: List[Dict[str, Any]] = []
        with contextlib.suppress(Exception):
            known = {(c["role"], c["label"], c["x"] // 8, c["y"] // 8) for c in self.collect()["controls"]}
            conts = self.page.evaluate(CONTAINERS_JS)
            for step in range(1, 6):
                moved = False
                for i, c in enumerate(conts):
                    y = int(step * c["c"] * 0.8)
                    if y < c["h"]:
                        self.page.evaluate(SCROLL_STEP_JS, [i, y])
                        moved = True
                if not moved:
                    break
                time.sleep(0.22)
                for c in self.collect()["controls"]:
                    k = (c["role"], c["label"], c["x"] // 8, c["y"] // 8)
                    if k not in known:
                        known.add(k)
                        found.append(c)
            for i in range(len(conts)):
                self.page.evaluate(SCROLL_STEP_JS, [i, 0])
        return found

    # ------------------------------------------------------------------ one click
    def try_click(self, path: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        target = path[-1]
        t0 = time.perf_counter()
        ok_reach = self.reach(path)
        t0 = self.tick("reach", t0)
        if not ok_reach:
            self.nodes.append({"path": self.breadcrumb(path), "outcome": "unreachable", "why": self.why, "n_new": 0, "depth": sum(1 for p in path if p["role"] != "@page")})
            return None
        el = self.find_live(target)
        if el is None:
            return None
        before_ctrls = self.collect()["controls"]
        before = {(c["role"], c["label"], c["x"] // 8, c["y"] // 8) for c in before_ctrls}
        before_named = {(c["role"], c["label"]) for c in before_ctrls}
        # WHAT WAS ON SCREEN when this control was chosen (up to 40 labelled controls in view, the target among them): the natural, many-choices situation that action training data needs
        tgt_txt = f"{target['role']}: {target['label']}"
        ctx_list = [f"{c['role']}: {c['label']}" for c in before_ctrls if c.get("inview") and c.get("label")]
        if tgt_txt in ctx_list:
            i0 = ctx_list.index(tgt_txt)
            ctx_list = ctx_list[max(0, min(i0 - 20, len(ctx_list) - 40)):][:40]
        else:
            ctx_list = [tgt_txt] + ctx_list[:39]
        pages_before, url_before, dialogs_before = len(self.ctx.pages), self.page.url, self.dialogs()
        title_before = ""
        with contextlib.suppress(Exception):
            title_before = self.page.title()[:80]
        t0 = self.tick("before_read", t0)
        acted = self.act(el, target.get("via", "click"))
        t0 = self.tick("click", t0)
        if not acted:
            self.nodes.append({"path": self.breadcrumb(path), "outcome": "could not click", "n_new": 0, "depth": sum(1 for p in path if p["role"] != "@page")})
            return None
        self.clicks += 1
        if self.klass(target) > 0:
            self.link_clicks += 1
        else:
            self.ui_clicks += 1
        self.settle()
        t0 = self.tick("settle", t0)
        node: Dict[str, Any] = {"path": self.breadcrumb(path), "depth": sum(1 for p in path if p["role"] != "@page"), "outcome": "nothing visible happened", "n_new": 0, "children": [],
                                "prefix": path, "target": tgt_txt, "context": ctx_list, "on_page": title_before, "url_path": urlparse(url_before).path or "/"}
        self.max_depth_reached = max(self.max_depth_reached, node["depth"])
        if len(self.ctx.pages) > pages_before:                                                    # a child window / tab
            newp = self.ctx.pages[-1]
            info: Dict[str, Any] = {}
            with contextlib.suppress(Exception):
                newp.wait_for_load_state("domcontentloaded", timeout=4000)
                info = {"title": newp.title(), "url": newp.url}
            node.update(outcome="opened a child window", window=info)
            with contextlib.suppress(Exception):
                newp.close()
            self.log.append(f"{self.breadcrumb(path)[-40:]} -> child window '{info.get('title', '')[:24]}'")
            return node
        after_url = self.page.url
        if after_url.split("#")[0] != url_before.split("#")[0] or (after_url != url_before and urlparse(after_url).path != urlparse(url_before).path):
            if not after_url.startswith(self.origin):
                node.update(outcome="left the site (not followed)", page={"url": after_url})
                self.external.append(f"{target['label'][:30]} -> {urlparse(after_url).netloc}")
                self.to_home()
                return node
            data = self.collect()
            sig = urlparse(after_url).path or "/"
            for c in data["controls"]:
                self.note(c)
            kids = list(data["controls"])                                                        # enqueue() decides what may be clicked and records what was refused as risky
            node.update(outcome="opened a new page", page={"title": data["title"][:60], "url": after_url, "controls": len(data["controls"])}, n_new=len(data["controls"]))
            self.log.append(f"{self.breadcrumb(path)[-40:]} -> PAGE '{data['title'][:24]}' ({len(data['controls'])} controls)")
            self.maybe_media(node)
            if sig not in self.pages_seen and len(self.pages_seen) < self.max_pages:
                self.pages_seen[sig] = data["title"]
                with contextlib.suppress(Exception):
                    for c in self.reveal_scroll():                                             # side bars / long lists that only render once scrolled
                        self.note(c)
                        if self.clickable(c)[0]:
                            kids.append(c)
                node["children"] = kids
                node["prefix"] = [goto_step(after_url, data["title"][:30])]                    # this page can be reached directly from now on
            return node
        now = self.collect()
        new = [c for c in now["controls"] if (c["role"], c["label"], c["x"] // 8, c["y"] // 8) not in before and (c["role"], c["label"]) not in before_named]
        t0 = self.tick("after_read", t0)
        if not new and (target.get("opener") or target.get("zone") == "nav") and target.get("tag") != "a":      # menus that open when the pointer RESTS on them
            with contextlib.suppress(Exception):
                self.page.mouse.move(3, 3)
                time.sleep(0.2)
                if self.act(el, "hover"):
                    time.sleep(0.7)
                    new = [c for c in self.collect()["controls"] if (c["role"], c["label"], c["x"] // 8, c["y"] // 8) not in before and (c["role"], c["label"]) not in before_named]
                    if new:
                        target["via"] = "hover"
                        node["outcome"] = "opens on hover"
        t0 = self.tick("hover_try", t0)
        for c in new:
            self.note(c)
        if new:
            dialog = self.dialogs() > dialogs_before
            if node["outcome"] != "opens on hover":
                node["outcome"] = "opened a dialog" if dialog else "revealed a menu / panel"
            node.update(n_new=len(new), revealed=[f"{c['role']}: {c['label']}" for c in new[:40]])
            node["children"] = list(new)
            self.log.append(f"{self.breadcrumb(path)[-40:]} -> {node['outcome'].upper()}: {len(new)} new ({', '.join(c['label'][:12] for c in new[:3] if c['label'])})")
            for c in new[:3]:
                self.point(c, "#ff9d00")
                time.sleep(self.pace * 0.3)
            if dialog:
                self.maybe_media(node)                                                           # a video that plays inside a dialog (a product intro, a demo)
        else:
            self.log.append(f"{self.breadcrumb(path)[-40:]} -> nothing visible")
        return node

    # ------------------------------------------------------------------ the search
    @staticmethod
    def klass(c: Dict[str, Any]) -> int:
        """0 = buttons / openers / tabs (they open the app's inside), 1 = links in a nav bar / side bar / header, 2 = links in the page body, 3 = footer links (they only lead away)."""
        if c.get("tag") != "a" or c.get("opener"):
            return 0
        z = c.get("zone", "body")
        return 1 if z == "nav" else 3 if z == "footer" else 2

    def push(self, depth: int, path: List[Dict[str, Any]]) -> None:
        self.seq += 1
        heapq.heappush(self.heap, (self.klass(path[-1]) * 100 + depth, self.seq, path))

    LANG = re.compile(r"(language|langue|sprache|lingua|idioma|taal|\u8bed\u8a00|\u8a00\u8a9e|\u092d\u093e\u0937\u093e|locale|country|region)", re.I)

    def enqueue(self, kids: List[Dict[str, Any]], prefix: List[Dict[str, Any]], depth: int) -> None:
        if prefix and self.LANG.search(prefix[-1].get("label", "")):
            # a language / country picker: choosing an entry re-draws the SAME screen translated, which would be explored again in every language. The list is read, not walked.
            for c in kids:
                self.seen_state.setdefault(ckey(c), "language / country list (read, not walked)")
            return
        order = sorted(kids, key=lambda c: (0 if c.get("opener") else 1, c["y"] // 40, c["x"]))
        # a long run of look-alike entries (44 languages, 60 countries) is a LIST, not 44 features: the openers are all kept, ten of the plain entries are sampled, the rest are counted
        plain = [c for c in order if not c.get("opener")]
        if len(order) > 25 and len(plain) > 0.8 * len(order):
            keep = set(id(c) for c in order if c.get("opener")) | set(id(c) for c in plain[:10])
            dropped = [c for c in order if id(c) not in keep]
            for c in dropped:
                self.seen_state.setdefault(ckey(c), "sampled out (long list)")
            order = [c for c in order if id(c) in keep]
        n = 0
        for c in order:
            ok, why = self.clickable(c)
            k = ckey(c)
            if not ok:
                if why == "risky":
                    self.skipped.append(c["label"] or c["title"])
                continue
            if k in self.done or k in self.queued:
                continue
            self.queued.add(k)
            self.push(depth, prefix + [c])
            n += 1
            if n >= self.max_kids:
                break

    def run(self, first_level: List[Dict[str, Any]]) -> Dict[str, Any]:
        for c in first_level:
            self.note(c)
        with contextlib.suppress(Exception):
            for c in self.reveal_scroll():
                self.note(c)
                first_level.append(c)
        self.maybe_media(None)
        self.enqueue(first_level, [], 1)
        while self.heap and not self.out_of_budget():
            key, _, path = heapq.heappop(self.heap)
            depth = key % 100
            t = path[-1]
            k = ckey(t)
            if k in self.done:
                continue
            if key // 100 == 0 and self.ui_clicks >= self.max_clicks:
                self.seen_state[k] = "button budget spent"
                continue
            if key // 100 > 0 and self.link_clicks >= self.max_links:
                self.seen_state[k] = "link budget spent"
                continue
            self.done.add(k)
            self.seen_state[k] = "clicked"
            self.hud(f"HOJAIGA DEEP EXPLORE  buttons {self.ui_clicks}/{self.max_clicks}  links {self.link_clicks}/{self.max_links}  level {depth}  queue {len(self.heap)}", self.log[-12:] + [f"-> {self.breadcrumb(path)[-60:]}"])
            try:
                node = self.try_click(path)
            except Exception as e:                                                               # one bad click never ends the exploration
                self.nodes.append({"path": self.breadcrumb(path), "outcome": "error: " + type(e).__name__, "n_new": 0, "depth": depth})
                with contextlib.suppress(Exception):
                    self.to_home()
                continue
            if node is None:
                continue
            kids = node.pop("children", [])
            prefix = node.pop("prefix", path)
            self.nodes.append(node)
            if kids and node["depth"] < self.max_depth:
                self.enqueue(kids, prefix, depth + 1)
        self.to_home()
        by: Dict[str, int] = {}
        for n in self.nodes:
            by[n["outcome"]] = by.get(n["outcome"], 0) + 1
        tree = [f"{'  ' * (max(1, n.get('depth', 1)) - 1)}{n['path'].split(' > ')[-1]}  ->  {n['outcome']}" + (f" ({n['n_new']})" if n.get("n_new") else "") for n in self.nodes]
        left = [k for k, v in self.seen_state.items() if v == "pending"]
        reasons: Dict[str, int] = {}
        for v in self.seen_state.values():
            reasons[v] = reasons.get(v, 0) + 1
        stopped = "time" if time.monotonic() > self.deadline else "button and link budgets" if (self.ui_clicks >= self.max_clicks and self.link_clicks >= self.max_links) else "nothing left to try"
        btn = [k for k, kind in self.kind_of.items() if kind == "button" and self.seen_state.get(k) not in ("risky", "external")]
        lnk = [k for k, kind in self.kind_of.items() if kind == "link" and self.seen_state.get(k) not in ("risky", "external")]
        clicked = lambda ks: sum(1 for k in ks if self.seen_state.get(k) == "clicked")
        by_kind = {"buttons_seen": len(btn), "buttons_clicked": clicked(btn), "buttons_pct": round(100.0 * clicked(btn) / max(1, len(btn)), 1), "links_seen": len(lnk), "links_clicked": clicked(lnk),
                   "links_pct": round(100.0 * clicked(lnk) / max(1, len(lnk)), 1), "buttons_left": [f"{k[0]}: {k[1]}"[:50] + f" ({self.seen_state.get(k)})" for k in btn if self.seen_state.get(k) != "clicked"][:25]}
        coverage = {"distinct_controls_seen": len(self.seen_state), "clicked": reasons.get("clicked", 0), "not_clicked": {k: v for k, v in reasons.items() if k != "clicked"},
                    "left_over_sample": [f"{r}: {l}"[:50] for r, l in left[:25]], "pct_clicked": round(100.0 * reasons.get("clicked", 0) / max(1, len(self.seen_state) - reasons.get("risky", 0) - reasons.get("external", 0)), 1), **by_kind}
        return {"clicks": self.clicks, "max_depth": self.max_depth_reached, "outcomes": by, "nodes": self.nodes, "tree": tree, "pages": dict(self.pages_seen), "coverage": coverage,
                "external": list(dict.fromkeys(self.external))[:20], "skipped_risky": list(dict.fromkeys(self.skipped))[:40], "stopped_by": stopped, "controls": list(self.all_controls.values()),
                "seconds_by_phase": {k: round(v, 1) for k, v in self.t.items()}, "media": self.media, "button_clicks": self.ui_clicks, "link_clicks": self.link_clicks}
