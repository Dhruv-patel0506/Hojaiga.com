# **Organ 04 — Knowledge Specification Document**

## **1\. Overview**

The Knowledge Organ is the authoritative repository, semantic classifier, capabilities registry, and documentation intelligence engine of the Hojaiga Automation Operating System. It maintains structured, versioned, and immutable knowledge representations of applications, APIs, operating system utilities, execution workflows, system architecture, command capabilities, and governance policies. Operating CPU-first with disk-backed storage, the Knowledge Organ translates abstract capability requests into concrete executable targets and system documentation queries without relying on dynamic cloud lookups or unverified assumptions.

MD+ 4

## **2\. Purpose**

The purpose of the Knowledge Organ is to store, retrieve, index, match, and incrementally evolve all declarative knowledge within Hojaiga. It serves as the single source of truth for application capabilities, operating system capabilities, workflow rules, aliases, and system documentation (including the Constitution, Law Book, Policy Manual, and Architecture Blueprints). In accordance with Foundational Law 8 (Capability-First Execution) and Policy Manual Chapter 5, the Knowledge Organ decouples user intents from specific binaries by resolving tasks to application profiles by capability first.

MD+ 4

## **3\. Philosophy**

In strict compliance with Master Architecture Blueprint Chapter 5, Universal Law 10 (Evidence-Based Decision Making), and Policy Manual Chapter 4, knowledge in Hojaiga is structured, deterministic, auditable, and version-tracked. Knowledge objects never overwrite historical context arbitrarily; they evolve incrementally through merge operations and version updates. No automation or plan may execute without context verification provided by the Knowledge Organ. The Knowledge Organ strictly isolates factual knowledge from temporary runtime state (owned by Organ 03 Memory) and raw file logs (owned by Organ 09 Infrastructure).

MD+ 4

## **4\. Primary Responsibilities**

* **Capability Registry & Resolution:** Map capability queries (e.g., "screen\_recording", "pdf\_extraction") to installed application profiles and tools based on OS, priority, reliability score, and compatibility.  
   MD+ 1  
* **Application Intelligence Management:** Maintain profiles for installed software including paths, capabilities, aliases, CLI flags, OS dependencies, and failure characteristics.  
   MD+ 1  
* **Governing Document Knowledge Base:** Index and serve the Constitution, Law Book, Policy Manual, and Technical Architecture specifications to all organs for context verification.  
   MD+ 3  
* **Workflow & Command Knowledge:** Store standardized step-by-step procedures, terminal commands, and system integration patterns.  
   MD+ 2  
* **Semantic Vector & BM25 Indexing:** Provide hybrid semantic and full-text keyword search across system documentation, APIs, and operational knowledge repositories.  
   MD+ 1  
* **Incremental Knowledge Evolution:** Parse execution feedback from the Learning Organ to update application reliability scores and capability aliases without structural corruption.  
   MD+ 2

## **5\. Internal Modules**

* `knowledge_core`: Central IPC interface, query router, and knowledge request lifecycle coordinator.  
* `capability_registry`: Capability-to-provider matcher, priority evaluator, and alias resolution engine.  
   MD+ 1  
* `app_intelligence`: Application profile manager tracking installed software capabilities, versions, and operational health scores.  
   MD+ 1  
* `doc_engine`: Markdown/JSON document parser, validator, and reader for governing files and system blueprints.  
   MD+ 3  
* `hybrid_search_engine`: Combined BM25 text indexer and CPU-based vector search engine (`sqlite-vec` / HNSW index).  
   MD+ 1  
* `knowledge_merger`: Differential updater handling incremental additions, alias additions, and schema evolution.  
   MD+ 1  
* `policy_verifier`: Evaluates proposed execution parameters against stored policy rules and constitutional constraints.  
   MD+ 2

## **6\. Internal Folder Structure**

/organ\_04\_knowledge  
├── bin/  
│   └── knowledge\_daemon      \# Main process executable  
├── config/  
│   └── knowledge\_config.json \# Index paths and engine configurations  
├── data/  
│   ├── system\_docs/          \# Constitution, Law Book, Policy Manual, Blueprints  
│   ├── profiles/             \# Application intelligence JSON profiles  
│   ├── capabilities/         \# Capability definitions and mappings  
│   └── workflows/            \# Standardized workflow definitions  
├── storage/  
│   ├── indexes/              \# BM25 full-text indexes (SSD Runtime)  
│   └── knowledge\_db.sqlite   \# Primary SQLite knowledge store (SSD/HDD)  
├── src/  
│   ├── core/  
│   │   ├── knowledge\_kernel.py  
│   │   └── query\_dispatcher.py  
│   ├── capabilities/  
│   │   ├── registry.py  
│   │   └── app\_profile.py  
│   ├── docs/  
│   │   ├── doc\_parser.py  
│   │   └── policy\_reader.py  
│   ├── search/  
│   │   ├── bm25\_engine.py  
│   │   └── vector\_search.py  
│   ├── evolution/  
│   │   └── incremental\_merger.py  
│   └── sockets/  
│       └── ipc\_server.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* `IPC Socket Interface`: `\\.\pipe\hojaiga_knowledge` (Windows) / `/tmp/hojaiga_knowledge.sock` (Linux/Unix).  
   MD  
  * `rpc ResolveCapability(CapabilityQuery)` \-\> `CapabilityProviderList`  
  * `rpc QueryDocumentation(DocQueryPayload)` \-\> `DocSearchResult`  
  * `rpc GetAppProfile(AppNameOrAlias)` \-\> `AppProfileData`  
  * `rpc ReadPolicy(PolicyCategory)` \-\> `PolicyRules`  
  * `rpc SearchKnowledge(HybridSearchQuery)` \-\> `KnowledgeMatchArray`  
  * `rpc UpdateAppHealthScore(HealthUpdatePayload)` \-\> `Ack`  
  * `rpc IngestKnowledge(KnowledgeIngestPayload)` \-\> `IngestStatus`

## **8\. Internal Interfaces**

* `ICapabilityResolver`:  
  * `find_providers(capability_name, OS_platform)`: Queries installed app registry and returns ordered provider options.  
  * `register_alias(capability_name, alias_string)`: Appends alternative terms to capability index.  
* `IDocumentationReader`:  
  * `load_governing_doc(doc_type)`: Ingests raw Markdown file, validates structure, and returns AST representation.  
     MD+ 3  
* `IHybridSearch`:  
  * `execute_hybrid_query(text, vector, limit, alpha)`: Blends BM25 score and vector cosine similarity.

## **9\. Socket Definitions**

* Named Pipe Socket: `hojaiga_knowledge`.  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
   MD  
* Max Payload Size: 16 MB per request.

## **10\. Pipeline Definitions**

* `CapabilityResolutionPipeline`:  
  1. Brain/CNS Query Capability \-\> 2\. Knowledge Core Schema Check \-\> 3\. Match Capability ID in Registry \-\> 4\. Filter by Installed & Platform Compatible \-\> 5\. Sort Providers by Priority and Health Score \-\> 6\. Return Provider Specs.  
      MD+ 2  
* `DocumentationSearchPipeline`:  
  1. Ingestion Request \-\> 2\. Parse Markdown AST \-\> 3\. Extract Headings & Paragraph Chunks \-\> 4\. Generate Lexical BM25 Tokens & CPU Vectors \-\> 5\. Upsert to `knowledge_db.sqlite` \-\> 6\. Index Ack.  
      MD+ 3

## **11\. Incoming Connections**

* **Brain Organ (01):** Requests capability lookups, workflow context, and documentation verification prior to planning.  
   MD+ 2  
* **CNS Organ (02):** Routes incoming knowledge lookup and resolution tasks.  
   MD+ 1  
* **Learning Organ (08):** Sends application performance score updates and newly discovered execution strategies.  
   MD+ 2  
* **Agents Organ (10):** Queries application parameters, CLI flags, and API schemas during task execution.  
   MD+ 1

## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits status events (`EVENT_KNOWLEDGE_UPDATED`, `EVENT_CAPABILITY_UNRESOLVED`).  
   MD+ 1  
* **Infrastructure Organ (09):** Queries filesystem path existence to verify installed software binaries.  
   MD

## **13\. State Management**

The Knowledge Organ transitions through clear operational states:

* `INITIALIZING`: Loading SQLite knowledge stores, parsing core governing documents, and building runtime memory caches.  
   MD+ 3  
* `READY`: Fully indexed; servicing capability resolution and document search requests.  
   MD  
* `INDEXING`: Asynchronously updating BM25/Vector search indexes following a knowledge merge.  
   MD+ 1  
* `DEGRADED`: Primary index file missing or corrupted; running in read-only fallback mode using static JSON files.  
   MD+ 2  
* `MAINTENANCE`: Vacuuming SQLite databases, purging obsolete temp files, and optimizing search trees.  
   MD

## **14\. Event Definitions**

* `EVENT_KNOWLEDGE_INDEXED`: Emitted when document ingestion or index rebuild finishes.  
   MD+ 1  
* `EVENT_CAPABILITY_RESOLVED`: Fired when a capability request is mapped to an execution target.  
   MD+ 1  
* `EVENT_APP_PROFILE_UPDATED`: Triggered when an application's health score or alias list changes.  
   MD+ 1  
* `EVENT_GOVERNING_DOC_LOADED`: Fired when Constitution, Law Book, or Policy Manual AST is updated in cache.  
   MD+ 3

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "CapabilityResolutionRequest",  
  "type": "object",  
  "properties": {  
    "request\_id": { "type": "string", "format": "uuid" },  
    "capability": { "type": "string" },  
    "target\_os": { "type": "string", "default": "Windows\_11" },  
    "preferred\_provider": { "type": "string" },  
    "min\_reliability\_score": { "type": "number", "minimum": 0.0, "maximum": 1.0 }  
  },  
  "required": \["request\_id", "capability"\]  
}

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "AppProfile",  
  "type": "object",  
  "properties": {  
    "app\_id": { "type": "string" },  
    "name": { "type": "string" },  
    "aliases": { "type": "array", "items": { "type": "string" } },  
    "capabilities": { "type": "array", "items": { "type": "string" } },  
    "installed": { "type": "boolean" },  
    "os\_platform": { "type": "string" },  
    "executable\_path": { "type": "string" },  
    "version": { "type": "string" },  
    "reliability\_score": { "type": "number" },  
    "priority": { "type": "integer" }  
  },  
  "required": \["app\_id", "name", "capabilities", "installed", "executable\_path"\]  
}

## **16\. Internal Database Structures**

The Knowledge Organ utilizes embedded SQLite with FTS5 and `sqlite-vec` extensions (`storage/knowledge_db.sqlite`):

* Table `capabilities` (`cap_id` TEXT PRIMARY KEY, `name` TEXT, `description` TEXT, `aliases_json` TEXT).  
   MD+ 1  
* Table `app_profiles` (`app_id` TEXT PRIMARY KEY, `name` TEXT, `executable_path` TEXT, `installed` INTEGER, `version` TEXT, `reliability_score` REAL, `priority` INTEGER, `data_json` TEXT).  
   MD+ 1  
* Table `capability_providers` (`cap_id` TEXT, `app_id` TEXT, PRIMARY KEY(cap\_id, app\_id)).  
   MD+ 1  
* Table `doc_chunks_fts` (Virtual FTS5 Table: `chunk_id`, `doc_type`, `title`, `content_text`).  
   MD+ 3  
* Table `doc_chunks_vec` (`chunk_id` TEXT PRIMARY KEY, `embedding` FLOAT\[384\]).  
   MD+ 1

## **17\. Cache Strategy**

* Core Governing Document AST Cache: Constitution, Law Book, and Policy Manual reside permanently in RAM once parsed.  
   MD+ 3  
* Provider Resolution Cache: LRU Cache (256 slots) caching resolved capability-to-application provider objects for rapid lookup.

## **18\. Memory Strategy**

* Volatile RAM footprint kept strictly below 512 MB.  
* FTS5 and vector index lookups executed via memory-mapped SQLite files (`PRAGMA mmap_size=268435456`) to leverage OS page caching efficiently without inflating process private memory.  
   MD

## **19\. Thread Safety**

* Multi-threaded read operations on SQLite protected by shared read locks.  
* Knowledge database updates (such as health score updates or new knowledge ingestion) execute through a single-threaded write worker queue to ensure database lock safety and avoid lock contention.  
   MD

## **20\. Concurrency**

* Asynchronous IPC request processing using non-blocking I/O event loops.  
* Background indexing tasks run on isolated worker threads bounded to low process priority to prevent CPU starvation of active execution tasks.  
   MD

## **21\. Hardware Optimization**

* CPU: Utilizes AVX-512 / AVX2 vector SIMD instructions on Intel Core i7 for rapid vector similarity calculations during hybrid searches.  
   MD  
* Storage: Direct SSD read paths for indexing structures guarantee sub-5ms query latency.  
   MD

## **22\. GPU Usage**

* Zero GPU usage. All vector embedding calculations for knowledge indexing and retrieval are performed exclusively on the CPU. GPU VRAM is reserved strictly for Brain Organ LLM inference.  
   MD+ 1

## **23\. CPU Usage**

* Idle state CPU usage: \<0.2%.  
   MD  
* Peak CPU usage during full-text/vector index updates or bulk Markdown ingestion capped at 15% across physical CPU cores.  
   MD+ 3

## **24\. SSD Usage**

* Runtime SQLite database, FTS5 indexes, application JSON profiles, and system documentation Markdown source files stored on 100 GB SSD Runtime.  
   MD+ 3

## **25\. HDD Usage**

* External HDD stores archived historical knowledge snapshots, legacy documentation versions, and bulk knowledge backup dumps.  
   MD+ 2

## **26\. Security Model**

* Governing Document Protection: Core governing documents (Constitution, Law Book, Policy Manual) are read-only to all runtime processes.  
   MD+ 3  
* Modification Governance: Autonomous processes cannot alter knowledge base schemas or core documentation without governance authorization.  
   MD+ 2

## **27\. Permissions**

* Executable permissions scoped to the local Hojaiga user account.  
   MD  
* System documentation files set with file-system level read-only access flags for non-admin execution contexts.  
   MD+ 3

## **28\. Logging**

* Structured JSON logging compliant with Policy Manual Chapter 8\.  
   MD  
* Logs query parameters, resolved capabilities, matching scores, search latency, and index modification events.  
   MD+ 1

## **29\. History Recording**

* Knowledge base changes, application score updates, and capability additions are recorded as immutable delta events in the external HDD history store.  
   MD+ 2

## **30\. Recovery Strategy**

* Automatic Index Reconstruction: If the SQLite FTS5/Vector index becomes corrupted or unreadable, `doc_engine` automatically scans `data/system_docs/` and `data/profiles/` to rebuild the index from raw source files.  
   MD+ 3

## **31\. Failure Handling**

* Unresolved Capability: Returns empty provider list with `EVENT_CAPABILITY_UNRESOLVED`, triggering the Brain Organ to evaluate alternative execution strategies or prompt the user.  
   MD+ 2

## **32\. Validation Rules**

* Application profiles must adhere strictly to the JSON Schema (valid executable path, explicit installed flag, at least one declared capability).  
   MD+ 1

## **33\. Testing Strategy**

* Unit tests for capability alias resolution, provider sorting algorithms, and Markdown AST parsing.  
   MD+ 3  
* Benchmark tests verifying sub-10ms response times for hybrid documentation searches.

## **34\. Extension Points**

* Plug-in Document Parsers: Modular parsers for ingesting extra documentation formats (e.g., OpenAPI specs, Python docstrings, Windows CLI help texts).  
   MD+ 1

## **35\. Future Compatibility**

* Schema migration scripts managed via versioned SQL migrations under `src/evolution/migrations/`.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` Knowledge Organ Specification.  
   MD+ 1

## **37\. Dependencies**

* SQLite 3.45+ with `fts5` and `sqlite-vec` extensions.  
   MD  
* Python 3.11+ / C++17 runtime environment.  
   MD  
* `jsonschema` for payload and profile verification.  
   MD

## **38\. Interaction with Other Organs**

* **Brain (Organ 01):** Resolves capability dependencies and verifies documentation context prior to planning.  
   MD+ 3  
* **CNS (Organ 02):** Routes all incoming/outgoing Knowledge socket IPC packets.  
   MD+ 1  
* **Learning (Organ 08):** Ingests application score adjustments and workflow optimizations.  
   MD+ 2  
* **Infrastructure (Organ 09):** Validates binary executable paths on disk.  
   MD

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Knowledge Core\]  
    Core \--\> CapReg\[Capability Registry\]  
    Core \--\> AppIntel\[Application Intelligence\]  
    Core \--\> DocEng\[Documentation Engine\]  
    Core \--\> Search\[Hybrid Search Engine\]  
    DocEng \--\>|Parses| SystemDocs\[System Docs: Constitution, LawBook, Policies\]  
    CapReg \--\> AppIntel  
    AppIntel \--\>|App Profiles| DB\[(Knowledge SQLite DB)\]  
    Search \--\>|FTS5 & Vector| DB

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant Brain as Organ 01 (Brain)  
    participant CNS as Organ 02 (CNS)  
    participant Knw as Organ 04 (Knowledge)  
    participant DB as Knowledge SQLite DB

    Brain-\>\>CNS: Query Capability ("screen\_recording")  
    CNS-\>\>Knw: ResolveCapabilityPayload  
    Knw-\>\>DB: Query Capability Providers & App Profiles  
    DB--\>\>Knw: Return Matches (OBS Studio, Screen Recorder)  
    Knw-\>\>Knw: Sort Providers by Installed Status & Health Score  
    Knw--\>\>CNS: CapabilityProviderList (Top: OBS Studio)  
    CNS--\>\>Brain: Provider Details

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Capability Request Received\] \--\> B{In LRU Cache?}  
    B \-- Yes \--\> C\[Return Cached Provider List\]  
    B \-- No \--\> D\[Query SQLite Capabilities Table\]  
    D \--\> E\[Filter Installed & Platform Compatible Apps\]  
    E \--\> F{Providers Found?}  
    F \-- Yes \--\> G\[Sort by Priority & Reliability Score\]  
    F \-- No \--\> H\[Emit EVENT\_CAPABILITY\_UNRESOLVED\]  
    G \--\> I\[Update Cache & Return Response\]  
    H \--\> J\[Return Empty Provider List to Brain\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Initializing  
    Initializing \--\> Ready : Docs Loaded & DB Verified  
    Ready \--\> Indexing : Ingestion / Rebuild Triggered  
    Indexing \--\> Ready : Index Rebuilt  
    Ready \--\> Degraded : SQLite Corrupted  
    Degraded \--\> Indexing : Auto-Rebuild Triggered  
    Ready \--\> Maintenance : Vacuum / Optimization Call  
    Maintenance \--\> Ready : Complete

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_04\_knowledge\] \--\> Bin\[bin/knowledge\_daemon\]  
    Root \--\> Data\[data/\]  
    Data \--\> SysDocs\[data/system\_docs/\]  
    Data \--\> Profiles\[data/profiles/\]  
    Data \--\> Caps\[data/capabilities/\]  
    Root \--\> Storage\[storage/knowledge\_db.sqlite\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/knowledge\_kernel.py\]  
    Src \--\> Cap\[capabilities/registry.py\]  
    Src \--\> Docs\[docs/doc\_parser.py\]  
    Src \--\> Search\[search/hybrid\_search\_engine.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_knowledge\]  
    Pipe \--\> IPC Server\[Knowledge IPC Listener\]  
    IPC Server \--\> Queue\[Request Queue\]  
    Queue \--\> Core\[Knowledge Kernel\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    Step1\[1. IPC Ingestion\] \--\> Step2\[2. Schema Validation\]  
    Step2 \--\> Step3\[3. Capability Registry Lookup\]  
    Step3 \--\> Step4\[4. App Profile Verification\]  
    Step4 \--\> Step5\[5. Priority & Health Ranking\]  
    Step5 \--\> Step6\[6. Output Packaging & Dispatch\]

## **46\. Engineering Recommendations**

* SQLite FTS5 indexes should use the `porter` stemming tokenizer to ensure queries like "recording", "record", or "recorder" resolve to the same underlying capabilities.  
   MD+ 1  
* Pre-parse and compile the Constitution, Law Book, and Policy Manual into static memory structs during `INITIALIZING` to guarantee sub-1ms access when the Brain Organ requests governing rules.  
   MD+ 3

## **47\. Tradeoffs**

* **CPU Vector Hybrid Search vs. External Cloud Vector DB:** Eliminates external network dependencies and API token costs, but caps maximum vector search throughput compared to dedicated GPU cluster stores.  
   MD  
* **Local Static Profiles vs. Dynamic Web Scraping:** Guarantees deterministic, predictable execution behavior without network failure risks, but requires explicit updates when new software versions change CLI flags.  
   MD+ 2

## **48\. Alternatives Considered**

* **Elasticsearch / OpenSearch Local Process:** Rejected due to excessive Java Virtual Machine (JVM) RAM overhead (requires \>2 GB RAM) violating target resource constraints.  
   MD  
* **Flat JSON Files Only:** Rejected due to slow search speeds and lack of transactional guarantees when scaling to thousands of application capabilities and documentation chunks.  
   MD+ 1

## **49\. Future Improvements**

* Automatic background scanning of Windows Start Menu and Registry to discover newly installed local applications and generate draft profiles.  
   MD+ 1  
* Integration of lightweight C-based graph query engines for complex multi-hop capability relationship mappings.  
   MD+ 1

## **50\. Claude Implementation Instructions**

1. Establish directory framework per Section 6\.  
    MD  
2. Copy `Constitution.md`, `LawBook.md`, `PolicyManual.md`, and `MasterArchitectureBlueprint.md` into `data/system_docs/`.  
    MD+ 3  
3. Implement `docs/doc_parser.py` to convert Markdown files into chunked AST structures.  
    MD+ 3  
4. Build `storage/knowledge_db.sqlite` initialization scripts setting up FTS5 and `capabilities` tables.  
    MD+ 1  
5. Implement `sockets/ipc_server.py` listening on Windows Named Pipe `\\.\pipe\hojaiga_knowledge`.  
    MD

