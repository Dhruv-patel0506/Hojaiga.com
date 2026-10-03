"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: task_scheduler.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [task_scheduler.py]
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
Dependencies: random, enum, typing, __future__, collections...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: task_scheduler.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Task Scheduler Organ
Organ ID: ORGAN-34-TASK-SCHEDULER
Spec: SPEC-AOS-SCHED-001
Authority: Constitution > LawBook > Diagrams > Policy Manual > Master Blueprint > Organ Spec

PRE-CODE DIAGRAM (data flow):

    Brain --Task Request--> TaskScheduler.submit_task
        -> TaskValidator (schema/security/dup) -> TaskRegistry.register
        -> StateManager(CREATED->VALIDATED->QUEUED) -> QueueManager.enqueue
        -> PriorityManager (score/aging) -> DependencyResolver (DAG ready?)
        -> DispatchManager (worker allocation, concurrency, resource check)
        -> [emit dispatch event on DispatchSocket] -> External Resource Manager/Automation Engine
    Completion Event -> StateManager transition -> RetryManager (on failure) -> HistoryManager (on terminal)
        -> MetricsManager (always) -> Brain (status/result)

ACTUAL-CODE DIAGRAM (module composition, single file):

    TaskScheduler (facade / ITaskScheduler)
      ├── TaskRegistry           (task store, locking)
      ├── StateManager           (legal transitions, WAL)
      ├── QueueManager           (priority heap + fifo)
      ├── PriorityManager        (scoring + aging)
      ├── DependencyResolver     (DAG, cycle detection)
      ├── DispatchManager        (worker pool, concurrency gate)
      ├── TimeoutManager         (deadline watchdog)
      ├── RetryManager           (exponential backoff)
      ├── RecoveryManager        (failure handling, WAL replay)
      ├── HistoryManager         (append-only archive)
      ├── MetricsManager         (counters)
      └── SocketBus / Pipeline   (in-process pub/sub contract)

This organ never executes automation logic itself; it only plans, orders,
and dispatches through documented sockets/pipelines (Universal Law 3, 5).
"""


import asyncio
import heapq
import itertools
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

logger = logging.getLogger("hojaiga.task_scheduler")

# ═══════════════════════════════════════════════════════════════════
# Chapter 1 — Contracts (Task Registry, DTO, State Machine)
# ═══════════════════════════════════════════════════════════════════

MAX_QUEUE_CAPACITY = 100_000
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_CONCURRENCY = 8  # CPU-first, GPU reserved for Brain


class TaskState(Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    WAITING = "WAITING"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    COMPLETED = "COMPLETED"
    RETRY = "RETRY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RECOVERY = "RECOVERY"
    ARCHIVED = "ARCHIVED"


LEGAL_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.CREATED: {TaskState.VALIDATED, TaskState.FAILED},
    TaskState.VALIDATED: {TaskState.QUEUED},
    TaskState.QUEUED: {TaskState.WAITING, TaskState.CANCELLED},
    TaskState.WAITING: {TaskState.SCHEDULED, TaskState.CANCELLED},
    TaskState.SCHEDULED: {TaskState.RUNNING, TaskState.WAITING, TaskState.CANCELLED},
    TaskState.RUNNING: {
        TaskState.COMPLETED, TaskState.RETRY, TaskState.TIMEOUT,
        TaskState.CANCELLED, TaskState.PAUSED, TaskState.EMERGENCY_STOP,
    },
    TaskState.PAUSED: {TaskState.RESUMED, TaskState.CANCELLED},
    TaskState.RESUMED: {TaskState.RUNNING},
    TaskState.RETRY: {TaskState.QUEUED, TaskState.FAILED},
    TaskState.TIMEOUT: {TaskState.RETRY, TaskState.FAILED},
    TaskState.EMERGENCY_STOP: {TaskState.RECOVERY},
    TaskState.FAILED: {TaskState.RECOVERY, TaskState.ARCHIVED},
    TaskState.RECOVERY: {TaskState.ARCHIVED, TaskState.QUEUED},
    TaskState.COMPLETED: {TaskState.ARCHIVED},
    TaskState.CANCELLED: {TaskState.ARCHIVED},
    TaskState.ARCHIVED: set(),
}


class QueueClass(Enum):
    FIFO = "FIFO"
    PRIORITY = "PRIORITY"
    ROUND_ROBIN = "ROUND_ROBIN"
    WEIGHTED = "WEIGHTED"
    BATCH = "BATCH"
    BACKGROUND = "BACKGROUND"
    EMERGENCY = "EMERGENCY"
    MAINTENANCE = "MAINTENANCE"


class IllegalTransitionError(RuntimeError):
    pass


class CyclicDependencyError(RuntimeError):
    pass


@dataclass
class TaskDTO:
    task_id: uuid.UUID
    priority_code: str
    task_type: str
    payload: Dict[str, Any]
    dependencies: List[uuid.UUID] = field(default_factory=list)
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    max_retries: int = DEFAULT_MAX_RETRIES
    queue_class: QueueClass = QueueClass.PRIORITY
    resource_tags: Set[str] = field(default_factory=set)
    handler: Optional[Callable[["TaskDTO"], Awaitable[Any]]] = None


@dataclass
class TaskRecord:
    dto: TaskDTO
    state: TaskState = TaskState.CREATED
    score: float = 0.0
    attempt: int = 0
    created_at: float = field(default_factory=time.monotonic)
    enqueued_at: float = field(default_factory=time.monotonic)
    last_error: Optional[str] = None
    result: Any = None


# ═══════════════════════════════════════════════════════════════════
# Chapter 2 — Public Interfaces (versioned contracts, Law 5)
# ═══════════════════════════════════════════════════════════════════

class ITaskScheduler(ABC):
    VERSION = "1.0.0"

    @abstractmethod
    async def submit_task(self, request: TaskDTO) -> bool: ...

    @abstractmethod
    async def cancel_task(self, task_id: uuid.UUID, reason: str) -> bool: ...

    @abstractmethod
    async def pause_task(self, task_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def resume_task(self, task_id: uuid.UUID) -> bool: ...


class IDependencyResolver(ABC):
    VERSION = "1.0.0"

    @abstractmethod
    def add_dependency(self, child_id: uuid.UUID, parent_id: uuid.UUID) -> bool: ...

    @abstractmethod
    def validate_dag(self) -> bool: ...

    @abstractmethod
    def get_ready_tasks(self) -> List[uuid.UUID]: ...


class IDispatchManager(ABC):
    VERSION = "1.0.0"

    @abstractmethod
    async def dispatch_task(self, task: TaskDTO, target_socket: str) -> bool: ...

    @abstractmethod
    def acknowledge_dispatch(self, task_id: uuid.UUID) -> bool: ...


# ═══════════════════════════════════════════════════════════════════
# Chapter 3 — Socket Bus & Pipelines (Universal Law 5)
# ═══════════════════════════════════════════════════════════════════

class SocketBus:
    """In-process pub/sub. Cross-organ transport is swapped in at the
    Interface Layer without modifying this organ (Foundational Law 9)."""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Callable[[Dict[str, Any]], None]]] = defaultdict(list)

    def subscribe(self, socket: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._subs[socket].append(handler)

    def publish(self, socket: str, event: Dict[str, Any]) -> None:
        for handler in list(self._subs.get(socket, [])):
            try:
                handler(event)
            except Exception:  # socket subscribers must not break the scheduler
                logger.exception("Socket handler failed on %s", socket)


TASK_SOCKET = "TaskSocket"
QUEUE_SOCKET = "QueueSocket"
DISPATCH_SOCKET = "DispatchSocket"
HISTORY_SOCKET = "HistorySocket"
METRICS_SOCKET = "MetricsSocket"


# ═══════════════════════════════════════════════════════════════════
# Chapter 4 — Task Registry & State Manager
# ═══════════════════════════════════════════════════════════════════

class TaskRegistry:
    """Deterministic in-memory task store with async locking."""

    def __init__(self) -> None:
        self._tasks: Dict[uuid.UUID, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def register(self, dto: TaskDTO) -> TaskRecord:
        async with self._lock:
            if dto.task_id in self._tasks:
                raise ValueError(f"Duplicate task_id {dto.task_id}")
            record = TaskRecord(dto=dto)
            self._tasks[dto.task_id] = record
            return record

    def get(self, task_id: uuid.UUID) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def all(self) -> List[TaskRecord]:
        return list(self._tasks.values())

    def remove(self, task_id: uuid.UUID) -> None:
        self._tasks.pop(task_id, None)


class WriteAheadLog:
    """Append-only WAL for state transitions (Law Book Foundational Law 7)."""

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []

    def append(self, task_id: uuid.UUID, frm: TaskState, to: TaskState) -> None:
        self._entries.append({
            "task_id": str(task_id),
            "from": frm.value,
            "to": to.value,
            "ts": time.time(),
        })

    def replay_since(self, index: int) -> List[Dict[str, Any]]:
        return self._entries[index:]

    def __len__(self) -> int:
        return len(self._entries)


class StateManager:
    """Executes atomic, validated task state transitions."""

    def __init__(self, registry: TaskRegistry, bus: SocketBus) -> None:
        self._registry = registry
        self._bus = bus
        self.wal = WriteAheadLog()
        self._lock = asyncio.Lock()

    async def transition(self, task_id: uuid.UUID, to: TaskState) -> TaskRecord:
        async with self._lock:
            record = self._registry.get(task_id)
            if record is None:
                raise KeyError(f"Unknown task {task_id}")
            frm = record.state
            if to not in LEGAL_TRANSITIONS.get(frm, set()):
                raise IllegalTransitionError(f"{frm.value} -> {to.value} not permitted")
            record.state = to
            self.wal.append(task_id, frm, to)
            self._bus.publish(TASK_SOCKET, {"task_id": task_id, "from": frm, "to": to})
            return record


# ═══════════════════════════════════════════════════════════════════
# Chapter 5 — Priority Manager
# ═══════════════════════════════════════════════════════════════════

_PRIORITY_BASE = {"EMERGENCY": 1000, "HIGH": 100, "NORMAL": 10, "LOW": 1, "BACKGROUND": 0}
AGING_RATE_PER_SEC = 0.5  # score gain per second waited, prevents starvation


class PriorityManager:
    def calculate_score(self, record: TaskRecord) -> float:
        base = _PRIORITY_BASE.get(record.dto.priority_code.upper(), 10)
        waited = max(0.0, time.monotonic() - record.enqueued_at)
        aging = waited * AGING_RATE_PER_SEC
        record.score = base + aging
        return record.score


# ═══════════════════════════════════════════════════════════════════
# Chapter 6 — Dependency Resolver (DAG, cycle detection)
# ═══════════════════════════════════════════════════════════════════

class DependencyResolver(IDependencyResolver):
    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry
        self._edges: Dict[uuid.UUID, Set[uuid.UUID]] = defaultdict(set)  # child -> parents
        self._children: Dict[uuid.UUID, Set[uuid.UUID]] = defaultdict(set)  # parent -> children
        self._completed: Set[uuid.UUID] = set()
        self._lock = asyncio.Lock()

    def add_dependency(self, child_id: uuid.UUID, parent_id: uuid.UUID) -> bool:
        self._edges[child_id].add(parent_id)
        self._children[parent_id].add(child_id)
        if not self.validate_dag():
            self._edges[child_id].discard(parent_id)
            self._children[parent_id].discard(child_id)
            raise CyclicDependencyError(f"Cycle introduced by {child_id} -> {parent_id}")
        return True

    def validate_dag(self) -> bool:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[uuid.UUID, int] = defaultdict(int)

        def visit(node: uuid.UUID) -> bool:
            color[node] = GRAY
            for parent in self._edges.get(node, ()):
                if color[parent] == GRAY:
                    return False
                if color[parent] == WHITE and not visit(parent):
                    return False
            color[node] = BLACK
            return True

        nodes = set(self._edges) | set(self._children)
        return all(visit(n) for n in nodes if color[n] == WHITE)

    def mark_completed(self, task_id: uuid.UUID) -> List[uuid.UUID]:
        """Returns children now unblocked by this completion."""
        self._completed.add(task_id)
        unblocked = []
        for child in self._children.get(task_id, ()):
            if self._edges[child] <= self._completed:
                unblocked.append(child)
        return unblocked

    def is_ready(self, task_id: uuid.UUID) -> bool:
        return self._edges.get(task_id, set()) <= self._completed

    def get_ready_tasks(self) -> List[uuid.UUID]:
        pending = {r.dto.task_id for r in self._registry.all() if r.state == TaskState.WAITING}
        return [t for t in pending if self.is_ready(t)]


# ═══════════════════════════════════════════════════════════════════
# Chapter 7 — Queue Manager
# ═══════════════════════════════════════════════════════════════════

@dataclass(order=True)
class _HeapItem:
    neg_score: float
    seq: int
    task_id: uuid.UUID = field(compare=False)


class QueueManager:
    """Multi-class queue: priority heap for standard classes, plain
    deques for FIFO/emergency/maintenance/background lanes."""

    def __init__(self, priority_mgr: PriorityManager, capacity: int = MAX_QUEUE_CAPACITY) -> None:
        self._priority_mgr = priority_mgr
        self._capacity = capacity
        self._heap: List[_HeapItem] = []
        self._counter = itertools.count()
        self._lanes: Dict[QueueClass, deque] = defaultdict(deque)
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def enqueue(self, record: TaskRecord) -> None:
        if self._size >= self._capacity:
            raise OverflowError("Queue capacity exceeded — spooling required")
        record.enqueued_at = time.monotonic()
        if record.dto.queue_class in (QueueClass.PRIORITY, QueueClass.WEIGHTED):
            score = self._priority_mgr.calculate_score(record)
            heapq.heappush(self._heap, _HeapItem(-score, next(self._counter), record.dto.task_id))
        else:
            self._lanes[record.dto.queue_class].append(record.dto.task_id)
        self._size += 1

    def dequeue(self, registry: TaskRegistry) -> Optional[uuid.UUID]:
        for lane in (QueueClass.EMERGENCY, QueueClass.MAINTENANCE, QueueClass.FIFO, QueueClass.BATCH):
            if self._lanes[lane]:
                self._size -= 1
                return self._lanes[lane].popleft()
        if self._heap:
            item = heapq.heappop(self._heap)
            self._size -= 1
            return item.task_id
        if self._lanes[QueueClass.BACKGROUND]:
            self._size -= 1
            return self._lanes[QueueClass.BACKGROUND].popleft()
        return None

    def resort(self) -> None:
        """Re-scores priority heap to apply aging; called periodically."""
        rescored = [
            _HeapItem(-item.neg_score, item.seq, item.task_id) for item in self._heap
        ]
        heapq.heapify(rescored)
        self._heap = rescored


# ═══════════════════════════════════════════════════════════════════
# Chapter 8 — Retry / Backoff Manager
# ═══════════════════════════════════════════════════════════════════

class RetryManager:
    def __init__(self, base_delay_ms: int = 200, max_delay_ms: int = 30_000, jitter: float = 0.2) -> None:
        self._base = base_delay_ms
        self._max = max_delay_ms
        self._jitter = jitter

    def should_retry(self, record: TaskRecord) -> bool:
        return record.attempt < record.dto.max_retries

    def next_delay_ms(self, record: TaskRecord) -> float:
        exp = min(self._max, self._base * (2 ** record.attempt))
        spread = exp * self._jitter
        return exp + random.uniform(-spread, spread)


# ═══════════════════════════════════════════════════════════════════
# Chapter 9 — Timeout Manager
# ═══════════════════════════════════════════════════════════════════

class TimeoutManager:
    def __init__(self, state_mgr: StateManager) -> None:
        self._state_mgr = state_mgr
        self._deadlines: Dict[uuid.UUID, asyncio.Task] = {}

    def arm(self, record: TaskRecord, on_timeout: Callable[[uuid.UUID], Awaitable[None]]) -> None:
        async def _watch() -> None:
            try:
                await asyncio.sleep(record.dto.timeout_ms / 1000.0)
                if record.state == TaskState.RUNNING:
                    await on_timeout(record.dto.task_id)
            except asyncio.CancelledError:
                pass

        self._deadlines[record.dto.task_id] = asyncio.ensure_future(_watch())

    def disarm(self, task_id: uuid.UUID) -> None:
        task = self._deadlines.pop(task_id, None)
        if task and not task.done():
            task.cancel()


# ═══════════════════════════════════════════════════════════════════
# Chapter 10 — Worker Pool / Concurrency Gate (Resource Constraints)
# ═══════════════════════════════════════════════════════════════════

class WorkerPool:
    """Bounded concurrency gate. Actual execution is delegated to the
    Resource Manager / Automation Engine organs via socket dispatch;
    this only reserves logical worker slots to prevent oversubscription
    of the CPU-first hardware target (i7, GPU reserved for the Brain)."""

    def __init__(self, max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency
        self.in_flight = 0

    async def acquire(self) -> None:
        await self._sem.acquire()
        self.in_flight += 1

    def release(self) -> None:
        self.in_flight -= 1
        self._sem.release()


# ═══════════════════════════════════════════════════════════════════
# Chapter 11 — Dispatch Manager
# ═══════════════════════════════════════════════════════════════════

class DispatchManager(IDispatchManager):
    def __init__(self, bus: SocketBus, pool: WorkerPool) -> None:
        self._bus = bus
        self._pool = pool
        self._acked: Set[uuid.UUID] = set()

    async def dispatch_task(self, task: TaskDTO, target_socket: str = DISPATCH_SOCKET) -> bool:
        await self._pool.acquire()
        self._bus.publish(target_socket, {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "payload": task.payload,
            "resource_tags": task.resource_tags,
        })
        return True

    def acknowledge_dispatch(self, task_id: uuid.UUID) -> bool:
        self._acked.add(task_id)
        return True

    def release_slot(self) -> None:
        self._pool.release()


# ═══════════════════════════════════════════════════════════════════
# Chapter 12 — History & Metrics Managers
# ═══════════════════════════════════════════════════════════════════

class HistoryManager:
    def __init__(self, bus: SocketBus) -> None:
        self._archive: List[TaskRecord] = []
        self._bus = bus

    def archive(self, record: TaskRecord) -> None:
        self._archive.append(record)
        self._bus.publish(HISTORY_SOCKET, {
            "task_id": record.dto.task_id,
            "final_state": record.state.value,
            "attempts": record.attempt,
        })

    def query(self, task_id: uuid.UUID) -> Optional[TaskRecord]:
        return next((r for r in self._archive if r.dto.task_id == task_id), None)


class MetricsManager:
    def __init__(self) -> None:
        self.counters: Dict[str, int] = defaultdict(int)
        self.timings_ms: Dict[str, List[float]] = defaultdict(list)

    def incr(self, name: str, n: int = 1) -> None:
        self.counters[name] += n

    def record_timing(self, name: str, ms: float) -> None:
        self.timings_ms[name].append(ms)

    def snapshot(self) -> Dict[str, Any]:
        return {"counters": dict(self.counters),
                "avg_timings_ms": {k: (sum(v) / len(v) if v else 0.0) for k, v in self.timings_ms.items()}}


# ═══════════════════════════════════════════════════════════════════
# Chapter 13 — Recovery Manager
# ═══════════════════════════════════════════════════════════════════

class RecoveryManager:
    def __init__(self, state_mgr: StateManager, history: HistoryManager, metrics: MetricsManager) -> None:
        self._state_mgr = state_mgr
        self._history = history
        self._metrics = metrics

    async def handle_failure(self, record: TaskRecord, error: str) -> None:
        record.last_error = error
        self._metrics.incr("failures")
        if record.state == TaskState.RETRY:
            await self._state_mgr.transition(record.dto.task_id, TaskState.FAILED)
        await self._state_mgr.transition(record.dto.task_id, TaskState.RECOVERY)
        await self._state_mgr.transition(record.dto.task_id, TaskState.ARCHIVED)
        self._history.archive(record)

    async def emergency_stop(self, record: TaskRecord, reason: str) -> None:
        record.last_error = f"EMERGENCY_STOP: {reason}"
        await self._state_mgr.transition(record.dto.task_id, TaskState.RECOVERY)
        await self._state_mgr.transition(record.dto.task_id, TaskState.ARCHIVED)
        self._history.archive(record)


# ═══════════════════════════════════════════════════════════════════
# Chapter 14 — Task Validator
# ═══════════════════════════════════════════════════════════════════

class TaskValidator:
    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def validate(self, dto: TaskDTO) -> None:
        if not dto.task_type:
            raise ValueError("task_type is required")
        if dto.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if dto.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self._registry.get(dto.task_id) is not None:
            raise ValueError(f"Duplicate task submission {dto.task_id}")


# ═══════════════════════════════════════════════════════════════════
# Chapter 15 — Task Scheduler Facade (ITaskScheduler)
# ═══════════════════════════════════════════════════════════════════

class TaskScheduler(ITaskScheduler):
    """Central orchestrator. Owns no execution logic — plans, orders,
    resolves dependencies, and dispatches through sockets only."""

    def __init__(self, max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> None:
        self.bus = SocketBus()
        self.registry = TaskRegistry()
        self.state_mgr = StateManager(self.registry, self.bus)
        self.priority_mgr = PriorityManager()
        self.queue_mgr = QueueManager(self.priority_mgr)
        self.dep_resolver = DependencyResolver(self.registry)
        self.pool = WorkerPool(max_concurrency)
        self.dispatch_mgr = DispatchManager(self.bus, self.pool)
        self.timeout_mgr = TimeoutManager(self.state_mgr)
        self.retry_mgr = RetryManager()
        self.history_mgr = HistoryManager(self.bus)
        self.metrics_mgr = MetricsManager()
        self.recovery_mgr = RecoveryManager(self.state_mgr, self.history_mgr, self.metrics_mgr)
        self.validator = TaskValidator(self.registry)
        self._running_loop: Optional[asyncio.Task] = None
        self._shutdown = asyncio.Event()

    # ---- ITaskScheduler ----

    async def submit_task(self, request: TaskDTO) -> bool:
        t0 = time.monotonic()
        self.validator.validate(request)
        record = await self.registry.register(request)
        await self.state_mgr.transition(request.task_id, TaskState.VALIDATED)
        await self.state_mgr.transition(request.task_id, TaskState.QUEUED)

        for parent_id in request.dependencies:
            self.dep_resolver.add_dependency(request.task_id, parent_id)

        await self.state_mgr.transition(request.task_id, TaskState.WAITING)
        if self.dep_resolver.is_ready(request.task_id):
            self.queue_mgr.enqueue(record)
        self.bus.publish(QUEUE_SOCKET, {"task_id": request.task_id, "event": "queued"})
        self.metrics_mgr.incr("submitted")
        self.metrics_mgr.record_timing("ingestion", (time.monotonic() - t0) * 1000)
        return True

    async def cancel_task(self, task_id: uuid.UUID, reason: str) -> bool:
        record = self.registry.get(task_id)
        if record is None or record.state in (TaskState.ARCHIVED, TaskState.CANCELLED):
            return False
        self.timeout_mgr.disarm(task_id)
        await self.state_mgr.transition(task_id, TaskState.CANCELLED)
        await self.state_mgr.transition(task_id, TaskState.ARCHIVED)
        record.last_error = f"CANCELLED: {reason}"
        self.history_mgr.archive(record)
        self.metrics_mgr.incr("cancelled")
        return True

    async def pause_task(self, task_id: uuid.UUID) -> bool:
        record = self.registry.get(task_id)
        if record is None or record.state != TaskState.RUNNING:
            return False
        await self.state_mgr.transition(task_id, TaskState.PAUSED)
        return True

    async def resume_task(self, task_id: uuid.UUID) -> bool:
        record = self.registry.get(task_id)
        if record is None or record.state != TaskState.PAUSED:
            return False
        await self.state_mgr.transition(task_id, TaskState.RESUMED)
        await self.state_mgr.transition(task_id, TaskState.RUNNING)
        return True

    # ---- Dispatch loop ----

    async def _run_one(self, task_id: uuid.UUID) -> None:
        record = self.registry.get(task_id)
        if record is None:
            return
        await self.state_mgr.transition(task_id, TaskState.SCHEDULED)
        await self.state_mgr.transition(task_id, TaskState.RUNNING)
        record.attempt += 1
        self.timeout_mgr.arm(record, self._on_timeout)
        await self.dispatch_mgr.dispatch_task(record.dto)
        start = time.monotonic()
        try:
            if record.dto.handler is not None:
                result = await record.dto.handler(record.dto)
            else:
                result = None
            await self._on_success(task_id, result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - boundary catch by design
            await self._on_failure(task_id, str(exc))
        finally:
            self.timeout_mgr.disarm(task_id)
            self.dispatch_mgr.release_slot()
            self.metrics_mgr.record_timing("execution", (time.monotonic() - start) * 1000)

    async def _on_success(self, task_id: uuid.UUID, result: Any) -> None:
        record = self.registry.get(task_id)
        if record is None:
            return
        record.result = result
        await self.state_mgr.transition(task_id, TaskState.COMPLETED)
        await self.state_mgr.transition(task_id, TaskState.ARCHIVED)
        self.history_mgr.archive(record)
        self.metrics_mgr.incr("completed")
        for child_id in self.dep_resolver.mark_completed(task_id):
            child = self.registry.get(child_id)
            if child and self.dep_resolver.is_ready(child_id):
                self.queue_mgr.enqueue(child)

    async def _on_failure(self, task_id: uuid.UUID, error: str) -> None:
        record = self.registry.get(task_id)
        if record is None:
            return
        if self.retry_mgr.should_retry(record):
            await self.state_mgr.transition(task_id, TaskState.RETRY)
            delay = self.retry_mgr.next_delay_ms(record) / 1000.0
            await self.state_mgr.transition(task_id, TaskState.QUEUED)
            await self.state_mgr.transition(task_id, TaskState.WAITING)
            self.metrics_mgr.incr("retries")
            await asyncio.sleep(delay)
            self.queue_mgr.enqueue(record)
        else:
            await self.state_mgr.transition(task_id, TaskState.RETRY)
            await self.recovery_mgr.handle_failure(record, error)

    async def _on_timeout(self, task_id: uuid.UUID) -> None:
        record = self.registry.get(task_id)
        if record is None or record.state != TaskState.RUNNING:
            return
        await self.state_mgr.transition(task_id, TaskState.TIMEOUT)
        self.metrics_mgr.incr("timeouts")
        if self.retry_mgr.should_retry(record):
            await self.state_mgr.transition(task_id, TaskState.RETRY)
            await self.state_mgr.transition(task_id, TaskState.QUEUED)
            await self.state_mgr.transition(task_id, TaskState.WAITING)
            self.queue_mgr.enqueue(record)
        else:
            await self.state_mgr.transition(task_id, TaskState.FAILED)
            await self.recovery_mgr.handle_failure(record, "timeout exhausted retries")
        self.dispatch_mgr.release_slot()

    async def emergency_stop(self, task_id: uuid.UUID, reason: str) -> bool:
        record = self.registry.get(task_id)
        if record is None or record.state != TaskState.RUNNING:
            return False
        self.timeout_mgr.disarm(task_id)
        await self.state_mgr.transition(task_id, TaskState.EMERGENCY_STOP)
        await self.recovery_mgr.emergency_stop(record, reason)
        return True

    async def tick(self) -> int:
        """Single scheduling tick: promote ready WAITING tasks, drain
        the queue up to available worker slots. Returns tasks dispatched."""
        self.queue_mgr.resort()
        for task_id in self.dep_resolver.get_ready_tasks():
            record = self.registry.get(task_id)
            if record and record.state == TaskState.WAITING:
                self.queue_mgr.enqueue(record)

        dispatched = 0
        while self.pool.in_flight < self.pool.max_concurrency and len(self.queue_mgr):
            task_id = self.queue_mgr.dequeue(self.registry)
            if task_id is None:
                break
            asyncio.ensure_future(self._run_one(task_id))
            dispatched += 1
        return dispatched

    async def run_forever(self, interval_ms: float = 1.0) -> None:
        self._shutdown.clear()
        while not self._shutdown.is_set():
            await self.tick()
            await asyncio.sleep(interval_ms / 1000.0)

    def stop(self) -> None:
        self._shutdown.set()
