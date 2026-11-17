"""
train_rows -- training rows for the adapter, built from the REAL crawl rows (harvest/web_action_rows.jsonl), in four kinds:

    pick      the crawl row as it is: find the control that does what the intent says          (action click)
    confirm   the same real control lists, but the control asked for would pay / send / publish / delete / sign out / agree / install:
              the answer is "ask the person first" (action confirm, text = the kind of risk, verify_expectation = what it does)      <- labels from mind.consequence
    resume    a multi-step path with a Plan and how many steps are done, and the screen at that point: the next click                  (action click)
    replan    the same plan, but the screen belongs to somewhere else (another site, none of the plan's controls): say so             (action replan)

Honest limits, stated where the rows are written: pick/resume labels come from what the explorer saw happen; confirm labels come from the RULES in consequence.py (so a model trained on them
learns to apply those rules to labels it has never seen - it is not an independent source of truth); replan rows are constructed by pairing a plan with a screen from another site.
Whole SITES are held out of training, so the evaluation measures sites the adapter never saw.

    python -m core_organs.mind.train_rows build [--out DIR] [--rows P] [--seed N]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import time
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core_organs.mind import consequence as CQ
from core_organs.mind import picker as PK

ROWS = r"D:\new_automation\data\ai_root\harvest\training\web_action_rows.jsonl"
RUNS = r"D:\new_automation\data\ai_root\harvest\training\runs"
ROUND2_HELD = ["brew.sh", "code.org", "dev.to", "doc.rust-lang.org", "india.gov.in", "investopedia.com", "khanacademy.org", "mayoclinic.org", "medlineplus.gov", "openstreetmap.org", "pythontutor.com", "telegram.org", "vimeo.com", "xe.com"]
CLICKY = ("link", "button", "menuitem", "tab", "tabitem", "summary", "clickable", "submit input", "splitbutton", "listitem", "treeitem", "hyperlink")
_LINE = re.compile(r"^#(\d+) (.+?) '(.*)'$")
_INTENTS = ["Press the '{l}' button", "Click '{l}'", "Go ahead and use '{l}'", "I want to {w}", "Do this: {l}", "Use the '{l}' control", "Next, '{l}'"]


def _text(row: Dict[str, Any], i: int) -> str:
    return row["messages"][i]["content"][0]["text"]


def parse_user(user: str) -> Tuple[str, List[Dict[str, str]], str]:
    app = re.search(r"^Application: (.*)$", user, re.M)
    els = []
    for ln in user.split("\nIntent:")[0].splitlines():
        m = _LINE.match(ln.strip())
        if m:
            els.append({"role": m.group(2), "name": m.group(3)})
    intent = re.search(r"\nIntent: (.*?)\nPredict exact Action JSON:", user, re.S)
    return (app.group(1) if app else ""), els, (intent.group(1) if intent else "")


def _row(app: str, els: Sequence[Dict[str, str]], intent: str, answer: Dict[str, Any], meta: Dict[str, Any], plan: Sequence[str] = (), done: int = 0) -> Dict[str, Any]:
    return {"messages": [{"role": "system", "content": [{"type": "text", "text": PK.SYSTEM_V2}]},
                         {"role": "user", "content": [{"type": "text", "text": PK.user_prompt(app, els, intent, plan, done)}]},
                         {"role": "assistant", "content": [{"type": "text", "text": json.dumps([answer], ensure_ascii=False)}]}], "meta": meta}


def _act(kind: str, tid: Optional[int], text: Optional[str], expect: str) -> Dict[str, Any]:
    return {"step": 1, "action": kind, "target_id": tid, "hotkey": None, "text": text, "verify_expectation": expect}


def held_hosts(hosts: Sequence[str], round2: Sequence[str] = ROUND2_HELD) -> set:
    """Round 2's held-out sites stay held out; of the sites added since, one in five (by a stable hash) joins them."""
    return {h for h in hosts if h in round2 or zlib.crc32(h.encode()) % 5 == 0}


def build(rows_path: str = ROWS, out_dir: str = "", seed: int = 3407, max_confirm_per_host: int = 14, max_resume: int = 1500, max_replan: int = 450) -> Dict[str, Any]:
    rnd = random.Random(seed)
    raw = [json.loads(l) for l in open(rows_path, encoding="utf-8") if l.strip()]
    seen, base = set(), []
    for r in raw:
        try:
            a = json.loads(_text(r, 2))[0]
            u = _text(r, 1)
            if a.get("action") != "click" or a.get("target_id") is None or f"#{a['target_id']} " not in u:
                continue
        except Exception:
            continue
        k = (u, _text(r, 2))
        if k in seen:
            continue
        seen.add(k)
        base.append(r)
    by_path: Dict[Tuple[str, str], Dict[str, Any]] = {(r["meta"]["host"], r["meta"]["path"]): r for r in base}
    hosts = sorted({r["meta"]["host"] for r in base})
    held = held_hosts(hosts)

    out: List[Dict[str, Any]] = []
    def _risky_target(els: Sequence[Dict[str, str]], a: Dict[str, Any]) -> bool:
        """A crawl row whose answer is a control the rules say to ask about would contradict the confirm rows: leave it out."""
        try:
            e = els[int(a["target_id"]) - 1]
        except (KeyError, TypeError, ValueError, IndexError):
            return True
        return CQ.classify_label(e["name"], e["role"])["gate"] == "confirm"

    # ---- pick: the crawl rows under the v2 instructions
    skipped_risky = 0
    for r in base:
        app, els, intent = parse_user(_text(r, 1))
        a = json.loads(_text(r, 2))[0]
        if _risky_target(els, a):
            skipped_risky += 1
            continue
        out.append(_row(app, els, intent, a, {**r["meta"], "task": "pick"}))
    # ---- confirm: a risky control in a REAL list
    per_host = collections.Counter()
    cand = list(base)
    rnd.shuffle(cand)
    for r in cand:
        host = r["meta"]["host"]
        if per_host[host] >= max_confirm_per_host:
            continue
        app, els, _ = parse_user(_text(r, 1))
        risky = [(i, e, CQ.classify_label(e["name"], e["role"])) for i, e in enumerate(els, 1) if e["role"] in CLICKY]
        risky = [x for x in risky if x[2]["gate"] == "confirm" and x[2]["risk"] != "none"]
        if not risky:
            continue
        i, e, c = rnd.choice(risky)
        tmpl = rnd.choice(_INTENTS)
        intent = tmpl.format(l=e["name"], w=re.sub(r"\s+", " ", e["name"]).strip().lower())
        out.append(_row(app, els, intent, _act("confirm", i, c["risk"], f"asks the person first: it {c['consequence']}"), {"source": "consequence-rules", "host": host, "path": e["name"][:60], "task": "confirm", "risk": c["risk"], "severity": c["severity"]}))
        per_host[host] += 1
    # ---- resume: the screen at step k of a longer path, with the plan and how many steps are done
    resume = []
    for r in base:
        chain = [p.strip() for p in r["meta"]["path"].split(" > ") if p.strip()]
        if len(chain) < 2:
            continue
        host = r["meta"]["host"]
        for k in range(0, len(chain)):
            st = by_path.get((host, " > ".join(chain[:k + 1])))
            if not st:
                break
            app, els, _ = parse_user(_text(st, 1))
            a = json.loads(_text(st, 2))[0]
            resume.append((host, app, els, _parse_goal(_text(r, 1)), [f"Click '{c}'" for c in chain], k, a, r["meta"]))
    rnd.shuffle(resume)
    quota = collections.Counter()
    n_res = 0
    for host, app, els, goal, plan, k, a, meta in resume:
        if n_res >= max_resume or quota[host] >= max(6, max_resume // max(1, len(hosts))) * 2 or _risky_target(els, a):
            continue
        out.append(_row(app, els, goal, a, {"source": "web-explore", "host": host, "path": meta["path"], "task": "resume", "step_done": k, "plan_len": len(plan)}, plan=plan, done=k))
        quota[host] += 1
        n_res += 1
    # ---- replan: the plan is for one place, the screen is another site's
    n_rep = 0
    pool = [x for x in resume if x[5] == 0]
    for _ in range(max_replan * 3):
        if n_rep >= max_replan or len(pool) < 2:
            break
        a_, b_ = rnd.choice(pool), rnd.choice(pool)
        if a_[0] == b_[0]:
            continue
        plan_targets = [re.sub(r"^Click '|'$", "", p) for p in a_[4]]
        screen_names = [e["name"] for e in b_[2]]
        if any(any(t[:20].lower() in n.lower() for n in screen_names) for t in plan_targets):
            continue                                                       # some control of the plan is on that screen after all: not a clean "not here"
        k = rnd.randint(0, len(a_[4]) - 1)
        out.append(_row(b_[1], b_[2], a_[3], _act("replan", None, "not_here", "the screen shows a different place than the plan expects"),
                        {"source": "constructed", "host": b_[0], "path": a_[7]["path"], "task": "replan", "plan_host": a_[0], "step_done": k, "plan_len": len(a_[4])}, plan=a_[4], done=k))
        n_rep += 1
    # ---- split by site
    train = [r for r in out if r["meta"]["host"] not in held]
    ev = [r for r in out if r["meta"]["host"] in held]
    rnd.shuffle(train)
    out_dir = out_dir or os.path.join(RUNS, time.strftime("run_%Y%m%d_mind"))
    os.makedirs(out_dir, exist_ok=True)
    for name, rows in (("train", train), ("eval", ev)):
        with open(os.path.join(out_dir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cnt = lambda rows: dict(collections.Counter(r["meta"]["task"] for r in rows))
    summary = {"rows_file": rows_path, "crawl_rows_used": len(base), "crawl_rows_left_out_as_risky_targets": skipped_risky, "train": len(train), "eval": len(ev), "train_by_task": cnt(train), "eval_by_task": cnt(ev),
               "train_sites": len({r["meta"]["host"] for r in train}), "held_out_sites": sorted(held & set(hosts)), "confirm_risks": dict(collections.Counter(r["meta"].get("risk") for r in out if r["meta"]["task"] == "confirm")),
               "limits": ["confirm labels come from the rules in mind/consequence.py (distillation, not independent truth)", "replan rows are constructed (plan from one site, screen from another)",
                          "pick/resume contexts are reconstructed from the parent menu / page labels, text only, no screenshots"], "out_dir": out_dir}
    json.dump(summary, open(os.path.join(out_dir, "data_summary.json"), "w"), indent=2)
    return summary


def _parse_goal(user: str) -> str:
    return parse_user(user)[2]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--rows", default=ROWS)
    ap.add_argument("--out", default="")
    ap.add_argument("--seed", type=int, default=3407)
    a = ap.parse_args(argv)
    print(json.dumps(build(a.rows, a.out, a.seed), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
