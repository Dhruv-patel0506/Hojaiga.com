"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_service_registry_organ.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_service_registry_organ.py]
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
Dependencies: time, core_runtime.service_registry_organ, pytest...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_service_registry_organ.py]) --> output([Output Node])
```
"""

import time

import pytest  # type: ignore

from core_runtime.service_registry_organ import (
    ServiceRegistryCore, ServiceManifestDTO, DiscoveryQueryDTO,
    HeartbeatFrameDTO, HealthProbeDTO, FailureAlertDTO, FailureType,
    ServiceState, HealthStatus, PermissionLevel,
    RegistrationValidationError, ServiceNotFoundException,
    PermissionDeniedException, CircularDependencyError,
    IllegalStateTransitionError, VersionIncompatibleError,
    SemVerParser, TarjanDAG,
)


def manifest(name="organ.test.alpha", version="1.0.0", deps=None, **kw):
    return ServiceManifestDTO(
        service_name=name, description="test service", category="AUTOMATION_SERVICES",
        version=version, owner="test-owner", dependencies=deps or [], **kw,
    )


@pytest.fixture()
def core():
    return ServiceRegistryCore()


# ---- Registration ---------------------------------------------------

def test_register_service_success(core):
    record = core.registration_pipeline.run(manifest(), "LEVEL_3_ADMIN")
    assert record.status == ServiceState.REGISTERED
    assert core.db.get_by_name("organ.test.alpha") is not None


def test_register_duplicate_name_rejected(core):
    core.registration_pipeline.run(manifest(), "LEVEL_3_ADMIN")
    with pytest.raises(RegistrationValidationError):
        core.registration_pipeline.run(manifest(), "LEVEL_3_ADMIN")


def test_register_invalid_name_rejected(core):
    with pytest.raises(RegistrationValidationError):
        core.registration_pipeline.run(manifest(name="BadName"), "LEVEL_3_ADMIN")


def test_register_invalid_semver_rejected(core):
    with pytest.raises(VersionIncompatibleError):
        core.registration_pipeline.run(manifest(version="not-a-version"), "LEVEL_3_ADMIN")


def test_register_requires_admin_permission(core):
    with pytest.raises(PermissionDeniedException):
        core.registration_pipeline.run(manifest(), "LEVEL_1_INTERNAL")


def test_register_via_iserviceregistry_interface(core):
    assert core.register_service(manifest(name="organ.test.iface")) is True


# ---- Dependency graph -------------------------------------------------

def test_dependency_startup_order(core):
    core.registration_pipeline.run(manifest(name="organ.test.base"), "LEVEL_3_ADMIN")
    core.registration_pipeline.run(
        manifest(name="organ.test.dependent",
                 deps=[{"service_name": "organ.test.base", "version_range": ">=1.0.0"}]),
        "LEVEL_3_ADMIN",
    )
    order = core.dependency_mgr.get_startup_sequence()
    base_id = core.db.get_by_name("organ.test.base").service_id
    dep_id = core.db.get_by_name("organ.test.dependent").service_id
    assert order.index(base_id) < order.index(dep_id)


def test_circular_dependency_detected():
    dag = TarjanDAG()
    dag.add_edge("A", "B")
    dag.add_edge("B", "A")
    cycles = dag.detect_cycles()
    assert len(cycles) == 1


def test_registration_rolls_back_on_cycle(core):
    core.registration_pipeline.run(manifest(name="organ.test.x"), "LEVEL_3_ADMIN")
    x_id = core.db.get_by_name("organ.test.x").service_id
    core.registration_pipeline.run(
        manifest(name="organ.test.y", deps=[{"service_name": "organ.test.x", "version_range": ""}]),
        "LEVEL_3_ADMIN",
    )
    # Manually force a cycle: x depends on y (created after validation), then re-validate
    core.db.get(x_id).dependencies.append({"service_name": "organ.test.y", "version_range": ""})
    with pytest.raises(CircularDependencyError):
        core.dependency_mgr.validate_graph()


# ---- Discovery ---------------------------------------------------------

def test_discover_by_name(core):
    core.registration_pipeline.run(manifest(name="organ.test.discoverable"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.discoverable").service_id
    core.state_mgr.transition(sid, ServiceState.VALIDATED)
    core.db.get(sid).health_status = HealthStatus.HEALTHY
    endpoint = core.discovery_pipeline.run(
        DiscoveryQueryDTO(service_name="organ.test.discoverable", require_healthy=False)
    )
    assert endpoint.service_name == "organ.test.discoverable"


def test_discover_not_found(core):
    with pytest.raises(ServiceNotFoundException):
        core.discovery_pipeline.run(DiscoveryQueryDTO(service_name="does.not.exist"))


def test_discover_uses_cache(core):
    core.registration_pipeline.run(manifest(name="organ.test.cached"), "LEVEL_3_ADMIN")
    query = DiscoveryQueryDTO(service_name="organ.test.cached", require_healthy=False)
    e1 = core.discovery_pipeline.run(query)
    e2 = core.discovery_pipeline.run(query)
    assert e1.auth_token == e2.auth_token


def test_discover_permission_denied(core):
    core.registration_pipeline.run(
        manifest(name="organ.test.kernelonly", permission_level="LEVEL_4_KERNEL"), "LEVEL_3_ADMIN"
    )
    with pytest.raises(PermissionDeniedException):
        core.discovery_pipeline.run(
            DiscoveryQueryDTO(service_name="organ.test.kernelonly", caller_scope="LEVEL_0_PUBLIC",
                              require_healthy=False)
        )


# ---- Lifecycle -----------------------------------------------------------

def test_start_and_stop_service(core):
    core.registration_pipeline.run(manifest(name="organ.test.lifecycle"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.lifecycle").service_id
    assert core.startup_pipeline.run(sid) is True
    assert core.db.get(sid).status == ServiceState.RUNNING
    assert core.shutdown_pipeline.run(sid) is True
    assert core.db.get(sid).status == ServiceState.STOPPED


def test_illegal_state_transition_raises(core):
    core.registration_pipeline.run(manifest(name="organ.test.illegal"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.illegal").service_id
    with pytest.raises(IllegalStateTransitionError):
        core.state_mgr.transition(sid, ServiceState.RUNNING)


def test_start_blocked_by_unhealthy_dependency(core):
    core.registration_pipeline.run(manifest(name="organ.test.dep_base"), "LEVEL_3_ADMIN")
    core.registration_pipeline.run(
        manifest(name="organ.test.dep_child",
                 deps=[{"service_name": "organ.test.dep_base", "version_range": ""}]),
        "LEVEL_3_ADMIN",
    )
    child_id = core.db.get_by_name("organ.test.dep_child").service_id
    with pytest.raises(Exception):
        core.startup_pipeline.run(child_id)


def test_deregister_service(core):
    core.registration_pipeline.run(manifest(name="organ.test.deregister"), "LEVEL_3_ADMIN")
    record = core.db.get_by_name("organ.test.deregister")
    assert core.deregister_service(record.service_id, record.auth_secret) is True
    assert core.db.get(record.service_id) is None


def test_deregister_wrong_key_denied(core):
    core.registration_pipeline.run(manifest(name="organ.test.badkey"), "LEVEL_3_ADMIN")
    record = core.db.get_by_name("organ.test.badkey")
    with pytest.raises(PermissionDeniedException):
        core.deregister_service(record.service_id, "wrong-key")


# ---- Heartbeat / Health / Recovery ---------------------------------------

def test_heartbeat_updates_service(core):
    core.registration_pipeline.run(manifest(name="organ.test.hb"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.hb").service_id
    core.heartbeat_pipeline.run(HeartbeatFrameDTO(service_id=sid, tick=1))
    assert core.db.get(sid).missed_heartbeats == 0


def test_health_probe_marks_degraded_over_threshold(core):
    core.registration_pipeline.run(manifest(name="organ.test.health"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.health").service_id
    status = core.health_pipeline.run(HealthProbeDTO(service_id=sid, cpu_usage_pct=99.0, memory_usage_mb=100))
    assert status == HealthStatus.DEGRADED


def test_health_probe_marks_healthy_under_threshold(core):
    core.registration_pipeline.run(manifest(name="organ.test.health2"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.health2").service_id
    status = core.health_pipeline.run(HealthProbeDTO(service_id=sid, cpu_usage_pct=10.0, memory_usage_mb=100))
    assert status == HealthStatus.HEALTHY


def test_recovery_manager_disables_after_max_attempts(core):
    core.registration_pipeline.run(manifest(name="organ.test.crashy"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.crashy").service_id
    core.startup_pipeline.run(sid)
    record = core.db.get(sid)
    record.restart_attempts = 3
    core.db.update(record)
    core.recovery_pipeline.run(FailureAlertDTO(service_id=sid, failure_type=FailureType.CRASH, reason="x"))
    assert core.db.get(sid).status == ServiceState.DISABLED


def test_recovery_manager_schedules_restart_within_limits(core):
    core.registration_pipeline.run(manifest(name="organ.test.recoverable"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.recoverable").service_id
    core.startup_pipeline.run(sid)
    core.recovery_pipeline.run(FailureAlertDTO(service_id=sid, failure_type=FailureType.CRASH, reason="x"))
    assert core.db.get(sid).status == ServiceState.RECOVERING


# ---- SemVer ---------------------------------------------------------------

@pytest.mark.parametrize("version,constraint,expected", [
    ("2.1.0", ">=2.1.0", True),
    ("2.0.9", ">=2.1.0", False),
    ("1.5.0", "^1.2.0", True),
    ("2.0.0", "^1.2.0", False),
    ("1.2.9", "~1.2.0", True),
    ("1.3.0", "~1.2.0", False),
])
def test_semver_satisfies(version, constraint, expected):
    assert SemVerParser.satisfies(version, constraint) is expected


def test_semver_malformed_raises():
    with pytest.raises(VersionIncompatibleError):
        SemVerParser.parse("not-a-version")


# ---- Boot / Shutdown / Monitoring / Metrics --------------------------------

def test_boot_starts_services_in_dependency_order(core):
    core.registration_pipeline.run(manifest(name="organ.test.boot_base"), "LEVEL_3_ADMIN")
    core.registration_pipeline.run(
        manifest(name="organ.test.boot_child",
                 deps=[{"service_name": "organ.test.boot_base", "version_range": ""}]),
        "LEVEL_3_ADMIN",
    )
    started = core.boot()
    assert len(started) == 2
    for sid in started:
        assert core.db.get(sid).status == ServiceState.RUNNING


def test_monitoring_pipeline_aggregates(core):
    core.registration_pipeline.run(manifest(name="organ.test.mon"), "LEVEL_3_ADMIN")
    report = core.monitoring_pipeline.run()
    assert report["service_count"] >= 1


def test_metrics_pipeline_counts_discovery(core):
    core.registration_pipeline.run(manifest(name="organ.test.metrics"), "LEVEL_3_ADMIN")
    core.discovery_pipeline.run(DiscoveryQueryDTO(service_name="organ.test.metrics", require_healthy=False))
    snapshot = core.metrics_pipeline.run()
    assert snapshot.counters.get("registry.discovery.requests", 0) >= 1


# ---- Sockets ----------------------------------------------------------------

def test_registration_socket_enforces_admin_scope(core):
    with pytest.raises(PermissionDeniedException):
        core.registration_socket.send(manifest(name="organ.test.socketfail"), PermissionLevel.LEVEL_0_PUBLIC)


def test_lifecycle_socket_start_stop(core):
    core.registration_pipeline.run(manifest(name="organ.test.socketlc"), "LEVEL_3_ADMIN")
    sid = core.db.get_by_name("organ.test.socketlc").service_id
    assert core.lifecycle_socket.send(("start", sid), PermissionLevel.LEVEL_4_KERNEL) is True
    assert core.lifecycle_socket.send(("stop", sid, True), PermissionLevel.LEVEL_4_KERNEL) is True


def test_dependency_socket_validate(core):
    core.registration_pipeline.run(manifest(name="organ.test.socketdep"), "LEVEL_3_ADMIN")
    assert core.dependency_socket.send(("validate",), PermissionLevel.LEVEL_1_INTERNAL) is True


def test_metrics_socket_public_access(core):
    result = core.metrics_socket.send((), PermissionLevel.LEVEL_0_PUBLIC)
    assert result is not None
