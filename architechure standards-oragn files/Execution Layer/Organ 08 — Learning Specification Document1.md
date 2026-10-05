# **Organ 08 — Learning Specification Document**

## **1\. Overview**

The Learning Organ is the self-evaluation, continuous improvement, strategy optimization, and operational performance tracking kernel of the Hojaiga Automation Operating System. It monitors post-task execution traces, detects operational errors, calculates tool/application reliability scores, optimizes prompt assembly templates, and preserves successful execution strategies. Operating CPU-first with disk-backed analytical stores, the Learning Organ executes asynchronous evaluation loops without compromising core system performance or violating architectural immutability rules.

MD+ 4

## **2\. Purpose**

The purpose of the Learning Organ is to analyze execution telemetry, identify failure patterns, and refine future execution efficiency in accordance with Article II of the Constitution, Foundational Law 13 (Continuous Self-Evaluation), and Policy Manual Chapter 13\. It systematically transforms operational history into actionable knowledge improvements—such as adjusting application reliability scores, updating strategy templates, and flagging fragile selectors—without autonomously modifying protected core architecture or governing documents.

MD+ 4

## **3\. Philosophy**

In strict compliance with Master Architecture Blueprint Chapter 1, Universal Law 10 (Evidence-Based Decision Making), and Policy Manual Chapter 13, all learning in Hojaiga is evidence-based, incremental, traceable, and subject to governance. The Learning Organ observes execution results and proposes updates to knowledge repositories, tool profiles, and reasoning strategies. It never directly modifies source code or core system specifications. Autonomous adaptation is constrained strictly to parameter tuning, score updates, and strategy template caching.

MD+ 4

## **4\. Primary Responsibilities**

* **Post-Task Execution Evaluation:** Analyze execution logs, timing metrics, and status codes immediately following task completions.  
   MD+ 2  
* **Application & Tool Reliability Scoring:** Dynamically update reliability scores, priority rankings, and failure rates for installed applications and CLI tools based on real-world execution outcomes.  
   MD+ 1  
* **Strategy & Pattern Extraction:** Identify recurring execution paths, successful sub-task plan sequences, and high-latency bottlenecks.  
   MD+ 2  
* **Error Pattern & Failure Mode Analysis:** Classify execution failures (e.g., timeout, selector mismatch, process crash) and generate corrective strategy recommendations.  
   MD+ 2  
* **Prompt & DSL Optimization:** Recommend adjustments to system prompt layers and plan templates to reduce Brain Organ generation passes and token overhead.  
   MD+ 2  
* **Knowledge Store Evolution Feed:** Dispatch verified performance updates and new capability aliases directly to the Knowledge Organ.  
   MD+ 2

## **5\. Internal Modules**

* `learning_core`: Primary IPC socket interface, evaluation pipeline router, and asynchronous task listener.  
* `evaluator_engine`: Post-task performance scoring module calculating execution quality metrics and latency variance.  
   MD+ 2  
* `reliability_tracker`: Computes moving averages of tool and application success/failure ratios.  
   MD+ 1  
* `pattern_extractor`: Mining engine that extracts reusable plan trees and optimal execution paths from execution logs.  
   MD+ 2  
* `error_classifier`: Categorizes raw stack traces, process exit codes, and UIA/DOM timeouts into canonical error categories.  
   MD+ 2  
* `strategy_optimizer`: Generates refined strategy rules and prompt hint templates for the Brain and Knowledge Organs.  
   MD+ 2  
* `knowledge_publisher`: Constructs differential update payloads to evolve Knowledge Organ records safely.  
   MD+ 2

## **6\. Internal Folder Structure**

/organ\_08\_learning  
├── bin/  
│   └── learning\_daemon        \# Primary background worker binary  
├── config/  
│   └── evaluation\_rules.json  \# Scoring thresholds and decay metrics  
├── storage/  
│   ├── traces/                \# Raw trace buffers (SSD Runtime)  
│   └── learning\_db.sqlite     \# Analytical performance DB (HDD)  
├── src/  
│   ├── core/  
│   │   ├── learning\_kernel.py  
│   │   └── trace\_ingestor.py  
│   ├── evaluation/  
│   │   ├── evaluator\_engine.py  
│   │   └── reliability\_tracker.py  
│   ├── mining/  
│   │   ├── pattern\_extractor.py  
│   │   └── error\_classifier.py  
│   ├── optimization/  
│   │   └── strategy\_optimizer.py  
│   └── sockets/  
│       └── ipc\_server.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* `IPC Socket Interface`: `\\.\pipe\hojaiga_learning` (Windows) / `/tmp/hojaiga_learning.sock` (Linux/Unix).  
   MD  
  * `rpc IngestExecutionTrace(TracePayload)` \-\> `IngestAck`  
  * `rpc EvaluateTaskOutcome(TaskOutcomePayload)` \-\> `EvaluationSummary`  
  * `rpc GetAppReliabilityScore(AppQueryPayload)` \-\> `ReliabilityMetric`  
  * `rpc GetOptimalStrategy(GoalPatternPayload)` \-\> `StrategyRecommendation`  
  * `rpc RunBatchAnalysis(AnalysisParams)` \-\> `BatchAnalysisResult`

## **8\. Internal Interfaces**

* `IEvaluator`:  
  * `calculate_score(trace_data)`: Computes composite task score based on speed, resource consumption, and success status.  
     MD+ 1  
  * `update_decay_scores()`: Applies time-decay factors to historical performance statistics.  
     MD+ 1  
* `IKnowledgePublisher`:  
  * `publish_score_update(app_id, new_score)`: Emits payload frame to Knowledge Organ via CNS.  
     MD+ 2

## **9\. Socket Definitions**

* Named Pipe Socket: `hojaiga_learning`.  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
   MD  
* Max Payload Size: 16 MB per request frame.

## **10\. Pipeline Definitions**

* `TaskEvaluationPipeline`:  
  1. CNS Sends Task Completed Event \-\> 2\. `trace_ingestor` Buffers Trace Frame \-\> 3\. `evaluator_engine` Scores Performance \-\> 4\. `reliability_tracker` Recalculates Target Reliability \-\> 5\. Emit `EVENT_LEARNING_EVALUATION_COMPLETE` \-\> 6\. Publish Differential Updates to Knowledge Organ.  
      MD+ 2

## **11\. Incoming Connections**

* **CNS Organ (02):** Transmits task completion events, execution trace logs, and system error events.  
   MD+ 2  
* **Brain Organ (01):** Queries strategy recommendations during plan compilation.  
   MD+ 2

## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits evaluation completions and updates (`EVENT_LEARNING_EVALUATION_COMPLETE`, `EVENT_RELIABILITY_UPDATED`).  
   MD+ 2  
* **Knowledge Organ (04):** Dispatches score updates, alias additions, and optimized workflow procedures via CNS.  
   MD+ 2

## **13\. State Management**

The Learning Organ transitions through background operational stages:

* `IDLE`: Listening for incoming execution traces.  
   MD  
* `INGESTING`: Buffering trace events from active task executions.  
   MD+ 1  
* `ANALYZING`: Processing trace batches, calculating metrics, and classifying errors.  
   MD+ 2  
* `PUBLISHING`: Dispatching updated score vectors to Knowledge Organ.  
   MD+ 2  
* `MAINTENANCE`: Pruning obsolete trace buffers and compacting analytics database.  
   MD

## **14\. Event Definitions**

* `EVENT_LEARNING_EVALUATION_COMPLETE`: Emitted when post-task evaluation finishes.  
   MD+ 1  
* `EVENT_RELIABILITY_UPDATED`: Triggered when an application or tool reliability score changes.  
   MD+ 1  
* `EVENT_STRATEGY_OPTIMIZED`: Fired when an improved plan pattern is extracted and stored.  
   MD+ 2  
* `EVENT_FAILURE_PATTERN_DETECTED`: Emitted when recurring failure modes are identified.  
   MD+ 2

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "TracePayload",  
  "type": "object",  
  "properties": {  
    "trace\_id": { "type": "string", "format": "uuid" },  
    "task\_id": { "type": "string", "format": "uuid" },  
    "goal": { "type": "string" },  
    "executing\_organ": { "type": "string" },  
    "tool\_used": { "type": "string" },  
    "duration\_ms": { "type": "integer" },  
    "status": { "type": "string", "enum": \["SUCCESS", "FAILED", "RECOVERED"\] },  
    "error\_log": { "type": "string" }  
  },  
  "required": \["trace\_id", "task\_id", "status", "duration\_ms"\]  
}

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "ReliabilityUpdatePayload",  
  "type": "object",  
  "properties": {  
    "app\_or\_tool\_id": { "type": "string" },  
    "old\_score": { "type": "number" },  
    "new\_score": { "type": "number" },  
    "sample\_count": { "type": "integer" },  
    "last\_error\_category": { "type": "string" }  
  },  
  "required": \["app\_or\_tool\_id", "new\_score", "sample\_count"\]  
}

## **16\. Internal Database Structures**

The Learning Organ uses SQLite (`storage/learning_db.sqlite`):

* Table `task_traces` (`trace_id` TEXT PRIMARY KEY, `task_id` TEXT, `goal` TEXT, `tool_used` TEXT, `duration_ms` INTEGER, `status` TEXT, `created_at` TIMESTAMP).  
   MD+ 1  
* Table `reliability_scores` (`target_id` TEXT PRIMARY KEY, `score` REAL, `successes` INTEGER, `failures` INTEGER, `last_updated` TIMESTAMP).  
   MD+ 1  
* Table `strategy_patterns` (`pattern_id` TEXT PRIMARY KEY, `goal_hash` TEXT, `plan_template_json` TEXT, `avg_duration_ms` INTEGER, `score` REAL).  
   MD+ 2

## **17\. Cache Strategy**

* Score Cache: Active application and tool reliability scores cached in RAM (LRU 256 slots) for rapid response to query requests.  
* Strategy Pattern Cache: Frequently retrieved plan templates held in memory to accelerate Brain Organ strategy lookup.

## **18\. Memory Strategy**

* Volatile RAM footprint kept strictly below 256 MB.  
* Trace batching buffers raw traces in RAM up to 100 entries before executing bulk disk commits to minimize I/O overhead.  
   MD+ 1

## **19\. Thread Safety**

* Asynchronous trace ingesters run in non-blocking event loop threads.  
* Analytical database writes operate on an isolated single-threaded write queue to maintain SQLite transactional integrity.  
   MD

## **20\. Concurrency**

* Asynchronous, non-blocking IPC processing model.  
   MD  
* Heavy pattern extraction and statistical analysis execute on low-priority background worker threads to avoid interfering with primary execution tasks.  
   MD

## **21\. Hardware Optimization**

* CPU-First Architecture: Statistical scoring, text pattern matching, and decay calculations execute on physical Intel Core i7 CPU cores.  
   MD  
* Vector SIMD instructions used for fast text pattern hashing during strategy clustering.

## **22\. GPU Usage**

* Zero GPU usage. Evaluator algorithms and statistical modeling run entirely on host CPU.  
   MD

## **23\. CPU Usage**

* Idle state CPU footprint: \<0.1%.  
   MD  
* Peak CPU consumption during batch analysis capped at 10% on host CPU physical cores.  
   MD

## **24\. SSD Usage**

* Immediate trace buffers and active learning configuration files reside on 100 GB SSD Runtime.  
   MD+ 1

## **25\. HDD Usage**

* Analytical database (`learning_db.sqlite`), historical performance archives, and long-term trend stores reside on external HDD.  
   MD+ 1

## **26\. Security Model**

* Governance Restrictions: The Learning Organ is strictly prohibited from autonomously modifying governing documents, core architecture files, or application source code.  
   MD+ 3  
* Output Validation: All score updates and strategy updates dispatched to other organs are validated against schema rules.  
   MD+ 2

## **27\. Permissions**

* Executable permissions restricted to standard user context.  
   MD  
* Write operations limited strictly to `storage/` and IPC socket channels.  
   MD

## **28\. Logging**

* Structured JSON audit logging following Policy Manual Chapter 8\.  
   MD  
* Records `trace_id`, `evaluation_score`, `score_adjustments`, `pattern_matches`, and `processing_latency_ms`.  
   MD+ 1

## **29\. History Recording**

* Analytical evaluation results and historical performance score evolutions are appended to external HDD long-term history storage.  
   MD+ 2

## **30\. Recovery Strategy**

* Trace Replay: If the Learning Organ daemon crashes mid-analysis, `trace_ingestor` reads uncommitted traces from the SSD trace buffer upon restart and resumes processing.  
   MD+ 1

## **31\. Failure Handling**

* Corrupted Trace Ingestion: Invalid or malformed trace payloads are dropped, logged to DLQ, and emitted as `EVENT_DEAD_LETTER_LOGGED` without interrupting system loops.  
   MD+ 2

## **32\. Validation Rules**

* Traces must include valid UUIDs, non-negative duration metrics, and recognized status tags (`SUCCESS`, `FAILED`, `RECOVERED`).  
   MD+ 1

## **33\. Testing Strategy**

* Unit tests for score calculation formulas, time-decay algorithms, and error pattern classifiers.  
   MD+ 1  
* Integration tests verifying end-to-end trace ingestion, scoring, and Knowledge Organ update dispatching.  
   MD+ 2

## **34\. Extension Points**

* Custom Evaluator Plug-ins: Modular score calculator interfaces in `evaluation/` allow domain-specific metrics to be registered.  
   MD+ 1

## **35\. Future Compatibility**

* Schema migration tools in `src/core/` support database column additions for new analytics features.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` Learning Organ Specification.  
   MD+ 1

## **37\. Dependencies**

* Python 3.11+ / C++17 runtime.  
   MD  
* SQLite 3.45+.  
   MD

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Routes incoming execution traces and outgoing score update events.  
   MD+ 2  
* **Brain (Organ 01):** Consumes strategy recommendations to refine generation steps.  
   MD+ 2  
* **Knowledge (Organ 04):** Receives application reliability score updates and capability refinements.  
   MD+ 2  
* **Infrastructure (Organ 09):** Provides disk I/O metrics used as scoring inputs.  
   MD+ 1

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Learning Kernel\]  
    Core \--\> Ingest\[Trace Ingestor\]  
    Ingest \--\> Eval\[Evaluator Engine\]  
    Eval \--\> Rel\[Reliability Tracker\]  
    Eval \--\> Pattern\[Pattern Extractor\]  
    Eval \--\> Err\[Error Classifier\]  
    Pattern \--\> Strat\[Strategy Optimizer\]  
    Rel \--\> Pub\[Knowledge Publisher\]  
    Pub \--\>|Update Payload| Knw\[Knowledge Organ 04\]  
    Eval \--\> DB\[(Learning SQLite DB)\]

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant CNS as Organ 02 (CNS)  
    participant Learn as Organ 08 (Learning)  
    participant Eval as Evaluator Engine  
    participant Knw as Organ 04 (Knowledge)

    CNS-\>\>Learn: IngestExecutionTrace(Task Trace)  
    Learn-\>\>Eval: Calculate Score & Update Reliability  
    Eval-\>\>Eval: Score Decreased due to Timeout  
    Eval--\>\>Learn: New Score Calculated  
    Learn-\>\>Knw: Publish Reliability Score Update  
    Knw--\>\>Learn: Ack Update  
    Learn--\>\>CNS: Evaluation Complete Frame

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Execution Trace Received\] \--\> B\[Buffer Trace Frame in RAM\]  
    B \--\> C\[Parse Duration, Tool, and Status\]  
    C \--\> D{Task Status}  
    D \-- Success \--\> E\[Increase Tool Reliability Score\]  
    D \-- Failed \--\> F\[Decrease Tool Reliability Score & Classify Error\]  
    D \-- Recovered \--\> G\[Apply Mild Score Penalty & Extract Recovery Strategy\]  
    E \--\> H\[Check Pattern Extractor for Reusable Strategy\]  
    F \--\> I\[Log Failure Category\]  
    G \--\> H  
    H \--\> J\[Publish Score Updates to Knowledge Organ via CNS\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Idle  
    Idle \--\> Ingesting : Trace Event Received  
    Ingesting \--\> Analyzing : Batch Threshold Reached  
    Analyzing \--\> Publishing : Scores Recalculated  
    Publishing \--\> Idle : Updates Dispatched to Knowledge  
    Idle \--\> Maintenance : Vacuum / Prune Call  
    Maintenance \--\> Idle : Complete

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_08\_learning\] \--\> Bin\[bin/learning\_daemon\]  
    Root \--\> Config\[config/evaluation\_rules.json\]  
    Root \--\> Storage\[storage/learning\_db.sqlite\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/learning\_kernel.py\]  
    Src \--\> Eval\[evaluation/evaluator\_engine.py\]  
    Src \--\> Mining\[mining/pattern\_extractor.py\]  
    Src \--\> Opt\[optimization/strategy\_optimizer.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_learning\]  
    Pipe \--\> IPC\[Learning IPC Listener Thread\]  
    IPC \--\> Core\[Learning Kernel Engine\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    P1\[1. Trace Ingestion\] \--\> P2\[2. Score Calculation\]  
    P2 \--\> P3\[3. Error Classification\]  
    P3 \--\> P4\[4. Strategy Extraction\]  
    P4 \--\> P5\[5. Database Commit\]  
    P5 \--\> P6\[6. Knowledge Base Feed\]

## **46\. Engineering Recommendations**

* Implement exponential moving averages (EMA) for tool reliability scoring to allow recent execution performance to weigh more heavily than old historical runs.  
   MD+ 1  
* Enforce low-priority process scheduling (`IDLE_PRIORITY_CLASS` on Windows) for background pattern mining tasks to ensure complete CPU priority for real-time task execution.  
   MD

## **47\. Tradeoffs**

* **Asynchronous Batch Evaluation vs. Inline Real-Time Scoring:** Asynchronous evaluation introduces a short delay before reliability score updates are reflected in the Knowledge Organ, but prevents scoring overhead from delaying task completion.  
   MD+ 2  
* **Statistical Heuristic Learning vs. Continuous On-Disk Model Fine-Tuning:** Uses statistical metrics and template caching instead of fine-tuning LLM weights, preserving strict CPU/VRAM resource limits and preventing model hallucination decay.  
   MD+ 2

## **48\. Alternatives Considered**

* **Online LoRA Reinforcement Learning for Brain LLM:** Rejected due to high VRAM demands during training, risk of catastrophic forgetting, and violation of immutable core rules.  
   MD+ 3  
* **Direct Unfiltered File System Writes to Knowledge Base:** Rejected to maintain strict security isolation and prevent unverified telemetry from corrupting application profiles.  
   MD+ 2

## **49\. Future Improvements**

* Automated detection of flaky web element selectors using multi-run statistical variance analysis.  
   MD+ 1  
* Clustering algorithms for automated grouping of similar execution errors into failure categories.  
   MD+ 1

## **50\. Claude Implementation Instructions**

1. Build directory structure as specified in Section 6\.  
    MD  
2. Implement `evaluation/reliability_tracker.py` using exponential moving average formulas.  
    MD+ 1  
3. Build `mining/error_classifier.py` mapping raw exit codes to error categories.  
    MD+ 1  
4. Build `storage/learning_db.sqlite` schema and initialization routines.  
    MD+ 1  
5. Establish Windows Named Pipe listener at `\\.\pipe\hojaiga_learning`.  
    MD

