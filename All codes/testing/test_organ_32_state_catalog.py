"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 32
Name: State Catalog

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [State Catalog]
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
Dependencies: pytest, core_organs.organ_32_state_catalog, asyncio...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_32_state_catalog.py]) --> output([Output Node])
```
"""

"""Pytest suite for Organ 32 — State Catalog (AOS-STC)."""

import asyncio

import pytest  # type: ignore

from core_organs.organ_32_state_catalog import (
    StateCatalogOrgan, EntityType, StateCategory, StateName,
    AuthError, ValidationError, LookupError_, DEFAULT_STATE_CATALOG,
    TRANSITION_MATRICES, SOCKET_REGISTRY, PIPELINE_REGISTRY,
)


@pytest.fixture
def organ():
    o = StateCatalogOrgan(db_path=":memory:")
    yield o
    o.shutdown()


# -- catalog completeness -------------------------------------------------

def test_all_31_states_present():
    assert len(DEFAULT_STATE_CATALOG) == 31


def test_all_entity_types_have_matrices():
    for et in EntityType:
        assert et in TRANSITION_MATRICES


def test_socket_registry_has_14_sockets():
    assert len(SOCKET_REGISTRY) == 14


def test_pipeline_registry_populated():
    assert len(PIPELINE_REGISTRY) >= 5


# -- registration -----------------------------------------------------

def test_register_entity_defaults_to_created(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    state = organ.get_state(eid)
    assert state["current_state"] == "CREATED"
    assert state["previous_state"] is None


def test_register_entity_with_explicit_id(organ):
    eid = organ.register_entity("task-1", EntityType.TASK, StateCategory.TASK)
    assert eid == "task-1"


def test_unregister_removes_entity(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    organ.unregister_entity(eid)
    with pytest.raises(LookupError_):
        organ.get_state(eid)


# -- valid transitions --------------------------------------------------

def test_task_created_to_queued_succeeds(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    result = organ.request_transition(
        eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR",
        triggering_vector="TEST")
    assert result["ok"] is True
    assert result["value"]["new_state"] == "QUEUED"


def test_task_full_happy_path(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    path = [StateName.QUEUED, StateName.WAITING, StateName.RUNNING,
            StateName.PROCESSING, StateName.COMPLETED, StateName.SUCCESS]
    for target in path:
        result = organ.request_transition(
            eid, target, subject_token="EXECUTION_ORCHESTRATOR", triggering_vector="TEST")
        assert result["ok"] is True, result
    assert organ.get_state(eid)["current_state"] == "SUCCESS"


def test_service_lifecycle(organ):
    eid = organ.register_entity(None, EntityType.SERVICE, StateCategory.SERVICE,
                                 initial_state=StateName.REGISTERED)
    for target in [StateName.INITIALIZING, StateName.STARTING, StateName.READY,
                   StateName.RUNNING, StateName.BUSY, StateName.RUNNING]:
        result = organ.request_transition(
            eid, target, subject_token="REGISTERED_SERVICE_MANAGER", triggering_vector="TEST")
        assert result["ok"] is True, result


# -- invalid transitions --------------------------------------------------

def test_illegal_jump_rejected(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    result = organ.request_transition(
        eid, StateName.SUCCESS, subject_token="EXECUTION_ORCHESTRATOR",
        triggering_vector="TEST")
    assert result["ok"] is False
    assert "ERR_INVALID_STATE_TRANSITION" in result["error"]


def test_unregistered_entity_transition_fails(organ):
    result = organ.request_transition(
        "ghost-entity", StateName.RUNNING, subject_token="SYSTEM")
    assert result["ok"] is False
    assert "ERR_ENTITY_NOT_FOUND" in result["error"]


# -- permission boundary --------------------------------------------------

def test_service_manager_cannot_force_kernel_state(organ):
    eid = organ.register_entity(None, EntityType.KERNEL, StateCategory.KERNEL,
                                 initial_state=StateName.CREATED)
    result = organ.request_transition(
        eid, StateName.VALIDATED, subject_token="REGISTERED_SERVICE_MANAGER",
        triggering_vector="TEST")
    assert result["ok"] is False
    assert "ERR_UNAUTHORIZED_STATE_REQUEST" in result["error"]


def test_kernel_core_may_mutate_kernel_state(organ):
    eid = organ.register_entity(None, EntityType.KERNEL, StateCategory.KERNEL,
                                 initial_state=StateName.CREATED)
    result = organ.request_transition(
        eid, StateName.VALIDATED, subject_token="AOS_MICRO_KERNEL_CORE",
        triggering_vector="TEST")
    assert result["ok"] is True


def test_task_manager_restricted_to_allowed_targets(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    # QUEUED is in the WORKFLOW_TASK allowed target set
    result = organ.request_transition(
        eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR")
    assert result["ok"] is True


# -- recovery -----------------------------------------------------------

def test_recovery_from_failed_state(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    organ.request_transition(eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR")
    organ.request_transition(eid, StateName.WAITING, subject_token="EXECUTION_ORCHESTRATOR")
    organ.request_transition(eid, StateName.RUNNING, subject_token="EXECUTION_ORCHESTRATOR")
    organ.request_transition(eid, StateName.PROCESSING, subject_token="EXECUTION_ORCHESTRATOR")
    organ.request_transition(eid, StateName.FAILED, subject_token="EXECUTION_ORCHESTRATOR")
    outcome = organ.initiate_recovery(eid, failure_cause="TEST_FAILURE")
    assert outcome["outcome"] in ("RECOVERING", "ROLLING_BACK")


def test_recovery_rejects_non_eligible_state(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    with pytest.raises(Exception):
        organ.initiate_recovery(eid, failure_cause="TEST")


# -- history / audit ------------------------------------------------------

def test_history_records_transitions(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    organ.request_transition(eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR")
    history = organ.query_entity_history(eid)
    assert len(history) == 2  # registration + one transition
    assert history[-1]["new_state"] == "QUEUED"


def test_history_hash_chain_integrity(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    organ.request_transition(eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR")
    organ.request_transition(eid, StateName.WAITING, subject_token="EXECUTION_ORCHESTRATOR")
    assert organ.verify_history_integrity() is True


# -- metrics ---------------------------------------------------------------

def test_metrics_summary_tracks_transitions(organ):
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    organ.request_transition(eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR")
    summary = organ.get_metrics_summary()
    assert summary["total_transitions"] >= 1


# -- monitor ----------------------------------------------------------------

def test_monitor_can_start_and_stop(organ):
    async def run():
        task = asyncio.create_task(organ.start_monitor())
        await asyncio.sleep(0.05)
        organ.stop_monitor()
        await task
    asyncio.run(run())


# -- documentation ------------------------------------------------------

def test_export_documentation_json(organ):
    doc = organ.export_documentation("json")
    assert "CREATED" in doc
    assert "version" in doc


def test_export_documentation_markdown(organ):
    doc = organ.export_documentation("markdown")
    assert doc.startswith("# AOS State Catalog Export")


# -- batch lookups ------------------------------------------------------

def test_batch_get_states(organ):
    e1 = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    e2 = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    result = organ.batch_get_states([e1, e2, "missing"])
    assert result[e1] == "CREATED"
    assert result[e2] == "CREATED"
    assert "missing" not in result
