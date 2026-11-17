"""
rag.lexicon -- the cross-modal spine (DESIGN.md section 3.1): every SURFACE FORM an app's commands are known by -> the one command_id they name.

    a UIA name, an icon label, a menu path, a tooltip, a keymap action, a documentation term, a transcript phrase ... all resolve here, so retrieval joins modalities by an exact lookup
    rather than by hoping two embedding spaces align.

    command_id = "<app_key>:<canon(label)>"          canon() is command_registry.canon (imported when available, mirrored otherwise: a test pins the two together)

resolve(app_key, text, live=None) -> [Match]:   exact surface -> menu-path leaf -> IDF-weighted token containment -> fuzzy (difflib >= 0.88). Ties go to trust, then n_seen, then
membership in `live` (the commands present in the current UI state). Nothing unresolved is invented: an unknown phrase simply has no match, and the caller reports it as a gap.
"""
from __future__ import annotations

import difflib
from collections import Counter
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import config as C

_CHORD = re.compile(r"\(?\b((?:ctrl|control|alt|shift|win|cmd)(?:\s*\+\s*(?:ctrl|alt|shift|[a-z0-9]|f\d{1,2}|enter|space|tab|esc|del|home|end|up|down|left|right|plus|minus|=|-|,|\.))+)\b\)?", re.I)
_TAIL = re.compile(r"(\.\.\.|…)\s*$")
_STOP = {"the", "a", "an", "to", "in", "on", "of", "and", "my", "it", "this", "that", "for", "with", "please", "now", "then", "how", "do", "i", "can", "you", "click", "press",
         "select", "choose", "open", "use", "button", "tool", "menu", "tab", "then", "next", "just", "from", "into", "is", "are", "want", "need", "me", "show", "go"}
_W = re.compile(r"[a-z0-9]+")
_KIND_PRIORITY = {"label": 9, "menu_path": 8, "keymap_action": 7, "tooltip": 6, "icon_label": 6, "doc_term": 4, "transcript_term": 3, "synonym": 2}


def _local_canon(label: str) -> str:
    s = (label or "").replace("&", "")
    s = _CHORD.sub("", s)
    s = _TAIL.sub("", s.strip())
    s = re.sub(r"\(\s*\)", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


_canon_impl = None


def canon(label: str) -> str:
    """command_registry.canon when importable (the single definition of a canonical label), the identical local mirror otherwise."""
    global _canon_impl
    if _canon_impl is None:
        try:
            from core_organs.command_registry import canon as _c
            _canon_impl = _c
        except Exception:
            _canon_impl = _local_canon
    return _canon_impl(label)


def surface(text: str) -> str:
    return re.sub(r"\s+", " ", canon(text)).strip()


def toks(text: str) -> List[str]:
    return [w for w in _W.findall(surface(text)) if w not in _STOP and len(w) > 1]


def command_id(app_key: str, label: str) -> str:
    return f"{app_key}:{canon(label)}"


@dataclass
class Match:
    command_id: str
    score: float
    kind: str
    surface: str = ""
    trust: str = "seed"


class Lexicon:
    def __init__(self, st):
        self.st = st
        self.db = st.sql("lexicon")
        self._idf: Dict[str, Tuple[int, Dict[str, float], float]] = {}
        self._aix: Dict[str, Tuple[int, Any]] = {}                      # app -> (generation, alias index): built once, not per resolve

    # ---- writes -------------------------------------------------------------------------------------------------------------------------------------
    def add_command(self, app_key: str, label: str, archetype: str = "", source: str = "registry", trust: str = "catalog") -> str:
        cid = command_id(app_key, label)
        self.db.execute("INSERT OR IGNORE INTO commands(command_id,app_key,label,archetype) VALUES(?,?,?,?)", (cid, app_key, label, archetype))
        self.add_alias(app_key, label, cid, "label", source, trust)
        return cid

    def add_alias(self, app_key: str, text: str, cid: str, kind: str, source: str = "", trust: str = "seed", n: int = 1) -> bool:
        s = surface(text)
        if not s or len(s) > 120:
            return False
        with self.db.lock:
            row = self.db.one("SELECT kind, trust, n_seen FROM aliases WHERE app_key=? AND surface_norm=? AND command_id=?", (app_key, s, cid))
            if row:
                keep_kind = kind if _KIND_PRIORITY.get(kind, 0) > _KIND_PRIORITY.get(row["kind"], 0) else row["kind"]
                keep_trust = trust if C.TRUST_W.get(trust, 0) > C.TRUST_W.get(row["trust"], 0) else row["trust"]
                self.db.execute("UPDATE aliases SET kind=?, trust=?, n_seen=n_seen+? WHERE app_key=? AND surface_norm=? AND command_id=?", (keep_kind, keep_trust, n, app_key, s, cid))
            else:
                self.db.execute("INSERT INTO aliases(app_key,surface_norm,command_id,kind,source,trust,n_seen) VALUES(?,?,?,?,?,?,?)", (app_key, s, cid, kind, source, trust, n))
            self.db.commit()
        self._idf.pop(app_key, None)
        self.st.bump(f"lexicon:{app_key}")
        return True

    def ingest_registry(self, app_key: str, registry: Sequence[Dict[str, Any]], archetype: str = "") -> int:
        """command_registry.build() rows -> commands + aliases (names, menu paths, help-text leads, automation ids). Returns the number of commands."""
        trust_of = {4: "learned", 3: "catalog", 2: "seed", 1: "llm"}
        n = 0
        for g in registry:
            names = list(g.get("names") or [g.get("name", "")])
            name = (g.get("name") or (names[0] if names else "")).strip()
            if not name or not canon(name):
                continue
            tr = trust_of.get(int(g.get("trust", 2) or 2), "seed")
            cid = self.add_command(app_key, name, archetype, "command_registry", tr)
            for nm in names:
                self.add_alias(app_key, nm, cid, "label", "command_registry", tr)
            for mp in g.get("menu_paths") or ([g["menu_path"]] if g.get("menu_path") else []):
                leaf = mp.split(">")[-1]
                self.add_alias(app_key, mp, cid, "menu_path", "command_registry", tr)
                self.add_alias(app_key, leaf, cid, "menu_path", "command_registry", tr)
            h = (g.get("help") or "").strip()
            if h:
                self.add_alias(app_key, h.split(".")[0][:80], cid, "tooltip", "command_registry", tr)
            for aid in g.get("automation_ids") or []:
                self.add_alias(app_key, str(aid), cid, "label", "command_registry", tr)
            n += 1
        if n:
            self.db.execute("INSERT OR IGNORE INTO apps(app_key) VALUES(?)", (app_key,))
            self.db.commit()
        return n

    def set_app(self, app_key: str, tier: Optional[int] = None, archetype: str = "", version: str = "", toolkit: str = "") -> None:
        with self.db.lock:
            self.db.execute("INSERT OR IGNORE INTO apps(app_key) VALUES(?)", (app_key,))
            if tier is not None:
                self.db.execute("UPDATE apps SET tier=? WHERE app_key=?", (int(tier), app_key))
            for col, val in (("archetype", archetype), ("version", version), ("toolkit", toolkit)):
                if val:
                    self.db.execute(f"UPDATE apps SET {col}=? WHERE app_key=?", (val, app_key))
            self.db.commit()

    def app(self, app_key: str) -> Dict[str, Any]:
        return self.db.one("SELECT * FROM apps WHERE app_key=?", (app_key,)) or {"app_key": app_key, "tier": -1, "archetype": "", "version": "", "toolkit": ""}

    def apps_of(self, archetype: str) -> List[str]:
        return [r["app_key"] for r in self.db.rows("SELECT app_key FROM apps WHERE archetype=?", (archetype,))] if archetype else []

    def forget_app(self, app_key: str) -> int:
        with self.db.lock:
            n = self.db.execute("DELETE FROM aliases WHERE app_key=?", (app_key,)).rowcount
            self.db.execute("DELETE FROM commands WHERE app_key=?", (app_key,))
            self.db.commit()
        self._idf.pop(app_key, None)
        self.st.bump(f"lexicon:{app_key}")
        return int(n)

    # ---- reads --------------------------------------------------------------------------------------------------------------------------------------
    def n_commands(self, app_key: str) -> int:
        r = self.db.one("SELECT COUNT(*) AS n FROM commands WHERE app_key=?", (app_key,))
        return int(r["n"]) if r else 0

    def label_of(self, cid: str) -> str:
        r = self.db.one("SELECT label FROM commands WHERE command_id=?", (cid,))
        return r["label"] if r else cid.split(":", 1)[-1]

    def _alias_index(self, app_key: str) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Set[str]], Dict[str, Set[str]]]:
        """(rows by surface, token set of each surface, token -> surfaces holding it), rebuilt only when the app's aliases change. resolve() re-tokenised every alias on
        every call: 642,064 tokenisations for 30 manual pages (Oct-28, after 18,609 Office object-model members were filed); now only aliases sharing a word are checked."""
        g = self.st.gen(f"lexicon:{app_key}")
        hit = self._aix.get(app_key)
        if hit and hit[0] == g:
            return hit[1]
        by_surface: Dict[str, List[Dict[str, Any]]] = {}
        for r in self.db.rows("SELECT surface_norm, command_id, kind, trust, n_seen FROM aliases WHERE app_key=?", (app_key,)):
            by_surface.setdefault(r["surface_norm"], []).append(r)
        tok_of = {sf: set(toks(sf)) for sf in by_surface}
        holders: Dict[str, Set[str]] = {}
        for sf, ts in tok_of.items():
            for t in ts:
                holders.setdefault(t, set()).add(sf)
        self._aix[app_key] = (g, (by_surface, tok_of, holders))
        return by_surface, tok_of, holders

    def _idf_table(self, app_key: str) -> Tuple[Dict[str, float], float]:
        g = self.st.gen(f"lexicon:{app_key}")
        hit = self._idf.get(app_key)
        if hit and hit[0] == g:
            return hit[1], hit[2]
        df: Dict[str, int] = {}
        rows = self.db.rows("SELECT DISTINCT surface_norm FROM aliases WHERE app_key=?", (app_key,))
        for r in rows:
            for t in set(toks(r["surface_norm"])):
                df[t] = df.get(t, 0) + 1
        n = max(1, len(rows))
        idf = {t: math.log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}
        default = math.log(n + 1) + 1.0
        self._idf[app_key] = (g, idf, default)
        return idf, default

    def resolve(self, app_key: str, text: str, live: Optional[Iterable[str]] = None, limit: int = 8) -> List[Match]:
        s = surface(text)
        if not s:
            return []
        live_set: Set[str] = set(live or ())
        found: Dict[str, Match] = {}

        def put(cid: str, score: float, kind: str, surf: str, trust: str) -> None:
            if cid not in found or score > found[cid].score:
                found[cid] = Match(cid, round(score, 4), kind, surf, trust)

        by_surface, tok_of, holders = self._alias_index(app_key)
        # 1. exact surface, 2. menu-path leaf
        for key, score in ((s, 1.0), (surface(text.split(">")[-1]), 0.95)):
            for r in by_surface.get(key, ()):
                put(r["command_id"], score, r["kind"], r["surface_norm"], r["trust"])
        # 3. IDF-weighted containment: an alias whose every content token appears in the text
        qt = set(toks(s))
        if qt:
            idf, default = self._idf_table(app_key)
            qw = sum(idf.get(t, default) for t in qt) or 1.0
            for surf in set().union(*(holders.get(t, set()) for t in qt)):                 # only aliases sharing a word with the text can be contained in it
                at, lst = tok_of[surf], by_surface[surf]
                if not at or not at <= qt:
                    continue
                cov = sum(idf.get(t, default) for t in at) / qw
                for r in lst:
                    put(r["command_id"], 0.55 + 0.4 * min(1.0, cov), r["kind"], surf, r["trust"])
        # 3b. a rare content word that occurs in exactly ONE command's names names that command ('extrude' -> 'extrude region'); ambiguous or common words never do
        if qt:
            idf, default = self._idf_table(app_key)
            owners: Dict[str, Set[str]] = {}
            for t in qt:
                for surf in holders.get(t, ()):
                    owners.setdefault(t, set()).update(r["command_id"] for r in by_surface[surf])
            for t, cids in owners.items():
                if len(cids) == 1 and idf.get(t, default) >= C.UNIQUE_TOKEN_MIN_IDF:
                    cid = next(iter(cids))
                    if cid not in found:
                        row = next((r for lst in by_surface.values() for r in lst if r["command_id"] == cid), None)
                        put(cid, C.UNIQUE_TOKEN_SCORE, "synonym", t, row["trust"] if row else "seed")
        # 4. fuzzy, only when nothing else matched (a spelling variant)
        if not found and len(s) >= 4:
            sc = Counter(s)
            for surf, lst in by_surface.items():
                if abs(len(surf) - len(s)) > 4:
                    continue
                n = len(s) + len(surf)                                          # difflib's own upper bounds first (same verdicts): the full ratio over every alias
                if 2.0 * min(len(s), len(surf)) / n < C.FUZZY_RESOLVE or 2.0 * sum((sc & Counter(surf)).values()) / n < C.FUZZY_RESOLVE:
                    continue                                                    # was half of a manual import's time (Oct-28: 115k comparisons for 120 pages)
                ratio = difflib.SequenceMatcher(None, s, surf).ratio()
                if ratio >= C.FUZZY_RESOLVE:
                    for r in lst:
                        put(r["command_id"], 0.85 * ratio, r["kind"], surf, r["trust"])

        def key(m: Match):
            n = max((r["n_seen"] for r in by_surface.get(m.surface, ()) if r["command_id"] == m.command_id), default=1)
            return (-round(m.score, 2), -C.TRUST_W.get(m.trust, 0.3), 0 if m.command_id in live_set else 1, -n, m.command_id)
        return sorted(found.values(), key=key)[:limit]

    def best(self, app_key: str, text: str, live: Optional[Iterable[str]] = None, min_score: float = 0.6) -> Optional[Match]:
        r = self.resolve(app_key, text, live, 1)
        return r[0] if r and r[0].score >= min_score else None

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        w, a = (" WHERE app_key=?", (app_key,)) if app_key else ("", ())
        return {"commands": self.db.one(f"SELECT COUNT(*) AS n FROM commands{w}", a)["n"], "aliases": self.db.one(f"SELECT COUNT(*) AS n FROM aliases{w}", a)["n"]}
