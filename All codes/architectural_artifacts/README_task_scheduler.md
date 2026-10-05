# Organ 34 — Task Scheduler

**Spec:** SPEC-AOS-SCHED-001 · **Contract versions:** ITaskScheduler 1.0.0, IDependencyResolver 1.0.0, IDispatchManager 1.0.0

## Scope
Plans, orders, resolves dependencies, and dispatches tasks. Does **not** execute automation logic, allocate hardware, or reason — those belong to Automation Engine, Resource Manager, and Brain respectively.

## Modules
TaskValidator · TaskRegistry · StateManager (WAL) · PriorityManager (aging) · QueueManager (FIFO/Priority/Emergency/Background lanes) · DependencyResolver (DAG + cycle detection) · WorkerPool (concurrency gate) · DispatchManager · TimeoutManager · RetryManager (exponential backoff + jitter) · RecoveryManager · HistoryManager (append-only) · MetricsManager · SocketBus.

## State Machine
`CREATED → VALIDATED → QUEUED → WAITING → SCHEDULED → RUNNING → {COMPLETED|RETRY|TIMEOUT|PAUSED|CANCELLED|EMERGENCY_STOP} → ... → ARCHIVED`. All transitions validated against `LEGAL_TRANSITIONS`; illegal jumps raise `IllegalTransitionError`.

## Sockets
`TaskSocket`, `QueueSocket`, `DispatchSocket`, `HistorySocket`, `MetricsSocket` — in-process `SocketBus`, swappable at Interface Layer for cross-process transport without touching this organ.

## Pipelines
Task Creation → Validation → Queue → Dependency → Dispatch → Verification → History/Metrics.

## Resource Constraints & Deadlock Prevention
`WorkerPool` bounds concurrency (default 8, CPU-first; GPU reserved for Brain). `DependencyResolver.validate_dag` runs on every edge insertion (DFS coloring) — cycles rejected before entering the graph, preventing deadlock.

## Usage
```python
from task_scheduler import TaskScheduler, TaskDTO
import uuid, asyncio

async def handler(dto): return "done"

sched = TaskScheduler(max_concurrency=4)
await sched.submit_task(TaskDTO(task_id=uuid.uuid4(), priority_code="HIGH",
                                 task_type="demo", payload={}, handler=handler))
asyncio.create_task(sched.run_forever())
```

## Testing
`pytest test_task_scheduler.py -q --asyncio-mode=auto` — 14/14 passing. Covers success, retry+backoff, exhausted retries, timeout, cancel, dependency unblocking, cycle detection, illegal transitions, validation, aging, backoff growth, concurrency bound, emergency stop, metrics.
