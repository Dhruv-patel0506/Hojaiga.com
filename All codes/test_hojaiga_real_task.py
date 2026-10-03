"""
HOJAIGA AUTOMATION OS - MASTER TASK VALIDATION RUNNER
====================================================
File: test_hojaiga_real_task.py
Role: Comprehensive End-to-End Orchestrator & Multi-Organ Lifecycle Runner

Features:
- Initializes CNS EventBus and binds all 17 core organs.
- Dispatches user intent / real-world tasks across desktop and web layers.
- Listens to lifecycle events with deterministic watchdog timeouts.
- Produces clean telemetry, checkpoint verification, and exit codes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

# Core Organs & Observability Imports
from core_organs.organ_02_cns_single_file import CNSKernel, EventEnvelope
from core_organs.organ_01_brain import BrainOrgan
from core_organs.organ_22_decision_engine import DecisionEngineOrgan
from core_organs.organ_36_workflow_compiler import WorkflowCompilerKernel
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
from core_organs.organ_05_controllers import ControllersCore
from core_organs.organ_10_agents import AgentsOrgan
from core_organs.organ_13_interface_layer import InterfaceLayerOrgan
from core_organs.organ_31_visual_perception import VisualPerceptionOrgan
from core_organs.organ_30_app_scanner import AppScannerOrgan
from core_organs.organ_29_popup_handler import DesktopInteractionManager
from core_organs.organ_24_dap import DesktopAutomationProtocol
from core_organs.organ_12_integration import IntegrationOrgan
from core_organs.organ_32_state_catalog import StateCatalogOrgan
from observability.organ_16_audit_system import AuditSystem

# Configure Clean Logging Output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("hojaiga.test_runner")


class HojaigaTestRunner:
    def __init__(self, visualizer_enabled: bool = False, timeout_seconds: float = 120.0):
        self.visualizer_enabled = visualizer_enabled
        self.timeout_seconds = timeout_seconds
        self.completion_event = asyncio.Event()
        self.task_success = False
        self.task_error: Optional[str] = None
        self.task_id: Optional[str] = None

        # Organ Instances
        self.cns_kernel: Optional[CNSKernel] = None
        self.audit: Optional[AuditSystem] = None
        self.orchestrator: Optional[TaskOrchestrator] = None
        self.brain: Optional[BrainOrgan] = None
        self.decision: Optional[DecisionEngineOrgan] = None
        self.compiler: Optional[WorkflowCompilerKernel] = None
        self.controllers: Optional[ControllersCore] = None
        self.agents: Optional[AgentsOrgan] = None
        self.interface: Optional[InterfaceLayerOrgan] = None
        self.perception: Optional[VisualPerceptionOrgan] = None
        self.scanner: Optional[AppScannerOrgan] = None
        self.dim: Optional[DesktopInteractionManager] = None
        self.dap: Optional[DesktopAutomationProtocol] = None
        self.integration: Optional[IntegrationOrgan] = None
        self.state_catalog: Optional[StateCatalogOrgan] = None

    async def boot_system(self) -> None:
        """Initializes and interconnects all system organs over CNS."""
        logger.info("==================================================")
        logger.info("Initializing Hojaiga Automation OS Master Kernel...")
        logger.info("==================================================")

        # 1. Start CNS Master Kernel
        self.cns_kernel = CNSKernel()
        await self.cns_kernel.start()
        bus = self.cns_kernel.event_bus

        # 2. Initialize Audit & Security Mock
        self.audit = AuditSystem()
        security_guard = None

        # 3. Instantiate Organs
        self.orchestrator = TaskOrchestrator(bus, self.audit, security_guard)
        self.brain = BrainOrgan()
        self.decision = DecisionEngineOrgan()
        self.compiler = WorkflowCompilerKernel()
        self.controllers = ControllersCore()
        self.agents = AgentsOrgan()
        self.interface = InterfaceLayerOrgan()
        self.perception = VisualPerceptionOrgan()
        self.scanner = AppScannerOrgan()
        self.dim = DesktopInteractionManager()
        self.dap = DesktopAutomationProtocol()
        self.integration = IntegrationOrgan()
        self.state_catalog = StateCatalogOrgan()

        # 4. Connect Organs to CNS EventBus
        await self.orchestrator.start()
        await self.brain.start(bus)
        await self.decision.start_cns(bus)
        await self.compiler.start(bus)
        await self.controllers.start_cns(bus)
        await self.agents.start_cns(bus)
        await self.interface.start_cns(bus)
        await self.perception.start_cns(bus)
        await self.scanner.start_cns(bus)
        try:
            await self.dim.start_event_monitoring()
        except Exception as e:
            print(f"[WARN] Organ 29 event monitoring failed to start (non-critical): {e}")
        await self.dap.start()
        await self.integration.start_cns(bus)
        await self.state_catalog.start_cns(bus)

        # 5. Subscribe Runner to Lifecycle Completion Events
        await bus.subscribe("TASK_COMPLETED", "runner_listener", self._on_task_completed)
        await bus.subscribe("TASK_PERMANENTLY_FAILED", "runner_listener", self._on_task_failed)

        logger.info("All 17 Hojaiga core organs booted and synchronized.")

    async def _on_task_completed(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        self.task_id = payload.get("task_id")
        self.task_success = True
        logger.info(f"[RUNNER] Task {self.task_id} completed successfully.")
        self.completion_event.set()

    async def _on_task_failed(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        self.task_id = payload.get("task_id")
        self.task_success = False
        self.task_error = payload.get("error", "Unknown execution failure")
        logger.error(f"[RUNNER] Task {self.task_id} permanently failed: {self.task_error}")
        self.completion_event.set()

    async def execute_task(self, command: str) -> bool:
        """Submits task command and awaits verified execution."""
        logger.info(f"[RUNNER] Ingesting command: '{command}'")
        
        # Ensure system organs are booted before task submission
        if self.interface is None:
            logger.warning("[RUNNER] System interface not booted. Auto-booting system organs...")
            await self.boot_system()

        if self.interface is None:
            raise RuntimeError("[RUNNER] Failed to initialize InterfaceLayerOrgan. Ensure boot_system() succeeds.")

        # Ingest command through Organ 13 Interface
        self.task_id = await self.interface.submit_command(raw_command=command)

        # Await completion with watchdog timeout
        try:
            await asyncio.wait_for(self.completion_event.wait(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            logger.error(f"[RUNNER] Execution timed out after {self.timeout_seconds} seconds.")
            self.task_success = False
            self.task_error = "Watchdog timeout exceeded"

        return self.task_success

    async def shutdown(self) -> None:
        """Gracefully shuts down all organs and closes sockets."""
        logger.info("Initiating system shutdown...")
        if self.dap:
            await self.dap.stop()
        if self.perception:
            await self.perception.stop()
        if self.cns_kernel:
            await self.cns_kernel.shutdown()
        logger.info("Hojaiga Automation OS shutdown complete.")


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Hojaiga Automation OS Master Task Runner")
    parser.add_argument("--test", type=str, default="standard_off", help="Run mode (standard_off, standard_on, parallel_swarm)")
    parser.add_argument("--task", "--command", type=str, default="", dest="task", help="Custom task instruction string")
    parser.add_argument("--timeout", type=float, default=90.0, help="Task timeout in seconds")
    args = parser.parse_args()

    visualizer = "on" in args.test.lower()
    
    print("\n==================================================")
    print(f"Starting Real Task Validation: Standard Run (Vis {'ON' if visualizer else 'OFF'})")
    print(f"Visualizer Enabled: {visualizer}")
    print("==================================================\n")

    default_task = (
        "open obs studioa nd record the session for 30 sec and stop it "
        "as sson as the 30 sec hits and find me the folder where all the obs studio videos and screen reocrd are saved?"
    )
    task_command = args.task if args.task else default_task

    runner = HojaigaTestRunner(visualizer_enabled=visualizer, timeout_seconds=args.timeout)
    
    try:
        await runner.boot_system()
        success = await runner.execute_task(task_command)
        
        print("\n==================================================")
        print("                  ROLLUP REPORT                   ")
        print("==================================================")
        print(f"Task ID:          {runner.task_id}")
        print(f"Final Status:     {'SUCCESS (PASS)' if success else 'FAILED (CRITICAL)'}")
        if not success:
            print(f"Failure Reason:   {runner.task_error}")
        print("==================================================\n")

        sys.exit(0 if success else 1)
    finally:
        await runner.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execution cancelled by operator.")
        sys.exit(130)
