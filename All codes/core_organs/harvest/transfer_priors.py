"""
harvest.transfer_priors -- what the pool already knows about SIMILAR apps, used to learn a new one faster.

When the 30th text editor shows Ctrl+F for "Find", it does not take three authors to believe it: 29 apps of the same kind already have that pair. This module reads the RAG's own hotkey rows,
groups the apps by archetype (the label a person gave, a real scan's known class, or the profile the pool computed), and answers:

    strength(archetype, action, chord, app)    how many OTHER apps of this archetype (and of all apps) have the same chord for an action that shares a content word
    accept(archetype, action, chord, app)      True when the pair is already common: >= SAME_ARCHETYPE apps of the class, or >= ANY_APPS apps overall. Such a fact needs only ONE author's
                                               screen / voice instead of two, and is written with the reason ('matches N similar apps').
    expectations(archetype, app, seen)         the pairs common in the class that this app has NOT shown yet: leads to look for in the next video and to test live later.

No weights and no hardcoded rule about any app: the priors ARE the pool, so they sharpen with every app the curriculum adds.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

SAME_ARCHETYPE = 2
ANY_APPS = 4
_STOP = {"the", "a", "an", "to", "of", "in", "on", "and", "or", "for", "with", "selected", "current", "active", "all", "new", "open"}


def content(action: str) -> Set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (action or "").lower()) if w not in _STOP}


def archetype_map() -> Dict[str, str]:
    """app_key -> archetype, from every source of a label: real scanned apps, the curriculum's own ladders (a person's decision), profiles the pool computed (only when it had enough evidence)."""
    from core_organs.rag import archetypes as A
    out: Dict[str, str] = dict(A.REAL_LABELS)
    with contextlib.suppress(Exception):
        from core_organs.harvest import video_curriculum as VC
        for e in VC.load_curriculum():
            if e.get("archetype"):
                out[VC.app_key(e)] = e["archetype"]
    with contextlib.suppress(Exception):
        from core_organs.harvest import consolidate as C
        for d in os.listdir(C.GRAPH_DIR):
            p = os.path.join(C.GRAPH_DIR, d, "profile.json")
            if os.path.isfile(p):
                j = json.load(open(p, encoding="utf-8"))
                if j.get("status") in ("candidate",) and j.get("primary"):
                    out.setdefault(d.replace("webapp_", "webapp:", 1) if d.startswith("webapp_") else d, j["primary"])
    return out


class Priors:
    def __init__(self, rows: Sequence[Dict[str, Any]], arch_of: Callable[[str], str]):
        self.arch_of = arch_of
        self.by_arch: Dict[str, Dict[str, List[Tuple[Set[str], str]]]] = defaultdict(lambda: defaultdict(list))     # archetype -> chord -> [(content words, app)]
        self.any: Dict[str, List[Tuple[Set[str], str]]] = defaultdict(list)
        for r in rows:
            if r.get("kind") != "hotkey" or r.get("trust") == "llm" or not r.get("payload"):
                continue
            ws, app = content(r.get("task_pattern", "")), r["app_key"]
            if not ws:
                continue
            self.any[r["payload"]].append((ws, app))
            a = arch_of(app)
            if a:
                self.by_arch[a][r["payload"]].append((ws, app))

    @classmethod
    def from_rag(cls, rag: Any) -> "Priors":
        from core_organs.rag import lt
        rows = lt.fetch(rag.fast.st, "fast_paths", "app_key != ''", 50000)
        amap = archetype_map()
        return cls(rows, lambda k: amap.get(k, ""))

    def strength(self, archetype: str, action: str, chord: str, app: str = "") -> Tuple[int, int]:
        ws = content(action)
        if not ws:
            return 0, 0
        same = {a for w, a in self.by_arch.get(archetype, {}).get(chord, []) if a != app and w & ws}
        anyapps = {a for w, a in self.any.get(chord, []) if a != app and w & ws}
        return len(same), len(anyapps)

    def accept(self, archetype: str, action: str, chord: str, app: str = "") -> bool:
        s, g = self.strength(archetype, action, chord, app)
        return s >= SAME_ARCHETYPE or g >= ANY_APPS

    def expectations(self, archetype: str, app: str, seen: Sequence[Tuple[str, str]], top: int = 12) -> List[Dict[str, Any]]:
        """Chords common in this archetype (>= SAME_ARCHETYPE other apps) that this app has not shown, with the most common action name."""
        have = {c for _, c in seen}
        out = []
        for chord, items in self.by_arch.get(archetype, {}).items():
            apps = {a for _, a in items if a != app}
            if len(apps) >= SAME_ARCHETYPE and chord not in have:
                words: Dict[str, int] = defaultdict(int)
                for ws, a in items:
                    for w in ws:
                        words[w] += 1
                name = " ".join(sorted(words, key=lambda w: -words[w])[:3])
                out.append({"chord": chord, "action_words": name, "apps": len(apps)})
        return sorted(out, key=lambda x: -x["apps"])[:top]
