# **Organ 10 — Agents Specification Document**

## **1\. Overview**

The Agents Organ is the specialized task execution, autonomous agent instantiation, tool delegation, and context-bound reasoning worker runtime of the Hojaiga Automation Operating System. It translates structural task DAGs dispatched by the Central Nervous System (CNS) into domain-specific agent operations (e.g., Code Execution Agent, Browser Interaction Agent, Document Parsing Agent, System Maintenance Agent). Operating CPU-first, the Agents Organ enforces strict capability sandboxing, session isolation, and prompt context scoping across all instantiated agents without allowing uncoordinated global state mutations or direct inter-organ bypasses.

MD+ 4

## **2\. Purpose**

The purpose of the Agents Organ is to manage the lifecycle, scope, context memory, and execution routines of autonomous, role-specific agents within Hojaiga. In accordance with Policy Manual Chapter 7, every agent operates strictly within assigned capability boundaries, understands context prior to execution, logs decisions, and respects architectural governance without bypassing system security controls.

MD+ 4

## **3\. Philosophy**

In strict compliance with Master Architecture Blueprint Chapter 3, Universal Law 3 (Separation of Responsibility), and Policy Manual Chapter 7, agents in Hojaiga are ephemeral, single-purpose worker units rather than monolithic general-intelligence drivers. Agents own zero private persistent infrastructure; they query the Memory Organ for session context, request capability bindings from the Knowledge Organ, invoke actions via the Controllers Organ, and route all communication through the CNS. An agent exists to fulfill a specific sub-task within a plan tree and releases all thread allocations upon task completion.

MD+ 4

## **4\. Primary Responsibilities**

* **Agent Lifecycle Management:** Spawn, configure, monitor, pause, and terminate specialized worker agent instances.  
   MD+ 1  
* **Context & Role Scoping:** Bind specialized system prompts, tool schemas, and room session contexts to active agents.  
   MD+ 2  
* **Sub-Task Execution & Tool Invocation:** Deconstruct sub-goal steps and invoke domain tools through the Controllers Organ.  
   MD+ 2  
* **Agent State Tracking:** Maintain isolated, thread-safe execution state machines for each instantiated agent.  
   MD+ 2  
* **Inter-Agent Task Delegation:** Coordinate parent-child sub-agent task splitting via CNS pipeline channels.  
   MD+ 1  
* **Decision Trace Generation:** Record structured, step-by-step reasoning steps, tool invocation inputs, and outputs for history logging.  
   MD+ 2

## **5\. Internal Modules**

* `agents_core`: Primary IPC socket interface, worker pool scheduler, and agent registry.  
* `agent_factory`: Dynamic worker instantiator configuring role prompts, capability masks, and memory scopes.  
   MD+ 2  
* `role_registry`: Catalog of pre-configured agent roles (e.g., `BrowserAgent`, `CodeAgent`, `DocAgent`, `SysAdminAgent`).  
   MD+ 1  
* `task_runner`: Execution loop driver processing agent action steps and handling tool returns.  
   MD+ 2  
* `context_scope_manager`: Manages agent interaction rooms and prunes irrelevant tokens during long multi-step runs.  
   MD+ 1  
* `delegation_engine`: Orchestrates parent agent to child sub-agent task handoffs via CNS RPC contracts.  
   MD+ 1  
* `trace_collector`: Packages agent reasoning chains, tool calls, and outputs into structured audit payloads.  
   MD+ 2

## **6\. Internal Folder Structure**

/organ\_10\_agents  
├── bin/  
│   └── agents\_daemon          \# Core agent manager daemon executable  
├── config/  
│   └── agent\_roles.json       \# Pre-defined agent roles and tool mappings  
├── src/  
│   ├── core/  
│   │   ├── agents\_kernel.py  
│   │   └── worker\_pool.py  
│   ├── factory/  
│   │   ├── agent\_factory.py  
│   │   └── role\_registry.py  
│   ├── runners/  
│   │   ├── task\_runner.py  
│   │   └── delegation\_engine.py  
│   ├── context/  
│   │   └── scope\_manager.py  
│   ├── telemetry/  
│   │   └── trace\_collector.py  
│   └── sockets/  
│       └── ipc\_server.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* `IPC Socket Interface`: `\\.\pipe\hojaiga_agents` (Windows) / `/tmp/hojaiga_agents.sock` (Linux/Unix).  
   MD  
  * `rpc SpawnAgent(AgentSpawnPayload)` \-\> `AgentHandle`  
  * `rpc ExecuteAgentStep(AgentStepPayload)` \-\> `StepExecutionResult`  
  * `rpc DelegateSubTask(DelegationPayload)` \-\> `DelegationHandle`  
  * `rpc GetAgentStatus(AgentHandle)` \-\> `AgentStatusPayload`  
  * `rpc TerminateAgent(AgentHandle)` \-\> `TerminationAck`  
  * `rpc GetActiveAgentsSummary(QueryPayload)` \-\> `AgentSummaryList`

## **8\. Internal Interfaces**

* `IAgentRunner`:  
  * `initialize_role(role_id, session_room)`: Loads role prompts and binds session memory room.  
     MD+ 1  
  * `step_execution(action_input)`: Processes single reasoning pass and dispatches required tool action.  
     MD+ 2  
  * `get_memory_context()`: Fetches scoped interaction history from Memory Organ.  
     MD+ 1  
* `IDelegationManager`:  
  * `spawn_child_agent(parent_handle, child_role, sub_goal)`: Requests CNS to route child agent initialization.  
     MD+ 1

## **9\. Socket Definitions**

* Named Pipe Socket: `hojaiga_agents`.  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
   MD  
* Max Payload Size: 16 MB per request frame.

## **10\. Pipeline Definitions**

* `AgentTaskExecutionPipeline`:  
  1. CNS Dispatches Agent Task \-\> 2\. `agents_core` Schema Check \-\> 3\. `agent_factory` Spawns Worker \-\> 4\. Bind Session Room & Knowledge Tools \-\> 5\. `task_runner` Executes Reasoning/Action Loop \-\> 6\. Collect Decision Traces \-\> 7\. Return Response Frame to CNS.  
      MD+ 2

## **11\. Incoming Connections**

* **CNS Organ (02):** Transmits task dispatches, plan step executions, and sub-agent delegation requests.  
   MD+ 1  
* **Controllers Organ (05):** Coordinates task execution feedback and status inquiries via CNS.  
   MD+ 2

## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits agent step outcomes, tool call directives, delegation requests, and execution traces (`EVENT_AGENT_STARTED`, `EVENT_AGENT_STEP_COMPLETED`, `EVENT_AGENT_FAILED`).  
   MD+ 2

## **13\. State Management**

Individual instantiated workers manage local execution state machines:

* `INSTANTIATED`: Role configured, memory room attached, worker assigned.  
   MD+ 1  
* `WAITING_FOR_BRAIN`: Awaiting Brain Organ LLM reasoning response via CNS.  
   MD+ 2  
* `WAITING_FOR_TOOL`: Dispatched tool action to Controllers/Automation Organ; awaiting tool completion.  
   MD+ 2  
* `EXECUTING`: Processing output payload or formatting decision traces.  
   MD+ 2  
* `COMPLETED`: Sub-task finished successfully; trace committed; releasing memory buffers.  
   MD+ 2  
* `TERMINATED`: Agent forcibly stopped due to timeout or error.  
   MD+ 2

## **14\. Event Definitions**

* `EVENT_AGENT_SPAWNED`: Fired when a new agent instance is created.  
   MD+ 1  
* `EVENT_AGENT_STEP_COMPLETED`: Emitted upon successful execution of an intermediate action step.  
   MD+ 2  
* `EVENT_AGENT_DELEGATION_INITIATED`: Fired when an agent spawns a sub-agent task.  
   MD+ 1  
* `EVENT_AGENT_TIMEOUT`: Triggered if an agent action step exceeds execution time bounds.  
   MD+ 2

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "AgentSpawnRequest",  
  "type": "object",  
  "properties": {  
    "task\_id": { "type": "string", "format": "uuid" },  
    "role\_id": { "type": "string" },  
    "session\_room\_id": { "type": "string" },  
    "assigned\_sub\_goal": { "type": "string" },  
    "allowed\_capabilities": { "type": "array", "items": { "type": "string" } },  
    "timeout\_ms": { "type": "integer", "default": 60000 }  
  },  
  "required": \["task\_id", "role\_id", "session\_room\_id", "assigned\_sub\_goal"\]  
}

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "AgentStepResponse",  
  "type": "object",  
  "properties": {  
    "agent\_handle": { "type": "string", "format": "uuid" },  
    "step\_index": { "type": "integer" },  
    "status": { "type": "string", "enum": \["CONTINUE", "FINISHED", "FAILED", "BLOCKED"\] },  
    "tool\_call\_requested": { "type": "object" },  
    "decision\_reasoning": { "type": "string" },  
    "execution\_time\_ms": { "type": "integer" }  
  },  
  "required": \["agent\_handle", "step\_index", "status", "execution\_time\_ms"\]  
}

## **16\. Internal Database Structures**

The Agents Organ maintains an in-memory runtime tracking store using SQLite (`:memory:`):

* Table `active_agents` (`agent_handle` TEXT PRIMARY KEY, `task_id` TEXT, `role_id` TEXT, `room_id` TEXT, `status` TEXT, `spawned_at` TIMESTAMP, `timeout_ms` INTEGER).  
   MD+ 2  
* Table `agent_traces` (`trace_id` TEXT PRIMARY KEY, `agent_handle` TEXT, `step_index` INTEGER, `reasoning_text` TEXT, `tool_called` TEXT, `status` TEXT, `timestamp` TIMESTAMP).  
   MD+ 2

## **17\. Cache Strategy**

* Agent Role Profile Cache: Pre-compiled system prompts and tool schema masks for active roles held permanently in RAM for instant worker spawning.  
   MD+ 1  
* Step Output Cache: Last 5 tool execution outputs cached per agent worker to allow rapid retry loops without duplicate tool calls.  
   MD+ 1

## **18\. Memory Strategy**

* Total resident RAM footprint for the Agents Organ manager and all active worker threads capped at 512 MB.  
* Agents stream trace payloads exceeding 1 MB directly to SSD storage via Infrastructure Organ log appenders rather than accumulating large buffers in RAM.  
   MD+ 1

## **19\. Thread Safety**

* Worker agents execute on isolated thread handles managed by `worker_pool.py`.  
* Mutex wrappers (`threading.Lock` / `std::mutex`) protect active agent registry modifications and trace table writes.  
   MD

## **20\. Concurrency**

* Concurrently manages up to 8 active worker agent threads (matching physical CPU core limits on Intel Core i7).  
   MD  
* Thread pool prioritizes real-time user-facing tasks over background maintenance agent runs.  
   MD+ 1

## **21\. Hardware Optimization**

* CPU-First Architecture: Reasoning context parsing, tool argument assembly, and decision trace packaging run strictly on host CPU cores.  
   MD  
* Process thread affinity masks restrict worker threads to specific physical CPU cores during multi-agent execution.  
   MD

## **22\. GPU Usage**

* Zero GPU usage directly within the Agents Organ.  
   MD  
* When an agent requires LLM reasoning passes, it dispatches prompt requests to the Brain Organ via CNS, where GPU VRAM is managed exclusively by `llama.cpp`.  
   MD+ 1

## **23\. CPU Usage**

* Idle state CPU footprint: \<0.2%.  
   MD  
* Peak CPU consumption during multi-agent context parsing and trace formatting capped at 15% across CPU cores.  
   MD+ 1

## **24\. SSD Usage**

* Role configurations, task runner swap spaces, and immediate trace logs reside on 100 GB SSD Runtime.  
   MD+ 1

## **25\. HDD Usage**

* Completed agent execution traces, decision trees, and historical reasoning logs are archived sequentially to External HDD storage.  
   MD+ 2

## **26\. Security Model**

* Role Capability Boundaries: Workers are assigned strict capability masks upon spawning; an agent assigned `DocAgent` role cannot invoke raw browser commands or system administration utilities.  
   MD+ 2  
* Token Authorization: Every tool request generated by an agent must include its assigned capability token, which is verified by Security Organ before dispatch.  
   MD+ 2

## **27\. Permissions**

* Worker agents operate under restricted standard OS user privileges.  
   MD  
* Direct system access or administrative privilege escalation is blocked by Security and Governance Controllers.  
   MD+ 2

## **28\. Logging**

* Structured JSON audit logging following Policy Manual Chapter 8\.  
   MD  
* Logs record `agent_handle`, `task_id`, `role_id`, `step_index`, `reasoning_summary`, `tool_call`, `duration_ms`, and `status`.  
   MD+ 1

## **29\. History Recording**

* Complete agent reasoning logs, step inputs/outputs, and execution metrics are committed to external HDD history archives via CNS history pipelines.  
   MD+ 2

## **30\. Recovery Strategy**

* Step Retry Logic: If an agent step fails due to a temporary tool failure or timeout, `task_runner` re-evaluates context and attempts up to 2 retry passes before escalating failure to the Brain Organ for re-planning.  
   MD+ 2

## **31\. Failure Handling**

* Agent Hang: If a worker agent fails to respond within `timeout_ms`, `agents_core` forcefully terminates the worker thread, purges its local handles, logs `EVENT_AGENT_TIMEOUT`, and notifies CNS.  
   MD+ 2

## **32\. Validation Rules**

* Requests must specify valid `role_id` existing in `agent_roles.json`, attach a valid session room ID, and operate within assigned capability limits.  
   MD+ 2

## **33\. Testing Strategy**

* Unit tests for `agent_factory` instantiation, role capability masking, and trace collection.  
   MD+ 1  
* Integration tests simulating multi-step agent workflows executing mock tool calls through CNS.  
   MD+ 2

## **34\. Extension Points**

* Custom Agent Roles: New roles can be registered in `config/agent_roles.json` with customized system prompts and capability bindings without modifying core kernel code.  
   MD+ 2

## **35\. Future Compatibility**

* Forward-compatible role definitions supporting dynamic system prompt schema updates.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` Agents Organ Specification.  
   MD+ 1

## **37\. Dependencies**

* Python 3.11+ / C++17 runtime.  
   MD  
* SQLite 3.45+.  
   MD

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Central message bus for all agent spawn requests, tool calls, and event emissions.  
   MD+ 1  
* **Brain (Organ 01):** Receives prompt reasoning passes generated during agent steps.  
   MD+ 2  
* **Memory (Organ 03):** Supplies session history rooms and stores step context.  
   MD+ 1  
* **Controllers (Organ 05):** Executes tool invocations requested by agents.  
   MD+ 2

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Agents Kernel\]  
    Core \--\> Pool\[Worker Pool Scheduler\]  
    Core \--\> Factory\[Agent Factory\]  
    Factory \--\> Roles\[Role Registry\]  
    Pool \--\> Runner\[Task Runner\]  
    Runner \--\> Context\[Context Scope Manager\]  
    Runner \--\> Del\[Delegation Engine\]  
    Runner \--\> Trace\[Trace Collector\]  
    Runner \--\>|Tool Call via CNS| Ctrl\[Controllers Organ 05\]  
    Runner \--\>|Prompt via CNS| Brain\[Brain Organ 01\]

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant CNS as Organ 02 (CNS)  
    participant Core as Agents Kernel  
    participant Runner as Worker Task Runner  
    participant Brain as Organ 01 (Brain)  
    participant Ctrl as Organ 05 (Controllers)

    CNS-\>\>Core: SpawnAgent(Role: BrowserAgent, SubGoal)  
    Core-\>\>Runner: Instantiate Worker Thread & Bind Role  
    Runner-\>\>CNS: Request Reasoning (System \+ Context Prompt)  
    CNS-\>\>Brain: Forward Prompt to Brain  
    Brain--\>\>CNS: Return LLM Action Plan (Invoke Tool: Click)  
    CNS--\>\>Runner: Deliver Reasoning Result  
    Runner-\>\>CNS: Execute Tool Directive (Click Element)  
    CNS-\>\>Ctrl: Dispatch Action to Controller  
    Ctrl--\>\>CNS: Return Tool Execution Output  
    CNS--\>\>Runner: Deliver Tool Output  
    Runner--\>\>Core: Step Complete Payload  
    Core--\>\>CNS: Agent Step Outcome Frame

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Task Dispatch Received\] \--\> B\[Validate Role & Capabilities\]  
    B \--\> C{Role Exists?}  
    C \-- No \--\> D\[Return Invalid Role Error\]  
    C \-- Yes \--\> E\[Instantiate Ephemeral Worker Thread\]  
    E \--\> F\[Bind Session Room & Context\]  
    F \--\> G\[Execute Step Reasoning Loop via Brain\]  
    G \--\> H{Requires Tool Execution?}  
    H \-- Yes \--\> I\[Dispatch Tool Directive via Controllers Organ\]  
    H \-- No \--\> J{Goal Achieved?}  
    I \--\> K\[Process Tool Response\]  
    K \--\> G  
    J \-- No \--\> G  
    J \-- Yes \--\> L\[Package Trace & Terminate Worker Thread\]  
    L \--\> M\[Return Success Payload to CNS\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Instantiated  
    Instantiated \--\> WaitingForBrain : Reasoning Request Dispatched  
    WaitingForBrain \--\> WaitingForTool : Tool Action Dispatched  
    WaitingForTool \--\> Executing : Tool Result Received  
    Executing \--\> WaitingForBrain : Next Step Required  
    Executing \--\> Completed : Sub-Goal Achieved  
    WaitingForBrain \--\> Terminated : Timeout Breach  
    WaitingForTool \--\> Terminated : Execution Failure  
    Completed \--\> \[\*\] : Thread Released  
    Terminated \--\> \[\*\] : Handle Cleaned

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_10\_agents\] \--\> Bin\[bin/agents\_daemon\]  
    Root \--\> Config\[config/agent\_roles.json\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/agents\_kernel.py\]  
    Src \--\> Factory\[factory/agent\_factory.py\]  
    Src \--\> Runners\[runners/task\_runner.py\]  
    Src \--\> Context\[context/scope\_manager.py\]  
    Src \--\> Telemetry\[telemetry/trace\_collector.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_agents\]  
    Pipe \--\> IPC\[Agents IPC Listener Thread\]  
    IPC \--\> Core\[Agents Kernel Engine\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    P1\[1. Task Ingestion\] \--\> P2\[2. Role & Scope Binding\]  
    P2 \--\> P3\[3. Worker Thread Allocation\]  
    P3 \--\> P4\[4. Brain Reasoning Pass\]  
    P4 \--\> P5\[5. Controller Tool Execution\]  
    P5 \--\> P6\[6. Decision Trace Archival\]

## **46\. Engineering Recommendations**

* Pre-compile and validate role prompt templates during daemon startup to ensure sub-millisecond worker instantiation latency when high-priority tasks arrive.  
   MD+ 1  
* Set explicit thread timeouts (default 60000ms) on all worker runner loops to prevent hung tool responses or stalled LLM calls from leaking worker pool allocations.  
   MD+ 2

## **47\. Tradeoffs**

* **Ephemeral Worker Agents vs. Permanent Background Agent Processes:** Ephemeral workers incur a \~5ms instantiation setup cost per task step, but guarantee absolute memory reclamation, zero idle RAM usage, and complete task state isolation.  
   MD+ 2  
* **Strict Role Capability Masking vs. Universal Agent Tool Access:** Scoping capabilities per agent role requires explicit capability declaration in `agent_roles.json`, but prevents runaway agents from executing unauthorized commands or mutating unintended system states.  
   MD+ 2

## **48\. Alternatives Considered**

* **Monolithic Single-Agent Execution Architecture:** Rejected because a single agent blurs execution contexts, makes parallel multi-task processing impossible, and violates Universal Law 3\.  
   MD+ 1  
* **Dynamic Python Code Generation for Agents:** Rejected due to severe security vulnerabilities, lack of execution sandboxing, and difficulty in auditing generated agent code.  
   MD+ 2

## **49\. Future Improvements**

* Dynamic worker thread priority adjustment based on real-time task user-interactivity ratings.  
   MD+ 1  
* Hierarchical agent memory summarization algorithms to compress interaction context during deep sub-task execution trees.  
   MD+ 1

## **50\. Claude Implementation Instructions**

1. Build file and folder layout as specified in Section 6\.  
    MD  
2. Implement `factory/role_registry.py` parsing and caching role templates from `config/agent_roles.json`.  
    MD+ 1  
3. Build `runners/task_runner.py` executing worker step loops with explicit timeout bounds.  
    MD+ 2  
4. Build `telemetry/trace_collector.py` packaging decision chains into structured JSON logs.  
    MD+ 1  
5. Set up Named Pipe IPC listener at `\\.\pipe\hojaiga_agents`.  
    MD

