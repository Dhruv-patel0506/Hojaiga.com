# Organ 16 — Audit System

**File:** `organ16_audit_system.py`
**System Layer:** Infrastructure & Accountability Core
**Version:** 1.0.0
**Status:** Implemented — Production Draft

**Authority Order:** Constitution → Law Book → Policy Manual → Master Architecture Blueprint → Organ Specification → `AUDIT_SYSTEM_SPECIFICATION.md`

---

## 1. Purpose

Organ 16 is the immutable accountability, compliance, and operational forensics layer of Hojaiga. It records every state change, decision, security event, and error across the platform as an append-only, hash-chained, tamper-evident log, and exposes query, retention, and integrity-verification capabilities to every other organ exclusively through its public socket.

---

## 2. Responsibilities

- Capture audit events from any organ (system, kernel, brain, controllers, plugins, connectors, users).
- Validate every record against the mandatory schema before acceptance.
- Persist records in a write-once-read-many (WORM), hash-chained store.
- Index records for fast category / actor / trace / severity lookup.
- Provide a query engine for search and reporting.
- Enforce category-based retention and move expired segments to cold archive without deleting or mutating originals.
- Verify chain integrity on demand and on recovery.
- Publish a live audit stream to subscribed organs.

---

## 3. Architecture — Pre-Code Diagram

```
[ EVENT PRODUCERS ]        [ INGESTION ]         [ VALIDATION / INTEGRITY ]
 Kernel/Controllers/  ---> AuditCollector  --->   AuditValidator
 Brain/Plugins/Users        (async queue)          (schema + policy rules)
                                 |                          |
                                 v                          v
                          AuditSocketRouter          IntegrityEngine
                                 |                    (SHA-256 chain)
                                 v                          |
                       [ IMMUTABLE STORAGE ] <--------------+
                        ImmutableAuditStore
                        - append-only JSONL segments
                        - hash-chained records (linear Merkle-style chain)
                                 |
                 -----------------------------------
                 |                                 |
                 v                                 v
        [ INDEX / SEARCH ]                [ LIFECYCLE MANAGEMENT ]
         AuditIndexer                       RetentionManager
         AuditQueryEngine                    ArchiveEngine
                 |
                 v
        [ REPORTING ]
         AuditReportGenerator (via AuditQueryEngine)
```

---

## 4. Architecture — Actual-Code Diagram

```
organ16_audit_system.py
│
├── AuditCategory (Enum)        — 31 operational domains (SYSTEM..USER)
├── AuditSeverity (Enum)        — DEBUG..SECURITY_ALERT
├── AuditRecordType (Enum)      — EVENT/DECISION/STATE_TRANSITION/ERROR/
│                                  SECURITY/COMPLIANCE/EXECUTION_HISTORY
├── ActorIdentity (dataclass)   — actor_type / actor_id / display_name
├── AuditRecord (dataclass)     — full immutable record schema
├── AuditValidationError
│
├── AuditValidator              — schema + policy enforcement
├── IntegrityEngine             — SHA-256 chain-hash primitives
├── ImmutableAuditStore         — append-only WORM segment writer/reader
├── AuditIndexer                — in-memory inverted index
├── AuditQueryEngine            — filterable search over the index
├── RetentionManager            — per-category retention + cold archive sweep
├── IntegrityVerifier           — full hash-chain re-verification
├── AuditSocketRouter           — in-process publish/subscribe socket
├── AuditCollector              — async queue: validate → store → index → publish
│
└── AuditSystem                 — public facade (the organ's only socket)
    ├── record() / record_async()
    ├── query() / trace()
    ├── verify_integrity()
    ├── sweep_retention()
    ├── subscribe()
    └── recover()
```

---

## 5. Public Socket Contract (v1)

Other organs interact with Organ 16 **only** through `AuditSystem`:

| Method | Direction | Description |
|---|---|---|
| `record(...)` | inbound | Synchronous audit record submission |
| `record_async(...)` | inbound | Awaitable submission for async organs |
| `query(AuditQuery)` | outbound | Search interface |
| `trace(trace_id)` | outbound | Retrieve all records for a correlation trace |
| `verify_integrity()` | outbound | Full hash-chain verification |
| `sweep_retention()` | internal/scheduled | Retention/archive cycle |
| `subscribe(handler)` | outbound | Live audit stream subscription |
| `recover()` | lifecycle | Rebuild index + verify chain on restart |

No organ may access `ImmutableAuditStore`, `AuditIndexer`, or any internal component directly — only via the `AuditSystem` facade, per Law Book Universal Law 3 (Separation of Responsibility) and Universal Law 7 (Least Privilege).

---

## 6. Audit Record Schema

| Field | Type | Notes |
|---|---|---|
| `record_id` | UUID string | Unique per record |
| `trace_id` | UUID string | Correlates a chain of related records |
| `parent_trace_id` | UUID string / null | Optional causal link |
| `timestamp_utc` | ISO-8601 string | UTC timestamp |
| `category` | `AuditCategory` | One of 31 domain classifications |
| `severity` | `AuditSeverity` | DEBUG..SECURITY_ALERT |
| `record_type` | `AuditRecordType` | EVENT/DECISION/STATE_TRANSITION/ERROR/SECURITY/COMPLIANCE/EXECUTION_HISTORY |
| `source_organ` | string | Emitting organ identifier |
| `actor` | `ActorIdentity` | USER / AGENT / SYSTEM / PLUGIN |
| `action` | string | Action verb/code |
| `summary` | string | Human-readable summary |
| `payload` | dict | Structured event detail |
| `outcome` | string | SUCCESS / FAILURE / PENDING / PARTIAL |
| `sequence_index` | int | Monotonic position in the chain |
| `hash` | string | SHA-256 of `previous_hash + canonical_json` |
| `previous_hash` | string | Prior record's hash (genesis = 64 zeros) |
| `storage_offset` | string | `segment_file:start:end` byte locator |

---

## 7. Sockets

- **Ingestion Socket** — `AuditCollector.submit()` / `submit_sync()`
- **Publish Socket** — `AuditSocketRouter.publish()` → all `subscribe()` handlers
- **Query Socket** — `AuditQueryEngine.search()`
- **Integrity Socket** — `IntegrityVerifier.verify_full_chain()`

## 8. Pipelines

1. **Ingestion Pipeline:** `AuditRecord.create()` → `AuditValidator.validate()` → `ImmutableAuditStore.append()` → `AuditIndexer.index()` → `AuditSocketRouter.publish()`
2. **Recovery Pipeline:** `ImmutableAuditStore.iter_all()` → `AuditIndexer.rebuild()` → `IntegrityVerifier.verify_full_chain()`
3. **Retention Pipeline:** `RetentionManager.sweep()` → per-segment expiry check → copy to archive directory (source never deleted)

---

## 9. Integrity Model

- Linear SHA-256 hash chain: `H_n = SHA256(H_{n-1} + canonical_json(record_n))`.
- Genesis hash is 64 zero characters.
- Canonical JSON excludes `hash`, `previous_hash`, `sequence_index`, and `storage_offset` from the signed payload to keep the chain deterministic and self-referential.
- `IntegrityVerifier.verify_full_chain()` recomputes every hash from segment 1 onward and reports the first broken record and its sequence index, if any.
- Storage is append-only JSONL, fsync'd per write; segments rotate at a configurable byte threshold.

---

## 10. Retention & Archival

- Default retention: SECURITY = 3650 days, ERROR = 1825 days, USER = 2555 days, BRAIN = 730 days, all other categories = 365 days (fallback).
- A segment is archived only when **every** record in it has exceeded its category's retention window.
- Archival copies the segment to the cold-archive directory; the original WORM segment is never deleted or mutated, preserving the audit trail.
- The active (currently-written) segment is always excluded from sweeps.

---

## 11. Failure Recovery

Per Law Book Universal Law 8 (Failure Transparency and Recovery):

- On restart, `AuditSystem.recover()` rebuilds the in-memory index from durable storage and re-verifies the full hash chain.
- Ingestion failures (validation errors, full queue) raise typed exceptions (`AuditValidationError`, `asyncio.QueueFull`) rather than silently dropping data, so callers can react per Foundational Law 8 (Exception Handling Policy: Detect → Pause → Analyze → Recover → Log).

---

## 12. Testing

File: `tests/test_organ16_audit_system.py` — 9 tests, all passing:

- Record submission and category query
- Hash-chain integrity across multiple records
- Tamper detection (bit-level mutation triggers `verify_integrity() == False` at the correct sequence)
- Schema validation rejection of malformed records
- Trace-ID correlation across multiple records
- Recovery rebuilds index and confirms chain validity after process restart
- Retention sweep archives an expired, non-active segment
- Async ingestion via `AuditCollector`
- Socket subscription delivers published records to handlers

Run with:
```bash
pytest tests/test_organ16_audit_system.py -q
```

---

## 13. Compliance Statement

This organ implements the AUDIT_SYSTEM_SPECIFICATION.md requirements for: Audit Event Capture, Execution History, Decision Records, User/Agent Identity, Trace IDs, Immutable/Append-Only Records, Security Events, Error Events, Compliance Records, Audit Queries, Retention, Integrity Verification, Sockets, Pipelines, Recovery, and Testing — implemented from scratch in Python, reusing only architectural paradigms (hash-chained WORM append logic) from the reference specification, never its C++ implementation or class hierarchy.
