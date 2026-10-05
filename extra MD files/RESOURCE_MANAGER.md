# **RESOURCE\_MANAGER.MD**

**Component:** Resource Manager Layer

**Target System:** Hojaiga Automation Operating System (AOS)

**System Layer:** Core Service Layer / Resource Management Engine

**Document Status:** Production Architecture Specification

# **1\. RESOURCE MANAGER ARCHITECTURE**

The Resource Manager serves as the centralized hardware and software resource orchestrator for the Hojaiga Automation Operating System (AOS). No organ, runtime, or connector is permitted to directly reserve or allocate physical compute, memory, storage, or execution threads. All requests are mediated via strict ticket-based lease assignments issued by the Resource Manager.

\+---------------------------------------------------------------------------------------------------+  
|                                            KERNEL LAYER                                           |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         RESOURCE MANAGER                                          |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
|  |     Resource Core     |     |   Resource Registry   |     |          Quota Manager          |  |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         RESOURCE SCHEDULER                                        |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
|  |   Priority Scheduler  |     |     Queue Manager     |     |          Load Balancer         |  |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         ALLOCATION ENGINE                                         |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
|  |  CPU Mgr   |  |  RAM Mgr   |  |  GPU Mgr   |  |  VRAM Mgr  |  |  Disk Mgr  |  | Thread/Worker |  |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         MONITORING ENGINE                                         |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
|  |    Thermal Monitor    |     |     Power Monitor     |     |         Health Monitor          |  |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                           HARDWARE LAYER                                          |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
|  | Core i7    |  | 32GB RAM   |  | RTX 3050   |  | 4GB VRAM   |  | 100GB SSD  |  | External HDD  |  |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         SUBSYSTEM CONSUMERS                                       |  
|  \+------------------+  \+------------------+  \+----------------------+  \+-----------------------+  |  
|  |      Organs      |  |     Runtimes     |  | External Connectors  |  |    Shared Services    |  |  
|  \+------------------+  \+------------------+  \+----------------------+  \+-----------------------+  |  
\+---------------------------------------------------------------------------------------------------+

# **2\. TARGET HARDWARE BASELINE & EXTENSIBILITY**

The baseline architecture is optimized for a single-node host running Windows OS with the following physical constraints:

* **Processor:** Intel Core i7 Processor (Multi-core, Hybrid P/E-core architecture topology).  
* **System Memory:** 32GB DDR4/DDR5 System RAM.  
* **Discrete GPU:** NVIDIA GeForce RTX 3050 Laptop/Desktop GPU.  
* **Video RAM:** 4GB Dedicated GDDR6 VRAM.  
* **Primary High-Speed Storage:** 100GB SSD Runtime partition (OS, transient caches, active databases, low-latency execution workspaces).  
* **Secondary Mass Storage:** External HDD Model Repository (Models, vector index backups, historical logs, cold data archives).  
* **Operating System:** Windows Operating System (Win32 / Native NT API abstractions & Win32 Cgroup-equivalent Job Objects).

### **Extensibility Guarantees:**

1. **Multi-GPU Dynamic Layer:** Abstract GPU IDs using virtual CUDA device ordinal handles (vgpu:0, vgpu:1).  
2. **Distributed & Remote Worker Interfaces:** Resource allocation endpoints communicate using RPC/ZeroMQ socket messages, permitting worker pool scaling across network nodes without changing interface semantics.  
3. **Hybrid Accelerator Abstractions:** GPU/VRAM engines expose an abstract IAccelerator API, supporting future NPU, TPU, or DirectML device backends.

# **3\. MERMAID DIAGRAMS**

## **3.1 Overall Resource Architecture**

Code snippet  
graph TD  
    Kernel(\[Kernel Core\]) \--\> RC\[Resource Core\]  
    RC \--\> Reg\[Resource Registry\]  
    RC \--\> QM\[Quota Manager\]  
    RC \--\> RS\[Resource Scheduler\]  
    RS \--\> PS\[Priority Scheduler\]  
    RS \--\> Queue\[Queue Manager\]  
    RS \--\> AE\[Allocation Engine\]  
    AE \--\> CPU\[CPU Manager\]  
    AE \--\> RAM\[RAM Manager\]  
    AE \--\> GPU\[GPU Manager\]  
    AE \--\> VRAM\[VRAM Manager\]  
    AE \--\> Disk\[Disk Manager\]  
    AE \--\> Thread\[Thread/Worker Manager\]  
    CPU \--\> HW\_CPU\[Intel Core i7\]  
    RAM \--\> HW\_RAM\[32GB System RAM\]  
    GPU \--\> HW\_GPU\[NVIDIA RTX 3050\]  
    VRAM \--\> HW\_VRAM\[4GB Dedicated VRAM\]  
    Disk \--\> HW\_SSD\[100GB SSD Runtime\]  
    Disk \--\> HW\_HDD\[External HDD Repo\]  
    AE \--\> Mon\[Monitoring Engine\]  
    Mon \--\> HW\_CPU  
    Mon \--\> HW\_GPU  
    AE \--\> Sub\[Subsystem Consumers: Organs / Runtimes / Connectors\]

## **3.2 CPU Allocation Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant C as Consumer Process  
    participant Core as Resource Core  
    participant CPU as CPU Manager  
    participant OS as Windows Win32 API

    C-\>\>Core: Request CPU Allocation (Thread Count, Priority, Class)  
    Core-\>\>CPU: Evaluate CPU Capacity & Affinity  
    CPU-\>\>CPU: Determine Core Type (P-Core vs E-Core)  
    alt Allocation Permitted  
        CPU-\>\>OS: SetThreadAffinityMask() / SetPriorityClass()  
        OS--\>\>CPU: Handle / Mask Confirmed  
        CPU--\>\>Core: Lease Issued (CPU Lease Ticket)  
        Core--\>\>C: Return Execution Lease Handle  
    else Quota / Core Limit Exceeded  
        CPU--\>\>Core: Allocation Denied (Capacity Saturation)  
        Core--\>\>C: Enqueue Request / Return Throttled Status  
    end

## **3.3 RAM Allocation Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant C as Consumer Process  
    participant Core as Resource Core  
    participant RAM as RAM Manager  
    participant Pool as Memory Pool Engine

    C-\>\>Core: Request RAM Allocation (Bytes, Pool Class)  
    Core-\>\>RAM: Check Quota & Global RAM Pressure  
    alt RAM Pressure \< 85%  
        RAM-\>\>Pool: Reserve Slice from Shared/Temporary Buffer  
        Pool--\>\>RAM: Memory Pointer / Descriptor  
        RAM--\>\>Core: Allocation Lease Confirmed  
        Core--\>\>C: Grant Memory Lease  
    else RAM Pressure \>= 85%  
        RAM-\>\>RAM: Trigger Lazy Cache Eviction & GC  
        RAM-\>\>Core: Signal Memory Pressure Warning  
        alt RAM Pressure \< 92% Post-Eviction  
            RAM-\>\>Pool: Reserve Memory Slice  
            Pool--\>\>RAM: Memory Pointer  
            RAM--\>\>Core: Grant Lease  
        else RAM Pressure \>= 92% (OOM Danger)  
            RAM--\>\>Core: Deny Allocation / Preempt Low-Priority  
            Core--\>\>C: Return Out-Of-Memory Error  
        end  
    end

## **3.4 GPU Scheduling**

Code snippet  
flowchart TD  
    Start(\[Inference/Compute Request\]) \--\> CheckGPU{Is RTX 3050 Idle?}  
    CheckGPU \-- Yes \--\> LockGPU\[Acquire GPU Mutex Lock\]  
    LockGPU \--\> Dispatch\[Dispatch CUDA Kernel Execution\]  
    Dispatch \--\> ReleaseGPU\[Release GPU Mutex Lock\] \--\> End(\[Execution Complete\])  
    CheckGPU \-- No \--\> CheckPrio{Request Priority \> Active Task?}  
    CheckPrio \-- Yes \--\> Preempt\[Preempt/Pause Low-Prio CUDA Context\]  
    Preempt \--\> LockGPU  
    CheckPrio \-- No \--\> QueueTask\[Insert Request into Priority Queue\]  
    QueueTask \--\> Wait\[Wait for GPU Idle Signal\]  
    Wait \--\> CheckGPU

## **3.5 VRAM Allocation**

Code snippet  
flowchart TD  
    A(\[VRAM Reservation Request\]) \--\> B{Requested MB \<= Available VRAM?}  
    B \-- Yes \--\> C\[Allocate CUDA VRAM Block\]  
    C \--\> D\[Update VRAM Registry Tracker\]  
    D \--\> E(\[Return VRAM Pointer Lease\])  
    B \-- No \--\> F{Is Model Unload Permitted?}  
    F \-- Yes \--\> G\[Unload Lowest Priority Idle Model Weights\]  
    G \--\> H\[Flush PyTorch / CUDA Context Cache\]  
    H \--\> B  
    F \-- No \--\> I{Can Automation Playwright Headless Budget Scale Down?}  
    I \-- Yes \--\> J\[Purge Offscreen Playwright Canvas Buffers\]  
    J \--\> B  
    I \-- No \--\> K\[Reject Request: VRAM Exhaustion\]

## **3.6 Disk Management**

Code snippet  
flowchart TD  
    A(\[Disk I/O Request\]) \--\> B{Target Storage Volume?}  
    B \-- High IOPS / Runtime \--\> C\[SSD Runtime Manager / 100GB Volume\]  
    B \-- Cold Storage / Models \--\> D\[External HDD Manager / Mass Repo\]  
    C \--\> E{SSD Space \> 10% Free?}  
    E \-- Yes \--\> F\[Execute Fast NVMe Direct Write\]  
    E \-- No \--\> G\[Trigger Log Rotation & Temp Workspace Cleanup\]  
    G \--\> F  
    D \--\> H{External HDD Volume Mounted?}  
    H \-- Yes \--\> I\[Execute Buffered Sequential Write\]  
    H \-- No \--\> J\[Queue Write to SSD Buffer & Raise Mount Request\]

## **3.7 Scheduler Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant Sub as Subsystem Consumer  
    participant Queue as Queue Manager  
    participant PS as Priority Scheduler  
    participant Exec as Execution Engine

    Sub-\>\>Queue: Submit Task (TaskSpec, Priority, ResourceRequirements)  
    Queue-\>\>PS: Re-evaluate Heap Order  
    PS-\>\>PS: Calculate Dynamic Priority Score  
    PS-\>\>Exec: Select Top Task for Execution Slot  
    Exec-\>\>Exec: Verify Resource Lease Availability  
    alt Resources Available  
        Exec--\>\>Sub: Dispatch Task Execution Ticket  
    else Resource Constrained  
        Exec-\>\>PS: Return Task to Queue (Preemption Hold)  
    end

## **3.8 Monitoring Flow**

Code snippet  
flowchart TD  
    A(\[Monitoring Interval Tick: 500ms\]) \--\> B\[Poll CPU & System RAM Usage\]  
    B \--\> C\[Poll NVML API: GPU Usage, VRAM, Temp\]  
    C \--\> D\[Poll Storage Volumes: SSD & HDD Capacity/IOPS\]  
    D \--\> E{Thermal Level \> 85°C?}  
    E \-- Yes \--\> F\[Emit Thermal Throttle Event & Scale Down GPU Freq\]  
    E \-- No \--\> G{RAM Usage \> 85% or VRAM \> 90%?}  
    G \-- Yes \--\> H\[Emit Resource Warning & Trigger Cleanup Manager\]  
    G \-- No \--\> I\[Update Metrics Stream & Resource Registry\]

## **3.9 Recovery Flow**

Code snippet  
flowchart TD  
    A(\[Resource Failure Event\]) \--\> B{Identify Failure Type}  
    B \-- Out Of Memory \--\> C\[Execute OOM Cleanup: Kill Background Tasks\]  
    B \-- GPU Lockup / Driver Reset \--\> D\[Re-initialize NVML Context & Rebind CUDA\]  
    B \-- Disk Full \--\> E\[Force Purge Cache / Temp Files / Old Logs\]  
    B \-- Thread Starvation \--\> F\[Expand Thread Pool / Terminate Deadlocks\]  
    C \--\> G{Recovery Successful?}  
    D \--\> G  
    E \--\> G  
    F \--\> G  
    G \-- Yes \--\> H\[Resume Task Processing\]  
    G \-- No \--\> I\[Escalate to Safe Mode / Alert Kernel\]

## **3.10 State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Uninitialized  
    Uninitialized \--\> Initializing: Boot Signal  
    Initializing \--\> Normal: Hardware Probed & Baselines Loaded  
    Normal \--\> Throttled: High Thermal or Power Constraint  
    Throttled \--\> Normal: Temperature Normalization  
    Normal \--\> Degradation: Resource Exhaustion (RAM/VRAM \> 90%)  
    Degradation \--\> Normal: Cleanup & Eviction Successful  
    Degradation \--\> Critical: Recovery Failed  
    Critical \--\> RecoveryMode: Enforce Safe Allocation Caps  
    RecoveryMode \--\> Normal: Manual or System Self-Heal

## **3.11 Deployment Diagram**

Code snippet  
graph LR  
    subgraph Host Hardware Engine  
        CPU\_HW\[Intel Core i7\]  
        RAM\_HW\[32GB RAM\]  
        GPU\_HW\[NVIDIA RTX 3050\]  
        SSD\_HW\[100GB SSD\]  
        HDD\_HW\[External HDD\]  
    end

    subgraph Windows NT Environment  
        WinJob\[Win32 Job Objects\]  
        NVML\[NVIDIA NVML Driver API\]  
        WinIO\[Win32 Overlapped File I/O\]  
    end

    subgraph AOS Resource Manager Engine  
        RMCore\[Resource Core\]  
        RMCpu\[CPU/Thread Manager\]  
        RMGpu\[GPU/VRAM Manager\]  
        RMDisk\[Disk Storage Manager\]  
    end

    RMCpu \--\> WinJob \--\> CPU\_HW  
    RMCpu \--\> RAM\_HW  
    RMGpu \--\> NVML \--\> GPU\_HW  
    RMDisk \--\> WinIO \--\> SSD\_HW  
    RMDisk \--\> WinIO \--\> HDD\_HW

## **3.12 Folder Diagram**

/aos/resource\_manager/  
├── bin/  
├── config/  
├── include/  
├── src/  
│   ├── core/  
│   ├── allocation/  
│   ├── hardware/  
│   ├── scheduler/  
│   ├── monitoring/  
│   ├── comm/  
│   └── utils/  
└── tests/

# **4\. RESOURCE MODULES SPECIFICATION**

## **4.1 Resource Core**

* **Purpose:** Serves as the central command plane for all resource reservation, allocation validation, and lease tracking.  
* **Responsibilities:** Mediating consumer resource requests, enforcing lease timeouts, orchestrating sub-managers.  
* **Inputs:** Consumer resource requests (ResourceRequestSpec), lease revocation commands, kernel control flags.  
* **Outputs:** Resource Lease Handles (LeaseTicket), capacity status descriptors.  
* **Dependencies:** None (Base resource layer).  
* **Sockets:** Resource Socket, Quota Socket.  
* **Pipelines:** Allocation Pipeline, Reservation Pipeline.  
* **Failure Modes:** Internal concurrency deadlock, lease tracking corruption.  
* **Recovery:** Re-evaluate all active process leases against physical OS telemetry; flush stale lease tables.  
* **Future Expansion:** Dynamic lease routing for multi-node clusters.

## **4.2 CPU Manager**

* **Purpose:** Handles CPU core discovery, thread affinity mapping, priority class assignments, and load distribution across Intel Core i7 P/E-cores.  
* **Responsibilities:** Binding latency-sensitive tasks to Performance cores (P-cores) and background tasks to Efficiency cores (E-cores); setting Win32 process/thread priorities.  
* **Inputs:** Core allocation requests, task execution class profiles.  
* **Outputs:** Win32 Thread Affinity Masks, Priority Class Handle bindings.  
* **Dependencies:** Resource Core, Thermal Monitor.  
* **Sockets:** CPU Socket.  
* **Pipelines:** Allocation Pipeline, Scheduling Pipeline.  
* **Failure Modes:** Thread affinity binding error, core saturation (100% load on all logical processors).  
* **Recovery:** Unbind explicit core affinities; fallback to standard Windows OS NT scheduler load balancing.  
* **Future Expansion:** Automatic NUMA node detection and dynamic affinity scheduling for multi-socket servers.

## **4.3 RAM Manager**

* **Purpose:** Manages allocation, pooling, shared memory buffers, and virtual memory pressure across 32GB System RAM.  
* **Responsibilities:** Partitioning memory pools, monitoring physical page pressure, executing lazy cache evictions.  
* **Inputs:** Memory allocation requests (bytes), memory pool class identifiers.  
* **Outputs:** Virtual memory pointers, page pool leases, memory pressure warning alerts.  
* **Dependencies:** Resource Core, Health Monitor.  
* **Sockets:** Memory Socket.  
* **Pipelines:** Allocation Pipeline, Recovery Pipeline.  
* **Failure Modes:** Allocation failure, RAM utilization exceeding 92% (OOM condition).  
* **Recovery:** Force garbage collection across execution runtimes; flush transient in-memory vector caches; terminate lowest priority background workers.  
* **Future Expansion:** Compressed RAM swap ring buffers.

## **4.4 GPU Manager**

* **Purpose:** Orchestrates compute access, CUDA driver validation, and inference lock scheduling for the NVIDIA RTX 3050 GPU.  
* **Responsibilities:** Managing single-GPU access concurrency via mutexes; enforcing inference time-slicing; handling fallback to CPU execution paths.  
* **Inputs:** CUDA execution requests, inference batch jobs, context lock release signals.  
* **Outputs:** CUDA Device Context handles, execution leases, GPU lock states.  
* **Dependencies:** Resource Core, Thermal Monitor, Power Monitor.  
* **Sockets:** GPU Socket.  
* **Pipelines:** Allocation Pipeline, Scheduling Pipeline.  
* **Failure Modes:** CUDA driver crash (CUDA\_ERROR\_UNKNOWN), GPU hardware lockup, NVML API unresponsiveness.  
* **Recovery:** Re-initialize NVML driver interface bindings; flush CUDA execution contexts; route non-critical inferences to CPU runtime fallback.  
* **Future Expansion:** Multi-GPU scheduling layer supporting CUDA device ordinal array topologies.

## **4.5 VRAM Manager**

* **Purpose:** Tracks and allocates the dedicated 4GB GDDR6 VRAM footprint across LLM models, automation browsers (Playwright), and compute workflows.  
* **Responsibilities:** Maintaining static/dynamic VRAM memory maps; executing model weight unloads on capacity shortage; preventing VRAM fragmentation.  
* **Inputs:** VRAM allocation specs (MB), model loading profiles, buffer request parameters.  
* **Outputs:** VRAM block offsets, model reservation tickets, allocation failure alerts.  
* **Dependencies:** GPU Manager, Resource Core.  
* **Sockets:** GPU Socket, Memory Socket.  
* **Pipelines:** Allocation Pipeline, Cleanup Pipeline.  
* **Failure Modes:** VRAM Out-Of-Memory (CUDA\_ERROR\_OUT\_OF\_MEMORY), VRAM fragmentation preventing contiguous tensor allocation.  
* **Recovery:** Purge offscreen Playwright render buffers; unload idle LLM model weights from VRAM; issue CUDA context cache resets.  
* **Future Expansion:** Unified virtual VRAM paging using unified memory architectures across system RAM.

## **4.6 Disk Manager**

* **Purpose:** Oversees high-level storage volume abstractions, I/O bandwidth routing, and partition space policies.  
* **Responsibilities:** Directing read/write ops to appropriate storage devices based on performance targets; monitoring total free space.  
* **Inputs:** File I/O registration requests, volume performance specs.  
* **Outputs:** Target storage path descriptors, IOPS lease parameters.  
* **Dependencies:** SSD Manager, External HDD Manager.  
* **Sockets:** Disk Socket.  
* **Pipelines:** Allocation Pipeline, Cleanup Pipeline.  
* **Failure Modes:** Volume unmount, storage space exhaustion (\< 5% free space).  
* **Recovery:** Redirect write streams to secondary volumes; invoke Cleanup Manager to purge temporary files and rotated logs.  
* **Future Expansion:** Distributed POSIX virtual filesystem layer.

## **4.7 SSD Manager**

* **Purpose:** Optimizes the 100GB SSD Runtime partition for high-speed, low-latency execution workspaces, database files, and transient runtime caches.  
* **Responsibilities:** Managing temporary file lifecycles; maintaining database write-buffers; preventing SSD write-wear saturation.  
* **Inputs:** SSD allocation/write requests, cache staging data streams.  
* **Outputs:** File handles on /ssd/runtime/, direct I/O channel descriptors.  
* **Dependencies:** Disk Manager.  
* **Sockets:** Disk Socket.  
* **Pipelines:** Allocation Pipeline, Cleanup Pipeline.  
* **Failure Modes:** SSD runtime volume full, write-rate throttling detected.  
* **Recovery:** Move aged runtime logs and cold cache buffers from SSD partition to External HDD storage.  
* **Future Expansion:** Direct NVMe queue depth management via native Win32 NVMe pass-through drivers.

## **4.8 External HDD Manager**

* **Purpose:** Manages the high-capacity, cold/mass storage repository hosted on the External HDD (LLM model weight archives, knowledge DB snapshots).  
* **Responsibilities:** Managing model weight streaming; tracking external USB/SATA drive mount states; buffering slow sequential reads/writes.  
* **Inputs:** Model load requests, archive store read/write operations.  
* **Outputs:** File streams from external mass storage, volume availability status.  
* **Dependencies:** Disk Manager.  
* **Sockets:** Disk Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Drive disconnected/unmounted unexpectedly, slow read IOPS causing execution timeouts.  
* **Recovery:** Pause dependent model load pipelines; alert Kernel of missing storage volume; enter degraded mode.  
* **Future Expansion:** Dynamic drive auto-discovery and secondary backup mirror sync.

## **4.9 Network Resource Manager**

* **Purpose:** Tracks and limits bandwidth usage, socket descriptor limits, and concurrent connection pools across external connectors and local IPC channels.  
* **Responsibilities:** Socket pool rationing, network bandwidth shaping, connection timeout enforcement.  
* **Inputs:** Socket allocation requests, connection bandwidth specs.  
* **Outputs:** Socket pool handles, bandwidth lease quotas.  
* **Dependencies:** Resource Core.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Socket descriptor exhaustion (EMFILE), network interface saturation.  
* **Recovery:** Force-close idle TCP socket connections; drop low-priority telemetry traffic.  
* **Future Expansion:** Distributed eBPF traffic shaping and packet prioritization.

## **4.10 Thread Manager**

* **Purpose:** Controls native operating system thread creation, worker pool sizing, and OS thread pool limits.  
* **Responsibilities:** Maintaining thread pools for sync/async operations; preventing thread starvation and excessive context switching overhead.  
* **Inputs:** Thread allocation requests, task queue parameters.  
* **Outputs:** Native Thread handles, worker execution channels.  
* **Dependencies:** CPU Manager.  
* **Sockets:** CPU Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Thread creation failure (EAGAIN), deadlock detected across worker threads.  
* **Recovery:** Break deadlock dependencies by terminating unresponsive worker threads; reset thread pool allocations.  
* **Future Expansion:** User-space fiber / green thread execution runtime.

## **4.11 Worker Manager**

* **Purpose:** Manages higher-level asynchronous process and worker execution units (background task execution workers, agent process pools).  
* **Responsibilities:** Spawning, scaling, monitoring, and reaping background execution worker processes.  
* **Inputs:** Worker pool scaling requests, task workloads.  
* **Outputs:** Active Worker PIDs, worker readiness signals.  
* **Dependencies:** Thread Manager, Resource Core.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Worker process crash loop, unhandled worker exception.  
* **Recovery:** Restart crashed worker instances up to 3 times; if failure persists, mark worker queue degraded.  
* **Future Expansion:** Isolated container/sandbox process worker instantiation.

## **4.12 Queue Manager**

* **Purpose:** Maintains multi-level prioritized task queues for compute, disk, and execution requests.  
* **Responsibilities:** Enqueuing task payloads, preventing task starvation through dynamic priority boosting, tracking queue depth metrics.  
* **Inputs:** Task submission objects (TaskEnvelope), queue configuration specs.  
* **Outputs:** Ordered task streams, queue saturation alerts.  
* **Dependencies:** Priority Scheduler.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Queue buffer overflow (max task limit reached), priority inversion condition.  
* **Recovery:** Promote age-stagnated low-priority tasks; drop non-critical background telemetry tasks if queue fills.  
* **Future Expansion:** Lock-free ring buffer queue architectures for sub-microsecond queue dispatches.

## **4.13 Priority Scheduler**

* **Purpose:** Determines task execution scheduling order using priority scoring algorithms.  
* **Responsibilities:** Calculating dynamic priority scores based on base priority, task age, and resource availability; selecting tasks for execution slots.  
* **Inputs:** Enqueued tasks from Queue Manager, current resource availability state.  
* **Outputs:** Scheduled task dispatch orders, preemption execution signals.  
* **Dependencies:** Queue Manager, Allocation Manager.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Scheduler loop lockup, invalid task priority calculation.  
* **Recovery:** Re-initialize queue state using strict First-In, First-Out (FIFO) fallback logic.  
* **Future Expansion:** Machine-learning-based execution duration estimation for optimal task scheduling.

## **4.14 Allocation Manager**

* **Purpose:** Coordinates multi-resource requirements (CPU \+ RAM \+ GPU \+ VRAM) into atomic, transactional lease grants.  
* **Responsibilities:** Executing all-or-nothing allocation transactions across resource sub-managers; issuing lease tickets.  
* **Inputs:** Composite resource allocation requests.  
* **Outputs:** Atomic Resource Lease Tickets (LeaseTicket), multi-resource allocation rejections.  
* **Dependencies:** CPU Manager, RAM Manager, GPU Manager, VRAM Manager, Disk Manager.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Partial allocation failure (e.g., RAM granted, VRAM denied), partial lock condition.  
* **Recovery:** Execute immediate transactional rollback; release all partially granted resource leases.  
* **Future Expansion:** Two-phase commit protocol for distributed resource allocations.

## **4.15 Reservation Manager**

* **Purpose:** Allows high-priority organs or emergency runtimes to pre-reserve compute/memory capacity for upcoming critical operations.  
* **Responsibilities:** Maintaining future-window resource reservation calendars; locking allocation capacity in advance.  
* **Inputs:** Capacity reservation requests (ReservationSpec), time window bounds.  
* **Outputs:** Confirmed Reservation Handles, capacity hold locks.  
* **Dependencies:** Allocation Manager, Priority Scheduler.  
* **Sockets:** Resource Socket, Scheduler Socket.  
* **Pipelines:** Reservation Pipeline.  
* **Failure Modes:** Over-reservation overlap, expired unclaimed reservations locking resources.  
* **Recovery:** Automatically purge reservation holds if not claimed within a 5,000ms grace period window.  
* **Future Expansion:** Predictive dynamic reservation based on historic workflow triggers.

## **4.16 Monitoring Manager**

* **Purpose:** Collects real-time hardware metrics and process resource consumption figures across system layers.  
* **Responsibilities:** Polling OS counters, NVML APIs, and disk statistics; aggregating metric feeds; serving telemetry streams.  
* **Inputs:** Raw hardware sensors, process handle counters.  
* **Outputs:** System Resource Metric Streams, resource consumption histograms.  
* **Dependencies:** Thermal Monitor, Power Monitor, Health Monitor.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Metric collection thread hang, driver API query timeout.  
* **Recovery:** Restart polling worker threads; mark affected telemetry counters stale.  
* **Future Expansion:** Sub-millisecond hardware telemetry tracing pipelines.

## **4.17 Performance Analyzer**

* **Purpose:** Analyzes hardware utilization profiles to detect bottlenecks, resource leaks, and sub-optimal worker allocations.  
* **Responsibilities:** Computing resource efficiency indexes; detecting memory leak trends; recommending dynamic quota adjustments.  
* **Inputs:** Telemetry logs from Monitoring Manager, scheduler execution traces.  
* **Outputs:** Optimization Recommendations, Bottleneck Alert Signals.  
* **Dependencies:** Monitoring Manager.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Optimization Pipeline.  
* **Failure Modes:** Metric aggregation buffer overrun, statistical calculation overflow.  
* **Recovery:** Flush analytical buffers; reset metrics baseline tracking windows.  
* **Future Expansion:** Automated runtime auto-tuning using heuristic decision trees.

## **4.18 Load Balancer**

* **Purpose:** Distributes worker workloads evenly across available CPU cores, thread pools, and worker processes.  
* **Responsibilities:** Monitoring core/worker queue depths; dynamic thread re-balancing; preventing execution hotspots.  
* **Inputs:** Worker pool status specs, task execution queues.  
* **Outputs:** Workload redistribution dispatches, worker thread assignments.  
* **Dependencies:** CPU Manager, Thread Manager, Worker Manager.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Load imbalance causing single P-core saturation while others sit idle.  
* **Recovery:** Trigger core affinity shift; migrate worker threads to underutilized logical processors.  
* **Future Expansion:** Cross-node workload distribution across networked execution clusters.

## **4.19 Cleanup Manager**

* **Purpose:** Executes automated storage, memory, and handle garbage collection routines.  
* **Responsibilities:** Deleting orphaned temporary files, clearing offscreen Playwright buffers, releasing abandoned resource leases.  
* **Inputs:** Cleanup triggers (Scheduled, Memory Pressure Event, Storage Full Signal).  
* **Outputs:** Reclaimed bytes report, cleanup execution logs.  
* **Dependencies:** RAM Manager, VRAM Manager, SSD Manager.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Cleanup Pipeline.  
* **Failure Modes:** File lock prevents temporary file deletion, cleanup step timeout.  
* **Recovery:** Force-close handles locking temporary files; queue files for deletion on next system boot.  
* **Future Expansion:** Zero-overhead asynchronous background memory compaction engines.

## **4.20 Recovery Manager**

* **Purpose:** Handles severe resource exhaustion events, executing automated remediation runbooks.  
* **Responsibilities:** Handling OOM conditions, GPU lockups, disk-full events, and thread deadlocks; escalating to Kernel when self-healing fails.  
* **Inputs:** Critical Resource Fault Signals (OOM\_EVENT, GPU\_LOCKUP, DISK\_FULL).  
* **Outputs:** Emergency remediation actions, system recovery event reports.  
* **Dependencies:** Cleanup Manager, Allocation Manager, Resource Core.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Recovery Pipeline.  
* **Failure Modes:** Cascading failure during recovery execution, recovery loop exceeding maximum retry count.  
* **Recovery:** Escalate system state to SAFE\_MODE; trigger Kernel panic handler if critical services remain deadlocked.  
* **Future Expansion:** Automated state rollback to pre-fault execution checkpoints.

## **4.21 Thermal Monitor**

* **Purpose:** Tracks physical CPU and NVIDIA RTX 3050 GPU core temperatures to prevent thermal throttling damage.  
* **Responsibilities:** Polling hardware thermal sensors; enforcing software compute throttling when temperatures breach safety bounds.  
* **Inputs:** OS ACPI thermal zone data, NVML GPU temperature readings.  
* **Outputs:** Temperature metrics (°C), Thermal Warning Events, Throttle Triggers.  
* **Dependencies:** None.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Thermal sensor read failure, unrecorded rapid thermal spike.  
* **Recovery:** Assume conservative high-temperature state; reduce GPU clock allocations and scale back CPU thread activity by 50%.  
* **Future Expansion:** Direct interface with custom liquid cooling pump/fan controllers.

## **4.22 Power Monitor**

* **Purpose:** Monitors system power source (AC Power vs Battery) and system power draw profiles.  
* **Responsibilities:** Detecting power state changes; enforcing power-saving resource limits when running on battery power.  
* **Inputs:** Win32 Power Status APIs (GetSystemPowerStatus), NVML Power Telemetry.  
* **Outputs:** Power State Indicators (AC\_POWER, BATTERY\_POWER), Power Cap Signals.  
* **Dependencies:** None.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Win32 power API query failure.  
* **Recovery:** Default to BATTERY\_POWER power-saving operational limits.  
* **Future Expansion:** Fine-grained per-component wattage consumption accounting.

## **4.23 Health Monitor**

* **Purpose:** Aggregates operational health telemetry across all resource management modules and underlying hardware devices.  
* **Responsibilities:** Calculating the Global Resource Health Index; generating health degradation reports.  
* **Inputs:** Heartbeats and error metrics from all Resource Manager modules.  
* **Outputs:** Resource Health Objects (HEALTHY, DEGRADED, CRITICAL).  
* **Dependencies:** Monitoring Manager, Thermal Monitor, Power Monitor.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Telemetry collection lockup.  
* **Recovery:** Re-initialize monitoring threads; issue health query ping directly to module sockets.  
* **Future Expansion:** Health-driven predictive failure analysis using trend evaluation.

## **4.24 Resource Registry**

* **Purpose:** Serves as the authoritative, thread-safe index of all physical resources, virtual pools, and active resource leases.  
* **Responsibilities:** Tracking active resource lease allocations, owner subsystem IDs, lease expiration timestamps, and physical paths.  
* **Inputs:** Lease creation, modification, and revocation events.  
* **Outputs:** Resource lease maps, resource availability vectors.  
* **Dependencies:** None.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Registry map corruption, stale lease handles lingering in index.  
* **Recovery:** Re-scan all active processes and open handle tables to re-build resource index from scratch.  
* **Future Expansion:** Distributed registry synchronization via consensus algorithms.

## **4.25 Quota Manager**

* **Purpose:** Stores, evaluates, and enforces subsystem resource usage limits against pre-configured limits.  
* **Responsibilities:** Validating allocation requests against subsystem quotas; blocking allocation requests that breach limits.  
* **Inputs:** Allocation requests, subsystem quota configuration rules.  
* **Outputs:** Quota Evaluation Results (PERMITTED, QUOTA\_EXCEEDED).  
* **Dependencies:** Configuration Manager Interface, Resource Registry.  
* **Sockets:** Quota Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Quota schema read error, invalid quota configuration payload.  
* **Recovery:** Enforce conservative fallback quotas (20% max capacity per subsystem).  
* **Future Expansion:** Dynamic time-of-day adaptive quota adjustments.

## **4.26 Configuration Manager Interface**

* **Purpose:** Handles configuration retrieval and dynamic parameter updates from the centralized AOS Configuration Manager.  
* **Responsibilities:** Fetching resource rules, handling live-reload notifications for thread limits and cleanup intervals.  
* **Inputs:** Configuration streams via Configuration Socket.  
* **Outputs:** Validated internal configuration parameters for Resource Manager modules.  
* **Dependencies:** None.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Configuration Manager IPC connection loss.  
* **Recovery:** Load read-only fallback hardware configuration file (/aos/resource\_manager/config/defaults.json).  
* **Future Expansion:** Zero-copy shared-memory configuration updates.

# **5\. TARGET HARDWARE SPECIFIC MANAGEMENT**

## **5.1 CPU Management**

* **Core & Logical Processor Topology:** Discovers Intel Core i7 architecture layout (distinguishing performance P-cores from efficiency E-cores via Win32 GetLogicalProcessorInformationEx).  
* **Worker Allocation Rules:** Latency-critical tasks (Brain reasoning, low-latency UI pipelines) are pinned to P-cores using SetThreadAffinityMask. Background workers, log flushing, and telemetry compression are pinned to E-cores.  
* **Priority Mapping:** Maps internal priority classes (Critical, High, Normal, Low, Background) directly to Win32 Priority Classes (REALTIME\_PRIORITY\_CLASS, HIGH\_PRIORITY\_CLASS, ABOVE\_NORMAL\_PRIORITY\_CLASS, NORMAL\_PRIORITY\_CLASS, BELOW\_NORMAL\_PRIORITY\_CLASS, IDLE\_PRIORITY\_CLASS).

## **5.2 RAM Management**

* **Memory Pool Partitioning:**  
  * **Static Kernel Pool:** 2GB reserved exclusively for Kernel and Core OS operation.  
  * **Shared Subsystem Pool:** 20GB allocated across Organs, Knowledge Graph, and Vector Memory.  
  * **Transient Execution Pool:** 8GB reserved for active workflow steps, task buffers, and temporary data conversions.  
  * **Emergency Reserve Pool:** 2GB held completely unallocated to prevent total OS deadlock during sudden spikes.  
* **Fragmentation Prevention:** Enforces standard memory allocation bucket sizes ($64\\text{ KB}$, $1\\text{ MB}$, $16\\text{ MB}$) to allow reusable page pooling and prevent heap fragmentation.

## **5.3 GPU Management**

* **NVIDIA RTX 3050 Hardware Profile:** Detects compute capabilities, streaming multiprocessors (SMs), and CUDA core counts via NVML runtime headers (nvmlDeviceGetHandleByIndex).  
* **Inference Scheduling & Context Isolation:** Since the RTX 3050 operates as a single discrete GPU compute node, concurrent CUDA streams are prioritized via a global GPU Mutex lock. Real-time Brain inferences preempt background image/embedding generation jobs.  
* **CPU Fallback Logic:** If GPU core temperature exceeds 88°C, or CUDA execution throws an unrecoverable driver error, tensor workloads automatically drop back to ONNX Runtime / PyTorch CPU execution backends utilizing OpenMP CPU multithreading.

## **5.4 VRAM Management**

* **4GB Dedicated GDDR6 VRAM Budget Partitioning:**

\+-----------------------------------------------------------------------------------+  
| VRAM PARTITION BUDGET (TOTAL: 4096 MB)                                            |  
\+-----------------------------------------------------------------------------------+  
| 1\. Reserved System/Driver Overhead :  512 MB (Fixed NVML base context)            |  
| 2\. LLM Inference Context Budget   : 2048 MB (Quantized local model weights)       |  
| 3\. Automation Playwright Headless :  768 MB (Offscreen canvas/DOM render target)  |  
| 4\. Transient Vision/Embedding Pool:  512 MB (Dynamic image/vector buffer)          |  
| 5\. Emergency Safety Margin        :  256 MB (Unallocated buffer against OOM)       |  
\+-----------------------------------------------------------------------------------+

* **VRAM Eviction Cascades:**  
  1. Purge transient vision and embedding tensor caches.  
  2. Throttle Playwright instances (force drop offscreen canvas buffers).  
  3. Unload local quantized LLM model weights from VRAM to System RAM or External HDD storage.

## **5.5 Storage Management**

* **100GB SSD Partition Strategy:** Fast NVMe storage utilized exclusively for /aos/runtime/, active database write-ahead logs (WAL), IPC sockets, temporary task workspaces, and low-latency system logs.  
* **External HDD Model Repository:** High-capacity secondary storage utilized for static LLM model files (.gguf, .safetensors), historical vector index snapshots, cold logs, and system backup archives.  
* **Cleanup Policies:** SSD /tmp/ workspaces auto-purged if files exceed 24 hours of age or if total SSD free space drops below 10%.

# **6\. THREAD & WORKER MANAGEMENT SPECIFICATION**

\+--------------------+-------------------+-------------------+-------------------+-------------------+  
| POOL TYPE          | MIN THREAD COUNT  | MAX THREAD COUNT  | WORKER CLASS      | IDLE TIMEOUT      |  
\+--------------------+-------------------+-------------------+-------------------+-------------------+  
| System Core Pool   | 4                 | 8                 | P-Core / High     | Infinite (Keep)   |  
| Inference Pool     | 2                 | 4                 | P-Core / Critical | 30,000ms          |  
| Worker Task Pool   | 4                 | 16                | Dynamic / Normal  | 10,000ms          |  
| Background I/O Pool| 2                 | 8                 | E-Core / Low      | 5,000ms           |  
| Emergency Pool     | 1                 | 2                 | Realtime / Emergency| 60,000ms        |  
\+--------------------+-------------------+-------------------+-------------------+-------------------+

# **7\. RESOURCE PRIORITIES & QUOTAS SPECIFICATION**

## **7.1 Resource Priority Levels**

1. **Emergency:** Reserved for Kernel panic handlers, watchdog resets, and system recovery runbooks. Overrides all other allocations.  
2. **Critical:** Real-time Brain reasoning loops, critical controller actuation steps, low-latency user input handlers.  
3. **High:** Active task execution pipelines, memory vector index reads, active UI rendering feeds.  
4. **Normal:** Standard agent step iterations, workflow automation steps, standard IPC transfers.  
5. **Low:** Background indexing, model weight pre-caching, non-urgent external connector polling.  
6. **Background:** Diagnostic checks, metrics aggregation, log rotation, file workspace compression.  
7. **Maintenance:** Scheduled database vacuuming, backup archive generation, system update verification.

## **7.2 Subsystem Quota Limits**

\+-------------------+-----------+------------+------------+------------+------------+---------------+  
| SUBSYSTEM         | MAX CPU % | MAX RAM MB | MAX GPU %  | MAX VRAM MB| MAX SSD MB | DISK PRIORITY |  
\+-------------------+-----------+------------+------------+------------+------------+---------------+  
| Brain             | 80%       | 8,192 MB   | 100%       | 2,048 MB   | 10,240 MB  | HIGH          |  
| CNS               | 20%       | 2,048 MB   | 0%         | 0 MB       | 2,048 MB   | HIGH          |  
| Memory            | 40%       | 6,144 MB   | 50%        | 512 MB     | 20,480 MB  | HIGH          |  
| Knowledge         | 40%       | 4,096 MB   | 0%         | 0 MB       | 20,480 MB  | NORMAL        |  
| Controllers       | 30%       | 1,024 MB   | 0%         | 0 MB       | 1,024 MB   | CRITICAL      |  
| Learning          | 30%       | 2,048 MB   | 50%        | 512 MB     | 5,120 MB   | LOW           |  
| Automation        | 50%       | 4,096 MB   | 30%        | 768 MB     | 10,240 MB  | NORMAL        |  
| Agents            | 40%       | 2,048 MB   | 0%         | 0 MB       | 2,048 MB   | NORMAL        |  
| Runtime           | 100%      | 16,384 MB  | 100%       | 3,584 MB   | 50,200 MB  | HIGH          |  
| Connectors        | 20%       | 1,024 MB   | 0%         | 0 MB       | 1,024 MB   | LOW           |  
| Plugins           | 10%       | 512 MB     | 0%         | 0 MB       | 512 MB     | LOW           |  
\+-------------------+-----------+------------+------------+------------+------------+---------------+

# **8\. RESOURCE SCHEDULER SPECIFICATION**

The Priority Scheduler employs a Multi-Level Feedback Queue (MLFQ) dynamic scoring formula to select enqueued tasks:

$$\\text{Priority Score} \= P\_{\\text{base}} \+ \\alpha \\cdot T\_{\\text{wait}} \+ \\beta \\cdot \\left(1 \- \\frac{R\_{\\text{requested}}}{R\_{\\text{available}}}\\right)$$  
Where:

* $P\_{\\text{base}}$: Base priority score ($1000$ for Emergency, $100$ for Low).  
* $T\_{\\text{wait}}$: Milliseconds elapsed in queue waiting for execution slot.  
* $\\alpha$: Aging coefficient factor ($0.05$) to prevent task starvation.  
* $R\_{\\text{requested}} / R\_{\\text{available}}$: Ratio of requested hardware resources against current unallocated capacity.  
* $\\beta$: Resource fit weighting coefficient ($10.0$).

# **9\. PERFORMANCE OPTIMIZATION TECHNIQUES**

* **Lazy Loading:** Model weights and large vector indexes are loaded on-demand and kept mapped in virtual memory via memory-mapped files (mmap / Win32 CreateFileMapping).  
* **Resource Pooling:** Pre-allocates fixed thread pools, socket connection pools, and CUDA stream handles to eliminate runtime allocation latency.  
* **Caching:** Employs a two-tier cache structure (L1 In-RAM Cache, L2 SSD Cache) for parsed configurations and frequent query contexts.  
* **Batch Processing:** Groups individual vector embedding requests into single GPU tensor execution batches (batch size $8$-$32$) to maximize RTX 3050 CUDA utilization.  
* **Compression:** Outgoing telemetry, logs, and cold database WAL archives are compressed using LZ4 acceleration.  
* **Idle Resource Recovery:** If the global system state remains IDLE for $\> 60,000\\text{ ms}$, VRAM context buffers are flushed, and thread pools drop to minimum core numbers.

# **10\. FAILURE RECOVERY & FALLBACK MATRIX**

\+------------------------+------------------------------------+---------------------------------------------+  
| FAILURE CONDITION      | DETECTION MECHANISM                | RECOVERY WORKFLOW STEPS                     |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Out Of Memory (RAM)    | RAM Manager pressure \> 92%         | 1\. Flush L1/L2 caches                       |  
|                        |                                    | 2\. Reclaim idle thread stack allocations    |  
|                        |                                    | 3\. Terminate background processes           |  
\+------------------------+------------------------------------+---------------------------------------------+  
| VRAM Exhausted         | CUDA allocation error 2            | 1\. Purge Playwright offscreen canvas        |  
|                        |                                    | 2\. Unload idle LLM weights to RAM/HDD       |  
|                        |                                    | 3\. Force CUDA context cache reset           |  
\+------------------------+------------------------------------+---------------------------------------------+  
| GPU Unavailable / Crash| NVML API exception / driver reset  | 1\. Re-initialize NVML driver handles        |  
|                        |                                    | 2\. Switch inference paths to ONNX CPU engine|  
|                        |                                    | 3\. Emit GPU\_DEGRADED warning event          |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Disk Full (SSD)        | Disk Manager capacity \< 5%         | 1\. Purge /tmp/ task workspace files         |  
|                        |                                    | 2\. Compress and move logs to External HDD   |  
|                        |                                    | 3\. Pause non-essential write operations     |  
\+------------------------+------------------------------------+---------------------------------------------+  
| CPU Saturation         | CPU Manager 100% load \> 10,000ms   | 1\. Throttle background tasks on E-cores     |  
|                        |                                    | 2\. Enforce strict task execution rate limit |  
|                        |                                    | 3\. Delay low-priority cron jobs             |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Thread Starvation      | Queue Manager wait time \> 30,000ms | 1\. Expand maximum thread pool capacity      |  
|                        |                                    | 2\. Boost priority score of stalled tasks    |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Deadlock Detected      | Lock wait time \> 5,000ms           | 1\. Trace lock dependency graph cycle        |  
|                        |                                    | 2\. Terminate lowest-priority lock holder    |  
|                        |                                    | 3\. Release and re-aquire mutex handles      |  
\+------------------------+------------------------------------+---------------------------------------------+

# **11\. SOCKETS SPECIFICATION**

\+-------------------+-----------------------------------------------------+-----------+--------------------+----------+-------+---------+  
| SOCKET NAME       | PURPOSE                                             | DIRECTION | AUTHENTICATION     | TIMEOUT  | RETRY | LOGGING |  
\+-------------------+-----------------------------------------------------+-----------+--------------------+----------+-------+---------+  
| Resource Socket   | Process resource lease requests & grants            | In/Out    | Bearer ACL Token   | 2,000ms  | 3     | INFO    |  
| CPU Socket        | Enforce thread affinity & CPU priority assignments  | In/Out    | Internal ACL Token | 1,000ms  | 2     | DEBUG   |  
| GPU Socket        | CUDA context locks & inference execution slots      | In/Out    | Internal ACL Token | 5,000ms  | 2     | INFO    |  
| Memory Socket     | System RAM allocation, release & memory pool leases | In/Out    | Internal ACL Token | 1,000ms  | 3     | DEBUG   |  
| Disk Socket       | IOPS allocations & volume path reservations         | In/Out    | Internal ACL Token | 2,000ms  | 2     | INFO    |  
| Monitoring Socket | Stream real-time hardware telemetry and alerts      | Outbound  | System Kernel Auth | 1,000ms  | 0     | DEBUG   |  
| Scheduler Socket  | Task queue submissions & execution dispatches      | In/Out    | Bearer ACL Token   | 2,000ms  | 3     | INFO    |  
| Quota Socket      | Subsystem quota queries & live parameter updates    | In/Out    | System Admin Token | 5,000ms  | 1     | INFO    |  
\+-------------------+-----------------------------------------------------+-----------+--------------------+----------+-------+---------+

# **12\. PIPELINES SPECIFICATION**

\+----------------------+----------------------+----------------------+------------------------------------+-------+----------+-----------------------+  
| PIPELINE             | SOURCE               | DESTINATION          | PAYLOAD DATA                       | RETRY | TIMEOUT  | RECOVERY ACTION       |  
\+----------------------+----------------------+----------------------+------------------------------------+-------+----------+-----------------------+  
| Allocation Pipeline  | Subsystem Consumer   | Allocation Manager   | Composite Resource Request Spec    | 3     | 3,000ms  | Rollback Partial Alloc|  
| Reservation Pipeline | Priority Scheduler   | Reservation Manager  | Time-Windowed Reservation Spec     | 2     | 5,000ms  | Cancel Hold Lock      |  
| Monitoring Pipeline  | Hardware Sensors     | Monitoring Manager   | Raw Sensor Datagram (NVML/OS)      | 0     | 500ms    | Mark Sensor Stale     |  
| Recovery Pipeline    | Recovery Manager     | Affected Subsystem   | Emergency Remediation Action Command| 3    | 10,000ms | Escalate to Safe Mode |  
| Cleanup Pipeline     | Cleanup Manager      | Storage / Memory     | Purge Target Paths / Handles       | 2     | 15,000ms | Skip Locked Files     |  
| Scheduling Pipeline  | Queue Manager        | Execution Engine     | Enqueued Task Envelope             | 5     | 2,000ms  | Re-enqueue Task       |  
| Optimization Pipeline| Performance Analyzer | Resource Core        | Dynamic Quota Adjustment Directive | 1     | 5,000ms  | Revert Rules Adjust   |  
\+----------------------+----------------------+----------------------+------------------------------------+-------+----------+-----------------------+

# **13\. SECURITY & AUDITING SPECIFICATION**

* **Resource Isolation:** Operating System processes are executed under Win32 Job Objects with strict limits on memory, handle counts, and user interface access.  
* **Permission Validation:** Every socket connection requires an authenticated Bearer ACL Token granted by the Kernel during component bootstrap.  
* **Quota Enforcement:** The Quota Manager strictly enforces maximum capability bounds. Subsystems cannot exceed allocated memory/CPU ceilings without explicit privilege escalation tickets.  
* **Denial-Of-Service (DoS) Protection:** Implements rate-limiting on incoming allocation requests per subsystem (max 100 allocation requests/second). Malicious processes making rapid failing allocation calls are isolated.  
* **Resource Auditing:** All allocation grants, rejections, quota overrides, and emergency recovery events are written to an immutable, cryptographically signed audit log stream (/var/log/aos/resource\_audit.log).

# **14\. LOGGING & METRICS SPECIFICATION**

The Resource Manager generates structured JSON operational logs:

JSON  
{  
  "timestamp": "2026-08-07T18:10:15.120Z",  
  "level": "INFO",  
  "module": "VRAMManager",  
  "event": "VRAMAllocated",  
  "details": {  
    "subsystem": "Brain",  
    "requested\_mb": 2048,  
    "available\_vram\_mb": 1536,  
    "action\_taken": "Unloaded Idle Model Weights",  
    "reclaimed\_vram\_mb": 800,  
    "final\_allocated\_mb": 2048  
  },  
  "correlation\_id": "alloc-8f7b-20260807"  
}

* **Log Categories:** Allocation Logs, Resource Usage Logs, Performance Logs, Scheduler Logs, Recovery Logs, Cleanup Logs, Health Logs, Audit Logs.  
* **Tracked Metrics:** CPU utilization per core (%), RAM usage (Bytes), GPU utilization (%), VRAM allocation map (MB), SSD IOPS / disk space (%), HDD IOPS / disk space (%), core temperatures (°C), thread counts, and active task queue depths.

# **15\. CONFIGURATION SPECIFICATION**

Primary configuration file location: /aos/resource\_manager/config/resource\_manager.json.

JSON  
{  
  "system\_hardware": {  
    "cpu\_model": "Intel Core i7",  
    "system\_ram\_mb": 32768,  
    "gpu\_model": "NVIDIA RTX 3050",  
    "vram\_mb": 4096,  
    "ssd\_runtime\_path": "C:\\\\aos\\\\runtime",  
    "external\_hdd\_path": "D:\\\\aos\\\\models"  
  },  
  "limits": {  
    "max\_system\_ram\_threshold\_pct": 92.0,  
    "max\_vram\_threshold\_pct": 95.0,  
    "cpu\_thermal\_throttle\_celsius": 85.0,  
    "gpu\_thermal\_throttle\_celsius": 88.0,  
    "max\_threads\_global": 64  
  },  
  "monitoring": {  
    "polling\_interval\_ms": 500,  
    "metrics\_retention\_hours": 24  
  },  
  "cleanup": {  
    "auto\_cleanup\_interval\_ms": 300000,  
    "temp\_file\_max\_age\_hours": 24  
  }  
}

# **16\. COMPLETE RESOURCE ASCII DIAGRAM**

\===================================================================================================  
                                HOJAIGA AUTOMATION OPERATING SYSTEM (AOS)  
                               RESOURCE MANAGER SYSTEM ARCHITECTURE  
\===================================================================================================

                                 \+---------------------------------+  
                                 |          KERNEL LAYER           |  
                                 \+---------------------------------+  
                                                  |  
                                                  v  
\+-------------------------------------------------------------------------------------------------+  
|                                       RESOURCE MANAGER                                          |  
|                                                                                                 |  
|  \+-----------------------+   \+-----------------------+   \+-----------------------------------+  |  
|  |     Resource Core     |\<-\>|   Resource Registry   |\<-\>|           Quota Manager           |  |  
|  \+-----------------------+   \+-----------------------+   \+-----------------------------------+  |  
|              |                           |                                 |                    |  
|              v                           v                                 v                    |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                  RESOURCE SCHEDULER                                       |  |  
|  |  \+---------------------+   \+---------------------+   \+---------------------------------+  |  |  
|  |  | Priority Scheduler  |   |    Queue Manager    |   |          Load Balancer          |  |  |  
|  |  \+---------------------+   \+---------------------+   \+---------------------------------+  |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
|                                                                                                 |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                   ALLOCATION ENGINE                                       |  |  
|  |  \[CPU Manager\]    \[RAM Manager\]    \[GPU Manager\]   \[VRAM Manager\]   \[Disk Manager\]          |  |  
|  |  \[SSD Manager\]    \[Ext HDD Mgr\]    \[Net Res Mgr\]   \[Thread Mgr\]     \[Worker Manager\]        |  |  
|  |  \[Allocation Mgr\] \[Reservation Mgr\]                                                       |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
|                                                                                                 |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                  MONITORING & RECOVERY                                    |  |  
|  |  \[Monitoring Mgr\] \[Perf Analyzer\]  \[Thermal Monitor\] \[Power Monitor\] \[Health Monitor\]       |  |  
|  |  \[Cleanup Manager\]\[Recovery Mgr\]                                                          |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
|                                                                                                 |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                COMMUNICATION LAYER                                        |  |  
|  |  \[Resource Socket\] \[CPU Socket\]    \[GPU Socket\]    \[Memory Socket\] \[Disk Socket\]           |  |  
|  |  \[Monitoring Sock\] \[Scheduler Sock\]\[Quota Socket\]                                         |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
\+-------------------------------------------------------------------------------------------------+  
          |                                        |                                      |  
          v                                        v                                      v  
\+-------------------+                    \+------------------+                   \+------------------+  
| PHYSICAL HARDWARE |                    |   OS / DRIVERS   |                   |    CONSUMERS     |  
| \- Intel Core i7   |                    | \- Windows NT API |                   | \- Organs         |  
| \- 32GB System RAM |                    | \- NVIDIA NVML    |                   | \- Runtimes       |  
| \- NVIDIA RTX 3050 |                    | \- Win32 Job Objs |                   | \- Connectors     |  
| \- 4GB GDDR6 VRAM  |                    | \- DirectNVMe     |                   | \- Services       |  
| \- 100GB SSD       |                    |                  |                   |                  |  
| \- External HDD    |                    |                  |                   |                  |  
\+-------------------+                    \+------------------+                   \+------------------+  
\===================================================================================================

# **17\. DIRECTORY STRUCTURAL DESIGN**

/aos/resource\_manager/  
├── bin/  
│   └── aos-resource-manager.exe        \# Primary executable binary  
├── config/  
│   ├── resource\_manager.json           \# Master hardware & system bounds config  
│   └── defaults.json                   \# Fallback operational parameters  
├── include/  
│   └── resource\_manager/               \# Public C++ Header interfaces  
│       ├── resource\_manager.h  
│       ├── lease\_ticket.h  
│       └── socket\_protocol.h  
├── src/  
│   ├── core/                           \# Core Engine Modules  
│   │   ├── resource\_core.cpp  
│   │   ├── resource\_registry.cpp  
│   │   └── quota\_manager.cpp  
│   ├── allocation/                     \# Hardware Allocators  
│   │   ├── cpu\_manager.cpp  
│   │   ├── ram\_manager.cpp  
│   │   ├── gpu\_manager.cpp  
│   │   ├── vram\_manager.cpp  
│   │   ├── disk\_manager.cpp  
│   │   ├── ssd\_manager.cpp  
│   │   ├── external\_hdd\_manager.cpp  
│   │   ├── network\_resource\_manager.cpp  
│   │   ├── thread\_manager.cpp  
│   │   ├── worker\_manager.cpp  
│   │   ├── allocation\_manager.cpp  
│   │   └── reservation\_manager.cpp  
│   ├── scheduler/                      \# Scheduling Engines  
│   │   ├── priority\_scheduler.cpp  
│   │   ├── queue\_manager.cpp  
│   │   └── load\_balancer.cpp  
│   ├── monitoring/                     \# Health & Telemetry  
│   │   ├── monitoring\_manager.cpp  
│   │   ├── performance\_analyzer.cpp  
│   │   ├── thermal\_monitor.cpp  
│   │   ├── power\_monitor.cpp  
│   │   ├── health\_monitor.cpp  
│   │   ├── cleanup\_manager.cpp  
│   │   └── recovery\_manager.cpp  
│   ├── comm/                           \# IPC & Socket Drivers  
│   │   ├── socket\_server.cpp  
│   │   └── pipeline\_bus.cpp  
│   └── utils/                          \# Hardware Abstractions  
│       ├── win32\_job\_objects.cpp  
│       ├── nvml\_wrapper.cpp  
│       └── process\_utils.cpp  
└── tests/                              \# Testing Suites  
    ├── unit/  
    └── integration/

### **Folder Responsibilities Directory Mapping**

* /aos/resource\_manager/bin/: Contains compiled Windows Win32 binary executables.  
* /aos/resource\_manager/config/: Configuration files defining limits, quotas, and cleanup options.  
* /aos/resource\_manager/include/: Public headers exposing resource reservation APIs to AOS component developers.  
* /aos/resource\_manager/src/core/: Central control plane, lease tracking, and quota calculation logic.  
* /aos/resource\_manager/src/allocation/: Hardware-specific managers for CPU, RAM, GPU, VRAM, and storage.  
* /aos/resource\_manager/src/scheduler/: Task priority queue logic, dynamic priority scoring, and load balancing.  
* /aos/resource\_manager/src/monitoring/: Hardware telemetry wrappers (NVML, ACPI, Win32 counters), cleanup routines, and recovery runbooks.  
* /aos/resource\_manager/src/comm/: Socket message protocol handlers and data streaming channels.  
* /aos/resource\_manager/src/utils/: Native Win32 NT APIs and NVIDIA NVML C-API binding wrappers.  
* /aos/resource\_manager/tests/: Unit and stress testing suites covering memory leaks, GPU crashes, and load spikes.

# **18\. IMPLEMENTATION & INTERFACE GUIDE**

## **18.1 Class Responsibilities Matrix**

\+--------------------------+---------------------------------------------------------------------------------+  
| CLASS NAME               | PRIMARY RESPONSIBILITY                                                          |  
\+--------------------------+---------------------------------------------------------------------------------+  
| ResourceCore             | Primary controller; manages lease issuing, validation, and lifecycle handles.   |  
| ResourceRegistry         | Thread-safe registry tracking active resource leases, owners, and parameters.   |  
| CpuManager               | Manages Intel Core i7 affinity, thread priorities, and P/E-core distributions.  |  
| RamManager               | Partitioning system memory, managing allocations, and evaluating OOM risks.     |  
| GpuManager               | Controls NVIDIA RTX 3050 execution locks, CUDA context resets, and CPU fallbacks.|  
| VramManager              | Tracks 4GB VRAM usage, manages LLM model weight allocations, and handles purges. |  
| DiskManager              | Routes read/write operations between SSD Runtime and External HDD storage.     |  
| PriorityScheduler        | Calculates dynamic MLFQ priority scores and schedules queued task dispatches.   |  
| MonitoringManager        | Aggregates real-time metrics from NVML, Win32 APIs, and hardware sensors.       |  
| RecoveryManager          | Processes recovery runbooks for OOM, GPU lockups, and disk exhaustion events.   |  
| QuotaManager             | Enforces per-subsystem resource ceilings against configuration rules.           |  
\+--------------------------+---------------------------------------------------------------------------------+

## **18.2 Public C++ Header Definitions**

C++  
// ResourceInterface.h  
\#ifndef AOS\_RESOURCE\_INTERFACE\_H  
\#define AOS\_RESOURCE\_INTERFACE\_H

\#include \<string\>  
\#include \<vector\>  
\#include \<memory\>  
\#include \<cstdint\>

namespace aos {  
namespace resource {

enum class ResourcePriority { EMERGENCY, CRITICAL, HIGH, NORMAL, LOW, BACKGROUND, MAINTENANCE };  
enum class ResourceType { CPU\_CORE, SYSTEM\_RAM, GPU\_COMPUTE, GPU\_VRAM, STORAGE\_SSD, STORAGE\_HDD };

struct ResourceRequestSpec {  
    std::string subsystem\_id;  
    ResourcePriority priority;  
    uint32\_t cpu\_threads\_requested;  
    uint64\_t ram\_bytes\_requested;  
    uint32\_t gpu\_compute\_pct\_requested;  
    uint64\_t vram\_bytes\_requested;  
    uint64\_t ssd\_bytes\_requested;  
    bool allow\_cpu\_fallback;  
};

struct LeaseTicket {  
    std::string lease\_id;  
    std::string subsystem\_id;  
    bool is\_granted;  
    uint64\_t granted\_ram\_bytes;  
    uint64\_t granted\_vram\_bytes;  
    uint64\_t expiration\_timestamp\_ms;  
    std::string error\_message;  
};

class IResourceManager {  
public:  
    virtual \~IResourceManager() \= default;  
    virtual LeaseTicket RequestResourceLease(const ResourceRequestSpec& spec) \= 0;  
    virtual bool ReleaseLease(const std::string& lease\_id) \= 0;  
    virtual bool RenewLease(const std::string& lease\_id, uint64\_t extend\_duration\_ms) \= 0;  
    virtual double GetGlobalResourceHealth() \= 0;  
};

} // namespace resource  
} // namespace aos

\#endif // AOS\_RESOURCE\_INTERFACE\_H

## **18.3 Internal IPC Protocol Header**

C++  
// ResourceSocketProtocol.h  
\#ifndef AOS\_RESOURCE\_SOCKET\_PROTOCOL\_H  
\#define AOS\_RESOURCE\_SOCKET\_PROTOCOL\_H

\#include \<cstdint\>

namespace aos {  
namespace resource {

\#pragma pack(push, 1\)  
struct ResourceSocketHeader {  
    uint32\_t magic\_bytes;      // Always 0x414F5352 ('AOSR')  
    uint16\_t protocol\_version; // Protocol version (e.g., 1\)  
    uint16\_t message\_type;     // Message Type Identifier  
    uint32\_t payload\_size;     // Size of JSON payload following header  
    uint64\_t timestamp\_ns;     // Nanoseconds since epoch  
    char     auth\_token\[32\];   // Authorization token handle  
};  
\#pragma pack(pop)

enum MessageTypes : uint16\_t {  
    MSG\_RESOURCE\_LEASE\_REQ   \= 0x20,  
    MSG\_RESOURCE\_LEASE\_RESP  \= 0x21,  
    MSG\_RESOURCE\_RELEASE\_REQ \= 0x22,  
    MSG\_RESOURCE\_RENEW\_REQ   \= 0x23,  
    MSG\_TELEMETRY\_STREAM    \= 0x24,  
    MSG\_RECOVERY\_ALERT       \= 0x25  
};

} // namespace resource  
} // namespace aos

\#endif // AOS\_RESOURCE\_SOCKET\_PROTOCOL\_H

## **18.4 Naming Conventions & Standards**

* **C++ Source Files:** snake\_case.cpp and snake\_case.h.  
* **C++ Classes:** PascalCase (ResourceCore, VramManager).  
* **JSON Config Keys:** snake\_case strictly (max\_ram\_bytes, cpu\_threads\_requested).  
* **Socket Endpoints:** /var/run/aos/resource\_\*.sock or Named Pipes on Windows (\\\\.\\pipe\\aos\_resource\_\*).

## **18.5 Testing Strategy**

* **Unit Tests:** Direct test coverage for MLFQ priority scheduling algorithms, memory pool bucket allocations, and lease lifecycle expiration maps.  
* **Hardware Mocking:** Synthetic hardware test suite mocking NVML responses to simulate GPU driver crashes, high thermal states (\> 90°C), and VRAM OOM exceptions.  
* **Stress Testing:** High-concurrency allocation stress tests issuing 5,000 parallel allocation requests/second to test thread lock safety and transactional rollback logic.

## **18.6 Performance Targets**

* **Allocation Ticket Latency:** $\< 1.0\\text{ ms}$ for standard memory and thread allocation lease responses.  
* **GPU Context Switching Overhead:** $\< 5.0\\text{ ms}$ context switch time between inference dispatches.  
* **Telemetry Polling Overhead:** $\< 0.5\\%$ CPU overhead for the background Monitoring Manager polling cycle.  
* **Memory Footprint:** $\< 32\\text{ MB}$ static resident set size (RSS) memory consumption for the Resource Manager binary runtime.

# **RESOURCE\_MANAGER.MD**

**Component:** Resource Manager Layer

**Target System:** Hojaiga Automation Operating System (AOS)

**System Layer:** Core Service Layer / Resource Management Engine

**Document Status:** Production Architecture Specification

# **1\. RESOURCE MANAGER ARCHITECTURE**

The Resource Manager serves as the centralized hardware and software resource orchestrator for the Hojaiga Automation Operating System (AOS). No organ, runtime, or connector is permitted to directly reserve or allocate physical compute, memory, storage, or execution threads. All requests are mediated via strict ticket-based lease assignments issued by the Resource Manager.

\+---------------------------------------------------------------------------------------------------+  
|                                            KERNEL LAYER                                           |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         RESOURCE MANAGER                                          |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
|  |     Resource Core     |     |   Resource Registry   |     |          Quota Manager          |  |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         RESOURCE SCHEDULER                                        |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
|  |   Priority Scheduler  |     |     Queue Manager     |     |          Load Balancer         |  |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         ALLOCATION ENGINE                                         |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
|  |  CPU Mgr   |  |  RAM Mgr   |  |  GPU Mgr   |  |  VRAM Mgr  |  |  Disk Mgr  |  | Thread/Worker |  |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         MONITORING ENGINE                                         |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
|  |    Thermal Monitor    |     |     Power Monitor     |     |         Health Monitor          |  |  
|  \+-----------------------+     \+-----------------------+     \+---------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                           HARDWARE LAYER                                          |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
|  | Core i7    |  | 32GB RAM   |  | RTX 3050   |  | 4GB VRAM   |  | 100GB SSD  |  | External HDD  |  |  
|  \+------------+  \+------------+  \+------------+  \+------------+  \+------------+  \+---------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                         SUBSYSTEM CONSUMERS                                       |  
|  \+------------------+  \+------------------+  \+----------------------+  \+-----------------------+  |  
|  |      Organs      |  |     Runtimes     |  | External Connectors  |  |    Shared Services    |  |  
|  \+------------------+  \+------------------+  \+----------------------+  \+-----------------------+  |  
\+---------------------------------------------------------------------------------------------------+

# **2\. TARGET HARDWARE BASELINE & EXTENSIBILITY**

The baseline architecture is optimized for a single-node host running Windows OS with the following physical constraints:

* **Processor:** Intel Core i7 Processor (Multi-core, Hybrid P/E-core architecture topology).  
* **System Memory:** 32GB DDR4/DDR5 System RAM.  
* **Discrete GPU:** NVIDIA GeForce RTX 3050 Laptop/Desktop GPU.  
* **Video RAM:** 4GB Dedicated GDDR6 VRAM.  
* **Primary High-Speed Storage:** 100GB SSD Runtime partition (OS, transient caches, active databases, low-latency execution workspaces).  
* **Secondary Mass Storage:** External HDD Model Repository (Models, vector index backups, historical logs, cold data archives).  
* **Operating System:** Windows Operating System (Win32 / Native NT API abstractions & Win32 Cgroup-equivalent Job Objects).

### **Extensibility Guarantees:**

1. **Multi-GPU Dynamic Layer:** Abstract GPU IDs using virtual CUDA device ordinal handles (vgpu:0, vgpu:1).  
2. **Distributed & Remote Worker Interfaces:** Resource allocation endpoints communicate using RPC/ZeroMQ socket messages, permitting worker pool scaling across network nodes without changing interface semantics.  
3. **Hybrid Accelerator Abstractions:** GPU/VRAM engines expose an abstract IAccelerator API, supporting future NPU, TPU, or DirectML device backends.

# **3\. MERMAID DIAGRAMS**

## **3.1 Overall Resource Architecture**

Code snippet  
graph TD  
    Kernel(\[Kernel Core\]) \--\> RC\[Resource Core\]  
    RC \--\> Reg\[Resource Registry\]  
    RC \--\> QM\[Quota Manager\]  
    RC \--\> RS\[Resource Scheduler\]  
    RS \--\> PS\[Priority Scheduler\]  
    RS \--\> Queue\[Queue Manager\]  
    RS \--\> AE\[Allocation Engine\]  
    AE \--\> CPU\[CPU Manager\]  
    AE \--\> RAM\[RAM Manager\]  
    AE \--\> GPU\[GPU Manager\]  
    AE \--\> VRAM\[VRAM Manager\]  
    AE \--\> Disk\[Disk Manager\]  
    AE \--\> Thread\[Thread/Worker Manager\]  
    CPU \--\> HW\_CPU\[Intel Core i7\]  
    RAM \--\> HW\_RAM\[32GB System RAM\]  
    GPU \--\> HW\_GPU\[NVIDIA RTX 3050\]  
    VRAM \--\> HW\_VRAM\[4GB Dedicated VRAM\]  
    Disk \--\> HW\_SSD\[100GB SSD Runtime\]  
    Disk \--\> HW\_HDD\[External HDD Repo\]  
    AE \--\> Mon\[Monitoring Engine\]  
    Mon \--\> HW\_CPU  
    Mon \--\> HW\_GPU  
    AE \--\> Sub\[Subsystem Consumers: Organs / Runtimes / Connectors\]

## **3.2 CPU Allocation Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant C as Consumer Process  
    participant Core as Resource Core  
    participant CPU as CPU Manager  
    participant OS as Windows Win32 API

    C-\>\>Core: Request CPU Allocation (Thread Count, Priority, Class)  
    Core-\>\>CPU: Evaluate CPU Capacity & Affinity  
    CPU-\>\>CPU: Determine Core Type (P-Core vs E-Core)  
    alt Allocation Permitted  
        CPU-\>\>OS: SetThreadAffinityMask() / SetPriorityClass()  
        OS--\>\>CPU: Handle / Mask Confirmed  
        CPU--\>\>Core: Lease Issued (CPU Lease Ticket)  
        Core--\>\>C: Return Execution Lease Handle  
    else Quota / Core Limit Exceeded  
        CPU--\>\>Core: Allocation Denied (Capacity Saturation)  
        Core--\>\>C: Enqueue Request / Return Throttled Status  
    end

## **3.3 RAM Allocation Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant C as Consumer Process  
    participant Core as Resource Core  
    participant RAM as RAM Manager  
    participant Pool as Memory Pool Engine

    C-\>\>Core: Request RAM Allocation (Bytes, Pool Class)  
    Core-\>\>RAM: Check Quota & Global RAM Pressure  
    alt RAM Pressure \< 85%  
        RAM-\>\>Pool: Reserve Slice from Shared/Temporary Buffer  
        Pool--\>\>RAM: Memory Pointer / Descriptor  
        RAM--\>\>Core: Allocation Lease Confirmed  
        Core--\>\>C: Grant Memory Lease  
    else RAM Pressure \>= 85%  
        RAM-\>\>RAM: Trigger Lazy Cache Eviction & GC  
        RAM-\>\>Core: Signal Memory Pressure Warning  
        alt RAM Pressure \< 92% Post-Eviction  
            RAM-\>\>Pool: Reserve Memory Slice  
            Pool--\>\>RAM: Memory Pointer  
            RAM--\>\>Core: Grant Lease  
        else RAM Pressure \>= 92% (OOM Danger)  
            RAM--\>\>Core: Deny Allocation / Preempt Low-Priority  
            Core--\>\>C: Return Out-Of-Memory Error  
        end  
    end

## **3.4 GPU Scheduling**

Code snippet  
flowchart TD  
    Start(\[Inference/Compute Request\]) \--\> CheckGPU{Is RTX 3050 Idle?}  
    CheckGPU \-- Yes \--\> LockGPU\[Acquire GPU Mutex Lock\]  
    LockGPU \--\> Dispatch\[Dispatch CUDA Kernel Execution\]  
    Dispatch \--\> ReleaseGPU\[Release GPU Mutex Lock\] \--\> End(\[Execution Complete\])  
    CheckGPU \-- No \--\> CheckPrio{Request Priority \> Active Task?}  
    CheckPrio \-- Yes \--\> Preempt\[Preempt/Pause Low-Prio CUDA Context\]  
    Preempt \--\> LockGPU  
    CheckPrio \-- No \--\> QueueTask\[Insert Request into Priority Queue\]  
    QueueTask \--\> Wait\[Wait for GPU Idle Signal\]  
    Wait \--\> CheckGPU

## **3.5 VRAM Allocation**

Code snippet  
flowchart TD  
    A(\[VRAM Reservation Request\]) \--\> B{Requested MB \<= Available VRAM?}  
    B \-- Yes \--\> C\[Allocate CUDA VRAM Block\]  
    C \--\> D\[Update VRAM Registry Tracker\]  
    D \--\> E(\[Return VRAM Pointer Lease\])  
    B \-- No \--\> F{Is Model Unload Permitted?}  
    F \-- Yes \--\> G\[Unload Lowest Priority Idle Model Weights\]  
    G \--\> H\[Flush PyTorch / CUDA Context Cache\]  
    H \--\> B  
    F \-- No \--\> I{Can Automation Playwright Headless Budget Scale Down?}  
    I \-- Yes \--\> J\[Purge Offscreen Playwright Canvas Buffers\]  
    J \--\> B  
    I \-- No \--\> K\[Reject Request: VRAM Exhaustion\]

## **3.6 Disk Management**

Code snippet  
flowchart TD  
    A(\[Disk I/O Request\]) \--\> B{Target Storage Volume?}  
    B \-- High IOPS / Runtime \--\> C\[SSD Runtime Manager / 100GB Volume\]  
    B \-- Cold Storage / Models \--\> D\[External HDD Manager / Mass Repo\]  
    C \--\> E{SSD Space \> 10% Free?}  
    E \-- Yes \--\> F\[Execute Fast NVMe Direct Write\]  
    E \-- No \--\> G\[Trigger Log Rotation & Temp Workspace Cleanup\]  
    G \--\> F  
    D \--\> H{External HDD Volume Mounted?}  
    H \-- Yes \--\> I\[Execute Buffered Sequential Write\]  
    H \-- No \--\> J\[Queue Write to SSD Buffer & Raise Mount Request\]

## **3.7 Scheduler Flow**

Code snippet  
sequenceDiagram  
    autonumber  
    participant Sub as Subsystem Consumer  
    participant Queue as Queue Manager  
    participant PS as Priority Scheduler  
    participant Exec as Execution Engine

    Sub-\>\>Queue: Submit Task (TaskSpec, Priority, ResourceRequirements)  
    Queue-\>\>PS: Re-evaluate Heap Order  
    PS-\>\>PS: Calculate Dynamic Priority Score  
    PS-\>\>Exec: Select Top Task for Execution Slot  
    Exec-\>\>Exec: Verify Resource Lease Availability  
    alt Resources Available  
        Exec--\>\>Sub: Dispatch Task Execution Ticket  
    else Resource Constrained  
        Exec-\>\>PS: Return Task to Queue (Preemption Hold)  
    end

## **3.8 Monitoring Flow**

Code snippet  
flowchart TD  
    A(\[Monitoring Interval Tick: 500ms\]) \--\> B\[Poll CPU & System RAM Usage\]  
    B \--\> C\[Poll NVML API: GPU Usage, VRAM, Temp\]  
    C \--\> D\[Poll Storage Volumes: SSD & HDD Capacity/IOPS\]  
    D \--\> E{Thermal Level \> 85°C?}  
    E \-- Yes \--\> F\[Emit Thermal Throttle Event & Scale Down GPU Freq\]  
    E \-- No \--\> G{RAM Usage \> 85% or VRAM \> 90%?}  
    G \-- Yes \--\> H\[Emit Resource Warning & Trigger Cleanup Manager\]  
    G \-- No \--\> I\[Update Metrics Stream & Resource Registry\]

## **3.9 Recovery Flow**

Code snippet  
flowchart TD  
    A(\[Resource Failure Event\]) \--\> B{Identify Failure Type}  
    B \-- Out Of Memory \--\> C\[Execute OOM Cleanup: Kill Background Tasks\]  
    B \-- GPU Lockup / Driver Reset \--\> D\[Re-initialize NVML Context & Rebind CUDA\]  
    B \-- Disk Full \--\> E\[Force Purge Cache / Temp Files / Old Logs\]  
    B \-- Thread Starvation \--\> F\[Expand Thread Pool / Terminate Deadlocks\]  
    C \--\> G{Recovery Successful?}  
    D \--\> G  
    E \--\> G  
    F \--\> G  
    G \-- Yes \--\> H\[Resume Task Processing\]  
    G \-- No \--\> I\[Escalate to Safe Mode / Alert Kernel\]

## **3.10 State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Uninitialized  
    Uninitialized \--\> Initializing: Boot Signal  
    Initializing \--\> Normal: Hardware Probed & Baselines Loaded  
    Normal \--\> Throttled: High Thermal or Power Constraint  
    Throttled \--\> Normal: Temperature Normalization  
    Normal \--\> Degradation: Resource Exhaustion (RAM/VRAM \> 90%)  
    Degradation \--\> Normal: Cleanup & Eviction Successful  
    Degradation \--\> Critical: Recovery Failed  
    Critical \--\> RecoveryMode: Enforce Safe Allocation Caps  
    RecoveryMode \--\> Normal: Manual or System Self-Heal

## **3.11 Deployment Diagram**

Code snippet  
graph LR  
    subgraph Host Hardware Engine  
        CPU\_HW\[Intel Core i7\]  
        RAM\_HW\[32GB RAM\]  
        GPU\_HW\[NVIDIA RTX 3050\]  
        SSD\_HW\[100GB SSD\]  
        HDD\_HW\[External HDD\]  
    end

    subgraph Windows NT Environment  
        WinJob\[Win32 Job Objects\]  
        NVML\[NVIDIA NVML Driver API\]  
        WinIO\[Win32 Overlapped File I/O\]  
    end

    subgraph AOS Resource Manager Engine  
        RMCore\[Resource Core\]  
        RMCpu\[CPU/Thread Manager\]  
        RMGpu\[GPU/VRAM Manager\]  
        RMDisk\[Disk Storage Manager\]  
    end

    RMCpu \--\> WinJob \--\> CPU\_HW  
    RMCpu \--\> RAM\_HW  
    RMGpu \--\> NVML \--\> GPU\_HW  
    RMDisk \--\> WinIO \--\> SSD\_HW  
    RMDisk \--\> WinIO \--\> HDD\_HW

## **3.12 Folder Diagram**

/aos/resource\_manager/  
├── bin/  
├── config/  
├── include/  
├── src/  
│   ├── core/  
│   ├── allocation/  
│   ├── hardware/  
│   ├── scheduler/  
│   ├── monitoring/  
│   ├── comm/  
│   └── utils/  
└── tests/

# **4\. RESOURCE MODULES SPECIFICATION**

## **4.1 Resource Core**

* **Purpose:** Serves as the central command plane for all resource reservation, allocation validation, and lease tracking.  
* **Responsibilities:** Mediating consumer resource requests, enforcing lease timeouts, orchestrating sub-managers.  
* **Inputs:** Consumer resource requests (ResourceRequestSpec), lease revocation commands, kernel control flags.  
* **Outputs:** Resource Lease Handles (LeaseTicket), capacity status descriptors.  
* **Dependencies:** None (Base resource layer).  
* **Sockets:** Resource Socket, Quota Socket.  
* **Pipelines:** Allocation Pipeline, Reservation Pipeline.  
* **Failure Modes:** Internal concurrency deadlock, lease tracking corruption.  
* **Recovery:** Re-evaluate all active process leases against physical OS telemetry; flush stale lease tables.  
* **Future Expansion:** Dynamic lease routing for multi-node clusters.

## **4.2 CPU Manager**

* **Purpose:** Handles CPU core discovery, thread affinity mapping, priority class assignments, and load distribution across Intel Core i7 P/E-cores.  
* **Responsibilities:** Binding latency-sensitive tasks to Performance cores (P-cores) and background tasks to Efficiency cores (E-cores); setting Win32 process/thread priorities.  
* **Inputs:** Core allocation requests, task execution class profiles.  
* **Outputs:** Win32 Thread Affinity Masks, Priority Class Handle bindings.  
* **Dependencies:** Resource Core, Thermal Monitor.  
* **Sockets:** CPU Socket.  
* **Pipelines:** Allocation Pipeline, Scheduling Pipeline.  
* **Failure Modes:** Thread affinity binding error, core saturation (100% load on all logical processors).  
* **Recovery:** Unbind explicit core affinities; fallback to standard Windows OS NT scheduler load balancing.  
* **Future Expansion:** Automatic NUMA node detection and dynamic affinity scheduling for multi-socket servers.

## **4.3 RAM Manager**

* **Purpose:** Manages allocation, pooling, shared memory buffers, and virtual memory pressure across 32GB System RAM.  
* **Responsibilities:** Partitioning memory pools, monitoring physical page pressure, executing lazy cache evictions.  
* **Inputs:** Memory allocation requests (bytes), memory pool class identifiers.  
* **Outputs:** Virtual memory pointers, page pool leases, memory pressure warning alerts.  
* **Dependencies:** Resource Core, Health Monitor.  
* **Sockets:** Memory Socket.  
* **Pipelines:** Allocation Pipeline, Recovery Pipeline.  
* **Failure Modes:** Allocation failure, RAM utilization exceeding 92% (OOM condition).  
* **Recovery:** Force garbage collection across execution runtimes; flush transient in-memory vector caches; terminate lowest priority background workers.  
* **Future Expansion:** Compressed RAM swap ring buffers.

## **4.4 GPU Manager**

* **Purpose:** Orchestrates compute access, CUDA driver validation, and inference lock scheduling for the NVIDIA RTX 3050 GPU.  
* **Responsibilities:** Managing single-GPU access concurrency via mutexes; enforcing inference time-slicing; handling fallback to CPU execution paths.  
* **Inputs:** CUDA execution requests, inference batch jobs, context lock release signals.  
* **Outputs:** CUDA Device Context handles, execution leases, GPU lock states.  
* **Dependencies:** Resource Core, Thermal Monitor, Power Monitor.  
* **Sockets:** GPU Socket.  
* **Pipelines:** Allocation Pipeline, Scheduling Pipeline.  
* **Failure Modes:** CUDA driver crash (CUDA\_ERROR\_UNKNOWN), GPU hardware lockup, NVML API unresponsiveness.  
* **Recovery:** Re-initialize NVML driver interface bindings; flush CUDA execution contexts; route non-critical inferences to CPU runtime fallback.  
* **Future Expansion:** Multi-GPU scheduling layer supporting CUDA device ordinal array topologies.

## **4.5 VRAM Manager**

* **Purpose:** Tracks and allocates the dedicated 4GB GDDR6 VRAM footprint across LLM models, automation browsers (Playwright), and compute workflows.  
* **Responsibilities:** Maintaining static/dynamic VRAM memory maps; executing model weight unloads on capacity shortage; preventing VRAM fragmentation.  
* **Inputs:** VRAM allocation specs (MB), model loading profiles, buffer request parameters.  
* **Outputs:** VRAM block offsets, model reservation tickets, allocation failure alerts.  
* **Dependencies:** GPU Manager, Resource Core.  
* **Sockets:** GPU Socket, Memory Socket.  
* **Pipelines:** Allocation Pipeline, Cleanup Pipeline.  
* **Failure Modes:** VRAM Out-Of-Memory (CUDA\_ERROR\_OUT\_OF\_MEMORY), VRAM fragmentation preventing contiguous tensor allocation.  
* **Recovery:** Purge offscreen Playwright render buffers; unload idle LLM model weights from VRAM; issue CUDA context cache resets.  
* **Future Expansion:** Unified virtual VRAM paging using unified memory architectures across system RAM.

## **4.6 Disk Manager**

* **Purpose:** Oversees high-level storage volume abstractions, I/O bandwidth routing, and partition space policies.  
* **Responsibilities:** Directing read/write ops to appropriate storage devices based on performance targets; monitoring total free space.  
* **Inputs:** File I/O registration requests, volume performance specs.  
* **Outputs:** Target storage path descriptors, IOPS lease parameters.  
* **Dependencies:** SSD Manager, External HDD Manager.  
* **Sockets:** Disk Socket.  
* **Pipelines:** Allocation Pipeline, Cleanup Pipeline.  
* **Failure Modes:** Volume unmount, storage space exhaustion (\< 5% free space).  
* **Recovery:** Redirect write streams to secondary volumes; invoke Cleanup Manager to purge temporary files and rotated logs.  
* **Future Expansion:** Distributed POSIX virtual filesystem layer.

## **4.7 SSD Manager**

* **Purpose:** Optimizes the 100GB SSD Runtime partition for high-speed, low-latency execution workspaces, database files, and transient runtime caches.  
* **Responsibilities:** Managing temporary file lifecycles; maintaining database write-buffers; preventing SSD write-wear saturation.  
* **Inputs:** SSD allocation/write requests, cache staging data streams.  
* **Outputs:** File handles on /ssd/runtime/, direct I/O channel descriptors.  
* **Dependencies:** Disk Manager.  
* **Sockets:** Disk Socket.  
* **Pipelines:** Allocation Pipeline, Cleanup Pipeline.  
* **Failure Modes:** SSD runtime volume full, write-rate throttling detected.  
* **Recovery:** Move aged runtime logs and cold cache buffers from SSD partition to External HDD storage.  
* **Future Expansion:** Direct NVMe queue depth management via native Win32 NVMe pass-through drivers.

## **4.8 External HDD Manager**

* **Purpose:** Manages the high-capacity, cold/mass storage repository hosted on the External HDD (LLM model weight archives, knowledge DB snapshots).  
* **Responsibilities:** Managing model weight streaming; tracking external USB/SATA drive mount states; buffering slow sequential reads/writes.  
* **Inputs:** Model load requests, archive store read/write operations.  
* **Outputs:** File streams from external mass storage, volume availability status.  
* **Dependencies:** Disk Manager.  
* **Sockets:** Disk Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Drive disconnected/unmounted unexpectedly, slow read IOPS causing execution timeouts.  
* **Recovery:** Pause dependent model load pipelines; alert Kernel of missing storage volume; enter degraded mode.  
* **Future Expansion:** Dynamic drive auto-discovery and secondary backup mirror sync.

## **4.9 Network Resource Manager**

* **Purpose:** Tracks and limits bandwidth usage, socket descriptor limits, and concurrent connection pools across external connectors and local IPC channels.  
* **Responsibilities:** Socket pool rationing, network bandwidth shaping, connection timeout enforcement.  
* **Inputs:** Socket allocation requests, connection bandwidth specs.  
* **Outputs:** Socket pool handles, bandwidth lease quotas.  
* **Dependencies:** Resource Core.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Socket descriptor exhaustion (EMFILE), network interface saturation.  
* **Recovery:** Force-close idle TCP socket connections; drop low-priority telemetry traffic.  
* **Future Expansion:** Distributed eBPF traffic shaping and packet prioritization.

## **4.10 Thread Manager**

* **Purpose:** Controls native operating system thread creation, worker pool sizing, and OS thread pool limits.  
* **Responsibilities:** Maintaining thread pools for sync/async operations; preventing thread starvation and excessive context switching overhead.  
* **Inputs:** Thread allocation requests, task queue parameters.  
* **Outputs:** Native Thread handles, worker execution channels.  
* **Dependencies:** CPU Manager.  
* **Sockets:** CPU Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Thread creation failure (EAGAIN), deadlock detected across worker threads.  
* **Recovery:** Break deadlock dependencies by terminating unresponsive worker threads; reset thread pool allocations.  
* **Future Expansion:** User-space fiber / green thread execution runtime.

## **4.11 Worker Manager**

* **Purpose:** Manages higher-level asynchronous process and worker execution units (background task execution workers, agent process pools).  
* **Responsibilities:** Spawning, scaling, monitoring, and reaping background execution worker processes.  
* **Inputs:** Worker pool scaling requests, task workloads.  
* **Outputs:** Active Worker PIDs, worker readiness signals.  
* **Dependencies:** Thread Manager, Resource Core.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Worker process crash loop, unhandled worker exception.  
* **Recovery:** Restart crashed worker instances up to 3 times; if failure persists, mark worker queue degraded.  
* **Future Expansion:** Isolated container/sandbox process worker instantiation.

## **4.12 Queue Manager**

* **Purpose:** Maintains multi-level prioritized task queues for compute, disk, and execution requests.  
* **Responsibilities:** Enqueuing task payloads, preventing task starvation through dynamic priority boosting, tracking queue depth metrics.  
* **Inputs:** Task submission objects (TaskEnvelope), queue configuration specs.  
* **Outputs:** Ordered task streams, queue saturation alerts.  
* **Dependencies:** Priority Scheduler.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Queue buffer overflow (max task limit reached), priority inversion condition.  
* **Recovery:** Promote age-stagnated low-priority tasks; drop non-critical background telemetry tasks if queue fills.  
* **Future Expansion:** Lock-free ring buffer queue architectures for sub-microsecond queue dispatches.

## **4.13 Priority Scheduler**

* **Purpose:** Determines task execution scheduling order using priority scoring algorithms.  
* **Responsibilities:** Calculating dynamic priority scores based on base priority, task age, and resource availability; selecting tasks for execution slots.  
* **Inputs:** Enqueued tasks from Queue Manager, current resource availability state.  
* **Outputs:** Scheduled task dispatch orders, preemption execution signals.  
* **Dependencies:** Queue Manager, Allocation Manager.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Scheduler loop lockup, invalid task priority calculation.  
* **Recovery:** Re-initialize queue state using strict First-In, First-Out (FIFO) fallback logic.  
* **Future Expansion:** Machine-learning-based execution duration estimation for optimal task scheduling.

## **4.14 Allocation Manager**

* **Purpose:** Coordinates multi-resource requirements (CPU \+ RAM \+ GPU \+ VRAM) into atomic, transactional lease grants.  
* **Responsibilities:** Executing all-or-nothing allocation transactions across resource sub-managers; issuing lease tickets.  
* **Inputs:** Composite resource allocation requests.  
* **Outputs:** Atomic Resource Lease Tickets (LeaseTicket), multi-resource allocation rejections.  
* **Dependencies:** CPU Manager, RAM Manager, GPU Manager, VRAM Manager, Disk Manager.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Partial allocation failure (e.g., RAM granted, VRAM denied), partial lock condition.  
* **Recovery:** Execute immediate transactional rollback; release all partially granted resource leases.  
* **Future Expansion:** Two-phase commit protocol for distributed resource allocations.

## **4.15 Reservation Manager**

* **Purpose:** Allows high-priority organs or emergency runtimes to pre-reserve compute/memory capacity for upcoming critical operations.  
* **Responsibilities:** Maintaining future-window resource reservation calendars; locking allocation capacity in advance.  
* **Inputs:** Capacity reservation requests (ReservationSpec), time window bounds.  
* **Outputs:** Confirmed Reservation Handles, capacity hold locks.  
* **Dependencies:** Allocation Manager, Priority Scheduler.  
* **Sockets:** Resource Socket, Scheduler Socket.  
* **Pipelines:** Reservation Pipeline.  
* **Failure Modes:** Over-reservation overlap, expired unclaimed reservations locking resources.  
* **Recovery:** Automatically purge reservation holds if not claimed within a 5,000ms grace period window.  
* **Future Expansion:** Predictive dynamic reservation based on historic workflow triggers.

## **4.16 Monitoring Manager**

* **Purpose:** Collects real-time hardware metrics and process resource consumption figures across system layers.  
* **Responsibilities:** Polling OS counters, NVML APIs, and disk statistics; aggregating metric feeds; serving telemetry streams.  
* **Inputs:** Raw hardware sensors, process handle counters.  
* **Outputs:** System Resource Metric Streams, resource consumption histograms.  
* **Dependencies:** Thermal Monitor, Power Monitor, Health Monitor.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Metric collection thread hang, driver API query timeout.  
* **Recovery:** Restart polling worker threads; mark affected telemetry counters stale.  
* **Future Expansion:** Sub-millisecond hardware telemetry tracing pipelines.

## **4.17 Performance Analyzer**

* **Purpose:** Analyzes hardware utilization profiles to detect bottlenecks, resource leaks, and sub-optimal worker allocations.  
* **Responsibilities:** Computing resource efficiency indexes; detecting memory leak trends; recommending dynamic quota adjustments.  
* **Inputs:** Telemetry logs from Monitoring Manager, scheduler execution traces.  
* **Outputs:** Optimization Recommendations, Bottleneck Alert Signals.  
* **Dependencies:** Monitoring Manager.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Optimization Pipeline.  
* **Failure Modes:** Metric aggregation buffer overrun, statistical calculation overflow.  
* **Recovery:** Flush analytical buffers; reset metrics baseline tracking windows.  
* **Future Expansion:** Automated runtime auto-tuning using heuristic decision trees.

## **4.18 Load Balancer**

* **Purpose:** Distributes worker workloads evenly across available CPU cores, thread pools, and worker processes.  
* **Responsibilities:** Monitoring core/worker queue depths; dynamic thread re-balancing; preventing execution hotspots.  
* **Inputs:** Worker pool status specs, task execution queues.  
* **Outputs:** Workload redistribution dispatches, worker thread assignments.  
* **Dependencies:** CPU Manager, Thread Manager, Worker Manager.  
* **Sockets:** Scheduler Socket.  
* **Pipelines:** Scheduling Pipeline.  
* **Failure Modes:** Load imbalance causing single P-core saturation while others sit idle.  
* **Recovery:** Trigger core affinity shift; migrate worker threads to underutilized logical processors.  
* **Future Expansion:** Cross-node workload distribution across networked execution clusters.

## **4.19 Cleanup Manager**

* **Purpose:** Executes automated storage, memory, and handle garbage collection routines.  
* **Responsibilities:** Deleting orphaned temporary files, clearing offscreen Playwright buffers, releasing abandoned resource leases.  
* **Inputs:** Cleanup triggers (Scheduled, Memory Pressure Event, Storage Full Signal).  
* **Outputs:** Reclaimed bytes report, cleanup execution logs.  
* **Dependencies:** RAM Manager, VRAM Manager, SSD Manager.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Cleanup Pipeline.  
* **Failure Modes:** File lock prevents temporary file deletion, cleanup step timeout.  
* **Recovery:** Force-close handles locking temporary files; queue files for deletion on next system boot.  
* **Future Expansion:** Zero-overhead asynchronous background memory compaction engines.

## **4.20 Recovery Manager**

* **Purpose:** Handles severe resource exhaustion events, executing automated remediation runbooks.  
* **Responsibilities:** Handling OOM conditions, GPU lockups, disk-full events, and thread deadlocks; escalating to Kernel when self-healing fails.  
* **Inputs:** Critical Resource Fault Signals (OOM\_EVENT, GPU\_LOCKUP, DISK\_FULL).  
* **Outputs:** Emergency remediation actions, system recovery event reports.  
* **Dependencies:** Cleanup Manager, Allocation Manager, Resource Core.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Recovery Pipeline.  
* **Failure Modes:** Cascading failure during recovery execution, recovery loop exceeding maximum retry count.  
* **Recovery:** Escalate system state to SAFE\_MODE; trigger Kernel panic handler if critical services remain deadlocked.  
* **Future Expansion:** Automated state rollback to pre-fault execution checkpoints.

## **4.21 Thermal Monitor**

* **Purpose:** Tracks physical CPU and NVIDIA RTX 3050 GPU core temperatures to prevent thermal throttling damage.  
* **Responsibilities:** Polling hardware thermal sensors; enforcing software compute throttling when temperatures breach safety bounds.  
* **Inputs:** OS ACPI thermal zone data, NVML GPU temperature readings.  
* **Outputs:** Temperature metrics (°C), Thermal Warning Events, Throttle Triggers.  
* **Dependencies:** None.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Thermal sensor read failure, unrecorded rapid thermal spike.  
* **Recovery:** Assume conservative high-temperature state; reduce GPU clock allocations and scale back CPU thread activity by 50%.  
* **Future Expansion:** Direct interface with custom liquid cooling pump/fan controllers.

## **4.22 Power Monitor**

* **Purpose:** Monitors system power source (AC Power vs Battery) and system power draw profiles.  
* **Responsibilities:** Detecting power state changes; enforcing power-saving resource limits when running on battery power.  
* **Inputs:** Win32 Power Status APIs (GetSystemPowerStatus), NVML Power Telemetry.  
* **Outputs:** Power State Indicators (AC\_POWER, BATTERY\_POWER), Power Cap Signals.  
* **Dependencies:** None.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Win32 power API query failure.  
* **Recovery:** Default to BATTERY\_POWER power-saving operational limits.  
* **Future Expansion:** Fine-grained per-component wattage consumption accounting.

## **4.23 Health Monitor**

* **Purpose:** Aggregates operational health telemetry across all resource management modules and underlying hardware devices.  
* **Responsibilities:** Calculating the Global Resource Health Index; generating health degradation reports.  
* **Inputs:** Heartbeats and error metrics from all Resource Manager modules.  
* **Outputs:** Resource Health Objects (HEALTHY, DEGRADED, CRITICAL).  
* **Dependencies:** Monitoring Manager, Thermal Monitor, Power Monitor.  
* **Sockets:** Monitoring Socket.  
* **Pipelines:** Monitoring Pipeline.  
* **Failure Modes:** Telemetry collection lockup.  
* **Recovery:** Re-initialize monitoring threads; issue health query ping directly to module sockets.  
* **Future Expansion:** Health-driven predictive failure analysis using trend evaluation.

## **4.24 Resource Registry**

* **Purpose:** Serves as the authoritative, thread-safe index of all physical resources, virtual pools, and active resource leases.  
* **Responsibilities:** Tracking active resource lease allocations, owner subsystem IDs, lease expiration timestamps, and physical paths.  
* **Inputs:** Lease creation, modification, and revocation events.  
* **Outputs:** Resource lease maps, resource availability vectors.  
* **Dependencies:** None.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Registry map corruption, stale lease handles lingering in index.  
* **Recovery:** Re-scan all active processes and open handle tables to re-build resource index from scratch.  
* **Future Expansion:** Distributed registry synchronization via consensus algorithms.

## **4.25 Quota Manager**

* **Purpose:** Stores, evaluates, and enforces subsystem resource usage limits against pre-configured limits.  
* **Responsibilities:** Validating allocation requests against subsystem quotas; blocking allocation requests that breach limits.  
* **Inputs:** Allocation requests, subsystem quota configuration rules.  
* **Outputs:** Quota Evaluation Results (PERMITTED, QUOTA\_EXCEEDED).  
* **Dependencies:** Configuration Manager Interface, Resource Registry.  
* **Sockets:** Quota Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Quota schema read error, invalid quota configuration payload.  
* **Recovery:** Enforce conservative fallback quotas (20% max capacity per subsystem).  
* **Future Expansion:** Dynamic time-of-day adaptive quota adjustments.

## **4.26 Configuration Manager Interface**

* **Purpose:** Handles configuration retrieval and dynamic parameter updates from the centralized AOS Configuration Manager.  
* **Responsibilities:** Fetching resource rules, handling live-reload notifications for thread limits and cleanup intervals.  
* **Inputs:** Configuration streams via Configuration Socket.  
* **Outputs:** Validated internal configuration parameters for Resource Manager modules.  
* **Dependencies:** None.  
* **Sockets:** Resource Socket.  
* **Pipelines:** Allocation Pipeline.  
* **Failure Modes:** Configuration Manager IPC connection loss.  
* **Recovery:** Load read-only fallback hardware configuration file (/aos/resource\_manager/config/defaults.json).  
* **Future Expansion:** Zero-copy shared-memory configuration updates.

# **5\. TARGET HARDWARE SPECIFIC MANAGEMENT**

## **5.1 CPU Management**

* **Core & Logical Processor Topology:** Discovers Intel Core i7 architecture layout (distinguishing performance P-cores from efficiency E-cores via Win32 GetLogicalProcessorInformationEx).  
* **Worker Allocation Rules:** Latency-critical tasks (Brain reasoning, low-latency UI pipelines) are pinned to P-cores using SetThreadAffinityMask. Background workers, log flushing, and telemetry compression are pinned to E-cores.  
* **Priority Mapping:** Maps internal priority classes (Critical, High, Normal, Low, Background) directly to Win32 Priority Classes (REALTIME\_PRIORITY\_CLASS, HIGH\_PRIORITY\_CLASS, ABOVE\_NORMAL\_PRIORITY\_CLASS, NORMAL\_PRIORITY\_CLASS, BELOW\_NORMAL\_PRIORITY\_CLASS, IDLE\_PRIORITY\_CLASS).

## **5.2 RAM Management**

* **Memory Pool Partitioning:**  
  * **Static Kernel Pool:** 2GB reserved exclusively for Kernel and Core OS operation.  
  * **Shared Subsystem Pool:** 20GB allocated across Organs, Knowledge Graph, and Vector Memory.  
  * **Transient Execution Pool:** 8GB reserved for active workflow steps, task buffers, and temporary data conversions.  
  * **Emergency Reserve Pool:** 2GB held completely unallocated to prevent total OS deadlock during sudden spikes.  
* **Fragmentation Prevention:** Enforces standard memory allocation bucket sizes ($64\\text{ KB}$, $1\\text{ MB}$, $16\\text{ MB}$) to allow reusable page pooling and prevent heap fragmentation.

## **5.3 GPU Management**

* **NVIDIA RTX 3050 Hardware Profile:** Detects compute capabilities, streaming multiprocessors (SMs), and CUDA core counts via NVML runtime headers (nvmlDeviceGetHandleByIndex).  
* **Inference Scheduling & Context Isolation:** Since the RTX 3050 operates as a single discrete GPU compute node, concurrent CUDA streams are prioritized via a global GPU Mutex lock. Real-time Brain inferences preempt background image/embedding generation jobs.  
* **CPU Fallback Logic:** If GPU core temperature exceeds 88°C, or CUDA execution throws an unrecoverable driver error, tensor workloads automatically drop back to ONNX Runtime / PyTorch CPU execution backends utilizing OpenMP CPU multithreading.

## **5.4 VRAM Management**

* **4GB Dedicated GDDR6 VRAM Budget Partitioning:**

\+-----------------------------------------------------------------------------------+  
| VRAM PARTITION BUDGET (TOTAL: 4096 MB)                                            |  
\+-----------------------------------------------------------------------------------+  
| 1\. Reserved System/Driver Overhead :  512 MB (Fixed NVML base context)            |  
| 2\. LLM Inference Context Budget   : 2048 MB (Quantized local model weights)       |  
| 3\. Automation Playwright Headless :  768 MB (Offscreen canvas/DOM render target)  |  
| 4\. Transient Vision/Embedding Pool:  512 MB (Dynamic image/vector buffer)          |  
| 5\. Emergency Safety Margin        :  256 MB (Unallocated buffer against OOM)       |  
\+-----------------------------------------------------------------------------------+

* **VRAM Eviction Cascades:**  
  1. Purge transient vision and embedding tensor caches.  
  2. Throttle Playwright instances (force drop offscreen canvas buffers).  
  3. Unload local quantized LLM model weights from VRAM to System RAM or External HDD storage.

## **5.5 Storage Management**

* **100GB SSD Partition Strategy:** Fast NVMe storage utilized exclusively for /aos/runtime/, active database write-ahead logs (WAL), IPC sockets, temporary task workspaces, and low-latency system logs.  
* **External HDD Model Repository:** High-capacity secondary storage utilized for static LLM model files (.gguf, .safetensors), historical vector index snapshots, cold logs, and system backup archives.  
* **Cleanup Policies:** SSD /tmp/ workspaces auto-purged if files exceed 24 hours of age or if total SSD free space drops below 10%.

# **6\. THREAD & WORKER MANAGEMENT SPECIFICATION**

\+--------------------+-------------------+-------------------+-------------------+-------------------+  
| POOL TYPE          | MIN THREAD COUNT  | MAX THREAD COUNT  | WORKER CLASS      | IDLE TIMEOUT      |  
\+--------------------+-------------------+-------------------+-------------------+-------------------+  
| System Core Pool   | 4                 | 8                 | P-Core / High     | Infinite (Keep)   |  
| Inference Pool     | 2                 | 4                 | P-Core / Critical | 30,000ms          |  
| Worker Task Pool   | 4                 | 16                | Dynamic / Normal  | 10,000ms          |  
| Background I/O Pool| 2                 | 8                 | E-Core / Low      | 5,000ms           |  
| Emergency Pool     | 1                 | 2                 | Realtime / Emergency| 60,000ms        |  
\+--------------------+-------------------+-------------------+-------------------+-------------------+

# **7\. RESOURCE PRIORITIES & QUOTAS SPECIFICATION**

## **7.1 Resource Priority Levels**

1. **Emergency:** Reserved for Kernel panic handlers, watchdog resets, and system recovery runbooks. Overrides all other allocations.  
2. **Critical:** Real-time Brain reasoning loops, critical controller actuation steps, low-latency user input handlers.  
3. **High:** Active task execution pipelines, memory vector index reads, active UI rendering feeds.  
4. **Normal:** Standard agent step iterations, workflow automation steps, standard IPC transfers.  
5. **Low:** Background indexing, model weight pre-caching, non-urgent external connector polling.  
6. **Background:** Diagnostic checks, metrics aggregation, log rotation, file workspace compression.  
7. **Maintenance:** Scheduled database vacuuming, backup archive generation, system update verification.

## **7.2 Subsystem Quota Limits**

\+-------------------+-----------+------------+------------+------------+------------+---------------+  
| SUBSYSTEM         | MAX CPU % | MAX RAM MB | MAX GPU %  | MAX VRAM MB| MAX SSD MB | DISK PRIORITY |  
\+-------------------+-----------+------------+------------+------------+------------+---------------+  
| Brain             | 80%       | 8,192 MB   | 100%       | 2,048 MB   | 10,240 MB  | HIGH          |  
| CNS               | 20%       | 2,048 MB   | 0%         | 0 MB       | 2,048 MB   | HIGH          |  
| Memory            | 40%       | 6,144 MB   | 50%        | 512 MB     | 20,480 MB  | HIGH          |  
| Knowledge         | 40%       | 4,096 MB   | 0%         | 0 MB       | 20,480 MB  | NORMAL        |  
| Controllers       | 30%       | 1,024 MB   | 0%         | 0 MB       | 1,024 MB   | CRITICAL      |  
| Learning          | 30%       | 2,048 MB   | 50%        | 512 MB     | 5,120 MB   | LOW           |  
| Automation        | 50%       | 4,096 MB   | 30%        | 768 MB     | 10,240 MB  | NORMAL        |  
| Agents            | 40%       | 2,048 MB   | 0%         | 0 MB       | 2,048 MB   | NORMAL        |  
| Runtime           | 100%      | 16,384 MB  | 100%       | 3,584 MB   | 50,200 MB  | HIGH          |  
| Connectors        | 20%       | 1,024 MB   | 0%         | 0 MB       | 1,024 MB   | LOW           |  
| Plugins           | 10%       | 512 MB     | 0%         | 0 MB       | 512 MB     | LOW           |  
\+-------------------+-----------+------------+------------+------------+------------+---------------+

# **8\. RESOURCE SCHEDULER SPECIFICATION**

The Priority Scheduler employs a Multi-Level Feedback Queue (MLFQ) dynamic scoring formula to select enqueued tasks:

$$\\text{Priority Score} \= P\_{\\text{base}} \+ \\alpha \\cdot T\_{\\text{wait}} \+ \\beta \\cdot \\left(1 \- \\frac{R\_{\\text{requested}}}{R\_{\\text{available}}}\\right)$$  
Where:

* $P\_{\\text{base}}$: Base priority score ($1000$ for Emergency, $100$ for Low).  
* $T\_{\\text{wait}}$: Milliseconds elapsed in queue waiting for execution slot.  
* $\\alpha$: Aging coefficient factor ($0.05$) to prevent task starvation.  
* $R\_{\\text{requested}} / R\_{\\text{available}}$: Ratio of requested hardware resources against current unallocated capacity.  
* $\\beta$: Resource fit weighting coefficient ($10.0$).

# **9\. PERFORMANCE OPTIMIZATION TECHNIQUES**

* **Lazy Loading:** Model weights and large vector indexes are loaded on-demand and kept mapped in virtual memory via memory-mapped files (mmap / Win32 CreateFileMapping).  
* **Resource Pooling:** Pre-allocates fixed thread pools, socket connection pools, and CUDA stream handles to eliminate runtime allocation latency.  
* **Caching:** Employs a two-tier cache structure (L1 In-RAM Cache, L2 SSD Cache) for parsed configurations and frequent query contexts.  
* **Batch Processing:** Groups individual vector embedding requests into single GPU tensor execution batches (batch size $8$-$32$) to maximize RTX 3050 CUDA utilization.  
* **Compression:** Outgoing telemetry, logs, and cold database WAL archives are compressed using LZ4 acceleration.  
* **Idle Resource Recovery:** If the global system state remains IDLE for $\> 60,000\\text{ ms}$, VRAM context buffers are flushed, and thread pools drop to minimum core numbers.

# **10\. FAILURE RECOVERY & FALLBACK MATRIX**

\+------------------------+------------------------------------+---------------------------------------------+  
| FAILURE CONDITION      | DETECTION MECHANISM                | RECOVERY WORKFLOW STEPS                     |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Out Of Memory (RAM)    | RAM Manager pressure \> 92%         | 1\. Flush L1/L2 caches                       |  
|                        |                                    | 2\. Reclaim idle thread stack allocations    |  
|                        |                                    | 3\. Terminate background processes           |  
\+------------------------+------------------------------------+---------------------------------------------+  
| VRAM Exhausted         | CUDA allocation error 2            | 1\. Purge Playwright offscreen canvas        |  
|                        |                                    | 2\. Unload idle LLM weights to RAM/HDD       |  
|                        |                                    | 3\. Force CUDA context cache reset           |  
\+------------------------+------------------------------------+---------------------------------------------+  
| GPU Unavailable / Crash| NVML API exception / driver reset  | 1\. Re-initialize NVML driver handles        |  
|                        |                                    | 2\. Switch inference paths to ONNX CPU engine|  
|                        |                                    | 3\. Emit GPU\_DEGRADED warning event          |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Disk Full (SSD)        | Disk Manager capacity \< 5%         | 1\. Purge /tmp/ task workspace files         |  
|                        |                                    | 2\. Compress and move logs to External HDD   |  
|                        |                                    | 3\. Pause non-essential write operations     |  
\+------------------------+------------------------------------+---------------------------------------------+  
| CPU Saturation         | CPU Manager 100% load \> 10,000ms   | 1\. Throttle background tasks on E-cores     |  
|                        |                                    | 2\. Enforce strict task execution rate limit |  
|                        |                                    | 3\. Delay low-priority cron jobs             |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Thread Starvation      | Queue Manager wait time \> 30,000ms | 1\. Expand maximum thread pool capacity      |  
|                        |                                    | 2\. Boost priority score of stalled tasks    |  
\+------------------------+------------------------------------+---------------------------------------------+  
| Deadlock Detected      | Lock wait time \> 5,000ms           | 1\. Trace lock dependency graph cycle        |  
|                        |                                    | 2\. Terminate lowest-priority lock holder    |  
|                        |                                    | 3\. Release and re-aquire mutex handles      |  
\+------------------------+------------------------------------+---------------------------------------------+

# **11\. SOCKETS SPECIFICATION**

\+-------------------+-----------------------------------------------------+-----------+--------------------+----------+-------+---------+  
| SOCKET NAME       | PURPOSE                                             | DIRECTION | AUTHENTICATION     | TIMEOUT  | RETRY | LOGGING |  
\+-------------------+-----------------------------------------------------+-----------+--------------------+----------+-------+---------+  
| Resource Socket   | Process resource lease requests & grants            | In/Out    | Bearer ACL Token   | 2,000ms  | 3     | INFO    |  
| CPU Socket        | Enforce thread affinity & CPU priority assignments  | In/Out    | Internal ACL Token | 1,000ms  | 2     | DEBUG   |  
| GPU Socket        | CUDA context locks & inference execution slots      | In/Out    | Internal ACL Token | 5,000ms  | 2     | INFO    |  
| Memory Socket     | System RAM allocation, release & memory pool leases | In/Out    | Internal ACL Token | 1,000ms  | 3     | DEBUG   |  
| Disk Socket       | IOPS allocations & volume path reservations         | In/Out    | Internal ACL Token | 2,000ms  | 2     | INFO    |  
| Monitoring Socket | Stream real-time hardware telemetry and alerts      | Outbound  | System Kernel Auth | 1,000ms  | 0     | DEBUG   |  
| Scheduler Socket  | Task queue submissions & execution dispatches      | In/Out    | Bearer ACL Token   | 2,000ms  | 3     | INFO    |  
| Quota Socket      | Subsystem quota queries & live parameter updates    | In/Out    | System Admin Token | 5,000ms  | 1     | INFO    |  
\+-------------------+-----------------------------------------------------+-----------+--------------------+----------+-------+---------+

# **12\. PIPELINES SPECIFICATION**

\+----------------------+----------------------+----------------------+------------------------------------+-------+----------+-----------------------+  
| PIPELINE             | SOURCE               | DESTINATION          | PAYLOAD DATA                       | RETRY | TIMEOUT  | RECOVERY ACTION       |  
\+----------------------+----------------------+----------------------+------------------------------------+-------+----------+-----------------------+  
| Allocation Pipeline  | Subsystem Consumer   | Allocation Manager   | Composite Resource Request Spec    | 3     | 3,000ms  | Rollback Partial Alloc|  
| Reservation Pipeline | Priority Scheduler   | Reservation Manager  | Time-Windowed Reservation Spec     | 2     | 5,000ms  | Cancel Hold Lock      |  
| Monitoring Pipeline  | Hardware Sensors     | Monitoring Manager   | Raw Sensor Datagram (NVML/OS)      | 0     | 500ms    | Mark Sensor Stale     |  
| Recovery Pipeline    | Recovery Manager     | Affected Subsystem   | Emergency Remediation Action Command| 3    | 10,000ms | Escalate to Safe Mode |  
| Cleanup Pipeline     | Cleanup Manager      | Storage / Memory     | Purge Target Paths / Handles       | 2     | 15,000ms | Skip Locked Files     |  
| Scheduling Pipeline  | Queue Manager        | Execution Engine     | Enqueued Task Envelope             | 5     | 2,000ms  | Re-enqueue Task       |  
| Optimization Pipeline| Performance Analyzer | Resource Core        | Dynamic Quota Adjustment Directive | 1     | 5,000ms  | Revert Rules Adjust   |  
\+----------------------+----------------------+----------------------+------------------------------------+-------+----------+-----------------------+

# **13\. SECURITY & AUDITING SPECIFICATION**

* **Resource Isolation:** Operating System processes are executed under Win32 Job Objects with strict limits on memory, handle counts, and user interface access.  
* **Permission Validation:** Every socket connection requires an authenticated Bearer ACL Token granted by the Kernel during component bootstrap.  
* **Quota Enforcement:** The Quota Manager strictly enforces maximum capability bounds. Subsystems cannot exceed allocated memory/CPU ceilings without explicit privilege escalation tickets.  
* **Denial-Of-Service (DoS) Protection:** Implements rate-limiting on incoming allocation requests per subsystem (max 100 allocation requests/second). Malicious processes making rapid failing allocation calls are isolated.  
* **Resource Auditing:** All allocation grants, rejections, quota overrides, and emergency recovery events are written to an immutable, cryptographically signed audit log stream (/var/log/aos/resource\_audit.log).

# **14\. LOGGING & METRICS SPECIFICATION**

The Resource Manager generates structured JSON operational logs:

JSON  
{  
  "timestamp": "2026-08-07T18:10:15.120Z",  
  "level": "INFO",  
  "module": "VRAMManager",  
  "event": "VRAMAllocated",  
  "details": {  
    "subsystem": "Brain",  
    "requested\_mb": 2048,  
    "available\_vram\_mb": 1536,  
    "action\_taken": "Unloaded Idle Model Weights",  
    "reclaimed\_vram\_mb": 800,  
    "final\_allocated\_mb": 2048  
  },  
  "correlation\_id": "alloc-8f7b-20260807"  
}

* **Log Categories:** Allocation Logs, Resource Usage Logs, Performance Logs, Scheduler Logs, Recovery Logs, Cleanup Logs, Health Logs, Audit Logs.  
* **Tracked Metrics:** CPU utilization per core (%), RAM usage (Bytes), GPU utilization (%), VRAM allocation map (MB), SSD IOPS / disk space (%), HDD IOPS / disk space (%), core temperatures (°C), thread counts, and active task queue depths.

# **15\. CONFIGURATION SPECIFICATION**

Primary configuration file location: /aos/resource\_manager/config/resource\_manager.json.

JSON  
{  
  "system\_hardware": {  
    "cpu\_model": "Intel Core i7",  
    "system\_ram\_mb": 32768,  
    "gpu\_model": "NVIDIA RTX 3050",  
    "vram\_mb": 4096,  
    "ssd\_runtime\_path": "C:\\\\aos\\\\runtime",  
    "external\_hdd\_path": "D:\\\\aos\\\\models"  
  },  
  "limits": {  
    "max\_system\_ram\_threshold\_pct": 92.0,  
    "max\_vram\_threshold\_pct": 95.0,  
    "cpu\_thermal\_throttle\_celsius": 85.0,  
    "gpu\_thermal\_throttle\_celsius": 88.0,  
    "max\_threads\_global": 64  
  },  
  "monitoring": {  
    "polling\_interval\_ms": 500,  
    "metrics\_retention\_hours": 24  
  },  
  "cleanup": {  
    "auto\_cleanup\_interval\_ms": 300000,  
    "temp\_file\_max\_age\_hours": 24  
  }  
}

# **16\. COMPLETE RESOURCE ASCII DIAGRAM**

\===================================================================================================  
                                HOJAIGA AUTOMATION OPERATING SYSTEM (AOS)  
                               RESOURCE MANAGER SYSTEM ARCHITECTURE  
\===================================================================================================

                                 \+---------------------------------+  
                                 |          KERNEL LAYER           |  
                                 \+---------------------------------+  
                                                  |  
                                                  v  
\+-------------------------------------------------------------------------------------------------+  
|                                       RESOURCE MANAGER                                          |  
|                                                                                                 |  
|  \+-----------------------+   \+-----------------------+   \+-----------------------------------+  |  
|  |     Resource Core     |\<-\>|   Resource Registry   |\<-\>|           Quota Manager           |  |  
|  \+-----------------------+   \+-----------------------+   \+-----------------------------------+  |  
|              |                           |                                 |                    |  
|              v                           v                                 v                    |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                  RESOURCE SCHEDULER                                       |  |  
|  |  \+---------------------+   \+---------------------+   \+---------------------------------+  |  |  
|  |  | Priority Scheduler  |   |    Queue Manager    |   |          Load Balancer          |  |  |  
|  |  \+---------------------+   \+---------------------+   \+---------------------------------+  |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
|                                                                                                 |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                   ALLOCATION ENGINE                                       |  |  
|  |  \[CPU Manager\]    \[RAM Manager\]    \[GPU Manager\]   \[VRAM Manager\]   \[Disk Manager\]          |  |  
|  |  \[SSD Manager\]    \[Ext HDD Mgr\]    \[Net Res Mgr\]   \[Thread Mgr\]     \[Worker Manager\]        |  |  
|  |  \[Allocation Mgr\] \[Reservation Mgr\]                                                       |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
|                                                                                                 |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                  MONITORING & RECOVERY                                    |  |  
|  |  \[Monitoring Mgr\] \[Perf Analyzer\]  \[Thermal Monitor\] \[Power Monitor\] \[Health Monitor\]       |  |  
|  |  \[Cleanup Manager\]\[Recovery Mgr\]                                                          |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
|                                                                                                 |  
|  \+-------------------------------------------------------------------------------------------+  |  
|  |                                COMMUNICATION LAYER                                        |  |  
|  |  \[Resource Socket\] \[CPU Socket\]    \[GPU Socket\]    \[Memory Socket\] \[Disk Socket\]           |  |  
|  |  \[Monitoring Sock\] \[Scheduler Sock\]\[Quota Socket\]                                         |  |  
|  \+-------------------------------------------------------------------------------------------+  |  
\+-------------------------------------------------------------------------------------------------+  
          |                                        |                                      |  
          v                                        v                                      v  
\+-------------------+                    \+------------------+                   \+------------------+  
| PHYSICAL HARDWARE |                    |   OS / DRIVERS   |                   |    CONSUMERS     |  
| \- Intel Core i7   |                    | \- Windows NT API |                   | \- Organs         |  
| \- 32GB System RAM |                    | \- NVIDIA NVML    |                   | \- Runtimes       |  
| \- NVIDIA RTX 3050 |                    | \- Win32 Job Objs |                   | \- Connectors     |  
| \- 4GB GDDR6 VRAM  |                    | \- DirectNVMe     |                   | \- Services       |  
| \- 100GB SSD       |                    |                  |                   |                  |  
| \- External HDD    |                    |                  |                   |                  |  
\+-------------------+                    \+------------------+                   \+------------------+  
\===================================================================================================

# **17\. DIRECTORY STRUCTURAL DESIGN**

/aos/resource\_manager/  
├── bin/  
│   └── aos-resource-manager.exe        \# Primary executable binary  
├── config/  
│   ├── resource\_manager.json           \# Master hardware & system bounds config  
│   └── defaults.json                   \# Fallback operational parameters  
├── include/  
│   └── resource\_manager/               \# Public C++ Header interfaces  
│       ├── resource\_manager.h  
│       ├── lease\_ticket.h  
│       └── socket\_protocol.h  
├── src/  
│   ├── core/                           \# Core Engine Modules  
│   │   ├── resource\_core.cpp  
│   │   ├── resource\_registry.cpp  
│   │   └── quota\_manager.cpp  
│   ├── allocation/                     \# Hardware Allocators  
│   │   ├── cpu\_manager.cpp  
│   │   ├── ram\_manager.cpp  
│   │   ├── gpu\_manager.cpp  
│   │   ├── vram\_manager.cpp  
│   │   ├── disk\_manager.cpp  
│   │   ├── ssd\_manager.cpp  
│   │   ├── external\_hdd\_manager.cpp  
│   │   ├── network\_resource\_manager.cpp  
│   │   ├── thread\_manager.cpp  
│   │   ├── worker\_manager.cpp  
│   │   ├── allocation\_manager.cpp  
│   │   └── reservation\_manager.cpp  
│   ├── scheduler/                      \# Scheduling Engines  
│   │   ├── priority\_scheduler.cpp  
│   │   ├── queue\_manager.cpp  
│   │   └── load\_balancer.cpp  
│   ├── monitoring/                     \# Health & Telemetry  
│   │   ├── monitoring\_manager.cpp  
│   │   ├── performance\_analyzer.cpp  
│   │   ├── thermal\_monitor.cpp  
│   │   ├── power\_monitor.cpp  
│   │   ├── health\_monitor.cpp  
│   │   ├── cleanup\_manager.cpp  
│   │   └── recovery\_manager.cpp  
│   ├── comm/                           \# IPC & Socket Drivers  
│   │   ├── socket\_server.cpp  
│   │   └── pipeline\_bus.cpp  
│   └── utils/                          \# Hardware Abstractions  
│       ├── win32\_job\_objects.cpp  
│       ├── nvml\_wrapper.cpp  
│       └── process\_utils.cpp  
└── tests/                              \# Testing Suites  
    ├── unit/  
    └── integration/

### **Folder Responsibilities Directory Mapping**

* /aos/resource\_manager/bin/: Contains compiled Windows Win32 binary executables.  
* /aos/resource\_manager/config/: Configuration files defining limits, quotas, and cleanup options.  
* /aos/resource\_manager/include/: Public headers exposing resource reservation APIs to AOS component developers.  
* /aos/resource\_manager/src/core/: Central control plane, lease tracking, and quota calculation logic.  
* /aos/resource\_manager/src/allocation/: Hardware-specific managers for CPU, RAM, GPU, VRAM, and storage.  
* /aos/resource\_manager/src/scheduler/: Task priority queue logic, dynamic priority scoring, and load balancing.  
* /aos/resource\_manager/src/monitoring/: Hardware telemetry wrappers (NVML, ACPI, Win32 counters), cleanup routines, and recovery runbooks.  
* /aos/resource\_manager/src/comm/: Socket message protocol handlers and data streaming channels.  
* /aos/resource\_manager/src/utils/: Native Win32 NT APIs and NVIDIA NVML C-API binding wrappers.  
* /aos/resource\_manager/tests/: Unit and stress testing suites covering memory leaks, GPU crashes, and load spikes.

# **18\. IMPLEMENTATION & INTERFACE GUIDE**

## **18.1 Class Responsibilities Matrix**

\+--------------------------+---------------------------------------------------------------------------------+  
| CLASS NAME               | PRIMARY RESPONSIBILITY                                                          |  
\+--------------------------+---------------------------------------------------------------------------------+  
| ResourceCore             | Primary controller; manages lease issuing, validation, and lifecycle handles.   |  
| ResourceRegistry         | Thread-safe registry tracking active resource leases, owners, and parameters.   |  
| CpuManager               | Manages Intel Core i7 affinity, thread priorities, and P/E-core distributions.  |  
| RamManager               | Partitioning system memory, managing allocations, and evaluating OOM risks.     |  
| GpuManager               | Controls NVIDIA RTX 3050 execution locks, CUDA context resets, and CPU fallbacks.|  
| VramManager              | Tracks 4GB VRAM usage, manages LLM model weight allocations, and handles purges. |  
| DiskManager              | Routes read/write operations between SSD Runtime and External HDD storage.     |  
| PriorityScheduler        | Calculates dynamic MLFQ priority scores and schedules queued task dispatches.   |  
| MonitoringManager        | Aggregates real-time metrics from NVML, Win32 APIs, and hardware sensors.       |  
| RecoveryManager          | Processes recovery runbooks for OOM, GPU lockups, and disk exhaustion events.   |  
| QuotaManager             | Enforces per-subsystem resource ceilings against configuration rules.           |  
\+--------------------------+---------------------------------------------------------------------------------+

## **18.2 Public C++ Header Definitions**

C++  
// ResourceInterface.h  
\#ifndef AOS\_RESOURCE\_INTERFACE\_H  
\#define AOS\_RESOURCE\_INTERFACE\_H

\#include \<string\>  
\#include \<vector\>  
\#include \<memory\>  
\#include \<cstdint\>

namespace aos {  
namespace resource {

enum class ResourcePriority { EMERGENCY, CRITICAL, HIGH, NORMAL, LOW, BACKGROUND, MAINTENANCE };  
enum class ResourceType { CPU\_CORE, SYSTEM\_RAM, GPU\_COMPUTE, GPU\_VRAM, STORAGE\_SSD, STORAGE\_HDD };

struct ResourceRequestSpec {  
    std::string subsystem\_id;  
    ResourcePriority priority;  
    uint32\_t cpu\_threads\_requested;  
    uint64\_t ram\_bytes\_requested;  
    uint32\_t gpu\_compute\_pct\_requested;  
    uint64\_t vram\_bytes\_requested;  
    uint64\_t ssd\_bytes\_requested;  
    bool allow\_cpu\_fallback;  
};

struct LeaseTicket {  
    std::string lease\_id;  
    std::string subsystem\_id;  
    bool is\_granted;  
    uint64\_t granted\_ram\_bytes;  
    uint64\_t granted\_vram\_bytes;  
    uint64\_t expiration\_timestamp\_ms;  
    std::string error\_message;  
};

class IResourceManager {  
public:  
    virtual \~IResourceManager() \= default;  
    virtual LeaseTicket RequestResourceLease(const ResourceRequestSpec& spec) \= 0;  
    virtual bool ReleaseLease(const std::string& lease\_id) \= 0;  
    virtual bool RenewLease(const std::string& lease\_id, uint64\_t extend\_duration\_ms) \= 0;  
    virtual double GetGlobalResourceHealth() \= 0;  
};

} // namespace resource  
} // namespace aos

\#endif // AOS\_RESOURCE\_INTERFACE\_H

## **18.3 Internal IPC Protocol Header**

C++  
// ResourceSocketProtocol.h  
\#ifndef AOS\_RESOURCE\_SOCKET\_PROTOCOL\_H  
\#define AOS\_RESOURCE\_SOCKET\_PROTOCOL\_H

\#include \<cstdint\>

namespace aos {  
namespace resource {

\#pragma pack(push, 1\)  
struct ResourceSocketHeader {  
    uint32\_t magic\_bytes;      // Always 0x414F5352 ('AOSR')  
    uint16\_t protocol\_version; // Protocol version (e.g., 1\)  
    uint16\_t message\_type;     // Message Type Identifier  
    uint32\_t payload\_size;     // Size of JSON payload following header  
    uint64\_t timestamp\_ns;     // Nanoseconds since epoch  
    char     auth\_token\[32\];   // Authorization token handle  
};  
\#pragma pack(pop)

enum MessageTypes : uint16\_t {  
    MSG\_RESOURCE\_LEASE\_REQ   \= 0x20,  
    MSG\_RESOURCE\_LEASE\_RESP  \= 0x21,  
    MSG\_RESOURCE\_RELEASE\_REQ \= 0x22,  
    MSG\_RESOURCE\_RENEW\_REQ   \= 0x23,  
    MSG\_TELEMETRY\_STREAM    \= 0x24,  
    MSG\_RECOVERY\_ALERT       \= 0x25  
};

} // namespace resource  
} // namespace aos

\#endif // AOS\_RESOURCE\_SOCKET\_PROTOCOL\_H

## **18.4 Naming Conventions & Standards**

* **C++ Source Files:** snake\_case.cpp and snake\_case.h.  
* **C++ Classes:** PascalCase (ResourceCore, VramManager).  
* **JSON Config Keys:** snake\_case strictly (max\_ram\_bytes, cpu\_threads\_requested).  
* **Socket Endpoints:** /var/run/aos/resource\_\*.sock or Named Pipes on Windows (\\\\.\\pipe\\aos\_resource\_\*).

## **18.5 Testing Strategy**

* **Unit Tests:** Direct test coverage for MLFQ priority scheduling algorithms, memory pool bucket allocations, and lease lifecycle expiration maps.  
* **Hardware Mocking:** Synthetic hardware test suite mocking NVML responses to simulate GPU driver crashes, high thermal states (\> 90°C), and VRAM OOM exceptions.  
* **Stress Testing:** High-concurrency allocation stress tests issuing 5,000 parallel allocation requests/second to test thread lock safety and transactional rollback logic.

## **18.6 Performance Targets**

* **Allocation Ticket Latency:** $\< 1.0\\text{ ms}$ for standard memory and thread allocation lease responses.  
* **GPU Context Switching Overhead:** $\< 5.0\\text{ ms}$ context switch time between inference dispatches.  
* **Telemetry Polling Overhead:** $\< 0.5\\%$ CPU overhead for the background Monitoring Manager polling cycle.  
* **Memory Footprint:** $\< 32\\text{ MB}$ static resident set size (RSS) memory consumption for the Resource Manager binary runtime.

