"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 25
Name: Error Catalog

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Error Catalog]
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
Dependencies: core_organs.organ_25_error_catalog, pytest, time, os, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_25_error_catalog.py]) --> output([Output Node])
```
"""

"""
Test Suite: Organ 25 — Error Catalog
Filename: test_organ_25_error_catalog.py
"""

import os
import time
import uuid

import pytest  # type: ignore

from core_organs.organ_25_error_catalog import (
    ErrorCatalogOrgan,
    ErrorCategory,
    SeverityLevel,
    RecoveryStrategyType,
    RetryAlgorithm,
    RetryPolicyConfig,
    AOSErrorDefinition,
    ErrorLifecycleState,
    ErrorCodeManager,
    RetryPolicyManager,
    CodeFormatError,
    UnregisteredErrorCodeError,
    SchemaValidationError,
    InvalidStateTransitionError,
    sanitize_text,
)


@pytest.fixture()
def organ(tmp_path):
    db_path = str(tmp_path / "history.db")
    o = ErrorCatalogOrgan(history_db_path=db_path)
    yield o
    o.shutdown()


# ---- Error Code Manager -------------------------------------------------

def test_code_format_valid():
    mgr = ErrorCodeManager()
    assert mgr.validate_format("SYS-0001")
    assert not mgr.validate_format("sys-0001")
    assert not mgr.validate_format("SYSTEM-1")


def test_prefix_mismatch_rejected():
    mgr = ErrorCodeManager()
    with pytest.raises(CodeFormatError):
        mgr.assert_category_prefix_match("SYS-0001", ErrorCategory.KERNEL)


# ---- Registry -------------------------------------------------------------

def test_standard_catalog_loaded(organ):
    assert organ.catalog_size() == 33
    assert organ.get_definition("SYS-0001") is not None
    assert organ.get_definition("RES-3003").severity == SeverityLevel.ERROR


def test_unregistered_code_raises(organ):
    with pytest.raises(UnregisteredErrorCodeError):
        organ.registry.require_definition("ZZZ-9999")


def test_duplicate_registration_rejected(organ):
    existing = organ.get_definition("SYS-0001")
    with pytest.raises(Exception):
        organ.register_custom_error(existing)


def test_register_custom_error(organ):
    definition = AOSErrorDefinition(
        error_id=str(uuid.uuid4()),
        error_code="AGT-9001",
        name="AgentGoalStalled",
        description="Agent goal loop made no progress within timeout.",
        category=ErrorCategory.AGENT,
        severity=SeverityLevel.WARNING,
        source_component="aos.agents.worker",
        possible_causes=("Unreachable sub-goal",),
        detection_method="Progress watchdog",
        recovery_strategy=RecoveryStrategyType.RETRY,
        retry_policy=RetryPolicyConfig(RetryAlgorithm.LINEAR_BACKOFF, 2, 100, 1000),
        user_message="An automated task made no progress and will retry.",
        developer_message="Agent goal loop stalled.",
        recommended_action="Inspect agent goal decomposition.",
        documentation_reference="https://docs.hojaiga.local/errors/AGT-9001",
        version="1.0.0",
        owner="Organ_10_Agents",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    assert organ.register_custom_error(definition) is True
    assert organ.get_definition("AGT-9001") is not None


# ---- Retry algorithms -------------------------------------------------------

def test_immediate_backoff_zero():
    rp = RetryPolicyManager()
    policy = RetryPolicyConfig(RetryAlgorithm.IMMEDIATE, 3, 100, 1000)
    assert rp.calculate_backoff(policy, 1) == 0.0


def test_linear_backoff_caps():
    rp = RetryPolicyManager()
    policy = RetryPolicyConfig(RetryAlgorithm.LINEAR_BACKOFF, 5, 1000, 2000)
    assert rp.calculate_backoff(policy, 1) == pytest.approx(1.0)
    assert rp.calculate_backoff(policy, 10) == pytest.approx(2.0)


def test_exponential_backoff_within_jitter_bounds():
    rp = RetryPolicyManager()
    policy = RetryPolicyConfig(RetryAlgorithm.EXPONENTIAL_BACKOFF, 5, 1000, 60000)
    for attempt in range(1, 6):
        delay = rp.calculate_backoff(policy, attempt)
        base = min(1.0 * (2 ** (attempt - 1)), 60.0)
        assert 0.5 * base <= delay <= 1.5 * base


# ---- Lifecycle / state machine ---------------------------------------------

def test_emit_error_success_path_archives(organ):
    instance = organ.emit_error(
        "SCH-4001",
        context={"task_id": "abc"},
        execution_context={"retry_target": lambda: True},
    )
    assert instance.state == ErrorLifecycleState.ARCHIVED
    assert instance.attempt_count == 1


def test_emit_error_no_recovery_needed_for_warning(organ):
    instance = organ.emit_error("USR-9901", context={"field": "x"})
    assert instance.state == ErrorLifecycleState.ARCHIVED


def test_emit_error_escalates_to_safe_mode(organ):
    instance = organ.emit_error("SEC-9802")
    assert instance.state == ErrorLifecycleState.ARCHIVED
    assert "SAFE_MODE" in [s for s, _ in instance.history]


def test_illegal_transition_raises(organ):
    instance = organ.emit_error("USR-9901")
    with pytest.raises(InvalidStateTransitionError):
        instance.transition(ErrorLifecycleState.DETECTED)


def test_emit_unregistered_code_raises(organ):
    with pytest.raises(UnregisteredErrorCodeError):
        organ.emit_error("ZZZ-0000")


# ---- Validation -------------------------------------------------------------

def test_validation_rejects_missing_correlation(organ):
    ok, reason = organ.validation_manager.validate_instance_payload(
        {"error_code": "SYS-0001", "trace_id": "t1"}
    )
    assert ok is False
    assert "correlation_id" in reason


def test_definition_validation_rejects_bad_version():
    bad = AOSErrorDefinition(
        error_id=str(uuid.uuid4()),
        error_code="AGT-9002",
        name="Bad",
        description="d",
        category=ErrorCategory.AGENT,
        severity=SeverityLevel.INFO,
        source_component="x",
        possible_causes=("c",),
        detection_method="d",
        recovery_strategy=RecoveryStrategyType.ABORT,
        retry_policy=RetryPolicyConfig(RetryAlgorithm.NONE, 0, 0, 0),
        user_message="u",
        developer_message="d",
        recommended_action="a",
        documentation_reference="https://x",
        version="not-semver",
        owner="o",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    o = ErrorCatalogOrgan()
    with pytest.raises(SchemaValidationError):
        o.register_custom_error(bad)
    o.shutdown()


# ---- Metrics / Monitoring ----------------------------------------------------

def test_metrics_snapshot_reports_counts(organ):
    organ.emit_error("SCH-4001", execution_context={"retry_target": lambda: True})
    organ.emit_error("SCH-4001", execution_context={"retry_target": lambda: True})
    snap = organ.metrics_snapshot()
    assert snap["error_count"]["SCH-4001"] == 2


def test_monitoring_alert_triggers_on_burst(organ):
    for _ in range(60):
        organ.emit_error("USR-9901")
    assert len(organ.alerts()) >= 1


# ---- Audit --------------------------------------------------------------------

def test_audit_chain_verifies(organ):
    organ.emit_error("SEC-9802")
    assert organ.verify_audit_integrity() is True


def test_audit_trail_nonempty_for_critical(organ):
    organ.emit_error("RES-3001", auto_recover=False)
    trail = organ.audit_trail()
    assert any(e["event"]["error_code"] == "RES-3001" for e in trail)


# ---- History --------------------------------------------------------------------

def test_history_query_by_code(organ):
    organ.emit_error("USR-9901")
    organ.emit_error("SCH-4001", execution_context={"retry_target": lambda: True})
    records = organ.query_history(error_code="USR-9901")
    assert all(r["error_code"] == "USR-9901" for r in records)
    assert len(records) >= 1


def test_history_persists_to_sqlite(tmp_path):
    db_path = str(tmp_path / "persist.db")
    o = ErrorCatalogOrgan(history_db_path=db_path)
    o.emit_error("USR-9901")
    o.shutdown()
    assert os.path.exists(db_path)


# ---- Localization -----------------------------------------------------------

def test_localized_message_defaults_to_user_message(organ):
    msg = organ.localized_user_message("SYS-0001")
    assert "AOS" in msg or "start" in msg.lower()


def test_localized_message_with_params(organ):
    organ.localization_manager.register_locale_strings(
        "en_US", {"USR-9901": "Invalid request: {field}"}
    )
    msg = organ.localized_user_message("USR-9901", field="email")
    assert msg == "Invalid request: email"


# ---- Compatibility ------------------------------------------------------------

def test_compatibility_alias_resolves(organ):
    organ.compatibility_manager.register_alias("LEGACY-001", "SYS-0001")
    instance = organ.emit_error("LEGACY-001", auto_recover=False)
    assert instance.error_code == "SYS-0001"


# ---- Sanitization -------------------------------------------------------------

def test_sanitize_text_masks_secrets():
    raw = 'token="abc123" password="hunter2"'
    cleaned = sanitize_text(raw)
    assert "abc123" not in cleaned
    assert "hunter2" not in cleaned
    assert "REDACTED" in cleaned


# ---- Performance smoke test ---------------------------------------------------

def test_registry_lookup_latency(organ):
    start = time.perf_counter()
    for _ in range(1000):
        organ.get_definition("SYS-0001")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 50.0
