"""
Hojaiga Autonomous Agent - The "Third Human Hand"

This is the main orchestrator that makes Hojaiga a truly autonomous agent capable of
handling ANY task the user gives - no hardcoded scenarios.

Features:
- Universal task understanding (not limited to email/docs/apps)
- Dynamic workflow generation
- Flexible execution across multiple organs
- Intelligent decision making
- Detailed report generation (5-9 pages, Times New Roman 12pt)
- User confirmation for critical actions
- Handles: document reading, lead scraping, app automation, data processing, research, etc.
"""

import asyncio
import logging
import sys
from datetime import timedelta
from typing import Any, Dict, List, Optional

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_46_task_understanding import (
    UniversalTaskParser, TaskWorkflow, TaskType, ActionType
)
from core_organs.organ_52_report_generator import ReportGenerator
from core_organs.visual_cursor import VisualCursor
from core_organs.organ_54_brainstorming import BrainstormingOrgan, DiagramType
from core_organs.organ_55_warning_system import WarningSystem
from core_organs.organ_56_task_reducer import TaskReducer, TaskCategory, TaskPriority
from core_organs.organ_57_workflow_automation import WorkflowEngine, NodeType, TriggerType
from core_organs.organ_58_api_integration import APIIntegrationHub, ServiceType, OperationType
from core_organs.organ_59_hybrid_bridge import HybridCloudDesktopBridge, BridgeDirection, SyncType
from core_organs.organ_60_ai_optimizer import AIWorkflowOptimizer, OptimizationType
from core_organs.organ_61_web_packages import WebPackageIntegration
from core_organs.organ_62_confirmation_dialog import UserConfirmationDialog

logger = logging.getLogger("hojaiga.autonomous_agent")


class HojaigaAutonomousAgent:
    """
    The "Third Human Hand" - Fully autonomous agent for ANY task.
    
    Features:
    - Understands ANY natural language task
    - Plans execution dynamically
    - Executes across multiple organs
    - Makes intelligent decisions
    - Asks for confirmation when needed
    - Generates detailed reports
    """
    
    def __init__(self):
        self.task_parser = UniversalTaskParser()
        self.report_generator = ReportGenerator()
        self.visual_cursor = VisualCursor()
        self.brainstorming_organ = BrainstormingOrgan()
        self.warning_system = WarningSystem()
        self.task_reducer = TaskReducer()
        self.workflow_engine = WorkflowEngine()
        self.api_hub = APIIntegrationHub()
        self.hybrid_bridge = HybridCloudDesktopBridge()
        self.ai_optimizer = AIWorkflowOptimizer()
        self.web_packages = WebPackageIntegration()
        self.confirmation_dialog = UserConfirmationDialog()
        self._organs = {}
        self._current_task: Optional[TaskWorkflow] = None
        self._execution_history: List[Dict[str, Any]] = []
    
    async def initialize(self):
        """Initialize the autonomous agent."""
        logger.info("[AutonomousAgent] Initializing Hojaiga Autonomous Agent")
        
        # Visual cursor is already initialized in __init__
        logger.info("[AutonomousAgent] Visual cursor ready")
        
        # Initialize scanner, popup, and fallback organs with cursor
        try:
            from core_organs.organ_41_scanner import ScannerOrgan
            from core_organs.organ_42_navigation_popup import NavigationPopupOrgan
            from core_organs.organ_43_fallback import FallbackOrgan
            
            self.scanner = ScannerOrgan()
            self.popup_handler = NavigationPopupOrgan(scanner_organ=self.scanner)
            self.fallback_handler = FallbackOrgan()
            
            # Integrate visual cursor
            self.scanner.set_visual_cursor(self.visual_cursor)
            self.popup_handler.set_visual_cursor(self.visual_cursor)
            self.fallback_handler.set_visual_cursor(self.visual_cursor)
            
            logger.info("[AutonomousAgent] Scanner, popup, and fallback organs initialized")
        except Exception as e:
            logger.warning(f"[AutonomousAgent] Could not initialize scanner/popup/fallback: {e}")
            self.scanner = None
            self.popup_handler = None
            self.fallback_handler = None
        
        # Initialize actual organs (placeholder loading - would load real instances)
        logger.info("[AutonomousAgent] Initializing organ connections...")
        self._organs = {
            "CDP": None,  # Would be organ_19
            "DAP": None,  # Would be organ_24
            "LLM": None,  # Would be organ_37
            "Vision": None,  # Would be organ_31
            "AppLauncher": None,  # Would be organ_40
        }
        
        # Configure task parser with actual organs
        self.task_parser.set_cdp_runtime(self._organs["CDP"])
        self.task_parser.set_dap_runtime(self._organs["DAP"])
        self.task_parser.set_llm_gateway(self._organs["LLM"])
        self.task_parser.set_vision_organ(self._organs["Vision"])
        self.task_parser.set_app_launcher(self._organs["AppLauncher"])
        
        logger.info("[AutonomousAgent] Initialization complete")
    
    async def brainstorm_project(self, project_description: str) -> Dict[str, Any]:
        """
        Brainstorm a project with diagrams and visualizations.
        
        Args:
            project_description: Project to brainstorm
        
        Returns:
            Brainstorming results with diagrams
        """
        logger.info(f"[AutonomousAgent] Brainstorming project: {project_description}")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        result = await self.brainstorming_organ.brainstorm_project(project_description)
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def brief_document(self, document_path: str, detail_level: str = "maximum") -> Dict[str, Any]:
        """
        Brief a document in detail.
        
        Args:
            document_path: Path to document
            detail_level: Level of detail (brief, standard, maximum)
        
        Returns:
            Document briefing
        """
        logger.info(f"[AutonomousAgent] Briefing document: {document_path}")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        result = await self.task_reducer.brief_document(document_path, detail_level)
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def explain_report(self, report_path: str) -> Dict[str, Any]:
        """
        Explain a report in detail.
        
        Args:
            report_path: Path to report
        
        Returns:
            Report explanation
        """
        logger.info(f"[AutonomousAgent] Explaining report: {report_path}")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        result = await self.task_reducer.explain_report(report_path)
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def add_daily_task(self, description: str, category: str,
                           priority: str = "medium",
                           recurring: bool = False,
                           recurring_interval_hours: Optional[int] = None) -> str:
        """
        Add a daily automation task.
        
        Args:
            description: Task description
            category: Task category
            priority: Task priority
            recurring: Whether task recurs
            recurring_interval_hours: How often task recurs (in hours)
        
        Returns:
            Task ID
        """
        logger.info(f"[AutonomousAgent] Adding daily task: {description}")
        
        # Map strings to enums
        category_map = {
            "document_processing": TaskCategory.DOCUMENT_PROCESSING,
            "email_management": TaskCategory.EMAIL_MANAGEMENT,
            "data_entry": TaskCategory.DATA_ENTRY,
            "report_generation": TaskCategory.REPORT_GENERATION,
            "system_maintenance": TaskCategory.SYSTEM_MAINTENANCE,
            "file_organization": TaskCategory.FILE_ORGANIZATION,
            "web_automation": TaskCategory.WEB_AUTOMATION,
            "app_automation": TaskCategory.APP_AUTOMATION,
            "research": TaskCategory.RESEARCH,
            "communication": TaskCategory.COMMUNICATION,
            "general": TaskCategory.GENERAL,
        }
        
        priority_map = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
            "routine": TaskPriority.ROUTINE,
        }
        
        task_category = category_map.get(category.lower(), TaskCategory.GENERAL)
        task_priority = priority_map.get(priority.lower(), TaskPriority.MEDIUM)
        
        recurring_interval = None
        if recurring and recurring_interval_hours:
            recurring_interval = timedelta(hours=recurring_interval_hours)
        
        task_id = await self.task_reducer.add_task(
            description=description,
            category=task_category,
            priority=task_priority,
            recurring=recurring,
            recurring_interval=recurring_interval
        )
        
        return task_id
    
    async def process_daily_tasks(self) -> Dict[str, Any]:
        """Process all pending daily tasks."""
        logger.info("[AutonomousAgent] Processing daily tasks")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        
        result = await self.task_reducer.process_daily_tasks()
        
        return result
    
    async def create_workflow(self, name: str, description: str = "") -> str:
        """
        Create a workflow (n8n/Zapier/Make competitor).
        
        Args:
            name: Workflow name
            description: Workflow description
        
        Returns:
            Workflow ID
        """
        logger.info(f"[AutonomousAgent] Creating workflow: {name}")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        workflow_id = await self.workflow_engine.create_workflow(name, description)
        
        self.visual_cursor.set_buffering(False)
        
        return workflow_id
    
    async def add_workflow_node(self, workflow_id: str, node_type: str, name: str,
                             config: Dict[str, Any] = None) -> str:
        """Add a node to a workflow."""
        node_type_enum = NodeType(node_type)
        node_id = await self.workflow_engine.add_node(workflow_id, node_type_enum, name, config)
        return node_id
    
    async def execute_workflow(self, workflow_id: str, trigger_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a workflow."""
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        
        result = await self.workflow_engine.execute_workflow(workflow_id, trigger_data)
        
        return result
    
    async def execute_api_operation(self, service: str, operation: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute API operation (Gmail, Slack, GitHub, etc.).
        
        Args:
            service: Service name (gmail, slack, github, etc.)
            operation: Operation type (read, write, send, etc.)
            params: Operation parameters
        
        Returns:
            Operation result
        """
        logger.info(f"[AutonomousAgent] Executing API operation: {service}.{operation}")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        service_enum = ServiceType(service)
        operation_enum = OperationType(operation)
        
        if service_enum == ServiceType.GMAIL:
            result = await self.api_hub.execute_gmail_operation(operation_enum, params)
        elif service_enum == ServiceType.SLACK:
            result = await self.api_hub.execute_slack_operation(operation_enum, params)
        elif service_enum == ServiceType.GITHUB:
            result = await self.api_hub.execute_github_operation(operation_enum, params)
        elif service_enum == ServiceType.GOOGLE_SHEETS:
            result = await self.api_hub.execute_google_sheets_operation(operation_enum, params)
        else:
            result = {"success": False, "error": f"Service not implemented: {service}"}
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def create_bridge_rule(self, name: str, direction: str, sync_type: str,
                             trigger: str, cloud_service: str = "", desktop_path: str = "") -> str:
        """
        Create a hybrid cloud-desktop bridge rule (UNIQUE).
        
        Args:
            name: Rule name
            direction: Bridge direction (cloud_to_desktop, desktop_to_cloud, bidirectional)
            sync_type: Sync type (file_sync, data_sync, event_sync)
            trigger: Trigger type (webhook, file_change, manual)
            cloud_service: Cloud service name
            desktop_path: Desktop file/app path
        
        Returns:
            Rule ID
        """
        logger.info(f"[AutonomousAgent] Creating bridge rule: {name}")
        
        direction_enum = BridgeDirection(direction)
        sync_type_enum = SyncType(sync_type)
        trigger_enum = TriggerType(trigger)
        
        rule_id = await self.hybrid_bridge.create_bridge_rule(
            name, direction_enum, sync_type_enum, trigger_enum,
            cloud_service, desktop_path
        )
        
        return rule_id
    
    async def trigger_sync(self, rule_id: str, trigger_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Trigger a sync operation."""
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        result = await self.hybrid_bridge.trigger_sync(rule_id, trigger_data)
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def analyze_workflow(self, workflow_id: str, workflow_definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze workflow using AI (UNIQUE).
        
        Args:
            workflow_id: Workflow ID
            workflow_definition: Workflow definition
        
        Returns:
            Analysis results with issues and suggestions
        """
        logger.info(f"[AutonomousAgent] Analyzing workflow: {workflow_id}")
        
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        result = await self.ai_optimizer.analyze_workflow(workflow_id, workflow_definition)
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def auto_optimize_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Auto-optimize a workflow (UNIQUE - Self-healing)."""
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        self.visual_cursor.set_buffering(True)
        
        result = await self.ai_optimizer.auto_optimize_workflow(workflow_id)
        
        self.visual_cursor.set_buffering(False)
        
        return result
    
    async def execute_task(self, user_request: str) -> Dict[str, Any]:
        """
        Execute ANY task given by the user.
        
        Args:
            user_request: Natural language task description
        
        Returns:
            Execution results with report
        """
        logger.info(f"[AutonomousAgent] Received task: {user_request}")
        
        # Show visual cursor
        self.visual_cursor.show()
        self.visual_cursor.set_active_state("ACTIVE")
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Step 1: Understand task
            logger.info("[AutonomousAgent] Understanding task...")
            workflow = self.task_parser.parse_task(user_request)
            self._current_task = workflow
            
            logger.info(f"[AutonomousAgent] Task type: {workflow.task_type.value}")
            logger.info(f"[AutonomousAgent] Steps generated: {len(workflow.steps)}")
            
            # Step 2: Plan execution
            logger.info("[AutonomousAgent] Planning execution...")
            # (Planning is done in workflow generation)
            
            # Step 3: Execute workflow
            logger.info("[AutonomousAgent] Executing workflow...")
            execution_results = await self._execute_workflow(workflow)
            
            # Step 4: Generate report
            logger.info("[AutonomousAgent] Generating report...")
            duration = asyncio.get_event_loop(). time() - start_time
            execution_results["duration"] = duration
            
            report = self.report_generator.generate_report(
                task_id=workflow.task_id,
                original_request=user_request,
                task_type=workflow.task_type.value,
                execution_results=execution_results,
                context=workflow.context
            )
            
            # Save report
            report_path = self.report_generator.save_report(report)
            
            # Step 5: Request user review
            logger.info("[AutonomousAgent] Requesting user review...")
            await self._request_user_review(report, report_path)
            
            return {
                "task_id": workflow.task_id,
                "status": "completed",
                "task_type": workflow.task_type.value,
                "duration": duration,
                "report_path": report_path,
                "report": report,
                "execution_results": execution_results
            }
            
        except Exception as e:
            logger.error(f"[AutonomousAgent] Task execution failed: {e}", exc_info=True)
            return {
                "task_id": "unknown",
                "status": "failed",
                "error": str(e)
            }
    
    async def _execute_workflow(self, workflow: TaskWorkflow) -> Dict[str, Any]:
        """Execute a workflow (placeholder - would use actual execution engine)."""
        logger.info(f"[AutonomousAgent] Executing workflow with {len(workflow.steps)} steps")
        
        # Placeholder execution
        successful = 0
        results = []
        
        for step in workflow.steps:
            logger.info(f"[AutonomousAgent] Step {step.step_id}: {step.description}")
            
            # Update visual cursor state based on action
            if step.action == ActionType.LAUNCH:
                self.visual_cursor.set_active_state("ACTIVE")
                self.visual_cursor.set_buffering(True)
            elif step.action == ActionType.NAVIGATE:
                self.visual_cursor.set_active_state("MOVING")
                self.visual_cursor.set_buffering(False)
            elif step.action == ActionType.READ:
                self.visual_cursor.set_active_state("ACTIVE")
                self.visual_cursor.set_buffering(True)
            elif step.action == ActionType.CLICK:
                self.visual_cursor.set_active_state("CLICKING")
                self.visual_cursor.set_buffering(False)
            elif step.action == ActionType.TYPE:
                self.visual_cursor.set_active_state("DRAWING")
                self.visual_cursor.set_buffering(False)
            else:
                self.visual_cursor.set_active_state("ACTIVE")
                self.visual_cursor.set_buffering(False)
            
            # TODO: Actual execution using organ_52_report_generator
            # This would coordinate with actual organs
            await asyncio.sleep(0.5)  # Simulate execution time
            
            if step.requires_confirmation:
                confirmed = await self._request_confirmation(step)
                if not confirmed:
                    results.append({
                        "step_id": step.step_id,
                        "action": step.action.value,
                        "description": step.description,
                        "success": False,
                        "skipped": True
                    })
                else:
                    results.append({
                        "step_id": step.step_id,
                        "action": step.action.value,
                        "description": step.description,
                        "success": True
                    })
                    successful += 1
            else:
                results.append({
                    "step_id": step.step_id,
                    "action": step.action.value,
                    "description": step.description,
                    "success": True
                })
                successful += 1
        
        # Reset visual cursor
        self.visual_cursor.set_buffering(False)
        self.visual_cursor.set_active_state("ACTIVE")
        
        return {
            "total_steps": len(workflow.steps),
            "successful": successful,
            "results": results
        }
    
    async def _request_confirmation(self, step) -> bool:
        """Request user confirmation for a step."""
        logger.info(f"[AutonomousAgent] Confirmation requested for: {step.description}")
        
        if self.confirmation_dialog:
            result = await self.confirmation_dialog.ask_yes_no(
                title="Step Confirmation",
                message=f"Execute step: {step.description}\n\nAction: {step.action.value}"
            )
            confirmed = result.confirmed
        else:
            # Fallback to auto-confirm
            logger.info("[AutonomousAgent] Confirmation dialog not available, auto-confirming")
            confirmed = True
        
        return confirmed
    
    async def _request_user_review(self, report: str, report_path: str):
        """Request user review of the report."""
        logger.info(f"[AutonomousAgent] Report generated: {report_path}")
        logger.info("[AutonomousAgent] Please review the report and provide feedback.")
        logger.info("[AutonomousAgent] Report preview:")
        logger.info(report[:500] + "...")
        logger.info("[AutonomousAgent] (Full report saved to file)")
    
    def get_task_status(self) -> Dict[str, Any]:
        """Get current task status."""
        if self._current_task:
            return {
                "task_id": self._current_task.task_id,
                "original_request": self._current_task.original_request,
                "task_type": self._current_task.task_type.value,
                "steps_total": len(self._current_task.steps),
                "status": "in_progress"
            }
        return {"status": "idle"}


async def main():
    """Test the autonomous agent with various task types."""
    
    agent = HojaigaAutonomousAgent()
    await agent.initialize()
    
    # Test various task types
    test_tasks = [
        "Read the document at C:\\Users\\dhruv\\Documents\\report.pdf and summarize it to the maximum extent so I can understand easily, no details should be missed",
        "Scrape leads from LinkedIn and export to Excel",
        "Open the Notepad app (even if minimized) and type 'Hello World' then save it",
        "Go to https://example.com, read the content, and summarize it",
        "Open the Excel file at C:\\Users\\dhruv\\Documents\\data.xlsx, process the data, and export results",
        "Research the latest developments in AI and provide a summary",
    ]
    
    for task in test_tasks:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing task: {task}")
        logger.info(f"{'='*60}")
        
        result = await agent.execute_task(task)
        
        logger.info(f"\nResult: {result['status']}")
        logger.info(f"Task type: {result.get('task_type', 'unknown')}")
        logger.info(f"Duration: {result.get('duration', 0):.1f}s")
        logger.info(f"Report saved to: {result.get('report_path', 'N/A')}")
        
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
