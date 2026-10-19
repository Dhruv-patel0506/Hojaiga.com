"""
web_delegate -- DO the work on a website or web app: the same Understand -> Teach -> Delegate, for the browser.

The loop is the one every other route uses: look at the page, decide ONE next action, do it, check that something really changed, go on - until the order is done, the page needs the person (a login), or the
steps run out.

    look      the page's interactive controls from the browser's own accessibility tree / DOM (name, role, box); a shortlist of the ~40 that matter for THIS order goes to the brain (the Top-40 trim)
    decide    the CPU brain (brain_planner) answers with one JSON action: click | type | key | scroll | drag | navigate | wait | done | stuck
    gate      Send / Post / Submit / Delete / Pay ... are NEVER operated automatically: the agent fills everything in, stops at that control (staged: its box is returned so it can be highlighted) and operates it only after a live yes from the person (the `confirm` callback), once, for that control. The blind background scanner keeps its own block.
    act       DevTools input events to the page (pointer, text insertion, keys) - never the operating system's input
    check     the page's fingerprint (address, title, controls, the focused field's text) must have changed; a step that changed nothing is reported and tried differently, never counted as done

Nothing here knows a site. A login is never typed for the person: the loop stops at the sign-in wall, says so, and (in a visible, persistent profile of its own - never the person's main browser profile) waits
for them to sign in once; their session stays in that profile for next time.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import socket
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import brain_planner as BP

SUBMIT_RX = re.compile(r"\b(send|post|publish|submit|delete|remove|purchase|buy|pay|place order|confirm order|sign out|log out|logout|tweet|repost|share|reply|unsubscribe|checkout)\b", re.I)
LOGIN_RX = re.compile(r"\b(password|sign in|log in|login|create account|sign up)\b", re.I)
TEXT_ROLES = ("textbox", "searchbox", "combobox", "input", "textarea", "edit", "text field", "search")


def is_text_control(c: Dict[str, Any]) -> bool:
    """A control that takes typed text. A combobox is reported as 'dropdown' by the page reader; a wide one (a search box with suggestions, as on YouTube) is typed into, a narrow one is a picker."""
    role = (c.get("role", "") or "").lower()
    if any(r in role for r in TEXT_ROLES):
        return True
    try:
        return role == "dropdown" and float(c["box"][2]) >= 150
    except Exception:
        return False
STOP = {"the", "a", "an", "to", "of", "in", "on", "and", "or", "for", "it", "is", "this", "that", "with", "then", "open", "go", "please", "me", "my", "i", "do", "you"}


def tokens(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 1]


def needs_confirmation(control_name: str) -> bool:
    """Controls that send, publish, delete or pay for something on the person's behalf: never operated without the person's own live yes."""
    return bool(SUBMIT_RX.search(control_name or ""))


def shortlist(controls: Sequence[Dict[str, Any]], task: str, recent: Sequence[str] = (), k: int = 40) -> List[Tuple[int, Dict[str, Any]]]:
    """The Top-k controls that matter for this order: overlap with the order's words and what was just touched, text boxes first, then the rest in page order. Ids are positions in the FULL list."""
    want = set(tokens(task)) | {t for r in recent for t in tokens(r)}
    scored: List[Tuple[float, int]] = []
    for i, c in enumerate(controls):
        name = c.get("name", "")
        nt = set(tokens(name))
        s = len(want & nt) * 2.0
        if nt and nt <= want:                                          # the control's whole name is words of the order: an exact match beats a longer variant ('Ada Lovelace' over 'Ada Lovelace (microarchitecture)')
            s += 3.0
        s -= 0.4 * len(nt - want) if (nt & want) else 0.0
        if (c.get("role") == "canvas") and re.search(r"draw|paint|sketch|diagram|canvas", task, re.I):
            s += 6.0                                               # the surface the order draws on is always shown to the model
        if is_text_control(c):
            s += 1.5
        if c.get("role") in ("button", "link", "tab", "menuitem"):
            s += 0.2
        s -= i * 0.002
        scored.append((s, i))
    keep = sorted(scored, reverse=True)[:k]
    return [(i, controls[i]) for _s, i in sorted(keep, key=lambda x: x[1])]


def parse_action(obj: Any, n_controls: int) -> Tuple[Optional[Dict[str, Any]], str]:
    """The brain's answer as a checked action, or why it is not one."""
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    a = str(obj.get("action", "")).lower().strip()
    if a not in ("click", "type", "key", "scroll", "drag", "navigate", "wait", "done", "stuck"):
        return None, f"unknown action {a!r}"
    out: Dict[str, Any] = {"action": a, "why": str(obj.get("why", ""))[:160]}
    if a in ("click", "type", "drag"):
        try:
            i = int(obj.get("id"))
        except Exception:
            return None, f"{a} needs an id"
        if not 0 <= i < n_controls:
            return None, f"id {i} is not on the page"
        out["id"] = i
    if a == "type":
        t = str(obj.get("text", ""))
        if not t:
            return None, "type needs text"
        out["text"], out["enter"] = t[:500], bool(obj.get("enter", False))
    if a == "key":
        out["key"] = str(obj.get("key", "enter")).lower()
    if a == "navigate":
        u = str(obj.get("url", "")).strip()
        if not u:
            return None, "navigate needs a url"
        out["url"] = u if re.match(r"^[a-z]+://", u) else "https://" + u
    if a == "drag":
        try:
            out["dx"], out["dy"] = float(obj.get("dx", 0)), float(obj.get("dy", 0))
        except Exception:
            return None, "drag needs dx, dy"
    if a == "scroll":
        out["dy"] = 600.0 if str(obj.get("direction", "down")).lower().startswith("d") else -600.0
    if a == "done":
        out["summary"] = str(obj.get("summary") or obj.get("why") or "")[:200]
    return out, ""


def decide_prompt(task: str, page: Dict[str, Any], short: Sequence[Tuple[int, Dict[str, Any]]], history: Sequence[Dict[str, Any]], problem: str = "") -> str:
    lines = [f'Order: "{task}"', f"Page: {page.get('title', '')[:80]} | {page.get('url', '')[:100]}"]
    if page.get("dialog"):
        lines += [f"A DIALOG IS OPEN over the page: \"{page['dialog']}\". Only its own controls are listed. If you did not mean to open it, close it (its Close / Cancel / X control, or key escape) before anything else."]
    lines += ["Controls on the page (id: role \"name\"):"]
    lines += [f"{i}: {c.get('role', '')} \"{c.get('name', '')[:50]}\"" for i, c in short]
    if history:
        lines += ["", "Done so far:"] + [f"- {h['action']} {h.get('target', '')} {h.get('text', '')[:30]} -> {'worked' if h.get('ok') else 'NO EFFECT'} ({h.get('effect', '')[:40]})" for h in history[-6:]]
    if problem:
        lines += ["", "Problem with your last answer: " + problem]
    lines += ["", 'Choose the ONE next action. Reply JSON: {"action": "click|type|key|navigate|scroll|drag|wait|done|stuck", "id": number, "text": "...", "enter": true|false, "key": "enter", "url": "...", "dx": 0, "dy": 0, "why": "short", "summary": "when done"}.',
              "Rules: if the page already shows what the order asked for (its title or address matches), reply done; to DRAW, first click the tool, then use drag on the drawing canvas (id of the canvas, dx and dy in pixels, e.g. dx 160 dy 100 draws a shape that size); when several links fit, take the one whose name is exactly what the order is about, not a longer variant or a different thing with the same name; type puts text into a text box (enter true presses Enter after it); never type a password; never repeat an action that had no effect; use navigate only when no control helps; say done when the order is complete (summary = what was achieved); say stuck if it cannot be done on this page."]
    return "\n".join(lines)


MODAL_JS = ("(function(){var m=document.querySelector('[role=dialog],[aria-modal=true],dialog[open],tp-yt-paper-dialog');if(!m)return null;var r=m.getBoundingClientRect();"
            "if(r.width<60||r.height<40)return null;return {x:r.left,y:r.top,w:r.width,h:r.height,text:(m.innerText||'').trim().replace(/\\s+/g,' ').slice(0,160)};})()")


def inside(c: Dict[str, Any], rect: Dict[str, Any]) -> bool:
    x, y, w, h = c["box"]
    cx, cy = x + w / 2.0, y + h / 2.0
    return rect["x"] - 4 <= cx <= rect["x"] + rect["w"] + 4 and rect["y"] - 4 <= cy <= rect["y"] + rect["h"] + 4


class WebAgent:
    def __init__(self, brain: BP.Brain, driver: Any, log: Callable[[str], None] = print, confirm: Optional[Callable[[str, str], bool]] = None, max_steps: int = 14, on_login: Optional[Callable[[], bool]] = None, growth: Any = None) -> None:
        self.growth = growth                                          # rag.self_growth.SelfGrowth: a click whose effect was checked is kept as a fast path (and a replay line)
        self.brain, self.d, self.log = brain, driver, log
        self.confirm, self.max_steps, self.on_login = confirm, max_steps, on_login
        self.history: List[Dict[str, Any]] = []
        self.model_seconds = 0.0

    # ------------------------------------------------------------------------------------------------------------------------------------- looking
    def page(self) -> Dict[str, Any]:
        return {"title": self.d.title(), "url": self.d.url()}

    def active_text(self) -> str:
        with contextlib.suppress(Exception):
            v = self.d.p.call("Runtime.evaluate", {"expression": "(function(){var e=document.activeElement;return e?((e.value!==undefined?e.value:e.innerText)||'').slice(0,120):'';})()", "returnByValue": True}).get("result", {}).get("value")
            return str(v or "")
        return ""

    CANVAS_JS = ("(function(){var o=[];document.querySelectorAll('canvas').forEach(function(x){var r=x.getBoundingClientRect();if(r.width>=300&&r.height>=200&&r.bottom>0&&r.right>0)"
                 "o.push({x:r.left,y:r.top,w:r.width,h:r.height})});return o})()")

    site0 = ""
    rejections = 0
    SEARCH_RX = re.compile(r"\bsearch(?:\s+(?:the\s+)?(?:\w+\s+)?(?:for|about))?\s+[\"“']?(.+?)[\"”']?(?=\s+(?:and|then|,|;)\b|[,;.]|$)", re.I)

    def search_step(self, task: str, controls: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """'search for X ...': the first move is read from the order's own words (type X into the page's search box, Enter), not chosen by the model (which sometimes clicks the Search BUTTON first). Once per order."""
        if getattr(self, "_searched", False) or any(h["action"] == "type" for h in self.history):
            return None
        m = self.SEARCH_RX.search(task)
        if not m or len(m.group(1).strip()) < 2:
            return None
        for i, c in enumerate(controls):
            if is_text_control(c) and "search" in ((c.get("name", "") or "") + " " + (c.get("role", "") or "")).lower():
                self._searched = True
                return {"action": "type", "id": i, "text": m.group(1).strip(), "enter": True, "why": "the order says to search for it"}
        return None

    def check_done(self, task: str) -> Tuple[bool, str]:
        """Does the page in front of us satisfy the order? One short question to the brain with the page's title, address and opening words (no controls, no history)."""
        with contextlib.suppress(Exception):
            pg = self.page()
            prompt = " | ".join([f'Order: "{task}"', f'The browser now shows: title "{pg.get("title", "")[:100]}", address {pg.get("url", "")[:120]}', f'Opening text of the page: "{self.body_text(500)}"',
                                 'Is the order complete - does this page exactly match what the order asked for (the right person / thing, not a different one with a similar name)? Reply JSON {"satisfied": true|false, "why_not": "one short sentence"}'])
            obj, meta = self.brain.json(prompt, "You check whether a web page satisfies an order. JSON only.", max_tokens=80)
            self.model_seconds += float(meta.get("seconds") or 0.0)
            if isinstance(obj, dict) and obj.get("satisfied") is False:
                return False, str(obj.get("why_not", "it is not the right page"))[:160]
        return True, ""

    @staticmethod
    def host_of(url: str) -> str:
        from urllib.parse import urlparse
        h = urlparse(url if "://" in (url or "") else "https://" + (url or "")).netloc.lower()
        return h.split(":")[0].removeprefix("www.")

    def leaves_site(self, c: Dict[str, Any], task: str) -> bool:
        href = c.get("href") or ""
        if not href.startswith("http"):
            return False
        h = self.host_of(href)
        base = ".".join(self.site0.split(".")[-2:])
        return bool(h) and not h.endswith(base) and h.split(".")[-2] not in task.lower()

    def with_canvas(self, controls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """A drawing surface is a <canvas>, which the page reader does not list: the biggest one is added as a control ('drawing canvas') so the order 'draw ...' has something to drag on. Appended last: earlier ids do not move."""
        with contextlib.suppress(Exception):
            got = self.d.p.call("Runtime.evaluate", {"expression": self.CANVAS_JS, "returnByValue": True}).get("result", {}).get("value") or []
            if got:
                b = max(got, key=lambda r: r["w"] * r["h"])
                return list(controls) + [{"name": "drawing canvas", "role": "canvas", "box": (b["x"], b["y"], b["w"], b["h"])}]
        return controls

    def modal(self) -> Optional[Dict[str, Any]]:
        """A dialog / pop-up that is open over the page right now ({x, y, w, h, text}), or None."""
        with contextlib.suppress(Exception):
            v = self.d.p.call("Runtime.evaluate", {"expression": MODAL_JS, "returnByValue": True}).get("result", {}).get("value")
            return v if isinstance(v, dict) else None
        return None

    def fingerprint(self, controls: Sequence[Dict[str, Any]]) -> str:
        pg = self.page()
        h = hashlib.sha1(json.dumps([pg["url"], pg["title"], [c.get("name") for c in controls[:60]], self.active_text()], default=str).encode()).hexdigest()
        return h[:12]

    def body_text(self, n: int = 1500) -> str:
        with contextlib.suppress(Exception):
            return str(self.d.p.call("Runtime.evaluate", {"expression": f"(document.body&&document.body.innerText||'').slice(0,{n})", "returnByValue": True}).get("result", {}).get("value") or "")
        return ""

    WALL_URL = re.compile(r"(accounts\.google\.com|/signin|/sign-in|/login|/log-in|/uas/login|servicelogin|/authwall|login\.microsoftonline|/oauth|workspace\.google\.com/.*gmail)", re.I)
    WALL_TEXT = re.compile(r"(scan (?:the|this) qr code|link (?:a|with) (?:phone|device)|use whatsapp on your computer|sign in to continue|log in to continue|to continue, sign in|welcome back!.{0,40}log in)", re.I)

    def login_wall(self, controls: Sequence[Dict[str, Any]]) -> bool:
        with contextlib.suppress(Exception):
            if self.WALL_URL.search(self.d.url() or ""):
                return True
            if self.WALL_TEXT.search(self.body_text(1200) or ""):
                return True
        return any(LOGIN_RX.search(c.get("name", "")) and ("password" in c.get("name", "").lower() or "password" in (c.get("role", "") or "").lower()) for c in controls)

    # ------------------------------------------------------------------------------------------------------------------------------------- acting
    @staticmethod
    def is_text(c: Dict[str, Any]) -> bool:
        return is_text_control(c)

    def text_field(self, controls: Sequence[Dict[str, Any]], i: int) -> Dict[str, Any]:
        """The control to type into: the chosen one when it is a text field, else the text field that shares its name (a search BUTTON and a search BOX are both called 'Search'), else the first text field on the page."""
        c = controls[i]
        if self.is_text(c):
            return c
        want = set(tokens(c.get("name", "")))
        cands = [d for d in controls if self.is_text(d)]
        same = [d for d in cands if want & set(tokens(d.get("name", "")))]
        return (same or cands or [c])[0]

    def center(self, c: Dict[str, Any]) -> Tuple[float, float]:
        x, y, w, h = c["box"]
        return x + w / 2.0, y + h / 2.0

    def do(self, act: Dict[str, Any], controls: Sequence[Dict[str, Any]]) -> Tuple[bool, str]:
        a = act["action"]
        try:
            if a == "click":
                self.d.click_at(*self.center(controls[act["id"]]))
            elif a == "type":
                x, y = self.center(self.text_field(controls, act["id"]))
                self.d.click_at(x, y)
                time.sleep(0.3)
                self.d.p.call("Runtime.evaluate", {"expression": "(function(){var e=document.activeElement;if(e&&e.select)e.select();})()"})
                self.d.p.call("Input.insertText", {"text": act["text"]})
                tf = self.text_field(controls, act["id"])
                if act.get("enter") or "search" in ((tf.get("role", "") or "") + " " + (tf.get("name", "") or "")).lower():          # a search box is submitted by Enter (the button beside it is often covered by the suggestion list)
                    act = dict(act, enter=True)
                if act.get("enter"):
                    time.sleep(0.3)
                    self.d.key("enter")
            elif a == "key":
                self.d.key(act["key"])
            elif a == "scroll":
                self.d.p.call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 400, "y": 400, "deltaX": 0, "deltaY": act["dy"]})
            elif a == "drag":
                x, y = self.center(controls[act["id"]])
                ex, ey = x + act["dx"], y + act["dy"]
                for typ, px, py in (("mouseMoved", x, y), ("mousePressed", x, y)) + tuple(("mouseMoved", x + (ex - x) * t / 8.0, y + (ey - y) * t / 8.0) for t in range(1, 9)) + (("mouseReleased", ex, ey),):
                    self.d.p.call("Input.dispatchMouseEvent", {"type": typ, "x": px, "y": py, "button": "left", "clickCount": 1, "buttons": 1 if typ != "mouseReleased" else 0})
                    time.sleep(0.04)
            elif a == "navigate":
                self.d.navigate(act["url"])
            elif a == "wait":
                time.sleep(2.0)
            return True, "sent"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {str(exc)[:80]}"

    # ------------------------------------------------------------------------------------------------------------------------------------- the loop
    def run(self, task: str, start_url: str = "") -> Dict[str, Any]:
        t0 = time.time()
        if start_url:
            self.d.navigate(start_url)
        rep: Dict[str, Any] = {"task": task, "status": "max_steps", "steps": [], "model_seconds": 0.0}
        with contextlib.suppress(Exception):
            self.site0 = self.host_of(self.d.url())
        fails = 0
        problem = ""
        for n in range(self.max_steps):
            time.sleep(0.5)
            controls = self.with_canvas(self.d.controls(160))
            if self.login_wall(controls):
                rep["status"] = "needs_login"
                if self.on_login is not None and self.on_login():
                    continue
                break
            before = self.fingerprint(controls)
            md = self.modal()
            pool = ([c for c in controls if inside(c, md)] if md else controls) or controls
            if self.site0:                                                  # a link that leaves the site is not part of an order about this site (unless the order names where to go)
                stay = [c for c in pool if not self.leaves_site(c, task)]
                pool = stay or pool               # a dialog that is open is the only thing that can be operated
            short = [(controls.index(c), c) for _i, c in shortlist(pool, task, [h.get("target", "") for h in self.history[-3:]])]
            obj, meta = self.search_step(task, controls), {"seconds": 0.0}
            if obj is None:
                obj, meta = self.brain.json(decide_prompt(task, self.page(), short, self.history, problem), BP.DESIGN_SYSTEM.replace("3D modeller", "web operator"), max_tokens=150)
            self.model_seconds += float(meta.get("seconds") or 0.0)
            act, problem = parse_action(obj, len(controls))
            if act is None:
                fails += 1
                self.log(f"[web] step {n + 1}: unusable answer ({problem})")
                if fails >= 3:
                    rep["status"] = "stuck"
                    break
                continue
            problem = ""
            key = (act["action"], act.get("id"), act.get("text", act.get("url", "")))
            if len(self.history) >= 2 and all((h["action"], h.get("id"), h.get("text", "")) == (key[0], key[1], key[2] if key[0] != "navigate" else key[2]) and h["ok"] for h in self.history[-2:]) and act["action"] in ("click", "key"):
                problem = "you have already done exactly that twice and it worked; it is done. Choose the NEXT step of the order (for a drawing: drag on the drawing canvas), or say done if the order is complete"
                loops = getattr(self, "_loops", 0) + 1
                self._loops = loops
                self.log(f"[web] step {n + 1}: the same successful action again; asked for the next step")
                if loops >= 3:
                    rep["status"] = "stuck"
                    break
                continue
            if key in {(h["action"], h.get("id"), h.get("text", "")) for h in self.history if not h["ok"]}:
                problem = "you already did exactly that and it had no effect: choose a different control or action"
                fails += 1
                self.log(f"[web] step {n + 1}: repeated a failed action; asked again")
                if fails >= 4:
                    rep["status"] = "stuck"
                    break
                continue
            if act["action"] == "done":
                if self.rejections < 2 and self.history:                          # the model says it is finished: look at the page once more before believing it
                    ok_done, why_not = self.check_done(task)
                    if not ok_done:
                        self.rejections += 1
                        with contextlib.suppress(Exception):                          # that page was the wrong one: its link is struck off (a repeat is refused) and the browser goes back to where the choice was made
                            if self.history and self.history[-1]["action"] == "click":
                                self.history[-1]["ok"] = False
                            self.d.back()
                            time.sleep(1.2)
                        problem = "the page does not show what the order asked for yet: " + why_not + ". Search again with more specific words from the order (the right kind of thing, not the first suggestion), or use a link on this page that leads to the right one"
                        self.log(f"[web] step {n + 1}: 'done' rejected ({why_not[:80]})")
                        continue
                rep["status"], rep["summary"] = "done", act.get("summary", "")
                break
            if act["action"] == "stuck":
                rep["status"], rep["summary"] = "stuck", act.get("why", "")
                break
            target = controls[act["id"]].get("name", "") if "id" in act else ""
            if act["action"] in ("click", "type") and needs_confirmation(target):
                said_yes = False
                if self.confirm is not None:
                    with contextlib.suppress(Exception):
                        said_yes = bool(self.confirm(target, task))
                if not said_yes:
                    rep["status"], rep["staged"] = "staged", {"control": target, "box": controls[act["id"]]["box"]}
                    self.log(f"[web] step {n + 1}: '{target}' sends / publishes / deletes / pays: staged for your yes, not operated")
                    break
                self.log(f"[web] step {n + 1}: '{target}' confirmed by the person")
            ok, note = self.do(act, controls)
            time.sleep(1.6)
            after_controls = self.d.controls(160)
            changed = self.fingerprint(after_controls) != before
            if ok and not changed and act["action"] == "click":              # a pointer click that did nothing: ask the page itself to click what is under that point (covered / re-rendered targets)
                x, y = self.center(controls[act["id"]])
                with contextlib.suppress(Exception):
                    self.d.p.call("Runtime.evaluate", {"expression": "(function(){var e=document.elementFromPoint(%d,%d);if(e){var t=e.closest('a,button,[role=button],[role=link],[role=tab],input,summary')||e;t.click();return 1}return 0})()" % (x, y)})
                    time.sleep(1.4)
                    after_controls = self.d.controls(160)
                    changed = self.fingerprint(after_controls) != before
            effect = "page changed" if changed else "nothing changed"
            md_after = self.modal()
            if md_after and not md:
                effect = f"a dialog opened: {md_after.get('text', '')[:50]}"
            if act["action"] == "scroll" or act["action"] == "wait":
                changed = ok
            rec = {"action": act["action"], "target": target, "id": act.get("id"), "text": act.get("text", act.get("url", "")), "ok": bool(ok and changed), "effect": effect if ok else note, "why": act.get("why", ""), "n": n + 1}
            if self.growth is not None and rec["ok"] and act["action"] == "click" and target:
                with contextlib.suppress(Exception):
                    from urllib.parse import urlparse
                    site = urlparse(self.page().get("url", "")).netloc.lower().removeprefix("www.") or "web"
                    cx, cy = self.center(controls[act["id"]])
                    self.growth.learn("web:" + site, [c.get("name", "") for c in controls][:60], {"name": target, "type": controls[act["id"]].get("role", "button"), "center": (int(cx), int(cy)), "box": tuple(controls[act["id"]]["box"])},
                                      "click", [c.get("name", "") for c in after_controls][:60], None, True)
            self.history.append(rec)
            rep["steps"].append(rec)
            self.log(f"[web] step {n + 1}: {act['action']} '{target[:40]}' {act.get('text', '')[:30]} -> {rec['effect']}")
            fails = 0 if rec["ok"] else fails + 1
            if fails >= 3:
                rep["status"] = "stuck"
                break
        rep["seconds"], rep["model_seconds"] = round(time.time() - t0, 1), round(self.model_seconds, 1)
        rep["final"] = {**self.page(), "text": self.body_text(300)}
        rep["done_steps"] = sum(1 for s in rep["steps"] if s["ok"])
        return rep


# ------------------------------------------------------------------------------------------------------------------------------------- a browser of its own
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class OwnedBrowser:
    """A browser the run starts, visible, with a profile of its OWN (data/web_profile): the person signs in there once and the session stays. The person's everyday browser profile is never touched. Ended by its
    process id at the end."""

    def __init__(self, profile: str = "", exe: str = "", visible: bool = True) -> None:
        self.profile = profile or os.path.join(os.environ.get("HOJAIGA_DATA", r"D:\new_automation\data"), "web_profile")
        self.exe, self.visible = exe, visible
        self.proc: Optional[subprocess.Popen] = None
        self.port = 0
        self.browser: Any = None

    def __enter__(self) -> "OwnedBrowser":
        from core_organs.professor import launcher as LN
        from core_organs.professor.adapters.cdp import CdpBrowser
        exe = self.exe or LN.resolve("Microsoft Edge").exe or LN.resolve("Google Chrome").exe
        if not exe:
            raise RuntimeError("no Edge or Chrome found")
        os.makedirs(self.profile, exist_ok=True)
        self.port = free_port()
        args = [exe, f"--remote-debugging-port={self.port}", f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check", "--window-size=1280,860", "--window-position=40,40", "about:blank"]
        self.proc = subprocess.Popen(args)
        self.browser = CdpBrowser(self.port)
        if not self.browser.wait(25.0):
            self.__exit__(None, None, None)
            raise RuntimeError("the browser did not answer on its DevTools port")
        return self

    def driver(self) -> Any:
        from core_organs.harvest import web_recorder as WR
        from core_organs.professor.adapters.cdp import CdpPage
        tg = [t for t in self.browser.targets() if t.get("type") == "page"]
        d = WR.CdpDriver(CdpPage(tg[0]))
        with contextlib.suppress(Exception):
            d.p.call("Emulation.clearDeviceMetricsOverride")                          # a visible window keeps its real size
        return d

    def __exit__(self, *exc: Any) -> bool:
        if self.proc is not None:
            with contextlib.suppress(Exception):
                import psutil
                par = psutil.Process(self.proc.pid)
                for ch in par.children(recursive=True):
                    with contextlib.suppress(Exception):
                        ch.kill()
                par.kill()
        return False
