"""
harvest.web_tasks_eval -- does what the system stored actually help?  20 tasks on sites it has learned, done twice, with proof.

    D:\\new_automation\\hojaiga_env\\Scripts\\python.exe -X utf8 -m core_organs.harvest.web_tasks_eval --n 20

Each task is a real thing a person asks ('How do I get to Pricing on Todoist?', 'Open the Product menu on Notion'), taken from a click the explorer once made. The same task is then done by two agents in
fresh browser sessions:

  COLD   only the live page: it reads the visible labels, clicks the control whose words best match the question, opens menus when nothing matches, up to 8 clicks.
  POOL   the RAG: it retrieves the procedure for the question (rag.proc.find_procedures, the question is a PARAPHRASE of the stored goal, not a copy) and replays its steps on the live page.

Success is checked on the page afterwards (the page the task names opened / the menu items it should show are visible), not by the agent's own say-so. Every run leaves a picture of the page it ended on.
After a POOL run the result is reported back to the RAG (rag.observe), so a procedure that works gains reliability and one that fails loses it: the stored knowledge is trained by use.

Honest limits: the procedures came from an earlier scan of the same site, so this tests MEMORY of the app (does a stored path still work, is it found from a spoken question), not generalisation to an unseen site; sites change,
so some stored paths will have moved; the COLD agent is a simple greedy one, not an LLM.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from core_organs.harvest import web_actions as WA
from core_organs.harvest import web_learn as WL

REPORTS = os.environ.get("HOJAIGA_REPORTS", os.path.join("D:" + os.sep, "new_automation", "reports"))
OUT = os.path.join(REPORTS, "web_tasks")
GENERIC = {"close", "menu", "next", "previous", "skip", "back", "more", "search", "home", "toggle", "open", "play", "pause", "mute", "done", "cancel", "ok", "yes", "no"}
STOPW = {"the", "a", "an", "on", "in", "to", "of", "and", "page", "menu", "open", "go", "how", "do", "i", "get", "show", "me", "find"}


def toks(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]{2,}", (s or "").lower()) if w not in STOPW]


def newest_reports() -> Dict[str, Dict[str, Any]]:
    newest: Dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(REPORTS, "try_app", "2026*", "report.json")), key=os.path.getmtime):
        with contextlib.suppress(Exception):
            rep = json.load(open(p, encoding="utf-8"))
            if (rep.get("scan") or {}).get("explore") and not ((rep.get("understanding") or {}).get("auth") or {}).get("blocked"):
                newest[WL.host_of(rep.get("target", ""))] = p
    return {h: json.load(open(p, encoding="utf-8")) for h, p in newest.items()}


def _known_ratio(text: str) -> float:
    with contextlib.suppress(Exception):
        from core_organs.harvest import fact_cleaner as FC
        return FC.known_ratio(text, FC.vocabulary())
    return 1.0


def full_url(t: str) -> str:
    return t if re.match(r"^https?://", t or "", re.I) else "https://" + (t or "").lstrip("/")


def pick_tasks(n: int = 20, seed: int = 7, per_site: int = 2, reports: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    rnd = random.Random(seed)
    reports = reports if reports is not None else newest_reports()
    pool: List[Dict[str, Any]] = []
    for host, rep in reports.items():
        site = WA.site_name(host)
        nodes = [x for x in (rep.get("scan") or {}).get("explore", {}).get("nodes", []) if x.get("path")]
        by_path = {x["path"]: x for x in nodes}
        for node in nodes:
            chain = WA.chain_of(node["path"])
            if node.get("outcome") not in WA.EFFECTS or not (1 <= len(chain) <= 2):
                continue
            role, label, ctx, _ = WA._resolve(rep, by_path, chain)
            if len(label) < 4 or len(label) > 34 or label.lower() in GENERIC or not re.search(r"[A-Za-z]{3}", label) or not re.fullmatch(r"[A-Za-z][A-Za-z '&,\-\?]*", label):
                continue                                                                      # names, not file names / quoted tokens / numbered footnotes / 'Expand: ...'
            if "logo" in label.lower() or label.lower() == site.lower() or label.lower() == host.split(".")[0].lower():         # the home link goes nowhere new
                continue
            if _known_ratio(label) < (0.99 if len(label.split()) == 1 else 0.8):                                                      # not English words the pool knows (a Bahasa Indonesia menu, an acronym soup)
                continue
            from core_organs.try_app_explore import Explorer
            if any(Explorer.LANG.search(c) or len(c) > 40 or "(" in c for c in chain):                    # language pickers and index entries are not things a person asks for
                continue
            if node["outcome"] == "opened a new page" and not ((node.get("page") or {}).get("title") or "").strip():
                continue
            pool.append({"host": host, "site": site, "url": full_url(rep.get("target") or host), "category": rep.get("category", ""), "chain": chain, "label": label, "outcome": node["outcome"],
                         "expect_title": ((node.get("page") or {}).get("title") or ""), "expect_items": WA.items_of(node, 4), "stored_goal": WA.goal_of(site, label, node, chain)})
    rnd.shuffle(pool)
    tasks, used = [], {}
    pages = [t for t in pool if t["outcome"] == "opened a new page"]
    other = [t for t in pool if t["outcome"] != "opened a new page"]
    for group, quota in ((pages, int(n * 0.7)), (other, n)):
        for t in group:
            if len([x for x in tasks if x in group]) >= quota or len(tasks) >= n:
                break
            if used.get(t["host"], 0) >= per_site or any(x["host"] == t["host"] and x["label"] == t["label"] for x in tasks):
                continue
            used[t["host"]] = used.get(t["host"], 0) + 1
            tasks.append(t)
    for i, t in enumerate(tasks, 1):
        verb = {"opened a new page": "How do I get to {l} on {s}?", "revealed a menu / panel": "I want to see the {l} menu on {s}. What do I click?", "opened a dialog": "How do I open {l} on {s}?",
                "opens on hover": "How do I open the {l} menu on {s}?", "opened a child window": "How do I open {l} on {s} in a new window?"}[t["outcome"]]
        t["id"] = i
        t["question"] = verb.format(l=t["label"], s=t["site"])
    return tasks


# --------------------------------------------------------------------------------------------------------------------------------- the page
def controls(page: Any) -> List[Dict[str, Any]]:
    from core_organs import try_app_show as TS
    for _ in range(4):
        try:
            return page.evaluate(TS.COLLECT_JS)["controls"]
        except Exception as e:
            if "context was destroyed" not in str(e) and "navigat" not in str(e).lower():
                return []
            with contextlib.suppress(Exception):
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            time.sleep(0.4)
    return []


def click_control(page: Any, c: Dict[str, Any]) -> bool:
    loc = page.locator(f"[data-hj-id='{c['id']}']").first
    with contextlib.suppress(Exception):
        loc.scroll_into_view_if_needed(timeout=900)
    try:
        loc.click(timeout=1500)
        return True
    except Exception:
        pass
    with contextlib.suppress(Exception):
        loc.evaluate("e => e.click()", timeout=1000)
        return True
    return False


def match_controls(cs: Sequence[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    """Controls on the live page that are the stored one: same name, then same first 24 characters, then the same words (a label that gained or lost a word since it was recorded)."""
    lab = (label or "").lower().strip()
    exact = [c for c in cs if c["label"].lower() == lab]
    pre = [c for c in cs if lab[:24] and (c["label"].lower().startswith(lab[:24]) or lab.startswith(c["label"].lower()[:24]) and len(c["label"]) >= 4)]
    tw = set(toks(lab))
    near = [c for c in cs if tw and len(tw) >= 1 and (lambda cw: cw and len(tw & cw) / max(len(tw), len(cw)) >= 0.6)(set(toks(c["label"])))]
    out = exact or pre or near
    out = sorted(out, key=lambda c: (not c.get("inview"), c["y"]))
    return out


def settle(page: Any) -> None:
    time.sleep(0.6)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("domcontentloaded", timeout=3000)


def check(page: Any, task: Dict[str, Any], home: Dict[str, Any]) -> bool:
    """Did the thing the task names happen? Judged on the page, not by the agent."""
    path = urlparse(page.url).path
    title = ""
    with contextlib.suppress(Exception):
        title = page.title()
    low = (title + " " + path).lower()
    if task["outcome"] == "opened a new page":
        moved = path != home["path"] or title != home["title"]
        words = toks(task["label"])
        exp = toks(task["expect_title"])
        hit = any(w in low for w in words) or (exp and len(set(exp) & set(toks(title))) / len(exp) >= 0.5)
        return bool(moved and hit)
    labs = [c["label"].lower() for c in controls(page)]
    want = [w.lower() for w in task["expect_items"]]
    if not want:
        return False
    found = sum(1 for w in want if any(l.startswith(w[:20]) for l in labs))
    return found / len(want) >= 0.5 and bool(set(want) - set(home["labels"]))


def snapshot(page: Any) -> Dict[str, Any]:
    title = ""
    with contextlib.suppress(Exception):
        title = page.title()
    return {"path": urlparse(page.url).path, "title": title, "labels": [c["label"].lower() for c in controls(page)][:300]}


# --------------------------------------------------------------------------------------------------------------------------------- the two agents
def run_cold(page: Any, task: Dict[str, Any], home: Dict[str, Any], budget: int = 8) -> Dict[str, Any]:
    from core_organs.try_app_show import DANGER
    goal = set(toks(task["label"]))
    tried: set = set()
    clicks = 0
    why = "budget spent"
    for _ in range(budget):
        cs = [c for c in controls(page) if c["label"] and c["tag"] not in ("input", "textarea", "select") and not DANGER.search(c["label"] or "")]
        best, bs = None, 0.0
        for c in cs:
            k = (c["role"], c["label"])
            if k in tried:
                continue
            lt = set(toks(c["label"]))
            s = (3.0 if c["label"].lower() == task["label"].lower() else 0.0) + (2.0 if goal and goal <= lt else 0.0) + len(goal & lt)
            if s == 0 and (c.get("opener") and c.get("zone") == "nav"):
                s = 0.3
            if s > bs:
                best, bs = c, s
        if best is None:
            why = "nothing on the page matches"
            break
        tried.add((best["role"], best["label"]))
        if not click_control(page, best):
            continue
        clicks += 1
        settle(page)
        if check(page, task, home):
            return {"ok": True, "clicks": clicks, "why": ""}
    return {"ok": False, "clicks": clicks, "why": why}


def run_pool(page: Any, task: Dict[str, Any], home: Dict[str, Any], rag: Any) -> Dict[str, Any]:
    key = "webapp:" + task["host"]
    t0 = time.time()
    ev = rag.proc.find_procedures(key, task["question"], k=3)
    ms = round((time.time() - t0) * 1000)
    if not ev:
        return {"ok": False, "clicks": 0, "why": "the pool had no procedure for the question", "retrieved": None, "retrieval_ms": ms}
    top = ev[0]
    steps = (top.payload or {}).get("steps") or []
    chain = [s.get("target") or "" for s in steps]
    want = [c.lower() for c in task["chain"]]
    got = [c.lower() for c in chain]
    correct = len(got) == len(want) and all(g.startswith(w[:24]) or w.startswith(g[:24]) for g, w in zip(got, want))
    in_top3 = any(len([s.get("target", "") for s in (e.payload or {}).get("steps", [])]) == len(want) and all((s.get("target", "").lower().startswith(w[:24]) or w.startswith(s.get("target", "").lower()[:24]))
                                                                                                         for s, w in zip((e.payload or {}).get("steps", []), want)) for e in ev)
    clicks = 0
    meta = {"retrieved": top.text, "retrieved_correct": correct, "in_top3": in_top3, "retrieval_ms": ms, "pid": (top.payload or {}).get("procedure_id")}
    skipped: List[str] = []
    for i, st in enumerate(steps):
        final = i == len(steps) - 1
        cs = match_controls([c for c in controls(page) if c["label"]], st.get("target") or "")
        if not cs:
            if final:
                skipped.append(st.get("target") or "")
                break
            skipped.append(st.get("target") or "")                           # an earlier step that is no longer there (a banner, a player button, a menu that was always open): go on without it
            continue
        if not click_control(page, cs[0]):
            skipped.append(st.get("target") or "")
            continue
        clicks += 1
        settle(page)
        if check(page, task, home):
            break
    ok = clicks > 0 and check(page, task, home)                                             # no click, no success: a page that merely finished loading or redirected is not an answer
    if ok:
        return {"ok": True, "clicks": clicks, "why": "", "healed": False, "skipped": skipped, **meta}
    # the stored path did not get there: fall back to reading the live page for the rest, and REMEMBER what works
    fb = run_cold(page, task, home, budget=5)
    total = clicks + fb["clicks"]
    return {"ok": fb["ok"], "clicks": total, "why": "" if fb["ok"] else f"the stored path failed (skipped {skipped}) and the live page did not help", "healed": fb["ok"], "skipped": skipped, "fallback_clicks": fb["clicks"], **meta}


def heal(rag: Any, task: Dict[str, Any], res: Dict[str, Any], run_id: str) -> bool:
    """A path that worked after the stored one failed is itself knowledge: file the direct way (the last control, one step) as a new, 'learned'-trust procedure."""
    if not res.get("ok") or not res.get("healed"):
        return False
    with contextlib.suppress(Exception):
        import hashlib
        key = "webapp:" + task["host"]
        pid = hashlib.sha1(f"healed|{task['host']}|{task['label']}".encode()).hexdigest()[:20]
        goal = WA.goal_of(task["site"], task["label"], {"outcome": task["outcome"]}, [task["label"]])
        steps = [{"text": f"Click '{task['label']}'", "target": task["label"], "role": "link", "route_hint": "click", "expect": task["expect_title"] and f"the page '{task['expect_title']}' opens" or "the menu opens"}]
        with WL.rag_lock():
            rag.proc.ingest_procedure(key, goal, steps, f"web_tasks:{run_id}", trust="learned", procedure_id=pid)
        return True
    return False


def report_back(rag: Any, task: Dict[str, Any], res: Dict[str, Any], run_id: str) -> None:
    """The result teaches the RAG: the procedure that was run gains (or loses) reliability."""
    pid = res.get("pid")
    if not pid:
        return
    with contextlib.suppress(Exception):
        from core_organs.rag.types import Outcome, PlanStep
        step = PlanStep(command_id="", route="control_click", args={"procedure_id": pid, "surface": task["question"]})
        with WL.rag_lock():
            rag.observe(Outcome(run_id=run_id, app_key="webapp:" + task["host"], step=step, ok=bool(res["ok"]), effect="page matched" if res["ok"] else (res.get("why") or "failed")))


# --------------------------------------------------------------------------------------------------------------------------------- run
def run(n: int = 20, seed: int = 7, show: bool = False, learn: bool = True, log=print) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright
    from core_organs import rag as R
    from core_organs.try_app import launch_browser
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(OUT, stamp)
    os.makedirs(out, exist_ok=True)
    rag = R.get_rag()
    tasks = pick_tasks(n, seed)
    log(f"{len(tasks)} tasks on {len({t['host'] for t in tasks})} sites; proof pictures in {out}")
    results: List[Dict[str, Any]] = []
    with sync_playwright() as pw:
        br = launch_browser(pw, headless=not show, args=[] if not show else ["--window-position=30,20", "--window-size=1500,940"])
        for t in tasks:
            row: Dict[str, Any] = {"task": t}
            for cond in ("cold", "pool"):
                ctx = br.new_context(viewport={"width": 1440, "height": 820}, locale="en-US") if not show else br.new_context(no_viewport=True, locale="en-US")
                page = ctx.new_page()
                t0 = time.time()
                try:
                    page.goto(t["url"], wait_until="domcontentloaded", timeout=30000)
                    with contextlib.suppress(Exception):
                        page.wait_for_load_state("networkidle", timeout=5000)
                    home = snapshot(page)
                    res = run_cold(page, t, home) if cond == "cold" else run_pool(page, t, home, rag)
                except Exception as e:
                    res = {"ok": False, "clicks": 0, "why": f"{type(e).__name__}: {str(e)[:80]}"}
                res["seconds"] = round(time.time() - t0, 1)
                with contextlib.suppress(Exception):
                    shot = os.path.join(out, f"task_{t['id']:02d}_{cond}_{'ok' if res['ok'] else 'fail'}.png")
                    page.screenshot(path=shot)
                    res["picture"] = os.path.basename(shot)
                ctx.close()
                row[cond] = res
                if cond == "pool" and learn:
                    report_back(rag, t, res, "webtasks_" + stamp)
                    res["filed_correction"] = heal(rag, t, res, "webtasks_" + stamp)
            results.append(row)
            c, p = row["cold"], row["pool"]
            log(f"  #{t['id']:02d} {t['site']:<14} {t['label'][:26]:<26} cold {'OK ' if c['ok'] else 'no '}{c['clicks']} clicks  |  pool {'OK ' if p['ok'] else 'no '}{p['clicks']} clicks"
                + (f"  [{p.get('why', '')[:48]}]" if not p["ok"] else ""))
        br.close()
    sm = summarize(results)
    json.dump({"stamp": stamp, "summary": sm, "results": results}, open(os.path.join(out, "results.json"), "w", encoding="utf-8"), indent=1, default=str)
    open(os.path.join(out, "RESULTS.md"), "w", encoding="utf-8").write(markdown(sm, results))
    log(json.dumps(sm, indent=1))
    log("proof folder: " + out)
    return {"summary": sm, "folder": out}


def summarize(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(results)

    def side(k: str) -> Dict[str, Any]:
        ok = [r[k] for r in results if r[k]["ok"]]
        return {"success": f"{len(ok)}/{n}", "success_rate": round(len(ok) / max(1, n), 2), "mean_clicks_when_ok": round(sum(x["clicks"] for x in ok) / max(1, len(ok)), 1),
                "mean_seconds_all": round(sum(r[k]["seconds"] for r in results) / max(1, n), 1)}
    pool = [r["pool"] for r in results]
    return {"tasks": n, "cold": side("cold"), "pool": side("pool"), "retrieval_top1_correct": f"{sum(1 for p in pool if p.get('retrieved_correct'))}/{n}", "retrieval_in_top3": f"{sum(1 for p in pool if p.get('in_top3'))}/{n}",
            "pool_found_nothing": sum(1 for p in pool if p.get("retrieved") is None), "pool_healed_after_a_stale_path": sum(1 for p in pool if p.get("healed") and p["ok"]),
            "pool_ok_by_stored_path_alone": sum(1 for p in pool if p["ok"] and not p.get("healed")), "mean_retrieval_ms": round(sum(p.get("retrieval_ms", 0) for p in pool) / max(1, n)),
            "pool_failures_by_reason": {w: sum(1 for p in pool if not p["ok"] and p.get("why", "").startswith(w)) for w in ("the pool had no", "step '", "could not click", "the page did not")}}


def markdown(sm: Dict[str, Any], results: Sequence[Dict[str, Any]]) -> str:
    md = ["# Does the pool help? 20 tasks, done cold and with the pool", "", f"- cold (live page only): {sm['cold']}", f"- pool (RAG procedure replayed): {sm['pool']}",
          f"- the right procedure was retrieved first: {sm['retrieval_top1_correct']}; among the top 3: {sm['retrieval_in_top3']}; retrieval {sm['mean_retrieval_ms']} ms on average", "",
          "| # | site | task | cold | pool | what the pool retrieved | pictures |", "|---|---|---|---|---|---|---|"]
    for r in results:
        t, c, p = r["task"], r["cold"], r["pool"]
        md.append(f"| {t['id']} | {t['site']} | {t['question']} | {'ok' if c['ok'] else 'no'} ({c['clicks']} clicks) | {'ok' if p['ok'] else 'no: ' + p.get('why', '')[:40]} ({p['clicks']} clicks) | "
                  f"{(p.get('retrieved') or '-')[:60]} | {c.get('picture', '')}, {p.get('picture', '')} |")
    return "\n".join(md)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--no-learn", action="store_true", help="do not report results back to the RAG")
    a = ap.parse_args(argv)
    run(a.n, a.seed, a.show, not a.no_learn, log=lambda s: print(s, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
