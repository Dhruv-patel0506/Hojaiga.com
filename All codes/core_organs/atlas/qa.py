"""
atlas.qa -- ask anything about an application; the answer comes only from stored, evidenced knowledge.

Retrieval is lexical TF-IDF over every claim, command, dialog, gesture and tooltip (optionally re-ranked by local embeddings when the embedding
model is running). The answer is either the top facts verbatim (always available) or, when the local language model is reachable, a short synthesis
that must cite fact numbers; a citation that does not exist, or a number that is not in the cited facts, makes the synthesis fall back to the facts.
Every answer carries the evidence behind each fact and its trust class.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from . import common as C
from . import llm

_W = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "to", "in", "on", "of", "and", "is", "it", "do", "does", "how", "what", "which", "can", "i", "you", "this", "that", "for", "with", "are", "app", "work", "works", "use"}


def tokens(s: str) -> List[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s or "")
    out = []
    for w in _W.findall(s.lower()):
        if len(w) > 1 and w not in STOP:
            w = re.sub(r"(ing|ed|es|s|e)$", "", w) if len(w) > 4 else w
            out.append(w[:7])
    return out


def corpus(app_key: str, store: C.AtlasStore, model) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for c in store.claims(app_key, limit=4000):
        docs.append({"text": c["statement"], "kind": c["kind"], "trust": c["trust_name"], "conf": c["confidence"], "evidence": c["evidence"][:2], "id": c["id"]})
    for g in store.gestures(app_key):
        if g.get("effective"):
            docs.append({"text": f"{g['gesture']} on a {g['region_kind']} causes {g['effect_class']}" + (f" ({g['effect'].get('zoom_factor') and 'zoom x' + str(g['effect']['zoom_factor']) or ''})" if g.get("effect") else ""),
                         "kind": "gesture.measured", "trust": "measured", "conf": 0.85, "evidence": [{"type": "gesture", "ref": g["run_id"]}], "id": g["id"]})
    try:
        from core_organs import command_registry as cr
        for r in cr.build(model, app_key)[:1500]:
            docs.append({"text": f"command '{r['name']}'" + (f" at {r['menu_path']}" if r["menu_path"] else "") + (f" shortcut {r['shortcut']}" if r["shortcut"] else "") + (f": {r['help']}" if r["help"] else ""),
                         "kind": "ui.command", "trust": {4: "measured", 3: "static"}.get(r["trust"], "inferred"), "conf": 0.7, "evidence": [{"type": "probe" if r["verified"] else "uia", "ref": r["cmd_ids"][0] if r.get("cmd_ids") else r["name"]}], "id": r["key"]})
    except Exception:
        pass
    try:
        from core_organs import knowledge_store as ks
        for d in ks.dialogs(model, app_key, with_controls=True):
            ctl = ", ".join((c.get("name") if isinstance(c, dict) else str(c)) for c in (d.get("controls") or [])[:20])
            docs.append({"text": f"dialog '{d['title']}' contains: {ctl}", "kind": "ui.dialog", "trust": "measured", "conf": 0.8, "evidence": [{"type": "probe", "ref": d["title"]}], "id": "dlg:" + d["title"]})
    except Exception:
        pass
    return docs


def ask(app_key: str, question: str, store: Optional[C.AtlasStore] = None, model=None, *, k: int = 8, synthesize: bool = True) -> Dict[str, Any]:
    store = store or C.get_store()
    if model is None:
        from core_organs import organ_48_app_behavior_model as bm
        model = bm.get_model()
    docs = corpus(app_key, store, model)
    qt = tokens(question)
    if not docs or not qt:
        return {"question": question, "answer": "Nothing is known about this application yet (run a scan first).", "facts": [], "grounded": False}
    df: Dict[str, int] = {}
    dtoks = []
    for d in docs:
        t = set(tokens(d["text"]))
        dtoks.append(t)
        for w in t:
            df[w] = df.get(w, 0) + 1
    N = len(docs)
    scored = []
    for d, t in zip(docs, dtoks):
        s = sum(math.log(1 + N / df[w]) for w in qt if w in t)
        if s <= 0:
            continue
        s *= {"measured": 1.3, "static": 1.15, "published": 1.0, "inferred": 0.85}.get(d["trust"], 1.0)
        s *= 0.8 + 0.4 * float(d.get("conf", 0.5))
        s *= 1.0 + 0.5 * (sum(1 for w in qt if w in t) / len(qt))
        scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    top = [d for _, d in scored[:k * 2]]
    emb = llm.embed([question] + [d["text"] for d in top]) if top and synthesize else None
    if emb and len(emb) == len(top) + 1:
        def cos(a, b):
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return sum(x * y for x, y in zip(a, b)) / (na * nb)
        qv = emb[0]
        top = [d for _, d in sorted(zip([-(cos(qv, v)) for v in emb[1:]], top), key=lambda x: x[0])]
    facts = top[:k]
    out: Dict[str, Any] = {"question": question, "facts": [{"n": i + 1, "text": f["text"], "kind": f["kind"], "trust": f["trust"], "evidence": f["evidence"]} for i, f in enumerate(facts)],
                           "grounded": bool(facts), "answer": "", "method": "facts"}
    if not facts:
        out["answer"] = "The stored knowledge does not mention that."
        return out
    if synthesize and llm.available():
        listing = "\n".join(f"[{f['n']}] {f['text']}" for f in out["facts"])
        r = llm.chat("Answer the question using ONLY the numbered facts. Be brief (2-5 sentences). Cite fact numbers like [2]. If the facts do not answer it, say so. Reply JSON: {\"answer\": \"...\"}",
                     f"FACTS:\n{listing}\n\nQUESTION: {question}", timeout=60, max_tokens=350)
        ans = (r.get("json") or {}).get("answer") if isinstance(r.get("json"), dict) else None
        if isinstance(ans, str) and ans.strip():
            cites = [int(x) for x in re.findall(r"\[(\d+)\]", ans)]
            nums_ok = all(n in range(1, len(facts) + 1) for n in cites)
            factblob = " ".join(f["text"] for f in out["facts"]).lower()
            nums = re.findall(r"\b\d+(?:\.\d+)?\b", re.sub(r"\[\d+\]", "", ans))
            num_ok = all(n in factblob for n in nums)
            if cites and nums_ok and num_ok:
                out.update(answer=ans.strip(), method="synthesis", model=r.get("model"))
                return out
            out["synthesis_rejected"] = "citation or number not supported by the cited facts"
    out["answer"] = " ".join(f"[{f['n']}] {f['text']}." for f in out["facts"][:4])
    return out
