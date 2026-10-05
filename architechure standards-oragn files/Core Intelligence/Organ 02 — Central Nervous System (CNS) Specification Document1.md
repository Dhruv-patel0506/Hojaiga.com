# **Organ 02 — Central Nervous System (CNS) Specification Document**

## **1\. Overview**

The Central Nervous System (CNS) Organ is the core inter-organ communication, synchronization, routing, and task dispatch engine of the Hojaiga Automation Operating System. It serves as the primary message broker, session controller, socket manager, and event highway across all Hojaiga components. Operating entirely on the CPU using low-overhead IPC channels, the CNS guarantees deterministic event ordering, system-wide state synchronization, and strict execution dispatch without direct organ-to-organ coupling.

MD+ 4

## **2\. Purpose**

The purpose of the CNS Organ is to provide a fault-tolerant, high-throughput, low-latency messaging backbone that connects, orchestrates, and monitors all operational organs (Brain, Memory, Knowledge, Controllers, Automation, Security, Learning, Infrastructure, Agents, Interface, and Integration). It enforces communication contracts, manages execution pipelines, coordinates system heartbeats, and dispatches scheduled tasks while preserving zero-trust isolation boundaries between modules.

MD+ 3

## **3\. Philosophy**

In strict adherence to Chapter 8 of the Master Architecture Blueprint and Universal Law 5 (Standardized Communication), no organ in Hojaiga may directly invoke private implementation methods or access private memory buffers of another organ. All cross-organ interactions must route through the CNS via standardized sockets, pipelines, or event channels. The CNS enforces complete decoupling: organs register public sockets with the CNS Socket Manager, publish events to the CNS Event Bus, and receive dispatched payloads through deterministic pipelines.

MD+ 4

## **4\. Primary Responsibilities**

* **Event Bus Management:** Maintain publish/subscribe channels for asynchronous system-wide event distribution.  
   MD+ 1  
* **Session Bus Management:** Manage session-scoped context, state boundaries, and cross-organ session tokens.  
   MD+ 2  
* **Socket Registry & Management:** Lifecycle tracking, authorization verification, and connection pooling for IPC Named Pipes and Unix Domain Sockets.  
   MD+ 1  
* **Pipeline Orchestration:** Execution routing through sequential and parallel data transformation pipelines.  
   MD+ 1  
* **Task Scheduling & Dispatch:** Preemptive priority queuing, context-aware routing, and worker pool dispatch.  
   MD+ 1  
* **Heartbeat & Health Monitoring:** Continuous ping/pong liveness verification across all registered organ sockets.  
   MD+ 1  
* **Synchronization & Locking:** Distributed lock management, transaction synchronization, and resource access control.  
   MD+ 1

## **5\. Internal Modules**

* `cns_core`: Master orchestration kernel and lifecycle control loop.  
* `event_bus`: Pub/Sub topic router with support for prioritized and filtered subscriptions.  
* `session_bus`: State context registry for maintaining task-specific and user-session state variables.  
   MD  
* `socket_manager`: IPC Named Pipe listener, connection pool, and security validation wrapper.  
   MD+ 1  
* `pipeline_manager`: Pipeline definition parser, stage runner, and payload transformer.  
   MD  
* `scheduler`: Cron and task-queue dispatcher managing real-time execution intervals.  
   MD+ 1  
* `router`: Address lookup table routing message headers to destination organ sockets.  
   MD+ 1  
* `heartbeat_monitor`: Periodic health probe generator and dead-letter detector.  
   MD+ 1  
* `sync_engine`: Mutual exclusion locks, condition variables, and system semaphores.

## **6\. Internal Folder Structure**

/organ\_02\_cns  
├── bin/  
│   └── cns\_daemon            \# Core executable process binary  
├── config/  
│   ├── routes.json           \# Static socket routing rules  
│   └── pipelines.json        \# Pre-compiled pipeline definitions  
├── src/  
│   ├── core/  
│   │   ├── cns\_kernel.py  
│   │   └── state\_machine.py  
│   ├── bus/  
│   │   ├── event\_bus.py  
│   │   └── session\_bus.py  
│   ├── sockets/  
│   │   ├── listener.py  
│   │   ├── registry.py  
│   │   └── protocol\_frame.py  
│   ├── pipelines/  
│   │   ├── engine.py  
│   │   └── transformers.py  
│   ├── scheduling/  
│   │   ├── priority\_queue.py  
│   │   └── dispatcher.py  
│   ├── health/  
│   │   └── heartbeat.py  
│   └── sync/  
│       └── lock\_manager.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* `IPC Master Socket`: `\\.\pipe\hojaiga_cns_master` (Windows) / `/tmp/hojaiga_cns_master.sock` (Linux/Unix).  
   MD  
  * `rpc RegisterSocket(SocketRegistrationPayload)` \-\> `RegistrationResult`  
  * `rpc UnregisterSocket(SocketUnregistrationPayload)` \-\> `Ack`  
  * `rpc PublishEvent(EventEnvelope)` \-\> `PublishResult`  
  * `rpc SubscribeEvent(SubscriptionFilter)` \-\> `Stream EventEnvelope`  
  * `rpc DispatchTask(TaskPayload)` \-\> `TaskDispatchResult`  
  * `rpc ExecutePipeline(PipelineExecutionPayload)` \-\> `PipelineResult`  
  * `rpc AcquireLock(LockRequest)` \-\> `LockGrant`  
  * `rpc ReleaseLock(LockRelease)` \-\> `Ack`  
  * `rpc SendHeartbeat(HeartbeatFrame)` \-\> `HeartbeatAck`

## **8\. Internal Interfaces**

* `ISocketRegistry`:  
  * `bind_socket(organ_id, endpoint)`: Maps organ identifiers to active physical IPC endpoints.  
  * `resolve_route(destination_organ)`: Retrieves target IPC endpoint from routing lookup table.  
* `IPipelineRunner`:  
  * `compile_pipeline(pipeline_id)`: Loads stage definitions and binds input/output transformers.  
  * `execute_stage(stage_id, input_payload)`: Runs atomic data transformation and forwards result.  
* `IHealthCheck`:  
  * `ping_organ(organ_id)`: Issues low-level IPC health query to targeted organ socket.

## **9\. Socket Definitions**

* Master Listening Socket: `hojaiga_cns_master`.  
   MD  
* Transport Protocol: Named Pipes (Windows API `CreateNamedPipeW`) / Unix Domain Sockets (`AF_UNIX`).  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length (uint32) | 2-byte message\_type (uint16) | Payload (JSON/Protobuf) \].  
* Maximum Payload Length: 32 MB per single frame transmission.

## **10\. Pipeline Definitions**

* `StandardTaskDispatchPipeline`:  
  1. CNS Ingests Task Payload \-\> 2\. Security Organ Socket Validation \-\> 3\. Brain Organ Execution Planning \-\> 4\. Knowledge/Memory Organ Context Enrichment \-\> 5\. Execution Controller/Automation Organ Execution \-\> 6\. Result Validation \-\> 7\. History Append & Return.  
      MD+ 2  
* `EventBroadcastPipeline`:  
  1. Producer Emits Event \-\> 2\. CNS Schema Validation \-\> 3\. Session Context Verification \-\> 4\. Subscriber Filter Matching \-\> 5\. Parallel Fan-Out Dispatch to Subscribed Sockets.  
      MD+ 2

## **11\. Incoming Connections**

* All Hojaiga Organs (01 Brain, 03 Memory, 04 Knowledge, 05 Controllers, 06 Automation, 07 Security, 08 Learning, 09 Infrastructure, 10 Agents, 11 Interface, 12 Integration) connect to `hojaiga_cns_master` upon process initialization.  
   MD+ 1

## **12\. Outgoing Connections**

* CNS establishes dedicated client Named Pipe connections back to individual organ listening sockets (`\\.\pipe\hojaiga_organ_01` through `\\.\pipe\hojaiga_organ_12`) for asynchronous payload delivery and event fan-out.  
   MD+ 1

## **13\. State Management**

The CNS operates a finite state machine managing global operating readiness:

* `BOOTSTRAPPING`: Initializing master sockets, parsing static routes, waiting for core organs.  
   MD  
* `OPERATIONAL`: All essential organ sockets bound; handling dynamic task dispatches and event fan-outs.  
   MD  
* `DEGRADED`: One or more non-essential organs unaligned or failed heartbeat checks; restricted task dispatch enabled.  
   MD+ 1  
* `PAUSED`: Execution suspended by Security Organ or human operator request; queueing incoming events.  
   MD+ 2  
* `SHUTTING_DOWN`: Flushing queues, signaling graceful shutdown frames to all bound sockets, closing pipes.  
   MD+ 1

## **14\. Event Definitions**

* `EVENT_CNS_STARTED`: Emitted when the master socket registry completes initial bind.  
* `EVENT_ORGAN_CONNECTED`: Fired when an organ successfully handshakes with `hojaiga_cns_master`.  
* `EVENT_ORGAN_DISCONNECTED`: Fired on pipe disconnection or heartbeat failure.  
* `EVENT_TASK_QUEUED`: Emitted when a task enters the high-priority execution scheduling queue.  
   MD  
* `EVENT_TASK_DISPATCHED`: Emitted when a task payload is routed to an execution target.  
   MD  
* `EVENT_DEAD_LETTER_LOGGED`: Fired when a message cannot be delivered after maximum retries.  
   MD+ 2

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "CNSEventEnvelope",  
  "type": "object",  
  "properties": {  
    "event\_id": { "type": "string", "format": "uuid" },  
    "session\_id": { "type": "string", "format": "uuid" },  
    "source\_organ": { "type": "string" },  
    "topic": { "type": "string" },  
    "timestamp": { "type": "integer" },  
    "priority": { "type": "integer", "minimum": 0, "maximum": 5 },  
    "payload": { "type": "object" }  
  },  
  "required": \["event\_id", "session\_id", "source\_organ", "topic", "timestamp", "payload"\]  
}

## **16\. Internal Database Structures**

The CNS maintains an in-memory SQLite database (`cns_runtime.db` in `:memory:`) for rapid routing and lock tables:

* Table `socket_registry` (`organ_id` TEXT PRIMARY KEY, `endpoint_path` TEXT, `connected_at` TIMESTAMP, `status` TEXT, `last_heartbeat` TIMESTAMP).  
   MD+ 1  
* Table `active_locks` (`resource_id` TEXT PRIMARY KEY, `holding_organ` TEXT, `acquired_at` TIMESTAMP, `expires_at` TIMESTAMP).  
   MD+ 1  
* Table `task_queue` (`task_id` TEXT PRIMARY KEY, `priority` INTEGER, `source_organ` TEXT, `target_organ` TEXT, `payload_blob` BLOB, `created_at` TIMESTAMP).  
   MD+ 1

## **17\. Cache Strategy**

* Address Lookup Cache: In-memory hash table caching resolved organ socket descriptors to avoid SQLite lookups on high-frequency event dispatches.  
* Topic Subscription Map: Bitmask indexed array matching event topic pattern strings directly to active subscriber socket pointers.

## **18\. Memory Strategy**

* Total resident RAM usage maintained strictly under 256 MB.  
* Circular ring buffers used for high-frequency pub/sub queues to prevent dynamic heap fragmentation.  
* Payload pass-through uses shared memory blocks (`CreateFileMapping` / `mmap`) for binary payloads exceeding 1 MB to minimize memory copying overhead.

## **19\. Thread Safety**

* Thread-safe lock-free queues (`RingBuffer`) for lockless single-producer/single-consumer IPC receiver threads.  
* Global mutex wrappers (`pthread_mutex` / Windows `CRITICAL_SECTION`) guarding socket table registration and task queue updates.

## **20\. Concurrency**

* Asynchronous I/O processing model driven by Windows Completion Ports (IOCP) or Linux `epoll`.  
* Multi-threaded worker pool (fixed at CPU physical core count \= 8 threads) for payload schema parsing and pipeline stage evaluations.  
   MD

## **21\. Hardware Optimization**

* CPU-first architecture: Implemented entirely in native code / high-performance asynchronous runtime targeting Intel Core i7.  
   MD  
* SIMD vector instructions utilized for high-speed payload hashing and frame checksum validation.

## **22\. GPU Usage**

* Zero GPU usage. The CNS does not allocate VRAM or invoke CUDA libraries.  
   MD

## **23\. CPU Usage**

* Highly efficient thread synchronization ensures \<1% CPU utilization when idle.  
   MD  
* Peak CPU usage capped at 15% during heavy parallel event broadcasting across all 12 organs.  
   MD

## **24\. SSD Usage**

* Master configuration files (`routes.json`, `pipelines.json`) and temporary overflow buffers written to SSD runtime partition (`100 GB SSD Runtime`).  
   MD

## **25\. HDD Usage**

* Event message audit logs and dead-letter payloads archived sequentially to the external HDD log store via non-blocking write streams.  
   MD+ 1

## **26\. Security Model**

* Capability-based security verification: CNS validates that the originating socket possesses explicit permissions to emit to the targeted socket or pub/sub topic.  
   MD+ 2  
* Payload Schema Enforcement: Rejects malformed JSON/Protobuf messages before routing.  
   MD+ 1

## **27\. Permissions**

* CNS process runs under the main user security context on Windows 11\.  
   MD  
* Restricts Named Pipe permissions via DACLs to permit connections strictly from local processes owned by the same user account.  
   MD+ 1

## **28\. Logging**

* Structured binary/JSON logging following Policy Manual Chapter 8\.  
   MD  
* Records `event_id`, `source_organ`, `destination_organ`, `routing_latency_us`, `payload_size_bytes`, and `status_code`.  
   MD+ 1

## **29\. History Recording**

* Every dispatched task and system event frame metadata is appended to the operational history database on external HDD.  
   MD+ 2

## **30\. Recovery Strategy**

* Socket Reconnection Handler: Auto-detects broken IPC pipes, removes dead socket handles from active routing tables, enters organ recovery state, and listens for organ process auto-restart handshakes.  
   MD+ 2

## **31\. Failure Handling**

* Unroutable Payload: Message redirected to Dead Letter Queue (DLQ), error logged, emitting organ notified via `EVENT_DEAD_LETTER_LOGGED`.  
   MD+ 2  
* Heartbeat Timeout: If an organ fails 3 consecutive heartbeat pings (interval 1000ms), CNS marks organ `OFFLINE` and notifies Security & Infrastructure Organs.  
   MD+ 2

## **32\. Validation Rules**

* Every message header must contain valid UUIDv4 `event_id`, valid source organ ID, valid target/topic, and integer timestamp within ±5000ms of system clock.  
   MD+ 1

## **33\. Testing Strategy**

* Unit tests covering pipe framing, ring buffer enqueue/dequeue, and topic pattern matching.  
* Stress testing: Simulating 100,000 events/sec across 12 concurrent mock organ sockets to measure latency and queue saturation limits.

## **34\. Extension Points**

* Custom Pipeline Transformers: Plug-in architecture allowing custom serialization/deserialization routines within pipeline definitions.  
   MD+ 1  
* Custom Scheduler Drivers: Allows adding cron-like or event-driven schedule rules.  
   MD

## **35\. Future Compatibility**

* Forward-compatible protocol framing incorporating a 2-byte version header field in all wire packets, permitting live side-by-side protocol migrations.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` CNS Core API. Protocol changes breaking frame header structure require major version bump.  
   MD+ 1

## **37\. Dependencies**

* C++20 / Python 3.11 asynchronous kernel libraries.  
   MD  
* Windows Win32 API (`NamedPipe`, `IOCP`) / POSIX Sockets (`AF_UNIX`, `epoll`).  
   MD

## **38\. Interaction with Other Organs**

* **Brain (Organ 01):** Dispatches high-level execution plans compiled by Brain to functional organ targets.  
   MD  
* **Security (Organ 07):** Queries Security for socket permission validation before granting pipe bindings.  
   MD+ 2  
* **Infrastructure (Organ 09):** Receives system monitoring telemetry from CNS heartbeat monitors.  
   MD+ 1

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    ClientOrgans\[Organs 01-12\] \--\>|Named Pipe / Unix Sock| SocketMgr\[Socket Manager\]  
    SocketMgr \--\> Protocol\[Protocol Frame Parser\]  
    Protocol \--\> Router\[Message Router & Dispatcher\]  
    Router \--\> EventBus\[Event Bus Pub/Sub\]  
    Router \--\> PipeEngine\[Pipeline Engine\]  
    Router \--\> Queue\[Priority Task Scheduler\]  
    EventBus \--\> SessionBus\[Session Context Bus\]  
    Heartbeat\[Heartbeat Monitor\] \--\> SocketMgr

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant OrgA as Organ 01 (Brain)  
    participant CNS as CNS Master Socket  
    participant Sec as Organ 07 (Security)  
    participant OrgB as Organ 06 (Automation)

    OrgA-\>\>CNS: Send Message Frame (Target: Automation, Payload: Plan)  
    CNS-\>\>Sec: Validate Routing Permission(OrgA \-\> OrgB)  
    Sec--\>\>CNS: Permission Granted  
    CNS-\>\>CNS: Queue Task in Priority Queue  
    CNS-\>\>OrgB: Dispatch Payload Frame via IPC Pipe  
    OrgB--\>\>CNS: Acknowledge Frame Handshake  
    CNS--\>\>OrgA: Return Dispatch Success Context

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Incoming IPC Frame\] \--\> B\[Parse Wire Header & Checksum\]  
    B \--\> C{Header Valid?}  
    C \-- No \--\> D\[Drop Frame & Log Error\]  
    C \-- Yes \--\> E\[Validate Permissions via Security Registry\]  
    E \--\> F{Authorized?}  
    F \-- No \--\> G\[Emit EVENT\_SECURITY\_VIOLATION\]  
    F \-- Yes \--\> H{Message Type}  
    H \-- Event Pub \--\> I\[Fan-Out to Topic Subscribers\]  
    H \-- Task Execution \--\> J\[Enqueue in Priority Task Scheduler\]  
    H \-- Direct RPC \--\> K\[Route directly to Destination Pipe\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Bootstrapping  
    Bootstrapping \--\> Operational : Core Organs Bound  
    Operational \--\> Degraded : Non-Essential Organ Heartbeat Lost  
    Degraded \--\> Operational : Organ Reconnected  
    Operational \--\> Paused : Admin/Security Pause Lock  
    Paused \--\> Operational : Resume Signal  
    Operational \--\> ShuttingDown : Termination Initiated  
    ShuttingDown \--\> \[\*\]

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_02\_cns\] \--\> Bin\[bin/cns\_daemon\]  
    Root \--\> Config\[config/routes.json\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/cns\_kernel.py\]  
    Src \--\> Bus\[bus/event\_bus.py\]  
    Src \--\> Sockets\[sockets/listener.py\]  
    Src \--\> Pipelines\[pipelines/engine.py\]  
    Src \--\> Scheduling\[scheduling/dispatcher.py\]  
    Src \--\> Health\[health/heartbeat.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    O1\[Brain Sock\] \<--\>|IPC Pipe| CNS\[hojaiga\_cns\_master\]  
    O3\[Memory Sock\] \<--\>|IPC Pipe| CNS  
    O6\[Automation Sock\] \<--\>|IPC Pipe| CNS  
    O7\[Security Sock\] \<--\>|IPC Pipe| CNS  
    CNS \<--\>|IPC Pipe| OX\[Organs 04,05,08-12 Sockets\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    Stage1\[1. Payload Ingestion\] \--\> Stage2\[2. Schema & Auth Check\]  
    Stage2 \--\> Stage3\[3. Priority Queue Selection\]  
    Stage3 \--\> Stage4\[4. Data Transformation Engine\]  
    Stage4 \--\> Stage5\[5. Socket Routing\]  
    Stage5 \--\> Stage6\[6. Receipt Verification\]

## **46\. Engineering Recommendations**

* Use Windows IO Completion Ports (IOCP) for socket listener implementations on Windows 11 to achieve maximum throughput with minimal CPU worker thread context switches.  
   MD  
* Enforce strict timeout windows (500ms max) on socket read/write operations to prevent slow or frozen organ processes from blocking CNS dispatcher threads.  
   MD+ 1

## **47\. Tradeoffs**

* **Centralized CNS Broker vs. Direct Organ Mesh:** Centralized routing adds a microsecond-level hop latency between organs, but provides total isolation, centralized governance, strict contract enforcement, and simple audit logging.  
   MD+ 2  
* **IPC Named Pipes vs. Shared Memory Buffers:** Named Pipes introduce small serialization overhead compared to raw shared memory, but provide complete OS-level process boundary safety and thread protection.  
   MD+ 1

## **48\. Alternatives Considered**

* **gRPC over HTTP/2 Local Loopback:** Rejected due to HTTP header parsing overhead, high memory footprint, and CPU costs compared to raw binary length-prefixed IPC frames.  
   MD  
* **ZeroMQ / RabbitMQ External Broker:** Rejected to eliminate third-party daemon runtime dependencies and preserve strict CPU/RAM footprint limits on host hardware.  
   MD

## **49\. Future Improvements**

* Implementation of Zero-Copy shared memory buffers (`CreateFileMapping` handles) automatically leveraged for payloads \> 5 MB.  
   MD  
* Adaptive dynamic task queue prioritization based on real-time execution duration telemetry.  
   MD

## **50\. Claude Implementation Instructions**

1. Build `organ_02_cns` runtime using Python 3.11 `asyncio` loop integrated with native C++ IOCP bindings for Windows 11\.  
    MD  
2. Implement binary packet header parsing (4-byte length \+ 2-byte type \+ JSON body).  
    MD  
3. Establish Named Pipe server at `\\.\pipe\hojaiga_cns_master`.  
    MD  
4. Implement heartbeating loop checking all connected organ sockets every 1000ms.  
    MD+ 1  
5. Ensure all message dispatches evaluate permissions against Security Organ registry.  
    MD+ 2

