# **Organ 09 — Infrastructure Specification Document**

## **1\. Overview**

The Infrastructure Organ is the core hardware abstraction, resource scheduling, operational monitoring, filesystem orchestration, version management, and logging substrate of the Hojaiga Automation Operating System. It interfaces directly with host hardware resources—specifically the Intel Core i7 CPU, NVIDIA RTX 3050 GPU (4 GB VRAM), 32 GB RAM, 100 GB SSD Runtime partition, and External HDD store—to enforce strict hardware operational boundaries. Operating CPU-first, the Infrastructure Organ guarantees low-overhead resource provisioning, system telemetry collection, hardware status tracking, and API gateway routing across all Hojaiga organs.

MD+ 4

## **2\. Purpose**

The purpose of the Infrastructure Organ is to isolate the software automation stack from raw operating system hardware primitives while providing unified, controlled, and optimized access to storage, compute, logging, configuration, downloads, and external peripheral interfaces. In accordance with Universal Law 11 (Resource Responsibility) and Policy Manual Chapter 12, the Infrastructure Organ ensures that CPU, VRAM, RAM, and disk storage are utilized efficiently, transparently, and safely across all operations.

MD+ 4

## **3\. Philosophy**

In strict compliance with Chapter 9 of the Master Architecture Blueprint, Universal Law 4 (Modularity and Replaceability), and Policy Manual Chapter 12, hardware resources in Hojaiga are treated as managed assets subject to explicit scheduling quotas and isolation barriers. GPU usage is restricted exclusively to LLM inference executed by the Brain Organ, leaving 100% of host GPU compute and VRAM available for Qwen3 processing. All other operations run CPU-first. System storage is strictly bifurcated between high-speed 100 GB SSD Runtime storage for active execution states and low-cost External HDD storage for immutable logs, knowledge vector backups, and long-term history archives.

MD+ 4

## **4\. Primary Responsibilities**

* **Hardware Resource Control & Allocation:** Monitor and partition CPU thread allocation, GPU VRAM availability, system RAM footprint, and disk capacity.  
   MD+ 1  
* **Resource Scheduler & Priority Governor:** Dispatch CPU core affinity masks and process priority classes (`Win32 JobObjects`) to prevent resource starvation.  
   MD+ 1  
* **Centralized Append-Only Logger:** Manage non-blocking, structured JSON log appenders writing to SSD staging buffers and flushing sequentially to external HDD archives.  
   MD+ 2  
* **Filesystem & Storage Partition Management:** Enforce the operational storage layout across SSD Runtime directories (`/working`, `/snapshots`) and External HDD directories (`/logs`, `/history`, `/archives`).  
   MD+ 1  
* **System Downloads & Uploads Engine:** Execute bandwidth-throttled, cryptographically verified file download and upload routines.  
   MD+ 1  
* **Configuration & Version Manager:** Serve versioned configuration files (`/config/`) and manage semantic system migration manifests.  
   MD+ 1  
* **API Gateway & External Networking:** Manage outbound API request routing, proxy binding, network throttling, and circuit-breaker safety limits.  
   MD+ 2  
* **Telemetry & Performance Monitoring:** Collect real-time operational metrics (CPU load, VRAM allocation, disk I/O latency, memory page faults) and emit telemetry events to the Central Nervous System (CNS).  
   MD+ 2

## **5\. Internal Modules**

* `infrastructure_core`: Central IPC communication socket listener and subsystem coordinator.  
* `hardware_controller`: Direct Interface for querying CPU, GPU (NVIDIA Management Library \- NVML), RAM, and storage health metrics.  
   MD+ 1  
* `resource_scheduler`: Enforces Win32 Process Priority Classes and Job Object memory quotas across organ processes.  
   MD+ 1  
* `central_logger`: Thread-safe, non-blocking log ingestion engine that writes structured JSON logs sequentially to disk.  
   MD+ 1  
* `filesystem_manager`: Directs file I/O operations between fast SSD runtime storage and long-term external HDD storage.  
   MD+ 1  
* `download_manager`: Network transfer manager handling file downloads, checksum verification (SHA-256), and temporary staging.  
   MD+ 1  
* `version_manager`: Manages system version manifests, schema migration scripts, and component release tracks.  
   MD+ 1  
* `api_gateway`: Outbound network HTTP/gRPC request wrapper enforcing connection pooling, timeout windows, and rate limits.  
   MD+ 1  
* `monitoring_engine`: Continuous background thread collecting resource consumption metrics at 1000ms intervals.  
   MD+ 1

## **6\. Internal Folder Structure**

/organ\_09\_infrastructure  
├── bin/  
│   └── infra\_daemon           \# Main infrastructure kernel daemon  
├── config/  
│   ├── hardware\_limits.json   \# Memory, VRAM, and CPU thresholds  
│   └── network\_gateway.json   \# Proxy, timeout, and API rate limits  
├── storage/  
│   ├── ssd\_runtime/           \# Staged logs, temp downloads, active swap  
│   │   ├── downloads/  
│   │   └── log\_buffer/  
│   └── hdd\_archive/           \# Path references to External HDD storage  
│       ├── logs/  
│       ├── history/  
│       └── backups/  
├── src/  
│   ├── core/  
│   │   ├── infra\_kernel.py  
│   │   └── config\_loader.py  
│   ├── hardware/  
│   │   ├── hardware\_controller.py  
│   │   ├── nvml\_monitor.py  
│   │   └── resource\_scheduler.py  
│   ├── storage\_engine/  
│   │   ├── filesystem\_manager.py  
│   │   └── download\_manager.py  
│   ├── logging\_engine/  
│   │   └── central\_logger.py  
│   ├── gateway/  
│   │   ├── api\_gateway.py  
│   │   └── network\_throttler.py  
│   ├── versioning/  
│   │   └── version\_manager.py  
│   └── sockets/  
│       └── ipc\_server.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* `IPC Socket Interface`: `\\.\pipe\hojaiga_infrastructure` (Windows) / `/tmp/hojaiga_infrastructure.sock` (Linux/Unix).  
   MD  
  * `rpc GetHardwareStatus(StatusQueryPayload)` \-\> `HardwareStatusMetrics`  
  * `rpc AllocateResourceQuota(QuotaRequestPayload)` \-\> `QuotaGrant`  
  * `rpc AppendSystemLog(LogEntryPayload)` \-\> `LogAck`  
  * `rpc InitiateDownload(DownloadRequestPayload)` \-\> `DownloadHandle`  
  * `rpc RouteOutboundAPI(APIRequestPayload)` \-\> `APIResponsePayload`  
  * `rpc GetSystemVersion(VersionQueryPayload)` \-\> `VersionManifest`  
  * `rpc ExecuteStorageArchival(ArchivalRequestPayload)` \-\> `ArchivalStatus`

## **8\. Internal Interfaces**

* `IHardwareMonitor`:  
  * `query_vram_usage()`: Calls NVML C-bindings to retrieve exact bytes allocated on NVIDIA RTX 3050\.  
     MD+ 1  
  * `query_cpu_and_ram()`: Uses Win32 `GetSystemInfo` and `GlobalMemoryStatusEx` for system telemetry.  
     MD+ 1  
* `IFilesystemManager`:  
  * `get_runtime_path(relative_path)`: Resolves file path against SSD Runtime root partition.  
     MD+ 1  
  * `get_archive_path(relative_path)`: Resolves file path against External HDD root partition.  
     MD+ 1  
* `ICentralLogger`:  
  * `write_log_frame(log_json)`: Pushes log envelope to in-memory lockless ring buffer for non-blocking disk flush.  
     MD+ 1

## **9\. Socket Definitions**

* Named Pipe Socket: `hojaiga_infrastructure`.  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
   MD  
* Max Payload Size: 32 MB per request frame.

## **10\. Pipeline Definitions**

* `SystemLoggingPipeline`:  
  1. Organ Emits Log Entry \-\> 2\. Infrastructure IPC Socket Ingestion \-\> 3\. Lockless Ring Buffer Enqueue \-\> 4\. Async Worker Flush to SSD Log Buffer \-\> 5\. Sequential Flush Worker Moves Buffer to External HDD Log Store.  
      MD+ 2  
* `OutboundAPIRoutingPipeline`:  
  1. External API Request from Organ \-\> 2\. Security Organ Authorization Token Verification \-\> 3\. API Gateway Rate-Limit & Timeout Check \-\> 4\. HTTP Transfer \-\> 5\. Response Schema Verification \-\> 6\. Return Payload to Requesting Organ.  
      MD+ 2

## **11\. Incoming Connections**

* All Hojaiga Organs (01 Brain through 12 Integration) connect to the Infrastructure Organ to emit system logs, query hardware resource constraints, and route outbound API requests.  
   MD+ 2

## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits system telemetry frames, resource warning events, and storage quota alerts (`EVENT_INFRASTRUCTURE_RESOURCE_WARNING`, `EVENT_STORAGE_QUOTA_BREACH`).  
   MD+ 2  
* **External Networks:** Outbound HTTPS/gRPC connections routed exclusively via `api_gateway`.  
   MD+ 1

## **13\. State Management**

The Infrastructure Organ operates continuous operational management states:

* `BOOTSTRAPPING`: Verifying SSD and External HDD mount points, initializing NVML bindings, parsing configuration files.  
   MD+ 1  
* `OPERATIONAL`: Resource monitors active; logging pipeline flushing continuously; servicing API gateway requests.  
   MD+ 2  
* `THROTTLED`: System RAM or CPU load exceeds 85%; enforcing low-priority execution states via `resource_scheduler`.  
   MD+ 1  
* `DEGRADED`: External HDD disconnected or unavailable; logging pipelines buffering strictly to SSD staging area.  
   MD+ 2  
* `SHUTTING_DOWN`: Flushing all unwritten log buffers from RAM/SSD to disk, releasing NVML hooks, terminating network gateways.  
   MD+ 1

## **14\. Event Definitions**

* `EVENT_INFRASTRUCTURE_RESOURCE_WARNING`: Fired when RAM, CPU, or VRAM consumption breaches 80% threshold.  
   MD+ 1  
* `EVENT_VRAM_RELEASED`: Fired when NVML confirms full release of GPU VRAM following Brain process termination.  
   MD+ 1  
* `EVENT_STORAGE_QUOTA_BREACH`: Emitted when remaining space on 100 GB SSD drops below 5 GB.  
   MD+ 1  
* `EVENT_HDD_DISCONNECTED`: Triggered if the External HDD storage drive becomes unreachable during I/O operations.  
   MD+ 2

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "HardwareStatusResponse",  
  "type": "object",  
  "properties": {  
    "timestamp": { "type": "integer" },  
    "cpu\_usage\_percent": { "type": "number" },  
    "ram\_used\_mb": { "type": "integer" },  
    "ram\_total\_mb": { "type": "integer", "default": 32768 },  
    "vram\_used\_mb": { "type": "integer" },  
    "vram\_total\_mb": { "type": "integer", "default": 4096 },  
    "ssd\_free\_gb": { "type": "number" },  
    "hdd\_free\_gb": { "type": "number" },  
    "active\_processes": { "type": "integer" }  
  },  
  "required": \["timestamp", "cpu\_usage\_percent", "ram\_used\_mb", "vram\_used\_mb", "ssd\_free\_gb"\]  
}

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "LogEntryRequest",  
  "type": "object",  
  "properties": {  
    "log\_id": { "type": "string", "format": "uuid" },  
    "timestamp": { "type": "integer" },  
    "source\_organ": { "type": "string" },  
    "log\_level": { "type": "string", "enum": \["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"\] },  
    "message": { "type": "string" },  
    "metadata": { "type": "object" }  
  },  
  "required": \["log\_id", "timestamp", "source\_organ", "log\_level", "message"\]  
}

## **16\. Internal Database Structures**

The Infrastructure Organ maintains an in-memory SQLite performance database (`:memory:`):

* Table `telemetry_history` (`timestamp` INTEGER PRIMARY KEY, `cpu_percent` REAL, `ram_mb` INTEGER, `vram_mb` INTEGER, `ssd_read_kbps` REAL, `ssd_write_kbps` REAL).  
   MD+ 1  
* Table `active_downloads` (`download_id` TEXT PRIMARY KEY, `url` TEXT, `destination_path` TEXT, `bytes_downloaded` INTEGER, `total_bytes` INTEGER, `status` TEXT).  
   MD+ 1  
* Table `api_rate_limits` (`endpoint_domain` TEXT PRIMARY KEY, `request_count` INTEGER, `window_start` TIMESTAMP).  
   MD+ 1

## **17\. Cache Strategy**

* Hardware Telemetry Cache: Latest hardware performance metrics cached in RAM and updated every 1000ms to eliminate NVML/Win32 driver query overhead on frequent requests.  
   MD+ 1  
* Config Value Cache: In-memory hash map caching loaded configuration parameters from `config/` files.

## **18\. Memory Strategy**

* Infrastructure daemon resident RAM footprint capped at 128 MB.  
* Logging buffers utilize a fixed 32 MB circular memory ring buffer to absorb high-burst logging events without heap expansion.  
   MD+ 1

## **19\. Thread Safety**

* Mutex wrappers (`std::mutex` / Python `threading.Lock`) guard NVML driver invocations and resource quota tables.  
   MD  
* Atomic file appenders prevent log frame corruption during concurrent writes.  
   MD+ 1

## **20\. Concurrency**

* Non-blocking asynchronous event loop for IPC handling.  
   MD  
* Dedicated background threads for:  
  1. Telemetry monitoring loop (1000ms frequency).  
      MD  
  2. Log flushing worker (switches RAM buffers to SSD/HDD).  
      MD+ 1  
  3. Download manager thread pool (max 2 concurrent download streams).  
      MD+ 1

## **21\. Hardware Optimization**

* CPU Target: Optimized for Intel Core i7 physical cores, utilizing Win32 process thread affinity masks when necessary to pin intensive processing jobs.  
   MD  
* GPU Target: Direct binding to NVIDIA RTX 3050 via NVML (`pynvml` / C-API) for real-time VRAM allocation tracking.  
   MD+ 1

## **22\. GPU Usage**

* Zero GPU compute or VRAM consumption by the Infrastructure Organ itself.  
   MD  
* Acts strictly as a passive monitor querying NVML drivers to report GPU temperature and VRAM utilization.  
   MD+ 1

## **23\. CPU Usage**

* Idle state CPU footprint: \<0.2%.  
   MD  
* Peak CPU consumption during heavy log flushing and API transfer encryption capped at 5%.  
   MD+ 1

## **24\. SSD Usage**

* Fast 100 GB SSD Runtime partition stores active system binaries, staging log buffers, active download files, and snapshot files.  
   MD+ 1  
* Disk writes utilize sequential append strategies to maximize SSD lifespan and throughput.  
   MD+ 1

## **25\. HDD Usage**

* External HDD holds append-only archived historical logs, knowledge base backups, system execution traces, and media recordings.  
   MD+ 1

## **26\. Security Model**

* Path Isolation: Filesystem manager enforces path traversal blocks (rejecting `../` inputs) to restrict file I/O operations strictly within authorized Hojaiga folder boundaries.  
   MD+ 2  
* Egress Filtering: Outbound API Gateway enforces domain whitelisting and blocks unauthorized external IP communication attempts.  
   MD+ 1

## **27\. Permissions**

* Infrastructure daemon process operates under standard OS user permissions.  
   MD  
* Admin rights requested only during explicit driver or Win32 system query calls when required by host OS.  
   MD+ 1

## **28\. Logging**

* Centralized append-only logging system strictly following Policy Manual Chapter 8\.  
   MD  
* Appends structured JSON logs with fields: `log_id`, `timestamp`, `source_organ`, `log_level`, `message`, `duration_ms`, `error_details`.  
   MD+ 1

## **29\. History Recording**

* Historical operational logs, system hardware telemetry trends, and version update records are committed sequentially to external HDD long-term archives.  
   MD+ 2

## **30\. Recovery Strategy**

* Storage Fallback: If the External HDD becomes unreachable during active logging, `central_logger` automatically redirects write streams to a failover buffer on the 100 GB SSD Runtime partition and fires `EVENT_HDD_DISCONNECTED`.  
   MD+ 2

## **31\. Failure Handling**

* Download Hash Mismatch: Downloaded files failing SHA-256 hash verification are purged immediately, triggering `EVENT_DOWNLOAD_FAILED` and alerting the requesting organ.  
   MD+ 1

## **32\. Validation Rules**

* Outbound API calls must specify valid target URLs, stay within rate limits, and provide required authentication headers.  
   MD+ 2

## **33\. Testing Strategy**

* Unit tests for path resolution security, NVML driver metrics parsing, and circular buffer log flushing.  
   MD+ 1  
* Stress tests: Simulating high-frequency logging streams (10,000 entries/sec) to verify ring-buffer stability and zero loss.  
   MD+ 1

## **34\. Extension Points**

* Custom Telemetry Exporters: Plug-in interface in `hardware/` allowing custom metrics collectors to be registered.  
   MD+ 1

## **35\. Future Compatibility**

* Forward-compatible configuration manifests using versioned schema loaders in `versioning/`.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` Infrastructure Organ Specification.  
   MD+ 1

## **37\. Dependencies**

* Python 3.11+ / C++17 runtime.  
   MD  
* NVIDIA Management Library (NVML) bindings.  
   MD+ 1  
* `aiohttp` / `requests` for API Gateway transfers.  
   MD

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Receives system logs and routes hardware telemetry warnings.  
   MD+ 2  
* **Brain (Organ 01):** Monitored by Infrastructure to confirm complete GPU VRAM clearance upon process termination.  
   MD+ 1  
* **Security (Organ 07):** Validates API Gateway egress permission tokens.  
   MD+ 2  
* **Memory (Organ 03):** Interfaces with Infrastructure for SSD runtime snapshot storage and HDD long-term archiving.  
   MD+ 1

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Infrastructure Kernel\]  
    Core \--\> HW\[Hardware Controller\]  
    Core \--\> Logger\[Central Logger\]  
    Core \--\> FS\[Filesystem Manager\]  
    Core \--\> GW\[API Gateway\]  
    Core \--\> Mon\[Monitoring Engine\]  
    HW \--\>|NVML C-API| GPU\[NVIDIA RTX 3050 VRAM\]  
    HW \--\>|Win32 API| CPU\[Intel Core i7 / RAM\]  
    FS \--\>|Fast I/O| SSD\[100 GB SSD Runtime\]  
    FS \--\>|Archival Stream| HDD\[External HDD Store\]  
    Logger \--\>|Append-Only| SSD

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant Organ as Organ Process (e.g. Brain)  
    participant CNS as Organ 02 (CNS)  
    participant Infra as Organ 09 (Infrastructure)  
    participant Log as Central Logger  
    participant Disk as SSD / HDD Storage

    Organ-\>\>CNS: Emit Log Envelope Payload  
    CNS-\>\>Infra: AppendSystemLog(LogEntry)  
    Infra-\>\>Log: Push to Lockless Ring Buffer  
    Log--\>\>Infra: Ingestion Ack  
    Infra--\>\>CNS: Log Ack  
    Note over Log,Disk: Async Background Worker  
    Log-\>\>Disk: Flush Staged Buffer to SSD/HDD Store

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Hardware Telemetry Loop 1000ms\] \--\> B\[Query CPU & RAM via Win32\]  
    B \--\> C\[Query VRAM via NVML\]  
    C \--\> D{VRAM \> 3.5 GB or RAM \> 85%?}  
    D \-- Yes \--\> E\[Emit EVENT\_INFRASTRUCTURE\_RESOURCE\_WARNING\]  
    D \-- No \--\> F\[Cache Telemetry Metrics in Memory\]  
    E \--\> F  
    F \--\> G\[Check SSD Remaining Capacity\]  
    G \--\> H{SSD Free Space \< 5 GB?}  
    H \-- Yes \--\> I\[Emit EVENT\_STORAGE\_QUOTA\_BREACH\]  
    H \-- No \--\> J\[Sleep Until Next Interval\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Bootstrapping  
    Bootstrapping \--\> Operational : Drives Verified & NVML Up  
    Operational \--\> Throttled : High CPU/RAM Load (\>85%)  
    Throttled \--\> Operational : Load Normalised  
    Operational \--\> Degraded : External HDD Disconnected  
    Degraded \--\> Operational : External HDD Reconnected  
    Operational \--\> ShuttingDown : Termination Triggered  
    ShuttingDown \--\> \[\*\]

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_09\_infrastructure\] \--\> Bin\[bin/infra\_daemon\]  
    Root \--\> Config\[config/hardware\_limits.json\]  
    Root \--\> Storage\[storage/\]  
    Storage \--\> SSD\[storage/ssd\_runtime/\]  
    Storage \--\> HDD\[storage/hdd\_archive/\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/infra\_kernel.py\]  
    Src \--\> HW\[hardware/hardware\_controller.py\]  
    Src \--\> FS\[storage\_engine/filesystem\_manager.py\]  
    Src \--\> Log\[logging\_engine/central\_logger.py\]  
    Src \--\> GW\[gateway/api\_gateway.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_infrastructure\]  
    Pipe \--\> IPC\[Infra IPC Listener Thread\]  
    IPC \--\> Core\[Infrastructure Kernel\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    P1\[1. Log / Query Ingestion\] \--\> P2\[2. Permission & Header Check\]  
    P2 \--\> P3\[3. Lockless Ring Buffer Enqueue\]  
    P3 \--\> P4\[4. Telemetry / File I/O Execution\]  
    P4 \--\> P5\[5. SSD Staging Write\]  
    P5 \--\> P6\[6. Sequential HDD Archival Commit\]

## **46\. Engineering Recommendations**

* Initialize NVIDIA Management Library (NVML) asynchronously during bootstrapping to prevent driver query delays from blocking daemon startup.  
   MD+ 1  
* Use Win32 non-buffered sequential file write flags (`FILE_FLAG_SEQUENTIAL_SCAN`) for log stream writers to optimize disk caching and maximize SSD write performance.  
   MD+ 1

## **47\. Tradeoffs**

* **Centralized Async Logger vs. Direct Per-Organ File Writes:** Routing all system logs through the Infrastructure Organ adds a microsecond IPC transit step, but guarantees append-only log integrity, prevents multi-process file locking conflicts, and centralizes HDD archival flushing.  
   MD+ 2  
* **1000ms Passive Telemetry Polling vs. Real-Time Hardware Event Hooks:** Passive polling introduces up to 1 second of telemetry latency, but eliminates high CPU interrupt overhead associated with continuous real-time hardware polling.  
   MD+ 1

## **48\. Alternatives Considered**

* **Prometheus / Grafana Local Exporter Service:** Rejected to avoid third-party service dependencies, high RAM footprints, and background web server execution overhead.  
   MD  
* **Direct Unrestricted File Access per Organ:** Rejected because multi-process uncoordinated writes cause disk lock contention, log frame corruption, and path security risks.  
   MD+ 2

## **49\. Future Improvements**

* Dynamic CPU thread-affinity tuning based on real-time task priority classes.  
   MD+ 1  
* Automatic SSD TRIM command execution during system maintenance windows to optimize runtime partition performance.  
   MD+ 1

## **50\. Claude Implementation Instructions**

1. Establish file and folder structure as specified in Section 6\.  
    MD  
2. Implement `hardware/nvml_monitor.py` wrapping NVML calls for NVIDIA RTX 3050 VRAM tracking.  
    MD+ 1  
3. Build `logging_engine/central_logger.py` deploying a 32 MB circular ring buffer for non-blocking SSD/HDD writes.  
    MD+ 1  
4. Implement `storage_engine/filesystem_manager.py` enforcing strict path traversal validation.  
    MD+ 1  
5. Set up Named Pipe IPC listener at `\\.\pipe\hojaiga_infrastructure`.  
    MD

