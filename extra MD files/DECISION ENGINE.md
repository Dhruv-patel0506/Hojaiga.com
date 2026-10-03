# **DECISION ENGINE**

## **File: Decision\_Engine.md**

# **1\. OVERVIEW & PURPOSE**

The Decision Engine is the central reasoning, evaluation, and policy-enforcement organ of the Hojaiga Automation Operating System (AOS). It occupies a precise tier in the control architecture: directly below the **Brain** (which interprets intent) and directly above the **Workflow Compiler** (which synthesizes executable code).

                               \+-------------------+  
                                |       Brain       |  
                                \+---------+---------+  
                                          |  
                                 Decision Request  
                                          v  
                                \+-------------------+  
                                |  Decision Engine  |  
                                \+---------+---------+  
                                          |  
                                   Selected Plan  
                                          v  
                                \+-------------------+  
                                | Workflow Compiler |  
                                \+-------------------+

The Decision Engine is strictly deterministic, explainable, and policy-compliant. It does NOT execute workflows, schedule jobs, or invoke automation side-effects directly. Its sole domain is evaluating available system state, capabilities, constraints, and policies to select the optimal execution strategy, generate confidence scores, assign risk profiles, and maintain a tamper-proof audit log.

# **2\. HIGH-LEVEL ARCHITECTURE**

The Decision Engine processes incoming DecisionRequest payloads through a decoupled pipeline of evaluation engines, validators, and scoring modules.

\+----------------------------------------------------------------------------------------------------+  
|                                         DECISION ENGINE                                            |  
|                                                                                                    |  
|  \+-------------------+     \+--------------------+     \+-------------------+     \+------------------+  |  
|  |   Goal Analyzer   | \--\> |  Context Analyzer  | \--\> | Constraint/Policy | \--\> |    Capability    |  |  
|  |                   |     |                    |     |     Validator     |     |     Resolver     |  |  
|  \+-------------------+     \+--------------------+     \+-------------------+     \+--------+---------+  |  
|                                                                                          |         |  
|  \+-------------------+     \+--------------------+     \+-------------------+              |         |  
|  | Strategy Selector | \<-- |    Confidence &    | \<-- |   Risk Analyzer   | \<------------+         |  
|  |   & Explanation   |     |   Scoring Engine   |     |  & Alternatives   |                        |  
|  \+---------+---------+     \+--------------------+     \+-------------------+                        |  
\+------------|---------------------------------------------------------------------------------------+  
             v  
    Execution Intent / Selected Strategy  
             |  
             v  
  \+-------------------+  
  | Workflow Compiler |  
  \+-------------------+

# **3\. COMPLETE MODULE SPECIFICATIONS**

## **3.1 Decision Core (DecisionCore)**

* **Purpose:** Orchestrates the lifecycle of a decision request across all internal sub-modules.  
* **Responsibilities:** Receives raw request, instantiates pipeline context, enforces global timeouts, handles top-level panic recovery, emits final decision structure.  
* **Inputs:** DecisionRequest struct (Goal, Context Overrides, Constraints, Requestor Metadata).  
* **Outputs:** DecisionResponse struct (Selected Strategy, Alternatives, Metadata, Audit Hash).  
* **Dependencies:** ContextAnalyzer, PolicyValidator, CapabilityResolver, RiskAnalyzer, ScoringEngine, StrategySelector, DecisionHistory, MetricsCollector.  
* **Sockets:** DecisionSocketIn, DecisionSocketOut.  
* **Pipelines:** DecisionRequestPipeline.  
* **Failure Modes:** Timeout during sub-module evaluation, unhandled runtime exception, pipeline abort.  
* **Recovery:** Rollback to hardcoded safe fallback strategy or emit DECISION\_REJECTED response with diagnostic trace.  
* **Future Expansion:** Async multi-core parallel branch evaluation.

## **3.2 Goal Analyzer (GoalAnalyzer)**

* **Purpose:** Deconstructs high-level intent from the Brain into structured decision goals and tactical invariants.  
* **Responsibilities:** Validates syntax of input goals, extracts required outcomes, flags implicit constraints.  
* **Inputs:** UnparsedGoal string/object from Brain.  
* **Outputs:** ParsedGoal object with normalized target primitives, target metrics, and strict boundary conditions.  
* **Dependencies:** AOS\_Schema\_Registry.  
* **Sockets:** BrainInterfaceSocket.  
* **Pipelines:** DecisionRequestPipeline (Stage 1).  
* **Failure Modes:** Malformed goal schema, ambiguous intent.  
* **Recovery:** Reject decision request back to Brain with INVALID\_GOAL\_SCHEMA.  
* **Future Expansion:** Natural language parsing validation interface.

## **3.3 Context Analyzer (ContextAnalyzer)**

* **Purpose:** Aggregates real-time system state, environment telemetry, and user preferences.  
* **Responsibilities:** Queries systemic health, hardware capacity, network conditions, active user profiles, and past session variables.  
* **Inputs:** System State Telemetry, Environment Variables, User Session Data.  
* **Outputs:** NormalizedContext object containing resource availability vector, system thermal/load stats, user authority level.  
* **Dependencies:** System Telemetry Socket, User Preference Registry.  
* **Sockets:** ContextSocket.  
* **Pipelines:** ContextPipeline.  
* **Failure Modes:** Telemetry source offline, stale state cache.  
* **Recovery:** Fallback to safe conservative state defaults (e.g., assume 90% system load).  
* **Future Expansion:** Predictive load state modeling.

## **3.4 Constraint Analyzer (ConstraintAnalyzer)**

* **Purpose:** Extracts and parses hard boundaries from context, user settings, and execution bounds.  
* **Responsibilities:** Defines hard stop criteria (e.g., maximum memory allocation, latency caps, forbidden time windows).  
* **Inputs:** ParsedGoal, NormalizedContext.  
* **Outputs:** ConstraintMatrix (Set of boolean evaluation rules).  
* **Dependencies:** None.  
* **Sockets:** ContextSocket.  
* **Pipelines:** ContextPipeline (Stage 2).  
* **Failure Modes:** Conflicting constraints (un-satisfiable boundary).  
* **Recovery:** Issue CONSTRAINTS\_UNSATISFIABLE error and generate diagnostic report.  
* **Future Expansion:** Dynamic constraint relaxation algorithms.

## **3.5 Policy Validator (PolicyValidator)**

* **Purpose:** Enforces system-wide legal, governance, security, and founder laws.  
* **Responsibilities:** Verifies strict compliance against the Constitution, Universal LawBook, Founder Law, User Law, and Policy Manual hierarchy.  
* **Inputs:** ParsedGoal, ConstraintMatrix, Security Token.  
* **Outputs:** PolicyValidationResult (PASS/FAIL, Violated Policies List, Masked Scope).  
* **Dependencies:** Policy Engine Master Registry.  
* **Sockets:** PolicySocket.  
* **Pipelines:** ValidationPipeline.  
* **Failure Modes:** Policy database unreachable, security rule conflict.  
* **Recovery:** Hard fail to SECURITY\_REJECT. Block decision completely.  
* **Future Expansion:** Automated policy compliance proof generation.

## **3.6 Capability Resolver (CapabilityResolver)**

* **Purpose:** Maps goal requirements to available hardware and software capabilities.  
* **Responsibilities:** Queries the AOS Capability Registry to match required execution primitives with installed system traits.  
* **Inputs:** ParsedGoal, System Capability List.  
* **Outputs:** ResolvedCapabilitySet (Matching capabilities, Missing required capabilities).  
* **Dependencies:** CapabilityRegistry.  
* **Sockets:** CapabilitySocket.  
* **Pipelines:** CapabilityResolutionPipeline.  
* **Failure Modes:** Missing required capability primitive.  
* **Recovery:** Mark strategy path as unviable; drop candidates requiring missing traits.  
* **Future Expansion:** Dynamic plugin discovery and hot-loading capability checks.

## **3.7 Service Resolver (ServiceResolver)**

* **Purpose:** Resolves underlying system services required to fulfill identified capabilities.  
* **Responsibilities:** Validates service status, health checks, version compatibility, and IPC endpoint access.  
* **Inputs:** ResolvedCapabilitySet.  
* **Outputs:** ResolvedServiceMap (Service ID, Health Status, Response Latency, API Endpoint).  
* **Dependencies:** AOS Service Directory.  
* **Sockets:** ServiceSocket.  
* **Pipelines:** CapabilityResolutionPipeline (Stage 2).  
* **Failure Modes:** Target service unhealthy, degraded, or version-mismatched.  
* **Recovery:** Route to backup service instance or degrade capability tier.  
* **Future Expansion:** Microservice latency-aware auto-routing.

## **3.8 Connector Resolver (ConnectorResolver)**

* **Purpose:** Identifies external system integrations, APIs, and protocol adapters.  
* **Responsibilities:** Verifies credential availability, network connection status, rate-limit allowances, and connector health.  
* **Inputs:** ResolvedServiceMap.  
* **Outputs:** ResolvedConnectorSet (Active connectors, Token lifespans, Remaining quota).  
* **Dependencies:** Secret Storage / Key Vault, Network Monitor.  
* **Sockets:** ServiceSocket.  
* **Pipelines:** CapabilityResolutionPipeline (Stage 3).  
* **Failure Modes:** Expired OAuth tokens, network partition, rate limit reached.  
* **Recovery:** Flag connector as unavailable; filter out strategies reliant on it.  
* **Future Expansion:** Automated credential refresh integration.

## **3.9 Dependency Evaluator (DependencyEvaluator)**

* **Purpose:** Constructs Directed Acyclic Graphs (DAG) of capability, service, and data dependencies.  
* **Responsibilities:** Detects circular dependencies, verifies ordering constraints, determines execution prerequisite sequences.  
* **Inputs:** ResolvedCapabilitySet, ResolvedServiceMap, ResolvedConnectorSet.  
* **Outputs:** ValidDependencyGraph or DependencyError.  
* **Dependencies:** Graph processing utilities.  
* **Sockets:** None (Internal pipeline engine).  
* **Pipelines:** CapabilityResolutionPipeline (Stage 4).  
* **Failure Modes:** Circular dependency detected, missing intermediate asset.  
* **Recovery:** Reject specific candidate path; attempt alternative path synthesis.  
* **Future Expansion:** Real-time dependency graph optimization.

## **3.10 Risk Analyzer (RiskAnalyzer)**

* **Purpose:** Quantifies execution, security, hardware, and external risks across candidate strategies.  
* **Responsibilities:** Calculates cumulative risk index based on failure probability, system impact, data loss potential, and recovery complexity.  
* **Inputs:** Candidate Execution Paths, System Health, Dependency Graph.  
* **Outputs:** RiskAssessment (Overall Risk Score \[0.0 \- 1.0\], Vector of specific risk factors).  
* **Dependencies:** Risk Metrics Database, Vulnerability Scanner Feed.  
* **Sockets:** RiskSocket.  
* **Pipelines:** RiskAnalysisPipeline.  
* **Failure Modes:** Calculation overflow, unrated component encountered.  
* **Recovery:** Assign maximum conservative risk value (1.0) to unrated components.  
* **Future Expansion:** Real-time Bayesian risk estimation models.

## **3.11 Confidence Engine (ConfidenceEngine)**

* **Purpose:** Assigns categorical and numerical confidence ratings to strategies based on historical data and component health.  
* **Responsibilities:** Maps context clarity, capability health, and historical success rates into a final Confidence Level.  
* **Inputs:** RiskAssessment, System Telemetry, Historical Execution Metrics.  
* **Outputs:** ConfidenceScore (Float: 0.0 to 1.0, Level: VERY\_HIGH, HIGH, MEDIUM, LOW, UNKNOWN).  
* **Dependencies:** Decision History database.  
* **Sockets:** ScoringSocket.  
* **Pipelines:** ScoringPipeline.  
* **Failure Modes:** Historical database offline.  
* **Recovery:** Default to conservative calculation based strictly on live health stats (omit history).  
* **Future Expansion:** Machine-learning-based success forecasting.

## **3.12 Decision Scoring Engine (DecisionScoringEngine)**

* **Purpose:** Computes weighted mathematical scores for all candidate strategies.  
* **Responsibilities:** Combines Policy Compliance, Success Probability, Cost, Time, Reliability, Health, Security, and User Preference into a single final score.  
* **Inputs:** Strategy Options, Weighted Matrix Config, Risk Scores, Confidence Scores.  
* **Outputs:** ScoredStrategyList (Ranked array of strategies with itemized sub-scores).  
* **Dependencies:** Configuration Manager.  
* **Sockets:** ScoringSocket.  
* **Pipelines:** ScoringPipeline.  
* **Failure Modes:** Score tie, invalid configuration weights.  
* **Recovery:** Apply hardcoded tie-breaker precedence (Security \> Policy \> Cost \> Latency).  
* **Future Expansion:** Adaptive dynamic weight tuning based on user feedback.

## **3.13 Alternative Generator (AlternativeGenerator)**

* **Purpose:** Synthesizes non-primary candidate paths (e.g., fallback paths, low-resource paths, degraded modes).  
* **Responsibilities:** Modifies baseline variables to construct viable secondary and tertiary execution plans.  
* **Inputs:** ParsedGoal, ResolvedCapabilitySet.  
* **Outputs:** Array of CandidateStrategy objects.  
* **Dependencies:** Strategy Template Library.  
* **Sockets:** None (Internal pipeline engine).  
* **Pipelines:** DecisionPipeline.  
* **Failure Modes:** Unable to generate alternative options.  
* **Recovery:** Output single viable candidate or explicit fail state.  
* **Future Expansion:** Genetic algorithm strategy synthesis.

## **3.14 Strategy Selector (StrategySelector)**

* **Purpose:** Selects the winning strategy based on scoring, risk thresholds, and human-in-the-loop triggers.  
* **Responsibilities:** Validates winning score against minimum thresholds, handles escalation to human approval if required.  
* **Inputs:** ScoredStrategyList, System Configuration Thresholds.  
* **Outputs:** SelectedStrategy, HumanApprovalRequired flag.  
* **Dependencies:** None.  
* **Sockets:** DecisionSocketOut.  
* **Pipelines:** DecisionPipeline.  
* **Failure Modes:** Top strategy below minimum acceptable confidence threshold.  
* **Recovery:** Request human confirmation or issue NO\_VIABLE\_STRATEGY event.  
* **Future Expansion:** Dynamic human-in-the-loop routing based on real-time operator availability.

## **3.15 Decision Validator (DecisionValidator)**

* **Purpose:** Performs a final pre-flight verification on the selected decision before emission.  
* **Responsibilities:** Checks payload completeness, signature integrity, non-repudiation invariants, and target compiler readiness.  
* **Inputs:** SelectedStrategy, DecisionMetadata.  
* **Outputs:** ValidationResult (VALID / INVALID).  
* **Dependencies:** Security Cryptographic Module.  
* **Sockets:** ValidationSocket.  
* **Pipelines:** ValidationPipeline.  
* **Failure Modes:** Cryptographic signing failure, structural corruption.  
* **Recovery:** Abort decision, generate critical audit fault event.  
* **Future Expansion:** Formal verification of output intent contracts.

## **3.16 Explanation Generator (ExplanationGenerator)**

* **Purpose:** Generates human-readable and machine-auditable justifications for why a specific strategy was chosen.  
* **Responsibilities:** Compiles trade-off explanations, dropped alternative rationales, policy check traces, and score breakdowns.  
* **Inputs:** SelectedStrategy, ScoredStrategyList, RiskAssessment, PolicyValidationResult.  
* **Outputs:** Structured DecisionExplanation (Plain-text trace, Structured Reason Tree).  
* **Dependencies:** None.  
* **Sockets:** HistorySocket.  
* **Pipelines:** DecisionPipeline.  
* **Failure Modes:** Template formatting exception.  
* **Recovery:** Emit raw JSON log trace without formatted explanation.  
* **Future Expansion:** LLM-driven natural language decision reporting.

## **3.17 Decision History (DecisionHistory)**

* **Purpose:** Persists decisions, context vectors, and resulting execution outcomes for long-term auditability and learning.  
* **Responsibilities:** Implements append-only tamper-evident store of all system decisions.  
* **Inputs:** FinalDecisionRecord.  
* **Outputs:** Queryable record reference, historical metrics feed.  
* **Dependencies:** Local encrypted storage / SQLite DB.  
* **Sockets:** HistorySocket.  
* **Pipelines:** HistoryPipeline.  
* **Failure Modes:** Storage I/O failure, disk full.  
* **Recovery:** Write to emergency fallback ring-buffer memory; raise storage alert.  
* **Future Expansion:** Distributed ledger audit log sync.

## **3.18 Decision Metrics (DecisionMetrics)**

* **Purpose:** Tracks statistical performance of the Decision Engine.  
* **Responsibilities:** Measures decision latency, confidence drift, rejection rates, alternative selection frequency, and scoring variance.  
* **Inputs:** Pipeline execution events, time deltas.  
* **Outputs:** Prometheus-compatible metrics stream, performance traces.  
* **Dependencies:** AOS Monitoring Engine.  
* **Sockets:** MetricsSocket.  
* **Pipelines:** MetricsPipeline.  
* **Failure Modes:** Buffer overflow.  
* **Recovery:** Drop oldest metric points, keep operational engine uninterrupted.  
* **Future Expansion:** Automated latency optimization alerts.

## **3.19 Configuration Interface (ConfigurationInterface)**

* **Purpose:** Manages operational parameters, scoring weights, risk ceilings, and confidence rules.  
* **Responsibilities:** Parses and validates decision\_config.toml updates at runtime without restarting the engine.  
* **Inputs:** Configuration file modifications, administrative override calls.  
* **Outputs:** Live ConfigState instance.  
* **Dependencies:** File system watcher.  
* **Sockets:** Administrative Management Socket.  
* **Pipelines:** Internal config sync.  
* **Failure Modes:** Syntax error in config file.  
* **Recovery:** Reject config change; retain previous active configuration state in memory.  
* **Future Expansion:** Remote secure config pushing.

## **3.20 Recovery Manager (RecoveryManager)**

* **Purpose:** Handles internal failures, execution exceptions, and degraded operation modes within the Decision Engine itself.  
* **Responsibilities:** Monitors internal pipeline timeouts, restores fallback configurations, resets degraded memory structures.  
* **Inputs:** Engine runtime panic events, module error signals.  
* **Outputs:** Pipeline recovery directives, safe system fallback states.  
* **Dependencies:** AOS Core Watchdog.  
* **Sockets:** System Control Socket.  
* **Pipelines:** Internal recovery routing.  
* **Failure Modes:** Complete internal deadlock.  
* **Recovery:** Trigger hard sub-system engine restart and drop back to safe hardware fallback state.  
* **Future Expansion:** Self-healing internal node re-instantiation.

# **4\. DECISION TYPES**

The Decision Engine processes fifteen distinct operational decision domains:

                 \+----------------------------------------------+  
                  |               DECISION TYPES                 |  
                  \+----------------------+-----------------------+  
                                         |  
     \+-----------------------------------+-----------------------------------+  
     |                                   |                                   |  
\[System & Infrastructure\]         \[Strategy & Execution\]            \[Governance & Safety\]  
  \* Capability Selection            \* Workflow Strategy               \* Security Decision  
  \* Service Selection               \* Recovery Strategy               \* User Confirmation Decision  
  \* Connector Selection             \* Retry Strategy                  \* Automation Decision  
  \* Plugin Selection                \* Fallback Strategy               \* Learning Decision  
  \* Resource Strategy               \* Optimization Strategy

1. **Capability Selection:** Selects required high-level operations (e.g., IMAGE\_PROCESSING, LOCAL\_LLM\_INFERENCE).  
2. **Service Selection:** Chooses specific local or remote services to execute selected capabilities.  
3. **Connector Selection:** Identifies specific protocol adapters, API routes, or hardware interfaces.  
4. **Plugin Selection:** Dynamically resolves third-party code modules or extension binaries.  
5. **Workflow Strategy:** Decides topology of task execution (Sequential, Parallel, DAG Branching).  
6. **Recovery Strategy:** Formulates actions following an external system fault.  
7. **Retry Strategy:** Determines backoff algorithm, max attempts, and jitter parameters for failed steps.  
8. **Fallback Strategy:** Chooses degraded or alternative pathways when preferred capabilities are down.  
9. **Optimization Strategy:** Balances speed vs. resource usage vs. cost based on active directives.  
10. **Resource Strategy:** Allocates specific RAM, GPU VRAM, CPU cores, and thread pools.  
11. **Security Decision:** Evaluates elevated permission requests, cryptographic checks, and sandbox constraints.  
12. **User Confirmation Decision:** Determines if an action carries sufficient risk to require human intervention.  
13. **Automation Decision:** Decides whether a step should execute autonomously or await trigger verification.  
14. **Learning Decision:** Decides whether to persist execution telemetry into local training data stores.

# **5\. DECISION PROCESS LIFECYCLE**

\[Brain / System Request\]  
          |  
          v  
\+-------------------+  
|   Goal Received   |  
\+---------+---------+  
          |  
          v  
\+-------------------+  
| Context Collection|  \<-- Telemetry, Hardware State, User Prefs  
\+---------+---------+  
          |  
          v  
\+-------------------+  
| Policy Validation |  \<-- Constitution, Laws, Authority Check  
\+---------+---------+  
          |  
          v  
\+-------------------+  
|Capability Discovery| \<-- Capabilities, Services, Connectors  
\+---------+---------+  
          |  
          v  
\+-------------------+  
|Alternative Gen.   |  \<-- Synthesize Candidate Plan A, B, C  
\+---------+---------+  
          |  
          v  
\+-------------------+  
|   Risk Analysis   |  \<-- Evaluate Failure Prob, Security Risk  
\+---------+---------+  
          |  
          v  
\+-------------------+  
| Decision Scoring  |  \<-- Weighted Matrix Evaluation  
\+---------+---------+  
          |  
          v  
\+-------------------+  
| Best Strategy Sel.|  \<-- Check Thresholds, Confidence Level  
\+---------+---------+  
          |  
          v  
\+-------------------+  
|Decision Validation|  \<-- Sign Metadata, Final Verification  
\+---------+---------+  
          |  
          v  
\[Decision Published\] \--\> \[Workflow Compiler\]

# **6\. DECISION SCORING ENGINE**

The Decision Scoring Engine ranks candidate strategies using a normalized weighted summation model:

$$\\text{Final Score} \= \\sum\_{i=1}^{11} \\left( W\_i \\times S\_i \\right)$$  
Where $W\_i$ represents the normalized weight ($\\sum W\_i \= 1.0$) and $S\_i$ represents the sub-score calculated for each metric ($0.0 \\le S\_i \\le 1.0$).

| Metric Key (i) | Metric Name | Description / Evaluation Criteria | Default Weight (W) |
| :---- | :---- | :---- | :---- |
| M\_POL | Policy Compliance | Binary or granular match with active security policies and law hierarchy. Violations result in strategy drop ($S \= 0.0$). | 0.20 |
| M\_PRB | Success Probability | Historical run success rates combined with real-time component health checks. | 0.15 |
| M\_SEC | Security Score | Sandboxing depth, vulnerability surface area, and privilege level requirements. | 0.15 |
| M\_REL | Reliability | Mean Time Between Failures (MTBF) of chosen services and connectors. | 0.10 |
| M\_HLT | Health Status | Real-time operational telemetry (CPU load, thermal headroom, network drop rate). | 0.10 |
| M\_CST | Resource Cost | Monetary or computational expense (API costs, token costs, watt energy usage). | 0.05 |
| M\_TIM | Execution Time | Projected latency from start to terminal output. | 0.05 |
| M\_PRF | User Preferences | Explicit alignment with user-configured priority vectors (e.g., "prefer local LLM"). | 0.05 |
| M\_HIS | Historical Success | Tailored success rate metric specific to identical context inputs in the past. | 0.05 |
| M\_HW | Hardware Match | Direct affinity to available acceleration hardware (NPU, CUDA, AVX-512). | 0.05 |
| M\_SCL | Scalability | Capability to process concurrent execution without performance degradation. | 0.05 |

# **7\. CONFIDENCE MODEL**

The Confidence Engine processes calculated metrics to assign a categorical level and threshold action:

Score: 0.00         0.40         0.60         0.80         0.90         1.00  
Level:  |-- UNKNOWN \--|--- LOW \---|-- MEDIUM \--|--- HIGH \---|- VERY HIGH \-|  
Action: \[  REJECT   \] \[HUMAN REQ\] \[WARN/EXEC\]  \[ AUTO EXEC \] \[ FAST AUTO \]

| Confidence Level | Score Threshold | System Action / Fallback Behavior | Human Approval Requirement |
| :---- | :---- | :---- | :---- |
| **Very High** | $\\ge 0.90$ | Automatic, immediate execution via Workflow Compiler. Fast path. | None. Fully autonomous. |
| **High** | $0.80 \\le \\text{Score} \< 0.90$ | Automatic execution with full audit logging and diagnostic trace. | None. Autonomous. |
| **Medium** | $0.60 \\le \\text{Score} \< 0.80$ | Execution allowed if non-destructive. Fallback strategy pre-compiled. | Required if action impacts persistent state or network. |
| **Low** | $0.40 \\le \\text{Score} \< 0.60$ | Execution blocked by default. System generates diagnostic report. | **Mandatory.** Interactive confirmation requested. |
| **Unknown** | $\< 0.40$ | Absolute rejection. Pipeline safe-stop triggered. | Rejected outright. Approval disabled. |

### **Calculation Factors**

$$\\text{Confidence} \= \\text{BaseScore} \\times (1.0 \- \\text{TotalRisk}) \\times \\text{ContextClarityFactor}$$  
Where $\\text{ContextClarityFactor}$ represents the completeness of available context vectors ($1.0 \= \\text{complete data}$, $0.5 \= \\text{degraded context}$).

# **8\. RISK ANALYSIS MODEL**

The Risk Analyzer calculates a composite Risk Index across nine domains ($R\_k \\in \[0.0, 1.0\]$):

                      \+-----------------------------------+  
                       |        COMPOSITE RISK INDEX       |  
                       \+-----------------+-----------------+  
                                         |  
     \+-----------------------------------+-----------------------------------+  
     |                                   |                                   |  
\[System & Security\]                 \[Operational\]                     \[Hardware & External\]  
  \* Security Risk                     \* Dependency Risk                 \* External API Risk  
  \* Hardware Risk                     \* Failure Probability             \* Plugin Risk  
                                      \* Timeout Risk  
                                      \* Compatibility Risk

$$\\text{Composite Risk} \= 1.0 \- \\prod\_{k=1}^{9} (1.0 \- R\_k \\times w\_k)$$

1. **Security Risk ($R\_{\\text{SEC}}$):** Probability of boundary violation or privilege escalation.  
2. **Resource Risk ($R\_{\\text{RES}}$):** Probability of memory exhaustion, thrashing, or OOM killing.  
3. **Dependency Risk ($R\_{\\text{DEP}}$):** Likelihood of downstream dependency failure or structural breaking changes.  
4. **Failure Probability ($R\_{\\text{FLR}}$):** Historical failure rate under similar context parameters.  
5. **Timeout Risk ($R\_{\\text{TMO}}$):** Projected latency exceeding system hard timeout ceilings.  
6. **Compatibility Risk ($R\_{\\text{CMP}}$):** Mismatch between binary interfaces, schemas, or API versions.  
7. **Plugin Risk ($R\_{\\text{PLG}}$):** Unverified third-party code execution risk.  
8. **External API Risk ($R\_{\\text{EXT}}$):** Remote rate limits, network latency, connection resets.  
9. **Hardware Risk ($R\_{\\text{HDW}}$):** Thermal throttling state, disk write endurance, power delivery stability.

# **9\. VALIDATION MATRIX**

Every selected decision must pass the validation matrix prior to release to the Workflow Compiler:

\+---------------------------------------------------------------------------------+  
|                               VALIDATION MATRIX                                 |  
\+---------------------+-----------------------------------+-----------------------+  
| Validation Category | Evaluation Check                  | On Failure Action     |  
\+---------------------+-----------------------------------+-----------------------+  
| Policies            | Constitutional / Law Alignment    | Hard Reject           |  
| Permissions         | Token Cryptographic Validity      | Security Halt         |  
| Capabilities        | Physical Feature Existence        | Strategy Drop         |  
| Dependencies        | Unmet Pre-requisites              | Route to Alternative  |  
| Resources           | Hardware Headroom Availability    | Enforce Queue/Wait    |  
| Configuration       | System Parameter Range Bounds     | Apply Defaults        |  
| Version             | Schema Compatibility Check        | Re-compile Request    |  
| Security            | Integrity & Tamper Check          | Quarantine Engine     |  
| System State        | Thermal / Stability State Bounds  | Degraded Execution    |  
\+---------------------+-----------------------------------+-----------------------+

# **10\. SOCKET SPECIFICATIONS**

Communication into and out of the Decision Engine uses strict typed asynchronous sockets.

\+-------------------------------------------------------------------------------------------------------------+  
|                                              SOCKET SPECIFICATION                                           |  
\+--------------------+-----------+--------------------+---------------------+---------+-------+---------------+  
| Socket Name        | Direction | Auth Protocol      | Validation Schema   | Timeout | Retry | Version Tag   |  
\+--------------------+-----------+--------------------+---------------------+---------+-------+---------------+  
| DecisionSocketIn   | Input     | Mutual TLS / HMAC  | DecisionRequest.json| 500ms   | 3x    | v1.0.0-aos    |  
| DecisionSocketOut  | Output    | Internal IPC / Shared Mem | ExecutionIntent.json | 200ms | 0x    | v1.0.0-aos    |  
| ContextSocket      | Bi-Dir    | IPC Token          | ContextVector.json  | 100ms   | 2x    | v1.0.0-aos    |  
| PolicySocket       | Output    | Signed Kernel Bus  | PolicyCheck.json    | 50ms    | 1x    | v1.0.0-aos    |  
| CapabilitySocket   | Bi-Dir    | IPC Token          | CapabilityQuery.json| 100ms   | 2x    | v1.0.0-aos    |  
| ServiceSocket      | Bi-Dir    | IPC Token          | ServiceState.json   | 100ms   | 2x    | v1.0.0-aos    |  
| RiskSocket         | Internal  | Direct Memory Path | RiskVector.json     | 20ms    | 0x    | v1.0.0-aos    |  
| ScoringSocket      | Internal  | Direct Memory Path | ScoreMatrix.json    | 20ms    | 0x    | v1.0.0-aos    |  
| ValidationSocket   | Internal  | Direct Memory Path | ValidReport.json    | 10ms    | 0x    | v1.0.0-aos    |  
| HistorySocket      | Output    | Encrypted Local Bus| AuditRecord.json    | 1000ms  | 5x    | v1.0.0-aos    |  
| MetricsSocket      | Output    | Unauthenticated UDP| Prometheus Metric   | 10ms    | 0x    | v1.0.0-aos    |  
\+--------------------+-----------+--------------------+---------------------+---------+-------+---------------+

# **11\. PIPELINE DESCRIPTIONS**

                     \+------------------------------------------+  
                      |         DECISION ENGINE PIPELINES        |  
                      \+--------------------+---------------------+  
                                           |  
     \+-------------------------------------+-------------------------------------+  
     |                                     |                                     |  
\[Core Execution\]                      \[Analysis & Scoring\]                 \[System & Metrics\]  
  \* Decision Request Pipeline           \* Context Pipeline                   \* History Pipeline  
  \* Decision Pipeline                   \* Validation Pipeline                \* Metrics Pipeline  
                                        \* Capability Resolution Pipeline  
                                        \* Risk Analysis Pipeline  
                                        \* Scoring Pipeline

### **11.1 Decision Request Pipeline**

* **Source:** Brain / External Trigger.  
* **Destination:** Goal Analyzer / Decision Core.  
* **Payload:** DecisionRequestStruct (Goal ID, Brain Context, Intent Data).  
* **Validation:** CRC32 Checksum \+ Schema Validation.  
* **Retry:** 3 attempts backoff.  
* **Timeout:** 500ms.  
* **Recovery:** Emit BAD\_REQUEST\_FORMAT to Brain.

### **11.2 Context Pipeline**

* **Source:** Context Analyzer.  
* **Destination:** Constraint Analyzer & Policy Validator.  
* **Payload:** AggregatedContextPayload (System State, Active Constraints).  
* **Validation:** Bounds Check on State Attributes.  
* **Retry:** 2 attempts.  
* **Timeout:** 100ms.  
* **Recovery:** Inject safe baseline context vector.

### **11.3 Validation Pipeline**

* **Source:** Policy Validator.  
* **Destination:** Capability Resolver / Strategy Selector.  
* **Payload:** PolicyValidationResultPayload.  
* **Validation:** Cryptographic Policy Ledger Proof.  
* **Retry:** 0 (Immediate fail).  
* **Timeout:** 50ms.  
* **Recovery:** Abort request, notify System Security Organ.

### **11.4 Capability Resolution Pipeline**

* **Source:** Capability Resolver.  
* **Destination:** Alternative Generator.  
* **Payload:** CapabilityMapPayload.  
* **Validation:** Registry Availability Verification.  
* **Retry:** 2 attempts.  
* **Timeout:** 150ms.  
* **Recovery:** Strip unresolvable optional capabilities; proceed with baseline minimum.

### **11.5 Risk Analysis Pipeline**

* **Source:** Risk Analyzer.  
* **Destination:** Scoring Engine.  
* **Payload:** RiskAssessmentVector.  
* **Validation:** Float Range Validation ($0.0 \\le R \\le 1.0$).  
* **Retry:** 0\.  
* **Timeout:** 30ms.  
* **Recovery:** Apply maximum risk rating.

### **11.6 Scoring Pipeline**

* **Source:** Scoring Engine.  
* **Destination:** Strategy Selector.  
* **Payload:** RankedStrategyPayload.  
* **Validation:** Summation Verification.  
* **Retry:** 0\.  
* **Timeout:** 30ms.  
* **Recovery:** Use simple non-weighted policy-first precedence.

### **11.7 Decision Pipeline**

* **Source:** Strategy Selector.  
* **Destination:** Workflow Compiler (via DecisionSocketOut).  
* **Payload:** ExecutionIntentPayload (Selected Plan, Confidence, Audit Token).  
* **Validation:** Output JSON Schema \+ Cryptographic Signature.  
* **Retry:** 1 attempt.  
* **Timeout:** 200ms.  
* **Recovery:** Abort execution; trigger fallback decision request.

### **11.8 History Pipeline**

* **Source:** Decision Core.  
* **Destination:** Decision History Store.  
* **Payload:** EncryptedAuditRecord.  
* **Validation:** SHA-256 Hash Ring Integrity Check.  
* **Retry:** 5 attempts with background retry queue.  
* **Timeout:** Non-blocking async write (1000ms).  
* **Recovery:** Spool to local emergency disk cache.

### **11.9 Metrics Pipeline**

* **Source:** Pipeline Metrics Hooks.  
* **Destination:** Local Metrics Engine.  
* **Payload:** MetricDatapoint.  
* **Validation:** None.  
* **Retry:** 0 (Fire-and-forget).  
* **Timeout:** 10ms.  
* **Recovery:** Drop metric point.

# **12\. SECURITY ARCHITECTURE**

\+-----------------------------------------------------------------------------------+  
|                               SECURITY ARCHITECTURE                               |  
\+--------------------+--------------------------------------------------------------+  
| Security Feature   | Implementation Details                                       |  
\+--------------------+--------------------------------------------------------------+  
| Authorization      | Token-based Capability Allocation using Ed25519 signatures. |  
| Policy Enforcement | Immutable inline Policy Engine check prior to candidate gen. |  
| Integrity Checks   | SHA-256 hashing of all decision payload inputs and outputs.   |  
| Anti-Tamper       | Ephemeral state verification prevents memory patching.       |  
| Secure Storage     | AES-256-GCM encryption for stored decision history records.  |  
| Audit Logging      | Append-only Merkle-tree structured audit logging engine.     |  
\+--------------------+--------------------------------------------------------------+

# **13\. LOGGING & AUDIT SUBSYSTEM**

The Decision Engine emits standardized structured JSON log frames across eight log streams:

JSON  
{  
  "timestamp": "2026-08-07T13:21:42.104Z",  
  "decision\_id": "dec\_8f9a2b1c4e6d",  
  "trace\_id": "tr\_001928374651",  
  "log\_stream": "DECISION\_AUDIT",  
  "log\_level": "INFO",  
  "module": "StrategySelector",  
  "payload": {  
    "selected\_strategy\_id": "strat\_local\_gpu\_v2",  
    "confidence\_score": 0.942,  
    "confidence\_level": "VERY\_HIGH",  
    "policy\_check": "PASSED",  
    "risk\_index": 0.041,  
    "winning\_score": 0.887,  
    "execution\_intent": "COMPILE\_WORKFLOW\_DAG",  
    "hash\_signature": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  
  }  
}

### **Log Streams**

1. DECISION\_LOGS: High-level incoming requests and output execution intent events.  
2. CONTEXT\_LOGS: System state inputs, telemetry snapshots, and user preference inputs.  
3. VALIDATION\_LOGS: Traces of policy and legal compliance checks.  
4. RISK\_LOGS: Detailed component risk factor breakdowns.  
5. SCORING\_LOGS: Granular mathematical score matrices for all evaluated candidates.  
6. HISTORY\_LOGS: Long-term records stored for regression analysis and learning.  
7. AUDIT\_LOGS: Security-critical events, permission checks, and override tracking.  
8. PERFORMANCE\_METRICS: Execution latencies of individual pipeline stages.

# **14\. CONFIGURATION SCHEME**

The Decision Engine is configured via decision\_config.toml. Dynamic reload is supported without component teardown.

Ini, TOML  
\[engine\]  
version \= "1.0.0-aos"  
environment \= "production"  
max\_decision\_latency\_ms \= 500  
fallback\_on\_timeout \= true

\[scoring.weights\]  
policy\_compliance \= 0.20  
success\_probability \= 0.15  
security\_score \= 0.15  
reliability \= 0.10  
health\_status \= 0.10  
resource\_cost \= 0.05  
execution\_time \= 0.05  
user\_preferences \= 0.05  
historical\_success \= 0.05  
hardware\_match \= 0.05  
scalability \= 0.05

\[confidence.thresholds\]  
very\_high \= 0.90  
high \= 0.80  
medium \= 0.60  
low \= 0.40  
human\_approval\_required\_below \= 0.80

\[risk.ceilings\]  
max\_allowed\_composite\_risk \= 0.65  
max\_allowed\_security\_risk \= 0.10  
max\_allowed\_hardware\_risk \= 0.80

\[cache\]  
enabled \= true  
max\_entries \= 10000  
ttl\_seconds \= 300

\[logging\]  
level \= "INFO"  
audit\_encryption \= "AES-256-GCM"  
export\_prometheus \= true

# **15\. MERMAID DIAGRAMS**

## **15.1 Overall Decision Engine Architecture**

Code snippet  
graph TD  
    SubGraphBrain\[Brain\] \--\>|DecisionRequest| DecisionCore\[Decision Core\]  
      
    subgraph DecisionEngine \[Decision Engine Organ\]  
        DecisionCore \--\> GoalAnalyzer\[Goal Analyzer\]  
        GoalAnalyzer \--\> ContextAnalyzer\[Context Analyzer\]  
        ContextAnalyzer \--\> PolicyValidator\[Policy Validator\]  
        PolicyValidator \--\> CapabilityResolver\[Capability Resolver\]  
          
        CapabilityResolver \--\> ServiceResolver\[Service Resolver\]  
        ServiceResolver \--\> ConnectorResolver\[Connector Resolver\]  
        ConnectorResolver \--\> DependencyEvaluator\[Dependency Evaluator\]  
          
        DependencyEvaluator \--\> AlternativeGen\[Alternative Generator\]  
        AlternativeGen \--\> RiskAnalyzer\[Risk Analyzer\]  
        RiskAnalyzer \--\> ConfidenceEngine\[Confidence Engine\]  
          
        ConfidenceEngine \--\> ScoringEngine\[Scoring Engine\]  
        ScoringEngine \--\> StrategySelector\[Strategy Selector\]  
        StrategySelector \--\> DecisionValidator\[Decision Validator\]  
        DecisionValidator \--\> ExplanationGen\[Explanation Generator\]  
    end

    ExplanationGen \--\>|ExecutionIntent| WorkflowCompiler\[Workflow Compiler\]  
    DecisionValidator \--\>|Audit Payload| DecisionHistory\[(Decision History DB)\]  
    DecisionCore \--\>|Telemetry| DecisionMetrics\[Decision Metrics\]

## **15.2 Decision Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant B as Brain  
    participant DE as Decision Core  
    participant CA as Context & Policy  
    participant CR as Capability Resolver  
    participant SE as Scoring & Risk  
    participant WC as Workflow Compiler

    B-\>\>DE: Submit DecisionRequest  
    DE-\>\>CA: Fetch Context & Validate Laws  
    CA--\>\>DE: Context OK & Policy PASS  
    DE-\>\>CR: Resolve Capabilities & Services  
    CR--\>\>DE: Viable Capability Graph  
    DE-\>\>SE: Evaluate Risks & Score Candidates  
    SE--\>\>DE: Scored Strategy Vector \+ Confidence  
    DE-\>\>DE: Perform Final Decision Validation  
    DE-\>\>WC: Emit ExecutionIntent / Selected Strategy  
    DE-\>\>B: Return Decision Summary Response

## **15.3 Context Analysis**

Code snippet  
flowchart LR  
    A\[Raw System Telemetry\] \--\> ContextAnalyzer  
    B\[User Profile & Prefs\] \--\> ContextAnalyzer  
    C\[Active Hardware Load\] \--\> ContextAnalyzer  
      
    ContextAnalyzer \--\> D{Constraint Check}  
    D \-- Pass \--\> E\[Normalized Context Vector\]  
    D \-- Fail \--\> F\[Inject Conservative State Defaults\]  
    F \--\> E

## **15.4 Scoring Pipeline**

Code snippet  
flowchart TD  
    Candidate\[Candidate Strategy\] \--\> PolicyEval\[Policy Compliance Evaluator\]  
    Candidate \--\> PerfEval\[Performance & Latency Model\]  
    Candidate \--\> CostEval\[Resource Cost Model\]  
    Candidate \--\> HistEval\[History Metrics Engine\]

    PolicyEval \--\> WeightSum\[Weighted Summation Matrix\]  
    PerfEval \--\> WeightSum  
    CostEval \--\> WeightSum  
    HistEval \--\> WeightSum

    WeightSum \--\> FinalScore\[Final Strategy Score: 0.0 \- 1.0\]

## **15.5 Risk Analysis**

Code snippet  
flowchart TD  
    Strat\[Candidate Strategy\] \--\> SecRisk\[Security Risk Check\]  
    Strat \--\> DepRisk\[Dependency Topology Check\]  
    Strat \--\> HwRisk\[Hardware Thermal/Load Check\]

    SecRisk \--\> Matrix\[Risk Matrix Synthesizer\]  
    DepRisk \--\> Matrix  
    HwRisk \--\> Matrix

    Matrix \--\> CompositeScore\[Composite Risk Index Calculation\]

## **15.6 Alternative Evaluation**

Code snippet  
flowchart TD  
    Goal\[Goal Input\] \--\> Primary\[Synthesize Primary Strategy A\]  
    Goal \--\> AltB\[Synthesize Alternative B \- Low Resource\]  
    Goal \--\> AltC\[Synthesize Alternative C \- Fallback Mode\]

    Primary \--\> Evaluator\[Scoring & Risk Engine\]  
    AltB \--\> Evaluator  
    AltC \--\> Evaluator

    Evaluator \--\> Ranker\[Rank Strategy Results\]  
    Ranker \--\> Win\[Select Highest Score Above Threshold\]

## **15.7 Decision Lifecycle**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Received  
    Received \--\> Contextualizing  
    Contextualizing \--\> ValidatingPolicy  
    ValidatingPolicy \--\> CapabilityResolving  
    CapabilityResolving \--\> ScoringAndRisk  
    ScoringAndRisk \--\> StrategySelected  
    StrategySelected \--\> ValidatingOutput  
    ValidatingOutput \--\> Published  
    Published \--\> \[\*\]

    ValidatingPolicy \--\> Rejected: Policy Violation  
    ScoringAndRisk \--\> Rejected: Confidence Below Threshold  
    ValidatingOutput \--\> Rejected: Validation Fault  
    Rejected \--\> \[\*\]

## **15.8 Deployment Diagram**

Code snippet  
graph TB  
    subgraph AOS Core Host  
        subgraph Decision Engine Process Space  
            Core\[Decision Core Subsystem\]  
            MemCache\[In-Memory Decision Cache\]  
            Sockets\[IPC Socket Handlers\]  
        end  
          
        subgraph Storage Tier  
            DB\[(Encrypted SQLite Audit DB)\]  
            ConfigFS\[decision\_config.toml\]  
        end  
    end

    Sockets \<--\>|IPC Shared Memory| Compiler\[Workflow Compiler Daemon\]  
    Sockets \<--\>|Local TLS Unix Socket| Brain\[Brain Process\]  
    ConfigFS \--\> Core  
    Core \--\> DB

## **15.9 Folder Diagram**

decision\_engine/  
├── docs/  
├── config/  
├── src/  
│   ├── core/  
│   ├── analyzers/  
│   ├── validators/  
│   ├── resolvers/  
│   ├── scoring/  
│   ├── history/  
│   ├── sockets/  
│   └── pipelines/  
└── tests/

# **16\. ASCII DIAGRAMS**

## **16.1 Complete Decision Engine Architecture**

\+---------------------------------------------------------------------------------------------------+  
|                                      DECISION ENGINE SYSTEM                                       |  
|                                                                                                   |  
|  \[ Brain Request \]                                                                                |  
|         |                                                                                         |  
|         v                                                                                         |  
|  \+--------------+     \+-------------------+     \+------------------+     \+---------------------+  |  
|  | Decision Core| \--\> | Context Analyzer  | \--\> | Policy Validator | \--\> | Capability Resolver |  |  
|  \+--------------+     \+-------------------+     \+------------------+     \+---------------------+  |  
|                                                                                     |             |  
|  \+--------------+     \+-------------------+     \+------------------+                |             |  
|  | Output Intent| \<-- | Strategy Selector | \<-- |  Scoring & Risk  | \<--------------+             |  
|  \+--------------+     \+-------------------+     \+------------------+                              |  
|         |                                                                                         |  
|         v                                                                                         |  
|  \[ Workflow Compiler \]                                                                            |  
\+---------------------------------------------------------------------------------------------------+

## **16.2 Decision Pipeline**

Request \---\> \[Goal Extraction\] \---\> \[Context Stitching\] \---\> \[Policy Screening\]  
                                                                   |  
                                                                   v  
Response \<--- \[Metadata Sign\] \<--- \[Strategy Select\] \<--- \[Scoring & Risk Engine\]

## **16.3 Scoring Flow**

Candidate Plan \---\> ( Policy Metric  \* 0.20 ) \--+  
               \---\> ( Success Metric \* 0.15 ) \--|  
               \---\> ( Security Metric\* 0.15 ) \--|---\> \[ SUMMATION \] \---\> Final Strategy Score  
               \---\> ( Resource Metric\* 0.05 ) \--|  
               \---\> ( Time Metric     \* 0.05 ) \--+

## **16.4 Risk Evaluation**

              \+---\> Security Risk Factor    (Weight: 0.25) \--+  
               |                                              |  
Candidate Path \+---\> Hardware Thermal Factor (Weight: 0.15) \--+---\> \[ COMPOSITE RISK \]  
               |                                              |  
               \+---\> External API Factor     (Weight: 0.10) \--+

## **16.5 Alternative Selection**

                 \+---\> Candidate Strategy A (Primary)    \--\> Score: 0.88 (SELECTED)  
                  |  
Goal Input Matrix \+---\> Candidate Strategy B (Degraded)   \--\> Score: 0.72 (ALTERNATIVE)  
                  |  
                  \+---\> Candidate Strategy C (Low-Resource)--\> Score: 0.54 (FALLBACK)

## **16.6 Decision Lifecycle**

\[RECEIVED\] \---\> \[CONTEXT\_COLLECTED\] \---\> \[POLICY\_PASSED\] \---\> \[SCORED\] \---\> \[PUBLISHED\]  
      |                 |                    |                    |  
      \+-----------------+--------------------+--------------------+---\> \[REJECTED\]

## **16.7 Component Interaction**

 \+-------+             \+-----------------+             \+-------------------+  
  | Brain |             | Decision Engine |             | Workflow Compiler |  
  \+---+---+             \+--------+--------+             \+---------+---------+  
      |                          |                                |  
      |--- DecisionRequest \-----\>|                                |  
      |                          |--- Process Pipeline \-----------|  
      |                          |                                |  
      |                          |--- ExecutionIntent \------------\>|  
      |\<-- Decision Response \----|                                |

## **16.8 Context Flow**

\[Raw System Telemetry\] \----+  
                           v  
\[User Preferences Settings\] \--\> \[ Context Analyzer \] \---\> \[ Normalized Context Vector \]  
                           ^  
\[Hardware State & Thermals\]-+

# **17\. FOLDER STRUCTURE**

decision\_engine/  
├── README.md  
├── Cargo.toml / package.json  
├── config/  
│   ├── decision\_config.toml            \# Engine parameters and weights  
│   ├── policy\_rules.json               \# Hardcoded runtime policy bindings  
│   └── scoring\_matrices.json           \# Scoring coefficients  
├── docs/  
│   ├── Decision\_Engine.md              \# System Architecture Specification  
│   └── API\_SPECIFICATION.md            \# Socket and pipeline API references  
├── src/  
│   ├── main.rs / index.ts              \# Entry point daemon  
│   ├── core/  
│   │   ├── mod.rs                      \# Core module exports  
│   │   ├── decision\_core.rs            \# Lifecycle master orchestrator  
│   │   ├── engine\_state.rs             \# Internal runtime state  
│   │   └── recovery\_manager.rs         \# Recovery and fault-handling engine  
│   ├── analyzers/  
│   │   ├── goal\_analyzer.rs            \# Brain goal deconstructors  
│   │   ├── context\_analyzer.rs         \# Real-time state collector  
│   │   ├── constraint\_analyzer.rs      \# Hard boundary calculator  
│   │   └── risk\_analyzer.rs            \# Multi-vector risk calculator  
│   ├── validators/  
│   │   ├── policy\_validator.rs         \# Constitution/Law hierarchy checker  
│   │   └── decision\_validator.rs       \# Pre-flight output verifier  
│   ├── resolvers/  
│   │   ├── capability\_resolver.rs      \# System capability resolver  
│   │   ├── service\_resolver.rs         \# System service router  
│   │   ├── connector\_resolver.rs       \# External integration verifier  
│   │   └── dependency\_evaluator.rs     \# DAG dependency validator  
│   ├── scoring/  
│   │   ├── scoring\_engine.rs           \# Weighted summation engine  
│   │   ├── confidence\_engine.rs        \# Categorical confidence mapper  
│   │   ├── alternative\_generator.rs    \# Secondary strategy generator  
│   │   └── strategy\_selector.rs        \# Winning candidate selector  
│   ├── history/  
│   │   ├── decision\_history.rs         \# SQLite audit log interface  
│   │   ├── explanation\_generator.rs    \# Human-readable rationale writer  
│   │   └── metrics\_collector.rs        \# Prometheus performance exporter  
│   ├── sockets/  
│   │   ├── decision\_socket.rs          \# Brain / Compiler IPC handlers  
│   │   ├── context\_socket.rs           \# System state IPC connection  
│   │   └── policy\_socket.rs            \# Kernel policy bus connection  
│   ├── pipelines/  
│   │   ├── decision\_pipeline.rs        \# Master execution pipeline  
│   │   ├── scoring\_pipeline.rs         \# Scoring execution stage  
│   │   └── validation\_pipeline.rs      \# Policy validation stage  
│   └── utils/  
│       ├── crypto.rs                   \# SHA-256 and Ed25519 routines  
│       └── telemetry.rs                \# Internal latency tracking  
└── tests/  
    ├── unit/                           \# Isolated component unit tests  
    ├── integration/                    \# End-to-end pipeline tests  
    └── mock\_data/                      \# Simulated contexts and goals

### **Directory Responsibilities**

* config/: Contains runtime configuration files governing scoring weights, confidence limits, and policy mappings.  
* docs/: Contains official architectural designs, schema references, and engineering documentation.  
* src/core/: Contains the master orchestrator, state containers, and safety recovery sub-systems.  
* src/analyzers/: Contains modules that parse raw goals, stitch context, quantify limits, and assess risk vectors.  
* src/validators/: Contains absolute compliance gatekeepers enforcing policies, security, and laws.  
* src/resolvers/: Contains matching engines that connect goals to physical hardware, services, and API connectors.  
* src/scoring/: Contains mathematical engines that calculate scores, construct alternative plans, and choose strategies.  
* src/history/: Contains output persistence, metrics export, and decision explanation compilation.  
* src/sockets/: Contains IPC communication handlers and network protocol interfaces.  
* src/pipelines/: Contains stage-by-stage pipeline definitions managing data flow between modules.  
* src/utils/: Contains cryptographical signature, hashing, and performance profiling helpers.  
* tests/: Contains complete automated test suits, fake drivers, and system scenario mocks.

# **18\. IMPLEMENTATION GUIDE**

## **18.1 Class & Structural Responsibilities**

### **DecisionEngineCore**

* **Role:** Primary Entry Point.  
* **Fields:** config: ConfigState, history: DecisionHistoryStore, pipeline: MasterDecisionPipeline.  
* **Public Methods:** process\_request(req: DecisionRequest) \-\> DecisionResponse, reload\_config(cfg: ConfigState) \-\> Status.

### **ContextAnalyzer**

* **Role:** State Aggregator.  
* **Fields:** telemetry\_socket: ContextSocket, cache: StateCache.  
* **Public Methods:** get\_active\_context(overrides: ContextOverride) \-\> NormalizedContext.

### **PolicyValidator**

* **Role:** Hard Gatekeeper.  
* **Fields:** policy\_db: PolicyRegistry.  
* **Public Methods:** validate\_policy(goal: ParsedGoal, ctx: NormalizedContext) \-\> PolicyResult.

### **ScoringEngine**

* **Role:** Strategy Evaluator.  
* **Fields:** weights: WeightMatrix.  
* **Public Methods:** score\_candidates(candidates: Vec\<Strategy\>, ctx: NormalizedContext) \-\> Vec\<ScoredStrategy\>.

## **18.2 Public Interfaces (Type Definitions)**

TypeScript  
export interface DecisionRequest {  
  requestId: string;  
  traceId: string;  
  timestamp: number;  
  requestor: {  
    id: string;  
    authorityLevel: number;  
    securityToken: string;  
  };  
  goal: {  
    rawIntent: string;  
    targetPrimitive: string;  
    parameters: Record\<string, any\>;  
  };  
  contextOverrides?: Record\<string, any\>;  
}

export interface SelectedStrategy {  
  strategyId: string;  
  name: string;  
  confidenceScore: number;  
  confidenceLevel: 'VERY\_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';  
  compositeRiskScore: number;  
  executionSteps: Array\<{  
    stepId: string;  
    capabilityRequired: string;  
    serviceAssigned: string;  
    connectorAssigned?: string;  
    fallbackStepId?: string;  
  }\>;  
  explanationTree: {  
    primaryReason: string;  
    tradeOffsAccepted: string\[\];  
    rejectedAlternatives: Array\<{ strategyId: string; reason: string }\>;  
  };  
  auditSignature: string;  
}

export interface DecisionResponse {  
  requestId: string;  
  decisionId: string;  
  status: 'ACCEPTED' | 'REJECTED' | 'HUMAN\_APPROVAL\_REQUIRED';  
  selectedStrategy?: SelectedStrategy;  
  rejectionReason?: string;  
  metrics: {  
    totalLatencyMs: number;  
    candidatesEvaluated: number;  
  };  
}

## **18.3 Configuration File Format**

See Section 14 for the complete specifications of decision\_config.toml.

## **18.4 Naming Conventions**

* **Files:** Lowercase with snake\_case (e.g., decision\_core.rs, policy\_validator.rs).  
* **Classes / Structs:** PascalCase (e.g., DecisionEngineCore, CapabilityResolver).  
* **Interfaces / Traits:** PascalCase prefixed with I or ending with trait domain (e.g., PolicyValidatable, IDecisionSocket).  
* **Functions / Methods:** snake\_case (e.g., calculate\_composite\_risk(), evaluate\_policy()).  
* **Constants:** ALL\_CAPS\_SNAKE\_CASE (e.g., MAX\_DECISION\_LATENCY\_MS, DEFAULT\_WEIGHT\_POLICY).

## **18.5 Coding Standards**

* **Memory Safety:** Zero unhandled null or undefined references. All errors must use explicit Result / Option pattern primitives.  
* **Concurrency:** Thread-safe state access using lock-free structures or read-write locks (RwLock).  
* **Panics:** Absolutely zero runtime panics allowed in production paths. Every sub-module must catch internal exceptions and emit a fallback result.  
* **Immutability:** Inputs to pipelines must remain immutable. Data transformations must output new structured instances.

## **18.6 Testing Strategy**

* **Unit Tests:** Every module must achieve minimum 95% line test coverage. All scoring algorithms must be verified against deterministic test matrices.  
* **Integration Tests:** Simulated Brain-to-Compiler pipeline executions validating state handling under degraded service conditions.  
* **Policy Compliance Tests:** Automated security test battery verifying that zero policy-violating strategies can pass through the PolicyValidator.  
* **Fuzz Testing:** Random malformed DecisionRequest payload injections into the GoalAnalyzer to guarantee non-crashing behavior.

## **18.7 Performance Targets**

* **End-to-End Decision Latency:** $\\le 50\\text{ms}$ (Target), $200\\text{ms}$ (Upper Ceiling).  
* **Throughput Capacity:** Minimum 2,000 full decision evaluations per second per CPU core.  
* **Memory Footprint:** $\\le 128\\text{MB}$ total persistent resident set size (RSS).  
* **Cold Start Latency:** Engine fully initialized and ready to accept sockets within $100\\text{ms}$ of daemon start.

# **19\. FUTURE COMPATIBILITY & EXTENSIBILITY**

The Decision Engine is architected to evolve without breaking core contracts:

1. **Multiple Decision Models:** Interfaces support hot-swapping deterministic scoring engines with probabilistic Bayesian networks or dynamic rule trees.  
2. **AI-Assisted Planning Integration:** Future local LLMs or symbolic reasoning engines can be attached to the AlternativeGenerator to propose novel execution candidate DAGs, while leaving deterministic scoring and policy validation intact.  
3. **Distributed Decision Engines:** Sockets support remote protocol bindings, enabling multi-node consensus voting across distributed AOS instances.  
4. **Multi-Agent Collaboration:** Supports multi-intent merging where decisions involve input goals from multiple autonomous agent entities.  
5. **Rule-Based to Probabilistic Transition:** Scoring modules isolate evaluation algorithms behind standard trait abstractions, allowing seamless migration from static matrix weighting to dynamic offline-trained reinforcement models.

