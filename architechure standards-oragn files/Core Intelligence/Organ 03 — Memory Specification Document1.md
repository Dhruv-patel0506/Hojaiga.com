# **Organ 03 — Memory Specification Document**

## **1\. Overview**

The Memory Organ is the multi-tiered state, context, and persistent memory controller of the Hojaiga Automation Operating System. It provides zero-latency state synchronization, hierarchical working memory buffers, contextual session isolation, long-term state compression, and fault-tolerant persistent storage across host SSD and HDD hardware. Operating strictly under CPU control without GPU usage, the Memory Organ manages data retention across explicit temporal scopes without violating organ privacy or system state integrity.

## **2\. Purpose**

The purpose of the Memory Organ is to provide a structured, deterministic memory subsystem that stores, compresses, retrieves, and persists execution states, user interaction contexts, operational rooms, and historical snapshots. It serves as the single source of truth for runtime working states and long-term historical context without allowing memory corruption, state race conditions, or uncoordinated file overwrites.

## **3\. Philosophy**

In accordance with Chapter 4 of the Master Architecture Blueprint, Universal Law 6 (State Integrity), and Policy Manual Chapter 3, Hojaiga maintains multiple distinct, non-overlapping memory layers. Memory systems shall never overwrite one another or blur operational boundaries. Session Memory, Working Memory, Long-Term Memory, Shared Memory, Knowledge Memory, and Historical Memory each serve independent responsibilities. All memory writes are atomic, auditable, and backed by append-only persistence strategies on external HDD storage.

## **4\. Primary Responsibilities**

* **Working Memory Management:** Fast-access volatile memory for active task processing and intermediate DSL state transitions.  
* **Session Memory Management:** Contextual state preservation for active user/agent task sessions, partitioned into isolated operational "Rooms".  
* **Long-Term Memory Persistence:** Vectorized and indexed retrieval of historical execution trajectories, compressed summaries, and operational lessons.  
* **Shared Memory Sockets:** Ring-buffered low-latency shared RAM regions (mmap / Win32 File Mapping) for high-speed cross-organ payload transfers.  
* **Memory Compression & Deduplication:** Algorithmic context pruning, token-aware context summarization, and structural deduplication.  
* **Snapshot & Recovery:** Continuous delta state snapshotting to SSD runtime storage for instant point-in-time recovery after system crashes or hardware restarts.

## **5\. Internal Modules**

* memory\_core: Primary IPC socket interface, payload route handler, and memory orchestration controller.  
* working\_memory: In-memory volatile hash-table and LRU key-value storage engine.  
* session\_manager: Room-based session state isolation engine for managing concurrent workflow environments.  
* long\_term\_store: Embedded SQLite \+ Vector SQLite (sqlite-vec) disk-backed long-term memory engine.  
* shared\_memory\_allocator: OS-native IPC shared memory region manager (CreateFileMappingW / shm\_open).  
* compression\_engine: Context window compressor using LZ4 data compression and recursive semantic token pruning.  
* snapshot\_manager: Delta-logging snapshot worker that commits runtime state markers to disk.

## **6\. Internal Folder Structure**

/organ\_03\_memory  
├── bin/  
│   └── memory\_daemon         \# Core runtime executable process  
├── config/  
│   └── memory\_limits.json    \# Allocation caps for RAM/SSD/HDD  
├── storage/  
│   ├── working/              \# RAM-backed temp swap files  
│   ├── snapshots/            \# SSD delta snapshots (.snap)  
│   └── long\_term/            \# HDD long-term databases (.sqlite)  
├── src/  
│   ├── core/  
│   │   ├── memory\_kernel.py  
│   │   └── allocator.py  
│   ├── volatile/  
│   │   ├── working\_memory.py  
│   │   └── shared\_ram.py  
│   ├── session/  
│   │   ├── session\_room.py  
│   │   └── context\_tracker.py  
│   ├── persistence/  
│   │   ├── lt\_store.py  
│   │   └── snapshot.py  
│   ├── compression/  
│   │   ├── lz4\_compressor.py  
│   │   └── semantic\_pruner.py  
│   └── sockets/  
│       └── ipc\_handler.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* IPC Socket Interface: \\\\.\\pipe\\hojaiga\_memory (Windows) / /tmp/hojaiga\_memory.sock (Linux/Unix).  
  * rpc StoreWorking(Key, Value, TTL) \-\> Ack  
  * rpc FetchWorking(Key) \-\> Value  
  * rpc CreateSessionRoom(RoomID, Metadata) \-\> RoomHandle  
  * rpc AppendSessionContext(RoomID, ContextChunk) \-\> Ack  
  * rpc FetchSessionHistory(RoomID, Depth) \-\> ContextArray  
  * rpc QueryLongTerm(SemanticQueryVector, Limit) \-\> QueryResult  
  * rpc CreateSharedBuffer(BufferID, SizeBytes) \-\> SharedMemoryDescriptor  
  * rpc CreateSnapshot(Tag) \-\> SnapshotID  
  * rpc RestoreSnapshot(SnapshotID) \-\> RecoveryStatus

## **8\. Internal Interfaces**

* IVolatileMemory:  
  * allocate\_block(size): Reserves locked memory addresses in core system RAM.  
  * free\_block(handle): Safely releases memory region back to heap.  
* IPersistentStorage:  
  * commit\_delta(transaction\_log): Flushes unwritten WAL frames from SSD to HDD long-term storage.  
  * prune\_expired\_sessions(): Cleans up ephemeral session rooms older than configured retention limits.

## **9\. Socket Definitions**

* Named Pipe Socket: hojaiga\_memory.  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte length | 2-byte op\_code | JSON Payload / Raw Bytes \].  
* Maximum Message Size: 16 MB over socket; payloads \> 16 MB automatically route through Shared Memory allocations.

## **10\. Pipeline Definitions**

* MemoryIngestionPipeline:  
  1. CNS Routes Context Entry \-\> 2\. Memory Core Schema Check \-\> 3\. Write to Volatile Working Memory \-\> 4\. Append to Session Room Stream \-\> 5\. Async Compression Worker \-\> 6\. Flush to Disk WAL (SSD Delta Snapshot).  
* MemoryRetrievalPipeline:  
  1. CNS Requests Context Query \-\> 2\. Memory Core Checks Working RAM \-\> 3\. If Cache Miss, Query SQLite Long-Term Store \-\> 4\. Decompress Binary Frames \-\> 5\. Assemble Context Response \-\> 6\. Stream Result via Socket.

## **11\. Incoming Connections**

* **CNS Organ (02):** Transmits state store/fetch commands and orchestrates cross-organ memory access.  
* **Brain Organ (01):** Queries long-term history and session context for prompt context injection.  
* **Agents Organ (10):** Direct context streaming to active agent session rooms via CNS proxy.

## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits memory status events (EVENT\_MEMORY\_WARNING, EVENT\_SNAPSHOT\_CREATED, EVENT\_MEMORY\_CORRUPTION\_DETECTED).  
* **Infrastructure Organ (09):** Dispatches physical I/O write status and disk capacity metrics.

## **13\. State Management**

The Memory Organ manages memory state via defined runtime stages:

* INITIALIZING: Mounting disk stores, loading index tables, verifying snapshot integrity.  
* SYNCHRONIZED: Volatile and persistent stores active; accepting read/write transactions.  
* COMPACTING: Compression engine running background context pruning and database vacuuming.  
* FLUSHING: Synchronizing RAM buffers to SSD snapshot WAL before system shutdown or hibernate.  
* RECOVERY: Rolling back corrupted RAM state to the last valid SSD snapshot marker.

## **14\. Event Definitions**

* EVENT\_MEMORY\_SNAPSHOT\_CREATED: Emitted when an atomic point-in-time state marker is saved.  
* EVENT\_MEMORY\_ROOM\_CREATED: Fired when a new isolated session room is opened.  
* EVENT\_MEMORY\_THRESHOLD\_EXCEEDED: Triggered when working RAM allocations breach 80% capacity limit.  
* EVENT\_MEMORY\_COMPRESSION\_COMPLETED: Emitted when context summarization completes.

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "MemoryStoreRequest",  
  "type": "object",  
  "properties": {  
    "transaction\_id": { "type": "string", "format": "uuid" },  
    "memory\_layer": {   
      "type": "string",   
      "enum": \["working", "session", "long\_term", "shared"\]   
    },  
    "room\_id": { "type": "string" },  
    "key": { "type": "string" },  
    "value": { "type": "object" },  
    "ttl\_seconds": { "type": "integer", "default": 0 }  
  },  
  "required": \["transaction\_id", "memory\_layer", "key", "value"\]  
}

## **16\. Internal Database Structures**

The Memory Organ utilizes embedded SQLite database instances:

* working\_mem.db (:memory:):  
  * Table kv\_store (key TEXT PRIMARY KEY, val BLOB, created\_at TIMESTAMP, expires\_at TIMESTAMP).  
* session\_rooms.sqlite (SSD Runtime Storage):  
  * Table rooms (room\_id TEXT PRIMARY KEY, created\_at TIMESTAMP, metadata TEXT).  
  * Table room\_messages (msg\_id INTEGER PRIMARY KEY AUTOINCREMENT, room\_id TEXT, role TEXT, content TEXT, timestamp TIMESTAMP).  
* long\_term\_memory.sqlite (External HDD Storage):  
  * Table knowledge\_nodes (node\_id TEXT PRIMARY KEY, content TEXT, embedding FLOAT\[384\], tags TEXT, created\_at TIMESTAMP).

## **17\. Cache Strategy**

* Dual LRU Cache: High-frequency session memory stored in an in-memory ring buffer (128 MB max).  
* Write-Through Cache: Writes to Working Memory update RAM instantly and queue an asynchronous write to the SSD Write-Ahead Log (WAL).

## **18\. Memory Strategy**

* Physical RAM Allocation Cap: 2.0 GB maximum across working memory buffers and shared memory mappings.  
* Strict process bounds enforce page locking (VirtualLock on Windows) to prevent swapping sensitive keys or memory pools to host disk paging files.

## **19\. Thread Safety**

* Multi-reader, single-writer synchronization implemented using Read-Write Locks (std::shared\_mutex / Python threading.RLock).  
* Transactions on SQLite persistent stores enforce Strict Serializability using Write-Ahead Logging (PRAGMA journal\_mode=WAL).

## **20\. Concurrency**

* Asynchronous, non-blocking I/O loop for IPC request handling.  
* Background persistent worker thread pool (2 threads) assigned exclusively for handling disk writes, LZ4 compression, and snapshot generation without blocking memory read paths.

## **21\. Hardware Optimization**

* RAM: High-speed memory operations targeting 32 GB host DDR4/DDR5 RAM.  
* CPU: Parallel vector calculations for memory embedding lookups using AVX2 SIMD CPU instructions.

## **22\. GPU Usage**

* Zero GPU usage. Vector similarity search and context index scanning executed entirely on CPU SIMD units.

## **23\. CPU Usage**

* Idle CPU footprint: \<0.5%.  
* Peak CPU usage during semantic context compression or disk snapshotting capped at 10% on Intel Core i7.

## **24\. SSD Usage**

* Runtime session state, active room databases, and rapid snapshot markers stored on 100 GB SSD Runtime partition.  
* Fast write throughput using sequential WAL append operations to minimize write amplification.

## **25\. HDD Usage**

* External HDD holds append-only archived historical sessions, long-term knowledge indexes, and system execution trace dumps.

## **26\. Security Model**

* Room Isolation: Session contexts strictly scoped to unique room\_id strings; organs cannot cross-query room states without Security Organ validation.  
* AES-256 Encryption-at-Rest for all snapshot files and SQLite databases written to disk.

## **27\. Permissions**

* Memory Organ daemon process executes under standard restricted user account.  
* Memory mapped files protected using OS security descriptors permitting access only to Hojaiga process group members.

## **28\. Logging**

* Structured JSON audit logging following Policy Manual Chapter 8\.  
* Logs every transaction ID, target memory layer, read/write operation, payload size, and allocation latency.

## **29\. History Recording**

* All closed session rooms and state snapshots are appended sequentially to external HDD long-term storage and indexed for semantic search.

## **30\. Recovery Strategy**

* Crash Recovery: Upon boot, snapshot\_manager scans the SSD snapshot directory. If an ungraceful shutdown mark is found, the system replays the WAL log against the last clean .snap image to rebuild working memory.

## **31\. Failure Handling**

* Disk Full Detection: If SSD runtime storage drops below 2 GB remaining space, Memory Organ halts disk snapshotting, flushes non-essential cache to HDD, and emits EVENT\_MEMORY\_THRESHOLD\_EXCEEDED.  
* Database Corruption: Corrupted SQLite files automatically quarantined and recovered from the latest HDD mirror.

## **32\. Validation Rules**

* Every incoming store payload validated against schema rules: key length \<= 256 bytes, value size \<= 16 MB per operation.

## **33\. Testing Strategy**

* Unit tests for LRU eviction, LZ4 compression ratio verification, and shared memory descriptor creation.  
* Chaos tests: Simulating process crashes mid-write transaction to verify WAL snapshot recovery integrity.

## **34\. Extension Points**

* Custom Memory Storage Backends: Interface drivers allowed for external vector index backends or persistent key-value engines.

## **35\. Future Compatibility**

* Dynamic schema evolution for SQLite stores using versioned migration scripts stored in storage/schema\_migrations/.

## **36\. Versioning**

* Semantic Versioning: v1.0.0 Memory Organ Specification.

## **37\. Dependencies**

* SQLite 3.45+ with sqlite-vec extension.  
* LZ4 Compression C-bindings / py-lz4.  
* Windows Win32 API (MemoryMappedFiles) / POSIX shm\_open.

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Routes all incoming/outgoing memory socket traffic.  
* **Brain (Organ 01):** Retrieves session history and pushes reasoning context to working memory.  
* **Security (Organ 07):** Validates session room authorization tokens.  
* **Infrastructure (Organ 09):** Monitors disk storage health and triggers external HDD archival.

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Memory Core\]  
    Core \--\> WM\[Volatile Working Memory RAM\]  
    Core \--\> SM\[Session Manager Rooms\]  
    Core \--\> LTS\[Long-Term Vector Store SQLite\]  
    Core \--\> Comp\[Compression Engine LZ4\]  
    Core \--\> Snap\[Snapshot Engine\]  
    Snap \--\>|Delta WAL| SSD\[SSD Runtime Storage\]  
    LTS \--\>|Archival Stream| HDD\[External HDD Storage\]

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant CNS as CNS Organ  
    participant Mem as Memory Core  
    participant RAM as Working RAM  
    participant SSD as SSD Storage  
    participant HDD as HDD Storage

    CNS-\>\>Mem: StoreSessionContext(RoomID, Data)  
    Mem-\>\>RAM: Write Active State Frame  
    RAM--\>\>Mem: Ack  
    Mem-\>\>Mem: Queue Background Compression  
    Mem-\>\>SSD: Write Delta to WAL (.snap)  
    SSD--\>\>Mem: Disk Commit Ack  
    Mem--\>\>CNS: Success Response  
    Note over Mem,HDD: Async Session Archive  
    Mem-\>\>HDD: Append Closed Room to Long-Term Archive

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Incoming Context Query\] \--\> B{Layer Specified?}  
    B \-- Working Memory \--\> C\[Read Volatile RAM KV Store\]  
    B \-- Session Room \--\> D\[Query SQLite Session DB\]  
    B \-- Long Term \--\> E\[Execute Vector Search on HDD Index\]  
    C \--\> F{Found in Cache?}  
    F \-- Yes \--\> G\[Return Context Payload\]  
    F \-- No \--\> D  
    D \--\> G  
    E \--\> H\[Decompress LZ4 Payload\]  
    H \--\> G

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Initializing  
    Initializing \--\> Synchronized : Storage Mounted & Verified  
    Synchronized \--\> Compacting : Compression Task Triggered  
    Compacting \--\> Synchronized : Context Summarized  
    Synchronized \--\> Flushing : System Shutdown Signal  
    Flushing \--\> \[\*\] : Snapshot Committed  
    Synchronized \--\> Recovery : Crash Marker Detected  
    Recovery \--\> Synchronized : Rollback Successful

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_03\_memory\] \--\> Bin\[bin/memory\_daemon\]  
    Root \--\> Storage\[storage/\]  
    Storage \--\> Work\[storage/working/\]  
    Storage \--\> Snaps\[storage/snapshots/\]  
    Storage \--\> LongTerm\[storage/long\_term/\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/memory\_kernel.py\]  
    Src \--\> Vol\[volatile/working\_memory.py\]  
    Src \--\> Sess\[session/session\_room.py\]  
    Src \--\> Persist\[persistence/lt\_store.py\]  
    Src \--\> Comp\[compression/lz4\_compressor.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master\] \-- NamedPipe \--\> MemPipe\[\\\\.\\pipe\\hojaiga\_memory\]  
    MemPipe \--\> Handler\[IPC Handler Thread\]  
    Handler \--\> SharedMem\[OS Shared RAM Region mmap\]  
    Handler \--\> Core\[Memory Orchestration Core\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    P1\[1. IPC Ingestion\] \--\> P2\[2. Layer Routing\]  
    P2 \--\> P3\[3. RAM Hash Commit\]  
    P3 \--\> P4\[4. Context LZ4 Compression\]  
    P4 \--\> P5\[5. SSD WAL Persistence\]  
    P5 \--\> P6\[6. HDD Long-Term Indexing\]

## **46\. Engineering Recommendations**

* Force sqlite3 to use WAL mode (PRAGMA journal\_mode=WAL; PRAGMA synchronous=NORMAL;) to allow concurrent non-blocking reads while writing session logs.  
* Pre-allocate 64 MB chunk blocks for shared memory regions to avoid dynamic Windows kernel object creation overhead during multi-organ stream bursts.

## **47\. Tradeoffs**

* **In-Memory Volatile Layer vs. Pure Disk Operations:** Using RAM-first working memory provides microsecond access speeds, but requires absolute reliance on background WAL delta flushing to prevent data loss on unexpected power termination.  
* **LZ4 Speed vs. Higher Compression Ratios (e.g., ZSTD):** LZ4 selected for ultra-fast CPU decompressive throughput (\<1ms context unpacking), sacrificing \~5% compression efficiency compared to heavier algorithms.

## **48\. Alternatives Considered**

* **Redis Local Instance:** Rejected due to additional process dependencies, higher baseline RAM footprint, and violation of native executable runtime constraints.  
* **LMDB Key-Value Store:** Rejected in favor of SQLite to leverage native vector search extensions (sqlite-vec) for long-term semantic knowledge retrieval within a single database binary.

## **49\. Future Improvements**

* Implementation of custom hierarchical context summarization using quantized on-disk token trees.  
* Hardware-accelerated memory snapshot checksum verification using Intel CRC32 CPU instructions.

## **50\. Claude Implementation Instructions**

1. Construct directory framework per Section 6\.  
2. Implement volatile/working\_memory.py using thread-safe LRU dictionary with VirtualLock bounds.  
3. Build SQLite database drivers in persistence/lt\_store.py enforcing WAL configuration and sqlite-vec extension binding.  
4. Set up Windows Named Pipe listener at \\\\.\\pipe\\hojaiga\_memory handling structured binary frame headers.  
5. Implement background WAL snapshot worker committing delta markers to storage/snapshots/ every 30 seconds or 1000 write operations.

