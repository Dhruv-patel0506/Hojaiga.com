"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 16
Name: Audit System

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Audit System]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: enum, pathlib, __future__, typing, json...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_16_audit_system.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Audit System Organ
============================================================================
File: organ16_audit_system.py
Organ: Infrastructure & Accountability Core
Version: 1.0.0
Authority Order: Constitution -> Law Book -> Policy Manual ->
                  Master Architecture Blueprint -> Organ Specification ->
                  AUDIT_SYSTEM_SPECIFICATION.md

This module is a single, independently importable organ. It communicates
with every other organ exclusively through documented sockets and
pipelines (in-process pub/sub + queue based, replaceable by a real
transport without changing the public contract). It never depends on the
private implementation of another organ.

PRE-CODE ARCHITECTURE DIAGRAM
----------------------------------------------------------------------------
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
                        - hash-chained records (Merkle-style linear chain)
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
         AuditReportGenerator

ACTUAL-CODE DIAGRAM (this file)
----------------------------------------------------------------------------
AuditRecord (schema)
AuditCategory / AuditSeverity (enums)
IntegrityEngine        -> sha256 chaining primitives
ImmutableAuditStore     -> append-only WORM segment writer/reader
AuditIndexer            -> in-memory inverted index over stored records
AuditValidator          -> schema + policy enforcement
AuditCollector          -> async ingestion queue -> validate -> store -> index
AuditQueryEngine         -> search/filter over index + store
RetentionManager         -> TTL / archive sweep per category
IntegrityVerifier        -> full/partial chain re-verification
AuditSocketRouter        -> in-process pub/sub socket exposed to other organs
AuditPipeline             -> ordered stage pipeline (validate/store/index)
AuditSystem              -> public facade / single entry point (the socket)
============================================================================
"""


import asyncio
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

__all__ = [
    "AuditCategory",
    "AuditSeverity",
    "AuditRecord",
    "AuditValidationError",
    "IntegrityEngine",
    "ImmutableAuditStore",
    "AuditIndexer",
    "AuditValidator",
    "AuditCollector",
    "AuditQueryEngine",
    "RetentionManager",
    "IntegrityVerifier",
    "AuditSocketRouter",
    "AuditSystem",
]

GENESIS_HASH = "0" * 64


# ============================================================================
# 1. AUDIT CATEGORIES / SEVERITY
# ============================================================================

class AuditCategory(str, Enum):
    SYSTEM = "SYSTEM"
    KERNEL = "KERNEL"
    CONFIGURATION = "CONFIGURATION"
    RESOURCE = "RESOURCE"
    SCHEDULER = "SCHEDULER"
    SERVICE = "SERVICE"
    DEPENDENCY = "DEPENDENCY"
    CAPABILITY = "CAPABILITY"
    EVENT = "EVENT"
    STATE = "STATE"
    ERROR = "ERROR"
    SECURITY = "SECURITY"
    BRAIN = "BRAIN"
    CNS = "CNS"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    LEARNING = "LEARNING"
    AUTOMATION = "AUTOMATION"
    WORKFLOW = "WORKFLOW"
    TASK = "TASK"
    INTERFACE = "INTERFACE"
    LLM_RUNTIME = "LLM_RUNTIME"
    PLUGIN = "PLUGIN"
    CONNECTOR = "CONNECTOR"
    WINDOWS = "WINDOWS"
    PLAYWRIGHT = "PLAYWRIGHT"
    API = "API"
    DATABASE = "DATABASE"
    BACKUP = "BACKUP"
    RECOVERY = "RECOVERY"
    UPDATE = "UPDATE"
    USER = "USER"


class AuditSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    SECURITY_ALERT = "SECURITY_ALERT"


class AuditRecordType(str, Enum):
    EVENT = "EVENT"
    DECISION = "DECISION"
    STATE_TRANSITION = "STATE_TRANSITION"
    ERROR = "ERROR"
    SECURITY = "SECURITY"
    COMPLIANCE = "COMPLIANCE"
    EXECUTION_HISTORY = "EXECUTION_HISTORY"


# ============================================================================
# 2. AUDIT RECORD SCHEMA
# ============================================================================

@dataclass(frozen=True)
class ActorIdentity:
    actor_type: str  # "USER" | "AGENT" | "SYSTEM" | "PLUGIN"
    actor_id: str
    display_name: str = ""


@dataclass(frozen=True)
class AuditRecord:
    record_id: str
    trace_id: str
    parent_trace_id: Optional[str]
    timestamp_utc: str
    category: AuditCategory
    severity: AuditSeverity
    record_type: AuditRecordType
    source_organ: str
    actor: ActorIdentity
    action: str
    summary: str
    payload: Dict[str, Any]
    outcome: str  # "SUCCESS" | "FAILURE" | "PENDING" | "PARTIAL"
    sequence_index: int = 0
    hash: str = ""
    previous_hash: str = ""
    storage_offset: str = ""

    @staticmethod
    def create(
        category: AuditCategory,
        severity: AuditSeverity,
        record_type: AuditRecordType,
        source_organ: str,
        actor: ActorIdentity,
        action: str,
        summary: str,
        outcome: str = "SUCCESS",
        payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
    ) -> "AuditRecord":
        return AuditRecord(
            record_id=str(uuid.uuid4()),
            trace_id=trace_id or str(uuid.uuid4()),
            parent_trace_id=parent_trace_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            category=category,
            severity=severity,
            record_type=record_type,
            source_organ=source_organ,
            actor=actor,
            action=action,
            summary=summary,
            payload=payload or {},
            outcome=outcome,
        )

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Deterministic, field-sorted representation used for hashing."""
        d = asdict(self)
        d.pop("hash", None)
        d.pop("storage_offset", None)
        d.pop("previous_hash", None)
        d.pop("sequence_index", None)
        return json.loads(json.dumps(d, sort_keys=True, default=str))

    def to_canonical_json(self) -> str:
        return json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":"))

    def to_stored_dict(self) -> Dict[str, Any]:
        d = self.to_canonical_dict()
        d["hash"] = self.hash
        d["previous_hash"] = self.previous_hash
        d["sequence_index"] = self.sequence_index
        d["storage_offset"] = self.storage_offset
        return d

    @staticmethod
    def from_stored_dict(d: Dict[str, Any]) -> "AuditRecord":
        actor = ActorIdentity(**d["actor"])
        return AuditRecord(
            record_id=d["record_id"],
            trace_id=d["trace_id"],
            parent_trace_id=d.get("parent_trace_id"),
            timestamp_utc=d["timestamp_utc"],
            category=AuditCategory(d["category"]),
            severity=AuditSeverity(d["severity"]),
            record_type=AuditRecordType(d["record_type"]),
            source_organ=d["source_organ"],
            actor=actor,
            action=d["action"],
            summary=d["summary"],
            payload=d.get("payload", {}),
            outcome=d.get("outcome", "SUCCESS"),
            sequence_index=d.get("sequence_index", 0),
            hash=d.get("hash", ""),
            previous_hash=d.get("previous_hash", ""),
            storage_offset=d.get("storage_offset", ""),
        )


class AuditValidationError(Exception):
    pass


# ============================================================================
# 3. VALIDATOR
# ============================================================================

class AuditValidator:
    """Enforces schema completeness and policy rules before ingestion."""

    REQUIRED_STRING_FIELDS = (
        "record_id", "trace_id", "timestamp_utc", "action", "summary", "source_organ",
    )

    def validate(self, record: AuditRecord) -> None:
        for f in self.REQUIRED_STRING_FIELDS:
            value = getattr(record, f)
            if not isinstance(value, str) or not value.strip():
                raise AuditValidationError(f"Field '{f}' must be a non-empty string.")

        try:
            uuid.UUID(record.record_id)
            uuid.UUID(record.trace_id)
        except ValueError as exc:
            raise AuditValidationError(f"Invalid UUID format: {exc}") from exc

        if not isinstance(record.category, AuditCategory):
            raise AuditValidationError("Invalid audit category.")
        if not isinstance(record.severity, AuditSeverity):
            raise AuditValidationError("Invalid audit severity.")
        if not isinstance(record.record_type, AuditRecordType):
            raise AuditValidationError("Invalid audit record type.")
        if record.outcome not in ("SUCCESS", "FAILURE", "PENDING", "PARTIAL"):
            raise AuditValidationError("Invalid outcome value.")
        if not isinstance(record.actor, ActorIdentity):
            raise AuditValidationError("Invalid actor identity.")
        if record.actor.actor_type not in ("USER", "AGENT", "SYSTEM", "PLUGIN"):
            raise AuditValidationError("Invalid actor type.")

        try:
            datetime.fromisoformat(record.timestamp_utc)
        except ValueError as exc:
            raise AuditValidationError(f"Invalid timestamp: {exc}") from exc


# ============================================================================
# 4. INTEGRITY ENGINE
# ============================================================================

class IntegrityEngine:
    """Cryptographic hash-chain primitives (SHA-256 linear hash chain)."""

    @staticmethod
    def sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def chain_hash(cls, previous_hash: str, canonical_json: str) -> str:
        return cls.sha256(previous_hash + canonical_json)


# ============================================================================
# 5. IMMUTABLE AUDIT STORE (Append-Only WORM Store)
# ============================================================================

class ImmutableAuditStore:
    """
    Append-only, hash-chained JSONL storage engine.

    Guarantees:
      - Records are only ever appended, never rewritten or deleted.
      - Every record's hash covers the previous record's hash plus its own
        canonical payload, forming a tamper-evident linear chain.
      - Segment rotation keeps individual files bounded in size.
    """

    def __init__(self, storage_dir: str, segment_max_bytes: int = 64 * 1024 * 1024):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._segment_max_bytes = segment_max_bytes
        self._lock = threading.RLock()
        self._last_hash, self._sequence_index, self._active_segment = self._recover_state()

    # -- segment management --------------------------------------------

    def _segment_files(self) -> List[Path]:
        return sorted(self._dir.glob("segment_*.jsonl"))

    def _recover_state(self) -> "tuple[str, int, Path]":
        segments = self._segment_files()
        if not segments:
            return GENESIS_HASH, 0, self._dir / "segment_000001.jsonl"

        last_segment = segments[-1]
        last_hash = GENESIS_HASH
        seq = 0
        with open(last_segment, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                last_hash = record["hash"]
                seq = record["sequence_index"]
        return last_hash, seq, last_segment

    def _rotate_if_needed(self) -> None:
        if self._active_segment.exists() and self._active_segment.stat().st_size >= self._segment_max_bytes:
            index = int(self._active_segment.stem.split("_")[1]) + 1
            self._active_segment = self._dir / f"segment_{index:06d}.jsonl"

    # -- public API -------------------------------------------------------

    def append(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            self._rotate_if_needed()
            canonical_json = record.to_canonical_json()
            new_hash = IntegrityEngine.chain_hash(self._last_hash, canonical_json)
            sequence_index = self._sequence_index + 1

            stored_record = replace(
                record,
                hash=new_hash,
                previous_hash=self._last_hash,
                sequence_index=sequence_index,
            )

            with open(self._active_segment, "a", encoding="utf-8") as fh:
                start_offset = fh.tell()
                line = json.dumps(stored_record.to_stored_dict(), sort_keys=True)
                fh.write(line + "\n")
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
                end_offset = fh.tell()

            stored_record = replace(
                stored_record,
                storage_offset=f"{self._active_segment.name}:{start_offset}:{end_offset}"
            )

            self._last_hash = new_hash
            self._sequence_index = sequence_index
            return stored_record

    def iter_all(self):
        for segment in self._segment_files():
            with open(segment, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    yield AuditRecord.from_stored_dict(json.loads(line))

    @property
    def last_hash(self) -> str:
        return self._last_hash

    @property
    def sequence_index(self) -> int:
        return self._sequence_index


def asdict_no_enum_fix(record: AuditRecord) -> Dict[str, Any]:
    """Rebuild constructor kwargs for AuditRecord preserving enum/actor types."""
    return dict(
        record_id=record.record_id,
        trace_id=record.trace_id,
        parent_trace_id=record.parent_trace_id,
        timestamp_utc=record.timestamp_utc,
        category=record.category,
        severity=record.severity,
        record_type=record.record_type,
        source_organ=record.source_organ,
        actor=record.actor,
        action=record.action,
        summary=record.summary,
        payload=record.payload,
        outcome=record.outcome,
        sequence_index=record.sequence_index,
        hash=record.hash,
        previous_hash=record.previous_hash,
        storage_offset=record.storage_offset,
    )


# ============================================================================
# 6. INDEXER
# ============================================================================

class AuditIndexer:
    """In-memory inverted index for fast filtering; rebuildable from store."""

    def __init__(self):
        self._lock = threading.RLock()
        self._by_category: Dict[AuditCategory, List[str]] = {}
        self._by_trace: Dict[str, List[str]] = {}
        self._by_actor: Dict[str, List[str]] = {}
        self._by_severity: Dict[AuditSeverity, List[str]] = {}
        self._records: Dict[str, AuditRecord] = {}

    def index(self, record: AuditRecord) -> None:
        with self._lock:
            self._records[record.record_id] = record
            self._by_category.setdefault(record.category, []).append(record.record_id)
            self._by_trace.setdefault(record.trace_id, []).append(record.record_id)
            self._by_actor.setdefault(record.actor.actor_id, []).append(record.record_id)
            self._by_severity.setdefault(record.severity, []).append(record.record_id)

    def rebuild(self, records: Sequence[AuditRecord]) -> None:
        with self._lock:
            self._by_category.clear()
            self._by_trace.clear()
            self._by_actor.clear()
            self._by_severity.clear()
            self._records.clear()
        for r in records:
            self.index(r)

    def get(self, record_id: str) -> Optional[AuditRecord]:
        return self._records.get(record_id)

    def by_category(self, category: AuditCategory) -> List[AuditRecord]:
        return [self._records[i] for i in self._by_category.get(category, [])]

    def by_trace(self, trace_id: str) -> List[AuditRecord]:
        return [self._records[i] for i in self._by_trace.get(trace_id, [])]

    def by_actor(self, actor_id: str) -> List[AuditRecord]:
        return [self._records[i] for i in self._by_actor.get(actor_id, [])]

    def by_severity(self, severity: AuditSeverity) -> List[AuditRecord]:
        return [self._records[i] for i in self._by_severity.get(severity, [])]

    def all_records(self) -> List[AuditRecord]:
        return list(self._records.values())


# ============================================================================
# 7. QUERY ENGINE
# ============================================================================

@dataclass
class AuditQuery:
    category: Optional[AuditCategory] = None
    severity: Optional[AuditSeverity] = None
    trace_id: Optional[str] = None
    actor_id: Optional[str] = None
    source_organ: Optional[str] = None
    outcome: Optional[str] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    text: Optional[str] = None
    limit: int = 100


class AuditQueryEngine:
    def __init__(self, indexer: AuditIndexer):
        self._indexer = indexer

    def search(self, query: AuditQuery) -> List[AuditRecord]:
        candidates = self._indexer.all_records()

        if query.category is not None:
            candidates = [r for r in candidates if r.category == query.category]
        if query.severity is not None:
            candidates = [r for r in candidates if r.severity == query.severity]
        if query.trace_id is not None:
            candidates = [r for r in candidates if r.trace_id == query.trace_id]
        if query.actor_id is not None:
            candidates = [r for r in candidates if r.actor.actor_id == query.actor_id]
        if query.source_organ is not None:
            candidates = [r for r in candidates if r.source_organ == query.source_organ]
        if query.outcome is not None:
            candidates = [r for r in candidates if r.outcome == query.outcome]
        if query.time_from is not None:
            candidates = [r for r in candidates if r.timestamp_utc >= query.time_from]
        if query.time_to is not None:
            candidates = [r for r in candidates if r.timestamp_utc <= query.time_to]
        if query.text:
            needle = query.text.lower()
            candidates = [
                r for r in candidates
                if needle in r.summary.lower() or needle in r.action.lower()
            ]

        candidates.sort(key=lambda r: r.sequence_index)
        return candidates[: query.limit]


# ============================================================================
# 8. RETENTION MANAGER
# ============================================================================

class RetentionManager:
    """
    Enforces per-category retention windows. The store itself is append-only
    and immutable; retention here governs *archival* of segments to cold
    storage, never in-place mutation or deletion of individual records.
    """

    DEFAULT_RETENTION_DAYS: Dict[AuditCategory, int] = {
        AuditCategory.SECURITY: 3650,
        AuditCategory.ERROR: 1825,
        AuditCategory.USER: 2555,
        AuditCategory.BRAIN: 730,
    }
    FALLBACK_RETENTION_DAYS = 365

    def __init__(self, store: ImmutableAuditStore, archive_dir: str):
        self._store = store
        self._archive_dir = Path(archive_dir)
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    def retention_for(self, category: AuditCategory) -> int:
        return self.DEFAULT_RETENTION_DAYS.get(category, self.FALLBACK_RETENTION_DAYS)

    def sweep(self, now: Optional[datetime] = None) -> List[str]:
        """Move fully-expired, closed segments to the cold archive directory.
        A segment is eligible only when EVERY record inside it has exceeded
        its category retention window; source files are copied (never
        deleted) to preserve WORM guarantees."""
        now = now or datetime.now(timezone.utc)
        archived: List[str] = []
        for segment in self._store._segment_files():  # controlled internal access
            if segment == self._store._active_segment:
                continue
            expired = True
            with open(segment, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    ts = datetime.fromisoformat(d["timestamp_utc"])
                    retention_days = self.retention_for(AuditCategory(d["category"]))
                    age_days = (now - ts).days
                    if age_days < retention_days:
                        expired = False
                        break
            if expired:
                target = self._archive_dir / segment.name
                if not target.exists():
                    target.write_bytes(segment.read_bytes())
                    archived.append(segment.name)
        return archived


# ============================================================================
# 9. INTEGRITY VERIFIER
# ============================================================================

@dataclass
class IntegrityReport:
    verified_records: int
    valid: bool
    first_broken_record_id: Optional[str]
    broken_at_sequence: Optional[int]


class IntegrityVerifier:
    def __init__(self, store: ImmutableAuditStore):
        self._store = store

    def verify_full_chain(self) -> IntegrityReport:
        previous_hash = GENESIS_HASH
        count = 0
        for record in self._store.iter_all():
            expected = IntegrityEngine.chain_hash(previous_hash, record.to_canonical_json())
            if expected != record.hash or record.previous_hash != previous_hash:
                return IntegrityReport(
                    verified_records=count,
                    valid=False,
                    first_broken_record_id=record.record_id,
                    broken_at_sequence=record.sequence_index,
                )
            previous_hash = record.hash
            count += 1
        return IntegrityReport(
            verified_records=count, valid=True,
            first_broken_record_id=None, broken_at_sequence=None,
        )


# ============================================================================
# 10. AUDIT SOCKET ROUTER (Sockets & Pipelines)
# ============================================================================

class AuditSocketRouter:
    """
    In-process publish/subscribe socket. Other organs call `emit()` on the
    exposed AuditSystem socket; internal stages subscribe via `subscribe()`.
    This is the organ's only inbound/outbound communication surface.
    """

    def __init__(self):
        self._subscribers: List[Callable[[AuditRecord], None]] = []
        self._lock = threading.RLock()

    def subscribe(self, handler: Callable[[AuditRecord], None]) -> None:
        with self._lock:
            self._subscribers.append(handler)

    def publish(self, record: AuditRecord) -> None:
        with self._lock:
            handlers = list(self._subscribers)
        for handler in handlers:
            handler(record)


# ============================================================================
# 11. AUDIT COLLECTOR (Async Ingestion Pipeline)
# ============================================================================

class AuditCollector:
    """
    Async, non-blocking ingestion queue. Producers call `submit()` (sync or
    async) which enqueues events; a background worker drains the queue
    through the validate -> store -> index -> publish pipeline.
    """

    def __init__(
        self,
        validator: AuditValidator,
        store: ImmutableAuditStore,
        indexer: AuditIndexer,
        router: AuditSocketRouter,
        queue_max_size: int = 10000,
    ):
        self._validator = validator
        self._store = store
        self._indexer = indexer
        self._router = router
        self._queue: "asyncio.Queue[AuditRecord]" = asyncio.Queue(maxsize=queue_max_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._dropped = 0
        self._sync_lock = threading.RLock()

    async def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker_task is not None:
            await self._queue.join()
            self._worker_task.cancel()
            self._worker_task = None

    async def submit(self, record: AuditRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self._dropped += 1
            raise

    def submit_sync(self, record: AuditRecord) -> AuditRecord:
        """Synchronous ingestion path used when no event loop is present
        (e.g. called from plain synchronous organ code)."""
        with self._sync_lock:
            return self._process(record)

    async def _run(self) -> None:
        while True:
            record = await self._queue.get()
            try:
                self._process(record)
            finally:
                self._queue.task_done()

    def _process(self, record: AuditRecord) -> AuditRecord:
        self._validator.validate(record)
        stored = self._store.append(record)
        self._indexer.index(stored)
        self._router.publish(stored)
        return stored

    @property
    def dropped_count(self) -> int:
        return self._dropped


# ============================================================================
# 12. AUDIT SYSTEM FACADE (Public Socket Contract)
# ============================================================================

class AuditSystem:
    """
    Public entry point for the Audit organ. Every other organ interacts
    with the Audit System exclusively through this facade.

    Public contract (versioned v1):
      - record(...)              -> synchronous audit record submission
      - record_async(...)        -> awaitable submission for async organs
      - query(AuditQuery)        -> search interface
      - verify_integrity()       -> full hash-chain verification
      - sweep_retention()        -> retention/archive cycle
      - subscribe(handler)       -> live audit stream subscription
    """

    VERSION = "1.0.0"

    def __init__(self, storage_dir: Optional[str] = None, archive_dir: Optional[str] = None):
        storage_dir = storage_dir or os.path.join(os.getcwd(), "var", "hojaiga", "audit")
        archive_dir = archive_dir or str(Path(storage_dir) / "_archive")
        self.store = ImmutableAuditStore(storage_dir)
        self.indexer = AuditIndexer()
        self.indexer.rebuild(list(self.store.iter_all()))
        self.validator = AuditValidator()
        self.router = AuditSocketRouter()
        self.collector = AuditCollector(self.validator, self.store, self.indexer, self.router)
        self.query_engine = AuditQueryEngine(self.indexer)
        self.retention_manager = RetentionManager(self.store, archive_dir)
        self.integrity_verifier = IntegrityVerifier(self.store)

    # -- ingestion --------------------------------------------------------

    def record(
        self,
        category: AuditCategory,
        severity: AuditSeverity,
        record_type: AuditRecordType,
        source_organ: str,
        actor: ActorIdentity,
        action: str,
        summary: str,
        outcome: str = "SUCCESS",
        payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
    ) -> AuditRecord:
        record = AuditRecord.create(
            category=category, severity=severity, record_type=record_type,
            source_organ=source_organ, actor=actor, action=action, summary=summary,
            outcome=outcome, payload=payload, trace_id=trace_id, parent_trace_id=parent_trace_id,
        )
        return self.collector.submit_sync(record)

    async def record_async(
        self,
        category: AuditCategory,
        severity: AuditSeverity,
        record_type: AuditRecordType,
        source_organ: str,
        actor: ActorIdentity,
        action: str,
        summary: str,
        outcome: str = "SUCCESS",
        payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
    ) -> None:
        record = AuditRecord.create(
            category=category, severity=severity, record_type=record_type,
            source_organ=source_organ, actor=actor, action=action, summary=summary,
            outcome=outcome, payload=payload, trace_id=trace_id, parent_trace_id=parent_trace_id,
        )
        await self.collector.submit(record)

    # -- query / lifecycle / integrity ------------------------------------

    def query(self, query: AuditQuery) -> List[AuditRecord]:
        return self.query_engine.search(query)

    def trace(self, trace_id: str) -> List[AuditRecord]:
        return self.indexer.by_trace(trace_id)

    def verify_integrity(self) -> IntegrityReport:
        return self.integrity_verifier.verify_full_chain()

    def sweep_retention(self) -> List[str]:
        return self.retention_manager.sweep()

    def subscribe(self, handler: Callable[[AuditRecord], None]) -> None:
        self.router.subscribe(handler)

    # -- recovery -----------------------------------------------------------

    def recover(self) -> IntegrityReport:
        """Rebuild the in-memory index from durable storage and re-verify
        chain integrity. Used on organ restart per Universal Law 8
        (Failure Transparency and Recovery)."""
        self.indexer.rebuild(list(self.store.iter_all()))
        return self.verify_integrity()
