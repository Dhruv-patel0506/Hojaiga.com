"""
Hojaiga Automation OS - Testing Module
=======================================

This package contains comprehensive test suites for all components of the
Hojaiga Automation OS, including unit tests, integration tests, and validation
tests for each organ and core runtime component.

Test modules include:
- test_organ_*: Individual organ tests
- test_kernel: Kernel runtime tests
- test_infrastructure_organ: Infrastructure management tests
- test_task_scheduler: Task scheduling tests
- test_service_registry_organ: Service registry tests
- test_resource_manager: Resource management tests
- test_package_manager: Package manager tests
- test_voice_pipeline: Voice/STT pipeline tests
- test_configuration_*: Configuration system tests
"""

__version__ = "1.0.0"
__all__ = [
    "organ_23_test",
    "test_configuration_manager",
    "test_configuration_schema",
    "test_infrastructure_organ",
    "test_kernel",
    "test_organ16_audit_system",
    "test_organ_07_security",
    "test_organ_10_agents",
    "test_organ_13_interface_layer",
    "test_organ_14_llm_runtime",
    "test_organ_15_external_connectors",
    "test_organ_18_capability_registry",
    "test_organ_19_chrome_cdp_runtime",
    "test_organ_24_dap",
    "test_organ_25_error_catalog",
    "test_organ_26_event_catalog",
    "test_organ_29_popup_handler",
    "test_organ_32_state_catalog",
    "test_organ_33_system_manifest",
    "test_organ_35_update_manager",
    "test_organ_36_workflow_compiler",
    "test_package_manager",
    "test_resource_manager",
    "test_service_registry_organ",
    "test_task_scheduler",
    "test_voice_pipeline",
]
