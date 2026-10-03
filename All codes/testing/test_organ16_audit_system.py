"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_organ16_audit_system.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_organ16_audit_system.py]
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
Dependencies: pytest, pathlib, json, asyncio, sys...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ16_audit_system.py]) --> output([Output Node])
```
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # type: ignore

from observability.organ_16_audit_system import (
    ActorIdentity, AuditCategory, AuditQuery, AuditRecordType, AuditSeverity,
    AuditSystem, AuditValidationError, AuditValidator, AuditRecord,
)


@pytest.fixture()
def system(tmp_path):
    return AuditSystem(storage_dir=str(tmp_path / "audit_store"))


def make_actor():
    return ActorIdentity(actor_type="AGENT", actor_id="agent-001", display_name="Test Agent")


def test_record_and_query(system):
    system.record(
        category=AuditCategory.TASK,
        severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT,
        source_organ="execution_controller",
        actor=make_actor(),
        action="TASK_STARTED",
        summary="Task started",
    )
    results = system.query(AuditQuery(category=AuditCategory.TASK))
    assert len(results) == 1
    assert results[0].action == "TASK_STARTED"


def test_chain_hash_integrity(system):
    for i in range(5):
        system.record(
            category=AuditCategory.SECURITY,
            severity=AuditSeverity.SECURITY_ALERT,
            record_type=AuditRecordType.SECURITY,
            source_organ="security_controller",
            actor=make_actor(),
            action=f"LOGIN_ATTEMPT_{i}",
            summary="login attempt",
        )
    report = system.verify_integrity()
    assert report.valid
    assert report.verified_records == 5


def test_tamper_detection(system, tmp_path):
    system.record(
        category=AuditCategory.ERROR,
        severity=AuditSeverity.ERROR,
        record_type=AuditRecordType.ERROR,
        source_organ="kernel",
        actor=make_actor(),
        action="UNHANDLED_EXCEPTION",
        summary="boom",
    )
    segment = next((tmp_path / "audit_store").glob("segment_*.jsonl"))
    lines = segment.read_text().splitlines()
    record = json.loads(lines[0])
    record["summary"] = "tampered"
    segment.write_text(json.dumps(record) + "\n")

    fresh = AuditSystem(storage_dir=str(tmp_path / "audit_store"))
    report = fresh.verify_integrity()
    assert not report.valid
    assert report.broken_at_sequence == 1


def test_validation_rejects_bad_record():
    validator = AuditValidator()
    bad = AuditRecord.create(
        category=AuditCategory.SYSTEM,
        severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT,
        source_organ="kernel",
        actor=make_actor(),
        action="",
        summary="x",
    )
    with pytest.raises(AuditValidationError):
        validator.validate(bad)


def test_trace_correlation(system):
    trace_id = "11111111-1111-1111-1111-111111111111"
    system.record(
        category=AuditCategory.WORKFLOW, severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT, source_organ="workflow_engine",
        actor=make_actor(), action="STEP_1", summary="step 1", trace_id=trace_id,
    )
    system.record(
        category=AuditCategory.WORKFLOW, severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT, source_organ="workflow_engine",
        actor=make_actor(), action="STEP_2", summary="step 2", trace_id=trace_id,
    )
    linked = system.trace(trace_id)
    assert len(linked) == 2


def test_recovery_rebuilds_index(system, tmp_path):
    system.record(
        category=AuditCategory.BACKUP, severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT, source_organ="backup_manager",
        actor=make_actor(), action="SNAPSHOT_CREATED", summary="snapshot ok",
    )
    reopened = AuditSystem(storage_dir=str(tmp_path / "audit_store"))
    report = reopened.recover()
    assert report.valid
    assert len(reopened.indexer.all_records()) == 1


def test_retention_sweep_moves_expired_segment(system, tmp_path):
    import observability.organ_16_audit_system as mod
    from datetime import datetime, timedelta, timezone

    system.record(
        category=AuditCategory.SECURITY, severity=AuditSeverity.INFO,
        record_type=AuditRecordType.SECURITY, source_organ="security_controller",
        actor=make_actor(), action="OLD_EVENT", summary="old",
    )
    # force segment rotation so the record is not in the active segment
    system.store._active_segment = system.store._dir / "segment_000002.jsonl"

    far_future = datetime.now(timezone.utc) + timedelta(days=4000)
    archived = system.retention_manager.sweep(now=far_future)
    assert "segment_000001.jsonl" in archived


@pytest.mark.asyncio
async def test_async_ingestion(system):
    await system.collector.start()
    await system.record_async(
        category=AuditCategory.API, severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT, source_organ="api_gateway",
        actor=make_actor(), action="REQUEST_RECEIVED", summary="ok",
    )
    await system.collector.stop()
    results = system.query(AuditQuery(category=AuditCategory.API))
    assert len(results) == 1


def test_socket_subscription_notified(system):
    received = []
    system.subscribe(lambda r: received.append(r))
    system.record(
        category=AuditCategory.PLUGIN, severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT, source_organ="plugin_runtime",
        actor=make_actor(), action="PLUGIN_LOADED", summary="loaded",
    )
    assert len(received) == 1
    assert received[0].action == "PLUGIN_LOADED"
