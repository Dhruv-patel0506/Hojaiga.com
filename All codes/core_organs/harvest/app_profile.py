"""
harvest.app_profile -- what KIND of software an app is, as a mixture, from what the videos showed on its screens.

An app is rarely one pattern: Notion is part word processor, part database, part kanban; Photoshop is raster editor plus a little vector editor; Excalidraw is a whiteboard with a vector
editor's tools. So the profile is a DISTRIBUTION over the 25 archetypes (rag.archetypes), never a single hard-coded label:

    primary      the archetype with the largest share
    secondary    every other archetype with a share >= SECOND_FRACTION of the primary's (the hybrid)
    hybrid       True when there is at least one secondary pattern
    status       the router's own evidence verdict (candidate / weak_candidate / ambiguous / insufficient): a profile is written to the RAG only with enough class-specific words

The evidence is the text the OCR read at the places several authors showed (menu entries, panel headings, shortcut names), turned into the same word signature the scanner's control names
produce, scored by the existing ArchetypeRouter. The router's relative scores become shares with a softmax whose temperature is CALIBRATED on the real scanned apps that carry a known
label (rag.archetypes.REAL_LABELS): the temperature that minimises the log-loss of the true class. `evaluate()` reports leave-nothing-hidden numbers on those apps.
The app's NAME is never used as evidence here (the router's name prior is switched off), so the profile of a never-seen app is built from its screens alone.

No model weights, no network; learning = the calibration constant plus the archetype vocabularies the pool already holds.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core_organs.rag import archetypes as A

TRAIN_PATH = os.path.join(os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data")), "video_graph", "archetype_train.jsonl")
MODEL_PATH = os.path.join(os.path.dirname(TRAIN_PATH), "archetype_model.json")
MIN_APPS_TO_ADOPT = 40                 # a supervised model on fewer labelled apps than this is not trusted over the hand-written vocabularies
MIN_LOGLOSS_GAIN = 0.10                # ... and must beat the router by this much in leave-one-out evaluation
ALPHAS = (0.2, 0.3, 0.5, 0.7)
SECOND_FRACTION = 0.6
TEMPERATURES = (0.03, 0.05, 0.08, 0.12, 0.18, 0.25, 0.4, 0.6, 1.0)
_CAL: Dict[str, float] = {}


def signature_of(graph: Any) -> Dict[str, Any]:
    """The word signature of an app graph: every consensus text line and every shortcut action (OCR'd at the same place by two or more authors)."""
    controls: List[str] = []
    for e in graph.edges:
        for ln in (e.get("ocr") or {}).get("lines", []):
            controls.append(ln["text"])
        for f in (e.get("ocr") or {}).get("facts", []):
            controls.append(f["action"])
    return {"app": "", "title": "", "controls": list(dict.fromkeys(controls))}


def _doc(sig: Dict[str, Any]) -> str:
    return " ".join(" ".join(A._toks(c[1] if isinstance(c, (list, tuple)) else str(c))) for c in sig.get("controls", []))


def router_shares(sig: Dict[str, Any], temperature: Optional[float] = None, router: Optional[A.ArchetypeRouter] = None) -> Dict[str, float]:
    router = router or A.ArchetypeRouter()
    scores = dict(router.classify(sig, top=len(A.ARCHETYPES)))
    t = temperature or calibrated_temperature()
    m = max(scores.values())
    ex = {k: math.exp((v - m) / t) for k, v in scores.items()}
    z = sum(ex.values()) or 1.0
    return {k: v / z for k, v in ex.items()}


def examples() -> List[Tuple[str, Dict[str, Any]]]:
    """Every labelled app the pool has: the real scanned apps plus the apps the curriculum has profiled and labelled (archetype_train.jsonl)."""
    out = list(_labelled())
    if os.path.isfile(TRAIN_PATH):
        for line in open(TRAIN_PATH, encoding="utf-8"):
            with contextlib.suppress(Exception):
                j = json.loads(line)
                out.append((j["label"], {"app": "", "title": "", "controls": j["controls"]}))
    return out


def add_example(label: str, sig: Dict[str, Any], source: str) -> bool:
    """Append one labelled app (a label is a decision of the curriculum's author, not of the model: never the model's own prediction). Same source twice replaces nothing: it is skipped."""
    if label not in A.BY_ID or len(sig.get("controls", [])) < 8:
        return False
    os.makedirs(os.path.dirname(TRAIN_PATH), exist_ok=True)
    if os.path.isfile(TRAIN_PATH) and any(json.loads(l).get("source") == source for l in open(TRAIN_PATH, encoding="utf-8") if l.strip()):
        return False
    with open(TRAIN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"label": label, "source": source, "controls": sig["controls"][:300]}) + "\n")
    return True


def _fit(docs: Sequence[str], y: Sequence[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vec = TfidfVectorizer(sublinear_tf=True)
    m = LogisticRegression(C=20.0, max_iter=2000)
    m.fit(vec.fit_transform(docs), list(y))
    return vec, m


def _blend(base: Dict[str, float], vec: Any, m: Any, doc: str, alpha: float) -> Dict[str, float]:
    pr = dict(zip(m.classes_, m.predict_proba(vec.transform([doc]))[0]))
    out = {k: (1 - alpha) * v + alpha * pr.get(k, 0.0) for k, v in base.items()}
    z = sum(out.values()) or 1.0
    return {k: v / z for k, v in out.items()}


def fit_and_gate(force: bool = False) -> Dict[str, Any]:
    """Train the supervised blend on every labelled app and decide by LEAVE-ONE-OUT whether it may be used: only with >= MIN_APPS_TO_ADOPT apps AND a log-loss gain >= MIN_LOGLOSS_GAIN over the router.
    The decision and the numbers are written to archetype_model.json; the model itself is rebuilt from archetype_train.jsonl whenever it is needed (cheap), so nothing opaque is stored."""
    data = examples()
    n = len(data)
    rep: Dict[str, Any] = {"n_apps": n, "adopted": False, "alpha": 0.0, "when": __import__("time").strftime("%Y-%m-%d %H:%M:%S")}
    docs, y = [_doc(s) for _, s in data], [l for l, _ in data]
    router, t = A.ArchetypeRouter(), calibrated_temperature()
    base = [router_shares(dict(s), t, router) for _, s in data]
    ll0 = sum(-math.log(max(b.get(l, 1e-9), 1e-9)) for b, (l, _) in zip(base, data)) / max(n, 1)
    rep["router_loo_logloss"] = round(ll0, 3)
    if n >= 12 and len(set(y)) >= 3:
        best = (ll0, 0.0)
        for alpha in ALPHAS:
            ll = 0.0
            for i in range(n):
                tr = [j for j in range(n) if j != i]
                if len({y[j] for j in tr}) < 2:
                    ll = math.inf
                    break
                vec, m = _fit([docs[j] for j in tr], [y[j] for j in tr])
                ll += -math.log(max(_blend(base[i], vec, m, docs[i], alpha).get(y[i], 1e-9), 1e-9))
            ll /= n
            rep[f"blend_{alpha}_loo_logloss"] = round(ll, 3)
            if ll < best[0]:
                best = (ll, alpha)
        rep["best_alpha"], rep["best_loo_logloss"] = best[1], round(best[0], 3)
        if (n >= MIN_APPS_TO_ADOPT and ll0 - best[0] >= MIN_LOGLOSS_GAIN and best[1] > 0) or force:
            rep["adopted"], rep["alpha"] = True, best[1]
    rep["why"] = "adopted" if rep["adopted"] else f"not adopted: needs >= {MIN_APPS_TO_ADOPT} labelled apps (has {n}) and a leave-one-out log-loss gain >= {MIN_LOGLOSS_GAIN}"
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    json.dump(rep, open(MODEL_PATH, "w", encoding="utf-8"), indent=1)
    return rep


def shares(sig: Dict[str, Any], temperature: Optional[float] = None, router: Optional[A.ArchetypeRouter] = None) -> Dict[str, float]:
    """Router shares, blended with the supervised model only when `fit_and_gate` adopted it."""
    base = router_shares(sig, temperature, router)
    if temperature is None and os.path.isfile(MODEL_PATH):
        with contextlib.suppress(Exception):
            cfg = json.load(open(MODEL_PATH, encoding="utf-8"))
            if cfg.get("adopted") and cfg.get("alpha", 0) > 0:
                data = examples()
                vec, m = _fit([_doc(s) for _, s in data], [l for l, _ in data])
                return _blend(base, vec, m, _doc(sig), float(cfg["alpha"]))
    return base


def _labelled() -> List[Tuple[str, Dict[str, Any]]]:
    sigs = A.real_signatures()
    out = []
    for k, s in sigs.items():
        s = dict(s, app="")                                                # the name is not evidence
        out.append((A.REAL_LABELS[k], s))
    return out


def calibrated_temperature(refresh: bool = False) -> float:
    """The softmax temperature that minimises the mean log-loss of the TRUE class over the real labelled scans (cached)."""
    if "t" in _CAL and not refresh:
        return _CAL["t"]
    data = _labelled()
    best, best_loss = 0.18, math.inf
    if len(data) >= 8:
        router = A.ArchetypeRouter()
        for t in TEMPERATURES:
            loss = 0.0
            for label, sig in data:
                p = shares(sig, t, router).get(label, 1e-9)
                loss += -math.log(max(p, 1e-9))
            loss /= len(data)
            if loss < best_loss:
                best, best_loss = t, loss
        _CAL["loss"] = best_loss
    _CAL["t"] = best
    return best


def profile(graph_or_sig: Any, name: str = "") -> Dict[str, Any]:
    sig = graph_or_sig if isinstance(graph_or_sig, dict) else signature_of(graph_or_sig)
    router = A.ArchetypeRouter()
    sh = shares(sig, router=router)
    ranked = sorted(sh.items(), key=lambda kv: -kv[1])
    primary, p1 = ranked[0]
    secondary = [(k, round(v, 3)) for k, v in ranked[1:6] if v >= SECOND_FRACTION * p1 and v >= 0.05]
    verdict = router.assess(sig, top=3)
    words = set(router.words(sig))
    return {"name": name, "primary": primary, "share": round(p1, 3), "secondary": secondary, "hybrid": bool(secondary), "status": verdict["status"], "margin": verdict["margin"],
            "evidence_words": sorted(words & set(A.BY_ID[primary]["signals"]))[:12], "n_controls": len(sig.get("controls", [])), "top5": [(k, round(v, 3)) for k, v in ranked[:5]],
            "temperature": calibrated_temperature()}


def save(graph: Any, prof: Dict[str, Any]) -> str:
    path = os.path.join(graph.root, "profile.json")
    os.makedirs(graph.root, exist_ok=True)
    json.dump(prof, open(path, "w", encoding="utf-8"), indent=1)
    return path


def apply_to_rag(rag: Any, app_key: str, prof: Dict[str, Any]) -> bool:
    """Record the primary archetype for the app in the lexicon, ONLY when there is enough evidence and the app has no archetype yet (existing knowledge is never overwritten)."""
    if prof["status"] not in ("candidate", "weak_candidate"):
        return False
    with contextlib.suppress(Exception):
        if not (rag.lex.app(app_key).get("archetype") or ""):
            rag.lex.set_app(app_key, archetype=prof["primary"])
            return True
    return False


def evaluate() -> Dict[str, Any]:
    """Honest numbers on the real labelled scans (the app name is withheld): top-1 and top-2 accuracy, mean share given to the true class, mean log-loss at the calibrated temperature."""
    data = _labelled()
    router = A.ArchetypeRouter()
    t = calibrated_temperature()
    top1 = top2 = 0
    sh_true, ll = [], 0.0
    for label, sig in data:
        sh = shares(sig, t, router)
        r = sorted(sh, key=lambda k: -sh[k])
        top1 += r[0] == label
        top2 += label in r[:2]
        sh_true.append(sh[label])
        ll += -math.log(max(sh[label], 1e-9))
    n = len(data)
    return {"n_apps": n, "top1": round(top1 / n, 3), "top2": round(top2 / n, 3), "mean_share_of_true_class": round(sum(sh_true) / n, 3), "log_loss": round(ll / n, 3),
            "uniform_log_loss": round(math.log(len(A.ARCHETYPES)), 3), "temperature": t}
