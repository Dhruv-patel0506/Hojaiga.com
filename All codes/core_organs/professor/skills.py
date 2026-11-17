"""
professor.skills -- the MACRO-ACTION LIBRARY: sequences that were VERIFIED on screen become reusable skills ("muscle memory").

A guide (or the planner, or probing) proposes a sequence of the application's own commands. The executor performs it and checks every step against the interface (before/after delta).
Only a sequence in which EVERY step was verified is compiled into a skill - the library never stores a guess. Next time the same goal is asked, the skill is used first: no guide lookup,
no model call, the whole chain runs at once.

  compile            ExecReport (all steps done, nothing dry-run, nothing unknown)  ->  Skill {goal aliases, steps(verb ids + labels + the route that worked), safety, counters}
  find               goal -> best active skill of THIS application (word similarity of the goal against its aliases, success rate, still valid in the current catalog)
  record             success / failure counters; three failures in a row retire the skill (status 'stale') so the next call falls back to the guide / rules instead of repeating a bad chain
  staleness          a skill whose verbs no longer exist in the application's catalog (a new version moved or renamed them) is retired, not trusted
  suggest_cross_app  the SELF-HEALING path for an application without a guide: skills learned in OTHER applications of the same kind (archetype), kept only when every step's wording
                     resolves in this application's catalog. They are HYPOTHESES (never auto-trusted); the verified run that follows compiles a native skill with the lineage recorded.
Safety is recomputed from the CURRENT catalog on every use (a step that is risky today waits for a human today), never taken from the stored record.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config as CFG
from .schema import fold

SKILL_DB = os.path.join(CFG.DATA_DIR, "skills.db")
_STOP = set("a an the of to in on for and or is it this that with as at by be are was how do i you my me can what where when which from into your please make let".split())
RETIRE_AFTER = 3


def terms(text: str) -> List[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in _STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def similarity(a: str, b: str) -> float:
    """Jaccard of the content words (light plural stemming). 1.0 = same words."""
    x, y = set(terms(a)), set(terms(b))
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


@dataclass
class SkillStep:
    kind: str = "verb"                    # verb | text | key
    label: str = ""
    verb_id: str = ""
    path: List[str] = field(default_factory=list)
    aid: str = ""
    route: str = ""                       # the route that worked: 'shortcut:Ctrl+B', 'control:Add Marker' ...
    text: str = ""                        # typed text (a slot: bound from a quoted string in the goal when there is one)
    want: str = ""                        # '' | 'on' | 'off'
    cite: str = ""                        # manual passage the step came from


@dataclass
class Skill:
    id: str
    app_key: str
    name: str
    goals: List[str]
    steps: List[SkillStep]
    archetype: str = ""
    safety: str = "safe"
    verified: int = 0
    failed: int = 0
    consec_fail: int = 0
    status: str = "active"                # active | stale
    source: str = ""                      # guide:<cite> | rules | model | archetype:<app> | skill
    lineage: str = ""                     # id of the skill this one was adapted from (cross-application)
    app_version: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    hypothesis: bool = False              # offered from another application: not yet verified HERE

    def success_rate(self) -> float:
        n = self.verified + self.failed
        return (self.verified / n) if n else 0.0

    def signature(self) -> str:
        return hashlib.sha1("|".join(f"{s.kind}:{s.verb_id or fold(s.label)}:{s.text}" for s in self.steps).encode()).hexdigest()[:12]

    def brief(self) -> str:
        return f"{self.name}: " + " > ".join(s.label or f"type {s.text!r}" for s in self.steps)


def _slug(goal: str) -> str:
    w = terms(goal)[:5]
    return "_".join(w) or "skill"


class SkillLibrary:
    def __init__(self, path: Optional[str] = None):
        self.path = path or SKILL_DB
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS skills(id TEXT PRIMARY KEY, app_key TEXT, archetype TEXT, signature TEXT, status TEXT, verified INTEGER, failed INTEGER, consec INTEGER,
                                          updated REAL, body TEXT);
        CREATE INDEX IF NOT EXISTS i_skill_app ON skills(app_key, status);
        """)
        self.db.commit()

    # ------------------------------------------------------------------------------------------------------------- store
    def _save(self, s: Skill) -> None:
        s.updated = time.time()
        body = json.dumps(asdict(s), ensure_ascii=False)
        self.db.execute("INSERT OR REPLACE INTO skills(id,app_key,archetype,signature,status,verified,failed,consec,updated,body) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (s.id, s.app_key, s.archetype, s.signature(), s.status, s.verified, s.failed, s.consec_fail, s.updated, body))
        self.db.commit()

    @staticmethod
    def _load(body: str) -> Skill:
        d = json.loads(body)
        d["steps"] = [SkillStep(**x) for x in d.get("steps", [])]
        return Skill(**d)

    def get(self, skill_id: str) -> Optional[Skill]:
        r = self.db.execute("SELECT body FROM skills WHERE id=?", (skill_id,)).fetchone()
        return self._load(r[0]) if r else None

    def all(self, app_key: str = "", include_stale: bool = False) -> List[Skill]:
        q = "SELECT body FROM skills WHERE 1=1" + (" AND app_key=?" if app_key else "") + ("" if include_stale else " AND status='active'")
        return [self._load(r[0]) for r in self.db.execute(q, (app_key,) if app_key else ())]

    def forget(self, skill_id: str) -> bool:
        cur = self.db.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        self.db.commit()
        return cur.rowcount > 0

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        sk = self.all(app_key, include_stale=True)
        return {"skills": len(sk), "active": sum(1 for s in sk if s.status == "active"), "stale": sum(1 for s in sk if s.status == "stale"), "verified_runs": sum(s.verified for s in sk),
                "apps": sorted({s.app_key for s in sk})}

    # ----------------------------------------------------------------------------------------------------------- compile
    def compile(self, report: Any, app_key: str, archetype: str = "", version: str = "", source: str = "", lineage: str = "") -> Optional[Skill]:
        """A skill from a fully verified run, or None (with nothing stored) when any step was dry, unknown, refused, unverified or failed."""
        steps = list(getattr(report, "steps", []) or [])
        results = list(getattr(report, "results", []) or [])
        if not steps or getattr(report, "dry_run", True) or len(results) != len(steps) or any(r.status != "done" for r in results):
            return None
        if any(s.kind not in ("verb", "text", "key") for s in steps):
            return None
        out: List[SkillStep] = []
        worst = "safe"
        order = ["safe", "commit", "runtime", "sensitive", "unsafe"]
        for s, r in zip(steps, results):
            out.append(SkillStep(s.kind, s.verb or "", s.verb_id, list(s.path), getattr(s, "aid", ""), r.route, s.text, getattr(s, "want", ""), getattr(s, "cite", "")))
            if s.safety in order and order.index(s.safety) > order.index(worst):
                worst = s.safety
        goal = report.goal
        sk = Skill(id="", app_key=app_key, name=_slug(goal), goals=[goal], steps=out, archetype=archetype, safety=worst, verified=1, source=source or getattr(report, "by", "rules"),
                   lineage=lineage, app_version=version)
        sig = sk.signature()
        for ex in self.all(app_key, include_stale=True):                                        # the same chain again: one skill, more aliases and evidence
            if ex.signature() == sig:
                if goal not in ex.goals:
                    ex.goals.append(goal)
                ex.verified += 1
                ex.consec_fail = 0
                ex.status = "active"
                ex.app_version = version or ex.app_version
                self._save(ex)
                return ex
        sk.id = hashlib.sha1(f"{app_key}|{sig}".encode()).hexdigest()[:10]
        self._save(sk)
        return sk

    # -------------------------------------------------------------------------------------------------------------- find
    def find(self, goal: str, app_key: str, catalog: Any = None, min_sim: float = 0.7) -> Optional[Skill]:
        """The best active skill of this application for `goal`, or None. A skill whose verbs vanished from `catalog` is retired on the spot."""
        best: Optional[Tuple[Tuple[float, ...], Skill]] = None
        for s in self.all(app_key):
            sim = max((similarity(goal, g) for g in s.goals), default=0.0)
            if sim < min_sim or s.consec_fail >= RETIRE_AFTER:
                continue
            if catalog is not None and not self.still_valid(s, catalog):
                s.status = "stale"
                self._save(s)
                continue
            key = (round(sim, 3), round(s.success_rate(), 3), float(s.verified))
            if best is None or key > best[0]:
                best = (key, s)
        return best[1] if best else None

    @staticmethod
    def still_valid(s: Skill, catalog: Any) -> bool:
        ids = {v.id for v in catalog.verbs}
        labels = {fold(v.label) for v in catalog.verbs}
        for st in s.steps:
            if st.kind == "verb" and st.verb_id not in ids and fold(st.label) not in labels:
                return False
        return True

    def record(self, skill_id: str, ok: bool) -> Optional[Skill]:
        s = self.get(skill_id)
        if s is None:
            return None
        if ok:
            s.verified += 1
            s.consec_fail = 0
        else:
            s.failed += 1
            s.consec_fail += 1
            if s.consec_fail >= RETIRE_AFTER:
                s.status = "stale"
        self._save(s)
        return s

    # ---------------------------------------------------------------------------------------------- the no-guide fallback
    def suggest_cross_app(self, goal: str, app_key: str, archetype: str, catalog: Any, min_sim: float = 0.7, min_conf: float = 0.8) -> List[Tuple[Skill, float]]:
        """Skills from OTHER applications of the same kind whose every step resolves in this catalog. Returned as hypotheses (verified here = 0), best first."""
        if not archetype or archetype == "unknown":
            return []
        from .knowledge.guide_steps import resolve_label
        out: List[Tuple[Skill, float]] = []
        for s in self.all():
            if s.app_key == app_key or s.archetype != archetype:
                continue
            if max((similarity(goal, g) for g in s.goals), default=0.0) < min_sim:
                continue
            confs = []
            ok = True
            for st in s.steps:
                if st.kind != "verb":
                    continue
                v, c = resolve_label(catalog, st.label)
                if v is None or c < min_conf:
                    ok = False
                    break
                confs.append(c)
            if ok and confs:
                h = Skill(**{**asdict(s), "steps": s.steps, "hypothesis": True})
                out.append((h, sum(confs) / len(confs)))
        out.sort(key=lambda t: (-t[1], -t[0].verified))
        return out

    # ---------------------------------------------------------------------------------------------------- prompt / status
    def prompt_lines(self, question: str, app_key: str, k: int = 3) -> str:
        """Verified workflows relevant to the question, for the teacher's prompt (what has actually worked on this application)."""
        scored = []
        for s in self.all(app_key):
            sim = max((similarity(question, g) for g in s.goals), default=0.0)
            if sim >= 0.3 and s.verified >= 1:
                scored.append((sim, s))
        scored.sort(key=lambda t: -t[0])
        return "\n".join(f"- '{s.goals[0]}': " + " then ".join(st.label or f"type {st.text!r}" for st in s.steps) + f" (worked {s.verified}x)" for _sim, s in scored[:k])

    def close(self) -> None:
        try:
            self.db.commit()
            self.db.close()
        except Exception:
            pass


_LIB: Optional[SkillLibrary] = None


def library() -> SkillLibrary:
    global _LIB
    if _LIB is None:
        _LIB = SkillLibrary()
    return _LIB
