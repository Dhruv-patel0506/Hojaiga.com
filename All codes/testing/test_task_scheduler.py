"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_task_scheduler.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_task_scheduler.py]
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
Dependencies: core_runtime.task_scheduler, pytest, time, asyncio, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_task_scheduler.py]) --> output([Output Node])
```
"""

"""Test suite for the Hojaiga Task Scheduler organ. Run: pytest -q"""

import asyncio
import uuid

import pytest  # type: ignore

from core_runtime.task_scheduler import (
    CyclicDependencyError, DependencyResolver, IllegalTransitionError,
    QueueClass, RetryManager, StateManager, TaskDTO, TaskRecord, TaskRegistry,
    TaskScheduler, TaskState, TaskValidator,
)


def make_dto(**overrides) -> TaskDTO:
    defaults = dict(
        task_id=uuid.uuid4(), priority_code="NORMAL", task_type="noop", payload={},
    )
    defaults.update(overrides)
    return TaskDTO(**defaults)


@pytest.mark.asyncio
async def test_submit_and_complete_success():
    sched = TaskScheduler(max_concurrency=2)

    async def handler(dto: TaskDTO):
        return "ok"

    dto = make_dto(handler=handler)
    await sched.submit_task(dto)
    await sched.tick()
    await asyncio.sleep(0.05)
    record = sched.history_mgr.query(dto.task_id)
    assert record is not None
    assert record.state == TaskState.ARCHIVED
    assert record.result == "ok"


@pytest.mark.asyncio
async def test_retry_then_success_with_backoff():
    sched = TaskScheduler(max_concurrency=1)
    attempts = {"n": 0}

    async def handler(dto: TaskDTO):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return "recovered"

    dto = make_dto(handler=handler, max_retries=3)
    await sched.submit_task(dto)
    await sched.tick()
    await asyncio.sleep(0.5)
    record = sched.registry.get(dto.task_id) or sched.history_mgr.query(dto.task_id)
    assert attempts["n"] == 2
    assert record.result == "recovered"  # type: ignore


@pytest.mark.asyncio
async def test_exhausted_retries_goes_to_recovery_archive():
    sched = TaskScheduler(max_concurrency=1)

    async def handler(dto: TaskDTO):
        raise RuntimeError("permanent")

    dto = make_dto(handler=handler, max_retries=0)
    await sched.submit_task(dto)
    await sched.tick()
    await asyncio.sleep(0.05)
    record = sched.history_mgr.query(dto.task_id)
    assert record.state == TaskState.ARCHIVED  # type: ignore
    assert "permanent" in record.last_error  # type: ignore


@pytest.mark.asyncio
async def test_timeout_triggers_retry_then_fails():
    sched = TaskScheduler(max_concurrency=1)

    async def slow_handler(dto: TaskDTO):
        await asyncio.sleep(1.0)
        return "too slow"

    dto = make_dto(handler=slow_handler, timeout_ms=20, max_retries=0)
    await sched.submit_task(dto)
    await sched.tick()
    await asyncio.sleep(0.15)
    record = sched.history_mgr.query(dto.task_id)
    assert record is not None
    assert record.state == TaskState.ARCHIVED


@pytest.mark.asyncio
async def test_cancel_task():
    sched = TaskScheduler()
    dto = make_dto()
    await sched.submit_task(dto)
    ok = await sched.cancel_task(dto.task_id, "user requested")
    assert ok
    record = sched.history_mgr.query(dto.task_id)
    assert record.state == TaskState.ARCHIVED  # type: ignore


@pytest.mark.asyncio
async def test_dependency_unblocks_child():
    sched = TaskScheduler(max_concurrency=2)
    order = []

    async def parent_handler(dto: TaskDTO):
        order.append("parent")
        return "p"

    async def child_handler(dto: TaskDTO):
        order.append("child")
        return "c"

    parent = make_dto(handler=parent_handler)
    child = make_dto(handler=child_handler, dependencies=[parent.task_id])

    await sched.submit_task(parent)
    await sched.submit_task(child)

    assert sched.registry.get(child.task_id).state == TaskState.WAITING  # type: ignore
    for _ in range(5):
        await sched.tick()
        await asyncio.sleep(0.05)

    assert order == ["parent", "child"]


def test_cycle_detection_raises():
    reg = TaskRegistry()
    resolver = DependencyResolver(reg)
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    resolver.add_dependency(b, a)
    resolver.add_dependency(c, b)
    with pytest.raises(CyclicDependencyError):
        resolver.add_dependency(a, c)


@pytest.mark.asyncio
async def test_illegal_state_transition_rejected():
    reg = TaskRegistry()
    from core_runtime.task_scheduler import SocketBus
    bus = SocketBus()
    sm = StateManager(reg, bus)
    dto = make_dto()
    await reg.register(dto)
    with pytest.raises(IllegalTransitionError):
        await sm.transition(dto.task_id, TaskState.COMPLETED)


def test_validator_rejects_duplicate_and_bad_fields():
    reg = TaskRegistry()
    validator = TaskValidator(reg)
    dto = make_dto(task_type="")
    with pytest.raises(ValueError):
        validator.validate(dto)
    dto2 = make_dto(timeout_ms=0)
    with pytest.raises(ValueError):
        validator.validate(dto2)


def test_priority_aging_increases_score():
    from core_runtime.task_scheduler import PriorityManager
    import time as _time
    pm = PriorityManager()
    record = TaskRecord(dto=make_dto(priority_code="LOW"))
    record.enqueued_at -= 10  # simulate 10s wait
    score = pm.calculate_score(record)
    assert score > 1


def test_retry_backoff_grows_exponentially():
    rm = RetryManager(base_delay_ms=100, max_delay_ms=10_000, jitter=0.0)
    record = TaskRecord(dto=make_dto())
    record.attempt = 0
    d0 = rm.next_delay_ms(record)
    record.attempt = 3
    d3 = rm.next_delay_ms(record)
    assert d3 > d0


@pytest.mark.asyncio
async def test_worker_pool_bounds_concurrency():
    sched = TaskScheduler(max_concurrency=1)
    running = {"count": 0, "max": 0}

    async def handler(dto: TaskDTO):
        running["count"] += 1
        running["max"] = max(running["max"], running["count"])
        await asyncio.sleep(0.05)
        running["count"] -= 1
        return "ok"

    for _ in range(3):
        await sched.submit_task(make_dto(handler=handler))

    for _ in range(10):
        await sched.tick()
        await asyncio.sleep(0.02)

    assert running["max"] <= 1


@pytest.mark.asyncio
async def test_emergency_stop_archives_task():
    sched = TaskScheduler(max_concurrency=1)

    async def handler(dto: TaskDTO):
        await asyncio.sleep(1.0)

    dto = make_dto(handler=handler, timeout_ms=5000)
    await sched.submit_task(dto)
    await sched.tick()
    await asyncio.sleep(0.02)
    ok = await sched.emergency_stop(dto.task_id, "safety intervention")
    assert ok
    record = sched.history_mgr.query(dto.task_id)
    assert record.state == TaskState.ARCHIVED  # type: ignore


def test_metrics_snapshot_structure():
    from core_runtime.task_scheduler import MetricsManager
    m = MetricsManager()
    m.incr("submitted", 3)
    m.record_timing("ingestion", 1.5)
    snap = m.snapshot()
    assert snap["counters"]["submitted"] == 3
    assert "ingestion" in snap["avg_timings_ms"]
