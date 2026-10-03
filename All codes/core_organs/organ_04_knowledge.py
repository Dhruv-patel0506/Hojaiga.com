"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 4
Name: Knowledge

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Knowledge]
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
Dependencies: numpy, platform, jsonschema, dataclasses, re...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_04_knowledge.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
organ_04_knowledge.py

Hojaiga Automation OS — Organ 04: Knowledge
Single-file production implementation.

Authority: Constitution -> Law Book -> Policy Manual ->
           Master Architecture Blueprint -> Organ Specification.

Responsibilities implemented in this module:
  - Capability Registry & Resolution
  - Application Intelligence Management
  - Governing Document Knowledge Base (doc_engine)
  - Workflow & Command Knowledge storage
  - Hybrid Search (SQLite FTS5 BM25 + CPU vector cosine similarity)
  - Incremental Knowledge Evolution (append-only merge)
  - Policy Verification
  - Named Pipe / Unix Socket IPC server with length-prefixed binary framing
  - State machine: INITIALIZING -> READY -> INDEXING -> DEGRADED -> MAINTENANCE

Dependencies: Python 3.11+, sqlite3 (stdlib, must be built with FTS5),
              jsonschema, numpy (CPU vector math). No GPU usage.
"""


import asyncio
import inspect
import json
import logging
import math
import os
import platform
import re
import sqlite3
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    from jsonschema import validate as _jsonschema_validate
    from jsonschema import ValidationError as _JsonSchemaValidationError
except ImportError:  # pragma: no cover
    _jsonschema_validate = None
    _JsonSchemaValidationError = Exception


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — LOGGING (Policy Manual Chapter 8 — Structured JSON Logging)
# ═══════════════════════════════════════════════════════════════════════════

# [2026-08-17] Deprecated old JSON formatters in favor of centralized clean terminal logs.
# class JsonLogFormatter(logging.Formatter):
#     def format(self, record: logging.LogRecord) -> str:
#         payload = {
#             "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
#             "level": record.levelname,
#             "component": "organ_04_knowledge",
#             "logger": record.name,
#             "message": record.getMessage(),
#         }
#         if record.exc_info:
#             payload["exception"] = self.formatException(record.exc_info)
#         extra = getattr(record, "extra_fields", None)
#         if extra:
#             payload.update(extra)
#         return json.dumps(payload, ensure_ascii=False)
# 
# 
# def build_logger(name: str = "organ_04_knowledge") -> logging.Logger:
#     logger = logging.getLogger(name)
#     if not logger.handlers:
#         handler = logging.StreamHandler(sys.stdout)
#         handler.setFormatter(JsonLogFormatter())
#         logger.addHandler(handler)
#         logger.setLevel(logging.INFO)
#     return logger

def build_logger(name: str = "organ_04_knowledge") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('{"timestamp":"%(asctime)s","logger":"%(name)s","level":"%(levelname)s","message":"%(message)s"}'))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


LOGGER = build_logger()


def log_event(level: int, message: str, **fields: Any) -> None:
    LOGGER.log(level, message, extra={"extra_fields": fields})


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — STATE MANAGEMENT (Spec §13 / Mermaid State Diagram §42)
# ═══════════════════════════════════════════════════════════════════════════

class OrganState(str, Enum):
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    INDEXING = "INDEXING"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"


class StateMachine:
    """Guards legal transitions per Spec §13 / §42 state diagram."""

    _TRANSITIONS: dict[OrganState, set[OrganState]] = {
        OrganState.INITIALIZING: {OrganState.READY, OrganState.DEGRADED},
        OrganState.READY: {OrganState.INDEXING, OrganState.DEGRADED, OrganState.MAINTENANCE},
        OrganState.INDEXING: {OrganState.READY, OrganState.DEGRADED},
        OrganState.DEGRADED: {OrganState.INDEXING},
        OrganState.MAINTENANCE: {OrganState.READY},
    }

    def __init__(self) -> None:
        self._state = OrganState.INITIALIZING
        self._lock = asyncio.Lock()

    @property
    def state(self) -> OrganState:
        return self._state

    async def transition(self, target: OrganState) -> None:
        async with self._lock:
            allowed = self._TRANSITIONS.get(self._state, set())
            if target not in allowed and target != self._state:
                raise RuntimeError(
                    f"Illegal state transition {self._state} -> {target}"
                )
            previous = self._state
            self._state = target
            log_event(logging.INFO, "state_transition", previous=previous.value, current=target.value)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — EVENT BUS CLIENT STUB (Outgoing Connections §12 / §14)
# ═══════════════════════════════════════════════════════════════════════════

class EventEmitter:
    """
    Thin adapter that publishes documented events toward CNS Organ (02).
    Actual socket wiring to CNS event bus is CNS's responsibility; this
    organ only guarantees event *emission* per the documented contract.
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[str, dict], None]] = []

    def subscribe(self, callback: Callable[[str, dict], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, event_name: str, payload: dict) -> None:
        envelope = {
            "event": event_name,
            "source_organ": "organ_04_knowledge",
            "timestamp": time.time(),
            "payload": payload,
        }
        log_event(logging.INFO, "event_emitted", event=event_name, payload=payload)
        for cb in self._subscribers:
            try:
                cb(event_name, envelope)
            except Exception:  # noqa: BLE001
                log_event(logging.ERROR, "event_subscriber_failure", event=event_name)


EVENTS = EventEmitter()


class KnowledgeEvents:
    KNOWLEDGE_INDEXED = "EVENT_KNOWLEDGE_INDEXED"
    CAPABILITY_RESOLVED = "EVENT_CAPABILITY_RESOLVED"
    CAPABILITY_UNRESOLVED = "EVENT_CAPABILITY_UNRESOLVED"
    APP_PROFILE_UPDATED = "EVENT_APP_PROFILE_UPDATED"
    GOVERNING_DOC_LOADED = "EVENT_GOVERNING_DOC_LOADED"
    KNOWLEDGE_UPDATED = "EVENT_KNOWLEDGE_UPDATED"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — DATA CONTRACTS (Spec §15) — JSON Schemas
# ═══════════════════════════════════════════════════════════════════════════

CAPABILITY_RESOLUTION_REQUEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CapabilityResolutionRequest",
    "type": "object",
    "properties": {
        "request_id": {"type": "string"},
        "capability": {"type": "string"},
        "target_os": {"type": "string", "default": "Windows_11"},
        "preferred_provider": {"type": "string"},
        "min_reliability_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["request_id", "capability"],
}

APP_PROFILE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AppProfile",
    "type": "object",
    "properties": {
        "app_id": {"type": "string"},
        "name": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "installed": {"type": "boolean"},
        "os_platform": {"type": "string"},
        "executable_path": {"type": "string"},
        "version": {"type": "string"},
        "reliability_score": {"type": "number"},
        "priority": {"type": "integer"},
    },
    "required": ["app_id", "name", "capabilities", "installed", "executable_path"],
}


def validate_payload(payload: dict, schema: dict) -> None:
    if _jsonschema_validate is None:
        _minimal_schema_check(payload, schema)
        return
    try:
        _jsonschema_validate(instance=payload, schema=schema)
    except _JsonSchemaValidationError as exc:  # noqa: BLE001
        raise ValueError(f"Schema validation failed: {str(exc)}") from exc


def _minimal_schema_check(payload: dict, schema: dict) -> None:
    for required_field in schema.get("required", []):
        if required_field not in payload:
            raise ValueError(f"Missing required field: {required_field}")


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 — CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class KnowledgeConfig:
    root_dir: Path = field(default_factory=lambda: Path("./organ_04_knowledge"))
    db_relative_path: str = "storage/knowledge_db.sqlite"
    system_docs_dir: str = "data/system_docs"
    profiles_dir: str = "data/profiles"
    capabilities_dir: str = "data/capabilities"
    workflows_dir: str = "data/workflows"
    indexes_dir: str = "storage/indexes"
    mmap_size_bytes: int = 268_435_456  # 256 MB
    lru_cache_slots: int = 256
    vector_dim: int = 384
    hybrid_alpha_default: float = 0.5
    pipe_name: str = r"\\.\pipe\hojaiga_knowledge"
    unix_socket_path: str = "/tmp/hojaiga_knowledge.sock"
    max_payload_bytes: int = 16 * 1024 * 1024

    def resolve(self) -> "KnowledgeConfig":
        self.root_dir = Path(self.root_dir).resolve()
        return self

    @property
    def db_path(self) -> Path:
        return self.root_dir / self.db_relative_path

    @property
    def system_docs_path(self) -> Path:
        return self.root_dir / self.system_docs_dir

    @property
    def profiles_path(self) -> Path:
        return self.root_dir / self.profiles_dir

    @property
    def capabilities_path(self) -> Path:
        return self.root_dir / self.capabilities_dir

    @property
    def workflows_path(self) -> Path:
        return self.root_dir / self.workflows_dir

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "KnowledgeConfig":
        cfg = cls()
        if config_path and Path(config_path).exists():
            raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
            for key, value in raw.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
        return cfg.resolve()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6 — LRU CACHE (Spec §17 Cache Strategy)
# ═══════════════════════════════════════════════════════════════════════════

class LRUCache:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._store: dict[str, Any] = {}
        self._order: list[str] = []

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        self._order.remove(key)
        self._order.append(key)
        return self._store[key]

    def put(self, key: str, value: Any) -> None:
        if key in self._store:
            self._order.remove(key)
        elif len(self._store) >= self.capacity:
            oldest = self._order.pop(0)
            del self._store[oldest]
        self._store[key] = value
        self._order.append(key)

    def clear(self) -> None:
        self._store.clear()
        self._order.clear()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7 — SQLITE STORAGE LAYER (Spec §16 Internal Database Structures)
# ═══════════════════════════════════════════════════════════════════════════

class KnowledgeStorage:
    """
    Owns storage/knowledge_db.sqlite.
    Tables: capabilities, app_profiles, capability_providers,
            doc_chunks_fts (FTS5 virtual table), doc_chunks_vec.
    Multi-reader / single-writer concurrency model (Spec §19/§20).
    """

    def __init__(self, config: KnowledgeConfig) -> None:
        self.config = config
        self._write_lock = asyncio.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._fts5_available = False

    # -- lifecycle ------------------------------------------------------
    def open(self) -> None:
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.config.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(f"PRAGMA mmap_size={self.config.mmap_size_bytes};")
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._fts5_available = self._check_fts5()
        self._create_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _check_fts5(self) -> bool:
        try:
            cur = self._conn.execute(  # type: ignore
                "SELECT sqlite_compileoption_used('ENABLE_FTS5');"
            )
            return bool(cur.fetchone()[0])
        except sqlite3.Error:
            return False

    def _create_schema(self) -> None:
        assert self._conn is not None
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS capabilities (
                cap_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                aliases_json TEXT NOT NULL DEFAULT '[]'
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_profiles (
                app_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                executable_path TEXT NOT NULL,
                installed INTEGER NOT NULL DEFAULT 0,
                version TEXT,
                reliability_score REAL NOT NULL DEFAULT 0.5,
                priority INTEGER NOT NULL DEFAULT 100,
                os_platform TEXT,
                data_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_providers (
                cap_id TEXT NOT NULL,
                app_id TEXT NOT NULL,
                PRIMARY KEY (cap_id, app_id),
                FOREIGN KEY (cap_id) REFERENCES capabilities(cap_id),
                FOREIGN KEY (app_id) REFERENCES app_profiles(app_id)
            );
            """
        )
        if self._fts5_available:
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts
                USING fts5(chunk_id UNINDEXED, doc_type, title, content_text,
                           tokenize='porter');
                """
            )
        else:
            log_event(logging.WARNING, "fts5_unavailable_fallback_to_like_search")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_chunks_fts (
                    chunk_id TEXT PRIMARY KEY,
                    doc_type TEXT,
                    title TEXT,
                    content_text TEXT
                );
                """
            )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_chunks_vec (
                chunk_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_history (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        self._conn.commit()

    # -- write path (single-threaded worker queue guarantee via lock) ---
    async def execute_write(self, sql: str, params: tuple = ()) -> None:
        async with self._write_lock:
            assert self._conn is not None
            self._conn.execute(sql, params)
            self._conn.commit()

    async def execute_many_write(self, sql: str, seq_params: list[tuple]) -> None:
        async with self._write_lock:
            assert self._conn is not None
            self._conn.executemany(sql, seq_params)
            self._conn.commit()

    # -- read path --------------------------------------------------------
    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        assert self._conn is not None
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def append_history(self, event_type: str, payload: dict) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO knowledge_history (event_id, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?);",
            (str(uuid.uuid4()), event_type, json.dumps(payload), time.time()),
        )
        self._conn.commit()

    def is_healthy(self) -> bool:
        try:
            assert self._conn is not None
            self._conn.execute("SELECT 1;")
            return True
        except sqlite3.Error:
            return False

    def vacuum(self) -> None:
        assert self._conn is not None
        self._conn.execute("VACUUM;")
        self._conn.commit()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8 — DOC ENGINE (Markdown/JSON Documentation Intelligence)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DocChunk:
    chunk_id: str
    doc_type: str
    title: str
    content_text: str


class DocParser:
    """Converts Markdown governing documents into heading-scoped chunks (AST-lite)."""

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)

    def parse(self, doc_type: str, markdown_text: str) -> list[DocChunk]:
        headings = list(self._HEADING_RE.finditer(markdown_text))
        chunks: list[DocChunk] = []
        if not headings:
            chunks.append(
                DocChunk(
                    chunk_id=str(uuid.uuid4()),
                    doc_type=doc_type,
                    title=doc_type,
                    content_text=markdown_text.strip(),
                )
            )
            return chunks
        for idx, match in enumerate(headings):
            title = match.group(2).strip()
            start = match.end()
            end = headings[idx + 1].start() if idx + 1 < len(headings) else len(markdown_text)
            body = markdown_text[start:end].strip()
            if not body:
                continue
            chunks.append(
                DocChunk(
                    chunk_id=str(uuid.uuid4()),
                    doc_type=doc_type,
                    title=title,
                    content_text=body,
                )
            )
        return chunks


class DocEngine:
    """
    doc_engine: Loads governing documents, keeps a permanent in-RAM AST
    cache (Spec §17/§46), and feeds the hybrid search index.
    """

    GOVERNING_DOC_TYPES = (
        "constitution",
        "law_book",
        "policy_manual",
        "architecture_blueprint",
        "organ_specification",
    )

    def __init__(self, config: KnowledgeConfig, storage: KnowledgeStorage) -> None:
        self.config = config
        self.storage = storage
        self.parser = DocParser()
        self._ast_cache: dict[str, list[DocChunk]] = {}

    def load_governing_doc(self, doc_type: str) -> list[DocChunk]:
        cached = self._ast_cache.get(doc_type)
        if cached is not None:
            return cached
        file_path = self._resolve_doc_path(doc_type)
        if not file_path.exists():
            raise FileNotFoundError(f"Governing document not found: {file_path}")
        text = file_path.read_text(encoding="utf-8")
        chunks = self.parser.parse(doc_type, text)
        self._ast_cache[doc_type] = chunks
        EVENTS.emit(KnowledgeEvents.GOVERNING_DOC_LOADED, {"doc_type": doc_type, "chunks": len(chunks)})
        return chunks

    def preload_all(self) -> None:
        for doc_type in self.GOVERNING_DOC_TYPES:
            path = self._resolve_doc_path(doc_type)
            if path.exists():
                self.load_governing_doc(doc_type)

    def _resolve_doc_path(self, doc_type: str) -> Path:
        filename_map = {
            "constitution": "Constitution.md",
            "law_book": "LawBook.md",
            "policy_manual": "PolicyManual.md",
            "architecture_blueprint": "MasterArchitectureBlueprint.md",
            "organ_specification": "Organ_Specification.md",
        }
        filename = filename_map.get(doc_type, f"{doc_type}.md")
        return self.config.system_docs_path / filename

    def all_cached_chunks(self) -> list[DocChunk]:
        result: list[DocChunk] = []
        for chunks in self._ast_cache.values():
            result.extend(chunks)
        return result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9 — HYBRID SEARCH ENGINE (BM25 via FTS5 + CPU Vector Cosine)
# ═══════════════════════════════════════════════════════════════════════════

def naive_embed(text: str, dim: int = 384) -> "np.ndarray":  # type: ignore
    """
    Deterministic, dependency-free CPU embedding fallback based on
    hashed token bag projection. Serves as the default local vectorizer
    when no external embedding model is configured (CPU-only, no GPU).
    """
    if np is None:
        raise RuntimeError("numpy is required for vector search")
    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    for tok in tokens:
        h = hash(tok) % dim
        vec[h] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


class HybridSearchEngine:
    """
    hybrid_search_engine: Combines SQLite FTS5 BM25 lexical scoring with
    CPU vector cosine similarity (Spec §5, §21, §41).
    """

    def __init__(self, config: KnowledgeConfig, storage: KnowledgeStorage) -> None:
        self.config = config
        self.storage = storage

    async def index_chunk(self, chunk: DocChunk) -> None:
        await self.storage.execute_write(
            "INSERT OR REPLACE INTO doc_chunks_fts (chunk_id, doc_type, title, content_text) "
            "VALUES (?, ?, ?, ?);",
            (chunk.chunk_id, chunk.doc_type, chunk.title, chunk.content_text),
        )
        if np is not None:
            embedding = naive_embed(chunk.content_text, self.config.vector_dim)
            await self.storage.execute_write(
                "INSERT OR REPLACE INTO doc_chunks_vec (chunk_id, embedding) VALUES (?, ?);",
                (chunk.chunk_id, embedding.tobytes()),
            )

    async def index_many(self, chunks: list[DocChunk]) -> None:
        for chunk in chunks:
            await self.index_chunk(chunk)

    def _bm25_search(self, text_query: str, limit: int) -> dict[str, float]:
        results: dict[str, float] = {}
        if self.storage._fts5_available:
            try:
                rows = self.storage.query(
                    "SELECT chunk_id, bm25(doc_chunks_fts) AS score FROM doc_chunks_fts "
                    "WHERE doc_chunks_fts MATCH ? ORDER BY score LIMIT ?;",
                    (text_query, limit * 4),
                )
                for row in rows:
                    # bm25() returns lower-is-better; invert for unified higher-is-better scale.
                    results[row["chunk_id"]] = 1.0 / (1.0 + max(row["score"], 0.0))
            except sqlite3.OperationalError:
                results = self._like_fallback(text_query, limit)
        else:
            results = self._like_fallback(text_query, limit)
        return results

    def _like_fallback(self, text_query: str, limit: int) -> dict[str, float]:
        like_pattern = f"%{text_query}%"
        rows = self.storage.query(
            "SELECT chunk_id, content_text FROM doc_chunks_fts WHERE content_text LIKE ? LIMIT ?;",
            (like_pattern, limit * 4),
        )
        return {row["chunk_id"]: 0.5 for row in rows}

    def _vector_search(self, text_query: str, limit: int) -> dict[str, float]:
        if np is None:
            return {}
        query_vec = naive_embed(text_query, self.config.vector_dim)
        rows = self.storage.query("SELECT chunk_id, embedding FROM doc_chunks_vec;")
        scored: list[tuple[str, float]] = []
        for row in rows:
            vec = np.frombuffer(row["embedding"], dtype=np.float32)
            denom = (np.linalg.norm(query_vec) * np.linalg.norm(vec)) or 1e-9
            cosine = float(np.dot(query_vec, vec) / denom)
            scored.append((row["chunk_id"], cosine))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return dict(scored[: limit * 4])

    def execute_hybrid_query(
        self, text: str, limit: int = 10, alpha: Optional[float] = None
    ) -> list[dict]:
        alpha = self.config.hybrid_alpha_default if alpha is None else alpha
        bm25_scores = self._bm25_search(text, limit)
        vector_scores = self._vector_search(text, limit)
        all_ids = set(bm25_scores) | set(vector_scores)
        blended: list[tuple[str, float]] = []
        for chunk_id in all_ids:
            lexical = bm25_scores.get(chunk_id, 0.0)
            semantic = vector_scores.get(chunk_id, 0.0)
            blended_score = (alpha * semantic) + ((1 - alpha) * lexical)
            blended.append((chunk_id, blended_score))
        blended.sort(key=lambda pair: pair[1], reverse=True)
        top = blended[:limit]
        results = []
        for chunk_id, score in top:
            row = self.storage.query(
                "SELECT chunk_id, doc_type, title, content_text FROM doc_chunks_fts WHERE chunk_id = ?;",
                (chunk_id,),
            )
            if row:
                r = row[0]
                results.append(
                    {
                        "chunk_id": r["chunk_id"],
                        "doc_type": r["doc_type"],
                        "title": r["title"],
                        "snippet": r["content_text"][:400],
                        "score": round(score, 6),
                    }
                )
        return results


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10 — APPLICATION INTELLIGENCE (app_intelligence)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AppProfile:
    app_id: str
    name: str
    capabilities: list[str]
    installed: bool
    executable_path: str
    aliases: list[str] = field(default_factory=list)
    os_platform: str = field(default_factory=lambda: f"Windows_{platform.release()}")
    version: str = "0.0.0"
    reliability_score: float = 0.5
    priority: int = 100

    def to_dict(self) -> dict:
        return asdict(self)


class AppIntelligence:
    """app_intelligence: Application profile manager (Spec §5, §15, §16)."""

    def __init__(self, config: KnowledgeConfig, storage: KnowledgeStorage) -> None:
        self.config = config
        self.storage = storage

    async def upsert_profile(self, profile: AppProfile) -> None:
        validate_payload(profile.to_dict(), APP_PROFILE_SCHEMA)
        data_json = json.dumps(
            {"aliases": profile.aliases, "capabilities": profile.capabilities}
        )
        await self.storage.execute_write(
            """
            INSERT INTO app_profiles
                (app_id, name, executable_path, installed, version,
                 reliability_score, priority, os_platform, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                name=excluded.name,
                executable_path=excluded.executable_path,
                installed=excluded.installed,
                version=excluded.version,
                reliability_score=excluded.reliability_score,
                priority=excluded.priority,
                os_platform=excluded.os_platform,
                data_json=excluded.data_json;
            """,
            (
                profile.app_id,
                profile.name,
                profile.executable_path,
                int(profile.installed),
                profile.version,
                profile.reliability_score,
                profile.priority,
                profile.os_platform,
                data_json,
            ),
        )
        for cap in profile.capabilities:
            await self.storage.execute_write(
                "INSERT OR IGNORE INTO capabilities (cap_id, name, description, aliases_json) "
                "VALUES (?, ?, ?, ?);",
                (cap, cap, "", "[]"),
            )
            await self.storage.execute_write(
                "INSERT OR IGNORE INTO capability_providers (cap_id, app_id) VALUES (?, ?);",
                (cap, profile.app_id),
            )
        self.storage.append_history("APP_PROFILE_UPSERT", profile.to_dict())
        EVENTS.emit(KnowledgeEvents.APP_PROFILE_UPDATED, {"app_id": profile.app_id})

    def get_profile(self, app_id_or_alias: str) -> Optional[dict]:
        rows = self.storage.query(
            "SELECT * FROM app_profiles WHERE app_id = ? OR name = ?;",
            (app_id_or_alias, app_id_or_alias),
        )
        if not rows:
            rows = [
                row
                for row in self.storage.query("SELECT * FROM app_profiles;")
                if app_id_or_alias.lower()
                in [a.lower() for a in json.loads(row["data_json"]).get("aliases", [])]
            ]
        if not rows:
            return None
        row = rows[0]
        data = json.loads(row["data_json"])
        return {
            "app_id": row["app_id"],
            "name": row["name"],
            "executable_path": row["executable_path"],
            "installed": bool(row["installed"]),
            "version": row["version"],
            "reliability_score": row["reliability_score"],
            "priority": row["priority"],
            "os_platform": row["os_platform"],
            "aliases": data.get("aliases", []),
            "capabilities": data.get("capabilities", []),
        }

    async def update_health_score(self, app_id: str, delta: float) -> None:
        rows = self.storage.query(
            "SELECT reliability_score FROM app_profiles WHERE app_id = ?;", (app_id,)
        )
        if not rows:
            raise ValueError(f"Unknown app_id: {app_id}")
        new_score = max(0.0, min(1.0, rows[0]["reliability_score"] + delta))
        await self.storage.execute_write(
            "UPDATE app_profiles SET reliability_score = ? WHERE app_id = ?;",
            (new_score, app_id),
        )
        self.storage.append_history(
            "HEALTH_SCORE_UPDATE", {"app_id": app_id, "delta": delta, "new_score": new_score}
        )
        EVENTS.emit(KnowledgeEvents.APP_PROFILE_UPDATED, {"app_id": app_id, "reliability_score": new_score})


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11 — CAPABILITY REGISTRY (capability_registry)
# ═══════════════════════════════════════════════════════════════════════════

class CapabilityRegistry:
    """
    capability_registry: Capability-to-provider matcher, priority evaluator,
    alias resolution engine (Spec §5, §10 CapabilityResolutionPipeline).
    """

    def __init__(self, config: KnowledgeConfig, storage: KnowledgeStorage) -> None:
        self.config = config
        self.storage = storage
        self.cache = LRUCache(config.lru_cache_slots)

    async def register_alias(self, capability_name: str, alias: str) -> None:
        rows = self.storage.query(
            "SELECT aliases_json FROM capabilities WHERE cap_id = ?;", (capability_name,)
        )
        if not rows:
            await self.storage.execute_write(
                "INSERT INTO capabilities (cap_id, name, description, aliases_json) VALUES (?, ?, ?, ?);",
                (capability_name, capability_name, "", json.dumps([alias])),
            )
        else:
            aliases = json.loads(rows[0]["aliases_json"])
            if alias not in aliases:
                aliases.append(alias)
            await self.storage.execute_write(
                "UPDATE capabilities SET aliases_json = ? WHERE cap_id = ?;",
                (json.dumps(aliases), capability_name),
            )
        self.cache.clear()

    def _resolve_alias_to_capability(self, capability: str) -> str:
        rows = self.storage.query("SELECT cap_id, aliases_json FROM capabilities;")
        for row in rows:
            if row["cap_id"] == capability:
                return capability
            if capability.lower() in [a.lower() for a in json.loads(row["aliases_json"])]:
                return row["cap_id"]
        return capability

    def find_providers(
        self,
        capability: str,
        target_os: str = "Windows_11",
        min_reliability_score: float = 0.0,
        preferred_provider: Optional[str] = None,
    ) -> list[dict]:
        cache_key = f"{capability}|{target_os}|{min_reliability_score}|{preferred_provider}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        resolved_cap = self._resolve_alias_to_capability(capability)
        rows = self.storage.query(
            """
            SELECT ap.* FROM app_profiles ap
            JOIN capability_providers cp ON ap.app_id = cp.app_id
            WHERE cp.cap_id = ? AND ap.installed = 1
              AND (ap.os_platform = ? OR ap.os_platform = 'any')
              AND ap.reliability_score >= ?;
            """,
            (resolved_cap, target_os, min_reliability_score),
        )
        providers = []
        for row in rows:
            data = json.loads(row["data_json"])
            providers.append(
                {
                    "app_id": row["app_id"],
                    "name": row["name"],
                    "executable_path": row["executable_path"],
                    "version": row["version"],
                    "reliability_score": row["reliability_score"],
                    "priority": row["priority"],
                    "capabilities": data.get("capabilities", []),
                }
            )

        def sort_key(p: dict) -> tuple:
            preferred_rank = 0 if preferred_provider and p["app_id"] == preferred_provider else 1
            return (preferred_rank, -p["priority"], -p["reliability_score"])

        providers.sort(key=sort_key)
        self.cache.put(cache_key, providers)
        return providers


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 12 — POLICY VERIFIER
# ═══════════════════════════════════════════════════════════════════════════

class PolicyVerifier:
    """
    policy_verifier: Evaluates proposed execution parameters against
    stored policy rules and constitutional constraints (Spec §5, §38).
    """

    PROTECTED_RESOURCES = {
        "constitution",
        "law_book",
        "policy_manual",
        "core_architecture",
        "system_configuration",
        "credentials",
        "secrets",
    }

    def __init__(self, doc_engine: DocEngine) -> None:
        self.doc_engine = doc_engine

    def verify_action(self, action: dict) -> dict:
        target_resource = str(action.get("target_resource", "")).lower()
        requires_authorization = target_resource in self.PROTECTED_RESOURCES
        approved = not requires_authorization or bool(action.get("human_authorized", False))
        return {
            "approved": approved,
            "requires_authorization": requires_authorization,
            "reason": (
                "Protected resource requires explicit human authorization "
                "(Law Book — Foundational Law 12)."
                if requires_authorization and not approved
                else "Action within permitted operational scope."
            ),
        }

    def read_policy(self, category: str) -> list[dict]:
        try:
            chunks = self.doc_engine.load_governing_doc("policy_manual")
        except FileNotFoundError:
            return []
        matches = [c for c in chunks if category.lower() in c.title.lower()]
        return [{"title": c.title, "content": c.content_text} for c in matches]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 13 — INCREMENTAL KNOWLEDGE MERGER (evolution/incremental_merger.py)
# ═══════════════════════════════════════════════════════════════════════════

class IncrementalMerger:
    """
    knowledge_merger: Differential updater. Never overwrites arbitrarily;
    performs additive merges and records deltas in append-only history.
    """

    def __init__(self, storage: KnowledgeStorage, hybrid_search: HybridSearchEngine) -> None:
        self.storage = storage
        self.hybrid_search = hybrid_search

    async def merge_documents(self, chunks: list[DocChunk]) -> int:
        await self.hybrid_search.index_many(chunks)
        self.storage.append_history(
            "KNOWLEDGE_MERGE", {"chunk_count": len(chunks), "chunk_ids": [c.chunk_id for c in chunks]}
        )
        EVENTS.emit(KnowledgeEvents.KNOWLEDGE_UPDATED, {"chunks_merged": len(chunks)})
        return len(chunks)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 14 — KNOWLEDGE KERNEL (core/knowledge_kernel.py — knowledge_core)
# ═══════════════════════════════════════════════════════════════════════════

class KnowledgeKernel:
    """
    knowledge_core: Central IPC interface, query router, and knowledge
    request lifecycle coordinator (Spec §5, §7, §10).
    """

    def __init__(self, config: Optional[KnowledgeConfig] = None) -> None:
        self.config = config or KnowledgeConfig().resolve()
        self.state = StateMachine()
        self.storage = KnowledgeStorage(self.config)
        self.doc_engine: Optional[DocEngine] = None
        self.hybrid_search: Optional[HybridSearchEngine] = None
        self.app_intelligence: Optional[AppIntelligence] = None
        self.capability_registry: Optional[CapabilityRegistry] = None
        self.policy_verifier: Optional[PolicyVerifier] = None
        self.merger: Optional[IncrementalMerger] = None

    async def initialize(self) -> None:
        log_event(logging.INFO, "kernel_initializing")
        for directory in (
            self.config.system_docs_path,
            self.config.profiles_path,
            self.config.capabilities_path,
            self.config.workflows_path,
            (self.config.root_dir / self.config.indexes_dir),
        ):
            directory.mkdir(parents=True, exist_ok=True)

        try:
            self.storage.open()
        except sqlite3.Error as exc:
            log_event(logging.ERROR, "storage_open_failed", error=str(exc))
            await self.state.transition(OrganState.DEGRADED)
            return

        self.doc_engine = DocEngine(self.config, self.storage)
        self.hybrid_search = HybridSearchEngine(self.config, self.storage)
        self.app_intelligence = AppIntelligence(self.config, self.storage)
        self.capability_registry = CapabilityRegistry(self.config, self.storage)
        self.policy_verifier = PolicyVerifier(self.doc_engine)
        self.merger = IncrementalMerger(self.storage, self.hybrid_search)

        if not self.storage.is_healthy():
            await self.state.transition(OrganState.DEGRADED)
            await self.recover()
            return

        try:
            self.doc_engine.preload_all()
        except Exception as exc:  # noqa: BLE001
            log_event(logging.WARNING, "doc_preload_partial_failure", error=str(exc))

        await self.state.transition(OrganState.READY)
        log_event(logging.INFO, "kernel_ready")

    async def recover(self) -> None:
        """Recovery Strategy: rebuild index from raw source files (Spec §30)."""
        log_event(logging.WARNING, "recovery_started")
        await self.state.transition(OrganState.INDEXING)
        try:
            self.doc_engine.preload_all()  # type: ignore
            all_chunks = self.doc_engine.all_cached_chunks()  # type: ignore
            if all_chunks and self.merger:
                await self.merger.merge_documents(all_chunks)
            await self._reload_profiles_from_disk()
            EVENTS.emit(KnowledgeEvents.KNOWLEDGE_INDEXED, {"recovered_chunks": len(all_chunks)})
            await self.state.transition(OrganState.READY)
            log_event(logging.INFO, "recovery_complete")
        except Exception as exc:  # noqa: BLE001
            log_event(logging.ERROR, "recovery_failed", error=str(exc))
            await self.state.transition(OrganState.DEGRADED)

    async def _reload_profiles_from_disk(self) -> None:
        if not self.config.profiles_path.exists():
            return
        for profile_file in self.config.profiles_path.glob("*.json"):
            try:
                raw = json.loads(profile_file.read_text(encoding="utf-8"))
                profile = AppProfile(**raw)
                await self.app_intelligence.upsert_profile(profile)  # type: ignore
            except Exception as exc:  # noqa: BLE001
                log_event(logging.WARNING, "profile_reload_failed", file=str(profile_file), error=str(exc))

    async def enter_maintenance(self) -> None:
        await self.state.transition(OrganState.MAINTENANCE)
        self.storage.vacuum()
        await self.state.transition(OrganState.READY)

    async def shutdown(self) -> None:
        self.storage.close()
        log_event(logging.INFO, "kernel_shutdown")

    # -- RPC handlers (Spec §7 Public Interfaces) -------------------------

    async def resolve_capability(self, payload: dict) -> dict:
        validate_payload(payload, CAPABILITY_RESOLUTION_REQUEST_SCHEMA)
        providers = self.capability_registry.find_providers(  # type: ignore
            capability=payload["capability"],
            target_os=payload.get("target_os", "Windows_11"),
            min_reliability_score=payload.get("min_reliability_score", 0.0),
            preferred_provider=payload.get("preferred_provider"),
        )
        if providers:
            EVENTS.emit(
                KnowledgeEvents.CAPABILITY_RESOLVED,
                {"capability": payload["capability"], "top_provider": providers[0]["app_id"]},
            )
        else:
            EVENTS.emit(KnowledgeEvents.CAPABILITY_UNRESOLVED, {"capability": payload["capability"]})
        return {"request_id": payload["request_id"], "providers": providers}

    async def query_documentation(self, payload: dict) -> dict:
        doc_type = payload["doc_type"]
        chunks = self.doc_engine.load_governing_doc(doc_type)  # type: ignore
        return {"doc_type": doc_type, "chunks": [asdict(c) for c in chunks]}

    async def get_app_profile(self, app_name_or_alias: str) -> Optional[dict]:
        return self.app_intelligence.get_profile(app_name_or_alias)  # type: ignore

    async def read_policy(self, category: str) -> list[dict]:
        return self.policy_verifier.read_policy(category)  # type: ignore

    async def search_knowledge(self, payload: dict) -> list[dict]:
        return self.hybrid_search.execute_hybrid_query(  # type: ignore
            text=payload["text"],
            limit=payload.get("limit", 10),
            alpha=payload.get("alpha"),
        )

    async def update_app_health_score(self, payload: dict) -> dict:
        await self.app_intelligence.update_health_score(payload["app_id"], payload["delta"])  # type: ignore
        return {"ack": True}

    async def ingest_knowledge(self, payload: dict) -> dict:
        doc_type = payload.get("doc_type", "custom")
        text = payload["content_text"]
        chunks = self.doc_engine.parser.parse(doc_type, text)  # type: ignore
        count = await self.merger.merge_documents(chunks)  # type: ignore
        return {"ingested_chunks": count}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 15 — QUERY DISPATCHER (core/query_dispatcher.py)
# ═══════════════════════════════════════════════════════════════════════════

class QueryDispatcher:
    """Routes op_codes to KnowledgeKernel RPC handlers."""

    OP_RESOLVE_CAPABILITY = 1
    OP_QUERY_DOCUMENTATION = 2
    OP_GET_APP_PROFILE = 3
    OP_READ_POLICY = 4
    OP_SEARCH_KNOWLEDGE = 5
    OP_UPDATE_APP_HEALTH_SCORE = 6
    OP_INGEST_KNOWLEDGE = 7

    def __init__(self, kernel: KnowledgeKernel) -> None:
        self.kernel = kernel

    async def dispatch(self, op_code: int, payload: dict) -> dict:
        if self.kernel.state.state not in (OrganState.READY, OrganState.INDEXING):
            return {"error": f"organ_unavailable state={self.kernel.state.state.value}"}
        try:
            if op_code == self.OP_RESOLVE_CAPABILITY:
                return await self.kernel.resolve_capability(payload)
            if op_code == self.OP_QUERY_DOCUMENTATION:
                return await self.kernel.query_documentation(payload)
            if op_code == self.OP_GET_APP_PROFILE:
                result = await self.kernel.get_app_profile(payload["app_name_or_alias"])
                return result or {"error": "not_found"}
            if op_code == self.OP_READ_POLICY:
                return {"rules": await self.kernel.read_policy(payload["category"])}
            if op_code == self.OP_SEARCH_KNOWLEDGE:
                return {"matches": await self.kernel.search_knowledge(payload)}
            if op_code == self.OP_UPDATE_APP_HEALTH_SCORE:
                return await self.kernel.update_app_health_score(payload)
            if op_code == self.OP_INGEST_KNOWLEDGE:
                return await self.kernel.ingest_knowledge(payload)
            return {"error": f"unknown_op_code:{op_code}"}
        except (ValueError, FileNotFoundError) as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log_event(logging.ERROR, "dispatch_failure", op_code=op_code, error=str(exc))
            return {"error": "internal_error"}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 16 — IPC SERVER (sockets/ipc_server.py)
# Wire Protocol: [4-byte length | 2-byte op_code | JSON payload], max 16MB
# ═══════════════════════════════════════════════════════════════════════════

class IPCServer:
    def __init__(self, kernel: KnowledgeKernel, dispatcher: QueryDispatcher) -> None:
        self.kernel = kernel
        self.dispatcher = dispatcher
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        config = self.kernel.config
        if platform.system() == "Windows":
            log_event(logging.INFO, "ipc_named_pipe_mode_selected", pipe=config.pipe_name)
            # loop.start_serving_pipe() returns a LIST of server objects (one per
            # pipe instance) on Windows; normalise to a single AbstractServer.
            server = await self._start_windows_pipe(config.pipe_name)
            if isinstance(server, (list, tuple)):
                server = server[0] if server else None
            self._server = server
        else:
            socket_path = config.unix_socket_path
            if os.path.exists(socket_path):
                os.remove(socket_path)
            self._server = await asyncio.start_unix_server(self._handle_client, path=socket_path)  # type: ignore
            log_event(logging.INFO, "ipc_unix_socket_started", path=socket_path)

    async def _start_windows_pipe(self, pipe_name: str):
        try:
            import asyncio.windows_events  # noqa: F401
            loop = asyncio.get_event_loop()
            if hasattr(loop, "start_serving_pipe"):
                server = await loop.start_serving_pipe(  # type: ignore[attr-defined]
                    lambda: _PipeProtocolAdapter(self._handle_client), pipe_name
                )
                return server
            else:
                raise AttributeError("start_serving_pipe not available")
        except (AttributeError, NotImplementedError, OSError):
            log_event(
                logging.WARNING,
                "named_pipe_unavailable_fallback_tcp",
                fallback_host="127.0.0.1",
                fallback_port=48891,
            )
            return await asyncio.start_server(self._handle_client, host="127.0.0.1", port=48891)  # type: ignore

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername", "pipe-client")
        log_event(logging.INFO, "client_connected", peer=str(peer))
        try:
            while True:
                header = await reader.readexactly(6)
                length, op_code = struct.unpack(">IH", header)
                if length > self.kernel.config.max_payload_bytes:
                    await self._write_response(writer, {"error": "payload_too_large"})
                    break
                body = await reader.readexactly(length)
                try:
                    payload = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    await self._write_response(writer, {"error": "invalid_json"})
                    continue
                response = await self.dispatcher.dispatch(op_code, payload)
                await self._write_response(writer, response)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()
            log_event(logging.INFO, "client_disconnected", peer=str(peer))

    @staticmethod
    async def _write_response(writer: asyncio.StreamWriter, response: dict) -> None:
        body = json.dumps(response).encode("utf-8")
        header = struct.pack(">IH", len(body), 0)
        writer.write(header + body)
        await writer.drain()

    async def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.close()
            except Exception:  # noqa: BLE001 - pipe listeners may lack full AbstractServer API
                pass
            # wait_closed() is a coroutine on AbstractServer, a plain no-op on
            # Windows pipe listeners, and absent on _PipeServer (start_serving_pipe).
            waiter = getattr(self._server, "wait_closed", None)
            if waiter is not None:
                maybeAwaitable = waiter()
                if inspect.isawaitable(maybeAwaitable):
                    await maybeAwaitable


class _PipeProtocolAdapter(asyncio.Protocol):
    """Bridges Windows ProactorEventLoop pipe transport to the stream-based handler."""

    def __init__(self, handler: Callable) -> None:
        self._handler = handler
        self._reader: Optional[asyncio.StreamReader] = None
        self._transport: Optional[asyncio.WriteTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]
        self._reader = asyncio.StreamReader()
        writer = asyncio.StreamWriter(transport, self, self._reader, asyncio.get_event_loop())  # type: ignore[arg-type]
        asyncio.ensure_future(self._handler(self._reader, writer))

    def data_received(self, data: bytes) -> None:
        if self._reader:
            self._reader.feed_data(data)

    def eof_received(self) -> None:
        if self._reader:
            self._reader.feed_eof()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if self._reader:
            self._reader.feed_eof()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 17 — ORGAN ENTRYPOINT (bin/knowledge_daemon)
# ═══════════════════════════════════════════════════════════════════════════

class KnowledgeOrgan:
    """Top-level composition root importable as a single unit."""

    def __init__(self, config_path: Optional[str] = None, root_dir: Optional[str] = None) -> None:
        self.config = KnowledgeConfig.load(config_path)
        if root_dir:
            self.config.root_dir = Path(root_dir).resolve()
        self.kernel = KnowledgeKernel(self.config)
        self.dispatcher: Optional[QueryDispatcher] = None
        self.ipc_server: Optional[IPCServer] = None

    async def start(self) -> None:
        await self.kernel.initialize()
        self.dispatcher = QueryDispatcher(self.kernel)
        self.ipc_server = IPCServer(self.kernel, self.dispatcher)
        await self.ipc_server.start()
        log_event(logging.INFO, "organ_04_knowledge_started")

    async def stop(self) -> None:
        if self.ipc_server:
            await self.ipc_server.stop()
        await self.kernel.shutdown()
        log_event(logging.INFO, "organ_04_knowledge_stopped")

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start_cns(self, cns) -> None:
        """Connects this Knowledge organ to the central event bus."""
        self.cns = cns
        await self.cns.subscribe("KNOWLEDGE_QUERY", "organ_04_query", self._handle_cns_query)
        log_event(logging.INFO, "organ_04_knowledge_cns_connected")

    async def _handle_cns_query(self, env) -> None:
        payload = env.payload
        query = payload.get("query")
        req_id = payload.get("request_id")
        op_code = payload.get("op_code", QueryDispatcher.OP_SEARCH_KNOWLEDGE)
        
        if query and req_id:
            try:
                if self.dispatcher is None:
                    res = {"error": "dispatcher_not_initialized"}
                else:
                    res = await self.dispatcher.dispatch(op_code, payload)
            except Exception as e:
                res = {"error": str(e)}
                
            await self.cns.publish(env.__class__(
                topic="KNOWLEDGE_QUERY_RESULT",
                source_organ="organ_04",
                payload={"request_id": req_id, "result": res}
            ))

    async def run_forever(self) -> None:
        await self.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()


def main() -> None:
    organ = KnowledgeOrgan()
    try:
        asyncio.run(organ.run_forever())
    except KeyboardInterrupt:
        pass


# =============================================================================
# Logic Engine: Paradigm Analytics Engine
# =============================================================================
# Satisfies: Question 11 & 12 — Knowledge of 7 paradigms + automatic structured reporting
# Placement: Bottom of organ_04_knowledge.py (append-only, no existing code modified)

class ParadigmAnalyticsEngine:
    """Aggregates telemetry from all agents, categorizes it against the 7 established
    paradigms, and outputs normalized JSON datasets showing success/fail rates,
    time taken, and intelligence level used.
    
    The 7 paradigms:
        1. Parallel Web Automation
        2. Agent Chatroom
        3. Stochastic Consensus
        4. Verification Loop
        5. Video to Action
        6. Deterministic Lead Gen
        7. Research and Write
    """

    PARADIGMS = [
        "parallel_web_automation",
        "agent_chatroom",
        "stochastic_consensus",
        "verification_loop",
        "video_to_action",
        "deterministic_lead_gen",
        "research_and_write",
    ]

    def __init__(self):
        self._telemetry: list = []

    def ingest_agent_telemetry(self, agent_handle: str, paradigm: str,
                                 status: str, duration_ms: float,
                                 intelligence_level: str = "standard") -> None:
        """Record a single agent execution result."""
        import time as _time
        self._telemetry.append({
            "agent_handle": agent_handle,
            "paradigm": paradigm,
            "status": status,  # "success" | "failed" | "timeout"
            "duration_ms": duration_ms,
            "intelligence_level": intelligence_level,
            "timestamp": _time.time(),
        })

    def generate_paradigm_report(self) -> dict:
        """Generate a normalized JSON dataset grouped by paradigm."""
        report = {}
        for p in self.PARADIGMS:
            entries = [t for t in self._telemetry if t["paradigm"] == p]
            total = len(entries)
            successes = len([e for e in entries if e["status"] == "success"])
            failures = len([e for e in entries if e["status"] == "failed"])
            avg_duration = (sum(e["duration_ms"] for e in entries) / total) if total > 0 else 0
            report[p] = {
                "total_executions": total,
                "successes": successes,
                "failures": failures,
                "success_rate": round(successes / total, 4) if total > 0 else 0,
                "avg_duration_ms": round(avg_duration, 2),
                "intelligence_levels_used": list(set(e["intelligence_level"] for e in entries)),
            }
        return {
            "report_type": "paradigm_analytics",
            "total_telemetry_entries": len(self._telemetry),
            "paradigms": report,
        }

    def get_paradigm_description(self, paradigm_name: str) -> str:
        """Returns the functional description of a paradigm for agent knowledge injection."""
        descriptions = {
            "parallel_web_automation": "Execute multiple headless agents to scrape and automate web tasks simultaneously.",
            "agent_chatroom": "Collaborative environment where agents discuss and debate to reach a conclusion.",
            "stochastic_consensus": "Multiple models vote or sample different outputs to find the highest probability correct path.",
            "verification_loop": "Generate, verify, correct loop to ensure outputs meet specific constraints.",
            "video_to_action": "Process video feeds to determine immediate physical or UI interactions.",
            "deterministic_lead_gen": "Rule-based rigid extraction and qualification of sales or data leads.",
            "research_and_write": "Deep sequential search, summarize, and draft workflow.",
        }
        return descriptions.get(paradigm_name, "Unknown paradigm.")


if __name__ == "__main__":
    main()
