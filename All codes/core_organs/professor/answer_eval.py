"""
professor.answer_eval -- A LABELLED QUESTION SET WITH KNOWN ANSWERS, AND A MEASURED ACCURACY NUMBER for the Professor's answers.

The labels come from sources that are right by construction, never from the model being measured:
  where      'In Word, where is Custom Margins?'      -> the tab and the group/menu the control lives in: the vendor's command manifest checked against THIS build, or a live scan
                                                          (menus opened, ribbon walked) - catalog verbs whose sources say they were MEASURED
  shortcut   'What is the keyboard shortcut for Find?' -> the chord the application itself prints (catalog verbs with a shortcut from the tree / native menus)
  howto      'How do I change margins in Word?'        -> the controls of a guide procedure whose steps ALL ground in the application (ordered control labels)
The set is generated once with a fixed seed and FROZEN (data/professor/eval/qa_<app>.json); --rebuild makes a new one.

Two answerers are measured on the same questions:
  rules   the deterministic path: catalog lookup / guide grounding (no model)
  model   what the Professor says: guide passages (agentic RAG) + the matching controls from the catalog -> the local vision-language model (the 8B 'brain'), answer in words
Scoring is by the answer CONTAINING the labelled facts (tab + parent / the chord / at least half of the procedure's controls, the first one included) - folded, plural-insensitive.
Results: data/professor/eval/results_<stamp>.json (+ .md): accuracy per kind, per answerer, per application, and every miss with the answer that was given.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import config as CFG
from .schema import fold

EVAL_DIR = os.path.join(CFG.DATA_DIR, "eval")
MEASURED = {"uia", "win32-menu", "menu-expand", "ribbon", "reveal", "vendor-manifest"}


def _norm(s: str) -> str:
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in fold((s or "").replace("&", " and ")).split())


def _contains(answer: str, fact: str) -> bool:
    a, f = _norm(answer), _norm(fact)
    return bool(f) and (f in a or (len(f.split()) > 1 and all(w in a.split() for w in f.split())))


def app_name(app_key: str) -> str:
    try:
        from .knowledge import guide_corpus as GCP
        a = GCP.find_app(app_key)
        if a:
            return a.get("name") or app_key
    except Exception:
        pass
    return app_key


# ------------------------------------------------------------------------------------------------------------- the set
def build_set(app_key: str, n_per_kind: int = 8, seed: int = 7, catalog: Any = None) -> List[Dict[str, Any]]:
    from .harvest import Catalog
    from . import workflows as WF
    cat = catalog or Catalog.load(app_key)
    if cat is None:
        return []
    rnd = random.Random(seed)
    name = app_name(app_key)
    out: List[Dict[str, Any]] = []
    # where: a control with a real path (tab/menu + group/opener), measured or vendor-verified; not a context menu, not a person's list
    where = [v for v in cat.verbs if len(v.path) >= 1 and set(v.sources or []) & MEASURED and not str(v.path[0]).startswith(("Context menu", "Quick Access"))
             and 3 <= len(v.label) <= 40 and v.role in ("button", "dropdown", "toggle", "menu_item", "checkbox") and not re.search(r"(?i)recent|history|\d{2,}", v.label)]
    seen = set()
    uniq = []
    for v in where:                                                           # a label that exists in two places has no single right answer: left out
        k = fold(v.label)
        if k in seen:
            uniq = [u for u in uniq if fold(u.label) != k]
            continue
        seen.add(k)
        uniq.append(v)
    for v in rnd.sample(uniq, min(n_per_kind, len(uniq))):
        facts = [v.path[0]] + ([v.path[-1]] if len(v.path) > 1 else [])
        out.append({"id": f"{app_key}.where.{v.id}", "app": app_key, "kind": "where", "question": f"In {name}, where do I find '{v.label}'?", "facts": facts, "need": "all",
                    "label_source": "+".join(sorted(set(v.sources or []))), "target": v.label})
    # shortcut: chords the application prints
    sc = [v for v in cat.verbs if v.shortcut and set(v.sources or []) & (MEASURED - {"vendor-manifest"}) and 2 <= len(v.label) <= 40]
    by_chord: Dict[str, List[Any]] = {}
    for v in sc:
        by_chord.setdefault(v.shortcut, []).append(v)
    sc = [vs[0] for vs in by_chord.values() if len({fold(x.label) for x in vs}) == 1]
    for v in rnd.sample(sc, min(n_per_kind, len(sc))):
        out.append({"id": f"{app_key}.shortcut.{v.id}", "app": app_key, "kind": "shortcut", "question": f"What is the keyboard shortcut for '{v.label}' in {name}?", "facts": [v.shortcut],
                    "need": "all", "label_source": "+".join(sorted(set(v.sources or []))), "target": v.label})
    # howto: guide procedures whose every applicable step grounds in a control
    doc = WF.build(app_key, catalog=cat, write=False)
    good = []
    for w in doc.get("workflows", []):
        ctl = [s["verb"] for s in w["steps"] if s["verb"] and s["how"] in ("path", "label", "chord", "group")]
        app_steps = [s for s in w["steps"] if s["how"] != "outside"]
        if ctl and app_steps and all(s["how"] not in ("none", "human", "gesture") for s in app_steps) and len(w["goal"]) > 6:
            good.append((w, list(dict.fromkeys(ctl))))
    for w, ctl in rnd.sample(good, min(n_per_kind, len(good))):
        g = re.sub(r"(?i)^\s*(how (?:to|do i|can i)|to)\s+", "", w["goal"]).strip().rstrip("?.")
        g = re.sub(r"(?i)\s+(?:in|on|with|using)\s+(?:microsoft\s+)?" + re.escape(name.replace("Microsoft ", "")) + r"\b.*$", "", g)
        out.append({"id": f"{app_key}.howto.{w['id']}", "app": app_key, "kind": "howto", "question": f"How do I {g[0].lower() + g[1:]} in {name}?", "facts": ctl[:4],
                    "need": "half_with_first", "label_source": "guide procedure fully grounded: " + w["source"], "target": w["goal"]})
    return out


def score(answer: str, item: Dict[str, Any]) -> Tuple[bool, float]:
    facts = item["facts"]
    hits = [f for f in facts if _contains(answer, f) or (item["kind"] == "shortcut" and _norm(f).replace("+", " ") in _norm(answer.replace("+", " ")))]
    share = len(hits) / max(1, len(facts))
    if item["need"] == "all":
        return share == 1.0, share
    return (share >= 0.5 and bool(facts) and facts[0] in hits), share


# ------------------------------------------------------------------------------------------------------------- answerers
def answer_rules(item: Dict[str, Any], cat: Any, ix: Any) -> str:
    """No model: the catalog / the guide grounding answers directly."""
    from .knowledge import guide_steps as GS
    if item["kind"] in ("where", "shortcut"):
        v, c = GS.resolve_label_ctx(cat, item["target"])
        if v is None:
            return "I don't know."
        if item["kind"] == "where":
            return f"{' > '.join(v.path + [v.label])}"
        return f"{v.label}: {v.shortcut or 'no shortcut'}"
    gp = GS.plan_from_guide(item["target"], cat, ix, item["app"], None, k=4)
    if gp is None:
        return "I don't know."
    return "; ".join(" > ".join((list(g.verb.path) + [g.verb.label]) if g.verb is not None else [g.step.raw[:40]]) for g in gp["steps"])


def answer_model(item: Dict[str, Any], cat: Any, ix: Any, brain: Any) -> str:
    """What the Professor's language model says, given the same knowledge the Professor has: guide passages + the catalog's matching controls (paths, shortcuts)."""
    q = item["question"]
    passages = []
    try:
        res = ix.retrieve(q, item["app"], 3, None, rounds=1)
        passages = [f"[{p.cite}] {p.text[:700]}" for p in res.get("passages", [])[:3]]
    except Exception:
        pass
    words = re.sub(r"(?i)^(in \w+[ ,]+)?(where do i find|what is the keyboard shortcut for|how do i)\s+", "", q)
    ctl = [f"{' > '.join(v.path + [v.label])}" + (f" ({v.shortcut})" if v.shortcut else "") for v in cat.best(words, 10)]
    sysmsg = ("You are a software tutor. Answer the learner's question about the application using ONLY the guide passages and the list of the application's controls given. "
              "Name the exact path (Tab or menu > group > control) and the keyboard shortcut when there is one. If the material does not contain the answer, say you don't know. "
              "Answer in at most three short sentences.")
    prompt = f"Question: {q}\n\nGuide passages:\n" + ("\n".join(passages) or "(none)") + "\n\nControls of the application (path > control (shortcut)):\n" + ("\n".join(ctl) or "(none)")
    r = brain.generate(sysmsg, prompt, max_tokens=140, temperature=0.0, timeout=120)
    return (r.text or "").strip() if r.ok else f"(model error: {getattr(r, 'error', '') or 'no answer'})"


# ------------------------------------------------------------------------------------------------------------- the run
def set_path(app_key: str) -> str:
    return os.path.join(EVAL_DIR, f"qa_{app_key}.json")


def load_or_build(app_key: str, rebuild: bool = False, n_per_kind: int = 8) -> List[Dict[str, Any]]:
    p = set_path(app_key)
    if os.path.isfile(p) and not rebuild:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)["items"]
    items = build_set(app_key, n_per_kind)
    os.makedirs(EVAL_DIR, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"app": app_key, "built": time.strftime("%Y-%m-%d %H:%M:%S"), "about": __doc__.strip().splitlines()[0], "items": items}, fh, indent=1, ensure_ascii=False)
    return items


def run(apps: Sequence[str], use_model: bool = True, rebuild: bool = False, n_per_kind: int = 8, log: Callable[[str], None] = print) -> Dict[str, Any]:
    from .harvest import Catalog
    from .knowledge import manual_rag as MR
    brain = None
    if use_model:
        try:
            from .brain import Brain
            brain = Brain()
            if not brain.available():
                log("the language model is not reachable: only the rules answerer is measured")
                brain = None
        except Exception as exc:
            log(f"no language model ({type(exc).__name__}): only the rules answerer is measured")
            brain = None
    ix = MR.ManualIndex()
    t0 = time.time()
    rows: List[Dict[str, Any]] = []
    try:
        for app in apps:
            cat = Catalog.load(app)
            if cat is None:
                log(f"{app}: no catalog - skipped")
                continue
            items = load_or_build(app, rebuild, n_per_kind)
            log(f"{app}: {len(items)} labelled questions")
            for it in items:
                row = {"id": it["id"], "app": app, "kind": it["kind"], "question": it["question"], "facts": it["facts"]}
                a = answer_rules(it, cat, ix)
                row["rules_answer"], (row["rules_ok"], row["rules_share"]) = a[:300], score(a, it)
                if brain is not None:
                    t1 = time.time()
                    m = answer_model(it, cat, ix, brain)
                    row["model_answer"], (row["model_ok"], row["model_share"]) = m[:400], score(m, it)
                    row["model_s"] = round(time.time() - t1, 1)
                rows.append(row)
                log(f"  [{it['kind']:8s}] rules {'OK ' if row['rules_ok'] else 'no '}" + (f" model {'OK ' if row.get('model_ok') else 'no '}({row.get('model_s')}s)" if brain is not None else "") + f"  {it['question'][:70]}")
    finally:
        ix.close()

    def acc(sel: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
        vals = [r[key] for r in sel if key in r]
        return round(100.0 * sum(1 for v in vals if v) / len(vals), 1) if vals else None

    summary: Dict[str, Any] = {"questions": len(rows), "seconds": round(time.time() - t0, 1), "rules_accuracy": acc(rows, "rules_ok"), "model_accuracy": acc(rows, "model_ok"), "by_kind": {}, "by_app": {}}
    for k in sorted({r["kind"] for r in rows}):
        sel = [r for r in rows if r["kind"] == k]
        summary["by_kind"][k] = {"n": len(sel), "rules": acc(sel, "rules_ok"), "model": acc(sel, "model_ok")}
    for a in sorted({r["app"] for r in rows}):
        sel = [r for r in rows if r["app"] == a]
        summary["by_app"][a] = {"n": len(sel), "rules": acc(sel, "rules_ok"), "model": acc(sel, "model_ok")}
    out = {"run": time.strftime("%Y-%m-%d %H:%M:%S"), "model": "local brain (professor.brain)" if brain is not None else "none", "summary": summary, "rows": rows}
    os.makedirs(EVAL_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(EVAL_DIR, f"results_{stamp}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    md = [f"# Answer accuracy - {out['run']}", "", f"{summary['questions']} labelled questions · rules {summary['rules_accuracy']}% · model {summary['model_accuracy']}%", "",
          "| kind | n | rules | model |", "|---|---|---|---|"] + [f"| {k} | {v['n']} | {v['rules']} | {v['model']} |" for k, v in summary["by_kind"].items()] + \
         ["", "| app | n | rules | model |", "|---|---|---|---|"] + [f"| {k} | {v['n']} | {v['rules']} | {v['model']} |" for k, v in summary["by_app"].items()] + ["", "## Misses (model)", ""] + \
         [f"- **{r['question']}** expected {r['facts']} - said: {r.get('model_answer', '')[:200]}" for r in rows if r.get("model_ok") is False][:60]
    with open(os.path.join(EVAL_DIR, f"results_{stamp}.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    out["files"] = [os.path.join(EVAL_DIR, f"results_{stamp}.json"), os.path.join(EVAL_DIR, f"results_{stamp}.md")]
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Measure answer accuracy on a labelled question set")
    ap.add_argument("apps", nargs="*", default=["notepad", "mspaint", "winword", "powerpnt"])
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    r = run(a.apps, use_model=not a.no_model, rebuild=a.rebuild, n_per_kind=a.n)
    print(json.dumps(r["summary"], indent=1))
