# **Organ 05 — Controllers Specification Document**

## **1\. Overview**

The Controllers Organ serves as the primary operational orchestration and specialized execution control hub of the Hojaiga Automation Operating System. It manages, coordinates, and enforces boundaries for all high-level domain controllers, including the Master Controller, Task Controller, Planning Controller, Memory Controller, Knowledge Controller, Application Controller, Tool Controller, Execution Controller, Security Controller, Governance Controller, Learning Controller, and History Controller. Operating CPU-first, the Controllers Organ translates structured plans into discrete, domain-specific execution directives while strictly maintaining individual controller scopes.

MD+ 4

## **2\. Purpose**

The purpose of the Controllers Organ is to encapsulate specific operational domains into isolated, capability-bound controller units. In accordance with Chapter 2 and Chapter 3 of the Master Architecture Blueprint, each controller owns its specific operational lifecycle, manages domain-specific input/output translation, enforces its localized state machine, and isolates functional logic from direct organ-level manipulation.

MD+ 4

## **3\. Philosophy**

In strict compliance with Master Architecture Blueprint Chapter 3, Universal Law 3 (Separation of Responsibility), and Policy Manual Chapter 6, every controller within the Controllers Organ possesses exactly one clearly defined domain responsibility and shall avoid unrelated concerns. Controllers communicate exclusively through standardized request/response objects over defined IPC interfaces. Controllers shall never bypass governance, directly execute unverified low-level OS operations outside their domain, or perform responsibilities outside their assigned scope.

MD+ 4

## **4\. Primary Responsibilities**

* **Domain Controller Lifecycle Management:** Initialize, monitor, and gracefully cycle individual controller sub-instances.  
   MD+ 1  
* **Input/Output Request Routing:** Receive execution DAGs from the Central Nervous System (CNS) and route sub-task payloads to specialized domain controllers.  
   MD+ 1  
* **Domain Context Preservation:** Maintain isolated state boundaries for active tasks within individual controller scopes.  
   MD+ 2  
* **Tool & Application Routing:** Coordinate handshakes between the Application Controller, Tool Controller, and Execution Controller.  
   MD+ 2  
* **Governance & Security Validation Dispatch:** Intercept domain execution requests and route parameters through Security and Governance controllers before execution.  
   MD+ 2  
* **Execution Feedback Aggregation:** Collect execution telemetry, errors, and outcomes from specialized controllers and format results for CNS return.  
   MD+ 2

  ## **5\. Internal Modules**

* `controllers_core`: Master orchestration engine managing internal controller registration and payload dispatching.  
   MD+ 1  
* `master_controller`: Top-level orchestrator mapping macro-tasks to specialized controller pipelines.  
   MD+ 1  
* `task_controller`: Task lifecycle manager tracking task creation, queuing, state transitions, and completion states.  
   MD+ 2  
* `planning_controller`: Bridge interface translating Brain Organ DAG plans into controller-executable instruction trees.  
   MD+ 2  
* `app_controller`: Application-level interaction manager governing app instantiation and operational bindings.  
   MD+ 2  
* `tool_controller`: Functional tool execution wrapper managing CLI, API, script, and system utility invocations.  
   MD+ 2  
* `execution_controller`: Active execution monitor overseeing low-level process spawning and task execution loops.  
   MD+ 2  
* `governance_controller`: Operational governance enforcer validating active actions against policy rules.  
   MD+ 2  
* `history_controller`: Operational history packager recording step-by-step decision trails and outcomes.  
   MD+ 2

  ## **6\. Internal Folder Structure**

1. /organ\_05\_controllers  
2. ├── bin/  
3. │   └── controllers\_daemon     \# Main process executable binary  
4. ├── config/  
5. │   └── controller\_bindings.json \# Domain controller registry and routes  
6. ├── src/  
7. │   ├── core/  
8. │   │   ├── controllers\_kernel.py  
9. │   │   └── dispatcher.py  
10. │   ├── domain/  
11. │   │   ├── master\_controller.py  
12. │   │   ├── task\_controller.py  
13. │   │   ├── planning\_controller.py  
14. │   │   ├── app\_controller.py  
15. │   │   ├── tool\_controller.py  
16. │   │   ├── execution\_controller.py  
17. │   │   ├── governance\_controller.py  
18. │   │   └── history\_controller.py  
19. │   ├── interfaces/  
20. │   │   └── base\_controller.py  
21. │   └── sockets/  
22. │       └── ipc\_server.py  
23. ├── tests/  
24. └── manifest.json  
    

    ## **7\. Public Interfaces**

* `IPC Socket Interface`: `\\.\pipe\hojaiga_controllers` (Windows) / `/tmp/hojaiga_controllers.sock` (Linux/Unix).  
   MD  
  * `rpc DispatchControllerTask(ControllerTaskPayload)` \-\> `ControllerExecutionResult`  
  * `rpc GetControllerStatus(ControllerID)` \-\> `ControllerStatusPayload`  
  * `rpc RegisterToolProvider(ToolDefinitionPayload)` \-\> `RegistrationAck`  
  * `rpc ExecuteAppAction(AppActionPayload)` \-\> `ActionResult`  
  * `rpc ValidateGovernanceRule(GovernanceQueryPayload)` \-\> `GovernanceVerdict`  
  * `rpc TerminateControllerExecution(TaskID)` \-\> `TerminationAck`

  ## **8\. Internal Interfaces**

* `IBaseController`:  
  * `initialize(config_dict)`: Sets up local controller buffers, dependencies, and limits.  
     MD  
  * `execute_domain_task(task_object)`: Runs specialized domain logic and returns standardized response.  
     MD+ 2  
  * `get_health()`: Returns local controller state, memory footprint, and active task count.  
     MD+ 1  
* `IToolRunner`:  
  * `invoke_tool(tool_id, parameters)`: Safely executes an isolated system utility or script.  
     MD+ 2

  ## **9\. Socket Definitions**

* Named Pipe Socket: `hojaiga_controllers`.  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
   MD  
* Max Payload Size: 16 MB per request frame.

  ## **10\. Pipeline Definitions**

* `ControllerTaskExecutionPipeline`:  
  1. CNS Sends Action Directives \-\> 2\. `controllers_core` Parsing & Validation \-\> 3\. `master_controller` Domain Selection \-\> 4\. Governance & Policy Check \-\> 5\. Domain Controller Dispatch (`app_controller` / `tool_controller`) \-\> 6\. `execution_controller` Spawning & Monitoring \-\> 7\. Output Result Formatting \-\> 8\. Return to CNS.  
      MD+ 2

  ## **11\. Incoming Connections**

* **CNS Organ (02):** Transmits high-level task execution instructions, control directives, and cancellation signals.  
   MD+ 1  
* **Brain Organ (01):** Interacts via CNS to trigger dynamic plan adjustments and request domain-specific status summaries.  
   MD+ 2

  ## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits status updates, task execution logs, tool invocation outputs, and governance alerts (`EVENT_CONTROLLER_TASK_STARTED`, `EVENT_CONTROLLER_TASK_COMPLETED`, `EVENT_CONTROLLER_ERROR`).  
   MD+ 2  
* **Automation Organ (06):** Routes lower-level browser, window, and desktop GUI interaction tasks.  
   MD+ 1

  ## **13\. State Management**

Individual controllers operate under localized state rules managed by `controllers_core`:

* `UNINITIALIZED`: Controller binaries loaded but unconfigured.  
   MD  
* `IDLE`: Controller listening, active resource locks cleared.  
   MD  
* `EXECUTING`: Specialized domain logic actively processing a sub-task.  
   MD  
* `BLOCKED`: Awaiting external policy approval or resource lock release.  
   MD+ 2  
* `ERROR`: Domain execution failed; error isolation active.  
   MD+ 2

  ## **14\. Event Definitions**

* `EVENT_CONTROLLER_REGISTERED`: Emitted when a domain controller binds to `controllers_core`.  
   MD+ 1  
* `EVENT_TASK_DISPATCHED_TO_DOMAIN`: Fired when `master_controller` routes a task to a specific controller.  
   MD+ 1  
* `EVENT_GOVERNANCE_BLOCKED`: Triggered when an attempted controller operation violates operational policies.  
   MD+ 2  
* `EVENT_EXECUTION_TERMINATED`: Emitted when a task is forcibly stopped due to timeout or user intervention.  
   MD+ 2

  ## **15\. Data Contracts**

  JSON  
25. {  
26.   "$schema": "http://json-schema.org/draft-07/schema\#",  
27.   "title": "ControllerTaskRequest",  
28.   "type": "object",  
29.   "properties": {  
30.     "task\_id": { "type": "string", "format": "uuid" },  
31.     "target\_controller": {   
32.       "type": "string",  
33.       "enum": \["master", "task", "app", "tool", "execution", "governance", "history"\]  
34.     },  
35.     "action": { "type": "string" },  
36.     "parameters": { "type": "object" },  
37.     "timeout\_ms": { "type": "integer", "default": 30000 }  
38.   },  
39.   "required": \["task\_id", "target\_controller", "action", "parameters"\]  
40. }  
      
    JSON  
41. {  
42.   "$schema": "http://json-schema.org/draft-07/schema\#",  
43.   "title": "ControllerTaskResponse",  
44.   "type": "object",  
45.   "properties": {  
46.     "task\_id": { "type": "string", "format": "uuid" },  
47.     "status": { "type": "string", "enum": \["SUCCESS", "FAILED", "BLOCKED", "TIMED\_OUT"\] },  
48.     "result\_data": { "type": "object" },  
49.     "execution\_time\_ms": { "type": "integer" },  
50.     "errors": { "type": "array", "items": { "type": "string" } }  
51.   },  
52.   "required": \["task\_id", "status", "execution\_time\_ms"\]  
53. }  
    

    ## **16\. Internal Database Structures**

The Controllers Organ maintains an in-memory runtime status tracking table using SQLite (`:memory:`):

* Table `controller_registry` (`controller_id` TEXT PRIMARY KEY, `status` TEXT, `active_tasks` INTEGER, `last_heartbeat` TIMESTAMP).  
   MD+ 1  
* Table `active_executions` (`task_id` TEXT PRIMARY KEY, `controller_id` TEXT, `start_time` TIMESTAMP, `timeout_ms` INTEGER, `pid` INTEGER).  
   MD+ 2

  ## **17\. Cache Strategy**

* Tool Definition Cache: Frequently executed tool schemas and CLI invocation paths are held in RAM for instant dispatch.  
* Governance Rule Cache: Policy validation results for standard action patterns are cached (LRU 512 entries) to accelerate repeated actions.  
   MD+ 1

  ## **18\. Memory Strategy**

* Total resident RAM footprint for all domain controller threads capped at 512 MB.  
* Ephemeral execution outputs larger than 2 MB are streamed to temporary swap files on SSD runtime storage rather than buffered in process RAM.  
   MD+ 1

  ## **19\. Thread Safety**

* Individual domain controllers execute in isolated sub-threads or worker processes coordinated by `controllers_core`.  
* Shared registry tables are protected by reentrant locks (`threading.RLock` / C++ `std::recursive_mutex`).  
   MD

  ## **20\. Concurrency**

* Parallel multi-controller execution model managed via an asynchronous worker pool (fixed to physical CPU core limits).  
   MD  
* Independent domain controllers (e.g., `app_controller` and `history_controller`) can run tasks concurrently provided no mutual resource lock exists.  
   MD+ 1

  ## **21\. Hardware Optimization**

* CPU-First Architecture: Domain controller logic, parameter parsing, and result formatting run strictly on the Intel Core i7 host CPU.  
   MD  
* Sub-process optimization: Low-level process invocation via Win32 `CreateProcessW` APIs for fast execution management.  
   MD

  ## **22\. GPU Usage**

* Zero GPU usage. The Controllers Organ does not perform matrix math or allocate VRAM.  
   MD

  ## **23\. CPU Usage**

* Idle state CPU footprint: \<0.5%.  
   MD  
* Peak CPU utilization capped at 10% during heavy concurrent sub-process spawning and parameter validation.  
   MD

  ## **24\. SSD Usage**

* Master configuration files, tool bindings, and temporary task execution swap files stored on 100 GB SSD Runtime.  
   MD+ 1

  ## **25\. HDD Usage**

* Completed controller task traces, historical execution logs, and detailed step-by-step decision trees flushed to external HDD archive storage via CNS history pipelines.  
   MD+ 2

  ## **26\. Security Model**

* Principle of Least Privilege: Each domain controller is granted permissions strictly limited to its functional domain.  
   MD+ 2  
* Governance Interception: Any controller action attempting to write to system configuration or access sensitive files must pass through `governance_controller` validation.  
   MD+ 2

  ## **27\. Permissions**

* Executable permissions restricted to the standard Hojaiga OS execution user account.  
   MD  
* Application and Tool Controllers operate under restricted process rights, preventing unauthorized elevated privilege escalation.  
   MD+ 2

  ## **28\. Logging**

* Structured JSON logging adhering to Policy Manual Chapter 8\.  
   MD  
* Logs record `task_id`, `source_controller`, `target_controller`, `action`, `parameters_hash`, `execution_status`, `duration_ms`, and `errors`.  
   MD+ 1

  ## **29\. History Recording**

* Every task dispatch, domain state change, and controller execution outcome is appended to system history logs via the `history_controller`.  
   MD+ 2

  ## **30\. Recovery Strategy**

* Sub-process Failure Isolation: If a tool or process managed by `execution_controller` crashes or hangs, the parent controller captures the SIGSEGV/return code, terminates the stranded process, releases local resource locks, and returns a structured failure payload to CNS for re-planning.  
   MD+ 2

  ## **31\. Failure Handling**

* Action Timeout: Tasks exceeding `timeout_ms` are forcibly killed by `execution_controller`, triggering an `EVENT_EXECUTION_TERMINATED` event and an automatic recovery pass.  
   MD+ 2

  ## **32\. Validation Rules**

* Requests must specify a valid `target_controller` existing within `controller_bindings.json`, contain all required schema parameters, and pass governance policy checks.  
   MD+ 2

  ## **33\. Testing Strategy**

* Unit tests for each domain controller wrapper (`app_controller`, `tool_controller`, `governance_controller`).  
   MD+ 2  
* Integration tests simulating full execution flows from `master_controller` to low-level process instantiation.

  ## **34\. Extension Points**

* Plug-in Controllers: Modular interface allowing new domain controllers to be registered in `controller_bindings.json` without modifying core kernel logic.  
   MD+ 2

  ## **35\. Future Compatibility**

* Backward-compatible message contracts using versioned JSON Schemas stored in `config/schemas/`.  
   MD+ 1

  ## **36\. Versioning**

* Semantic Versioning: `v1.0.0` Controllers Organ Specification.  
   MD+ 1

  ## **37\. Dependencies**

* Python 3.11+ / C++17 native runtime.  
   MD  
* Windows Win32 API (`CreateProcessW`, `JobObjects`) for execution monitoring.  
   MD

  ## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Primary socket router for all controller requests and responses.  
   MD+ 1  
* **Brain (Organ 01):** Provides structured plans that drive controller workflows.  
   MD+ 2  
* **Automation (Organ 06):** Receives UI and browser automation directives from `app_controller`.  
   MD+ 1  
* **Security (Organ 07):** Validates execution permissions and sandboxing constraints prior to tool execution.  
   MD+ 2

  ## **39\. Mermaid Component Diagram**

  Code snippet  
54. graph TD  
55.     CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Controllers Core Kernel\]  
56.     Core \--\> Master\[Master Controller\]  
57.     Master \--\> Task\[Task Controller\]  
58.     Master \--\> App\[App Controller\]  
59.     Master \--\> Tool\[Tool Controller\]  
60.     Master \--\> Gov\[Governance Controller\]  
61.     App \--\> Exec\[Execution Controller\]  
62.     Tool \--\> Exec  
63.     Exec \--\> Auto\[Automation Organ 06\]  
64.     Master \--\> Hist\[History Controller\]  
    

    ## **40\. Mermaid Sequence Diagram**

    Code snippet  
65. sequenceDiagram  
66.     participant CNS as Organ 02 (CNS)  
67.     participant Core as Controllers Core  
68.     participant Master as Master Controller  
69.     participant Gov as Governance Controller  
70.     participant Tool as Tool Controller  
71.     participant Exec as Execution Controller  
72.   
73.     CNS-\>\>Core: Dispatch Task (Tool Execution)  
74.     Core-\>\>Master: Route to Master Controller  
75.     Master-\>\>Gov: Validate Tool Parameters vs Policy  
76.     Gov--\>\>Master: Policy Approved  
77.     Master-\>\>Tool: Invoke Tool (Parameters)  
78.     Tool-\>\>Exec: Spawn Process & Monitor  
79.     Exec--\>\>Tool: Return Process Output & Exit Code  
80.     Tool--\>\>Master: Tool Task Result  
81.     Master--\>\>Core: Final Response Object  
82.     Core--\>\>CNS: Dispatch Result  
    

    ## **41\. Mermaid Flow Diagram**

    Code snippet  
83. flowchart TD  
84.     A\[Incoming Task Payload\] \--\> B\[Parse Target Controller\]  
85.     B \--\> C{Registered Controller?}  
86.     C \-- No \--\> D\[Return Unregistered Controller Error\]  
87.     C \-- Yes \--\> E\[Dispatch to Governance Controller Check\]  
88.     E \--\> F{Policy Approved?}  
89.     F \-- No \--\> G\[Emit EVENT\_GOVERNANCE\_BLOCKED\]  
90.     F \-- Yes \--\> H\[Invoke Target Domain Controller\]  
91.     H \--\> I\[Execute via Execution Controller Wrapper\]  
92.     I \--\> J{Execution Successful?}  
93.     J \-- Yes \--\> K\[Package Results & Return to CNS\]  
94.     J \-- No \--\> L\[Capture Error & Trigger Sub-Process Recovery\]  
    

    ## **42\. Mermaid State Diagram**

    Code snippet  
95. stateDiagram-v2  
96.     \[\*\] \--\> Uninitialized  
97.     Uninitialized \--\> Idle : Configuration Loaded  
98.     Idle \--\> Executing : Task Received  
99.     Executing \--\> Blocked : Awaiting Governance/Resource Lock  
100.     Blocked \--\> Executing : Unblocked  
101.     Executing \--\> Idle : Task Complete  
102.     Executing \--\> Error : Sub-Process Crash / Timeout  
103.     Error \--\> Idle : State Reset & Cleaned  
     

     ## **43\. Mermaid Folder Diagram**

     Code snippet  
104. graph TD  
105.     Root\[organ\_05\_controllers\] \--\> Bin\[bin/controllers\_daemon\]  
106.     Root \--\> Config\[config/controller\_bindings.json\]  
107.     Root \--\> Src\[src/\]  
108.     Src \--\> Core\[core/controllers\_kernel.py\]  
109.     Src \--\> Domain\[domain/\]  
110.     Domain \--\> Master\[domain/master\_controller.py\]  
111.     Domain \--\> Task\[domain/task\_controller.py\]  
112.     Domain \--\> App\[domain/app\_controller.py\]  
113.     Domain \--\> Tool\[domain/tool\_controller.py\]  
114.     Domain \--\> Exec\[domain/execution\_controller.py\]  
115.     Domain \--\> Gov\[domain/governance\_controller.py\]  
     

     ## **44\. Mermaid Socket Diagram**

     Code snippet  
116. graph LR  
117.     CNS\[CNS Master Socket\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_controllers\]  
118.     Pipe \--\> Listener\[IPC Listener Thread\]  
119.     Listener \--\> Core\[Controllers Core Engine\]  
     

     ## **45\. Mermaid Pipeline Diagram**

     Code snippet  
120. graph LR  
121.     P1\[1. IPC Ingestion\] \--\> P2\[2. Master Routing\]  
122.     P2 \--\> P3\[3. Governance Interception\]  
123.     P3 \--\> P4\[4. Domain Execution\]  
124.     P4 \--\> P5\[5. Process Monitoring\]  
125.     P5 \--\> P6\[6. Result & History Packaging\]  
     

     ## **46\. Engineering Recommendations**

* Implement Win32 `JobObjects` around all processes spawned by `execution_controller` on Windows 11 to guarantee clean tree termination of child processes upon timeout or failure.  
   MD+ 2  
* Maintain strict separation between high-level policy decision-making (`governance_controller`) and low-level process execution (`execution_controller`) to prevent privilege leakage.  
   MD+ 2

  ## **47\. Tradeoffs**

* **Domain Controller Isolation vs. Single Direct Execution Runner:** Modular domain controllers add wrapper layer function call overhead, but provide complete functional separation, robust fault isolation, and simplified testability.  
   MD+ 2  
* **Strict Governance Interception vs. Unrestricted Execution Speed:** Validating every tool invocation against `governance_controller` adds \~2-5ms pre-execution latency, but guarantees absolute compliance with Constitutional and Policy boundaries.  
   MD+ 3

  ## **48\. Alternatives Considered**

* **Monolithic Execution Engine:** Rejected because a single execution runner creates high code coupling, makes individual domain failure recovery difficult, and violates Universal Law 3\.  
   MD+ 1  
* **Direct Script Spawning via Shell:** Rejected due to lack of environment sandboxing, security risks, and inability to track sub-process lifecycles accurately.  
   MD+ 2

  ## **49\. Future Improvements**

* Dynamic controller thread scaling based on real-time task queue depth.  
   MD  
* Hardware resource quota enforcement per domain controller via Windows Job Object resource limits.  
   MD

  ## **50\. Claude Implementation Instructions**

1. Build directory structure as specified in Section 6\.  
    MD  
2. Implement `interfaces/base_controller.py` defining standard domain controller interfaces.  
    MD+ 1  
3. Build domain controller implementations in `src/domain/`.  
    MD  
4. Set up Windows Named Pipe server at `\\.\pipe\hojaiga_controllers`.  
    MD  
5. Ensure `execution_controller.py` utilizes Windows Win32 `JobObjects` for process isolation and cleanup.  
    MD  
126. 

