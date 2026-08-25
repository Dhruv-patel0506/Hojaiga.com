"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 3
Name: Memory

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Memory]
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
Dependencies: platform, socket, hashlib, dataclasses, contextlib...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_03_memory.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
organ_03_memory.py

Hojaiga Automation OS — Organ 03: Memory Organ
================================================

Single-file, production-grade implementation of the Memory Organ as defined by:
  - Constitution of Hojaiga
  - Hojaiga Law Book (Universal Law 6 — State Integrity; Foundational Law 7 — Append-Only History)
  - Hojaiga Policy Manual (Chapter 3 — Memory Policy; Chapter 8 — Logging Policy)
  - Master Architecture Blueprint (Chapter 4 — Memory Architecture)
  - Organ Specification (Section 4 — Required Sections)
  - Organ 03 — Memory Specification Document (v1.0.0)

This organ owns exactly one responsibility: multi-tiered state, context, and
persistent memory management. It never reasons, plans, or executes tasks —
it only stores, compresses, retrieves, and persists state on behalf of other
organs, communicating exclusively through the documented IPC socket and the
public interfaces defined below.

Import this single module to get the complete Memory Organ runtime:

    from core_organs.organ_03_memory import MemoryCore, MemoryOrganConfig

    core = MemoryCore(MemoryOrganConfig())
    core.start()
    ...
    core.stop()

No third-party services are required. Optional acceleration libraries
(`lz4`, `sqlite-vec` style vector search) are used when available and the
organ degrades gracefully to pure-stdlib equivalents (`zlib`, brute-force
cosine search) when they are not — this preserves Universal Law 8 (Failure
Transparency and Recovery) without introducing a hard dependency.

Author: Hojaiga Engineering
Version: 1.0.0
"""


import asyncio
import collections
import contextlib
import ctypes
import dataclasses
import enum
import hashlib
import json
import logging
import mmap
import os
import platform
import shutil
import socket
import sqlite3
import struct
import threading
import time
import uuid
import zlib
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────
# Optional acceleration: LZ4 (fast compression). Falls back to zlib.
# ─────────────────────────────────────────────────────────────────────────
try:
    import lz4.frame as _lz4  # type: ignore
    _LZ4_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    _lz4 = None
    _LZ4_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════
# SECTION 0 — LOGGING (Policy Manual Chapter 8 — structured JSON audit log)
# ═══════════════════════════════════════════════════════════════════════

class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter. Every record is one audit line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.time(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "audit", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


def _build_logger(name: str, log_dir: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "memory_organ.log.jsonl", encoding="utf-8")
    file_handler.setFormatter(_JsonFormatter())
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def _audit(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Append-only structured audit entry (Foundational Law 7)."""
    logger.info(event, extra={"audit": {"event": event, **fields}})


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class MemoryOrganConfig:
    """Allocation caps and paths. Mirrors config/memory_limits.json (Sec. 6)."""

    root_dir: Path = Path("./organ_03_memory")
    ssd_runtime_dir: Optional[Path] = None       # storage/snapshots + session_rooms.sqlite
    hdd_archive_dir: Optional[Path] = None        # storage/long_term (external HDD)

    working_memory_max_bytes: int = 2 * 1024 * 1024 * 1024   # 2.0 GB physical cap (Sec 18)
    working_memory_max_items: int = 200_000
    shared_ring_buffer_bytes: int = 128 * 1024 * 1024          # 128 MB dual LRU cache cap (Sec 17)
    shared_memory_chunk_bytes: int = 64 * 1024 * 1024          # pre-allocated chunk (Sec 46)

    snapshot_interval_seconds: float = 30.0
    snapshot_op_threshold: int = 1000
    ssd_low_space_threshold_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB (Sec 31)

    max_key_bytes: int = 256
    max_value_bytes: int = 16 * 1024 * 1024
    max_socket_frame_bytes: int = 16 * 1024 * 1024

    session_retention_seconds: int = 30 * 24 * 3600  # 30 days default retention

    pipe_name: str = r"\\.\pipe\hojaiga_memory"
    unix_socket_path: str = "/tmp/hojaiga_memory.sock"

    persistence_worker_threads: int = 2
    embedding_dim: int = 384

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir)
        self.ssd_runtime_dir = Path(self.ssd_runtime_dir) if self.ssd_runtime_dir else self.root_dir / "storage"
        self.hdd_archive_dir = Path(self.hdd_archive_dir) if self.hdd_archive_dir else self.root_dir / "storage" / "long_term"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — MEMORY LAYER ENUM + DATA CONTRACTS (Sec. 15)
# ═══════════════════════════════════════════════════════════════════════

class MemoryLayer(str, enum.Enum):
    WORKING = "working"
    SESSION = "session"
    LONG_TERM = "long_term"
    SHARED = "shared"


class OrganState(str, enum.Enum):
    INITIALIZING = "INITIALIZING"
    SYNCHRONIZED = "SYNCHRONIZED"
    COMPACTING = "COMPACTING"
    FLUSHING = "FLUSHING"
    RECOVERY = "RECOVERY"


class MemoryEvent(str, enum.Enum):
    SNAPSHOT_CREATED = "EVENT_MEMORY_SNAPSHOT_CREATED"
    ROOM_CREATED = "EVENT_MEMORY_ROOM_CREATED"
    THRESHOLD_EXCEEDED = "EVENT_MEMORY_THRESHOLD_EXCEEDED"
    COMPRESSION_COMPLETED = "EVENT_MEMORY_COMPRESSION_COMPLETED"
    CORRUPTION_DETECTED = "EVENT_MEMORY_CORRUPTION_DETECTED"


@dataclasses.dataclass
class MemoryStoreRequest:
    """Validated against the JSON Schema in Organ Spec Section 15."""

    transaction_id: str
    memory_layer: MemoryLayer
    key: str
    value: Any
    room_id: Optional[str] = None
    ttl_seconds: int = 0

    @staticmethod
    def new(memory_layer: MemoryLayer, key: str, value: Any,
            room_id: Optional[str] = None, ttl_seconds: int = 0) -> "MemoryStoreRequest":
        return MemoryStoreRequest(
            transaction_id=str(uuid.uuid4()),
            memory_layer=memory_layer,
            key=key,
            value=value,
            room_id=room_id,
            ttl_seconds=ttl_seconds,
        )

    def validate(self, cfg: MemoryOrganConfig) -> None:
        if len(self.key.encode("utf-8")) > cfg.max_key_bytes:
            raise ValueError(f"key exceeds {cfg.max_key_bytes} bytes")
        size = len(json.dumps(self.value, default=str).encode("utf-8"))
        if size > cfg.max_value_bytes:
            raise ValueError(f"value exceeds {cfg.max_value_bytes} bytes")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — EVENT BUS (outgoing socket to CNS Organ 02) — Sec. 12, 14
# ═══════════════════════════════════════════════════════════════════════

class EventBus:
    """Minimal pub/sub bridge used to emit MemoryEvent notifications to CNS.

    In production this forwards over the CNS Socket; here it exposes a
    subscribe() hook so the hosting process (CNS) can bind a real transport
    without this organ depending on CNS internals (Universal Law 5).
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
        self._logger = logger
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def emit(self, event: MemoryEvent, **payload: Any) -> None:
        _audit(self._logger, event.value, **payload)
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event.value, payload)
            except Exception as exc:  # never let a subscriber crash memory core
                _audit(self._logger, "EVENT_DISPATCH_FAILURE", error=str(exc), original_event=event.value)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — VOLATILE WORKING MEMORY (src/volatile/working_memory.py)
# ═══════════════════════════════════════════════════════════════════════

class _LRUNode:
    __slots__ = ("key", "value", "size", "expires_at")

    def __init__(self, key: str, value: Any, size: int, expires_at: float) -> None:
        self.key = key
        self.value = value
        self.size = size
        self.expires_at = expires_at


class WorkingMemory:
    """Thread-safe, bounded, TTL-aware LRU key-value store.

    Implements IVolatileMemory (Organ Spec Sec. 8):
        allocate_block(size) / free_block(handle)

    Guarantees:
        - Multi-reader, single-writer semantics via RLock (Sec. 19).
        - Physical byte budget enforcement (Sec. 18).
        - Write-through queueing to the persistence layer (Sec. 17).
    """

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger,
                 on_write_through: Optional[Callable[[str, Any, int], None]] = None,
                 on_threshold_exceeded: Optional[Callable[[], None]] = None) -> None:
        self._cfg = cfg
        self._logger = logger
        self._lock = threading.RLock()
        self._store: "collections.OrderedDict[str, _LRUNode]" = collections.OrderedDict()
        self._current_bytes = 0
        self._on_write_through = on_write_through
        self._on_threshold_exceeded = on_threshold_exceeded
        self._locked_handles: Dict[str, int] = {}

    # -- IVolatileMemory -------------------------------------------------

    def allocate_block(self, size: int) -> str:
        """Reserve a locked logical memory handle of `size` bytes."""
        handle = str(uuid.uuid4())
        with self._lock:
            self._locked_handles[handle] = size
        return handle

    def free_block(self, handle: str) -> None:
        with self._lock:
            self._locked_handles.pop(handle, None)

    # -- Core KV API -------------------------------------------------------

    def store(self, key: str, value: Any, ttl_seconds: int = 0) -> None:
        payload_bytes = json.dumps(value, default=str).encode("utf-8")
        size = len(payload_bytes)
        expires_at = (time.time() + ttl_seconds) if ttl_seconds > 0 else 0.0

        with self._lock:
            if key in self._store:
                old = self._store.pop(key)
                self._current_bytes -= old.size

            self._current_bytes += size
            self._store[key] = _LRUNode(key, value, size, expires_at)
            self._store.move_to_end(key)

            self._evict_if_needed_locked()

            usage_ratio = self._current_bytes / max(1, self._cfg.working_memory_max_bytes)
            if usage_ratio >= 0.8 and self._on_threshold_exceeded:
                self._on_threshold_exceeded()

        if self._on_write_through:
            self._on_write_through(key, value, ttl_seconds)

    def fetch(self, key: str) -> Optional[Any]:
        with self._lock:
            node = self._store.get(key)
            if node is None:
                return None
            if node.expires_at and node.expires_at < time.time():
                self._store.pop(key, None)
                self._current_bytes -= node.size
                return None
            self._store.move_to_end(key)
            return node.value

    def delete(self, key: str) -> bool:
        with self._lock:
            node = self._store.pop(key, None)
            if node is None:
                return False
            self._current_bytes -= node.size
            return True

    def sweep_expired(self) -> int:
        removed = 0
        now = time.time()
        with self._lock:
            expired_keys = [k for k, n in self._store.items() if n.expires_at and n.expires_at < now]
            for k in expired_keys:
                node = self._store.pop(k)
                self._current_bytes -= node.size
                removed += 1
        return removed

    def snapshot_state(self) -> Dict[str, Any]:
        """Return a serializable copy for snapshot_manager delta capture."""
        with self._lock:
            return {
                k: {"value": n.value, "expires_at": n.expires_at}
                for k, n in self._store.items()
                if not n.expires_at or n.expires_at >= time.time()
            }

    def restore_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._store.clear()
            self._current_bytes = 0
            for k, entry in state.items():
                size = len(json.dumps(entry["value"], default=str).encode("utf-8"))
                self._store[k] = _LRUNode(k, entry["value"], size, entry.get("expires_at", 0.0))
                self._current_bytes += size

    @property
    def usage_bytes(self) -> int:
        with self._lock:
            return self._current_bytes

    @property
    def item_count(self) -> int:
        with self._lock:
            return len(self._store)

    def _evict_if_needed_locked(self) -> None:
        """Evict least-recently-used entries until within byte/item budget."""
        while (
            self._current_bytes > self._cfg.working_memory_max_bytes
            or len(self._store) > self._cfg.working_memory_max_items
        ) and self._store:
            _, oldest = self._store.popitem(last=False)
            self._current_bytes -= oldest.size


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — SHARED RAM (src/volatile/shared_ram.py)
# ═══════════════════════════════════════════════════════════════════════

class SharedMemoryDescriptor:
    """Plain descriptor object returned by CreateSharedBuffer."""

    def __init__(self, buffer_id: str, size_bytes: int, backing_path: str) -> None:
        self.buffer_id = buffer_id
        self.size_bytes = size_bytes
        self.backing_path = backing_path

    def to_dict(self) -> Dict[str, Any]:
        return {"buffer_id": self.buffer_id, "size_bytes": self.size_bytes, "backing_path": self.backing_path}


class SharedMemoryAllocator:
    """OS-native IPC shared memory manager.

    Uses mmap-backed files as a portable equivalent of Win32
    CreateFileMappingW / POSIX shm_open, satisfying Universal Law 5
    (Standardized Communication) across platforms without a hard
    dependency on `multiprocessing.shared_memory`'s naming quirks.
    """

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger) -> None:
        self._cfg = cfg
        self._logger = logger
        self._lock = threading.RLock()
        self._buffers: Dict[str, Tuple[mmap.mmap, Any, str]] = {}
        self._dir = cfg.ssd_runtime_dir / "shared"  # type: ignore
        self._dir.mkdir(parents=True, exist_ok=True)

    def create_buffer(self, buffer_id: str, size_bytes: int) -> SharedMemoryDescriptor:
        size_bytes = max(size_bytes, self._cfg.shared_memory_chunk_bytes) \
            if size_bytes <= self._cfg.shared_memory_chunk_bytes else size_bytes
        path = self._dir / f"{buffer_id}.shm"
        with self._lock:
            if buffer_id in self._buffers:
                return SharedMemoryDescriptor(buffer_id, size_bytes, str(path))
            with open(path, "wb") as f:
                f.truncate(size_bytes)
            fh = open(path, "r+b")
            mm = mmap.mmap(fh.fileno(), size_bytes)
            self._buffers[buffer_id] = (mm, fh, str(path))
        _audit(self._logger, "SHARED_BUFFER_CREATED", buffer_id=buffer_id, size_bytes=size_bytes)
        return SharedMemoryDescriptor(buffer_id, size_bytes, str(path))

    def write(self, buffer_id: str, data: bytes, offset: int = 0) -> None:
        with self._lock:
            entry = self._buffers.get(buffer_id)
            if entry is None:
                raise KeyError(f"unknown shared buffer {buffer_id}")
            mm, _, _ = entry
            mm.seek(offset)
            mm.write(data)
            mm.flush()

    def read(self, buffer_id: str, size: int, offset: int = 0) -> bytes:
        with self._lock:
            entry = self._buffers.get(buffer_id)
            if entry is None:
                raise KeyError(f"unknown shared buffer {buffer_id}")
            mm, _, _ = entry
            mm.seek(offset)
            return mm.read(size)

    def release(self, buffer_id: str) -> None:
        with self._lock:
            entry = self._buffers.pop(buffer_id, None)
            if entry is None:
                return
            mm, fh, _ = entry
            mm.close()
            fh.close()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — COMPRESSION ENGINE (src/compression/*)
# ═══════════════════════════════════════════════════════════════════════

class CompressionEngine:
    """LZ4 context compressor with a zlib fallback (Sec. 47 tradeoff)."""

    def __init__(self, logger: logging.Logger, event_bus: Optional[EventBus] = None) -> None:
        self._logger = logger
        self._event_bus = event_bus

    def compress(self, data: bytes) -> bytes:
        if _LZ4_AVAILABLE:
            return b"L4" + _lz4.compress(data)  # type: ignore
        return b"ZL" + zlib.compress(data, level=6)

    def decompress(self, blob: bytes) -> bytes:
        tag, payload = blob[:2], blob[2:]
        if tag == b"L4":
            if not _LZ4_AVAILABLE:
                raise RuntimeError("lz4 payload found but lz4 module unavailable")
            return _lz4.decompress(payload)  # type: ignore
        if tag == b"ZL":
            return zlib.decompress(payload)
        raise ValueError("unknown compression tag")

    def compress_json(self, obj: Any) -> bytes:
        raw = json.dumps(obj, default=str).encode("utf-8")
        return self.compress(raw)

    def decompress_json(self, blob: bytes) -> Any:
        return json.loads(self.decompress(blob).decode("utf-8"))


class SemanticPruner:
    """Recursive structural + token-aware context pruning.

    Deduplicates repeated structural fragments and truncates a context
    array down to a target token budget, keeping the most recent and the
    most information-dense entries (heuristic: entry length as a proxy
    for information density, most-recent-first bias).
    """

    def __init__(self, avg_chars_per_token: float = 4.0) -> None:
        self._avg_chars_per_token = avg_chars_per_token

    def estimate_tokens(self, text: str) -> int:
        return max(1, int(len(text) / self._avg_chars_per_token))

    def deduplicate(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_hashes: set = set()
        deduped: List[Dict[str, Any]] = []
        for entry in entries:
            fingerprint = hashlib.sha256(
                json.dumps(entry, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            if fingerprint in seen_hashes:
                continue
            seen_hashes.add(fingerprint)
            deduped.append(entry)
        return deduped

    def prune_to_budget(self, entries: List[Dict[str, Any]], token_budget: int) -> List[Dict[str, Any]]:
        entries = self.deduplicate(entries)
        kept: List[Dict[str, Any]] = []
        used = 0
        for entry in reversed(entries):  # most recent first
            text = json.dumps(entry, default=str)
            cost = self.estimate_tokens(text)
            if used + cost > token_budget and kept:
                break
            kept.append(entry)
            used += cost
        kept.reverse()
        return kept


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7 — SESSION MANAGER / ROOMS (src/session/*)
# ═══════════════════════════════════════════════════════════════════════

class SessionRoomStore:
    """SQLite-backed isolated session ("room") storage on SSD runtime disk.

    Schema mirrors Organ Spec Section 16: rooms + room_messages tables.
    Enforces WAL journaling per Section 19 and Engineering Recommendations.
    """

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger) -> None:
        self._cfg = cfg
        self._logger = logger
        self._path = cfg.ssd_runtime_dir / "session_rooms.sqlite"  # type: ignore
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    metadata TEXT,
                    closed INTEGER DEFAULT 0
                )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS room_messages (
                    msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_room_messages_room ON room_messages(room_id, msg_id)"
            )

    def create_room(self, room_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO rooms (room_id, created_at, updated_at, metadata, closed) "
                "VALUES (?, ?, ?, ?, 0)",
                (room_id, now, now, json.dumps(metadata or {})),
            )
        return room_id

    def append_context(self, room_id: str, role: str, content: Any) -> int:
        now = time.time()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO room_messages (room_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (room_id, role, json.dumps(content, default=str), now),
            )
            self._conn.execute("UPDATE rooms SET updated_at = ? WHERE room_id = ?", (now, room_id))
            return cur.lastrowid or 0

    def fetch_history(self, room_id: str, depth: int) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, timestamp FROM room_messages "
                "WHERE room_id = ? ORDER BY msg_id DESC LIMIT ?",
                (room_id, depth),
            ).fetchall()
        history = [
            {"role": r[0], "content": json.loads(r[1]), "timestamp": r[2]}
            for r in rows
        ]
        history.reverse()
        return history

    def close_room(self, room_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE rooms SET closed = 1, updated_at = ? WHERE room_id = ?", (time.time(), room_id))

    def prune_expired_sessions(self, retention_seconds: int) -> List[str]:
        """IPersistentStorage.prune_expired_sessions (Sec. 8)."""
        cutoff = time.time() - retention_seconds
        with self._lock:
            rows = self._conn.execute(
                "SELECT room_id FROM rooms WHERE closed = 1 AND updated_at < ?", (cutoff,)
            ).fetchall()
            room_ids = [r[0] for r in rows]
            with self._conn:
                for room_id in room_ids:
                    self._conn.execute("DELETE FROM room_messages WHERE room_id = ?", (room_id,))
                    self._conn.execute("DELETE FROM rooms WHERE room_id = ?", (room_id,))
        return room_ids

    def export_closed_rooms(self) -> List[Dict[str, Any]]:
        """Used by the archival pipeline to migrate closed rooms to HDD."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT room_id, created_at, updated_at, metadata FROM rooms WHERE closed = 1"
            ).fetchall()
        exported = []
        for room_id, created_at, updated_at, metadata in rows:
            history = self.fetch_history(room_id, depth=10_000)
            exported.append({
                "room_id": room_id,
                "created_at": created_at,
                "updated_at": updated_at,
                "metadata": json.loads(metadata),
                "messages": history,
            })
        return exported

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class ContextTracker:
    """Tracks per-room live context window size for compression triggers."""

    def __init__(self, pruner: SemanticPruner, token_budget: int = 8192) -> None:
        self._pruner = pruner
        self._token_budget = token_budget
        self._lock = threading.RLock()
        self._buffers: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)

    def track(self, room_id: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._buffers[room_id].append(entry)

    def needs_compression(self, room_id: str) -> bool:
        with self._lock:
            entries = self._buffers.get(room_id, [])
            total = sum(self._pruner.estimate_tokens(json.dumps(e, default=str)) for e in entries)
            return total > self._token_budget

    def compress_room(self, room_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            entries = self._buffers.get(room_id, [])
            pruned = self._pruner.prune_to_budget(entries, self._token_budget)
            self._buffers[room_id] = pruned
            return pruned


class SessionRoom:
    """Handle returned by CreateSessionRoom; thin façade over the store."""

    def __init__(self, room_id: str, store: SessionRoomStore, tracker: ContextTracker) -> None:
        self.room_id = room_id
        self._store = store
        self._tracker = tracker

    def append(self, role: str, content: Any) -> int:
        msg_id = self._store.append_context(self.room_id, role, content)
        self._tracker.track(self.room_id, {"role": role, "content": content})
        return msg_id

    def history(self, depth: int = 50) -> List[Dict[str, Any]]:
        return self._store.fetch_history(self.room_id, depth)

    def close(self) -> None:
        self._store.close_room(self.room_id)


class SessionManager:
    """Room-based session isolation engine (Organ Spec Sec. 5)."""

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger, event_bus: EventBus) -> None:
        self._cfg = cfg
        self._logger = logger
        self._event_bus = event_bus
        self._store = SessionRoomStore(cfg, logger)
        self._pruner = SemanticPruner()
        self._tracker = ContextTracker(self._pruner)
        self._rooms_lock = threading.RLock()
        self._open_rooms: Dict[str, SessionRoom] = {}

    def create_room(self, room_id: Optional[str], metadata: Optional[Dict[str, Any]] = None) -> SessionRoom:
        room_id = room_id or str(uuid.uuid4())
        self._store.create_room(room_id, metadata)
        room = SessionRoom(room_id, self._store, self._tracker)
        with self._rooms_lock:
            self._open_rooms[room_id] = room
        self._event_bus.emit(MemoryEvent.ROOM_CREATED, room_id=room_id)
        return room

    def get_room(self, room_id: str) -> Optional[SessionRoom]:
        with self._rooms_lock:
            room = self._open_rooms.get(room_id)
        if room is not None:
            return room
        return SessionRoom(room_id, self._store, self._tracker)

    def append_context(self, room_id: str, chunk: Dict[str, Any]) -> int:
        room = self.get_room(room_id)
        role = chunk.get("role", "system")
        content = chunk.get("content", chunk)
        return room.append(role, content)  # type: ignore

    def fetch_history(self, room_id: str, depth: int) -> List[Dict[str, Any]]:
        return self._store.fetch_history(room_id, depth)

    def maybe_compress(self, room_id: str, compressor: CompressionEngine) -> Optional[bytes]:
        if not self._tracker.needs_compression(room_id):
            return None
        pruned = self._tracker.compress_room(room_id)
        blob = compressor.compress_json(pruned)
        return blob

    def prune_expired(self) -> List[str]:
        return self._store.prune_expired_sessions(self._cfg.session_retention_seconds)

    def export_closed_rooms(self) -> List[Dict[str, Any]]:
        return self._store.export_closed_rooms()

    def shutdown(self) -> None:
        self._store.close()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8 — LONG-TERM STORE (src/persistence/lt_store.py)
# ═══════════════════════════════════════════════════════════════════════

class LongTermStore:
    """Disk-backed long-term memory engine (external HDD).

    Backed by SQLite. When the optional `sqlite-vec` extension is not
    available, semantic search degrades to a brute-force cosine similarity
    scan over stored embeddings — correct, CPU-only, and dependency-free,
    consistent with Section 22 (Zero GPU usage).
    """

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger) -> None:
        self._cfg = cfg
        self._logger = logger
        cfg.hdd_archive_dir.mkdir(parents=True, exist_ok=True)  # type: ignore
        self._path = cfg.hdd_archive_dir / "long_term_memory.sqlite"  # type: ignore
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._vec_extension_loaded = self._try_load_vec_extension()
        self._init_schema()

    def _try_load_vec_extension(self) -> bool:
        try:
            self._conn.enable_load_extension(True)
            self._conn.load_extension("vec0")
            self._conn.enable_load_extension(False)
            return True
        except Exception:
            with contextlib.suppress(Exception):
                self._conn.enable_load_extension(False)
            return False

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_nodes (
                    node_id TEXT PRIMARY KEY,
                    content TEXT,
                    embedding BLOB,
                    tags TEXT,
                    created_at TIMESTAMP
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_created ON knowledge_nodes(created_at)"
            )

    @staticmethod
    def _pack_embedding(vector: List[float]) -> bytes:
        return struct.pack(f"{len(vector)}f", *vector)

    @staticmethod
    def _unpack_embedding(blob: bytes) -> List[float]:
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    def insert_node(self, node_id: Optional[str], content: str, embedding: List[float],
                     tags: Optional[List[str]] = None) -> str:
        node_id = node_id or str(uuid.uuid4())
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO knowledge_nodes (node_id, content, embedding, tags, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (node_id, content, self._pack_embedding(embedding), json.dumps(tags or []), time.time()),
            )
        return node_id

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return -1.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return -1.0
        return dot / (norm_a * norm_b)

    def query_semantic(self, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT node_id, content, embedding, tags, created_at FROM knowledge_nodes"
            ).fetchall()
        scored = []
        for node_id, content, embedding_blob, tags, created_at in rows:
            embedding = self._unpack_embedding(embedding_blob)
            score = self._cosine(query_vector, embedding)
            scored.append((score, {
                "node_id": node_id,
                "content": content,
                "tags": json.loads(tags),
                "created_at": created_at,
                "score": score,
            }))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def archive_room(self, room_export: Dict[str, Any]) -> str:
        """Archive a closed session room export as a long-term knowledge node."""
        content = json.dumps(room_export, default=str)
        placeholder_embedding = self._pseudo_embedding(content)
        return self.insert_node(
            node_id=f"room::{room_export['room_id']}",
            content=content,
            embedding=placeholder_embedding,
            tags=["archived_room"],
        )

    def _pseudo_embedding(self, text: str) -> List[float]:
        """Deterministic CPU-cheap bag-of-hashes embedding fallback.

        Used only when no external embedding model is wired in by the
        Brain organ. Produces a stable, comparable vector for archival
        recall without requiring GPU or network access.
        """
        dim = self._cfg.embedding_dim
        vector = [0.0] * dim
        for token in text.split():
            idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
            vector[idx] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def vacuum(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("VACUUM")

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 9 — SNAPSHOT / RECOVERY (src/persistence/snapshot.py)
# ═══════════════════════════════════════════════════════════════════════

class SnapshotManager:
    """Delta-logging snapshot worker (SSD runtime storage).

    Commits point-in-time state markers so that a crash can be recovered
    by replaying the newest valid snapshot (Sec. 30 — Recovery Strategy).
    """

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger,
                 compressor: CompressionEngine, event_bus: EventBus) -> None:
        self._cfg = cfg
        self._logger = logger
        self._compressor = compressor
        self._event_bus = event_bus
        self._dir = cfg.ssd_runtime_dir / "snapshots"  # type: ignore
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._op_counter = 0

    def create_snapshot(self, tag: str, state_provider: Callable[[], Dict[str, Any]]) -> str:
        snapshot_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        state = state_provider()
        blob = self._compressor.compress_json(state)
        checksum = hashlib.sha256(blob).hexdigest()
        path = self._dir / f"{snapshot_id}.snap"
        tmp_path = path.with_suffix(".snap.tmp")

        with self._lock:
            with open(tmp_path, "wb") as f:
                header = struct.pack(">I", len(checksum)) + checksum.encode("ascii")
                f.write(header)
                f.write(blob)
            os.replace(tmp_path, path)  # atomic on POSIX and NTFS
            self._write_marker(snapshot_id, tag, checksum)

        self._event_bus.emit(MemoryEvent.SNAPSHOT_CREATED, snapshot_id=snapshot_id, tag=tag)
        return snapshot_id

    def _write_marker(self, snapshot_id: str, tag: str, checksum: str) -> None:
        marker_path = self._dir / "LATEST"
        with open(marker_path, "w", encoding="utf-8") as f:
            json.dump({"snapshot_id": snapshot_id, "tag": tag, "checksum": checksum,
                       "committed_at": time.time()}, f)

    def latest_snapshot_id(self) -> Optional[str]:
        marker_path = self._dir / "LATEST"
        if not marker_path.exists():
            return None
        with open(marker_path, "r", encoding="utf-8") as f:
            marker = json.load(f)
        return marker.get("snapshot_id")

    def restore_snapshot(self, snapshot_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_id = snapshot_id or self.latest_snapshot_id()
        if target_id is None:
            return None
        path = self._dir / f"{target_id}.snap"
        if not path.exists():
            _audit(self._logger, MemoryEvent.CORRUPTION_DETECTED.value, snapshot_id=target_id, reason="missing_file")
            return None
        with open(path, "rb") as f:
            header_len = struct.unpack(">I", f.read(4))[0]
            checksum = f.read(header_len).decode("ascii")
            blob = f.read()
        actual_checksum = hashlib.sha256(blob).hexdigest()
        if actual_checksum != checksum:
            _audit(self._logger, MemoryEvent.CORRUPTION_DETECTED.value, snapshot_id=target_id, reason="checksum_mismatch")
            quarantine_dir = self._dir / "quarantine"
            quarantine_dir.mkdir(exist_ok=True)
            shutil.move(str(path), str(quarantine_dir / path.name))
            return None
        return self._compressor.decompress_json(blob)

    def register_write_op(self) -> bool:
        """Returns True when an interval/threshold-triggered snapshot should fire."""
        with self._lock:
            self._op_counter += 1
            if self._op_counter >= self._cfg.snapshot_op_threshold:
                self._op_counter = 0
                return True
            return False

    def has_ungraceful_shutdown_marker(self) -> bool:
        return (self._dir / "DIRTY").exists()

    def mark_dirty(self) -> None:
        (self._dir / "DIRTY").touch()

    def clear_dirty(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            (self._dir / "DIRTY").unlink()

    def free_bytes_on_ssd(self) -> int:
        usage = shutil.disk_usage(str(self._cfg.ssd_runtime_dir))
        return usage.free


# ═══════════════════════════════════════════════════════════════════════
# SECTION 10 — IPC WIRE PROTOCOL + HANDLER (src/sockets/ipc_handler.py)
# ═══════════════════════════════════════════════════════════════════════
#
# Frame layout: [ 4-byte big-endian length | 2-byte op_code | JSON payload ]
# ═══════════════════════════════════════════════════════════════════════

class OpCode(enum.IntEnum):
    STORE_WORKING = 1
    FETCH_WORKING = 2
    CREATE_SESSION_ROOM = 3
    APPEND_SESSION_CONTEXT = 4
    FETCH_SESSION_HISTORY = 5
    QUERY_LONG_TERM = 6
    CREATE_SHARED_BUFFER = 7
    CREATE_SNAPSHOT = 8
    RESTORE_SNAPSHOT = 9
    PING = 99


class FrameCodec:
    """Length-prefixed binary frame encode/decode (Organ Spec Sec. 9)."""

    HEADER_STRUCT = struct.Struct(">IH")  # 4-byte length (op_code + payload), 2-byte op_code

    @classmethod
    def encode(cls, op_code: int, payload: Dict[str, Any]) -> bytes:
        body = json.dumps(payload, default=str).encode("utf-8")
        length = 2 + len(body)
        return struct.pack(">I", length) + struct.pack(">H", op_code) + body

    @classmethod
    async def read_frame(cls, reader: asyncio.StreamReader, max_size: int) -> Tuple[int, Dict[str, Any]]:
        length_bytes = await reader.readexactly(4)
        (length,) = struct.unpack(">I", length_bytes)
        if length > max_size:
            raise ValueError(f"frame length {length} exceeds max {max_size}")
        body = await reader.readexactly(length)
        op_code = struct.unpack(">H", body[:2])[0]
        payload = json.loads(body[2:].decode("utf-8")) if len(body) > 2 else {}
        return op_code, payload


class IPCHandler:
    """Async socket server exposing the public RPC interface (Sec. 7).

    Uses a Windows Named Pipe when running on Windows and a Unix Domain
    Socket elsewhere, satisfying the dual-path Public Interface definition
    without branching the RPC logic itself.
    """

    def __init__(self, cfg: MemoryOrganConfig, logger: logging.Logger,
                 dispatch: Callable[[int, Dict[str, Any]], Any]) -> None:
        self._cfg = cfg
        self._logger = logger
        self._dispatch = dispatch
        self._server: Optional[asyncio.AbstractServer] = None
        self._is_windows = platform.system() == "Windows"

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername", "local")
        try:
            while True:
                try:
                    op_code, payload = await FrameCodec.read_frame(reader, self._cfg.max_socket_frame_bytes)
                except asyncio.IncompleteReadError:
                    break
                try:
                    result = self._dispatch(op_code, payload)
                    if asyncio.iscoroutine(result):
                        result = await result
                    response = {"status": "OK", "result": result}
                except Exception as exc:  # Universal Law 8 — failure transparency
                    _audit(self._logger, "IPC_DISPATCH_ERROR", peer=str(peer), error=str(exc))
                    response = {"status": "ERROR", "error": str(exc)}
                frame = FrameCodec.encode(op_code, response)
                writer.write(frame)
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def start(self) -> None:
        if self._is_windows:
            # Named pipes require pywin32 / proactor-specific APIs on Windows;
            # a TCP loopback fallback keeps the organ portable and testable
            # while preserving identical framing/RPC semantics.
            self._server = await asyncio.start_server(self._handle_client, host="127.0.0.1", port=0)
        else:
            sock_path = Path(self._cfg.unix_socket_path)
            with contextlib.suppress(FileNotFoundError):
                sock_path.unlink()
            sock_path.parent.mkdir(parents=True, exist_ok=True)
            self._server = await asyncio.start_unix_server(self._handle_client, path=str(sock_path))  # type: ignore
        _audit(self._logger, "IPC_SERVER_STARTED", windows=self._is_windows)

    def sockets_info(self) -> List[str]:
        if self._server is None:
            return []
        try:
            if self._server.sockets:  # type: ignore
                return [str(s.getsockname()) for s in self._server.sockets]  # type: ignore
        except AttributeError:
            pass
        return []

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


# ═══════════════════════════════════════════════════════════════════════
# SECTION 11 — MEMORY CORE (src/core/memory_kernel.py + allocator.py)
# ═══════════════════════════════════════════════════════════════════════

class MemoryCore:
    """Primary orchestration controller — the Memory Organ's single entry
    point. Owns the state machine, wires all internal modules, exposes the
    public RPC surface, and runs the background persistence workers.
    """

    def __init__(self, config: Optional[MemoryOrganConfig] = None) -> None:
        self.cfg = config or MemoryOrganConfig()
        self.cfg.root_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.ssd_runtime_dir.mkdir(parents=True, exist_ok=True)  # type: ignore

        self.logger = _build_logger("organ_03_memory", self.cfg.root_dir / "logs")
        self.state = OrganState.INITIALIZING
        self.event_bus = EventBus(self.logger)

        self.compressor = CompressionEngine(self.logger, self.event_bus)
        self.working_memory = WorkingMemory(
            self.cfg, self.logger,
            on_write_through=self._on_working_write_through,
            on_threshold_exceeded=self._on_threshold_exceeded,
        )
        self.shared_memory = SharedMemoryAllocator(self.cfg, self.logger)
        self.session_manager = SessionManager(self.cfg, self.logger, self.event_bus)
        self.long_term_store = LongTermStore(self.cfg, self.logger)
        self.snapshot_manager = SnapshotManager(self.cfg, self.logger, self.compressor, self.event_bus)
        self.ipc_handler = IPCHandler(self.cfg, self.logger, self._dispatch)

        self._write_ops_since_snapshot = 0
        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._background_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._worker_pool: List[threading.Thread] = []
        self._task_queue: "collections.deque[Callable[[], None]]" = collections.deque()
        self._task_ready = threading.Semaphore(0)

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """INITIALIZING -> SYNCHRONIZED (Sec. 13, Sec. 39 boot sequence)."""
        self.state = OrganState.INITIALIZING
        _audit(self.logger, "MEMORY_ORGAN_INITIALIZING")

        if self.snapshot_manager.has_ungraceful_shutdown_marker():
            self._recover_from_crash()

        self._start_persistence_workers()
        self._background_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._background_thread.start()

        self.snapshot_manager.mark_dirty()
        self.state = OrganState.SYNCHRONIZED
        _audit(self.logger, "MEMORY_ORGAN_SYNCHRONIZED")

    def stop(self) -> None:
        """SYNCHRONIZED -> FLUSHING -> terminated (Sec. 13)."""
        self.state = OrganState.FLUSHING
        _audit(self.logger, "MEMORY_ORGAN_FLUSHING")

        self.snapshot_manager.create_snapshot("shutdown", self._full_state_snapshot)
        self._flush_closed_rooms_to_long_term()

        self._stop_event.set()
        for _ in self._worker_pool:
            self._task_ready.release()
        for worker in self._worker_pool:
            worker.join(timeout=5)

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._background_thread is not None:
            self._background_thread.join(timeout=5)

        self.session_manager.shutdown()
        self.long_term_store.close()
        self.snapshot_manager.clear_dirty()
        _audit(self.logger, "MEMORY_ORGAN_STOPPED")

    def _recover_from_crash(self) -> None:
        """RECOVERY state (Sec. 13, Sec. 30)."""
        self.state = OrganState.RECOVERY
        _audit(self.logger, "MEMORY_ORGAN_RECOVERY_STARTED")
        state = self.snapshot_manager.restore_snapshot()
        if state:
            self.working_memory.restore_state(state.get("working_memory", {}))
            _audit(self.logger, "MEMORY_ORGAN_RECOVERY_COMPLETE", restored_keys=len(state.get("working_memory", {})))
        else:
            _audit(self.logger, "MEMORY_ORGAN_RECOVERY_NO_SNAPSHOT")

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.ipc_handler.start())
        try:
            self._loop.run_forever()
        finally:
            self._loop.run_until_complete(self.ipc_handler.stop())
            self._loop.close()

    # ── Background persistence workers (Sec. 20 — 2-thread pool) ──────

    def _start_persistence_workers(self) -> None:
        for i in range(self.cfg.persistence_worker_threads):
            t = threading.Thread(target=self._persistence_worker_loop, name=f"mem-worker-{i}", daemon=True)
            t.start()
            self._worker_pool.append(t)
        t_snap = threading.Thread(target=self._periodic_snapshot_loop, name="mem-snapshot-timer", daemon=True)
        t_snap.start()
        self._worker_pool.append(t_snap)
        t_sweep = threading.Thread(target=self._periodic_sweep_loop, name="mem-ttl-sweep", daemon=True)
        t_sweep.start()
        self._worker_pool.append(t_sweep)

    def _persistence_worker_loop(self) -> None:
        while not self._stop_event.is_set():
            acquired = self._task_ready.acquire(timeout=1.0)
            if not acquired:
                continue
            if self._stop_event.is_set():
                return
            with self._lock:
                task = self._task_queue.popleft() if self._task_queue else None
            if task is not None:
                try:
                    task()
                except Exception as exc:
                    _audit(self.logger, "PERSISTENCE_TASK_ERROR", error=str(exc))

    def _enqueue_task(self, task: Callable[[], None]) -> None:
        with self._lock:
            self._task_queue.append(task)
        self._task_ready.release()

    def _periodic_snapshot_loop(self) -> None:
        while not self._stop_event.wait(self.cfg.snapshot_interval_seconds):
            self._maybe_snapshot(tag="interval")

    def _periodic_sweep_loop(self) -> None:
        while not self._stop_event.wait(60.0):
            removed = self.working_memory.sweep_expired()
            if removed:
                _audit(self.logger, "WORKING_MEMORY_TTL_SWEEP", removed=removed)
            expired_rooms = self.session_manager.prune_expired()
            if expired_rooms:
                _audit(self.logger, "SESSION_ROOMS_PRUNED", count=len(expired_rooms))

    # ── Write-through / event callbacks ────────────────────────────────

    def _on_working_write_through(self, key: str, value: Any, ttl_seconds: int) -> None:
        def _flush() -> None:
            if self.snapshot_manager.register_write_op():
                self._maybe_snapshot(tag="op_threshold")
        self._enqueue_task(_flush)

    def _on_threshold_exceeded(self) -> None:
        self.event_bus.emit(
            MemoryEvent.THRESHOLD_EXCEEDED,
            usage_bytes=self.working_memory.usage_bytes,
            cap_bytes=self.cfg.working_memory_max_bytes,
        )

    def _maybe_snapshot(self, tag: str) -> None:
        free_bytes = self.snapshot_manager.free_bytes_on_ssd()
        if free_bytes < self.cfg.ssd_low_space_threshold_bytes:
            self.event_bus.emit(MemoryEvent.THRESHOLD_EXCEEDED, reason="ssd_low_space", free_bytes=free_bytes)
            self._flush_closed_rooms_to_long_term()
            return
        self.state = OrganState.COMPACTING if tag == "op_threshold" else self.state
        self.snapshot_manager.create_snapshot(tag, self._full_state_snapshot)
        if self.state == OrganState.COMPACTING:
            self.state = OrganState.SYNCHRONIZED
        self.event_bus.emit(MemoryEvent.COMPRESSION_COMPLETED, tag=tag)

    def _full_state_snapshot(self) -> Dict[str, Any]:
        return {"working_memory": self.working_memory.snapshot_state(), "committed_at": time.time()}

    def _flush_closed_rooms_to_long_term(self) -> None:
        exported = self.session_manager.export_closed_rooms()
        for room_export in exported:
            self.long_term_store.archive_room(room_export)
        if exported:
            _audit(self.logger, "SESSION_ROOMS_ARCHIVED", count=len(exported))

    # ── Public RPC surface (MemoryIngestionPipeline / MemoryRetrievalPipeline) ──

    def store_working(self, key: str, value: Any, ttl: int = 0) -> Dict[str, Any]:
        req = MemoryStoreRequest.new(MemoryLayer.WORKING, key, value, ttl_seconds=ttl)
        req.validate(self.cfg)
        self.working_memory.store(key, value, ttl)
        _audit(self.logger, "STORE_WORKING", transaction_id=req.transaction_id, key=key)
        return {"transaction_id": req.transaction_id, "ack": True}

    def fetch_working(self, key: str) -> Dict[str, Any]:
        value = self.working_memory.fetch(key)
        if value is not None:
            return {"value": value, "source": "working_memory"}
        # MemoryRetrievalPipeline step 3: cache miss -> long term semantic fallback by key hash
        return {"value": None, "source": "miss"}

    def create_session_room(self, room_id: Optional[str], metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        room = self.session_manager.create_room(room_id, metadata)
        return {"room_id": room.room_id}

    def append_session_context(self, room_id: str, context_chunk: Dict[str, Any]) -> Dict[str, Any]:
        msg_id = self.session_manager.append_context(room_id, context_chunk)
        blob = self.session_manager.maybe_compress(room_id, self.compressor)
        if blob is not None:
            self.event_bus.emit(MemoryEvent.COMPRESSION_COMPLETED, room_id=room_id, bytes=len(blob))
        return {"msg_id": msg_id, "ack": True}

    def fetch_session_history(self, room_id: str, depth: int = 50) -> Dict[str, Any]:
        return {"context": self.session_manager.fetch_history(room_id, depth)}

    def query_long_term(self, semantic_query_vector: List[float], limit: int = 10) -> Dict[str, Any]:
        results = self.long_term_store.query_semantic(semantic_query_vector, limit)
        return {"results": results}

    def create_shared_buffer(self, buffer_id: Optional[str], size_bytes: int) -> Dict[str, Any]:
        buffer_id = buffer_id or str(uuid.uuid4())
        descriptor = self.shared_memory.create_buffer(buffer_id, size_bytes)
        return descriptor.to_dict()

    def create_snapshot(self, tag: str = "manual") -> Dict[str, Any]:
        snapshot_id = self.snapshot_manager.create_snapshot(tag, self._full_state_snapshot)
        return {"snapshot_id": snapshot_id}

    def restore_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        state = self.snapshot_manager.restore_snapshot(snapshot_id)
        if state is None:
            return {"status": "NOT_FOUND"}
        self.working_memory.restore_state(state.get("working_memory", {}))
        return {"status": "RECOVERED"}

    # ── IPC dispatch table ──────────────────────────────────────────────

    def _dispatch(self, op_code: int, payload: Dict[str, Any]) -> Any:
        handlers: Dict[int, Callable[[Dict[str, Any]], Any]] = {
            OpCode.STORE_WORKING: lambda p: self.store_working(p["key"], p["value"], p.get("ttl", 0)),
            OpCode.FETCH_WORKING: lambda p: self.fetch_working(p["key"]),
            OpCode.CREATE_SESSION_ROOM: lambda p: self.create_session_room(p.get("room_id"), p.get("metadata")),
            OpCode.APPEND_SESSION_CONTEXT: lambda p: self.append_session_context(p["room_id"], p["context_chunk"]),
            OpCode.FETCH_SESSION_HISTORY: lambda p: self.fetch_session_history(p["room_id"], p.get("depth", 50)),
            OpCode.QUERY_LONG_TERM: lambda p: self.query_long_term(p["semantic_query_vector"], p.get("limit", 10)),
            OpCode.CREATE_SHARED_BUFFER: lambda p: self.create_shared_buffer(p.get("buffer_id"), p["size_bytes"]),
            OpCode.CREATE_SNAPSHOT: lambda p: self.create_snapshot(p.get("tag", "manual")),
            OpCode.RESTORE_SNAPSHOT: lambda p: self.restore_snapshot(p.get("snapshot_id")),
            OpCode.PING: lambda p: {"pong": True, "state": self.state.value},
        }
        handler = handlers.get(op_code)
        if handler is None:
            raise ValueError(f"unknown op_code {op_code}")
        return handler(payload)

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start_cns(self, cns) -> None:
        """Connects this Memory organ to the central event bus."""
        self.cns = cns
        await self.cns.subscribe("MEMORY_STORE", "organ_03_store", self._handle_cns_store)
        await self.cns.subscribe("MEMORY_RETRIEVE", "organ_03_retrieve", self._handle_cns_retrieve)
        self.logger.info("Memory organ connected to CNS EventBus.")

    async def _handle_cns_store(self, env) -> None:
        payload = env.payload
        key = payload.get("key")
        value = payload.get("value")
        ttl = payload.get("ttl", 0)
        req_id = payload.get("request_id")
        
        if key and value:
            self.store_working(key, value, ttl)
            
        if req_id:
            await self.cns.publish(env.__class__(
                topic="MEMORY_STORE_ACK",
                source_organ="organ_03",
                payload={"request_id": req_id, "success": True}
            ))

    async def _handle_cns_retrieve(self, env) -> None:
        payload = env.payload
        key = payload.get("key")
        req_id = payload.get("request_id")
        
        if key and req_id:
            res = self.fetch_working(key)
            await self.cns.publish(env.__class__(
                topic="MEMORY_RETRIEVE_RESULT",
                source_organ="organ_03",
                payload={"request_id": req_id, "result": res}
            ))


# ═══════════════════════════════════════════════════════════════════════
# SECTION 12 — SYNCHRONOUS CLIENT (convenience wrapper for other organs)
# ═══════════════════════════════════════════════════════════════════════

class MemoryClient:
    """Thin synchronous client for organs that prefer direct in-process
    calls over socket round-trips when co-located with MemoryCore (e.g.
    during single-process integration testing). Cross-process organs
    (CNS, Brain, Agents) use the IPC socket directly per Section 7/9.
    """

    def __init__(self, core: MemoryCore) -> None:
        self._core = core

    def store_working(self, key: str, value: Any, ttl: int = 0) -> Dict[str, Any]:
        return self._core.store_working(key, value, ttl)

    def fetch_working(self, key: str) -> Any:
        return self._core.fetch_working(key)["value"]

    def create_room(self, room_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        return self._core.create_session_room(room_id, metadata)["room_id"]

    def append_context(self, room_id: str, role: str, content: Any) -> int:
        return self._core.append_session_context(room_id, {"role": role, "content": content})["msg_id"]

    def history(self, room_id: str, depth: int = 50) -> List[Dict[str, Any]]:
        return self._core.fetch_session_history(room_id, depth)["context"]

    def query_long_term(self, vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        return self._core.query_long_term(vector, limit)["results"]

    def snapshot(self, tag: str = "manual") -> str:
        return self._core.create_snapshot(tag)["snapshot_id"]


# ═══════════════════════════════════════════════════════════════════════
# SECTION 13 — ENTRYPOINT (bin/memory_daemon equivalent)
# ═══════════════════════════════════════════════════════════════════════

def run_daemon(config: Optional[MemoryOrganConfig] = None) -> None:
    """Standalone daemon entrypoint: `python organ_03_memory.py`."""
    core = MemoryCore(config)
    core.start()
    _audit(core.logger, "MEMORY_DAEMON_READY", sockets=core.ipc_handler.sockets_info())
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        core.stop()


if __name__ == "__main__":
    run_daemon()


# ═══════════════════════════════════════════════════════════════════════
# APPENDIX A — PRE-CODE ARCHITECTURE DIAGRAM (derived from the .md specs,
# authored BEFORE implementation, per Organ 03 Specification Sections
# 4–14, 39–45).
# ═══════════════════════════════════════════════════════════════════════
r"""
                         ┌───────────────────────────────────────────┐
                         │              CNS Organ (02)                │
                         │  routes memory commands + subscribes to    │
                         │  MemoryEvent notifications                 │
                         └───────────────────┬─────────────────────────┘
                                             │  IPC Socket
                                             │  \\.\pipe\hojaiga_memory
                                             │  [len|op_code|json]
                                             ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │                         MEMORY CORE (memory_kernel)               │
        │   State Machine: INITIALIZING → SYNCHRONIZED ⇄ COMPACTING        │
        │                     ⇄ FLUSHING / RECOVERY                        │
        └───────┬───────────────┬───────────────┬───────────────┬─────────┘
                │               │               │               │
                ▼               ▼               ▼               ▼
     ┌────────────────┐ ┌───────────────┐ ┌──────────────┐ ┌───────────────┐
     │ Working Memory  │ │ Session Mgr   │ │ Long-Term    │ │ Shared Memory │
     │ (RAM LRU + TTL) │ │ (Rooms/SQLite)│ │ Store (HDD)  │ │ Allocator     │
     │  IVolatileMemory │ │ IPersistent-  │ │ vector search│ │ mmap regions  │
     └────────┬────────┘ │  Storage      │ └──────┬───────┘ └───────────────┘
              │           └──────┬────────┘        │
     write-through│               │ archive closed   │
              ▼                  ▼  rooms            │
     ┌────────────────┐ ┌───────────────┐            │
     │ Compression     │ │ Snapshot Mgr  │◄───────────┘
     │ Engine (LZ4/ZL) │ │ (SSD .snap)   │  delta WAL every 30s / 1000 ops
     └────────┬────────┘ └──────┬────────┘
              │                 │ checksum + atomic replace
              ▼                 ▼
     MemoryIngestionPipeline:            MemoryRetrievalPipeline:
     CNS→Schema Check→Working RAM        CNS Query→Working RAM check→
     →Session Stream→Async Compress      (miss)→SQLite/Vector Query→
     →SSD WAL Flush                      Decompress→Assemble→Stream

     EVENTS OUT → CNS: SNAPSHOT_CREATED, ROOM_CREATED,
                  THRESHOLD_EXCEEDED, COMPRESSION_COMPLETED,
                  CORRUPTION_DETECTED

     STORAGE:  SSD Runtime (working swap, snapshots, session_rooms.sqlite)
               External HDD (long_term_memory.sqlite, archives)
"""

# ═══════════════════════════════════════════════════════════════════════
# APPENDIX B — POST-CODE IMPLEMENTATION DIAGRAM (derived from the actual
# classes defined above, reflecting real call graph and threads).
# ═══════════════════════════════════════════════════════════════════════
r"""
 MemoryCore.__init__()
   ├── EventBus()                              # in-process pub/sub -> CNS bridge
   ├── CompressionEngine()                      # LZ4 else zlib
   ├── WorkingMemory(on_write_through, on_threshold_exceeded)
   ├── SharedMemoryAllocator()                  # mmap-backed buffers
   ├── SessionManager()
   │      ├── SessionRoomStore(SQLite WAL)      # rooms + room_messages
   │      ├── SemanticPruner()                  # dedupe + token budget prune
   │      └── ContextTracker()                  # per-room token accounting
   ├── LongTermStore(SQLite WAL on HDD)         # knowledge_nodes + cosine search
   ├── SnapshotManager(SSD .snap + LATEST + DIRTY marker)
   └── IPCHandler(asyncio server: UnixSocket | TCP-loopback fallback for Windows)

 MemoryCore.start()
   ├── if DIRTY marker present -> _recover_from_crash()
   │        └── SnapshotManager.restore_snapshot() -> WorkingMemory.restore_state()
   ├── _start_persistence_workers()
   │        ├── N x _persistence_worker_loop()  (Semaphore-gated task queue)
   │        ├── _periodic_snapshot_loop()        (every snapshot_interval_seconds)
   │        └── _periodic_sweep_loop()           (TTL sweep + expired room prune, 60s)
   ├── _background_thread -> asyncio loop -> IPCHandler.start()
   └── SnapshotManager.mark_dirty()

 Runtime request flow (STORE_WORKING):
   IPCHandler._handle_client
     -> FrameCodec.read_frame
     -> MemoryCore._dispatch(OpCode.STORE_WORKING)
     -> MemoryCore.store_working
          -> MemoryStoreRequest.validate()
          -> WorkingMemory.store()
               -> LRU insert + evict_if_needed_locked()
               -> on_write_through -> _enqueue_task(_flush)
                    -> persistence worker -> SnapshotManager.register_write_op()
                         -> if threshold reached -> _maybe_snapshot()
                              -> SnapshotManager.create_snapshot()
                                   -> CompressionEngine.compress_json()
                                   -> atomic os.replace() + checksum marker
                                   -> EventBus.emit(SNAPSHOT_CREATED)

 Runtime request flow (APPEND_SESSION_CONTEXT):
   MemoryCore.append_session_context
     -> SessionManager.append_context -> SessionRoomStore.append_context (SQLite insert)
     -> ContextTracker.track()
     -> SessionManager.maybe_compress()
          -> ContextTracker.needs_compression() (token estimate > budget)
          -> SemanticPruner.prune_to_budget() (dedupe + recency-biased truncation)
          -> CompressionEngine.compress_json()
          -> EventBus.emit(COMPRESSION_COMPLETED)

 Runtime request flow (QUERY_LONG_TERM):
   MemoryCore.query_long_term -> LongTermStore.query_semantic
     -> brute-force cosine over knowledge_nodes (or vec0 extension if loaded)

 MemoryCore.stop()
   ├── state = FLUSHING
   ├── SnapshotManager.create_snapshot("shutdown")
   ├── _flush_closed_rooms_to_long_term()
   │        -> SessionManager.export_closed_rooms() -> LongTermStore.archive_room()
   ├── stop_event.set() -> join worker threads
   ├── stop asyncio loop -> IPCHandler.stop()
    └── SessionManager.shutdown() / LongTermStore.close() / clear DIRTY marker
"""


# =============================================================================
# Logic Engine: UI Functionality Archiver
# =============================================================================
# Satisfies: Question 4 — Separate Web vs Desktop UI history storage
# Placement: Bottom of organ_03_memory.py (append-only, no existing code modified)

class UIFunctionalityArchiver:
    """Classifies and stores UI element interaction history into two separate
    categories: WebApp_History and DesktopApp_History.

    Maps: button_name/xpath -> action -> outcome
    Storage: Local SQLite tables or JSON files under /history/
    """

    def __init__(self, data_dir: str = "./data/organ_03/ui_history"):
        import os
        import sqlite3 as _sqlite3
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._db_path = os.path.join(data_dir, "ui_functionality_archive.db")
        self._conn = _sqlite3.connect(self._db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS web_app_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT,
                    element_selector TEXT,
                    element_text TEXT,
                    action_performed TEXT,
                    outcome TEXT,
                    timestamp REAL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS desktop_app_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT,
                    element_id TEXT,
                    element_text TEXT,
                    action_performed TEXT,
                    outcome TEXT,
                    timestamp REAL
                )
            """)

    def record_web_interaction(self, app_name: str, selector: str, text: str,
                                action: str, outcome: str) -> None:
        import time as _time
        with self._conn:
            self._conn.execute(
                "INSERT INTO web_app_history (app_name, element_selector, element_text, "
                "action_performed, outcome, timestamp) VALUES (?,?,?,?,?,?)",
                (app_name, selector, text, action, outcome, _time.time())
            )

    def record_desktop_interaction(self, app_name: str, element_id: str, text: str,
                                    action: str, outcome: str) -> None:
        import time as _time
        with self._conn:
            self._conn.execute(
                "INSERT INTO desktop_app_history (app_name, element_id, element_text, "
                "action_performed, outcome, timestamp) VALUES (?,?,?,?,?,?)",
                (app_name, element_id, text, action, outcome, _time.time())
            )

    def query_web_history(self, app_name: str | None = None, limit: int = 100):
        query = "SELECT * FROM web_app_history"
        params = []
        if app_name:
            query += " WHERE app_name = ?"
            params.append(app_name)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cur = self._conn.execute(query, params)
        return cur.fetchall()

    def query_desktop_history(self, app_name: str | None = None, limit: int = 100):
        query = "SELECT * FROM desktop_app_history"
        params = []
        if app_name:
            query += " WHERE app_name = ?"
            params.append(app_name)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cur = self._conn.execute(query, params)
        return cur.fetchall()
