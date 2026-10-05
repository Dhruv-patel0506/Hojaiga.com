"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_infrastructure_organ.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_infrastructure_organ.py]
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
Dependencies: time, core_runtime.infrastructure_organ, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_infrastructure_organ.py]) --> output([Output Node])
```
"""

import time
import uuid

from core_runtime.infrastructure_organ import (
    InfrastructureConfig,
    InfrastructureOrgan,
    LogEntry,
    QuotaRequest,
    ArchivalRequest,
)


def _make_organ(tmp_path):
    cfg = InfrastructureConfig.defaults(str(tmp_path))
    return InfrastructureOrgan(cfg)


def test_hardware_status_shape(tmp_path):
    with _make_organ(tmp_path) as infra:
        status = infra.get_hardware_status()
        assert 0.0 <= status.cpu_percent <= 100.0
        assert status.ram_total_mb > 0


def test_quota_allocate_and_release(tmp_path):
    with _make_organ(tmp_path) as infra:
        grant = infra.allocate_quota(QuotaRequest(requesting_organ="test_organ"))
        assert grant.requesting_organ == "test_organ"
        assert infra.release_quota(grant.grant_id) is True
        assert infra.release_quota(grant.grant_id) is False


def test_log_append_and_flush(tmp_path):
    with _make_organ(tmp_path) as infra:
        infra.append_log(
            LogEntry(
                execution_id=str(uuid.uuid4()),
                responsible_component="pytest",
                agent_model=None,
                task_description="test",
            )
        )
        infra.logger._flush_once()
        assert infra.logger._buffer_file.exists()
        content = infra.logger._buffer_file.read_text(encoding="utf-8")
        assert "pytest" in content


def test_filesystem_path_traversal_blocked(tmp_path):
    with _make_organ(tmp_path) as infra:
        try:
            infra.filesystem.get_runtime_path("../../etc/passwd")
            assert False, "Expected PermissionError"
        except PermissionError:
            pass


def test_archive_missing_file_reports_failure(tmp_path):
    with _make_organ(tmp_path) as infra:
        status = infra.archive(ArchivalRequest(runtime_relative_path="nope.txt"))
        assert status.success is False
        assert status.error is not None


def test_version_manifest(tmp_path):
    with _make_organ(tmp_path) as infra:
        manifest = infra.get_version()
        assert manifest.organ == "infrastructure"
        assert manifest.version == "1.0.0"


def test_event_subscription_receives_warning(tmp_path):
    cfg = InfrastructureConfig.defaults(str(tmp_path))
    cfg.ram_warning_percent = -1.0  # force immediate warning
    cfg.monitor_interval_sec = 0.1
    with InfrastructureOrgan(cfg) as infra:
        received = []
        infra.subscribe_events(lambda e: received.append(e))
        time.sleep(0.5)
        assert any(
            e.event_type == "EVENT_INFRASTRUCTURE_RESOURCE_WARNING"
            for e in received
        )
