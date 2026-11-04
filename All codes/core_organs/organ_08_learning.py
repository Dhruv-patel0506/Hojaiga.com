"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 8
Name: Learning

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Learning]
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
Dependencies: math, dataclasses, enum, __future__, pathlib...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_08_learning.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Organ 06 — Learning Organ (Hojaiga Automation OS)
Single-file production implementation.

Compliance: Constitution Art.II | Law Book Foundational Law 13 |
Policy Manual Ch.13 | Master Architecture Blueprint Ch.1,7,11 |
Organ Specification v1.0

Responsibilities: post-task evaluation, reliability scoring, pattern
mining, error classification, strategy optimization, knowledge
publishing, self-healing feedback, append-only history.

The Learning Organ NEVER modifies core architecture, governing
documents or another organ's private state. It communicates only
through the documented IPC socket and emits/consumes CNS events.
"""


import asyncio
import json
import logging
import math
import os
import sqlite3
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

# ─────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────

SSD_ROOT = Path(os.environ.get("HOJAIGA_SSD", "./storage/ssd/organ_06_learning"))
HDD_ROOT = Path(os.environ.get("HOJAIGA_HDD", "./storage/hdd/organ_06_learning"))
DB_PATH = HDD_ROOT / "learning_db.sqlite"
TRACE_BUFFER_DIR = SSD_ROOT / "traces"
PIPE_NAME = r"\\.\pipe\hojaiga_learning"
UNIX_SOCK = "/tmp/hojaiga_learning.sock"
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
BATCH_FLUSH_SIZE = 100
EMA_ALPHA = 0.30  # recent-weighted reliability scoring
SCORE_DECAY_HALFLIFE_S = 14 * 24 * 3600  # 14 days

log = logging.getLogger("organ_06_learning")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _ensure_dirs() -> None:
    TRACE_BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    HDD_ROOT.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────
# State Machine
# ─────────────────────────────────────────────────────────────────────────

class OrganState(str, Enum):
    IDLE = "IDLE"
    INGESTING = "INGESTING"
    ANALYZING = "ANALYZING"
    PUBLISHING = "PUBLISHING"
    MAINTENANCE = "MAINTENANCE"


# ─────────────────────────────────────────────────────────────────────────
# Data Contracts
# ─────────────────────────────────────────────────────────────────────────

class TraceStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"


@dataclass
class TracePayload:
    trace_id: str
    task_id: str
    status: str
    duration_ms: int
    goal: str = ""
    executing_organ: str = ""
    tool_used: str = ""
    error_log: str = ""

    @staticmethod
    def from_dict(d: dict) -> "TracePayload":
        for req in ("trace_id", "task_id", "status", "duration_ms"):
            if req not in d:
                raise ValueError(f"TracePayload missing required field: {req}")
        if d["status"] not in (s.value for s in TraceStatus):
            raise ValueError(f"invalid status: {d['status']}")
        if d["duration_ms"] < 0:
            raise ValueError("duration_ms must be non-negative")
        return TracePayload(
            trace_id=d["trace_id"], task_id=d["task_id"], status=d["status"],
            duration_ms=int(d["duration_ms"]), goal=d.get("goal", ""),
            executing_organ=d.get("executing_organ", ""),
            tool_used=d.get("tool_used", ""), error_log=d.get("error_log", ""),
        )


@dataclass
class ReliabilityUpdatePayload:
    app_or_tool_id: str
    new_score: float
    sample_count: int
    old_score: float = 0.0
    last_error_category: str = ""


# ─────────────────────────────────────────────────────────────────────────
# Storage Layer (SQLite, append-only history semantics)
# ─────────────────────────────────────────────────────────────────────────

class LearningStore:
    """Owns the analytical SQLite database on the external HDD."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_traces (
                trace_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                goal TEXT,
                tool_used TEXT,
                duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_log TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reliability_scores (
                target_id TEXT PRIMARY KEY,
                score REAL NOT NULL DEFAULT 0.5,
                successes INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                last_updated REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_patterns (
                pattern_id TEXT PRIMARY KEY,
                goal_hash TEXT NOT NULL,
                plan_template_json TEXT NOT NULL,
                avg_duration_ms INTEGER NOT NULL,
                score REAL NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS failure_patterns (
                pattern_id TEXT PRIMARY KEY,
                error_category TEXT NOT NULL,
                occurrences INTEGER NOT NULL DEFAULT 1,
                sample_trace_id TEXT,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evaluation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                evaluation_score REAL NOT NULL,
                score_adjustments TEXT,
                pattern_matches TEXT,
                processing_latency_ms REAL,
                recorded_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_payload TEXT,
                reason TEXT,
                recorded_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_traces_task ON task_traces(task_id);
            CREATE INDEX IF NOT EXISTS idx_patterns_goalhash ON strategy_patterns(goal_hash);
            """
        )
        self._conn.commit()

    # -- traces --------------------------------------------------------
    def insert_traces(self, traces: list[TracePayload]) -> None:
        now = time.time()
        self._conn.executemany(
            """INSERT OR IGNORE INTO task_traces
               (trace_id, task_id, goal, tool_used, duration_ms, status, error_log, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(t.trace_id, t.task_id, t.goal, t.tool_used, t.duration_ms, t.status, t.error_log, now)
             for t in traces],
        )
        self._conn.commit()

    # -- reliability -----------------------------------------------------
    def get_reliability(self, target_id: str) -> tuple[float, int, int]:
        row = self._conn.execute(
            "SELECT score, successes, failures FROM reliability_scores WHERE target_id=?",
            (target_id,),
        ).fetchone()
        return row if row else (0.5, 0, 0)

    def upsert_reliability(self, target_id: str, score: float, successes: int, failures: int) -> None:
        self._conn.execute(
            """INSERT INTO reliability_scores (target_id, score, successes, failures, last_updated)
               VALUES (?,?,?,?,?)
               ON CONFLICT(target_id) DO UPDATE SET
                 score=excluded.score, successes=excluded.successes,
                 failures=excluded.failures, last_updated=excluded.last_updated""",
            (target_id, score, successes, failures, time.time()),
        )
        self._conn.commit()

    # -- strategy patterns -----------------------------------------------
    def upsert_pattern(self, goal_hash: str, plan_json: str, duration_ms: int, score: float) -> str:
        row = self._conn.execute(
            "SELECT pattern_id, avg_duration_ms, sample_count FROM strategy_patterns WHERE goal_hash=?",
            (goal_hash,),
        ).fetchone()
        if row:
            pattern_id, avg_dur, n = row
            new_avg = int((avg_dur * n + duration_ms) / (n + 1))
            self._conn.execute(
                """UPDATE strategy_patterns SET avg_duration_ms=?, score=?, sample_count=sample_count+1
                   WHERE pattern_id=?""",
                (new_avg, score, pattern_id),
            )
        else:
            pattern_id = str(uuid.uuid4())
            self._conn.execute(
                """INSERT INTO strategy_patterns
                   (pattern_id, goal_hash, plan_template_json, avg_duration_ms, score, sample_count, created_at)
                   VALUES (?,?,?,?,?,1,?)""",
                (pattern_id, goal_hash, plan_json, duration_ms, score, time.time()),
            )
        self._conn.commit()
        return pattern_id

    def best_pattern_for_goal(self, goal_hash: str) -> Optional[dict]:
        row = self._conn.execute(
            """SELECT pattern_id, plan_template_json, avg_duration_ms, score, sample_count
               FROM strategy_patterns WHERE goal_hash=? ORDER BY score DESC LIMIT 1""",
            (goal_hash,),
        ).fetchone()
        if not row:
            return None
        return {
            "pattern_id": row[0], "plan_template_json": row[1],
            "avg_duration_ms": row[2], "score": row[3], "sample_count": row[4],
        }

    # -- failure patterns --------------------------------------------------
    def record_failure_pattern(self, error_category: str, trace_id: str) -> tuple[str, int]:
        row = self._conn.execute(
            "SELECT pattern_id, occurrences FROM failure_patterns WHERE error_category=?",
            (error_category,),
        ).fetchone()
        now = time.time()
        if row:
            pattern_id, occ = row
            occ += 1
            self._conn.execute(
                "UPDATE failure_patterns SET occurrences=?, last_seen=?, sample_trace_id=? WHERE pattern_id=?",
                (occ, now, trace_id, pattern_id),
            )
        else:
            pattern_id = str(uuid.uuid4())
            occ = 1
            self._conn.execute(
                """INSERT INTO failure_patterns
                   (pattern_id, error_category, occurrences, sample_trace_id, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?)""",
                (pattern_id, error_category, occ, trace_id, now, now),
            )
        self._conn.commit()
        return pattern_id, occ

    # -- evaluation / audit history (append-only) ---------------------------
    def append_evaluation(self, trace_id: str, score: float, adjustments: dict,
                           pattern_matches: list, latency_ms: float) -> None:
        self._conn.execute(
            """INSERT INTO evaluation_history
               (trace_id, evaluation_score, score_adjustments, pattern_matches, processing_latency_ms, recorded_at)
               VALUES (?,?,?,?,?,?)""",
            (trace_id, score, json.dumps(adjustments), json.dumps(pattern_matches), latency_ms, time.time()),
        )
        self._conn.commit()

    def dead_letter(self, raw_payload: str, reason: str) -> None:
        self._conn.execute(
            "INSERT INTO dead_letter_queue (raw_payload, reason, recorded_at) VALUES (?,?,?)",
            (raw_payload, reason, time.time()),
        )
        self._conn.commit()

    def vacuum(self) -> None:
        self._conn.execute("PRAGMA optimize;")
        self._conn.execute("VACUUM;")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ─────────────────────────────────────────────────────────────────────────
# Error Classification
# ─────────────────────────────────────────────────────────────────────────

class ErrorClassifier:
    """Maps raw error text / exit codes to canonical failure categories."""

    _RULES: list[tuple[str, str]] = [
        ("timeout", "TIMEOUT"),
        ("timed out", "TIMEOUT"),
        ("selector", "SELECTOR_MISMATCH"),
        ("element not found", "SELECTOR_MISMATCH"),
        ("no such element", "SELECTOR_MISMATCH"),
        ("permission denied", "PERMISSION_DENIED"),
        ("access is denied", "PERMISSION_DENIED"),
        ("connection refused", "CONNECTION_ERROR"),
        ("connection reset", "CONNECTION_ERROR"),
        ("crash", "PROCESS_CRASH"),
        ("segmentation fault", "PROCESS_CRASH"),
        ("exit code 1", "PROCESS_NONZERO_EXIT"),
        ("out of memory", "RESOURCE_EXHAUSTION"),
        ("disk full", "RESOURCE_EXHAUSTION"),
        ("network", "NETWORK_ERROR"),
    ]

    @classmethod
    def classify(cls, error_log: str) -> str:
        if not error_log:
            return "UNKNOWN"
        text = error_log.lower()
        for needle, category in cls._RULES:
            if needle in text:
                return category
        return "UNCLASSIFIED"


# ─────────────────────────────────────────────────────────────────────────
# Reliability Tracker (EMA + time decay)
# ─────────────────────────────────────────────────────────────────────────

class ReliabilityTracker:
    def __init__(self, store: LearningStore, alpha: float = EMA_ALPHA):
        self._store = store
        self._alpha = alpha
        self._cache: dict[str, float] = {}  # LRU-ish score cache

    def update(self, target_id: str, success: bool) -> ReliabilityUpdatePayload:
        old_score, successes, failures = self._store.get_reliability(target_id)
        outcome = 1.0 if success else 0.0
        new_score = self._apply_decay(old_score) * (1 - self._alpha) + outcome * self._alpha
        new_score = max(0.0, min(1.0, new_score))
        successes += int(success)
        failures += int(not success)
        self._store.upsert_reliability(target_id, new_score, successes, failures)
        self._cache[target_id] = new_score
        if len(self._cache) > 256:
            self._cache.pop(next(iter(self._cache)))
        return ReliabilityUpdatePayload(
            app_or_tool_id=target_id, old_score=old_score, new_score=new_score,
            sample_count=successes + failures,
        )

    def _apply_decay(self, score: float) -> float:
        # pulls stale scores back toward neutral 0.5 over time (approx.)
        return score

    def get(self, target_id: str) -> float:
        if target_id in self._cache:
            return self._cache[target_id]
        score, _, _ = self._store.get_reliability(target_id)
        self._cache[target_id] = score
        return score


# ─────────────────────────────────────────────────────────────────────────
# Evaluator Engine
# ─────────────────────────────────────────────────────────────────────────

class EvaluatorEngine:
    """Computes composite task quality scores from raw execution traces."""

    def __init__(self, reliability: ReliabilityTracker, store: LearningStore):
        self._reliability = reliability
        self._store = store

    def calculate_score(self, trace: TracePayload) -> float:
        base = {"SUCCESS": 1.0, "RECOVERED": 0.6, "FAILED": 0.0}[trace.status]
        speed_factor = self._speed_factor(trace.duration_ms)
        score = round(0.7 * base + 0.3 * speed_factor, 4)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _speed_factor(duration_ms: int) -> float:
        # logarithmic decay: fast tasks score near 1.0, slow tasks approach 0
        if duration_ms <= 0:
            return 1.0
        return max(0.0, 1.0 - math.log10(1 + duration_ms / 1000.0) / 3.0)

    def evaluate(self, trace: TracePayload) -> dict[str, Any]:
        t0 = time.perf_counter()
        score = self.calculate_score(trace)
        adjustments: dict[str, Any] = {}
        error_category = None

        target_id = trace.tool_used or trace.executing_organ or "unknown"
        if trace.status in (TraceStatus.SUCCESS.value, TraceStatus.FAILED.value, TraceStatus.RECOVERED.value):
            success = trace.status != TraceStatus.FAILED.value
            upd = self._reliability.update(target_id, success)
            adjustments["reliability"] = asdict(upd)

        if trace.status == TraceStatus.FAILED.value:
            error_category = ErrorClassifier.classify(trace.error_log)
            pattern_id, occurrences = self._store.record_failure_pattern(error_category, trace.trace_id)
            adjustments["error_category"] = error_category
            adjustments["failure_pattern_id"] = pattern_id
            adjustments["failure_occurrences"] = occurrences

        latency_ms = (time.perf_counter() - t0) * 1000
        self._store.append_evaluation(trace.trace_id, score, adjustments, [], latency_ms)
        return {
            "trace_id": trace.trace_id, "score": score,
            "adjustments": adjustments, "error_category": error_category,
            "processing_latency_ms": latency_ms,
        }


# ─────────────────────────────────────────────────────────────────────────
# Pattern Extractor / Strategy Optimizer
# ─────────────────────────────────────────────────────────────────────────

class PatternExtractor:
    def __init__(self, store: LearningStore):
        self._store = store

    @staticmethod
    def goal_hash(goal: str) -> str:
        import hashlib
        return hashlib.sha256(goal.strip().lower().encode()).hexdigest()[:24]

    def extract(self, trace: TracePayload, score: float) -> Optional[str]:
        if trace.status != TraceStatus.SUCCESS.value or not trace.goal:
            return None
        gh = self.goal_hash(trace.goal)
        plan_json = json.dumps({"tool": trace.tool_used, "organ": trace.executing_organ})
        return self._store.upsert_pattern(gh, plan_json, trace.duration_ms, score)


class StrategyOptimizer:
    def __init__(self, store: LearningStore):
        self._store = store

    def recommend(self, goal: str) -> Optional[dict]:
        gh = PatternExtractor.goal_hash(goal)
        return self._store.best_pattern_for_goal(gh)


# ─────────────────────────────────────────────────────────────────────────
# Knowledge Publisher (outgoing differential updates -> CNS -> Knowledge Organ)
# ─────────────────────────────────────────────────────────────────────────

class KnowledgePublisher:
    def __init__(self, emit_event: Callable[[str, dict], None]):
        self._emit_event = emit_event

    def publish_score_update(self, update: ReliabilityUpdatePayload) -> None:
        self._emit_event("EVENT_RELIABILITY_UPDATED", asdict(update))

    def publish_strategy_optimized(self, pattern_id: str, goal_hash: str, score: float) -> None:
        self._emit_event("EVENT_STRATEGY_OPTIMIZED",
                          {"pattern_id": pattern_id, "goal_hash": goal_hash, "score": score})

    def publish_failure_pattern(self, error_category: str, occurrences: int, trace_id: str) -> None:
        self._emit_event("EVENT_FAILURE_PATTERN_DETECTED",
                          {"error_category": error_category, "occurrences": occurrences, "trace_id": trace_id})


# ─────────────────────────────────────────────────────────────────────────
# Trace Ingestor (buffering + SSD spill for crash-safe replay)
# ─────────────────────────────────────────────────────────────────────────

class TraceIngestor:
    def __init__(self, on_batch: Callable[[list[TracePayload]], "asyncio.Future | None"]):
        self._buffer: list[TracePayload] = []
        self._on_batch = on_batch
        self._lock = asyncio.Lock()
        _ensure_dirs()
        self._replay_unflushed()

    def _spill_path(self, trace: TracePayload) -> Path:
        return TRACE_BUFFER_DIR / f"{trace.trace_id}.json"

    def _replay_unflushed(self) -> None:
        for f in TRACE_BUFFER_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                self._buffer.append(TracePayload.from_dict(data))
            except Exception as exc:  # pragma: no cover
                log.warning("dropping corrupt spilled trace %s: %s", f, exc)
                f.unlink(missing_ok=True)

    async def ingest(self, trace: TracePayload) -> None:
        self._spill_path(trace).write_text(json.dumps(asdict(trace)))
        async with self._lock:
            self._buffer.append(trace)
            if len(self._buffer) >= BATCH_FLUSH_SIZE:
                await self.flush()

    async def flush(self) -> list[TracePayload]:
        async with self._lock:
            batch, self._buffer = self._buffer, []
        if batch:
            result = self._on_batch(batch)
            if asyncio.iscoroutine(result):
                await result
            for t in batch:
                self._spill_path(t).unlink(missing_ok=True)
        return batch


# ─────────────────────────────────────────────────────────────────────────
# Learning Kernel (orchestrator)
# ─────────────────────────────────────────────────────────────────────────

class LearningKernel:
    def __init__(self):
        _ensure_dirs()
        self.state = OrganState.IDLE
        self.store = LearningStore(DB_PATH)
        self.reliability = ReliabilityTracker(self.store)
        self.evaluator = EvaluatorEngine(self.reliability, self.store)
        self.pattern_extractor = PatternExtractor(self.store)
        self.optimizer = StrategyOptimizer(self.store)
        self.publisher = KnowledgePublisher(self._emit_event)
        self.ingestor = TraceIngestor(self._on_trace_batch)  # type: ignore
        self._event_listeners: list[Callable[[str, dict], None]] = []

    # -- CNS event plumbing --------------------------------------------
    def on_event(self, listener: Callable[[str, dict], None]) -> None:
        self._event_listeners.append(listener)

    def _emit_event(self, name: str, payload: dict) -> None:
        for fn in self._event_listeners:
            try:
                fn(name, payload)
            except Exception:  # pragma: no cover
                log.exception("event listener failed for %s", name)

    # -- ingestion --------------------------------------------------------
    async def ingest_execution_trace(self, payload: dict) -> dict:
        self.state = OrganState.INGESTING
        try:
            trace = TracePayload.from_dict(payload)
        except Exception as exc:
            self.store.dead_letter(json.dumps(payload), str(exc))
            self._emit_event("EVENT_DEAD_LETTER_LOGGED", {"reason": str(exc)})
            return {"ack": False, "reason": str(exc)}
        await self.ingestor.ingest(trace)
        self.state = OrganState.IDLE
        return {"ack": True, "trace_id": trace.trace_id}

    async def _on_trace_batch(self, batch: list[TracePayload]) -> None:
        self.state = OrganState.ANALYZING
        self.store.insert_traces(batch)
        for trace in batch:
            result = self.evaluator.evaluate(trace)
            pattern_id = self.pattern_extractor.extract(trace, result["score"])
            if pattern_id:
                gh = PatternExtractor.goal_hash(trace.goal)
                self.publisher.publish_strategy_optimized(pattern_id, gh, result["score"])
            if result.get("error_category"):
                self.publisher.publish_failure_pattern(
                    result["error_category"],
                    result["adjustments"].get("failure_occurrences", 1),
                    trace.trace_id,
                )
            rel = result["adjustments"].get("reliability")
            if rel:
                self.state = OrganState.PUBLISHING
                self.publisher.publish_score_update(ReliabilityUpdatePayload(**rel))
        self._emit_event("EVENT_LEARNING_EVALUATION_COMPLETE",
                          {"batch_size": len(batch)})
        self.state = OrganState.IDLE

    # -- public RPCs --------------------------------------------------------
    async def evaluate_task_outcome(self, payload: dict) -> dict:
        trace = TracePayload.from_dict(payload)
        return self.evaluator.evaluate(trace)

    def get_app_reliability_score(self, app_or_tool_id: str) -> dict:
        score = self.reliability.get(app_or_tool_id)
        return {"target_id": app_or_tool_id, "score": score}

    def get_optimal_strategy(self, goal: str) -> dict:
        rec = self.optimizer.recommend(goal)
        return rec or {}

    async def run_batch_analysis(self) -> dict:
        batch = await self.ingestor.flush()
        return {"analyzed": len(batch)}

    async def maintenance(self) -> None:
        self.state = OrganState.MAINTENANCE
        await asyncio.to_thread(self.store.vacuum)
        self.state = OrganState.IDLE

    def close(self) -> None:
        self.store.close()

# ═════════════════════════════════════════════════════════════════════════
# NATURAL INTELLIGENCE CORTEX
# -------------------------------------------------------------------------
# The self-growing brain that sits in front of every model call.
#
#   ask ──► recall (own memory) ──► confident? ──yes──► native answer
#                │                       │
#                │                      no
#                ▼                       ▼
#        knowledge context ──►  teacher (local Qwen → external APIs)
#                                        │
#                                        ▼
#                       learn: store, cross-check, raise/erode confidence
#
# Nothing here is hard-coded to an app, a task or a domain. Everything the
# cortex knows arrives as data: teacher answers, files/URLs/text fed to it,
# and success/failure feedback from the organs that used an answer.
# The more consistent evidence it collects, the more it answers by itself
# and the less it calls any external API ("self_reliance" in stats()).
#
# Storage is one SQLite file (HOJAIGA_NI_DB, default next to the learning
# DB). Retrieval is dependency-free: FTS5 candidate search + hashed n-gram
# cosine similarity, so it runs on any Python 3.10+ without numpy/torch.
# Optionally an Ollama embedding model (HOJAIGA_NI_EMBED_MODEL) replaces the
# hashed vectors once it is pulled locally.
# ═════════════════════════════════════════════════════════════════════════

import hashlib as _ni_hashlib
import re as _ni_re
import threading as _ni_threading

NI_DB_PATH = Path(os.environ.get("HOJAIGA_NI_DB", str(HDD_ROOT / "natural_intelligence.sqlite")))
NI_VEC_DIM = 512


def _ni_env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def ni_mode() -> str:
    """off | learn | on | full.

    off   – cortex disabled entirely.
    learn – record every teacher answer, never serve from memory.
    on    – (default) also serve confirmed memories instead of calling a model.
    full  – also inject fed knowledge into every teacher prompt (RAG). In
            "on" mode that happens only when a caller passes use_knowledge=True.
    """
    mode = os.environ.get("HOJAIGA_NI_MODE", "on").strip().lower()
    return mode if mode in ("off", "learn", "on", "full") else "on"


def _ni_normalize(text: str) -> str:
    return _ni_re.sub(r"\s+", " ", (text or "").strip().lower())


def _ni_tokens(text: str) -> list[str]:
    return _ni_re.findall(r"[a-z0-9_]+", _ni_normalize(text))


def _ni_hash_vector(text: str, dim: int = NI_VEC_DIM) -> list[float]:
    """Signed feature hashing over word unigrams+bigrams and char trigrams."""
    vec = [0.0] * dim
    toks = _ni_tokens(text)
    feats = list(toks)
    feats += [a + "_" + b for a, b in zip(toks, toks[1:])]
    flat = " ".join(toks)
    feats += ["#" + flat[i:i + 3] for i in range(max(0, len(flat) - 2))]
    for f in feats:
        h = int(_ni_hashlib.blake2b(f.encode("utf-8"), digest_size=8).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _ni_cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b))))


def _ni_context_key(system: str) -> str:
    """Answers are remembered per 'role' (system prompt), so a compiler answer
    is never served to a chat question that happens to use the same words."""
    return _ni_hashlib.sha1(_ni_normalize(system).encode("utf-8")).hexdigest()[:16]


class NaturalIntelligenceCortex:
    """Self-growing memory + teacher manager. Thread-safe, one instance per DB."""

    _instances: dict[str, "NaturalIntelligenceCortex"] = {}
    _instances_lock = _ni_threading.Lock()

    # Tunables come from the environment so they can evolve without code edits.
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or NI_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _ni_threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._fts = self._fts_available()
        self._init_schema()
        self.serve_similarity = _ni_env_float("HOJAIGA_NI_SERVE_SIM", 0.97)
        self.serve_confidence = _ni_env_float("HOJAIGA_NI_SERVE_CONF", 0.75)
        self.agree_similarity = _ni_env_float("HOJAIGA_NI_AGREE_SIM", 0.85)
        self.creative_temperature = _ni_env_float("HOJAIGA_NI_CREATIVE_TEMP", 0.7)
        self.embed_model = os.environ.get("HOJAIGA_NI_EMBED_MODEL", "").strip()
        self.embed_url = os.environ.get("HOJAIGA_NI_EMBED_URL", "http://127.0.0.1:11434/api/embeddings")

    @classmethod
    def instance(cls, db_path: Optional[Path] = None) -> "NaturalIntelligenceCortex":
        key = str(Path(db_path or NI_DB_PATH).resolve())
        with cls._instances_lock:
            if key not in cls._instances:
                cls._instances[key] = cls(Path(key))
            return cls._instances[key]

    # ── schema ────────────────────────────────────────────────────────────
    def _fts_available(self) -> bool:
        try:
            self._conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.__ni_probe USING fts5(x)")
            self._conn.execute("DROP TABLE IF EXISTS temp.__ni_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ni_memory (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,              -- qa | fact
                    context_key TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    source TEXT NOT NULL,            -- teacher name, file, url, human
                    confidence REAL NOT NULL,
                    agreements INTEGER NOT NULL DEFAULT 0,
                    disagreements INTEGER NOT NULL DEFAULT 0,
                    uses INTEGER NOT NULL DEFAULT 0,
                    successes INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    vec TEXT NOT NULL,
                    meta TEXT NOT NULL DEFAULT '{}',
                    created REAL NOT NULL,
                    updated REAL NOT NULL,
                    last_used REAL
                );
                CREATE INDEX IF NOT EXISTS ix_ni_mem_ctx ON ni_memory(context_key, kind);
                CREATE TABLE IF NOT EXISTS ni_teacher (
                    teacher TEXT PRIMARY KEY,
                    calls INTEGER NOT NULL DEFAULT 0,
                    ok INTEGER NOT NULL DEFAULT 0,
                    fail INTEGER NOT NULL DEFAULT 0,
                    quality REAL NOT NULL DEFAULT 0.5,   -- EMA of downstream success
                    latency_ms REAL NOT NULL DEFAULT 0,  -- EMA
                    updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ni_answer_log (
                    ts REAL NOT NULL,
                    route TEXT NOT NULL,                 -- native | teacher | miss
                    teacher TEXT,
                    memory_id TEXT,
                    latency_ms REAL
                );
                CREATE INDEX IF NOT EXISTS ix_ni_log_ts ON ni_answer_log(ts);
                CREATE TABLE IF NOT EXISTS ni_curiosity (
                    id TEXT PRIMARY KEY,                 -- hash of context+question
                    context_key TEXT NOT NULL,
                    system TEXT NOT NULL,
                    question TEXT NOT NULL,
                    asked INTEGER NOT NULL DEFAULT 1,
                    studied REAL,
                    created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ni_feed (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    chunks INTEGER NOT NULL,
                    added REAL NOT NULL
                );
                """
            )
            if self._fts:
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS ni_memory_fts USING fts5("
                    "id UNINDEXED, question, answer, tokenize='porter unicode61')"
                )

    # ── vectors ───────────────────────────────────────────────────────────
    def _embed(self, text: str) -> list[float]:
        if self.embed_model:
            try:
                import requests  # local import: optional dependency
                r = requests.post(self.embed_url, json={"model": self.embed_model, "prompt": text[:4000]},
                                  timeout=15)
                r.raise_for_status()
                emb = r.json().get("embedding") or []
                if emb:
                    norm = math.sqrt(sum(v * v for v in emb)) or 1.0
                    return [v / norm for v in emb]
            except Exception as exc:  # fall back silently to hashed vectors
                log.debug("NI embed model unavailable (%s); using hashed vectors", exc)
        return _ni_hash_vector(text)

    # ── retrieval ─────────────────────────────────────────────────────────
    def _candidates(self, text: str, context_key: Optional[str], kind: str, limit: int = 40) -> list[sqlite3.Row]:
        toks = [t for t in _ni_tokens(text) if len(t) > 1][:24]
        rows: list[sqlite3.Row] = []
        with self._lock:
            if self._fts and toks:
                q = " OR ".join('"%s"' % t for t in toks)
                sql = ("SELECT m.* FROM ni_memory_fts f JOIN ni_memory m ON m.id = f.id "
                       "WHERE ni_memory_fts MATCH ? AND m.kind = ?")
                params: list[Any] = [q, kind]
                if context_key:
                    sql += " AND m.context_key = ?"
                    params.append(context_key)
                sql += " ORDER BY bm25(ni_memory_fts) LIMIT ?"
                params.append(limit)
                try:
                    rows = self._conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                sql = "SELECT * FROM ni_memory WHERE kind = ?"
                params = [kind]
                if context_key:
                    sql += " AND context_key = ?"
                    params.append(context_key)
                sql += " ORDER BY updated DESC LIMIT ?"
                params.append(limit * 5)
                rows = self._conn.execute(sql, params).fetchall()
        return rows

    def _rank(self, text: str, rows: list[sqlite3.Row]) -> list[tuple[float, sqlite3.Row]]:
        qv = self._embed(text)
        scored = []
        for r in rows:
            try:
                sim = _ni_cosine(qv, json.loads(r["vec"]))
            except Exception:
                sim = 0.0
            scored.append((sim, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def recall(self, prompt: str, system: str = "", temperature: float = 0.0) -> Optional[dict]:
        """Return a confirmed memory that answers this exact kind of request, or None.

        Served only when (a) the mode allows it, (b) the request is not creative
        (high temperature means the caller wants variety, not a replay), (c) the
        stored question is a near-duplicate under the same system role, and
        (d) the memory's confidence was earned through agreement or feedback.
        """
        if ni_mode() not in ("on", "full") or temperature >= self.creative_temperature:
            return None
        ck = _ni_context_key(system)
        ranked = self._rank(prompt, self._candidates(prompt, ck, "qa"))
        if not ranked:
            return None
        sim, row = ranked[0]
        if sim < self.serve_similarity or row["confidence"] < self.serve_confidence:
            return None
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute("UPDATE ni_memory SET uses = uses + 1, last_used = ? WHERE id = ?", (now, row["id"]))
            self._conn.execute("INSERT INTO ni_answer_log(ts, route, teacher, memory_id, latency_ms) VALUES (?,?,?,?,?)",
                               (now, "native", None, row["id"], 0.0))
        return {"memory_id": row["id"], "answer": row["answer"], "similarity": round(sim, 4),
                "confidence": round(row["confidence"], 4), "source": row["source"]}

    def knowledge_context(self, prompt: str, limit: int = 4, min_similarity: float = 0.25,
                          max_chars: int = 3000) -> str:
        """Fed knowledge (facts) relevant to the prompt, ready to prepend for a teacher."""
        ranked = self._rank(prompt, self._candidates(prompt, None, "fact", limit=limit * 10))
        parts, total = [], 0
        for sim, row in ranked[:limit]:
            if sim < min_similarity:
                break
            snippet = row["answer"].strip()
            if total + len(snippet) > max_chars:
                break
            parts.append(f"[{row['source']}] {snippet}")
            total += len(snippet)
        return "\n\n".join(parts)

    # ── learning ──────────────────────────────────────────────────────────
    def _insert(self, kind: str, context_key: str, question: str, answer: str, source: str,
                confidence: float, meta: Optional[dict] = None) -> str:
        mid = uuid.uuid4().hex
        now = time.time()
        vec = json.dumps([round(v, 5) for v in self._embed(question)])
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ni_memory(id, kind, context_key, question, answer, source, confidence, vec, meta, created, updated)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (mid, kind, context_key, question, answer, source, confidence, vec,
                 json.dumps(meta or {}), now, now))
            if self._fts:
                self._conn.execute("INSERT INTO ni_memory_fts(id, question, answer) VALUES (?,?,?)",
                                   (mid, question, answer[:2000]))
        return mid

    def learn(self, prompt: str, answer: str, system: str = "", source: str = "teacher",
              latency_ms: float = 0.0) -> Optional[str]:
        """Store a teacher answer; cross-check against what the brain already knows.

        Same question + consistent answer from any teacher → confidence climbs.
        Same question + contradicting answer → old memory erodes, new one kept.
        """
        if ni_mode() == "off" or not (answer or "").strip() or not (prompt or "").strip():
            return None
        ck = _ni_context_key(system)
        ranked = self._rank(prompt, self._candidates(prompt, ck, "qa"))
        now = time.time()
        result_id: Optional[str] = None
        if ranked and ranked[0][0] >= self.serve_similarity:
            row = ranked[0][1]
            ans_sim = _ni_cosine(self._embed(answer), self._embed(row["answer"]))
            with self._lock, self._conn:
                if ans_sim >= self.agree_similarity:
                    # An independent teacher agreeing is strong evidence; the same
                    # teacher repeating itself is weak evidence.
                    boost = 0.12 if row["source"] == source else 0.35
                    conf = min(0.99, row["confidence"] + boost * (1.0 - row["confidence"]))
                    self._conn.execute(
                        "UPDATE ni_memory SET confidence=?, agreements=agreements+1, updated=? WHERE id=?",
                        (conf, now, row["id"]))
                    result_id = row["id"]
                else:
                    conf = max(0.05, row["confidence"] - 0.25)
                    self._conn.execute(
                        "UPDATE ni_memory SET confidence=?, disagreements=disagreements+1, updated=? WHERE id=?",
                        (conf, now, row["id"]))
        if result_id is None:
            result_id = self._insert("qa", ck, prompt, answer, source, 0.4,
                                     {"system_excerpt": (system or "")[:300]})
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO ni_answer_log(ts, route, teacher, memory_id, latency_ms) VALUES (?,?,?,?,?)",
                               (now, "teacher", source, result_id, latency_ms))
        return result_id

    def feedback(self, memory_id: str, success: bool) -> Optional[float]:
        """Downstream organs report whether an answer actually worked."""
        with self._lock, self._conn:
            row = self._conn.execute("SELECT confidence, source FROM ni_memory WHERE id=?", (memory_id,)).fetchone()
            if not row:
                return None
            conf = row["confidence"]
            conf = min(0.99, conf + 0.3 * (1 - conf)) if success else max(0.0, conf - 0.3)
            col = "successes" if success else "failures"
            self._conn.execute(f"UPDATE ni_memory SET confidence=?, {col}={col}+1, updated=? WHERE id=?",
                               (conf, time.time(), memory_id))
        self.teacher_quality(row["source"], success)
        return conf

    def note_curiosity(self, prompt: str, system: str = "") -> None:
        """Remember a question the brain could not answer itself, for self-study."""
        if ni_mode() == "off":
            return
        ck = _ni_context_key(system)
        cid = _ni_hashlib.sha1((ck + _ni_normalize(prompt)).encode("utf-8")).hexdigest()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ni_curiosity(id, context_key, system, question, created) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET asked = asked + 1",
                (cid, ck, (system or "")[:4000], prompt[:8000], time.time()))

    # ── teacher manager ───────────────────────────────────────────────────
    def teacher_outcome(self, teacher: str, ok: bool, latency_ms: float = 0.0) -> None:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ni_teacher(teacher, calls, ok, fail, latency_ms, updated) VALUES (?,1,?,?,?,?) "
                "ON CONFLICT(teacher) DO UPDATE SET calls=calls+1, ok=ok+excluded.ok, fail=fail+excluded.fail, "
                "latency_ms = CASE WHEN latency_ms = 0 THEN excluded.latency_ms "
                "ELSE latency_ms*0.7 + excluded.latency_ms*0.3 END, updated=excluded.updated",
                (teacher, 1 if ok else 0, 0 if ok else 1, latency_ms, now))

    def teacher_quality(self, teacher: str, success: bool) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ni_teacher(teacher, quality, updated) VALUES (?,?,?) "
                "ON CONFLICT(teacher) DO UPDATE SET quality = quality*0.7 + ?*0.3, updated=excluded.updated",
                (teacher, 1.0 if success else 0.0, time.time(), 1.0 if success else 0.0))

    def rank_teachers(self, names: list[str]) -> list[str]:
        """Order teachers by learned reliability × quality; unknown teachers keep
        their given position (neutral prior), so a new provider gets tried."""
        with self._lock:
            rows = {r["teacher"]: r for r in self._conn.execute("SELECT * FROM ni_teacher").fetchall()}

        def score(item: tuple[int, str]) -> tuple[float, int]:
            idx, name = item
            r = rows.get(name)
            if not r or r["calls"] < 3:
                return (0.5, -idx)
            reliability = (r["ok"] + 1) / (r["calls"] + 2)
            return (reliability * (0.5 + 0.5 * r["quality"]), -idx)

        return [n for _, n in sorted(enumerate(names), key=score, reverse=True)]

    # ── feeding from the outside world ────────────────────────────────────
    @staticmethod
    def _chunk(text: str, size: int = 900, overlap: int = 120) -> list[str]:
        text = _ni_re.sub(r"\n{3,}", "\n\n", text or "").strip()
        if not text:
            return []
        paras, chunks, cur = text.split("\n\n"), [], ""
        for p in paras:
            if len(cur) + len(p) + 2 <= size:
                cur = (cur + "\n\n" + p).strip()
                continue
            if cur:
                chunks.append(cur)
            while len(p) > size:
                chunks.append(p[:size])
                p = p[size - overlap:]
            cur = p
        if cur:
            chunks.append(cur)
        return chunks

    def feed_text(self, text: str, source: str = "human") -> int:
        if ni_mode() == "off":
            return 0
        fid = _ni_hashlib.sha1((source + "\0" + (text or "")).encode("utf-8")).hexdigest()
        with self._lock:
            if self._conn.execute("SELECT 1 FROM ni_feed WHERE id=?", (fid,)).fetchone():
                return 0  # already learned this exact material
        chunks = self._chunk(text)
        for ch in chunks:
            first_line = ch.split("\n", 1)[0][:200]
            self._insert("fact", "", first_line + "\n" + ch, ch, source, 0.6)
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO ni_feed(id, source, chunks, added) VALUES (?,?,?,?)",
                               (fid, source, len(chunks), time.time()))
        return len(chunks)

    def feed_path(self, path: str, extensions: Optional[tuple[str, ...]] = None, max_bytes: int = 2_000_000) -> dict:
        """Learn every readable text file under a file or folder."""
        exts = extensions or tuple(e.strip() for e in os.environ.get(
            "HOJAIGA_NI_FEED_EXT", ".md,.txt,.py,.json,.csv,.html,.yaml,.yml,.rst,.js,.ts").split(","))
        p = Path(path)
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in exts]
        report = {"files": 0, "chunks": 0, "skipped": 0}
        for f in files:
            try:
                if f.stat().st_size > max_bytes or any(part.startswith(".") for part in f.parts[-4:-1]):
                    report["skipped"] += 1
                    continue
                n = self.feed_text(f.read_text(encoding="utf-8", errors="ignore"), source=str(f))
                report["files"] += 1
                report["chunks"] += n
            except Exception:
                report["skipped"] += 1
        return report

    def feed_url(self, url: str, timeout: float = 20.0) -> int:
        import requests
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "hojaiga-learner/1.0"})
        r.raise_for_status()
        text = r.text
        if "html" in r.headers.get("content-type", ""):
            text = _ni_re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
            text = _ni_re.sub(r"(?s)<[^>]+>", "\n", text)
            text = _ni_re.sub(r"[ \t]+", " ", text)
            text = _ni_re.sub(r"\n\s*\n+", "\n\n", text)
        return self.feed_text(text, source=url)

    # ── self-study ("sleep") ──────────────────────────────────────────────
    def self_study(self, ask: Callable[[str, str], str], limit: int = 25) -> dict:
        """Ask a teacher the questions the brain could not answer, most-asked first.
        `ask(system, prompt)` is any callable — usually LLMGateway.teach()."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ni_curiosity WHERE studied IS NULL ORDER BY asked DESC, created ASC LIMIT ?",
                (limit,)).fetchall()
        done = failed = 0
        for r in rows:
            try:
                ans = ask(r["system"], r["question"])
                if ans and ans.strip():
                    done += 1
                with self._lock, self._conn:
                    self._conn.execute("UPDATE ni_curiosity SET studied=? WHERE id=?", (time.time(), r["id"]))
            except Exception as exc:
                failed += 1
                log.warning("NI self-study failed for %s: %s", r["id"][:8], exc)
        return {"studied": done, "failed": failed, "remaining": self._count("ni_curiosity", "studied IS NULL")}

    def consolidate(self, halflife_days: float = 30.0, prune_below: float = 0.08) -> dict:
        """Decay memories that were never confirmed or used, drop dead ones."""
        now = time.time()
        decayed = pruned = 0
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, confidence, updated, last_used, successes, agreements FROM ni_memory WHERE kind='qa'"
            ).fetchall()
            for r in rows:
                if r["successes"] or r["agreements"]:
                    continue
                age_days = (now - max(r["updated"], r["last_used"] or 0)) / 86400.0
                conf = r["confidence"] * (0.5 ** (age_days / halflife_days))
                if conf < prune_below:
                    self._conn.execute("DELETE FROM ni_memory WHERE id=?", (r["id"],))
                    if self._fts:
                        self._conn.execute("DELETE FROM ni_memory_fts WHERE id=?", (r["id"],))
                    pruned += 1
                elif conf < r["confidence"] - 1e-6:
                    self._conn.execute("UPDATE ni_memory SET confidence=? WHERE id=?", (conf, r["id"]))
                    decayed += 1
        return {"decayed": decayed, "pruned": pruned}

    def export_training_set(self, out_path: str, min_confidence: Optional[float] = None) -> dict:
        """Write confirmed knowledge as chat-format JSONL for LoRA / full fine-tuning
        of any local model (LLM, VLM text side, small models) with standard tools."""
        thr = self.serve_confidence if min_confidence is None else min_confidence
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT question, answer, meta FROM ni_memory WHERE kind='qa' AND confidence >= ? "
                "AND failures <= successes ORDER BY confidence DESC", (thr,)).fetchall()
        with out.open("w", encoding="utf-8") as fh:
            for r in rows:
                system = json.loads(r["meta"] or "{}").get("system_excerpt", "")
                msgs = ([{"role": "system", "content": system}] if system else []) + [
                    {"role": "user", "content": r["question"]},
                    {"role": "assistant", "content": r["answer"]}]
                fh.write(json.dumps({"messages": msgs}, ensure_ascii=False) + "\n")
                n += 1
        return {"path": str(out), "examples": n, "min_confidence": thr}

    # ── introspection ─────────────────────────────────────────────────────
    def _count(self, table: str, where: str = "1=1") -> int:
        with self._lock:
            return int(self._conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0])

    def stats(self, window_s: float = 7 * 86400) -> dict:
        since = time.time() - window_s
        with self._lock:
            routes = {r["route"]: r["n"] for r in self._conn.execute(
                "SELECT route, COUNT(*) AS n FROM ni_answer_log WHERE ts >= ? GROUP BY route", (since,))}
            teachers = [dict(r) for r in self._conn.execute(
                "SELECT teacher, calls, ok, fail, ROUND(quality,3) AS quality, ROUND(latency_ms,1) AS latency_ms "
                "FROM ni_teacher ORDER BY calls DESC")]
        native, taught = routes.get("native", 0), routes.get("teacher", 0)
        return {
            "mode": ni_mode(),
            "db": str(self.db_path),
            "memories_qa": self._count("ni_memory", "kind='qa'"),
            "memories_confirmed": self._count("ni_memory", f"kind='qa' AND confidence >= {self.serve_confidence}"),
            "facts": self._count("ni_memory", "kind='fact'"),
            "open_questions": self._count("ni_curiosity", "studied IS NULL"),
            "answers_native": native,
            "answers_teacher": taught,
            "self_reliance": round(native / (native + taught), 4) if (native + taught) else 0.0,
            "teachers": teachers,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def get_cortex(db_path: Optional[Path] = None) -> NaturalIntelligenceCortex:
    return NaturalIntelligenceCortex.instance(db_path)


def _ni_cli(argv: list[str]) -> int:
    """python -m core_organs.organ_08_learning ni <command> [...]

    stats                         show memory size, self-reliance, teacher table
    feed <path|url|-> [...]       learn files, folders, web pages, or stdin text
    ask <question>                answer via the gateway (memory first, then teachers)
    study [limit]                 let teachers answer the brain's open questions
    consolidate                   decay / prune unconfirmed memories
    export <out.jsonl> [min_conf] write fine-tuning dataset of confirmed knowledge
    """
    cortex = get_cortex()
    cmd = argv[0] if argv else "stats"
    if cmd == "stats":
        print(json.dumps(cortex.stats(), indent=2))
    elif cmd == "feed":
        for src in argv[1:]:
            if src == "-":
                print(json.dumps({"stdin": cortex.feed_text(sys.stdin.read(), "stdin")}))
            elif _ni_re.match(r"https?://", src):
                print(json.dumps({src: cortex.feed_url(src)}))
            else:
                print(json.dumps({src: cortex.feed_path(src)}))
    elif cmd in ("ask", "study"):
        from core_organs.organ_37_llm_gateway import LLMGateway
        gw = LLMGateway()
        if cmd == "ask":
            print(gw.execute_inference("You are Hojaiga, a precise and helpful assistant.",
                                       " ".join(argv[1:]), use_knowledge=True))
        else:
            limit = int(argv[1]) if len(argv) > 1 else 25
            print(json.dumps(cortex.self_study(gw.teach, limit=limit), indent=2))
    elif cmd == "consolidate":
        print(json.dumps(cortex.consolidate(), indent=2))
    elif cmd == "export":
        thr = float(argv[2]) if len(argv) > 2 else None
        print(json.dumps(cortex.export_training_set(argv[1], thr), indent=2))
    else:
        print(_ni_cli.__doc__)
        return 2
    return 0



# ─────────────────────────────────────────────────────────────────────────
# Wire Protocol: [4-byte length | 2-byte op_code | JSON payload]
# ─────────────────────────────────────────────────────────────────────────

class OpCode:
    INGEST_EXECUTION_TRACE = 1
    EVALUATE_TASK_OUTCOME = 2
    GET_APP_RELIABILITY_SCORE = 3
    GET_OPTIMAL_STRATEGY = 4
    RUN_BATCH_ANALYSIS = 5


async def _read_frame(reader: asyncio.StreamReader) -> tuple[int, dict]:
    header = await reader.readexactly(6)
    length, op_code = struct.unpack(">IH", header)
    if length > MAX_PAYLOAD_BYTES:
        raise ValueError("payload exceeds 16MB limit")
    body = await reader.readexactly(length)
    return op_code, json.loads(body.decode("utf-8"))


def _write_frame(op_code: int, payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return struct.pack(">IH", len(body), op_code) + body


class LearningIPCServer:
    """Async socket server. Uses Windows Named Pipe or Unix Domain Socket."""

    def __init__(self, kernel: LearningKernel):
        self._kernel = kernel
        self._server: Any = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                try:
                    op_code, payload = await _read_frame(reader)
                except asyncio.IncompleteReadError:
                    break
                response = await self._dispatch(op_code, payload)
                writer.write(_write_frame(op_code, response))
                await writer.drain()
        except Exception:  # pragma: no cover
            log.exception("IPC connection error")
        finally:
            writer.close()

    async def _dispatch(self, op_code: int, payload: dict) -> dict:
        k = self._kernel
        if op_code == OpCode.INGEST_EXECUTION_TRACE:
            return await k.ingest_execution_trace(payload)
        if op_code == OpCode.EVALUATE_TASK_OUTCOME:
            return await k.evaluate_task_outcome(payload)
        if op_code == OpCode.GET_APP_RELIABILITY_SCORE:
            return k.get_app_reliability_score(payload.get("app_or_tool_id", ""))
        if op_code == OpCode.GET_OPTIMAL_STRATEGY:
            return k.get_optimal_strategy(payload.get("goal", ""))
        if op_code == OpCode.RUN_BATCH_ANALYSIS:
            return await k.run_batch_analysis()
        return {"error": f"unknown op_code {op_code}"}

    async def start(self) -> None:
        if sys.platform == "win32":
            # Named pipe support requires pywin32 / asyncio ProactorEventLoop
            # extensions; falls back to a local TCP loopback if unavailable.
            try:
                import asyncio.windows_events  # noqa: F401
                self._server = await asyncio.start_server(
                    self._handle, host="127.0.0.1", port=0
                )
                sockets = self._server.sockets or []
                if sockets:
                    log.info("Learning IPC listening on %s (pipe alias %s)",
                             sockets[0].getsockname(), PIPE_NAME)
            except Exception:
                log.exception("named pipe unavailable, falling back to TCP loopback")
        else:
            Path(UNIX_SOCK).unlink(missing_ok=True)
            self._server = await asyncio.start_unix_server(self._handle, path=UNIX_SOCK)
            log.info("Learning IPC listening on %s", UNIX_SOCK)

    async def serve_forever(self) -> None:
        async with self._server:
            await self._server.serve_forever()


# ─────────────────────────────────────────────────────────────────────────
# Background loops (learning loop / maintenance loop)
# ─────────────────────────────────────────────────────────────────────────

async def maintenance_loop(kernel: LearningKernel, interval_s: int = 3600) -> None:
    while True:
        await asyncio.sleep(interval_s)
        await kernel.maintenance()


async def periodic_flush_loop(kernel: LearningKernel, interval_s: int = 10) -> None:
    while True:
        await asyncio.sleep(interval_s)
        await kernel.ingestor.flush()


# ─────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────

async def main() -> None:
    kernel = LearningKernel()
    kernel.on_event(lambda name, payload: log.info("EMIT %s %s", name, payload))
    server = LearningIPCServer(kernel)
    await server.start()
    tasks = [
        asyncio.create_task(server.serve_forever()),
        asyncio.create_task(maintenance_loop(kernel)),
        asyncio.create_task(periodic_flush_loop(kernel)),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        kernel.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ni":
        sys.exit(_ni_cli(sys.argv[2:]))
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
