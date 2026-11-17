"""
harvest.web_actions -- keep what every click DID, not just what it was called.

The deep explorer learns, for each control it clicks, an OUTCOME: a page opened (which one), a menu or panel appeared (showing what), a dialog opened, a menu appears on hover, a new window opened,
or nothing visible happened. The first version of the web curriculum stored only the NAMES of the paths ('Features > Inbox'); the outcome stayed in a report file, and the outcome is exactly the
part a live scan cannot re-derive. This module files it where it can be used:

  PROCEDURES   one retrievable procedure per path that did something, in the RAG's own procedure table (so the existing retrieval, ranking, and reliability learning apply to it):
                  goal   'Go to the Pricing page on Todoist'
                  steps  Click 'Product' (a menu opens: Features, Integrations, ...) -> Click 'Pricing' (the page 'Pricing | Todoist' opens)
               trust 'web' (read off a live page), grounded to the lexicon where the labels are known; ids are deterministic, so filing the same site twice changes nothing.
  TRAINING ROWS  one chat-format row per click, in the shape the vision / action model is trained on (numbered elements -> action JSON), but REAL: the list holds up to 40 controls that were on screen
               when the click was chosen (many choices, many different targets), not one element that is always #1. Written to its own file (web_action_rows.jsonl), never into the main dataset.
               Older reports kept no screen context; for them the list is rebuilt from what the parent menu revealed (marked 'reconstructed').
"""
from __future__ import annotations

import contextlib
import glob
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core_organs.harvest import web_learn as WL

DATA = WL.DATA
ROWS_PATH = os.path.join(DATA, "ai_root", "harvest", "training", "web_action_rows.jsonl")
SYSTEM = ("You operate desktop software by reading a numbered list of on-screen elements. Reply with a JSON list of actions: [{\"step\": 1, \"action\": \"click|hotkey|type\", \"target_id\": <number or null>, "
          "\"hotkey\": <keys or null>, \"text\": <text or null>, \"verify_expectation\": \"<what the screen should show next>\"}]")
EFFECTS = ("opened a new page", "revealed a menu / panel", "opened a dialog", "opens on hover", "opened a child window")


def _sha(*a: str) -> str:
    return hashlib.sha1("|".join(a).encode("utf-8")).hexdigest()[:20]


def site_name(host: str) -> str:
    base = host.split(".")[0] if host.count(".") < 2 else host.split(".")[-2]
    return base.capitalize() if base else host


def chain_of(path: str) -> List[str]:
    return [p.strip() for p in (path or "").split(" > ") if p.strip()]


def items_of(node: Dict[str, Any], top: int = 6) -> List[str]:
    out = []
    for x in node.get("revealed") or []:
        lab = str(x).split(": ", 1)[-1].strip()
        if lab and lab not in out:
            out.append(lab[:40])
    return out[:top]


def outcome_phrase(node: Dict[str, Any]) -> str:
    o = node.get("outcome", "")
    if o == "opened a new page":
        title = ((node.get("page") or {}).get("title") or "").strip()
        return f"the page '{title}' opens" if title else "a new page opens"
    if o in ("revealed a menu / panel", "opens on hover"):
        its = items_of(node)
        return ("a menu appears on hover" if o == "opens on hover" else "a menu or panel opens") + (f", showing: {', '.join(its)}" if its else "")
    if o == "opened a dialog":
        its = items_of(node)
        return "a dialog opens" + (f", showing: {', '.join(its)}" if its else "")
    if o == "opened a child window":
        t = ((node.get("window") or {}).get("title") or "").strip()
        return f"a new window opens ('{t}')" if t else "a new window opens"
    return ""


def goal_of(site: str, label: str, node: Dict[str, Any], chain: Sequence[str]) -> str:
    o = node.get("outcome", "")
    via = f" via {' > '.join(chain[:-1])}" if len(chain) > 1 else ""
    if o == "opened a new page":
        return f"Go to the {label} page on {site}{via}"
    if o == "revealed a menu / panel":
        return f"Open the {label} menu on {site}{via}"
    if o == "opens on hover":
        return f"Hover over {label} on {site} to open its menu{via}"
    if o == "opened a child window":
        return f"Open {label} on {site} (it opens in a new window){via}"
    return f"Open {label} on {site}{via}"


def _resolve(report: Dict[str, Any], by_path: Dict[str, Dict[str, Any]], chain: Sequence[str]) -> Tuple[str, str, List[str], bool]:
    """(role, full label, context list, reconstructed?) for the LAST element of a chain. Newer reports carry the real context; older ones are rebuilt from the parent's revealed list / the page labels."""
    node = by_path.get(" > ".join(chain), {})
    if node.get("context"):
        role, _, lab = (node.get("target") or "control: " + chain[-1]).partition(": ")
        return role, lab, list(node["context"]), False
    short = chain[-1]
    if len(chain) >= 2:
        parent = by_path.get(" > ".join(chain[:-1]), {})
        pool = [str(x) for x in (parent.get("revealed") or [])]
    else:
        pool = ["control: " + str(x) for x in (report.get("labels") or [])]
    full = next((x for x in pool if x.split(": ", 1)[-1].startswith(short)), None)
    if full is None:
        return "control", short, [], True
    role, _, lab = full.partition(": ")
    i = pool.index(full)
    ctx = pool[max(0, min(i - 20, len(pool) - 40)):][:40]
    return role, lab, ctx, True


def procedures_from(report: Dict[str, Any], url: str, cap: int = 150) -> List[Dict[str, Any]]:
    host = WL.host_of(url)
    site = site_name(host)
    ex = (report.get("scan") or {}).get("explore") or {}
    nodes = [n for n in ex.get("nodes", []) if n.get("path")]
    by_path = {n["path"]: n for n in nodes}
    out: List[Dict[str, Any]] = []
    seen = set()
    for n in nodes:
        if n.get("outcome") not in EFFECTS:
            continue
        chain = chain_of(n["path"])
        if not chain or tuple(chain) in seen:
            continue
        seen.add(tuple(chain))
        role, label, _, _ = _resolve(report, by_path, chain)
        if len(chain) >= 2:
            par = by_path.get(" > ".join(chain[:-1]), {})
            if any(str(c).split(": ", 1)[-1].lower().startswith(label.lower()[:24]) for c in (par.get("context") or [])):
                chain = chain[-1:]                                      # it was already on screen before the parent was clicked: the parent is not part of the way there
        steps = []
        for i in range(len(chain)):
            anc = by_path.get(" > ".join(chain[:i + 1]), {})
            r_i, l_i, _, _ = _resolve(report, by_path, chain[:i + 1])
            exp = outcome_phrase(anc) if anc else ""
            steps.append({"text": f"Click '{l_i}'" + (f" ({exp})" if exp else ""), "target": l_i, "role": r_i, "route_hint": "click", "expect": exp})
        out.append({"goal": goal_of(site, label, n, chain)[:190], "steps": steps, "pid": _sha("webact", host, " > ".join(chain), n["outcome"]), "outcome": outcome_phrase(n)})
        if len(out) >= cap:
            break
    return out


def training_rows_from(report: Dict[str, Any], url: str) -> List[Dict[str, Any]]:
    host = WL.host_of(url)
    site = site_name(host)
    ex = (report.get("scan") or {}).get("explore") or {}
    nodes = [n for n in ex.get("nodes", []) if n.get("path")]
    by_path = {n["path"]: n for n in nodes}
    rows: List[Dict[str, Any]] = []
    seen = set()
    for n in nodes:
        if n.get("outcome") not in EFFECTS:
            continue
        chain = chain_of(n["path"])
        if not chain or tuple(chain) in seen:
            continue
        seen.add(tuple(chain))
        role, label, ctx, recon = _resolve(report, by_path, chain)
        tgt = f"{role}: {label}"
        if tgt not in ctx:
            ctx = [tgt] + ctx[:39]
        if len(ctx) < 3:
            continue
        idx = ctx.index(tgt) + 1
        lines = "\n".join(f"#{i} {c.split(': ', 1)[0]} '{c.split(': ', 1)[-1]}'" for i, c in enumerate(ctx, 1))
        goal = goal_of(site, label, n, chain[-1:])
        user = f"Application: web:{host}\nElements:\n{lines}\nIntent: {goal}\nPredict exact Action JSON:"
        answer = json.dumps([{"step": 1, "action": "click", "target_id": idx, "hotkey": None, "text": None, "verify_expectation": outcome_phrase(n)}], ensure_ascii=False)
        rows.append({"messages": [{"role": "system", "content": [{"type": "text", "text": SYSTEM}]}, {"role": "user", "content": [{"type": "text", "text": user}]},
                                  {"role": "assistant", "content": [{"type": "text", "text": answer}]}],
                     "meta": {"source": "web-explore", "host": host, "path": n["path"], "outcome": n["outcome"], "action": "click", "elements": len(ctx), "target_id": idx, "modality": "text-only (no screenshot)",
                              "context": "reconstructed from the parent menu / page labels" if recon else "real: the controls in view when the click was chosen", "pair_id": _sha("webrow", host, " > ".join(chain))}})
    return rows


def file_actions(rag: Any, report: Dict[str, Any], url: str, run: str, write: bool = True, rows_path: str = "") -> Dict[str, Any]:
    key = "webapp:" + WL.host_of(url)
    rows_path = rows_path or ROWS_PATH
    procs = procedures_from(report, url)
    rows = training_rows_from(report, url)
    res = {"procedures": 0, "train_rows": 0, "procedures_found": len(procs), "rows_found": len(rows), "pids": []}
    if not write:
        return res
    if rag is not None and procs:
        with WL.rag_lock():
            for p in procs:
                with contextlib.suppress(Exception):
                    rag.proc.ingest_procedure(key, p["goal"], p["steps"], f"web_explore:{run}", trust="web", procedure_id=p["pid"])
                    res["procedures"] += 1
                    res["pids"].append(p["pid"])
    if rows:
        os.makedirs(os.path.dirname(rows_path), exist_ok=True)
        have = set()
        if os.path.isfile(rows_path):
            for l in open(rows_path, encoding="utf-8"):
                with contextlib.suppress(Exception):
                    have.add(json.loads(l)["meta"]["pair_id"])
        fresh = [r for r in rows if r["meta"]["pair_id"] not in have]
        with open(rows_path, "a", encoding="utf-8") as f:
            for r in fresh:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        res["train_rows"] = len(fresh)
    return res


def backfill(rag: Any, reports_root: str = "", rows_path: str = "", run: str = "backfill", log=print, ledger: str = "") -> Dict[str, Any]:
    """File the outcomes of every web report already on disk (newest report per site, blocked ones skipped)."""
    reports_root = reports_root or os.path.join("D:" + os.sep, "new_automation", "reports", "try_app")
    newest: Dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(reports_root, "2026*", "report.json")), key=os.path.getmtime):
        with contextlib.suppress(Exception):
            rep = json.load(open(p, encoding="utf-8"))
            if (rep.get("scan") or {}).get("explore") and not ((rep.get("understanding") or {}).get("auth") or {}).get("blocked"):
                newest[WL.host_of(rep.get("target", ""))] = p
    total = {"sites": 0, "procedures": 0, "train_rows": 0}
    for host, p in newest.items():
        rep = json.load(open(p, encoding="utf-8"))
        r = file_actions(rag, rep, rep.get("target", host), run, rows_path=rows_path)
        if ledger and r["pids"]:
            with open(ledger, "a", encoding="utf-8") as f:
                f.write(json.dumps({"run": run, "key": "webapp:" + host, "commands": [], "hotkeys": [], "procedures": r["pids"]}) + "\n")
        total["sites"] += 1
        total["procedures"] += r["procedures"]
        total["train_rows"] += r["train_rows"]
        log(f"  {host:<32} {r['procedures']:>4} procedures, {r['train_rows']:>4} training rows")
    return total


def main(argv: Optional[Sequence[str]] = None) -> int:
    a = list(argv if argv is not None else sys.argv[1:])
    if not a or a[0] != "backfill":
        print(__doc__)
        return 2
    from core_organs import rag as R
    import time
    from core_organs.harvest import web_curriculum as WC
    rag = R.get_rag()
    os.makedirs(WC.OUT, exist_ok=True)
    print(json.dumps(backfill(rag, run="backfill_" + time.strftime("%Y%m%d_%H%M%S"), ledger=WC.LEDGER), indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
