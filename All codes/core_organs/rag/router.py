"""
rag.router -- the Master Router & the Rag facade (DESIGN.md section 7).

    Rag                the five sub-RAGs + lexicon + storage in one object: retrieve / localize / observe / ingest / status
    Router.retrieve    Stage A context (app, tier, state) -> B intent -> C routing (cheapest reliable signal first, stop when sufficient) -> D fusion -> E one cached, capped query rewrite

No LLM on the hot path. Per-probe budgets are SOFT (a probe that has started is not killed; later optional probes are skipped once the budget is spent and the trace says so).
Every result carries `gaps` (what was not found and why) and a `trace` (each hop: probe, ms, hits, why it stopped).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from . import config as C
from . import lt
from . import storage as ST
from . import statekey as SK
from .fastpaths import FastPaths, KIND_ROUTE, spoken_chords
from .graph import Graph, GraphPath
from .icons import Icons
from .lexicon import Lexicon, Match, canon, surface, toks
from .procedures import Procedures
from .recovery import Recovery
from .types import (Evidence, Outcome, Plan, PlanStep, Query, RagStatus, Retrieval, UpsertReport, dumps, retrieval_from_dict, to_jsonable)

try:
    import safety_guard as _SG                      # type: ignore
except Exception:                                   # pragma: no cover
    try:
        from core_organs import safety_guard as _SG
    except Exception:
        _SG = None

# ---- Stage B: intent ---------------------------------------------------------------------------------------------------------------------------------
_IDENTIFY = re.compile(r"\bwhat(?:'s| is| does)?\b.*\b(this|that|these|those)\b.*\b(icon|button|tool|control|symbol|thing|do|does|for)\b|\bwhat does this\b", re.I)
_LOCATE = re.compile(r"^\s*(?:where(?:'s| is| are| can i find)?|find|locate|show me|point (?:me )?to|which (?:button|menu|tab|icon|tool))\b", re.I)
_CURRICULUM = re.compile(r"\b(teach me|learn|from (?:the )?basics|beginner|course|lesson|practice|curriculum|tutorial series)\b", re.I)
_EXPLAIN = re.compile(r"^\s*(?:why|explain|what(?:'s| is| are| does)|difference|define|meaning of|tell me about|is there)\b", re.I)
_DO_HOW = re.compile(r"^\s*(?:how (?:do|can|to|would)|how do i|can you|could you|please|i want to|i need to|help me)\b", re.I)
_DO_VERB = re.compile(r"^\s*(?:create|make|add|insert|open|save|export|import|delete|remove|build|draw|set|turn|toggle|apply|run|start|stop|close|rename|duplicate|copy|paste|move|rotate|scale|extrude|bevel|type|enter|select|click|press|switch|render|generate|model|resize|crop|zoom)\b", re.I)
_PARAMS = re.compile(r"\d|[\"'\u201c\u2018]")
_KEYS_Q = re.compile(r"\b(shortcut|shortcuts|hotkey|hotkeys|keyboard|key combination|key combo|keystroke|keybinding|key binding|chord)\b", re.I)
_CREATION = re.compile(r"\b(create|build|make|generate|model|draw|design|render|produce|automate|batch)\b", re.I)


def classify_intent(text: str) -> Tuple[str, float, List[str]]:
    """(intent, confidence, alternatives). Deterministic rules in priority order; two competing rules lower the confidence and name the alternative."""
    t = text or ""
    hits = []
    if _IDENTIFY.search(t):
        hits.append("IDENTIFY")
    if _LOCATE.search(t):
        hits.append("LOCATE")
    if _CURRICULUM.search(t):
        hits.append("CURRICULUM")
    explain, do = bool(_EXPLAIN.search(t)), bool(_DO_HOW.search(t) or _DO_VERB.search(t))
    if explain and not _IDENTIFY.search(t) and not _LOCATE.search(t):
        hits.append("EXPLAIN")
    if do:
        hits.append("DO")
    if not hits:
        return "EXPLAIN", 0.4, ["DO"]
    primary = hits[0]
    conf = 0.9 if len(hits) == 1 else 0.55
    return primary, conf, hits[1:]


def infer_tier(snapshot: Any, hint: int = -1) -> int:
    if hint is not None and hint >= 0:
        return int(hint)
    nodes = snapshot.get("nodes") if isinstance(snapshot, dict) else snapshot
    nodes = list(nodes or [])
    if not nodes:
        return 3 if isinstance(snapshot, dict) and (snapshot.get("ocr") or snapshot.get("icons") or snapshot.get("grid")) else 0

    def g(n, k):
        return n.get(k, "") if isinstance(n, dict) else getattr(n, k, "")
    classes = " ".join(str(g(n, "cls") or g(n, "class_name")) for n in nodes[:200]).lower()
    named = sum(1 for n in nodes if str(g(n, "name") or "").strip()) / max(1, len(nodes))
    tabs = sum(1 for n in nodes if str(g(n, "ctype")).lower().replace(" ", "") in ("tabitem", "tab"))
    if "chrome_widgetwin" in classes or "chrome_renderwidgethost" in classes:
        return 1
    if len(nodes) > 20 and named < 0.3:
        return 3
    if (tabs >= 4 and len(nodes) >= 150) or len(nodes) >= 400:
        return 2
    return 0


def _safety_of(label: str) -> str:
    if _SG is None or not label:
        return "allow"
    d = _SG.check(label)
    return "allow" if d.allowed else d.category


def utility(p: Plan, mode: str) -> float:
    return p.p_success - C.ALPHA_COST * (p.cost_ms / 1000.0) - C.BETA_UNGROUNDED * (1.0 - p.grounded_ratio) - (C.GAMMA_HUMAN if (p.needs_human and mode != "tutor") else 0.0)


def finish_plan(steps: List[PlanStep], origin: str, q: Query, grounded: Optional[int] = None, note: str = "") -> Plan:
    p = 1.0
    cost = 0.0
    human = False
    for s in steps:
        p *= max(1e-4, min(1.0, s.reliability))
        cost += C.ROUTE_COST_MS.get(s.route, 200) * (3 if s.probe else 1) if s.route != "meta" else 0.0
        lifted = s.safety in q.allow_categories and s.safety != "financial"
        if s.safety != "allow" and not lifted:
            human = True
    g = grounded if grounded is not None else sum(1 for s in steps if not s.probe)
    plan = Plan(steps, round(p, 4), round(cost, 1), round(g / len(steps), 3) if steps else 0.0, human, origin, 0.0, note)
    plan.utility = round(utility(plan, q.mode), 4)
    return plan


_LLM_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-llm")


class Rag:
    def __init__(self, storage: Optional[ST.Storage] = None, embedder=None, skills_provider: Optional[Callable[[str, str], Optional[List[PlanStep]]]] = None,
                 rewriter: Optional[Callable[[str, str], List[str]]] = None, seed: bool = True, icons: bool = True):
        self.st = storage or (ST.Storage(embedder=embedder) if embedder is not None else ST.get_storage())
        self.lex = Lexicon(self.st)
        self.graph = Graph(self.st)
        self.fast = FastPaths(self.st)
        self.proc = Procedures(self.st, self.lex)
        self.rec = Recovery(self.st)
        self.icons: Optional[Icons] = None
        if icons:
            try:
                self.icons = Icons(self.st, self.lex)
            except Exception:
                self.icons = None
        self.skills_provider = skills_provider
        self.rewriter = rewriter
        self.router = Router(self)
        if seed and self.st.count("error_playbooks") == 0:
            self.rec.seed()

    # ---- public API ---------------------------------------------------------------------------------------------------------------------------------
    def retrieve(self, q: Query) -> Retrieval:
        return self.router.retrieve(q)

    def retrieve_workflow(self, app_key: str, user_goal: str, current_som_map: Any = None, mode: str = "auto", **kw) -> Retrieval:
        """The brief's entry point: video-tutorial steps and exact UI graph paths for a goal in an app."""
        return self.retrieve(Query(text=user_goal, app_key=app_key, snapshot=current_som_map, mode=mode, **kw))

    def localize(self, app_key: str, snapshot: Any, **kw):
        return self.graph.localize(app_key, snapshot, **kw)

    def observe(self, o: Outcome) -> Dict[str, Any]:
        """The executor reports every step result: fans out to the graph, fast paths, procedures and recovery, and appends to telemetry."""
        res: Dict[str, Any] = {}
        res["graph"] = self.graph.observe(o)
        res["fast"] = self.fast.observe(o)
        self.proc.observe(o)
        res["recovery"] = self.rec.observe(o)
        try:
            self.st.sql("telemetry").execute("INSERT INTO outcomes(ts,run_id,app_key,command_id,route,ok,effect,failure_code) VALUES(?,?,?,?,?,?,?,?)",
                                            (time.time(), o.run_id, o.app_key, o.step.command_id, o.step.route, 1 if o.ok else 0, o.effect, o.failure_code))
            self.st.sql("telemetry").commit()
        except Exception:
            pass
        return res

    def ingest(self, sub_rag: str, records: Iterable[Dict[str, Any]]) -> UpsertReport:
        if sub_rag in ("fast", "fastpaths", "S4"):
            return self.fast.upsert(records)
        if sub_rag in ("recovery", "S5"):
            return self.rec.upsert(records)
        raise ValueError(f"ingest({sub_rag!r}): use procedures.ingest_transcript / ingest_document / ingest_procedure for S3, graph.add_edge for S2, icons.learn for S1")

    def status(self) -> RagStatus:
        deg = list(self.st.degraded)
        if not self.st.embed.healthy:
            deg.append("embedder_down")
        tables = {t: self.st.count(t) for t in ("knowledge_chunks", "procedures", "fast_paths", "error_playbooks", "ui_states")}
        for t, n in tables.items():
            if n >= C.IVF_PQ_MIN_ROWS and not self.st.meta.get(f"ann_rows:{t}"):
                deg.append(f"ann_recommended:{t}")
        return RagStatus(not any(d.startswith("store_unavailable") for d in deg), self.st.root, deg, tables, self.st.embed.id, int(self.st.meta.get("schema_version", 0)))

    def resolve_app(self, text: str) -> str:
        low = " " + surface(text) + " "
        best = ""
        for r in self.lex.db.rows("SELECT DISTINCT app_key FROM commands UNION SELECT app_key FROM apps"):
            a = r["app_key"]
            if a and f" {a.lower()} " in low and len(a) > len(best):
                best = a
        return best

    def forget_app(self, app_key: str) -> Dict[str, int]:
        return {"lexicon": self.lex.forget_app(app_key), "graph": self.graph.forget_app(app_key), "fast": self.fast.forget_app(app_key), "procedures": self.proc.forget_app(app_key),
                "recovery": self.rec.forget_app(app_key), "icons": self.icons.forget_app(app_key) if self.icons else 0}

    # ---- master domains (rag.domains) ---------------------------------------------------------------------------------------------------------------
    def domain_of(self, app_key: str) -> str:
        from . import domains as DM
        return DM.domain_of(app_key, DM.load(self))

    def register_domain(self, app_key: str, domain: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        from . import domains as DM
        DM.register(self, app_key, domain, evidence)

    def domain_stats(self) -> Dict[str, Dict[str, int]]:
        from . import domains as DM
        return DM.stats(self)

    def close(self) -> None:
        if self.icons:
            self.icons.close()
        self.st.close()


class Router:
    def __init__(self, rag: Rag):
        self.r = rag
        self.st = rag.st

    # ---- helpers ------------------------------------------------------------------------------------------------------------------------------------
    def _probe(self, trace: List[Dict[str, Any]], name: str, fn: Callable[..., Any], *a, default: Any = None, **kw) -> Any:
        t0 = time.perf_counter()
        why = ""
        try:
            out = fn(*a, **kw)
        except Exception as exc:                       # a sub-RAG that is unavailable degrades the answer; it never raises into the caller
            out, why = default, f"error:{type(exc).__name__}:{str(exc)[:80]}"
        n = len(out) if hasattr(out, "__len__") else (1 if out else 0)
        trace.append({"probe": name, "ms": round((time.perf_counter() - t0) * 1000, 2), "hits": n, "why": why})
        return out if out is not None else default

    def _over(self, t0: float, q: Query) -> bool:
        return (time.perf_counter() - t0) * 1000 > q.budget_ms

    def _gens(self, app: str) -> str:
        return ",".join(str(self.st.gen(f"{k}:{app}")) for k in ("graph", "fast", "proc", "recovery", "lexicon")) + f",{self.st.gen('recovery:*')}"

    # ---- retrieve -----------------------------------------------------------------------------------------------------------------------------------
    def retrieve(self, q: Query) -> Retrieval:
        t0 = time.perf_counter()
        r = self.r
        ret = Retrieval(query=q)
        ret.degraded = list(self.st.degraded)
        app = q.app_key or r.resolve_app(q.text)
        if not app:
            ret.gaps.append("app_unknown")
        if q.domain and app:                                           # master-domain partition: a key of another domain is not this query's knowledge (rag.domains)
            from . import domains as DM
            if DM.domain_of(app, DM.load(r)) != q.domain:
                ret.gaps.append(f"wrong_domain:{DM.domain_of(app, DM.load(r))}")
                return ret
        # Stage A: tier and state
        info = r.lex.app(app) if app else {"tier": -1}
        tier = infer_tier(q.snapshot, info.get("tier", -1)) if (q.snapshot is not None or info.get("tier", -1) >= 0) else 0
        if app and info.get("tier", -1) < 0 and q.snapshot is not None:
            r.lex.set_app(app, tier=tier)
        ret.tier = tier
        state_id = None
        live: Set[str] = set()
        if app and q.snapshot is not None:
            loc = self._probe(ret.trace, "localize", r.graph.localize, app, q.snapshot, app_version=q.app_version, tier=tier)
            if loc is not None and getattr(loc, "state_id", ""):
                state_id = loc.state_id
                live = r.graph.commands_in(app, state_id)
        ret.state_id = state_id
        ctx = {"window_kind": (r.graph.node(state_id) or {}).get("window_kind") if state_id else None}
        # Stage B: intent (RECOVER pre-empts)
        if q.popup is not None or q.failure:
            intent, conf, alts = "RECOVER", 1.0, []
        elif q.region is not None or q.crop is not None:
            intent, conf, alts = "IDENTIFY", 0.95, []
        else:
            intent, conf, alts = classify_intent(q.text)
        ret.intent = intent
        ret.trace.append({"probe": "intent", "ms": 0.0, "hits": 1, "why": f"{intent} conf={conf} alts={alts}"})
        # cache (pure text/state queries only)
        key = ""
        if app and q.popup is None and not q.failure and q.crop is None and q.region is None:
            key = hashlib.sha1("|".join([app, state_id or "", re.sub(r"\s+", " ", q.text.strip().lower()), intent, q.mode, ",".join(sorted(q.allow_categories)), q.app_version,
                                         self._gens(app), str(C.ROUTER_VERSION)]).encode()).hexdigest()
            row = self.st.sql("cache").one("SELECT v, ts FROM router_cache WHERE k=?", (key,))
            if row and time.time() - row["ts"] < C.CACHE_TTL_S:
                out = retrieval_from_dict(json.loads(row["v"]), q)
                out.trace = [{"probe": "cache", "ms": round((time.perf_counter() - t0) * 1000, 2), "hits": 1, "why": "router_cache"}]
                return out
        # Stage C/D
        handler = {"DO": self._do, "EXPLAIN": self._explain, "LOCATE": self._locate, "IDENTIFY": self._identify, "RECOVER": self._recover, "CURRICULUM": self._curriculum}[intent]
        handler(q, app, tier, state_id, live, ctx, ret, t0)
        if conf < 0.6 and alts and intent == "DO" and "EXPLAIN" in alts and not self._over(t0, q):
            self._explain(q, app, tier, state_id, live, ctx, ret, t0, merge=True)
        if intent == "EXPLAIN" and conf < 0.6 and "DO" in alts and not self._over(t0, q) and not ret.plans:
            self._do(q, app, tier, state_id, live, ctx, ret, t0, merge=True)
        ret.plans.sort(key=lambda p: (-p.utility, -p.p_success, len(p.steps)))
        ret.plans = ret.plans[:C.K_ALTERNATIVES + 1]
        if not self.st.embed.healthy:
            ret.degraded.append("embedder_down")
        if intent in ("DO", "EXPLAIN") and app and (ret.gaps or not ret.plans and not ret.evidence):
            ret.explore_targets = self._probe(ret.trace, "explore_targets", r.proc.explore_targets, app, default=[])
        total = (time.perf_counter() - t0) * 1000
        if key and (ret.plans or ret.evidence) and not any(d.startswith("embedder") for d in ret.degraded):
            body = to_jsonable(ret)
            body.pop("query", None)
            try:
                self.st.sql("cache").execute("INSERT OR REPLACE INTO router_cache(k,v,ts) VALUES(?,?,?)", (key, json.dumps(body, ensure_ascii=False), time.time()))
                self.st.sql("cache").commit()
            except Exception:
                pass
        try:
            best = ret.plans[0] if ret.plans else None
            self.st.sql("telemetry").execute("INSERT INTO router_calls(ts,app_key,intent,tier,ms_total,ms_by_probe_json,n_plans,best_p,grounded_ratio,llm_used,degraded) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                            (time.time(), app, intent, tier, total, json.dumps({t["probe"]: t["ms"] for t in ret.trace}), len(ret.plans), best.p_success if best else 0.0,
                                             best.grounded_ratio if best else 0.0, 1 if any(t["probe"] == "llm_rewrite" and t["hits"] for t in ret.trace) else 0, ",".join(ret.degraded)))
            self.st.sql("telemetry").commit()
        except Exception:
            pass
        return ret

    # ---- route building -----------------------------------------------------------------------------------------------------------------------------
    def _step_from_fast(self, ev: Evidence, cmd: str) -> PlanStep:
        pl = ev.payload
        return PlanStep(cmd, pl["route"], {"fast_id": pl["fast_id"], "payload": pl["payload"], "kind": pl["kind"], "missing": pl["missing"], "sandbox": pl["sandbox"]},
                        None, f"{pl['kind']} {pl['payload'][:40]}", ev.confidence, ev.safety, [], bool(pl["probe"]))

    def _command_choices(self, q: Query, app: str, tier: int, state_id: Optional[str], ctx: Dict[str, Any], cmd: str) -> Dict[str, Optional[Tuple[List[PlanStep], float, Optional[str], List[Evidence]]]]:
        """For ONE command: the best fast-path route and the best graph route (each: steps, cost_s, state_after, evidence) -- either may be None."""
        r = self.r
        fast_c = None
        evs = r.fast.by_command(app, cmd, ctx)
        direct = [e for e in evs if not e.payload["probe"]]
        pick = (direct or evs)[:1]
        if pick:
            e = pick[0]
            fast_c = ([self._step_from_fast(e, cmd)], C.ROUTE_COST_MS.get(e.payload["route"], 100) / 1000.0, state_id, [e])
        graph_c = None
        if state_id:
            paths = r.graph.path_to(app, state_id, cmd, q.allow_categories, tier, 1)
            if paths:
                gp = paths[0]
                graph_c = (gp.steps, gp.cost_s, gp.goal_state or state_id, [])
        return {"fast": fast_c, "graph": graph_c}

    @staticmethod
    def _score_choice(c: Tuple[List[PlanStep], float, Optional[str], List[Evidence]]) -> float:
        p = 1.0
        for s in c[0]:
            p *= max(1e-4, s.reliability) * (0.6 if s.probe else 1.0)
        return p - C.ALPHA_COST * c[1]

    def _plans_for_commands(self, q: Query, app: str, tier: int, state_id: Optional[str], ctx: Dict[str, Any], cmds: List[str], origin_hint: str = "") -> List[Plan]:
        if not cmds:
            return []
        per = [self._command_choices(q, app, tier, state_id, ctx, c) for c in cmds]
        variants: Dict[str, Optional[List[PlanStep]]] = {"best": [], "fast": [], "graph": []}
        used_graph = used_fast = False
        for cmd, ch in zip(cmds, per):
            avail = [(k, v) for k, v in ch.items() if v]
            if avail:
                k, v = max(avail, key=lambda kv: self._score_choice(kv[1]))
                variants["best"] += v[0]
                used_fast |= (k == "fast")
                used_graph |= (k == "graph")
            else:
                s = PlanStep(cmd, "control_click", {}, None, "route not yet known", 0.35, _safety_of(cmd.split(":", 1)[-1]), [], True)
                variants["best"].append(s)
            for k in ("fast", "graph"):
                if variants[k] is not None:
                    if ch[k]:
                        variants[k] += ch[k][0]
                    else:
                        variants[k] = None
        plans, seen = [], set()
        for name, steps in variants.items():
            if not steps:
                continue
            sig = tuple((s.command_id, s.route, s.args.get("fast_id", "")) for s in steps)
            if sig in seen:
                continue
            seen.add(sig)
            for s in steps:
                s.safety = s.safety if s.safety != "allow" else _safety_of(s.command_id.split(":", 1)[-1])
            origin = origin_hint or ("fast_path" if all(s.args.get("fast_id") for s in steps) else "graph")
            plans.append(finish_plan(steps, origin, q))
        return plans

    def _plan_from_steps(self, q: Query, app: str, tier: int, state_id: Optional[str], ctx: Dict[str, Any], steps: Sequence[Dict[str, Any]], origin: str, note: str = "") -> Optional[Plan]:
        r = self.r
        out: List[PlanStep] = []
        cur = state_id
        for s in steps:
            cmd = s.get("command_id")
            if cmd:
                ch = self._command_choices(q, app, tier, cur, ctx, cmd)
                avail = [(k, v) for k, v in ch.items() if v]
                if avail:
                    k, v = max(avail, key=lambda kv: self._score_choice(kv[1]))
                    out += v[0]
                    cur = v[2] or cur
                    continue
                out.append(PlanStep(cmd, s.get("route_hint") or "control_click", {"text": s.get("text", "")}, None, s.get("text", "")[:60], 0.4, _safety_of(cmd.split(":", 1)[-1]), [], True))
            elif s.get("chord"):
                out.append(PlanStep(f"{app}:chord:{s['chord']}", "hotkey", {"keys": s["chord"]}, None, s.get("text", "")[:60], 0.4, "allow", [], True))
            elif s.get("menu_path"):
                out.append(PlanStep(f"{app}:menu:{'>'.join(canon(p) for p in s['menu_path'])}", "menu_path", {"path": s["menu_path"]}, None, s.get("text", "")[:60], 0.4, "allow", [], True))
            else:
                continue
        return finish_plan(out, origin, q, note=note) if out else None

    # ---- DO -----------------------------------------------------------------------------------------------------------------------------------------
    def _greedy_commands(self, matches: List[Match], goal: str) -> List[Match]:
        """Strong matches that do not compete for the same words, in the order they appear in the goal."""
        claimed: Set[str] = set()
        chosen = []
        for m in sorted(matches, key=lambda m: -m.score):
            if m.score < 0.8:
                continue
            tk = set(toks(m.surface))
            if tk & claimed:
                continue
            claimed |= tk
            chosen.append(m)
        g = surface(goal)
        chosen.sort(key=lambda m: g.find(m.surface) if m.surface in g else 10_000)
        return chosen

    def _do(self, q: Query, app: str, tier: int, state_id: Optional[str], live: Set[str], ctx: Dict[str, Any], ret: Retrieval, t0: float, merge: bool = False) -> None:
        r = self.r
        goal = q.text
        plans: List[Plan] = []
        passages: Optional[List[Evidence]] = None                      # the supporting passages for this goal, fetched at most once

        def good() -> bool:
            return any(p.grounded_ratio >= 1.0 and p.p_success >= C.MIN_P_STOP for p in plans)
        if not app:
            ret.gaps.append("no_app_for_plan")
            return
        # 1. a verified macro skill
        if r.skills_provider:
            steps = self._probe(ret.trace, "skill", r.skills_provider, goal, app, default=None)
            if steps:
                plans.append(finish_plan(list(steps), "skill", q, grounded=len(steps), note="verified macro"))
        # 2. scripts compete whenever the goal is a creation, carries parameters (a number, a quoted name), or the app is tier 3: a verified template with its slots filled beats a UI route
        matches = self._probe(ret.trace, "lexicon", r.lex.resolve, app, goal, live, default=[])
        cmds = self._greedy_commands(matches, goal)
        creation = bool(_CREATION.search(goal))
        if not good() and (creation or tier == 3 or _PARAMS.search(goal)):
            for ev in self._probe(ret.trace, "fast_goal", r.fast.by_goal, app, goal, ctx, 4, default=[]):
                if ev.kind in ("script", "com", "cli"):
                    s = self._step_from_fast(ev, ev.command_ids[0] if ev.command_ids else f"{app}:script")
                    for m in ev.payload["missing"]:
                        ret.gaps.append(f"needs_param:{m}")
                    s.safety = ev.safety if ev.safety != "allow" else _safety_of(goal)
                    plans.append(finish_plan([s], "script", q, note=ev.text))
        # 3. the goal names known command(s): hotkey / command routes and graph paths
        if not good() and cmds:
            plans += self._probe(ret.trace, "routes", self._plans_for_commands, q, app, tier, state_id, ctx, [m.command_id for m in cmds], default=[])
        # 4. a procedure (guide / transcript / crawl doc) for the goal
        procs: List[Evidence] = []
        chunks: List[Evidence] = []
        if not good():
            procs = self._probe(ret.trace, "procedures", r.proc.find_procedures, app, goal, q.app_version, 3, default=[])
            for ev in procs[:2]:
                pl = self._plan_from_steps(q, app, tier, state_id, ctx, ev.payload["steps"], "procedure+graph", ev.text)
                if pl:
                    plans.append(pl)
            if not procs:
                chunks = self._probe(ret.trace, "chunks", r.proc.query, app, goal, q.app_version, live, 3, default=[])
                passages = chunks
                ret.evidence += chunks
                want = {m.command_id for m in cmds}
                for ev in chunks[:1]:
                    steps = ev.payload["steps"]
                    hit = [i for i, st_ in enumerate(steps) if st_.get("command_id") in want]
                    if hit:                                  # a transcript window is an excerpt: keep the span that is about this goal, not the whole minute of video
                        steps = steps[hit[0]:hit[-1] + 1]
                    pl = self._plan_from_steps(q, app, tier, state_id, ctx, steps, "procedure+graph", ev.citation)
                    if pl:
                        plans.append(pl)
        # 5. weak recall (NOT "no plan is grounded" -- without a scanned UI every plan is a probe): nothing resolved to a command AND no passage/procedure was found by both retrieval legs.
        #    One capped, cached rewrite.
        found_strong = bool(cmds) or any(e.score >= C.WEAK_RECALL_SCORE for e in procs) or any(e.payload.get("rrf", 0.0) >= C.WEAK_RECALL_SCORE for e in chunks)
        if not good() and not found_strong and q.allow_llm_rewrite and r.rewriter:
            alts = self._rewrite(app, goal, ret)
            for alt in alts[:2]:
                m2 = r.lex.resolve(app, alt, live)
                c2 = self._greedy_commands(m2, alt)
                if c2:
                    plans += self._plans_for_commands(q, app, tier, state_id, ctx, [m.command_id for m in c2])
                for ev in r.proc.find_procedures(app, alt, q.app_version, 1):
                    pl = self._plan_from_steps(q, app, tier, state_id, ctx, ev.payload["steps"], "procedure+graph", ev.text)
                    if pl:
                        plans.append(pl)
        # 6. a sparse app may borrow from its archetype siblings -- tagged, discounted, probe-only
        if not plans:
            plans += self._borrow_plans(q, app, tier, goal, ret)
        if not plans:
            ret.gaps.append("no_plan_found")
        if not cmds and not any(p.origin in ("skill", "script") for p in plans):
            ret.gaps.append("no_command_resolved")
        for p in plans:
            for s in p.steps:
                if s.args.get("missing"):
                    ret.gaps += [f"needs_param:{m}" for m in s.args["missing"] if f"needs_param:{m}" not in ret.gaps]
        ret.plans += plans
        if q.mode != "auto" and (passages is not None or not self._over(t0, q)):   # tutor / explain modes also quote the supporting passages (optional: skipped once the budget is spent)
            if passages is None:
                passages = self._probe(ret.trace, "explain_chunks", r.proc.query, app, goal, q.app_version, live, 2, default=[])
            have = {x.citation for x in ret.evidence}
            ret.evidence += [e for e in passages[:2] if e.citation not in have]

    def _has_knowledge(self, app: str) -> bool:
        r = self.r
        return bool(app) and (r.lex.n_commands(app) > 0 or r.proc.chunk_count(app) > 0 or r.fast.count(app) > 0)

    def _rewrite(self, app: str, goal: str, ret: Retrieval) -> List[str]:
        if not self._has_knowledge(app):                    # nothing to search with a better wording: do not spend an LLM call (seconds) to rephrase a question about an app we know nothing about
            ret.trace.append({"probe": "llm_rewrite", "ms": 0.0, "hits": 0, "why": "no_knowledge"})
            ret.gaps.append("app_has_no_knowledge")
            return []
        key = hashlib.sha1(f"{app}|{' '.join(toks(goal))}".encode()).hexdigest()
        row = self.st.sql("cache").one("SELECT v FROM rewrite_cache WHERE k=?", (key,))
        if row:
            ret.trace.append({"probe": "llm_rewrite", "ms": 0.0, "hits": 0, "why": "cached"})
            return json.loads(row["v"])
        # a WALL-CLOCK cap: the model call runs in a worker and the router stops waiting at LLM_REWRITE_TIMEOUT_S (the worker is abandoned, not killed; its answer is discarded)
        fut = _LLM_POOL.submit(self.r.rewriter, app, goal)
        t0 = time.perf_counter()
        try:
            out = fut.result(timeout=C.LLM_REWRITE_TIMEOUT_S) or []
            why = ""
        except Exception as exc:
            out, why = [], ("timeout" if type(exc).__name__ in ("TimeoutError", "Timeout") else f"error:{type(exc).__name__}")
        ret.trace.append({"probe": "llm_rewrite", "ms": round((time.perf_counter() - t0) * 1000, 2), "hits": len(out), "why": why})
        out = [str(x) for x in out][:2]
        if out:
            self.st.sql("cache").execute("INSERT OR REPLACE INTO rewrite_cache(k,v,ts) VALUES(?,?,?)", (key, json.dumps(out), time.time()))
            self.st.sql("cache").commit()
        return out

    def _borrow_sources(self, app: str) -> List[str]:
        r = self.r
        if r.lex.n_commands(app) >= C.BORROW_MIN_COMMANDS and r.proc.chunk_count(app) >= C.BORROW_MIN_CHUNKS:
            return []
        arche = r.lex.app(app).get("archetype", "")
        return [a for a in r.lex.apps_of(arche) if a != app][:3]

    def _borrow_plans(self, q: Query, app: str, tier: int, goal: str, ret: Retrieval) -> List[Plan]:
        plans = []
        for sib in self._borrow_sources(app):
            sources = list(self.r.proc.find_procedures(sib, goal, "", 1)) or list(self.r.proc.query(sib, goal, "", None, 1))
            for ev in sources:
                steps = []
                for s in ev.payload["steps"]:
                    steps.append(PlanStep(f"{app}:{canon(s.get('target') or s.get('text', ''))}", s.get("route_hint") or "control_click", {"text": s.get("text", ""), "borrowed_from": sib},
                                          None, s.get("text", "")[:60], 0.4 * C.BORROW_CONFIDENCE_MULT, "allow", [], True))
                if steps:
                    pl = finish_plan(steps, "borrowed", q, grounded=0, note=f"borrowed from {sib}")
                    plans.append(pl)
                    ret.gaps.append(f"borrowed_from:{sib}")
        return plans

    # ---- EXPLAIN ------------------------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _fuse(lists: Sequence[Sequence[Evidence]], mult: Optional[Sequence[float]] = None) -> List[Evidence]:
        scored: Dict[Tuple[str, str], Tuple[float, Evidence]] = {}
        for li, lst in enumerate(lists):
            for rank, e in enumerate(lst):
                w = C.TRUST_W.get(e.trust, 0.4) * max(0.05, e.confidence) / (C.RRF_K + rank + 1) * C.RRF_K * (mult[li] if mult else 1.0)
                k = (e.sub_rag, e.citation or e.text[:40])
                if k in scored:
                    scored[k] = (scored[k][0] + w, scored[k][1])
                else:
                    scored[k] = (w, e)
        out = []
        for w, e in sorted(scored.values(), key=lambda t: -t[0]):
            e.score = round(w, 5)
            out.append(e)
        return out

    def _where_evidence(self, q: Query, app: str, tier: int, state_id: Optional[str], cmds: List[str]) -> Tuple[List[Evidence], List[Plan]]:
        r = self.r
        evs, plans = [], []
        for cmd in cmds[:2]:
            paths = r.graph.path_to(app, state_id, cmd, q.allow_categories, tier, 2) if state_id else []
            for gp in paths:
                label = " → ".join(r.lex.label_of(s.command_id) for s in gp.steps)
                evs.append(Evidence("graph", app, "path", f"{r.lex.label_of(cmd)}: {label}", [cmd], {"steps": [to_jsonable(s) for s in gp.steps]}, "learned",
                                    round(gp.p_success, 3), gp.cost_s * 1000, "allow", f"graph:{state_id}", "", 0.0))
                plans.append(finish_plan(list(gp.steps), "graph", q))
        return evs, plans

    def _explain(self, q: Query, app: str, tier: int, state_id: Optional[str], live: Set[str], ctx: Dict[str, Any], ret: Retrieval, t0: float, merge: bool = False) -> None:
        r = self.r
        if not app:
            ret.evidence += self._probe(ret.trace, "procedures_global", self._global_chunks, q.text, default=[])
            ret.gaps.append("app_unknown")
            return
        chords = spoken_chords(q.text)
        keyq = bool(_KEYS_Q.search(q.text)) or bool(chords)           # a question about keys is answered best by the hotkey rows
        chunks = self._probe(ret.trace, "procedures", r.proc.query, app, q.text, q.app_version, live, 4, default=[])
        fast = [e for e in self._probe(ret.trace, "fast_goal", r.fast.by_goal, app, q.text, ctx, 4 if keyq else 2, default=[])]
        exact = [e for ch in chords for e in self._probe(ret.trace, "chord", r.fast.by_chord, app, ch, default=[])]        # 'what does ctrl plus h do': the rows whose keys ARE ctrl+h come first
        matches = self._probe(ret.trace, "lexicon", r.lex.resolve, app, q.text, live, default=[])
        where, _ = self._where_evidence(q, app, tier, state_id, [m.command_id for m in self._greedy_commands(matches, q.text)])
        # weak recall -> one capped rewrite. Weak = nothing was found by BOTH retrieval legs (raw reciprocal-rank score), no exact chord hit, no command resolved.
        strong = bool(exact) or bool(where) or any(e.payload.get("rrf", 0.0) >= C.WEAK_RECALL_SCORE for e in chunks) or any(e.score >= C.WEAK_RECALL_SCORE for e in fast)
        if not strong and q.allow_llm_rewrite and r.rewriter and not self._over(t0, q):
            for alt in self._rewrite(app, q.text, ret)[:2]:
                chunks += r.proc.query(app, alt, q.app_version, live, 2)
        if not chunks:
            for sib in self._borrow_sources(app):
                for e in r.proc.query(sib, q.text, "", None, 2):
                    e.trust, e.borrowed_from = "borrowed", sib
                    e.confidence *= C.BORROW_CONFIDENCE_MULT
                    chunks.append(e)
                    ret.gaps.append(f"borrowed_from:{sib}")
        # the key-question boost applies only to hotkey rows that genuinely matched (found by both legs); a row that matched one stray word must not outrank a passage that answers the question
        fast_strong = [e for e in fast if e.score >= C.WEAK_RECALL_SCORE]
        fast_weak = [e for e in fast if e.score < C.WEAK_RECALL_SCORE]
        fused = self._fuse([chunks, fast_strong, fast_weak, where], [1.0, C.SHORTCUT_QUERY_BOOST if keyq else 1.0, 1.0, 1.0])
        have = {e.citation for e in exact}
        ret.evidence += (exact + [e for e in fused if e.citation not in have])[:6]
        if not ret.evidence:
            ret.gaps.append("nothing_known")
        return
        ret.evidence += self._fuse([chunks, fast, where])[:6]
        if not ret.evidence:
            ret.gaps.append("nothing_known")

    def _global_chunks(self, text: str) -> List[Evidence]:
        out = []
        for r_ in lt.search(self.st, "knowledge_chunks", text, "", limit=3):
            out.append(Evidence("procedure", r_["app_key"], "chunk", r_["text"], list(r_.get("mentions") or []), {"chunk_id": r_["chunk_id"], "heading_path": r_["heading_path"]},
                                "borrowed", float(r_["quality"]) * C.BORROW_CONFIDENCE_MULT, 0.0, "allow", r_["source_ref"], r_["app_key"], r_["_rrf"]))
        return out

    # ---- LOCATE -------------------------------------------------------------------------------------------------------------------------------------
    def _locate(self, q: Query, app: str, tier: int, state_id: Optional[str], live: Set[str], ctx: Dict[str, Any], ret: Retrieval, t0: float) -> None:
        r = self.r
        if not app:
            ret.gaps.append("app_unknown")
            return
        matches = self._probe(ret.trace, "lexicon", r.lex.resolve, app, q.text, live, default=[])
        cmds = [m.command_id for m in self._greedy_commands(matches, q.text)] or [m.command_id for m in matches[:1]]
        if not cmds:
            ret.gaps.append("no_command_resolved")
        evs, plans = self._where_evidence(q, app, tier, state_id, cmds)
        ret.plans += plans
        ret.evidence += evs
        for cmd in cmds[:2]:
            if not state_id:
                ret.gaps.append("state_unknown")
            elif not any(cmd in e.command_ids for e in evs):
                ret.gaps.append(f"no_known_path:{cmd}")
                ret.evidence += self._probe(ret.trace, "fast_cmd", r.fast.by_command, app, cmd, ctx, 2, default=[])
        ret.evidence += self._probe(ret.trace, "ui_states", lambda: [Evidence("graph", app, "state", s["description"], [], {"state_id": s["state_id"]}, "learned", 0.5, 0.0, "allow", f"graph:{s['state_id']}", "", s["score"])
                                                                   for s in r.graph.find_states(app, q.text, 3)], default=[])
        if not ret.evidence and not ret.plans:
            # nothing scanned yet (no states, no paths): answer from what IS known -- the hotkey rows and passages that mention it -- and say the map is missing
            known = self._fuse([self._probe(ret.trace, "fast_goal", r.fast.by_goal, app, q.text, ctx, 4, default=[]),
                                self._probe(ret.trace, "procedures", r.proc.query, app, q.text, q.app_version, live, 3, default=[])])
            ret.evidence += known[:4]
            if known:
                ret.gaps.append("answered_from_text_not_from_a_ui_map")

    # ---- IDENTIFY -----------------------------------------------------------------------------------------------------------------------------------
    def _region_control(self, q: Query) -> Optional[str]:
        nodes = q.snapshot.get("nodes") if isinstance(q.snapshot, dict) else q.snapshot
        if not nodes or not q.region:
            return None
        x0, y0, x1, y1 = q.region
        best, best_a = None, 1e18
        for n in nodes:
            g = (lambda k: n.get(k) if isinstance(n, dict) else getattr(n, k, None))
            rc, name = g("rect"), (g("name") or "").strip()
            if not rc or not name:
                continue
            l, t, rr, b = rc
            if rr <= x0 or l >= x1 or b <= y0 or t >= y1:
                continue
            a = (rr - l) * (b - t)
            if 0 < a < best_a:
                best, best_a = name, a
        return best

    def _identify(self, q: Query, app: str, tier: int, state_id: Optional[str], live: Set[str], ctx: Dict[str, Any], ret: Retrieval, t0: float) -> None:
        r = self.r
        label, cmds = "", []
        if q.crop is not None and r.icons:
            ev, gaps = self._probe(ret.trace, "icon", r.icons.lookup, q.crop, None, 0, app, default=(None, ["icon_probe_failed"]))
            ret.gaps += gaps
            if ev:
                ret.evidence.append(ev)
                label, cmds = ev.text, list(ev.command_ids)
        if not label:
            name = self._probe(ret.trace, "region_control", self._region_control, q, default=None)
            if name:
                label = name
                ret.evidence.append(Evidence("graph", app, "control", name, [], {"name": name}, "learned", 0.9, 0.0, _safety_of(name), f"uia:{state_id}", "", 0.9))
        if label and not cmds and app:
            cmds = [m.command_id for m in r.lex.resolve(app, label, live, 2)]
        if not label:
            ret.gaps.append("control_unidentified")
            return
        for cmd in cmds[:1]:
            ret.evidence += self._probe(ret.trace, "fast_cmd", r.fast.by_command, app, cmd, ctx, 2, default=[])
            ret.evidence += self._probe(ret.trace, "explain", r.proc.query, app, r.lex.label_of(cmd), q.app_version, live, 2, default=[])
        if not cmds:
            ret.gaps.append("command_unresolved")
            ret.evidence += self._probe(ret.trace, "explain", r.proc.query, app, label, q.app_version, live, 2, default=[])
        ret.evidence = self._fuse([ret.evidence])

    # ---- RECOVER ------------------------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _popup_message(popup: Any) -> str:
        if popup is None:
            return ""
        if isinstance(popup, dict):
            return " ".join(str(popup.get(k, "")) for k in ("title", "text", "message"))
        return " ".join(str(getattr(popup, k, "")) for k in ("title", "text"))

    def _recover(self, q: Query, app: str, tier: int, state_id: Optional[str], live: Set[str], ctx: Dict[str, Any], ret: Retrieval, t0: float) -> None:
        r = self.r
        f = q.failure or {}
        code = f.get("failure_code", "")
        msg = f.get("message", "") or self._popup_message(q.popup)
        evs = self._probe(ret.trace, "recovery", r.rec.lookup, app or "*", q.popup, code, msg, f.get("toolkit", ""), 3, default=[])
        ret.evidence += evs
        for ev in evs[:1]:
            pb = ev.payload
            steps = []
            for a in pb["resolution"]:
                act = a.get("action", "")
                steps.append(PlanStep(f"recovery:{act}", "control_click" if act == "click_button" else "meta", dict(a, sig_id=pb["sig_id"]), None, act, ev.confidence, "allow", [], False))
            plan = finish_plan(steps, "playbook", q, grounded=len(steps), note=pb["failure_code"]) if steps else Plan([], ev.confidence, 0.0, 1.0, True, "playbook", 0.0, "needs a person")
            plan.needs_human = plan.needs_human or pb["needs_human"]
            ret.plans.append(plan)
            if pb["needs_human"]:
                ret.gaps.append(f"needs_human:{pb['class']}")
        target = f.get("command_id")
        if target and state_id and app:                                     # replan from where the screen actually is
            for gp in r.graph.path_to(app, state_id, target, q.allow_categories, tier, 2):
                ret.plans.append(finish_plan(list(gp.steps), "graph", q, note="replan from the actual state"))
        if not evs:
            ret.gaps.append("no_playbook")
            if code:
                ret.gaps.append(f"unknown_failure:{code}")

    # ---- CURRICULUM ---------------------------------------------------------------------------------------------------------------------------------
    def _curriculum(self, q: Query, app: str, tier: int, state_id: Optional[str], live: Set[str], ctx: Dict[str, Any], ret: Retrieval, t0: float) -> None:
        r = self.r
        if not app:
            ret.gaps.append("app_unknown")
            return
        topic = re.sub(r"\b(teach me|learn|from (?:the )?basics|beginner|course|lesson|practice|curriculum)\b", " ", q.text, flags=re.I).strip() or "basics"
        procs = self._probe(ret.trace, "procedures", r.proc.find_procedures, app, topic, q.app_version, 8, default=[])
        procs.sort(key=lambda e: (len(e.payload["steps"]), -e.payload["grounded_ratio"]))      # shortest, best-grounded first: basics before advanced
        ret.evidence += procs
        if not procs:
            ret.gaps.append("no_procedures_for_topic")
            ret.explore_targets = r.proc.explore_targets(app)
        ret.trace.append({"probe": "coverage", "ms": 0.0, "hits": r.graph.stats(app)["nodes"], "why": f"graph={r.graph.stats(app)} commands={r.lex.n_commands(app)}"})
