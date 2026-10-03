"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 23
Name: Test

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Test]
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
Dependencies: pytest, core_organs.organ_23, __future__, os...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_23_test.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
ORGAN 23 TEST SUITE — DEPENDENCY GRAPH (AOS-DEP)
Unit, integration, and chaos-style tests per Organ Specification
Section "Testing" and Dependency_Graph.md Section 12.3.
"""


import pytest  # type: ignore

from core_organs.organ_23 import (
    AOSDependencyRecord,
    CapabilityResolutionError,
    CircularDependencyDetector,
    ComponentMeta,
    ComponentState,
    CycleDetectedError,
    DependencyGraphOrgan,
    DependencyStrength,
    DependencyType,
    FailureImpact,
    MatrixMismatchError,
    NotFoundError,
    ResolutionError,
    TopologicalResolver,
    ValidationError,
    VersionCompatibilityEngine,
)


def make_record(source: str, target: str, **overrides) -> AOSDependencyRecord:
    defaults = dict(
        source_component=source,
        target_component=target,
        dependency_type=DependencyType.SERVICE,
        dependency_strength=DependencyStrength.MANDATORY,
        version_requirement="^1.0.0",
        compatibility_range="1.x",
        priority=100,
        startup_order=0,
        shutdown_order=0,
        recovery_order=0,
        failure_impact=FailureImpact.FATAL,
        owner="test-suite",
    )
    defaults.update(overrides)
    return AOSDependencyRecord(**defaults)


@pytest.fixture
def organ():
    o = DependencyGraphOrgan(db_path=":memory:")
    yield o
    o.shutdown()


# ---------------------------------------------------------------------
# UNIT TESTS — algorithms
# ---------------------------------------------------------------------

class TestRecordSchema:
    def test_valid_record(self):
        r = make_record("organ:brain", "organ:memory")
        assert r.dependency_id

    def test_invalid_component_pattern(self):
        with pytest.raises(ValidationError):
            make_record("Bad Component", "organ:memory")

    def test_priority_bounds(self):
        with pytest.raises(ValidationError):
            make_record("organ:a", "organ:b", priority=5000)

    def test_conditional_requires_expression(self):
        with pytest.raises(ValidationError):
            make_record(
                "organ:a", "organ:b", dependency_strength=DependencyStrength.CONDITIONAL
            )

    def test_self_dependency_rejected_by_validator(self, organ):
        r = make_record("organ:a", "organ:a")
        with pytest.raises(ValidationError):
            organ.register_dependency(r)


class TestCircularDependencyDetector:
    def test_no_cycle(self):
        detector = CircularDependencyDetector()
        graph = {"a": ["b"], "b": ["c"], "c": []}
        assert detector.detect_cycles(graph) == []
        detector.assert_acyclic(graph)

    def test_simple_cycle(self):
        detector = CircularDependencyDetector()
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 1
        with pytest.raises(CycleDetectedError):
            detector.assert_acyclic(graph)

    def test_self_loop_detected(self):
        detector = CircularDependencyDetector()
        graph = {"a": ["a"]}
        cycles = detector.detect_cycles(graph)
        assert cycles == [["a"]]


class TestTopologicalResolver:
    def test_resolve_execution_order(self):
        resolver = TopologicalResolver()
        edges = [make_record("organ:a", "organ:b"), make_record("organ:b", "organ:c")]
        order = resolver.resolve_execution_order(["organ:a", "organ:b", "organ:c"], edges)
        assert order.index("organ:c") < order.index("organ:b") < order.index("organ:a")

    def test_unresolvable_mandatory_cycle(self):
        resolver = TopologicalResolver()
        edges = [make_record("organ:a", "organ:b"), make_record("organ:b", "organ:a")]
        with pytest.raises(ResolutionError):
            resolver.resolve_execution_order(["organ:a", "organ:b"], edges)

    def test_optional_edges_excluded_from_ordering_constraints(self):
        resolver = TopologicalResolver()
        edges = [
            make_record("organ:a", "organ:b", dependency_strength=DependencyStrength.OPTIONAL)
        ]
        order = resolver.resolve_execution_order(["organ:a", "organ:b"], edges)
        assert set(order) == {"organ:a", "organ:b"}

    def test_resolve_capability(self):
        resolver = TopologicalResolver()
        providers = {
            "record_session": [
                ComponentMeta("plugin:obs", state=ComponentState.INITIALIZED),
                ComponentMeta("plugin:zoom", state=ComponentState.FAILED),
            ]
        }
        chosen = resolver.resolve_capability("record_session", providers)
        assert chosen == "plugin:obs"

    def test_resolve_capability_no_healthy_provider(self):
        resolver = TopologicalResolver()
        providers = {"x": [ComponentMeta("plugin:a", state=ComponentState.FAILED)]}
        with pytest.raises(CapabilityResolutionError):
            resolver.resolve_capability("x", providers)


class TestVersionCompatibilityEngine:
    def setup_method(self):
        self.engine = VersionCompatibilityEngine()

    def test_caret_compatible(self):
        assert self.engine.evaluate_compatibility("1.4.2", "^1.2.0").compatible

    def test_caret_incompatible_major(self):
        assert not self.engine.evaluate_compatibility("2.0.0", "^1.2.0").compatible

    def test_gte(self):
        assert self.engine.evaluate_compatibility("2.0.0", ">=2.0.0").compatible

    def test_exact_mismatch(self):
        assert not self.engine.evaluate_compatibility("1.0.1", "1.0.0").compatible

    def test_invalid_matrix_raises(self):
        with pytest.raises(MatrixMismatchError):
            self.engine.validate_matrix({"c": ("1.0.0", "^2.0.0")})


# ---------------------------------------------------------------------
# INTEGRATION TESTS — organ facade, sockets, persistence
# ---------------------------------------------------------------------

class TestOrganIntegration:
    def test_register_and_get(self, organ):
        r = make_record("organ:brain", "organ:memory")
        dep_id = organ.register_dependency(r)
        fetched = organ.get_dependency(dep_id)
        assert fetched.source_component == "organ:brain"

    def test_register_publishes_socket_event(self, organ):
        received = []
        organ.socket_bus.subscribe("dep_core", received.append)
        r = make_record("organ:brain", "organ:memory")
        organ.register_dependency(r)
        assert received and received[0]["event"] == "REGISTERED"

    def test_duplicate_edge_rejected(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        with pytest.raises(ValidationError):
            organ.register_dependency(make_record("organ:a", "organ:b"))

    def test_cycle_rejected_at_registration(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        organ.register_dependency(make_record("organ:b", "organ:c"))
        with pytest.raises(CycleDetectedError):
            organ.register_dependency(make_record("organ:c", "organ:a"))

    def test_unregister(self, organ):
        dep_id = organ.register_dependency(make_record("organ:a", "organ:b"))
        assert organ.unregister_dependency(dep_id) is True
        with pytest.raises(NotFoundError):
            organ.get_dependency(dep_id)

    def test_startup_sequence_waves(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        organ.register_dependency(make_record("organ:b", "organ:c"))
        seq = organ.compute_startup_sequence()
        flat = [n for wave in seq.waves for n in wave]
        assert flat.index("organ:c") < flat.index("organ:b") < flat.index("organ:a")

    def test_shutdown_sequence_is_reverse_of_startup(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        startup = organ.compute_startup_sequence()
        shutdown = organ.compute_shutdown_sequence()
        assert shutdown.waves[0] == startup.waves[-1]

    def test_persistence_round_trip(self):
        db_path = "/tmp/organ23_test.db"
        import os
        if os.path.exists(db_path):
            os.remove(db_path)
        o1 = DependencyGraphOrgan(db_path=db_path)
        o1.register_dependency(make_record("organ:a", "organ:b"))
        o1.shutdown()

        o2 = DependencyGraphOrgan(db_path=db_path)
        records = o2.registry.all_records()
        assert len(records) == 1
        o2.shutdown()
        os.remove(db_path)

    def test_upgrade_and_rollback(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        plan = organ.plan_upgrade("organ:b", "2.0.0")
        assert plan["target_component"] == "organ:b"
        organ.unregister_dependency(list(organ.registry.all_records())[0].dependency_id)
        organ.rollback(plan["rollback_checkpoint"])
        assert len(organ.registry.all_records()) == 1


# ---------------------------------------------------------------------
# CHAOS TESTS — component crash / recovery planning
# ---------------------------------------------------------------------

class TestRecovery:
    def test_recovery_plan_blast_radius(self, organ):
        organ.register_dependency(make_record("organ:consumer", "organ:core"))
        organ.register_dependency(make_record("organ:edge", "organ:consumer"))
        plan = organ.handle_component_failure("organ:core")
        assert "organ:consumer" in plan.quarantined
        assert "organ:edge" in plan.quarantined

    def test_recovery_plan_isolated_failure_has_no_dependents(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        plan = organ.handle_component_failure("organ:b")
        assert plan.quarantined == ["organ:a"]

    def test_repeated_failure_handling_is_stable(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        for _ in range(5):
            plan = organ.handle_component_failure("organ:b")
            assert plan.failed_component == "organ:b"


# ---------------------------------------------------------------------
# GRAPH-WIDE VALIDATION
# ---------------------------------------------------------------------

class TestGraphValidation:
    def test_validate_full_graph_ok(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        organ.validate_full_graph()

    def test_detect_cycles_empty_when_none(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        assert organ.detect_cycles() == []

    def test_status_report(self, organ):
        organ.register_dependency(make_record("organ:a", "organ:b"))
        status = organ.status()
        assert status["metrics"]["registrations"] == 1
        assert status["health"]["total_edges"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
