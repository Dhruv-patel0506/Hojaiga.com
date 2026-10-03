"""
Hojaiga Automation OS - Core Runtime Module
=============================================

This package contains the core runtime components of the Hojaiga Automation OS,
including the kernel, task scheduling, system boot, resource management, and
service registry.

Components:
- kernel: Main kernel runtime
- system_boot: System initialization and startup
- task_scheduler: Task scheduling and orchestration
- infrastructure_organ: Infrastructure monitoring and management
- service_registry_organ: Service discovery and registration
- resource_manager: Resource allocation and management
- package_manager: Package/plugin management
- agents: Runtime agent management
"""

__version__ = "1.0.0"
__all__ = [
    "kernel",
    "system_boot",
    "task_scheduler",
    "infrastructure_organ",
    "service_registry_organ",
    "resource_manager",
    "package_manager",
    "agents",
]
