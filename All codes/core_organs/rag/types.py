"""rag.types -- the common envelopes every sub-RAG and the router speak (DESIGN.md section 4). Pure dataclasses, JSON round-trippable."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple


def to_jsonable(o: Any) -> Any:
    if is_dataclass(o) and not isinstance(o, type):
        return {k: to_jsonable(v) for k, v in asdict(o).items() if k not in ("snapshot", "popup")}
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in o]
    return o


def dumps(o: Any) -> str:
    return json.dumps(to_jsonable(o), ensure_ascii=False, sort_keys=True)


@dataclass
class Evidence:
    sub_rag: str                    # icon | graph | procedure | fast | recovery
    app_key: str
    kind: str                       # path | hotkey | script | chunk | procedure | icon_label | playbook | ...
    text: str
    command_ids: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    trust: str = "seed"             # verified | learned | catalog | official_doc | seed | transcript | web | llm | borrowed
    confidence: float = 0.5
    cost_ms: float = 0.0
    safety: str = "allow"           # allow | destructive | financial | commit | unnamed
    citation: str = ""
    borrowed_from: str = ""
    score: float = 0.0


@dataclass
class PlanStep:
    command_id: str
    route: str                      # script | wm_command | hotkey | uia_invoke | menu_path | control_click | posted_click | type
    args: Dict[str, Any] = field(default_factory=dict)
    expect_state: Optional[str] = None
    expect_note: str = ""
    reliability: float = 0.5
    safety: str = "allow"
    evidence: List[int] = field(default_factory=list)
    probe: bool = False             # unverified: the executor tries it with before/after verification and reports the outcome


@dataclass
class Plan:
    steps: List[PlanStep] = field(default_factory=list)
    p_success: float = 0.0
    cost_ms: float = 0.0
    grounded_ratio: float = 0.0
    needs_human: bool = False
    origin: str = "graph"           # skill | fast_path | graph | procedure+graph | script | borrowed
    utility: float = 0.0
    note: str = ""


@dataclass
class Query:
    text: str = ""
    app_key: str = ""
    snapshot: Any = None
    region: Optional[Tuple[float, float, float, float]] = None
    popup: Any = None
    failure: Optional[Dict[str, Any]] = None
    mode: str = "tutor"             # tutor | auto | explain
    allow_categories: FrozenSet[str] = frozenset()
    budget_ms: int = 150
    allow_llm_rewrite: bool = True
    app_version: str = ""
    crop: Any = None                # PIL image of the region for IDENTIFY (optional)


@dataclass
class Retrieval:
    query: Query
    intent: str = ""
    tier: int = 0
    state_id: Optional[str] = None
    plans: List[Plan] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    degraded: List[str] = field(default_factory=list)
    explore_targets: List[str] = field(default_factory=list)


@dataclass
class Outcome:
    run_id: str
    app_key: str
    step: PlanStep
    src_state: Optional[str] = None
    observed_snapshot: Any = None
    ok: bool = True
    effect: str = ""                # what changed ("dialog opened") or "no_effect"
    latency_ms: float = 0.0
    failure_code: str = ""
    popup: Any = None
    expected_dst: Optional[str] = None
    observed_dst: Optional[str] = None
    resolution: Optional[Dict[str, Any]] = None   # a recovery action that was tried: {sig_id, ok}


@dataclass
class UpsertReport:
    sub_rag: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    degraded: List[str] = field(default_factory=list)


@dataclass
class RagStatus:
    ok: bool
    root: str
    degraded: List[str] = field(default_factory=list)
    tables: Dict[str, int] = field(default_factory=dict)
    embedder: str = ""
    schema_version: int = 0


def _build(cls, d: Dict[str, Any]):
    names = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in d.items() if k in names})


def retrieval_from_dict(d: Dict[str, Any], query: "Query") -> "Retrieval":
    """Rebuild a cached Retrieval (the query is never cached: it can hold live snapshots)."""
    plans = []
    for p in d.get("plans", []):
        p = dict(p)
        p["steps"] = [_build(PlanStep, s) for s in p.get("steps", [])]
        plans.append(_build(Plan, p))
    return Retrieval(query=query, intent=d.get("intent", ""), tier=d.get("tier", 0), state_id=d.get("state_id"), plans=plans, evidence=[_build(Evidence, e) for e in d.get("evidence", [])],
                     gaps=list(d.get("gaps", [])), trace=list(d.get("trace", [])), degraded=list(d.get("degraded", [])), explore_targets=list(d.get("explore_targets", [])))
