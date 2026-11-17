"""
professor.knowledge.guide_card -- the application's guide as ONE structured JSON card:  { app, ui_taxonomy, shortcuts, action_sequences, by_division, sources }.

The indexed guide (manual_rag) is text for retrieval; the card is the same knowledge laid out as a dictionary the planner, the teacher or a person can read at a glance - what the interface
is called (menus, nested paths, interface terms), which shortcuts the guide names, which procedures it describes (as parsed steps), and where each piece sits among the seven Hojaiga divisions.
Built deterministically from the indexed chunks (no model needed; a language model may refine it later but nothing depends on that). When the live catalog is given, every procedure carries the
share of its steps that ground in the real interface - the honest measure of how much of the guide applies to the version actually installed.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from .. import config as CFG
from . import guide_finder as GF, guide_steps as GS, manual_rag as MR

_BOLD = re.compile(r"\*\*([^*\n]{1,60})\*\*")
_SENT = re.compile(r"(?<=[.!?])\s+|\n")
_NOT_TERMS = {"note", "tip", "warning", "important", "example", "caution"}


def card_path(app_key: str) -> str:
    return os.path.join(GF.GUIDE_DIR, re.sub(r"[^A-Za-z0-9_.-]+", "_", app_key or "app") + ".card.json")


def _nest(tree: Dict[str, Any], path: List[str]) -> None:
    node = tree
    for p in path:
        node = node.setdefault(p, {})


def build_card(app_key: str, ix: Any = None, catalog: Any = None, save: bool = True) -> Dict[str, Any]:
    from ..harvest import chords_in
    own = ix is None
    ix = ix or MR.ManualIndex()
    try:
        rows = ix.db.execute("SELECT c.cite, c.text, c.division, d.source FROM chunks c JOIN docs d ON d.id=c.doc WHERE d.app=? ORDER BY d.id, c.ord", (app_key,)).fetchall()
    finally:
        if own:
            ix.close()
    menus: Dict[str, Any] = {}
    terms: Dict[str, int] = {}
    shortcuts: Dict[str, List[Dict[str, str]]] = {}
    sequences: List[Dict[str, Any]] = []
    by_div: Dict[str, List[str]] = {}
    chord_rx = re.compile(r"(?:\*\*[A-Za-z0-9]+\*\*\s*\+\s*)+\*\*[A-Za-z0-9]+\*\*")
    for cite, raw_text, division, source in rows:
        text = chord_rx.sub(lambda m: m.group(0).replace("**", ""), raw_text)                 # '**Ctrl**+**M**' -> 'Ctrl+M' (one chord, not two interface terms)
        by_div.setdefault(division or "unclassified", [])
        if cite not in by_div[division or "unclassified"]:
            by_div[division or "unclassified"].append(cite)
        for t in _BOLD.findall(text):
            t = t.strip()
            if t and t.lower() not in _NOT_TERMS and not chords_in(t) and len(t) > 1:
                terms[t] = terms.get(t, 0) + 1
        for sent in _SENT.split(text):
            for chord in chords_in(sent):
                lead = _BOLD.search(sent)
                purpose = re.search(r"\bto\s+([a-z][^.\n]{3,50})", sent)
                if lead and not chords_in(lead.group(1)):
                    label = lead.group(1)
                elif purpose:
                    label = purpose.group(1)
                else:
                    label = re.sub(r"\s+", " ", sent.replace("**", ""))[:60]
                label = label.strip(" .:-")
                ent = {"label": label, "cite": cite}
                if ent not in shortcuts.setdefault(chord, []):
                    shortcuts[chord].append(ent)
        steps = GS.parse_steps(text, cite)
        if steps:
            goal = cite.split(" > ")[-1]
            seq: Dict[str, Any] = {"goal": goal, "cite": cite, "source": source, "steps": [{"action": s.action, "target": s.target, "path": s.path, "chord": s.chord, "text": s.text} for s in steps]}
            for s in steps:
                if len(s.path) >= 2:
                    _nest(menus, s.path)
            if catalog is not None:
                g = GS.ground(steps, catalog)
                # 'how' alone is not enough: a verb the manual's path INVENTED ('guide-path') is a claim, not a confirmation - the installed catalog does not answer it
                seq["grounded"] = round(sum(1 for x in g if x.how in GS.GROUNDED_HOW and not x.tentative) / len(g), 3)
                seq["unmatched"] = [x.step.target or x.step.raw[:40] for x in g if x.how not in GS.GROUNDED_HOW]
            sequences.append(seq)
    reg = GF.load_registry(app_key)
    card = {"app": app_key, "built": time.strftime("%Y-%m-%d %H:%M:%S"), "documents": len({r[3] for r in rows}), "chunks": len(rows),
            "sources": [{"kind": s.get("kind"), "source": s.get("source"), "app_version": s.get("app_version", ""), "match": s.get("match", "")} for s in reg.get("sources", [])],
            "ui_taxonomy": {"menus": menus, "terms": [{"term": t, "mentions": n} for t, n in sorted(terms.items(), key=lambda kv: (-kv[1], kv[0]))[:200]]},
            "shortcuts": shortcuts, "action_sequences": sequences, "by_division": by_div}
    if catalog is not None and sequences:
        card["applies_to_installed_version"] = round(sum(s.get("grounded", 0.0) for s in sequences) / len(sequences), 3)
    if save:
        os.makedirs(GF.GUIDE_DIR, exist_ok=True)
        with open(card_path(app_key), "w", encoding="utf-8") as fh:
            json.dump(card, fh, indent=1, ensure_ascii=False)
    return card


_GENERIC_HEADS = {"related topics", "see also", "next steps", "more information", "feedback", "was this information helpful", "need more help", "contents", "overview", "in this article", "summary",
                  "in this topic", "in this section", "topics by category", "browse by category", "popular topics"}
_INDEX_HEADS = {"topics by category", "browse by category", "popular topics", "in this topic", "related topics"}      # a parent heading that makes its children LINK lists, not procedures


def procedures(app_key: str, ix: Any = None, min_steps: int = 1, max_steps: int = 14) -> List[Dict[str, Any]]:
    """Every procedure the indexed guide describes, as runnable material: [{goal, cite, source, steps: [GuideStep]}] - the card's `action_sequences` but with the parsed GuideStep objects (what the
    executor grounds and performs). Duplicates (the same heading with the same steps, e.g. a page reached by two URLs) appear once."""
    own = ix is None
    ix = ix or MR.ManualIndex()
    try:
        rows = ix.db.execute("SELECT c.cite, c.text, d.source FROM chunks c JOIN docs d ON d.id=c.doc WHERE d.app=? ORDER BY d.id, c.ord", (app_key,)).fetchall()
    finally:
        if own:
            ix.close()
    chord_rx = re.compile(r"(?:\*\*[A-Za-z0-9]+\*\*\s*\+\s*)+\*\*[A-Za-z0-9]+\*\*")
    out: List[Dict[str, Any]] = []
    seen = set()
    for cite, raw_text, source in rows:
        goal = cite.split(" > ")[-1].strip()
        if goal.lower() in _GENERIC_HEADS or any(h.strip().lower() in _INDEX_HEADS for h in cite.split(" > ")[:-1]):
            continue
        text = chord_rx.sub(lambda m: m.group(0).replace("**", ""), raw_text)
        steps = GS.parse_steps(text, cite)
        if not (min_steps <= len(steps) <= max_steps):
            continue
        sig = (goal.lower(), tuple((s.action, s.target.lower(), s.chord.lower()) for s in steps))
        if sig in seen:
            continue
        seen.add(sig)
        out.append({"goal": goal, "cite": cite, "source": source, "steps": steps, "text": raw_text})
    return out
