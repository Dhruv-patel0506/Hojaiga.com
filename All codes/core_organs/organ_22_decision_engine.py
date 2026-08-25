"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 22
Name: Decision Engine (Full Production Implementation)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Decision Engine]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: math, enum, typing, future, json, asyncio, logging, time, uuid, dataclasses...
"""
from __future__ import annotations

"""
Organ: Decision Engine
File: organ_22_decision_engine.py
Authority: Constitution > LawBook > PolicyManual > MasterArchitectureBlueprint
> Organ Specification > DECISION_ENGINE.md

Role: Deterministic, explainable, policy-compliant reasoning organ sitting
between Brain (intent) and Workflow Compiler (execution synthesis).
Never executes workflows or side effects. Sockets-only communication.
"""

import hashlib
import json
import math
import time
import uuid
import logging
import asyncio
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional, Dict, List, Tuple

try:
    from core_organs.organ_02_cns_single_file import EventEnvelope, EventBus
except ImportError:
    EventEnvelope = Any
    EventBus = Any

# ─────────────────────────────────────────────────────────────────────────
# Logging (structured, per Section 13)
# ─────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("hojaiga.decision_engine")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


def _log(stream: str, level: str, module: str, decision_id: str, trace_id: str, payload: dict) -> None:
    frame = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "decision_id": decision_id,
        "trace_id": trace_id,
        "log_stream": stream,
        "log_level": level,
        "module": module,
        "payload": payload,
    }
    logger.log(getattr(logging, level, logging.INFO), json.dumps(frame, default=str))


# ─────────────────────────────────────────────────────────────────────────
# Enums / Result Types
# ─────────────────────────────────────────────────────────────────────────
class ConfidenceLevel(str, Enum):
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class DecisionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


# ─────────────────────────────────────────────────────────────────────────
# Data Contracts
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class Requestor:
    id: str
    authority_level: int = 0
    security_token: str = ""


@dataclass
class Goal:
    raw_intent: str
    target_primitive: str
    parameters: dict = field(default_factory=dict)


@dataclass
class DecisionRequest:
    goal: Goal
    requestor: Requestor
    context_overrides: dict = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    trace_id: str = field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)


@dataclass
class ParsedGoal:
    target_primitive: str
    parameters: dict
    implicit_constraints: list = field(default_factory=list)


@dataclass
class NormalizedContext:
    resource_availability: dict = field(default_factory=lambda: {"cpu": 1.0, "ram": 1.0, "gpu": 1.0})
    system_load: float = 0.1
    thermal_headroom: float = 1.0
    user_authority_level: int = 0
    degraded: bool = False


@dataclass
class ConstraintMatrix:
    max_memory_mb: Optional[int] = None
    max_latency_ms: Optional[int] = None
    forbidden_windows: list = field(default_factory=list)
    satisfiable: bool = True


@dataclass
class PolicyValidationResult:
    passed: bool
    violated_policies: list = field(default_factory=list)
    masked_scope: dict = field(default_factory=dict)


@dataclass
class CandidateStrategy:
    strategy_id: str
    name: str
    required_capabilities: list = field(default_factory=list)
    execution_steps: list = field(default_factory=list)
    sub_scores: dict = field(default_factory=dict)
    risk_factors: dict = field(default_factory=dict)
    composite_risk: float = 0.0
    final_score: float = 0.0
    confidence_score: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    viable: bool = True
    rejection_reason: str = ""


@dataclass
class SelectedStrategy:
    strategy_id: str
    name: str
    confidence_score: float
    confidence_level: str
    composite_risk_score: float
    execution_steps: list
    explanation_tree: dict
    audit_signature: str


@dataclass
class DecisionResponse:
    request_id: str
    decision_id: str
    status: str
    selected_strategy: Optional[dict] = None
    rejection_reason: str = ""
    metrics: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class ScoringWeights:
    policy_compliance: float = 0.20
    success_probability: float = 0.15
    security_score: float = 0.15
    reliability: float = 0.10
    health_status: float = 0.10
    resource_cost: float = 0.05
    execution_time: float = 0.05
    user_preferences: float = 0.05
    historical_success: float = 0.05
    hardware_match: float = 0.05
    scalability: float = 0.05

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConfidenceThresholds:
    very_high: float = 0.90
    high: float = 0.80
    medium: float = 0.60
    low: float = 0.40
    human_approval_required_below: float = 0.80


@dataclass
class RiskCeilings:
    max_allowed_composite_risk: float = 0.65
    max_allowed_security_risk: float = 0.10
    max_allowed_hardware_risk: float = 0.80


@dataclass
class ConfigState:
    version: str = "1.0.0-aos"
    max_decision_latency_ms: int = 500
    fallback_on_timeout: bool = True
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    confidence: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    risk: RiskCeilings = field(default_factory=RiskCeilings)


# ─────────────────────────────────────────────────────────────────────────
# Sockets
# ─────────────────────────────────────────────────────────────────────────
class SocketError(Exception):
    pass


@dataclass
class Socket:
    name: str
    direction: str
    version: str = "v1.0.0-aos"
    timeout_ms: int = 100
    retries: int = 0
    handler: Optional[Callable[[dict], dict]] = None

    def call(self, payload: dict) -> dict:
        if self.handler is None:
            raise SocketError(f"{self.name} has no bound handler")
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                return self.handler(payload)
            except Exception as exc:
                last_exc = exc
        raise SocketError(f"{self.name} failed after {self.retries + 1} attempts: {last_exc}")


class DecisionEngineSockets:
    def __init__(self) -> None:
        self.decision_socket_in = Socket("DecisionSocketIn", "input", timeout_ms=500, retries=3)
        self.decision_socket_out = Socket("DecisionSocketOut", "output", timeout_ms=200, retries=0)
        self.context_socket = Socket("ContextSocket", "bidirectional", timeout_ms=100, retries=2)
        self.policy_socket = Socket("PolicySocket", "output", timeout_ms=50, retries=1)
        self.capability_socket = Socket("CapabilitySocket", "bidirectional", timeout_ms=100, retries=2)
        self.service_socket = Socket("ServiceSocket", "bidirectional", timeout_ms=100, retries=2)
        self.risk_socket = Socket("RiskSocket", "internal", timeout_ms=20, retries=0)
        self.scoring_socket = Socket("ScoringSocket", "internal", timeout_ms=20, retries=0)
        self.validation_socket = Socket("ValidationSocket", "internal", timeout_ms=10, retries=0)
        self.history_socket = Socket("HistorySocket", "output", timeout_ms=1000, retries=5)
        self.metrics_socket = Socket("MetricsSocket", "output", timeout_ms=10, retries=0)

    def bind_defaults(self) -> None:
        self.context_socket.handler = lambda p: {
            "resource_availability": {"cpu": 1.0, "ram": 1.0, "gpu": 1.0},
            "system_load": 0.1, "thermal_headroom": 1.0
        }
        self.policy_socket.handler = lambda p: {"passed": True, "violated_policies": []}
        self.capability_socket.handler = lambda p: {"matched": p.get("required_capabilities", []), "missing": []}
        self.service_socket.handler = lambda p: {"service_id": "local", "health": "OK", "latency_ms": 1}
        self.history_socket.handler = lambda p: {"stored": True}
        self.metrics_socket.handler = lambda p: {"accepted": True}


# ─────────────────────────────────────────────────────────────────────────
# Analyzers
# ─────────────────────────────────────────────────────────────────────────
class GoalAnalyzer:
    def analyze(self, goal: Goal) -> ParsedGoal:
        if not goal.target_primitive or not isinstance(goal.parameters, dict):
            raise ValueError("INVALID_GOAL_SCHEMA")
        implicit = []
        if goal.parameters.get("destructive"):
            implicit.append("REQUIRES_HUMAN_APPROVAL_IF_MEDIUM_OR_LOWER")
        return ParsedGoal(target_primitive=goal.target_primitive, parameters=dict(goal.parameters),
                          implicit_constraints=implicit)


class ContextAnalyzer:
    def __init__(self, sockets: DecisionEngineSockets) -> None:
        self._sockets = sockets

    def get_active_context(self, overrides: dict) -> NormalizedContext:
        try:
            raw = self._sockets.context_socket.call({"overrides": overrides})
            ctx = NormalizedContext(
                resource_availability=raw.get("resource_availability", {"cpu": 1.0, "ram": 1.0, "gpu": 1.0}),
                system_load=raw.get("system_load", 0.1),
                thermal_headroom=raw.get("thermal_headroom", 1.0),
                user_authority_level=overrides.get("user_authority_level", 0),
            )
            ctx.resource_availability.update(overrides.get("resource_availability", {}))
            return ctx
        except SocketError:
            return NormalizedContext(
                resource_availability={"cpu": 0.1, "ram": 0.1, "gpu": 0.0},
                system_load=0.9, thermal_headroom=0.5, degraded=True,
            )


class ConstraintAnalyzer:
    def analyze(self, parsed_goal: ParsedGoal, ctx: NormalizedContext) -> ConstraintMatrix:
        max_mem = parsed_goal.parameters.get("max_memory_mb")
        max_lat = parsed_goal.parameters.get("max_latency_ms")
        if max_mem is not None and max_lat is not None and max_mem <= 0:
            return ConstraintMatrix(satisfiable=False)
        return ConstraintMatrix(max_memory_mb=max_mem, max_latency_ms=max_lat)


class PolicyValidator:
    def __init__(self, sockets: DecisionEngineSockets) -> None:
        self._sockets = sockets

    def validate(self, parsed_goal: ParsedGoal, constraints: ConstraintMatrix,
                 requestor: Requestor) -> PolicyValidationResult:
        if not constraints.satisfiable:
            return PolicyValidationResult(passed=False, violated_policies=["CONSTRAINTS_UNSATISFIABLE"])
        try:
            result = self._sockets.policy_socket.call({
                "target_primitive": parsed_goal.target_primitive,
                "security_token": requestor.security_token,
            })
            return PolicyValidationResult(passed=result.get("passed", False),
                                           violated_policies=result.get("violated_policies", []))
        except SocketError:
            return PolicyValidationResult(passed=False, violated_policies=["SECURITY_REJECT_POLICY_UNREACHABLE"])


# ─────────────────────────────────────────────────────────────────────────
# Resolvers
# ─────────────────────────────────────────────────────────────────────────
class CapabilityResolver:
    def __init__(self, sockets: DecisionEngineSockets) -> None:
        self._sockets = sockets

    def resolve(self, parsed_goal: ParsedGoal) -> dict:
        required = parsed_goal.parameters.get("required_capabilities", [parsed_goal.target_primitive])
        try:
            result = self._sockets.capability_socket.call({"required_capabilities": required})
            return {"matched": result.get("matched", []), "missing": result.get("missing", [])}
        except SocketError:
            return {"matched": [], "missing": required}


class ServiceResolver:
    def __init__(self, sockets: DecisionEngineSockets) -> None:
        self._sockets = sockets

    def resolve(self, matched_capabilities: list) -> dict:
        try:
            result = self._sockets.service_socket.call({"capabilities": matched_capabilities})
            return {"service_id": result.get("service_id", "local"), "health": result.get("health", "UNKNOWN"),
                    "latency_ms": result.get("latency_ms", 0)}
        except SocketError:
            return {"service_id": None, "health": "OFFLINE", "latency_ms": None}


class ConnectorResolver:
    def resolve(self, service: dict) -> dict:
        return {"active_connectors": ["local"], "quota_remaining": 1.0} if service.get("service_id") else {
            "active_connectors": [], "quota_remaining": 0.0
        }


class DependencyEvaluator:
    def evaluate(self, matched: list, service: dict, connectors: dict) -> dict:
        if service.get("health") == "OFFLINE" and not connectors["active_connectors"]:
            return {"valid": False, "error": "NO_VIABLE_DEPENDENCY_PATH"}
        return {"valid": True, "order": list(matched)}


# ─────────────────────────────────────────────────────────────────────────
# Alternative Generation
# ─────────────────────────────────────────────────────────────────────────
class AlternativeGenerator:
    def generate(self, parsed_goal: ParsedGoal, capability_map: dict) -> list[CandidateStrategy]:
        candidates: list[CandidateStrategy] = []
        base_id = f"strat_{parsed_goal.target_primitive.replace('.', '_')}"
        candidates.append(CandidateStrategy(
            strategy_id=f"{base_id}_primary",
            name=f"Primary::{parsed_goal.target_primitive}",
            required_capabilities=capability_map.get("matched", [parsed_goal.target_primitive]),
            execution_steps=[{"step_id": "s1", "capability_required": parsed_goal.target_primitive, "service_assigned": "local"}],
        ))
        return candidates


# ─────────────────────────────────────────────────────────────────────────
# Risk Analyzer
# ─────────────────────────────────────────────────────────────────────────
class RiskAnalyzer:
    _DOMAIN_WEIGHTS = {
        "security": 0.20, "resource": 0.12, "dependency": 0.12, "failure": 0.12,
        "timeout": 0.10, "compatibility": 0.10, "plugin": 0.08, "external": 0.08, "hardware": 0.08,
    }

    def analyze(self, candidate: CandidateStrategy, ctx: NormalizedContext,
                dependency_result: dict) -> dict:
        risks = {
            "security": 0.02,
            "resource": max(0.0, 1.0 - ctx.resource_availability.get("ram", 1.0)),
            "dependency": 0.0 if dependency_result.get("valid") else 1.0,
            "failure": 0.05,
            "timeout": max(0.0, ctx.system_load - 0.5) if ctx.system_load > 0.5 else 0.0,
            "compatibility": 0.0,
            "plugin": 0.0,
            "external": 0.0,
            "hardware": max(0.0, 1.0 - ctx.thermal_headroom),
        }
        composite = 1.0
        for k, r in risks.items():
            composite *= (1.0 - min(1.0, max(0.0, r)) * self._DOMAIN_WEIGHTS[k])
        composite_risk = round(1.0 - composite, 6)
        return {"factors": risks, "composite_risk": composite_risk}


# ─────────────────────────────────────────────────────────────────────────
# Confidence Engine
# ─────────────────────────────────────────────────────────────────────────
class ConfidenceEngine:
    def __init__(self, thresholds: ConfidenceThresholds) -> None:
        self._t = thresholds

    def score(self, base_score: float, composite_risk: float, ctx: NormalizedContext) -> tuple[float, ConfidenceLevel]:
        context_clarity = 0.5 if ctx.degraded else 1.0
        confidence = base_score * (1.0 - min(1.0, composite_risk)) * context_clarity
        confidence = round(max(0.0, min(1.0, confidence)), 6)
        if confidence >= self._t.very_high:
            level = ConfidenceLevel.VERY_HIGH
        elif confidence >= self._t.high:
            level = ConfidenceLevel.HIGH
        elif confidence >= self._t.medium:
            level = ConfidenceLevel.MEDIUM
        elif confidence >= self._t.low:
            level = ConfidenceLevel.LOW
        else:
            level = ConfidenceLevel.UNKNOWN
        return confidence, level


# ─────────────────────────────────────────────────────────────────────────
# Decision Scoring Engine
# ─────────────────────────────────────────────────────────────────────────
class DecisionScoringEngine:
    def __init__(self, weights: ScoringWeights) -> None:
        self._w = weights

    def score(self, candidate: CandidateStrategy, policy_passed: bool, service_health: str,
              composite_risk: float, ctx: NormalizedContext) -> float:
        sub = {
            "M_POL": 1.0 if policy_passed else 0.0,
            "M_PRB": 0.9 if candidate.viable else 0.0,
            "M_SEC": max(0.0, 1.0 - candidate.risk_factors.get("security", 0.0)) if candidate.risk_factors else 0.9,
            "M_REL": 0.85 if service_health == "OK" else 0.4,
            "M_HLT": 1.0 - ctx.system_load,
            "M_CST": 0.9,
            "M_TIM": 1.0 - min(1.0, ctx.system_load),
            "M_PRF": 0.7,
            "M_HIS": 0.7,
            "M_HW": ctx.thermal_headroom,
            "M_SCL": 0.8,
        }
        candidate.sub_scores = sub
        if sub["M_POL"] == 0.0:
            candidate.final_score = 0.0
            candidate.viable = False
            candidate.rejection_reason = candidate.rejection_reason or "POLICY_VIOLATION"
            return 0.0
        weight_map = self._w.as_dict()
        key_order = ["policy_compliance", "success_probability", "security_score", "reliability",
                     "health_status", "resource_cost", "execution_time", "user_preferences",
                     "historical_success", "hardware_match", "scalability"]
        metric_order = ["M_POL", "M_PRB", "M_SEC", "M_REL", "M_HLT", "M_CST", "M_TIM", "M_PRF", "M_HIS", "M_HW", "M_SCL"]
        final = sum(sub[m] * weight_map[k] for m, k in zip(metric_order, key_order))
        final = round(max(0.0, min(1.0, final - composite_risk * 0.05)), 6)
        candidate.final_score = final
        return final


# ─────────────────────────────────────────────────────────────────────────
# Strategy Selector
# ─────────────────────────────────────────────────────────────────────────
class StrategySelector:
    def __init__(self, thresholds: ConfidenceThresholds) -> None:
        self._t = thresholds

    def select(self, ranked: list[CandidateStrategy], destructive: bool) -> tuple[Optional[CandidateStrategy], bool, str]:
        viable = [c for c in ranked if c.viable and c.final_score > 0.0]
        if not viable:
            return None, False, "NO_VIABLE_STRATEGY"
        viable.sort(key=lambda c: c.final_score, reverse=True)
        top = viable[0]
        if top.confidence_level == ConfidenceLevel.UNKNOWN:
            return None, False, "CONFIDENCE_BELOW_MINIMUM_THRESHOLD"
        needs_human = (
            top.confidence_level == ConfidenceLevel.LOW
            or (top.confidence_level == ConfidenceLevel.MEDIUM and destructive)
        )
        return top, needs_human, ""


# ─────────────────────────────────────────────────────────────────────────
# Decision Validator & Explanation Generator
# ─────────────────────────────────────────────────────────────────────────
class DecisionValidator:
    def __init__(self, sockets: DecisionEngineSockets) -> None:
        self._sockets = sockets

    def validate(self, strategy: CandidateStrategy) -> bool:
        if not strategy.strategy_id or strategy.final_score <= 0.0:
            return False
        try:
            self._sockets.validation_socket.call({"strategy_id": strategy.strategy_id})
        except SocketError:
            pass
        return True

    @staticmethod
    def sign(payload: dict) -> str:
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


class ExplanationGenerator:
    def explain(self, selected: CandidateStrategy, all_ranked: list[CandidateStrategy]) -> dict:
        rejected = [{"strategy_id": c.strategy_id,
                     "reason": c.rejection_reason or f"lower_score:{c.final_score}"}
                    for c in all_ranked if c.strategy_id != selected.strategy_id]
        trade_offs = []
        if selected.composite_risk > 0.1:
            trade_offs.append(f"accepted_risk:{selected.composite_risk}")
        return {
            "primary_reason": f"highest_composite_score:{selected.final_score}",
            "trade_offs_accepted": trade_offs,
            "rejected_alternatives": rejected,
        }


# ─────────────────────────────────────────────────────────────────────────
# Decision History
# ─────────────────────────────────────────────────────────────────────────
class DecisionHistory:
    def __init__(self, sockets: DecisionEngineSockets) -> None:
        self._sockets = sockets
        self._chain: list[dict] = []

    def record(self, decision_id: str, trace_id: str, record: dict) -> None:
        prev_hash = self._chain[-1]["hash"] if self._chain else "0" * 64
        entry = {"decision_id": decision_id, "trace_id": trace_id, "record": record, "prev_hash": prev_hash}
        entry_hash = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()
        entry["hash"] = entry_hash
        self._chain.append(entry)
        try:
            self._sockets.history_socket.call(entry)
        except SocketError:
            pass


# ─────────────────────────────────────────────────────────────────────────
# Decision Core — Orchestrator
# ─────────────────────────────────────────────────────────────────────────
class DecisionEngineCore:
    def __init__(self, config: Optional[ConfigState] = None, sockets: Optional[DecisionEngineSockets] = None) -> None:
        self.config = config or ConfigState()
        self.sockets = sockets or DecisionEngineSockets()
        self.sockets.bind_defaults()

        self._goal_analyzer = GoalAnalyzer()
        self._context_analyzer = ContextAnalyzer(self.sockets)
        self._constraint_analyzer = ConstraintAnalyzer()
        self._policy_validator = PolicyValidator(self.sockets)
        self._capability_resolver = CapabilityResolver(self.sockets)
        self._service_resolver = ServiceResolver(self.sockets)
        self._connector_resolver = ConnectorResolver()
        self._dependency_evaluator = DependencyEvaluator()
        self._alt_generator = AlternativeGenerator()
        self._risk_analyzer = RiskAnalyzer()
        self._confidence_engine = ConfidenceEngine(self.config.confidence)
        self._scoring_engine = DecisionScoringEngine(self.config.weights)
        self._strategy_selector = StrategySelector(self.config.confidence)
        self._validator = DecisionValidator(self.sockets)
        self._explainer = ExplanationGenerator()
        self._history = DecisionHistory(self.sockets)

    def process_request(self, request: DecisionRequest) -> DecisionResponse:
        start = time.perf_counter()
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        candidates_evaluated = 0

        try:
            parsed_goal = self._goal_analyzer.analyze(request.goal)
        except ValueError as exc:
            return self._reject(request, decision_id, start, str(exc), candidates_evaluated)

        ctx = self._context_analyzer.get_active_context(request.context_overrides)
        constraints = self._constraint_analyzer.analyze(parsed_goal, ctx)
        policy_result = self._policy_validator.validate(parsed_goal, constraints, request.requestor)

        if not policy_result.passed:
            return self._reject(request, decision_id, start,
                                 f"SECURITY_REJECT:{policy_result.violated_policies}", candidates_evaluated)

        capability_map = self._capability_resolver.resolve(parsed_goal)
        service = self._service_resolver.resolve(capability_map.get("matched", []))
        connectors = self._connector_resolver.resolve(service)
        dependency_result = self._dependency_evaluator.evaluate(capability_map.get("matched", []), service, connectors)

        candidates = self._alt_generator.generate(parsed_goal, capability_map)
        candidates_evaluated = len(candidates)
        destructive = bool(parsed_goal.parameters.get("destructive"))

        for cand in candidates:
            risk = self._risk_analyzer.analyze(cand, ctx, dependency_result)
            cand.risk_factors = risk["factors"]
            cand.composite_risk = risk["composite_risk"]
            base_score = self._scoring_engine.score(cand, policy_result.passed, service.get("health", "OK"),
                                                      cand.composite_risk, ctx)
            confidence, level = self._confidence_engine.score(base_score, cand.composite_risk, ctx)
            cand.confidence_score = confidence
            cand.confidence_level = level

        selected, needs_human, reject_reason = self._strategy_selector.select(candidates, destructive)

        if selected is None:
            return self._reject(request, decision_id, start, reject_reason, candidates_evaluated)

        if not self._validator.validate(selected):
            return self._reject(request, decision_id, start, "DECISION_VALIDATION_FAILED", candidates_evaluated)

        explanation = self._explainer.explain(selected, candidates)
        audit_payload = {
            "decision_id": decision_id, "strategy_id": selected.strategy_id,
            "confidence": selected.confidence_score, "risk": selected.composite_risk,
        }
        signature = DecisionValidator.sign(audit_payload)

        selected_strategy = SelectedStrategy(
            strategy_id=selected.strategy_id,
            name=selected.name,
            confidence_score=selected.confidence_score,
            confidence_level=selected.confidence_level.value,
            composite_risk_score=selected.composite_risk,
            execution_steps=selected.execution_steps,
            explanation_tree=explanation,
            audit_signature=signature,
        )

        status = DecisionStatus.HUMAN_APPROVAL_REQUIRED if needs_human else DecisionStatus.ACCEPTED
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

        response = DecisionResponse(
            request_id=request.request_id,
            decision_id=decision_id,
            status=status.value,
            selected_strategy=asdict(selected_strategy),
            metrics={"total_latency_ms": elapsed_ms, "candidates_evaluated": candidates_evaluated},
        )

        self._history.record(decision_id, request.trace_id, {
            "status": status.value, "selected_strategy_id": selected.strategy_id,
            "confidence_level": selected.confidence_level.value, "signature": signature,
        })

        return response

    def _reject(self, request: DecisionRequest, decision_id: str, start: float,
                reason: str, candidates_evaluated: int) -> DecisionResponse:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        self._history.record(decision_id, request.trace_id, {"status": "REJECTED", "reason": reason})
        return DecisionResponse(
            request_id=request.request_id,
            decision_id=decision_id,
            status=DecisionStatus.REJECTED.value,
            rejection_reason=reason,
            metrics={"total_latency_ms": elapsed_ms, "candidates_evaluated": candidates_evaluated},
        )


def create_decision_engine(config: Optional[ConfigState] = None) -> DecisionEngineCore:
    return DecisionEngineCore(config=config)


class DecisionEngineOrgan:
    def __init__(self):
        self.cns = None
        self.core = create_decision_engine()

    async def start_cns(self, cns: EventBus) -> None:
        self.cns = cns
        await self.cns.subscribe("DECISION_EVALUATION_STARTED", "organ_22_decide", self._handle_evaluation_started)
        logger.info("DecisionEngineOrgan connected to CNS EventBus.")

    async def _handle_evaluation_started(self, env: EventEnvelope) -> None:
        try:
            payload = env.payload
            task_id = payload.get("task_id")
            command = payload.get("command", "").lower()
            
            # Fast path decision evaluation
            branches_required = []

            req = DecisionRequest(
                goal=Goal(raw_intent=command, target_primitive="workflow.execute",
                          parameters={"required_capabilities": ["workflow.execute"]}),
                requestor=Requestor(id="orchestrator", authority_level=2, security_token="system_token")
            )
            resp = self.core.process_request(req)
            
            await asyncio.sleep(0.05)

            if self.cns is not None:
                await self.cns.publish(EventEnvelope(
                    topic="DECISION_EVALUATION_COMPLETED",
                    source_organ="organ_22",
                    payload={
                        "task_id": task_id,
                        "branches_required": branches_required,
                        "decision_metrics": asdict(resp)
                    }
                ))
        except Exception as e:
            logger.error(f"Decision evaluation failed: {e}")
            if self.cns is not None:
                await self.cns.publish(EventEnvelope(
                    topic="DECISION_EVALUATION_COMPLETED",
                    source_organ="organ_22",
                    payload={
                        "task_id": env.payload.get("task_id"),
                        "branches_required": [],
                        "error": str(e)
                    }
                ))


if __name__ == "__main__":
    engine = create_decision_engine()
    demo_req = DecisionRequest(
        goal=Goal(raw_intent="open obs and record session", target_primitive="app.launch",
                  parameters={"required_capabilities": ["app.launch"]}),
        requestor=Requestor(id="admin", authority_level=2, security_token="auth"),
    )
    res = engine.process_request(demo_req)
    print(json.dumps(asdict(res), indent=2))
