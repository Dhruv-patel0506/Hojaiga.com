"""
rag.graph -- Sub-RAG 2: the UI topology / state-action graph (DESIGN.md section 5.2).

SQLite (graph.db) is the source of truth; a networkx DiGraph per app is a derived view, rebuilt when the app's generation counter moves. Nothing is pickled.

    localize(app, snapshot)        -> (state_id, similarity, created)   structural recognition, assigned UUIDs, exact-signature fast path, IDF-Jaccard fallback, variants, aliases
    observe(outcome)               append an observation, update the edge it describes, learn new states/edges, bump the generation
    add_edge(...)                  static knowledge (UIA maps, atlas, history) enters as an edge with no observations
    path_to(app, from, command)    cheapest edge sequence from a state to one that can perform `command` (Dijkstra; k distinct alternatives)
    rebuild_edges(app)             recompute every edge counter from the observation log (counters are an aggregate, never the truth)
    RunGuard                       the per-run loop guards: visited (state, command), replans, wall clock, step ceiling

Edge reliability: Beta(n_ok + a, n_fail + n_noeffect + b) with (a, b) by trust, eroded as p ** (1 + age_days / STALE_DAYS). Edge cost: route_cost/1000 * tier_mult + LAMBDA * -ln(p).
"""
from __future__ import annotations

import json
import math
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

import networkx as nx

from . import config as C
from . import lt
from . import statekey as SK
from .lexicon import canon
from .types import Outcome, PlanStep


@dataclass
class Localized:
    state_id: str
    similarity: float
    created: bool
    variant: bool = False

    def __iter__(self):
        return iter((self.state_id, self.similarity, self.created))


@dataclass
class GraphPath:
    steps: List[PlanStep]
    cost_s: float
    p_success: float
    goal_state: str = ""


def reliability(e: Dict[str, Any], now: Optional[float] = None) -> float:
    a, b = C.PRIORS.get(e.get("trust", "seed"), (1, 1))
    n = int(e.get("n_ok", 0)) + int(e.get("n_fail", 0)) + int(e.get("n_noeffect", 0))
    p = (int(e.get("n_ok", 0)) + a) / (n + a + b)
    ts = float(e.get("last_ok_ts") or e.get("last_seen_ts") or 0)
    age = max(0.0, ((now or time.time()) - ts) / 86400.0) if ts else 0.0
    return max(1e-4, min(1.0, p ** (1.0 + age / C.STALE_DAYS)))


class RunGuard:
    """Loop guards for one execution run (DESIGN 5.2): a repeated (state, command) means the step is blocked, replans are capped, the clock and step count are bounded."""

    def __init__(self, plan_len: int, budget_s: float = 120.0):
        self.visited: Set[Tuple[str, str]] = set()
        self.replans = 0
        self.max_steps = plan_len + 4
        self.steps = 0
        self.deadline = time.monotonic() + budget_s

    def allow(self, state_id: str, command_id: str) -> bool:
        if self.steps >= self.max_steps or time.monotonic() > self.deadline or (state_id, command_id) in self.visited:
            return False
        self.visited.add((state_id, command_id))
        self.steps += 1
        return True

    def can_replan(self) -> bool:
        if self.replans >= C.MAX_REPLANS or time.monotonic() > self.deadline:
            return False
        self.replans += 1
        return True


class Graph:
    def __init__(self, st):
        self.st = st
        self.db = st.sql("graph")
        self._views: "OrderedDict[str, Tuple[int, Dict[str, Any]]]" = OrderedDict()
        self._idf: Dict[str, Tuple[int, Dict[str, float], float]] = {}

    # ---- identity -----------------------------------------------------------------------------------------------------------------------------------
    def canonical(self, state_id: Optional[str]) -> Optional[str]:
        seen = 0
        while state_id and seen < 16:
            r = self.db.one("SELECT canonical_id FROM aliases WHERE state_id=?", (state_id,))
            if not r:
                return state_id
            state_id, seen = r["canonical_id"], seen + 1
        return state_id

    def node(self, state_id: str) -> Optional[Dict[str, Any]]:
        r = self.db.one("SELECT * FROM nodes WHERE state_id=?", (self.canonical(state_id),))
        if r:
            r["landmarks"] = json.loads(r["landmarks_json"])
            r["modal_stack"] = json.loads(r["modal_stack_json"])
        return r

    @staticmethod
    def _core(landmarks: Dict[str, Dict[str, float]], visits: int) -> Dict[str, float]:
        """The stable landmarks of a node: those present in at least half of its visits (all of them while it has been seen fewer than 3 times)."""
        if visits < 3:
            return {k: v["w"] for k, v in landmarks.items()}
        return {k: v["w"] for k, v in landmarks.items() if v["n"] / visits >= 0.5}

    def _idf_for(self, app_key: str) -> Tuple[Dict[str, float], float]:
        g = self.st.gen(f"graph:{app_key}")
        hit = self._idf.get(app_key)
        if hit and hit[0] == g:
            return hit[1], hit[2]
        n = self.db.one("SELECT COUNT(*) AS n FROM nodes WHERE app_key=?", (app_key,))["n"] or 1
        idf = {r["landmark"]: math.log((n + 1) / (r["df"] + 1)) + 1.0 for r in self.db.rows("SELECT landmark, df FROM landmark_df WHERE app_key=?", (app_key,))}
        default = math.log(n + 1) + 1.0
        self._idf[app_key] = (g, idf, default)
        return idf, default

    # ---- localize -----------------------------------------------------------------------------------------------------------------------------------
    def localize(self, app_key: str, snapshot: Any, app_version: str = "", tier: Optional[int] = None, screenshot_ref: str = "", create: bool = True,
                 app_pids: Optional[Iterable[int]] = None) -> Localized:
        f = SK.features(snapshot, app_pids)
        now = time.time()
        hit = self.db.one("SELECT state_id FROM sigs WHERE app_key=? AND sig=?", (app_key, f.sig))
        if hit:
            sid = self.canonical(hit["state_id"])
            self._visit(sid, f, merge_landmarks=True, now=now)
            return Localized(sid, 1.0, False)
        stack_json = json.dumps(f.modal_stack)
        cands = self.db.rows("SELECT state_id, landmarks_json, visits FROM nodes WHERE app_key=? AND window_kind=? AND modal_stack_json=?", (app_key, f.window_kind, stack_json))
        idf, default = self._idf_for(app_key)
        best, best_sim = None, 0.0
        for c in cands:
            sim = SK.similarity(f.landmarks, self._core(json.loads(c["landmarks_json"]), c["visits"]), idf, default)
            if sim > best_sim or (sim == best_sim and best is not None and c["visits"] > best["visits"]):
                best, best_sim = c, sim
        if best is not None and best_sim >= C.SAME_STATE:
            sid = best["state_id"]
            self._add_sig(app_key, f.sig, sid)
            self._visit(sid, f, merge_landmarks=True, now=now)
            self._maybe_merge(app_key, sid)
            return Localized(sid, best_sim, False)
        if best is not None and best_sim >= C.VARIANT_STATE:
            sid = best["state_id"]
            self._add_sig(app_key, f.sig, sid)
            self._visit(sid, f, merge_landmarks=False, now=now, variant_sig=f.sig)
            return Localized(sid, best_sim, False, True)
        if not create:
            return Localized("", best_sim, False)
        sid = uuid.uuid4().hex
        lm = {k: {"n": 1, "w": w} for k, w in f.landmarks.items()}
        with self.db.lock:
            self.db.execute("INSERT INTO nodes(state_id,app_key,app_version,window_kind,modal_stack_json,landmarks_json,exact_sig,tier,visits,first_seen,last_seen,screenshot_ref,description)"
                            " VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?)", (sid, app_key, app_version, f.window_kind, stack_json, json.dumps(lm, sort_keys=True), f.sig,
                                                                   -1 if tier is None else int(tier), now, now, screenshot_ref, SK.describe(f)))
            self._add_sig(app_key, f.sig, sid)
            self.db.executemany("INSERT INTO landmark_df(app_key,landmark,df) VALUES(?,?,1) ON CONFLICT(app_key,landmark) DO UPDATE SET df=df+1", [(app_key, k) for k in lm])
            self.db.commit()
        self.st.bump(f"graph:{app_key}")
        self._index_state(app_key, sid, SK.describe(f), screenshot_ref)
        return Localized(sid, best_sim, True)

    def _add_sig(self, app_key: str, sig: str, sid: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO sigs(app_key,sig,state_id) VALUES(?,?,?)", (app_key, sig, sid))
        self.db.commit()

    def _visit(self, sid: str, f: SK.Features, merge_landmarks: bool, now: float, variant_sig: str = "") -> None:
        with self.db.lock:
            r = self.db.one("SELECT landmarks_json, visits, variants_json FROM nodes WHERE state_id=?", (sid,))
            if not r:
                return
            lm = json.loads(r["landmarks_json"])
            new = []
            if merge_landmarks:
                for k, w in f.landmarks.items():
                    if k in lm:
                        lm[k]["n"] += 1
                    else:
                        lm[k] = {"n": 1, "w": w}
                        new.append(k)
            variants = json.loads(r["variants_json"] or "[]")
            if variant_sig and variant_sig not in variants:
                variants = (variants + [variant_sig])[-20:]
            app = self.db.one("SELECT app_key FROM nodes WHERE state_id=?", (sid,))["app_key"]
            self.db.execute("UPDATE nodes SET landmarks_json=?, visits=visits+1, last_seen=?, variants_json=? WHERE state_id=?", (json.dumps(lm, sort_keys=True), now, json.dumps(variants), sid))
            if new:
                self.db.executemany("INSERT INTO landmark_df(app_key,landmark,df) VALUES(?,?,1) ON CONFLICT(app_key,landmark) DO UPDATE SET df=df+1", [(app, k) for k in new])
            self.db.commit()
        if new:
            self.st.bump(f"graph:{app}")

    def _maybe_merge(self, app_key: str, sid: str) -> None:
        me = self.db.one("SELECT window_kind, modal_stack_json, landmarks_json, visits, first_seen FROM nodes WHERE state_id=?", (sid,))
        if not me:
            return
        idf, default = self._idf_for(app_key)
        mine = self._core(json.loads(me["landmarks_json"]), me["visits"])
        for o in self.db.rows("SELECT state_id, landmarks_json, visits, first_seen FROM nodes WHERE app_key=? AND window_kind=? AND modal_stack_json=? AND state_id<>?",
                              (app_key, me["window_kind"], me["modal_stack_json"], sid)):
            if SK.similarity(mine, self._core(json.loads(o["landmarks_json"]), o["visits"]), idf, default) >= C.MERGE_STATE:
                win, lose = sorted([(sid, me), (o["state_id"], o)], key=lambda x: (-x[1]["visits"], x[1]["first_seen"]))
                self._alias(app_key, lose[0], win[0])
                return

    def _alias(self, app_key: str, loser: str, winner: str) -> None:
        with self.db.lock:
            a = self.db.one("SELECT landmarks_json, visits FROM nodes WHERE state_id=?", (loser,))
            b = self.db.one("SELECT landmarks_json, visits FROM nodes WHERE state_id=?", (winner,))
            if not a or not b:
                return
            lm = json.loads(b["landmarks_json"])
            for k, v in json.loads(a["landmarks_json"]).items():
                lm[k] = {"n": lm.get(k, {"n": 0})["n"] + v["n"], "w": v["w"]}
            self.db.execute("UPDATE nodes SET landmarks_json=?, visits=visits+? WHERE state_id=?", (json.dumps(lm, sort_keys=True), a["visits"], winner))
            self.db.execute("INSERT OR REPLACE INTO aliases(state_id,canonical_id) VALUES(?,?)", (loser, winner))
            self.db.execute("UPDATE sigs SET state_id=? WHERE state_id=?", (winner, loser))
            self.db.execute("DELETE FROM nodes WHERE state_id=?", (loser,))
            self.db.commit()
        self.st.bump(f"graph:{app_key}")

    def _index_state(self, app_key: str, sid: str, desc: str, shot: str) -> None:
        try:
            lt.upsert(self.st, "ui_states", [{"state_id": sid, "app_key": app_key, "description": desc, "screenshot_ref": shot}], "description")
        except Exception:
            pass

    def find_states(self, app_key: str, text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Natural-language state search ('where is the export dialog?') over the state descriptions."""
        out = []
        for r in lt.search(self.st, "ui_states", text, app_key, limit=limit):
            sid = self.canonical(r["state_id"])
            if sid and all(sid != o["state_id"] for o in out):
                out.append({"state_id": sid, "description": r["description"], "score": r["_rrf"]})
        return out

    # ---- edges --------------------------------------------------------------------------------------------------------------------------------------
    def add_edge(self, app_key: str, src: str, dst: str, command_id: str, route: str, action_type: str = "", args: Optional[Dict[str, Any]] = None, source: str = "static",
                 trust: str = "seed", safety: str = "allow") -> int:
        src, dst = self.canonical(src), self.canonical(dst)
        now = time.time()
        with self.db.lock:
            self.db.execute("INSERT INTO edges(app_key,src,dst,command_id,action_type,route,args_json,source,trust,safety,last_seen_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)"
                            " ON CONFLICT(app_key,src,command_id,route,dst) DO UPDATE SET last_seen_ts=excluded.last_seen_ts, safety=excluded.safety,"
                            " trust=CASE WHEN ?>0 THEN excluded.trust ELSE trust END",
                            (app_key, src, dst, command_id, action_type or route, route, json.dumps(args or {}, sort_keys=True), source, trust, safety, now,
                             1 if C.TRUST_W.get(trust, 0) > 0 else 0))
            eid = self.db.one("SELECT edge_id FROM edges WHERE app_key=? AND src=? AND command_id=? AND route=? AND dst=?", (app_key, src, command_id, route, dst))["edge_id"]
            self.db.commit()
        self.st.bump(f"graph:{app_key}")
        return int(eid)

    def observe(self, o: Outcome, source: str = "executor") -> Dict[str, Any]:
        """Record what happened after one step. Returns {src, dst, matched, replan} so the caller knows whether to continue or replan."""
        step = o.step
        app = o.app_key
        src = self.canonical(o.src_state) if o.src_state else None
        dst = self.canonical(o.observed_dst) if o.observed_dst else None
        if dst is None and o.observed_snapshot is not None:
            dst = self.localize(app, o.observed_snapshot).state_id or None
        expected = self.canonical(o.expected_dst or step.expect_state) if (o.expected_dst or step.expect_state) else None
        effect = o.effect or ("" if o.ok else "no_effect")
        if src is None:
            return {"src": None, "dst": dst, "matched": None, "replan": not o.ok}
        edge_dst = dst or expected or src
        now = time.time()
        with self.db.lock:
            self.db.execute("INSERT INTO observations(ts,run_id,app_key,src,command_id,route,args_json,expected_dst,observed_dst,ok,effect,latency_ms,verify_note,source)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (now, o.run_id, app, src, step.command_id, step.route, json.dumps(step.args, sort_keys=True), expected, dst,
                                                                     1 if o.ok else 0, effect, o.latency_ms, step.expect_note, source))
            self.db.execute("INSERT OR IGNORE INTO edges(app_key,src,dst,command_id,action_type,route,args_json,source,trust,safety,last_seen_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (app, src, edge_dst, step.command_id, step.route, step.route, json.dumps(step.args, sort_keys=True), "observed", "learned", step.safety, now))
            ok_n, fail_n, noeff_n = (1, 0, 0) if o.ok else ((0, 0, 1) if effect == "no_effect" else (0, 1, 0))
            lat = o.latency_ms or 0.0
            self.db.execute("UPDATE edges SET n_ok=n_ok+?, n_fail=n_fail+?, n_noeffect=n_noeffect+?, last_seen_ts=?, last_ok_ts=CASE WHEN ?=1 THEN ? ELSE last_ok_ts END,"
                            " ewma_latency_ms=CASE WHEN ewma_latency_ms=0 THEN ? ELSE 0.7*ewma_latency_ms+0.3*? END"
                            " WHERE app_key=? AND src=? AND command_id=? AND route=? AND dst=?",
                            (ok_n, fail_n, noeff_n, now, ok_n, now, lat, lat, app, src, step.command_id, step.route, edge_dst))
            self.db.commit()
        self.st.bump(f"graph:{app}")
        matched = (dst == expected) if (expected and dst) else None
        return {"src": src, "dst": dst, "matched": matched, "replan": bool(not o.ok or matched is False)}

    def rebuild_edges(self, app_key: str) -> int:
        """Recompute every edge counter from the observation log (the log is the truth). Edges without observations keep zero counters."""
        with self.db.lock:
            self.db.execute("UPDATE edges SET n_ok=0, n_fail=0, n_noeffect=0, last_ok_ts=0 WHERE app_key=?", (app_key,))
            rows = self.db.rows("SELECT src, command_id, route, COALESCE(observed_dst, expected_dst, src) AS dst, ok, effect, MAX(ts) AS ts, COUNT(*) AS n FROM observations"
                                " WHERE app_key=? GROUP BY src, command_id, route, COALESCE(observed_dst, expected_dst, src), ok, effect", (app_key,))
            for r in rows:
                ok = int(r["ok"])
                col = "n_ok" if ok else ("n_noeffect" if r["effect"] == "no_effect" else "n_fail")
                self.db.execute(f"UPDATE edges SET {col}={col}+?, last_ok_ts=MAX(last_ok_ts, ?) WHERE app_key=? AND src=? AND command_id=? AND route=? AND dst=?",
                                (r["n"], r["ts"] if ok else 0, app_key, r["src"], r["command_id"], r["route"], r["dst"]))
            self.db.commit()
        self.st.bump(f"graph:{app_key}")
        return len(rows)

    # ---- the networkx view --------------------------------------------------------------------------------------------------------------------------
    def view(self, app_key: str) -> Dict[str, Any]:
        g = self.st.gen(f"graph:{app_key}")
        hit = self._views.get(app_key)
        if hit and hit[0] == g:
            self._views.move_to_end(app_key)
            return hit[1]
        G = nx.DiGraph()
        by_cmd: Dict[str, List[Dict[str, Any]]] = {}
        avail: Dict[str, Set[str]] = {}
        now = time.time()
        for e in self.db.rows("SELECT * FROM edges WHERE app_key=?", (app_key,)):
            e["src"], e["dst"] = self.canonical(e["src"]), self.canonical(e["dst"])
            e["p"] = reliability(e, now)
            e["args"] = json.loads(e["args_json"] or "{}")
            by_cmd.setdefault(e["command_id"], []).append(e)
            avail.setdefault(e["src"], set()).add(e["command_id"])
            if e["src"] != e["dst"]:
                cur = G.get_edge_data(e["src"], e["dst"])
                if cur is None or e["p"] > cur["e"]["p"]:
                    G.add_edge(e["src"], e["dst"], e=e)
        v = {"G": G, "by_cmd": by_cmd, "avail": avail, "gen": g}
        self._views[app_key] = (g, v)
        self._views.move_to_end(app_key)
        while len(self._views) > C.GRAPH_LRU_APPS:
            self._views.popitem(last=False)
        return v

    def commands_in(self, app_key: str, state_id: str) -> Set[str]:
        return set(self.view(app_key)["avail"].get(self.canonical(state_id), ()))

    @staticmethod
    def _edge_cost(e: Dict[str, Any], tier: int) -> float:
        base = C.ROUTE_COST_MS.get(e["route"], 300) / 1000.0 * C.TIER_ROUTE_MULT.get(tier, {}).get(e["route"], 1.0)
        return base + C.LAMBDA * -math.log(e["p"])

    def _step(self, e: Dict[str, Any]) -> PlanStep:
        return PlanStep(e["command_id"], e["route"], dict(e["args"]), e["dst"], "", e["p"], e["safety"], [])

    def path_to(self, app_key: str, from_state: str, command_id: str, allow: FrozenSet[str] = frozenset(), tier: int = 0, k: int = C.K_ALTERNATIVES,
                exclude: Optional[Set[Tuple[str, str]]] = None) -> List[GraphPath]:
        """Up to k distinct cheapest edge sequences from `from_state` ending in an edge that performs `command_id`. Unsafe edges are invisible unless their category is allowed."""
        v = self.view(app_key)
        G, goals = v["G"], v["by_cmd"].get(command_id, [])
        start = self.canonical(from_state)
        ex = exclude or set()

        def ok(e: Dict[str, Any]) -> bool:
            return (e["safety"] == "allow" or (e["safety"] in allow and e["safety"] != "financial")) and (e["src"], e["command_id"]) not in ex

        def w(u, x, d):
            e = d["e"]
            return self._edge_cost(e, tier) if ok(e) else None

        if start is None:
            return []
        try:
            dist, paths = nx.single_source_dijkstra(G, start, weight=w) if start in G else ({start: 0.0}, {start: [start]})
        except Exception:
            dist, paths = {start: 0.0}, {start: [start]}
        out: List[GraphPath] = []
        for ge in goals:
            if not ok(ge) or ge["src"] not in dist:
                continue
            nodes = paths[ge["src"]]
            if len(nodes) > C.MAX_PATH_DEPTH:
                continue
            steps, cost, p = [], 0.0, 1.0
            for a, b in zip(nodes, nodes[1:]):
                e = G[a][b]["e"]
                steps.append(self._step(e))
                cost += self._edge_cost(e, tier)
                p *= e["p"]
            steps.append(self._step(ge))
            cost += self._edge_cost(ge, tier)
            p *= ge["p"]
            out.append(GraphPath(steps, cost, p, ge["dst"]))
        out.sort(key=lambda gp: (gp.cost_s, -gp.p_success))
        seen, uniq = set(), []
        for gp in out:
            sig = tuple((s.command_id, s.route) for s in gp.steps)
            if sig not in seen:
                seen.add(sig)
                uniq.append(gp)
        return uniq[:k]

    def path_to_state(self, app_key: str, from_state: str, to_state: str, allow: FrozenSet[str] = frozenset(), tier: int = 0) -> Optional[GraphPath]:
        v = self.view(app_key)
        G = v["G"]
        a, b = self.canonical(from_state), self.canonical(to_state)
        if a == b:
            return GraphPath([], 0.0, 1.0, b or "")
        if a not in G or b not in G:
            return None

        def w(u, x, d):
            e = d["e"]
            return self._edge_cost(e, tier) if (e["safety"] == "allow" or (e["safety"] in allow and e["safety"] != "financial")) else None
        try:
            nodes = nx.dijkstra_path(G, a, b, weight=w)
        except Exception:
            return None
        steps, cost, p = [], 0.0, 1.0
        for x, y in zip(nodes, nodes[1:]):
            e = G[x][y]["e"]
            steps.append(self._step(e))
            cost += self._edge_cost(e, tier)
            p *= e["p"]
        return GraphPath(steps, cost, p, b)

    # ---- housekeeping -------------------------------------------------------------------------------------------------------------------------------
    def stats(self, app_key: str = "") -> Dict[str, Any]:
        w, a = (" WHERE app_key=?", (app_key,)) if app_key else ("", ())
        return {"nodes": self.db.one(f"SELECT COUNT(*) AS n FROM nodes{w}", a)["n"], "edges": self.db.one(f"SELECT COUNT(*) AS n FROM edges{w}", a)["n"],
                "observations": self.db.one(f"SELECT COUNT(*) AS n FROM observations{w}", a)["n"]}

    def forget_app(self, app_key: str) -> int:
        n = 0
        with self.db.lock:
            for t in ("edges", "observations", "landmark_df", "sigs"):
                n += self.db.execute(f"DELETE FROM {t} WHERE app_key=?", (app_key,)).rowcount
            ids = [r["state_id"] for r in self.db.rows("SELECT state_id FROM nodes WHERE app_key=?", (app_key,))]
            for i in ids:
                self.db.execute("DELETE FROM aliases WHERE state_id=? OR canonical_id=?", (i, i))
            n += self.db.execute("DELETE FROM nodes WHERE app_key=?", (app_key,)).rowcount
            self.db.commit()
        lt.drop_app(self.st, "ui_states", app_key)
        self._views.pop(app_key, None)
        self.st.bump(f"graph:{app_key}")
        return n
