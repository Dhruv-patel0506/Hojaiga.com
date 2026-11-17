"""
harvest.web_kind -- what KIND of web app is this?  Learned from the sites already scanned, not written by hand.

Every site the web curriculum scans arrives with a category its ladder gave it ('jobs', 'social', 'video', 'dev_platform' ...: the curriculum author's decision, never the model's own guess).
This module keeps one WORD PROFILE per site (what its buttons, menus, headings and description say) and recognises a new site by comparing its words with each category's average profile:

    add_example(host, category, words)   store / replace the profile of one site (data/web_curriculum/examples.jsonl)
    WebKind().classify(words)            [(category, similarity)], margin, status ('confident' | 'ambiguous' | 'too_few_examples')
    WebKind().leave_one_out()            honest accuracy: each site is held out, its category is predicted from all the OTHER sites
    WebKind().distinctive(category)      the words that most set a category apart (what a 'jobs' site says that others do not)

Plain TF-IDF + nearest class average (cosine). No model weights, nothing opaque: the whole 'model' is rebuilt from the examples file in milliseconds, so every new site makes the next
recognition better and the accuracy number is recomputed on real held-out sites.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
FOLDER = os.path.join(DATA, "web_curriculum")
EXAMPLES = os.path.join(FOLDER, "examples.jsonl")
MIN_EXAMPLES = 8                     # fewer labelled sites than this and no verdict is given
MIN_CLASSES = 3
CONFIDENT_MARGIN = 0.06
STOP = set("the and for you your with from that this are was have has not all new more can will get use our out now one any how what who why when where about into over under more less its their they them "
           "than then also just only each both such other some most many much very here there per via etc inc ltd com www http https html page home skip main content menu close open next previous back top "
           "click learn read view see show hide toggle button link navigation sign log login logout free".split())


def words_of(texts: Iterable[str]) -> Counter:
    c: Counter = Counter()
    for t in texts:
        for w in re.findall(r"[a-z]{3,}", (t or "").lower()):
            if w not in STOP and len(w) <= 22:
                c[w] += 1
    return c


def load_examples(path: str = "") -> List[Dict[str, Any]]:
    path = path or EXAMPLES
    out: Dict[str, Dict[str, Any]] = {}
    if os.path.isfile(path):
        for l in open(path, encoding="utf-8"):
            if l.strip():
                try:
                    j = json.loads(l)
                    out[j["host"]] = j                                   # the last line for a host wins
                except Exception:
                    pass
    return list(out.values())


def add_example(host: str, category: str, words: Counter, path: str = "") -> bool:
    """Store / replace the profile of one site. Fewer than 25 distinct words is not a profile (blocked page, empty shell) and is refused."""
    path = path or EXAMPLES
    if len(words) < 25 or not category:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"host": host, "category": category, "words": dict(words.most_common(400))}, ensure_ascii=False) + "\n")
    return True


def _vectors(examples: Sequence[Dict[str, Any]], idf: Dict[str, float]) -> List[Dict[str, float]]:
    out = []
    for e in examples:
        v = {w: (1.0 + math.log(n)) * idf[w] for w, n in e["words"].items() if w in idf}
        z = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out.append({w: x / z for w, x in v.items()})
    return out


MIN_DF = 1                           # tried 2 and 3 on 33 sites: held-out accuracy FELL (0.42 -> 0.29 / 0.39): with 1-6 sites per category a word seen by one site is often the category's signal. Revisit when there are 10+ per category.


def _idf(examples: Sequence[Dict[str, Any]], min_df: int = -1) -> Dict[str, float]:
    min_df = MIN_DF if min_df < 0 else min_df
    df: Counter = Counter()
    for e in examples:
        df.update(e["words"].keys())
    n = len(examples)
    return {w: math.log((n + 1) / (d + 1)) + 1.0 for w, d in df.items() if d >= min_df or n < 6}


def _centroids(examples: Sequence[Dict[str, Any]], vecs: Sequence[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    acc: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cnt: Counter = Counter()
    for e, v in zip(examples, vecs):
        cnt[e["category"]] += 1
        for w, x in v.items():
            acc[e["category"]][w] += x
    out = {}
    for c, d in acc.items():
        z = math.sqrt(sum(x * x for x in d.values())) or 1.0
        out[c] = {w: x / z for w, x in d.items()}
    return out


def _cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


class WebKind:
    def __init__(self, examples: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        self.examples = list(examples) if examples is not None else load_examples()
        self.idf = _idf(self.examples)
        self.vecs = _vectors(self.examples, self.idf)
        self.centroids = _centroids(self.examples, self.vecs)

    def classes(self) -> Dict[str, int]:
        return dict(Counter(e["category"] for e in self.examples))

    def classify(self, words: Counter, exclude_host: str = "") -> Dict[str, Any]:
        if len(self.examples) < MIN_EXAMPLES or len(self.classes()) < MIN_CLASSES:
            return {"status": "too_few_examples", "ranked": [], "margin": 0.0, "n_examples": len(self.examples)}
        ex = [e for e in self.examples if e["host"] != exclude_host]
        idf = _idf(ex) if exclude_host else self.idf
        vecs = _vectors(ex, idf) if exclude_host else self.vecs
        cents = _centroids(ex, vecs) if exclude_host else self.centroids
        v = {w: (1.0 + math.log(n)) * idf[w] for w, n in words.items() if w in idf}
        z = math.sqrt(sum(x * x for x in v.values())) or 1.0
        v = {w: x / z for w, x in v.items()}
        ranked = sorted(((c, round(_cos(v, cv), 4)) for c, cv in cents.items()), key=lambda kv: -kv[1])
        margin = round(ranked[0][1] - ranked[1][1], 4) if len(ranked) > 1 else ranked[0][1]
        return {"status": "confident" if margin >= CONFIDENT_MARGIN and ranked[0][1] > 0.05 else "ambiguous", "ranked": ranked[:4], "margin": margin, "n_examples": len(ex)}

    def leave_one_out(self) -> Dict[str, Any]:
        """Each site held out in turn; its category predicted from all the others. Classes with a single site cannot be predicted from the others and are counted separately."""
        n = ok1 = ok2 = skipped = 0
        wrong: List[Tuple[str, str, str]] = []
        counts = self.classes()
        for e in self.examples:
            if counts[e["category"]] < 2:
                skipped += 1
                continue
            r = self.classify(Counter(e["words"]), exclude_host=e["host"])
            if not r["ranked"]:
                continue
            n += 1
            top = [c for c, _ in r["ranked"]]
            ok1 += top[0] == e["category"]
            ok2 += e["category"] in top[:2]
            if top[0] != e["category"]:
                wrong.append((e["host"], e["category"], top[0]))
        return {"sites": len(self.examples), "scored": n, "top1": round(ok1 / n, 3) if n else None, "top2": round(ok2 / n, 3) if n else None, "single_site_classes_skipped": skipped,
                "wrong": wrong[:12]}

    def distinctive(self, category: str, top: int = 12) -> List[str]:
        c = self.centroids.get(category, {})
        others = [v for k, v in self.centroids.items() if k != category]
        avg = defaultdict(float)
        for o in others:
            for w, x in o.items():
                avg[w] += x / max(1, len(others))
        return [w for w, _ in sorted(((w, x - avg.get(w, 0.0)) for w, x in c.items()), key=lambda kv: -kv[1])[:top]]
