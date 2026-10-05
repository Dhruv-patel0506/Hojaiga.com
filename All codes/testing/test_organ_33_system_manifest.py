"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 33
Name: System Manifest

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [System Manifest]
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
Dependencies: pytest, asyncio, core_organs.organ_33_system_manifest...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_33_system_manifest.py]) --> output([Output Node])
```
"""

import asyncio
import pytest  # type: ignore
from core_organs.organ_33_system_manifest import (
    SystemManifest, ComponentMetadata, ComponentDependency, ComponentCategory,
    HealthStatus, LifecycleStage, satisfies_range, DependencyRegistry,
    CyclicDependencyError,
)


def make_meta(cid="hojaiga.organ.test", version="1.0.0", deps=None, cat=ComponentCategory.ORGAN):
    return ComponentMetadata(
        component_id=cid, component_name="test", display_name="Test Organ",
        description="A test organ for validation purposes.", category=cat,
        version=version, dependencies=deps or [], implementation_location="organ_test.py",
        documentation_file="Organ_Test.md",
    )


def test_register_success():
    sm = SystemManifest()
    resp = sm.register(make_meta())
    assert resp.success
    assert sm.get_component("hojaiga.organ.test")["component_id"] == "hojaiga.organ.test"


def test_duplicate_registration_rejected():
    sm = SystemManifest()
    sm.register(make_meta())
    resp = sm.register(make_meta())
    assert not resp.success
    assert "ERR_DUPLICATE_REGISTRATION" in resp.errors


def test_invalid_id_rejected():
    sm = SystemManifest()
    resp = sm.register(make_meta(cid="BadId"))
    assert not resp.success


def test_invalid_semver_rejected():
    sm = SystemManifest()
    resp = sm.register(make_meta(version="1.0"))
    assert not resp.success


def test_cyclic_dependency_detected():
    sm = SystemManifest()
    sm.register(make_meta("hojaiga.organ.a", deps=[ComponentDependency("hojaiga.organ.b", "*", False)]))
    resp = sm.register(make_meta("hojaiga.organ.b", deps=[ComponentDependency("hojaiga.organ.a", "*", False)]))
    assert not resp.success
    assert any("CYCLIC" in e for e in resp.errors)


def test_dependency_resolution_missing():
    sm = SystemManifest()
    sm.register(make_meta("hojaiga.organ.a", deps=[ComponentDependency("hojaiga.organ.missing", "*", False)]))
    unresolved = sm.resolve_dependencies("hojaiga.organ.a")
    assert "hojaiga.organ.missing" in unresolved


def test_dependency_resolution_optional_ok():
    sm = SystemManifest()
    sm.register(make_meta("hojaiga.organ.a", deps=[ComponentDependency("hojaiga.organ.missing", "*", True)]))
    unresolved = sm.resolve_dependencies("hojaiga.organ.a")
    assert unresolved == []


def test_health_report_and_query():
    sm = SystemManifest()
    sm.register(make_meta())
    sm.report_health("hojaiga.organ.test", HealthStatus.HEALTHY)
    results = sm.discover(health_status=HealthStatus.HEALTHY)
    assert len(results) == 1


def test_discover_by_category():
    sm = SystemManifest()
    sm.register(make_meta("hojaiga.organ.a"))
    sm.register(make_meta("hojaiga.service.b", cat=ComponentCategory.SERVICE))
    organs = sm.discover(category=ComponentCategory.ORGAN)
    assert len(organs) == 1
    assert organs[0]["component_id"] == "hojaiga.organ.a"


def test_lifecycle_transition():
    sm = SystemManifest()
    sm.register(make_meta())
    sm.transition("hojaiga.organ.test", LifecycleStage.ACTIVATED)
    assert sm.get_component("hojaiga.organ.test")["lifecycle_status"] == "ACTIVATED"


def test_architecture_summary():
    sm = SystemManifest()
    sm.register(make_meta())
    summary = sm.architecture_summary()
    assert summary["total_components"] == 1
    assert "ORGAN" in summary["by_category"]


def test_export_import_roundtrip(tmp_path):
    sm = SystemManifest()
    sm.register(make_meta())
    path = tmp_path / "manifest.json"
    sm.export_to(str(path))
    assert path.exists()
    diff = sm.import_from(str(path))
    assert diff["added"] == []


def test_audit_chain_valid():
    sm = SystemManifest()
    sm.register(make_meta())
    sm.report_health("hojaiga.organ.test", HealthStatus.DEGRADED)
    assert sm.audit_chain_valid()
    assert len(sm.audit_history()) >= 2


def test_semver_range_matching():
    assert satisfies_range("1.4.2", "^1.2.0")
    assert not satisfies_range("2.0.0", "^1.2.0")
    assert satisfies_range("1.2.5", "~1.2.0")
    assert not satisfies_range("1.3.0", "~1.2.0")
    assert satisfies_range("1.2.0", "1.2.0")
    assert satisfies_range("9.9.9", "*")


def test_dependency_registry_cycle_detection_standalone():
    dr = DependencyRegistry()
    dr.declare("a", [ComponentDependency("b", "*", False)])
    dr.declare("b", [ComponentDependency("c", "*", False)])
    dr.declare("c", [ComponentDependency("a", "*", False)])
    with pytest.raises(CyclicDependencyError):
        dr.validate_no_cycles()


def test_unregister_component():
    sm = SystemManifest()
    sm.register(make_meta())
    sm.unregister("hojaiga.organ.test")
    with pytest.raises(Exception):
        sm.get_component("hojaiga.organ.test")


def test_socket_subscription_receives_registration_event():
    sm = SystemManifest()
    received = []
    sm.subscribe("RegistrationSocket", lambda msg: received.append(msg))
    sm.register(make_meta())
    assert len(received) == 1
    assert received[0]["success"]


def test_async_register_many():
    sm = SystemManifest()
    metas = [make_meta(f"hojaiga.organ.bulk{i}") for i in range(5)]
    results = asyncio.run(sm.register_many(metas))
    assert all(r.success for r in results)
    assert sm.architecture_summary()["total_components"] == 5


def test_unknown_component_health_update_raises():
    sm = SystemManifest()
    with pytest.raises(Exception):
        sm.report_health("hojaiga.organ.nonexistent", HealthStatus.HEALTHY)
