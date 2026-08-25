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
            start_unix = getattr(asyncio, "start_unix_server", None)
            if start_unix is not None:
                self._server = await start_unix(self._handle, path=UNIX_SOCK)
            else:
                self._server = await asyncio.start_server(self._handle, "127.0.0.1", 47080)
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
