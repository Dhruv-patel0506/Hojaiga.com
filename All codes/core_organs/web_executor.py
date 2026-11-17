"""
web_executor -- do a task on a website, with the RAG's knowledge of that site, and say honestly whether it worked.

    r = run_web_task(rag, "go to the Pricing page on todoist.com")          # or "search for 'wireless mouse' on bestbuy.com", "type 'hello' into the name field on file:///x/form.html"
    r["status"]    DONE | NEEDS_CONFIRM | FAILED | NO_SITE        r["steps"], r["evidence"], r["screenshot"]

How a task is done (headless browser, nothing on the person's screen, never the person's own Chrome or profile):
  1 the site     a URL / domain / local file in the words, else a web app the RAG knows by name (webapp:<host>)
  2 the plan     what the task needs: navigate to a named control, search for text, type text into a named field
  3 knowledge    the RAG's stored procedure for this site and goal is replayed first (rag.proc.find_procedures); when it is not there or does not get there, the live page is read: controls whose words
                 match the goal are clicked, menus are opened when nothing matches (a bounded budget)
  4 the gate     every control is judged by mind.consequence BEFORE it is pressed; a control that would pay / send / publish / delete / sign out / agree stops the task with NEEDS_CONFIRM and the question,
                 unless the person approved it in the command (yes=True). Typing into a password / card field is never done.
  5 the proof    DONE only when the page shows it: the address or title moved and carries the goal's words, a menu with the goal's items opened, or the typed text is in the field / the results page has it
  6 learning     a path that worked is filed as a 'learned' procedure (so the next ask is a replay), and the stored procedure that was used gains or loses reliability
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from core_organs.mind import consequence as CQ

REPORTS = os.environ.get("HOJAIGA_REPORTS", os.path.join("D:" + os.sep, "new_automation", "reports"))
_URL = re.compile(r"(https?://[^\s'\"<>]+|file:///[^\s'\"<>]+|[A-Za-z]:[\\/][^\s'\"<>]+\.html?)", re.I)
_DOMAIN = re.compile(r"\b((?:[a-z0-9\-]+\.)+(?:com|org|net|io|gov|in|co|dev|app|ai|edu|uk|us|info|me|tv|sh)(?:/[^\s'\"<>]*)?)\b", re.I)
_FILLER = {"the", "a", "an", "on", "in", "to", "of", "and", "page", "go", "open", "click", "press", "find", "get", "show", "me", "please", "navigate", "visit", "then", "section", "button", "link", "menu", "site", "website", "web",
           "tab", "for", "search", "using", "my", "i", "want", "how", "do", "can", "you"}


def toks(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower())]


def full_url(t: str) -> str:
    t = (t or "").strip().strip(".,;")
    if re.match(r"^[A-Za-z]:[\\/]", t):
        return "file:///" + t.replace("\\", "/")
    return t if re.match(r"^(https?|file)://", t, re.I) else "https://" + t.lstrip("/")


# ---- 1 the site ----------------------------------------------------------------------------------------------------------------------------------------
def _public_host(url: str) -> bool:
    """Only http(s) to a host whose every address is public (the guard microsoft/UFO's web adapter keeps against requests to internal addresses)."""
    import ipaddress
    import socket
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))}
    except OSError:
        return False
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def page_tables(html: str) -> Tuple[List[List[List[str]]], str, str]:
    """(tables as rows of cell texts, the visible text, the title) from a page's HTML, with the standard library only."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.tables: List[List[List[str]]] = []
            self.stack: List[List[List[str]]] = []
            self.cell: Optional[List[str]] = None
            self.text: List[str] = []
            self.skip = 0
            self.title, self.in_title = "", False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "noscript"):
                self.skip += 1
            elif tag == "title":
                self.in_title = True
            elif tag == "table":
                self.stack.append([])
            elif tag == "tr" and self.stack:
                self.stack[-1].append([])
            elif tag in ("td", "th") and self.stack:
                self.cell = []
            elif tag in ("br", "p", "li", "div", "h1", "h2", "h3"):
                self.text.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style", "noscript"):
                self.skip = max(0, self.skip - 1)
            elif tag == "title":
                self.in_title = False
            elif tag in ("td", "th") and self.stack and self.cell is not None:
                if not self.stack[-1]:
                    self.stack[-1].append([])
                self.stack[-1][-1].append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
                self.cell = None
            elif tag == "table" and self.stack:
                t = [r for r in self.stack.pop() if r]
                if len(t) >= 2 and max(len(r) for r in t) >= 2:
                    self.tables.append(t)

        def handle_data(self, data):
            if self.skip:
                return
            if self.in_title:
                self.title += data
            if self.cell is not None:
                self.cell.append(data)
            self.text.append(data)
    p = P()
    with contextlib.suppress(Exception):
        p.feed(html)
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.text))).strip()
    return p.tables, text, p.title.strip()


def best_table(tables: List[List[List[str]]], words: str = "") -> List[List[str]]:
    """The table the step means: most of its words in the table's first rows, then the most cells (a navigation box is small)."""
    want = set(toks(re.sub(r"https?://\S+", " ", words or ""))) - {"table", "the", "of", "a", "list", "data"}   # the page's own address names every table on it

    def score(t):
        head = set(toks(" ".join(" ".join(r) for r in t[:3])))
        return len(want & head) + min(sum(len(r) for r in t), 2000) / 100.0                            # live Oct-28: a 7-row navigation box beat the 87-row data table on header words
    return max(tables, key=score) if tables else []


def read_page(url: str, fetch: Any = None) -> Dict[str, Any]:
    """A page's tables and text for another app (Chrome -> Excel): no browser window, nothing clicked. {'ok', 'tables', 'text', 'title', 'why'}."""
    if fetch is None and not _public_host(url):
        return {"ok": False, "why": f"refused: {url} is not a public http(s) address"}
    try:
        if fetch is not None:
            html = fetch(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hojaiga/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.geturl() != url and not _public_host(r.geturl()):
                    return {"ok": False, "why": "refused: the page redirected to a non-public address"}
                html = r.read(6_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception as e:
        return {"ok": False, "why": f"{type(e).__name__}: {str(e)[:160]}"}
    tables, text, title = page_tables(html)
    return {"ok": bool(tables or text), "tables": tables, "text": text[:20000], "title": title, "why": f"{len(tables)} table(s), {len(text)} chars of text"}


SITE_SYSTEM = "Which website does this task name or need? Reply with its domain only (like example.org), or none."
_SITE_SEEN: Dict[str, str] = {}


def site_by_name(task: str, ask: Any = None, resolves: Any = None) -> str:
    """A site the task names without its address ('search wikipedia for ...', live Oct-27: NO_SITE). The model names the domain; it is used only when a
    word of the task is in the domain and the domain resolves (a made-up domain never becomes a URL)."""
    import socket
    if task in _SITE_SEEN:
        return _SITE_SEEN[task]
    if ask is None:
        from core_organs.mind import app_qa as QA
        ask = lambda system, prompt: QA.ask_llm(prompt, system, timeout=30, max_tokens=20)
    ans = (ask(SITE_SYSTEM, f"Task: \"{task.strip()}\"\nDomain:") or "").strip().lower()
    d = _DOMAIN.search(ans)
    url = ""
    if d:
        dom = d.group(1).split("/")[0].removeprefix("www.")
        words = {w for w in toks(task) if len(w) >= 3}
        if any(w in dom.split(".")[0] for w in words):
            ok = False
            try:
                ok = bool((resolves or socket.getaddrinfo)(dom, 443))
            except Exception:
                ok = False
            url = full_url(dom) if ok else ""
    _SITE_SEEN[task] = url
    return url


def resolve_site(task: str, rag: Any = None, names: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    m = _URL.search(task or "")
    if m:
        url = full_url(m.group(1))
    else:
        d = _DOMAIN.search(task or "")
        url = full_url(d.group(1)) if d else ""
    if not url and rag is not None:
        from core_organs.mind import app_qa as QA
        for disp, key, _s in QA.find_app(task, "", names if names is not None else QA.app_names(rag), rag):
            if key.startswith("webapp:"):
                url = full_url(key.split(":", 1)[1])
                break
    if not url and os.environ.get("HOJAIGA_SITE_BY_NAME", "on").lower() != "off":
        url = site_by_name(task)
    if not url:
        return {}
    u = urlparse(url)
    host = (u.netloc or os.path.basename(u.path)).lower().removeprefix("www.")
    return {"url": url, "host": host, "key": "webapp:" + host, "words": " ".join(toks(host.split(".")[0]))}


# ---- 2 what the task needs ---------------------------------------------------------------------------------------------------------------------------------
def parse_task(task: str, site: Dict[str, str]) -> Dict[str, Any]:
    t = re.sub(_URL, " ", task or "")
    t = re.sub(_DOMAIN, " ", t)
    q = re.search(r"[\"“']([^\"”']{1,200})[\"”']", t)
    quoted = q.group(1) if q else ""
    m = re.search(r"\b(?:type|enter|write|fill(?: in)?)\s+[\"“']([^\"”']+)[\"”']\s+(?:in|into|in the|into the)\s+(?:the\s+)?(.+?)(?:\s+(?:field|box|input|bar))?\s*(?:$|[.,;]| and | then )", t, re.I)
    if m:
        return {"kind": "type", "text": m.group(1), "field": m.group(2).strip(), "label": m.group(2).strip()}
    m = re.search(r"\bsearch(?:\s+for)?\s+[\"“']?(.+?)[\"”']?(?:\s+(?:on|in|at)\s+\S+)?\s*$", t, re.I)
    if m and "search" in t.lower().split()[:3]:
        text = (quoted or m.group(1)).strip()
        for w in toks(site.get("words", "")):                                                         # 'search wikipedia for Alan Turing' on wikipedia searches 'Alan Turing'
            text = re.sub(rf"^(?:{re.escape(w)})\s+(?:for\s+)?", "", text, flags=re.I)
        return {"kind": "search", "text": text or (quoted or m.group(1)).strip(), "label": "search"}
    sw = set(toks(site.get("words", "")))
    label_words = [w for w in toks(t) if w not in _FILLER and w not in sw]
    return {"kind": "navigate", "label": " ".join(label_words), "words": label_words}


# ---- the page ---------------------------------------------------------------------------------------------------------------------------------------------------
def _controls(page: Any) -> List[Dict[str, Any]]:
    from core_organs.harvest import web_tasks_eval as WT
    return [c for c in WT.controls(page) if c.get("label")]


def _click(page: Any, c: Dict[str, Any]) -> bool:
    from core_organs.harvest import web_tasks_eval as WT
    return WT.click_control(page, c)


def _snap(page: Any) -> Dict[str, Any]:
    title = ""
    with contextlib.suppress(Exception):
        title = page.title()
    u = urlparse(page.url)
    return {"url": page.url, "path": u.path + ("?" + u.query if u.query else ""), "title": title, "labels": [c["label"].lower() for c in _controls(page)][:300], "text": _text(page)[:4000]}


def _text(page: Any) -> str:
    with contextlib.suppress(Exception):
        return page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 20000)").lower()
    return ""


def _settle(page: Any) -> None:
    time.sleep(0.5)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("domcontentloaded", timeout=3000)


def landed(page: Any, words: Sequence[str], home: Dict[str, Any], exact_click: bool = False, typed: Sequence[str] = (), ctrl_id: str = "") -> Tuple[bool, str, bool]:
    """Is the page now the thing the goal names? Judged on the page, not by the agent: the address or title moved AND carries the goal's words, or a menu/panel with those words appeared."""
    now = _snap(page)
    frag = urlparse(now.get("url", "")).fragment
    low = (now["title"] + " " + now["path"] + " " + frag.replace("_", " ")).lower()                      # a section is reached by its #anchor ('#Early_life')
    hit = [w for w in words if w in low]
    moved = now["path"] != home["path"] or now["title"] != home["title"] or (frag and frag != urlparse(home.get("url", "")).fragment)
    base = lambda u: ".".join((urlparse(u).hostname or "").split(".")[-2:])
    same_site = not home.get("url") or base(now.get("url", "")) == base(home["url"])
    need = len(words) if len(words) <= 2 else -(-2 * len(words) // 3)                                  # live Oct-28: 'early life' passed on a BBC page carrying only 'early'
    if moved and words and same_site and len(hit) >= need:
        return True, f"the page moved to '{now['title'][:60]}' ({now['path'][:60]}{'#' + frag if frag else ''}) and carries {hit}", False
    new = [l for l in now["labels"] if l not in set(home["labels"])]
    shown = [l for l in new if any(w in l for w in words)]
    if words and len(new) >= 2 and shown:
        return True, f"a menu / panel opened with {len(new)} new controls, including {shown[:3]}", False
    body = now["text"]
    shown_typed = [t for t in typed if t and t.lower() in body and t.lower() not in home.get("text", "")]
    if shown_typed:                                                                                    # text the task typed now stands on the page (an item added to a list, a message posted)
        return True, f"the text typed earlier ('{shown_typed[0][:40]}') now appears on the page", False
    if ctrl_id:
        st = None
        with contextlib.suppress(Exception):
            st = page.evaluate("(i) => { const e = document.querySelector(`[data-hj-id='${i}']`); return e ? [e.getAttribute('aria-selected'), e.getAttribute('aria-expanded'), e.getAttribute('aria-pressed'), e.getAttribute('aria-checked')] : null }", ctrl_id)
        if st and "true" in st:
            return True, "the control now reports itself selected / expanded / pressed", False
    before = set((home.get("text") or "").splitlines())
    added = [l for l in body.splitlines() if l.strip() and l not in before]
    shown_new = [l for l in added if words and all(w in l for w in words)]
    if shown_new:                                                                                      # text that was NOT on the page before now names the goal
        return True, f"new text on the page names the goal: '{shown_new[0][:70]}'", False
    if exact_click and now["text"] != home.get("text", now["text"]):                                   # the control the person named was pressed and the page changed, but the page does not carry the goal's words: real, not proof
        return True, "WEAK: the named control was pressed and the page text changed, but nothing on the page names the goal", True
    return False, f"the page did not show '{' '.join(words)}' (title '{now['title'][:50]}')", False


def _gate(c: Dict[str, Any], goal: str, yes: bool) -> Optional[Dict[str, Any]]:
    a = CQ.classify_label(c.get("label", ""), c.get("role", ""), context=goal)
    if a["gate"] == "confirm" and not yes:
        return {**a, "question": f"About to press '{c['label']}': it {a['consequence']}. Safer: {a['safer']}. Go ahead? (run again with approval)"}
    return None


def _match(cs: Sequence[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    from core_organs.harvest import web_tasks_eval as WT
    return WT.match_controls(cs, label)


# ---- 3 the run --------------------------------------------------------------------------------------------------------------------------------------------------
def run_web_task(rag: Any, task: str, url: str = "", yes: bool = False, show: bool = False, max_clicks: int = 10, out_dir: str = "", names: Optional[Dict[str, str]] = None, browser: Any = None, session: str = "") -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright
    t0 = time.time()
    site = {"url": full_url(url), "host": urlparse(full_url(url)).netloc.lower().removeprefix("www."), "key": "webapp:" + urlparse(full_url(url)).netloc.lower().removeprefix("www."), "words": ""} if url else resolve_site(task, rag, names)
    res: Dict[str, Any] = {"task": task, "status": "NO_SITE", "steps": [], "site": site}
    if not site:
        res["evidence"] = "no site found in the task: give a web address or the name of a web app the system has learned"
        return res
    # 'and' + an action verb starts a new step (live Oct-27: 'search wikipedia for Alan Turing and open the early life section' was searched as one phrase)
    actions = [a for a in re.split(r"\s*(?:;|\bthen\b|\band then\b|\bafter that\b|,?\s*\band\b(?=\s+(?:open|click|go to|scroll|find|type|search|read|select|press|choose|follow)\b))\s*",
                                   task or "", flags=re.I) if a and a.strip()] or [task]
    res["plan"] = [parse_task(a, site) for a in actions]
    out_dir = out_dir or os.path.join(REPORTS, "web_runs", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    with sync_playwright() as pw:
        from core_organs.try_app import launch_browser
        br = browser or launch_browser(pw, headless=not show, args=[] if not show else ["--window-position=30,20", "--window-size=1400,900"])
        try:
            kw: Dict[str, Any] = {}
            if session:                                                                                # opt-in: start already signed in, from the vault (a session the PERSON created); absent or expired = start signed out, and say so
                from core_organs import session_vault as SV
                kw = SV.context_kwargs(session)
                res["session"] = {"site": SV.host_of(session), "used": bool(kw), "note": "" if kw else "no valid stored session: this run is signed out"}
            ctx = br.new_context(viewport={"width": 1440, "height": 820}, locale="en-US", **kw)
            page = ctx.new_page()
            try:
                page.goto(site["url"], wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                res.update(status="FAILED", evidence=f"could not open {site['url']}: {type(e).__name__}")
                return res
            _settle(page)
            first = _snap(page)
            res["start"] = {"url": first["url"], "title": first["title"]}
            ok, evs = True, []
            for act, plan in zip(actions, res["plan"]):                                                # the actions of one task share ONE page session: 'type X into the box; click Add' needs the same page
                home = _snap(page)
                res["weak"] = False                                                                    # weakness is judged on the LAST action: a later action that proves its own result settles it
                if plan["kind"] == "search":
                    ok, ev = _do_search(page, plan, res)
                elif plan["kind"] == "type":
                    ok, ev = _do_type(page, plan, res)
                else:
                    ok, ev = _do_navigate(page, rag, act, site, plan, home, yes, max_clicks, res)
                evs.append(f"[{plan['kind']}] {ev}")
                if not ok:
                    break
            res["evidence"] = " | ".join(evs)
            if res.get("status") != "NEEDS_CONFIRM":
                res["status"] = ("UNVERIFIED" if res.get("weak") else "DONE") if ok else "FAILED"
            shot = os.path.join(out_dir, "end.png")
            with contextlib.suppress(Exception):
                page.screenshot(path=shot)
                res["screenshot"] = shot
            res["end"] = {"url": page.url, "title": _snap(page)["title"]}
        finally:
            if browser is None:
                with contextlib.suppress(Exception):
                    br.close()
    res["seconds"] = round(time.time() - t0, 1)
    if res["status"] == "DONE" and rag is not None and not res.get("weak") and all(p["kind"] == "navigate" for p in res["plan"]):
        _learn(rag, site, task, res)
    return res


def _input_for(cs: Sequence[Dict[str, Any]], hint: str, search: bool = False) -> Optional[Dict[str, Any]]:
    ins = [c for c in cs if c.get("tag") in ("input", "textarea") and not re.search(r"password|hidden|checkbox|radio|submit|button|file", c.get("role", ""), re.I)]
    named = [c for c in ins if c.get("label")]
    if search:
        s = [c for c in ins if re.search(r"search|find|query", (c.get("label", "") + " " + c.get("role", "")), re.I)]
        return (s or ins or [None])[0]
    want = set(toks(hint))
    scored = sorted(((len(want & set(toks(c.get("label", "")))), c) for c in ins), key=lambda x: -x[0])
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return ins[0] if len(ins) == 1 else None                                                           # the page has ONE text field (unlabelled): that is the one meant


def _all_inputs(page: Any) -> List[Dict[str, Any]]:
    from core_organs.harvest import web_tasks_eval as WT
    return WT.controls(page)


def _do_type(page: Any, plan: Dict[str, Any], res: Dict[str, Any]) -> Tuple[bool, str]:
    cs = _all_inputs(page)
    field = _input_for(cs, plan["field"])
    if field is None:
        return False, f"no field on the page is called '{plan['field']}'"
    a = CQ.assess_step("type", field.get("label", ""), typed_text=plan["text"], field=field.get("label", "") + " " + field.get("role", ""))
    if a["gate"] == "block":
        res["status"] = "NEEDS_CONFIRM"
        return False, a["question"]
    assumed = not (set(toks(plan["field"])) & set(toks(field.get("label", ""))))
    loc = page.locator(f"[data-hj-id='{field['id']}']").first
    try:
        loc.fill(plan["text"], timeout=3000)
    except Exception as e:
        return False, f"could not type into '{field['label']}': {type(e).__name__}"
    if assumed:
        res["weak"] = True
    got = ""
    with contextlib.suppress(Exception):
        got = loc.input_value(timeout=1500)
    res["steps"].append({"do": f"typed into '{field['label'] or 'the text field'}'", "ok": got == plan["text"]})
    res.setdefault("typed", []).append(plan["text"])
    return got == plan["text"], (f"the field '{field['label']}' now holds '{got[:60]}'" if not assumed else f"ASSUMED: no field is named '{plan['field']}', so the page's only text field (unlabelled) now holds '{got[:60]}'")


def _do_search(page: Any, plan: Dict[str, Any], res: Dict[str, Any]) -> Tuple[bool, str]:
    cs = _all_inputs(page)
    field = _input_for(cs, "search", search=True)
    if field is None:
        return False, "no search box found on the page"
    home = _snap(page)
    loc = page.locator(f"[data-hj-id='{field['id']}']").first
    try:
        loc.fill(plan["text"], timeout=3000)
        loc.press("Enter", timeout=3000)
    except Exception as e:
        return False, f"could not search: {type(e).__name__}"
    _settle(page)
    now = _snap(page)
    res["steps"].append({"do": f"searched for '{plan['text']}'", "ok": True})
    words = toks(plan["text"])
    has = [w for w in words if w in (now["title"] + " " + now["path"] + " " + _text(page)).lower()]
    moved = now["path"] != home["path"] or now["title"] != home["title"]
    ok = bool(words) and (moved or now["text"] != home["text"]) and len(has) / len(words) >= 0.5          # a results page, or a list that filtered itself on the page
    return ok, (f"the results page '{now['title'][:60]}' mentions {has}" if ok else f"the page did not move to results for '{plan['text']}'")


def _do_navigate(page: Any, rag: Any, task: str, site: Dict[str, str], plan: Dict[str, Any], home: Dict[str, Any], yes: bool, max_clicks: int, res: Dict[str, Any]) -> Tuple[bool, str]:
    words = plan.get("words") or toks(plan["label"])
    if not words:
        return False, "the task names nothing to go to"
    clicks = 0
    used_pid = None
    # --- knowledge first: the stored procedure for this site and goal
    steps: List[Dict[str, Any]] = []
    if rag is not None:
        with contextlib.suppress(Exception):
            ev = rag.proc.find_procedures(site["key"], task, k=3)
            for e in ev:
                st = (e.payload or {}).get("steps") or []
                tl = " ".join(str(s.get("target", "")) for s in st).lower()
                if st and any(w in tl for w in words):
                    steps, used_pid = st, (e.payload or {}).get("procedure_id")
                    break
    res["used_stored_procedure"] = bool(steps)
    for st in steps:
        cs = _controls(page)
        m = _match(cs, st.get("target") or "")
        if not m:
            continue
        g = _gate(m[0], task, yes)
        if g:
            res["status"] = "NEEDS_CONFIRM"
            res["question"] = g["question"]
            return False, g["question"]
        if _click(page, m[0]):
            clicks += 1
            res["steps"].append({"do": f"clicked '{m[0]['label'][:60]}' (stored path)", "ok": True})
            _settle(page)
            ok, ev, weak = landed(page, words, home, exact_click=bool(m[0]["label"].lower() == plan["label"].lower()), typed=res.get("typed", []), ctrl_id=str(m[0].get("id", "")) if set(words) & set(toks(m[0]["label"])) else "")
            if weak:
                res["weak"] = True
            if ok:
                return True, ev
    # --- the live page: controls whose words match the goal, then openers
    tried: set = set()
    for _ in range(max_clicks - clicks):
        cs = [c for c in _controls(page) if c.get("tag") not in ("input", "textarea", "select")]
        best, bs = None, 0.0
        for c in cs:
            k = (c.get("role"), c["label"])
            if k in tried:
                continue
            lw = set(toks(c["label"]))
            s = (3.0 if c["label"].lower() == plan["label"].lower() else 0.0) + (2.0 if set(words) <= lw else 0.0) + len(set(words) & lw)
            if s == 0 and c.get("opener") and c.get("zone") == "nav":
                s = 0.3
            if s > bs:
                best, bs = c, s
        if best is None:
            break
        tried.add((best.get("role"), best["label"]))
        g = _gate(best, task, yes)
        if g:
            res["status"] = "NEEDS_CONFIRM"
            res["question"] = g["question"]
            return False, g["question"]
        if not _click(page, best):
            continue
        clicks += 1
        res["steps"].append({"do": f"clicked '{best['label'][:60]}'", "ok": True})
        _settle(page)
        ok, ev, weak = landed(page, words, home, exact_click=bool(best["label"].lower() == plan["label"].lower()), typed=res.get("typed", []), ctrl_id=str(best.get("id", "")) if set(words) & set(toks(best["label"])) else "")
        if weak:
            res["weak"] = True
        if ok:
            res["used_pid"] = used_pid
            return True, ev
    res["used_pid"] = used_pid
    return False, f"after {clicks} click(s) the page never showed '{' '.join(words)}'"


# ---- 6 learning ---------------------------------------------------------------------------------------------------------------------------------------------
def _learn(rag: Any, site: Dict[str, str], task: str, res: Dict[str, Any]) -> None:
    from core_organs.harvest import web_learn as WL
    clicks = [s["do"].split("'")[1] for s in res["steps"] if s.get("do", "").startswith("clicked") and s.get("ok")]
    if not clicks:
        return
    with contextlib.suppress(Exception):
        pid = hashlib.sha1(f"webrun|{site['host']}|{'>'.join(clicks)}".encode()).hexdigest()[:20]
        steps = [{"text": f"Click '{c}'", "target": c, "role": "link", "route_hint": "click", "expect": ""} for c in clicks]
        with WL.rag_lock():
            rag.proc.ingest_procedure(site["key"], task[:190], steps, f"web_executor:{time.strftime('%Y%m%d_%H%M%S')}", trust="learned", procedure_id=pid)
        res["learned"] = pid
    pid_used = res.get("used_pid")
    if pid_used:
        with contextlib.suppress(Exception):
            from core_organs.rag.types import Outcome, PlanStep
            with WL.rag_lock():
                rag.observe(Outcome(run_id="web_executor", app_key=site["key"], step=PlanStep(command_id="", route="control_click", args={"procedure_id": pid_used, "surface": task}), ok=True, effect="page matched"))
