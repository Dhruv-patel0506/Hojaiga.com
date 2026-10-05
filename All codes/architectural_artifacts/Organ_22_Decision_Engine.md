# Organ 22 — Decision Engine

**Authority:** Constitution → LawBook → PolicyManual → MasterArchitectureBlueprint → Organ Specification → DECISION_ENGINE.md
**Implementation:** `organ_22_decision_engine.py`

## Purpose
Deterministic, explainable, policy-compliant reasoning organ between Brain and Workflow Compiler. Evaluates capability, risk, confidence; selects strategy. Never executes side effects.

## Pre-Implementation Design Diagram
```
Brain --DecisionRequest--> DecisionCore
  GoalAnalyzer -> ContextAnalyzer -> ConstraintAnalyzer -> PolicyValidator
  -> CapabilityResolver -> ServiceResolver -> ConnectorResolver -> DependencyEvaluator
  -> AlternativeGenerator -> RiskAnalyzer -> ConfidenceEngine -> ScoringEngine
  -> StrategySelector -> DecisionValidator -> ExplanationGenerator
  -> DecisionSocketOut --ExecutionIntent--> Workflow Compiler
  -> HistorySocket (append-only, hash-chained)
```

## Actual Code Topology
```
organ_22_decision_engine.py
├── logging: _log() -> 8 structured JSON streams
├── enums: ConfidenceLevel, DecisionStatus
├── contracts: Requestor, Goal, DecisionRequest, ParsedGoal, NormalizedContext,
│              ConstraintMatrix, PolicyValidationResult, CandidateStrategy,
│              SelectedStrategy, DecisionResponse
├── config: ScoringWeights, ConfidenceThresholds, RiskCeilings, ConfigState
├── sockets: Socket, DecisionEngineSockets (11 typed sockets, retry/timeout bound)
├── analyzers: GoalAnalyzer, ContextAnalyzer, ConstraintAnalyzer, PolicyValidator
├── resolvers: CapabilityResolver, ServiceResolver, ConnectorResolver, DependencyEvaluator
├── AlternativeGenerator
├── RiskAnalyzer (9-domain composite: security/resource/dependency/failure/
│                 timeout/compatibility/plugin/external/hardware)
├── ConfidenceEngine (BaseScore * (1-Risk) * ContextClarity -> 5 levels)
├── DecisionScoringEngine (11-metric weighted sum, policy-gate to 0.0)
├── StrategySelector (threshold + human-approval escalation)
├── DecisionValidator (pre-flight + SHA-256 signature)
├── ExplanationGenerator (reason tree + rejected alternatives)
├── DecisionHistory (hash-chained append-only ledger)
└── DecisionEngineCore (orchestrator) -> create_decision_engine()
```

## Sockets (v1.0.0-aos)
| Socket | Dir | Timeout | Retry |
|---|---|---|---|
| DecisionSocketIn | in | 500ms | 3 |
| DecisionSocketOut | out | 200ms | 0 |
| ContextSocket | bi | 100ms | 2 |
| PolicySocket | out | 50ms | 1 |
| CapabilitySocket | bi | 100ms | 2 |
| ServiceSocket | bi | 100ms | 2 |
| RiskSocket / ScoringSocket | internal | 20ms | 0 |
| ValidationSocket | internal | 10ms | 0 |
| HistorySocket | out | 1000ms | 5 |
| MetricsSocket | out | 10ms | 0 |

Default handlers bind safe local fallbacks so the organ runs standalone; production wires real transports over the same `Socket.handler` contract without touching orchestration logic.

## Scoring Model
11 metrics (M_POL…M_SCL), default weights per Section 6, policy failure forces score 0.0 (hard reject). Composite risk = `1 - Π(1 - Rk·wk)` over 9 domains.

## Confidence Actions
- ≥0.90 VERY_HIGH: autonomous fast path
- ≥0.80 HIGH: autonomous, logged
- ≥0.60 MEDIUM: human approval if destructive
- ≥0.40 LOW: mandatory human approval
- <0.40 UNKNOWN: hard reject

## State & Recovery
Stateless per request except in-memory hash-chained `DecisionHistory`. All sub-module failures degrade to safe conservative defaults or hard-reject (no silent success). Socket failures raise `SocketError`, caught at each analyzer/resolver boundary.

## Testing
`python3 organ_22_decision_engine.py` — smoke test emits full DecisionResponse + structured audit logs to stderr.

## Extension Points
Swap `ScoringWeights`/`ConfidenceThresholds` via `reload_config`; replace `AlternativeGenerator` with LLM/Brain-driven candidate synthesis without touching scoring/policy/risk logic (per Section 19).
