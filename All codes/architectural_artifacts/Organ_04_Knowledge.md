# Organ_04_Knowledge.md

## 1. Pre-Code Architecture Diagram (Specification-Derived)

```
═══════════════════════════════════════════════════════════════════════════════════
                    ORGAN 04 — KNOWLEDGE (SPECIFICATION TOPOLOGY)
═══════════════════════════════════════════════════════════════════════════════════

                              ┌────────────────────────┐
                              │  CNS Organ (02)        │
                              │  Routes IPC Requests   │
                              └───────────┬────────────┘
                                          │ Named Pipe / Unix Socket
                                          │ \\.\pipe\hojaiga_knowledge
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │            sockets/ipc_server.py             │
                    │  Length-Prefixed Binary Frame:               │
                    │  [4B length | 2B op_code | JSON payload]     │
                    │  Max payload 16MB. Async non-blocking loop.  │
                    └───────────────────────┬───────────────────────┘
                                            ▼
                    ┌─────────────────────────────────────────────┐
                    │           core/knowledge_kernel.py            │
                    │      (knowledge_core — Request Lifecycle)     │
                    │  Query Dispatcher → State Machine Guard       │
                    │  States: INITIALIZING→READY→INDEXING          │
                    │          →DEGRADED / MAINTENANCE              │
                    └───┬─────────┬─────────┬─────────┬────────────┘
                        │         │         │         │
          ┌─────────────┘         │         │         └───────────────┐
          ▼                       ▼         ▼                         ▼
┌───────────────────┐  ┌──────────────────┐ ┌────────────────────┐ ┌──────────────────┐
│ capability_registry│  │  app_intelligence │ │    doc_engine       │ │ hybrid_search_engine│
│ ------------------ │  │ ----------------  │ │ ------------------  │ │ ------------------ │
│ find_providers()   │  │ AppProfile CRUD   │ │ load_governing_doc()│ │ BM25 (FTS5)        │
│ register_alias()   │  │ health score       │ │ Markdown → AST      │ │ CPU Vector Cosine  │
│ Priority + Health   │  │ reliability update │ │ Chunk extraction    │ │ execute_hybrid_query│
│ ranking, LRU cache  │  │                    │ │                     │ │ (alpha blend)       │
└─────────┬──────────┘  └─────────┬──────────┘ └──────────┬──────────┘ └──────────┬─────────┘
          │                       │                        │                       │
          └───────────────────────┴────────────┬───────────┴───────────────────────┘
                                                ▼
                                   ┌──────────────────────────┐
                                   │   knowledge_merger         │
                                   │   (evolution/incremental_  │
                                   │    merger.py)              │
                                   │  Diff-based, append-only,  │
                                   │  no destructive overwrite  │
                                   └────────────┬───────────────┘
                                                ▼
                                   ┌──────────────────────────┐
                                   │     policy_verifier        │
                                   │  Validates plans against   │
                                   │  Constitution / Law Book / │
                                   │  Policy Manual rules       │
                                   └────────────┬───────────────┘
                                                ▼
                    ┌───────────────────────────────────────────────┐
                    │         storage/knowledge_db.sqlite             │
                    │  Tables: capabilities, app_profiles,             │
                    │  capability_providers, doc_chunks_fts (FTS5),    │
                    │  doc_chunks_vec (CPU float blob vectors)         │
                    │  PRAGMA mmap_size=268435456                      │
                    └───────────────────────────────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        ▼                                               ▼
              ┌────────────────────┐                         ┌───────────────────────┐
              │ data/system_docs/  │                         │ data/profiles/          │
              │ Constitution.md    │                         │ capabilities/           │
              │ LawBook.md         │                         │ workflows/               │
              │ PolicyManual.md    │                         │ (raw recovery source)    │
              │ Blueprint.md       │                         └───────────────────────┘
              └────────────────────┘

  EVENTS EMITTED (→ CNS Organ 02):
  EVENT_KNOWLEDGE_INDEXED · EVENT_CAPABILITY_RESOLVED
  EVENT_APP_PROFILE_UPDATED · EVENT_GOVERNING_DOC_LOADED
  EVENT_CAPABILITY_UNRESOLVED · EVENT_KNOWLEDGE_UPDATED

  INCOMING: Brain(01) capability/doc queries · CNS(02) routing ·
            Learning(08) health-score feedback · Agents(10) param/schema queries
  OUTGOING: CNS(02) events · Infrastructure(09) binary-path verification

  RECOVERY: DEGRADED → auto-rescan data/system_docs + data/profiles → rebuild index → READY
  CONCURRENCY: Multi-reader SQLite (shared lock) + single-threaded write worker queue.
  HARDWARE: CPU-only (AVX2/AVX-512 SIMD cosine), zero GPU, <512MB RAM, SSD-backed mmap.
═══════════════════════════════════════════════════════════════════════════════════
```

---

## 2. Implementation Reference

**File:** `organ_04_knowledge.py` — single-file, self-contained, importable module.

This document is the specification and diagram companion to `organ_04_knowledge.py`.
The full production Python source is delivered as a separate standalone file
(see accompanying download) so it can be directly imported:

```python
from organ_04_knowledge import KnowledgeOrgan
```

### 2.1 Module Responsibilities Implemented

- Capability Registry & Resolution
- Application Intelligence Management
- Governing Document Knowledge Base (doc_engine)
- Workflow & Command Knowledge storage
- Hybrid Search (SQLite FTS5 BM25 + CPU vector cosine similarity)
- Incremental Knowledge Evolution (append-only merge)
- Policy Verification
- Named Pipe / Unix Socket IPC server with length-prefixed binary framing
- State machine: INITIALIZING -> READY -> INDEXING -> DEGRADED -> MAINTENANCE

### 2.2 Dependencies

Python 3.11+, `sqlite3` (stdlib, must be built with FTS5), `jsonschema`,
`numpy` (CPU vector math). No GPU usage.

### 2.3 Public IPC Interface (op_codes)

| op_code | RPC                        | Handler                              |
|--------:|-----------------------------|---------------------------------------|
| 1       | `ResolveCapability`         | `KnowledgeKernel.resolve_capability`  |
| 2       | `QueryDocumentation`        | `KnowledgeKernel.query_documentation` |
| 3       | `GetAppProfile`             | `KnowledgeKernel.get_app_profile`     |
| 4       | `ReadPolicy`                | `KnowledgeKernel.read_policy`         |
| 5       | `SearchKnowledge`           | `KnowledgeKernel.search_knowledge`    |
| 6       | `UpdateAppHealthScore`      | `KnowledgeKernel.update_app_health_score` |
| 7       | `IngestKnowledge`           | `KnowledgeKernel.ingest_knowledge`    |

Wire protocol: `[4-byte length | 2-byte op_code | JSON payload]`, max 16 MB per request,
served on `\\.\pipe\hojaiga_knowledge` (Windows) / `/tmp/hojaiga_knowledge.sock` (POSIX).

---

## 3. Post-Implementation Diagram (Actual Code Topology)

```
═══════════════════════════════════════════════════════════════════════════════════
                ORGAN 04 — KNOWLEDGE (AS-BUILT organ_04_knowledge.py)
═══════════════════════════════════════════════════════════════════════════════════

KnowledgeOrgan (composition root / entrypoint)
   │
   ├── KnowledgeConfig.load() ─────────────► root_dir, db paths, pipe name, alpha, LRU size
   │
   ├── KnowledgeKernel(config)
   │      │
   │      ├── StateMachine  ── INITIALIZING → READY ⇄ INDEXING → DEGRADED → MAINTENANCE
   │      │
   │      ├── KnowledgeStorage.open()
   │      │      ├── sqlite3 connection (WAL, mmap_size=256MB)
   │      │      ├── tables: capabilities, app_profiles, capability_providers,
   │      │      │           doc_chunks_fts (FTS5 porter | LIKE fallback),
   │      │      │           doc_chunks_vec (float32 blob), knowledge_history
   │      │      └── async write_lock ⇒ single-writer guarantee
   │      │
   │      ├── DocEngine(config, storage)
   │      │      ├── DocParser (heading-regex → DocChunk[])
   │      │      ├── preload_all() → Constitution/LawBook/PolicyManual/Blueprint/OrganSpec
   │      │      └── _ast_cache (permanent RAM cache) → EVENT_GOVERNING_DOC_LOADED
   │      │
   │      ├── HybridSearchEngine(config, storage)
   │      │      ├── index_chunk() → FTS5 insert + naive_embed() → vec insert
   │      │      ├── _bm25_search() (FTS5 MATCH / LIKE fallback)
   │      │      ├── _vector_search() (numpy cosine similarity, CPU-only)
   │      │      └── execute_hybrid_query(alpha) → blended ranked results
   │      │
   │      ├── AppIntelligence(config, storage)
   │      │      ├── upsert_profile() → validate_payload(APP_PROFILE_SCHEMA)
   │      │      ├── get_profile() (id / name / alias lookup)
   │      │      └── update_health_score() → EVENT_APP_PROFILE_UPDATED
   │      │
   │      ├── CapabilityRegistry(config, storage)
   │      │      ├── LRUCache(256) — provider resolution cache
   │      │      ├── register_alias()
   │      │      └── find_providers() → filter installed+OS+reliability → sort → cache
   │      │
   │      ├── PolicyVerifier(doc_engine)
   │      │      ├── verify_action() → PROTECTED_RESOURCES gate (Law 12)
   │      │      └── read_policy(category) → policy_manual chunk filter
   │      │
   │      ├── IncrementalMerger(storage, hybrid_search)
   │      │      └── merge_documents() → append-only history + EVENT_KNOWLEDGE_UPDATED
   │      │
   │      └── recover() ── DEGRADED path: rescan data/system_docs + data/profiles
   │                       → re-merge chunks → EVENT_KNOWLEDGE_INDEXED → READY
   │
   ├── QueryDispatcher(kernel)
   │      op_code routing table:
   │        1 RESOLVE_CAPABILITY      → kernel.resolve_capability()
   │        2 QUERY_DOCUMENTATION     → kernel.query_documentation()
   │        3 GET_APP_PROFILE         → kernel.get_app_profile()
   │        4 READ_POLICY             → kernel.read_policy()
   │        5 SEARCH_KNOWLEDGE        → kernel.search_knowledge()
   │        6 UPDATE_APP_HEALTH_SCORE → kernel.update_app_health_score()
   │        7 INGEST_KNOWLEDGE        → kernel.ingest_knowledge()
   │      guard: only dispatches when state ∈ {READY, INDEXING}
   │
   └── IPCServer(kernel, dispatcher)
          ├── Windows: ProactorEventLoop named pipe (\\.\pipe\hojaiga_knowledge)
          │            via _PipeProtocolAdapter → StreamReader/Writer bridge
          │            (falls back to TCP 127.0.0.1:48891 if pipe API unavailable)
          ├── POSIX:   asyncio.start_unix_server(/tmp/hojaiga_knowledge.sock)
          ├── Frame:   [4B length | 2B op_code | JSON payload], ≤16MB
          └── _handle_client(): readexactly(6) → readexactly(length) → dispatch → write

EVENT EMISSIONS (EventEmitter — outward to CNS Organ 02):
   EVENT_KNOWLEDGE_INDEXED · EVENT_CAPABILITY_RESOLVED · EVENT_CAPABILITY_UNRESOLVED
   EVENT_APP_PROFILE_UPDATED · EVENT_GOVERNING_DOC_LOADED · EVENT_KNOWLEDGE_UPDATED

LOGGING: JsonLogFormatter → structured stdout JSON (Policy Manual Ch.8 compliant)

CALL SEQUENCE (Capability Resolution, matches Spec §40):
   IPC client → IPCServer._handle_client → QueryDispatcher.dispatch(op=1)
   → KnowledgeKernel.resolve_capability → validate_payload(schema)
   → CapabilityRegistry.find_providers (LRU check → SQL join → sort)
   → EVENTS.emit(CAPABILITY_RESOLVED | CAPABILITY_UNRESOLVED)
   → JSON response framed back to caller
═══════════════════════════════════════════════════════════════════════════════════
```
