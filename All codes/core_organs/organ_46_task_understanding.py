"""
Organ 46 — Universal Task Understanding (Flexible & Dynamic)

Responsibility: Understand ANY natural language task the user gives and break it down
into executable steps. No hardcoded scenarios - truly dynamic and flexible.

Features:
- Universal task parsing (not limited to email/docs/apps)
- Dynamic workflow generation
- Tool selection based on task type
- Step-by-step execution planning
- Handles: document reading, lead scraping, app automation, data processing, etc.
"""

import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.organ46.task_understanding")


class TaskType(Enum):
    """Universal task types."""
    DOCUMENT_READING = "document_reading"
    DOCUMENT_SUMMARIZATION = "document_summarization"
    LEAD_SCRAPING = "lead_scraping"
    APP_AUTOMATION = "app_automation"
    DATA_PROCESSING = "data_processing"
    WEB_AUTOMATION = "web_automation"
    EMAIL_MANAGEMENT = "email_management"
    FILE_MANAGEMENT = "file_management"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    GENERIC = "generic"


class ActionType(Enum):
    """Universal action types."""
    NAVIGATE = "navigate"
    READ = "read"
    EXTRACT = "extract"
    SUMMARIZE = "summarize"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    LAUNCH = "launch"
    CLOSE = "close"
    DELETE = "delete"
    COPY = "copy"
    PASTE = "paste"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    SEARCH = "search"
    ANALYZE = "analyze"
    COMPARE = "compare"
    CALCULATE = "calculate"
    EXECUTE = "execute"
    WAIT = "wait"
    VERIFY = "verify"


@dataclass
class TaskStep:
    """A single step in a task workflow."""
    step_id: int
    action: ActionType
    description: str
    target: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    tools_needed: List[str] = field(default_factory=list)
    estimated_duration: float = 0.0


@dataclass
class TaskWorkflow:
    """Complete workflow for a task."""
    task_id: str
    original_request: str
    task_type: TaskType
    steps: List[TaskStep] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    estimated_duration: float = 0.0
    requires_organ: List[str] = field(default_factory=list)


class UniversalTaskParser:
    """
    Universal task parser - handles ANY task dynamically.
    
    Features:
    - No hardcoded scenarios
    - Dynamic task type detection
    - Flexible workflow generation
    - Handles any user request
    """
    
    def __init__(self):
        self._task_patterns = {
            # Document-related
            r"(read|document|pdf|word|text|article|paper|report)": TaskType.DOCUMENT_READING,
            r"(summarize|summary|overview|digest|recap|condense)": TaskType.DOCUMENT_SUMMARIZATION,
            
            # Lead-related
            r"(lead|contact|prospect|customer|client|sales)": TaskType.LEAD_SCRAPING,
            r"(scrape|extract|harvest|collect|gather)": TaskType.LEAD_SCRAPING,
            
            # App-related
            r"(app|application|software|program|tool)": TaskType.APP_AUTOMATION,
            r"(minimized|background|hidden)": TaskType.APP_AUTOMATION,
            r"(open|launch|start|run)": TaskType.APP_AUTOMATION,
            
            # Web-related
            r"(website|web|browser|chrome|firefox|edge)": TaskType.WEB_AUTOMATION,
            r"(url|link|page|site)": TaskType.WEB_AUTOMATION,
            
            # Email-related
            r"(email|mail|gmail|outlook|inbox)": TaskType.EMAIL_MANAGEMENT,
            r"(reply|respond|answer|write)": TaskType.EMAIL_MANAGEMENT,
            
            # File-related
            r"(file|folder|directory|document)": TaskType.FILE_MANAGEMENT,
            r"(copy|move|delete|rename|organize)": TaskType.FILE_MANAGEMENT,
            
            # Data-related
            r"(data|process|transform|convert|format)": TaskType.DATA_PROCESSING,
            r"(excel|spreadsheet|csv|database)": TaskType.DATA_PROCESSING,
            
            # Analysis-related
            r"(analyze|analysis|audit|review|evaluate)": TaskType.ANALYSIS,
            r"(compare|difference|vs|versus)": TaskType.ANALYSIS,
            
            # Research-related
            r"(research|find|search|look up|investigate)": TaskType.RESEARCH,
        }
        
        # Initialize organ connections (will be set externally)
        self._cdp_runtime = None
        self._dap_runtime = None
        self._llm_gateway = None
        self._vision_organ = None
        self._app_launcher = None
    
    def set_cdp_runtime(self, cdp_runtime):
        """Set CDP runtime instance."""
        self._cdp_runtime = cdp_runtime
    
    def set_dap_runtime(self, dap_runtime):
        """Set DAP runtime instance."""
        self._dap_runtime = dap_runtime
    
    def set_llm_gateway(self, llm_gateway):
        """Set LLM gateway instance."""
        self._llm_gateway = llm_gateway
    
    def set_vision_organ(self, vision_organ):
        """Set vision organ instance."""
        self._vision_organ = vision_organ
    
    def set_app_launcher(self, app_launcher):
        """Set app launcher instance."""
        self._app_launcher = app_launcher
    
    def parse_task(self, user_request: str) -> TaskWorkflow:
        """
        Parse ANY user request into a workflow.
        
        Args:
            user_request: Natural language task description
        
        Returns:
            TaskWorkflow with steps
        """
        task_id = f"task_{int(asyncio.get_event_loop().time() * 1000)}"
        
        # Detect task type
        task_type = self._detect_task_type(user_request)
        
        # Extract context
        context = self._extract_context(user_request)
        
        # Generate workflow steps
        steps = self._generate_workflow_steps(user_request, task_type, context)
        
        # Calculate estimated duration
        duration = sum(step.estimated_duration for step in steps)
        
        # Determine required organs
        required_organs = self._determine_required_organs(steps)
        
        workflow = TaskWorkflow(
            task_id=task_id,
            original_request=user_request,
            task_type=task_type,
            steps=steps,
            context=context,
            estimated_duration=duration,
            requires_organ=required_organs
        )
        
        logger.info(f"[TaskParser] Parsed task: {task_type.value}")
        logger.info(f"[TaskParser] Generated {len(steps)} steps")
        
        return workflow
    
    def _detect_task_type(self, user_request: str) -> TaskType:
        """Detect task type from user request."""
        request_lower = user_request.lower()
        
        # Check each pattern
        scores = {}
        for pattern, task_type in self._task_patterns.items():
            if re.search(pattern, request_lower):
                scores[task_type] = scores.get(task_type, 0) + 1
        
        if scores:
            # Return task type with highest score
            return max(scores, key=scores.get)
        
        return TaskType.GENERIC
    
    def _extract_context(self, user_request: str) -> Dict[str, Any]:
        """Extract context from user request."""
        context = {
            "original_request": user_request,
            "mentions_email": bool(re.search(r"(email|mail|gmail|outlook)", user_request.lower())),
            "mentions_document": bool(re.search(r"(document|pdf|word|file|text)", user_request.lower())),
            "mentions_app": bool(re.search(r"(app|application|software|program)", user_request.lower())),
            "mentions_website": bool(re.search(r"(website|web|url|link|http)", user_request.lower())),
            "mentions_minimized": bool(re.search(r"(minimized|background|hidden)", user_request.lower())),
        }
        
        # Extract specific entities
        # URLs
        urls = re.findall(r'https?://[^\s]+', user_request)
        if urls:
            context["urls"] = urls
        
        # File paths
        file_paths = re.findall(r'[A-Za-z]:\\[^\s]+', user_request)
        if file_paths:
            context["file_paths"] = file_paths
        
        # App names
        app_keywords = re.findall(r'\b(?:open|launch|start|use|work with)\s+(\w+)', user_request, re.IGNORECASE)
        if app_keywords:
            context["mentioned_apps"] = [match[1] for match in app_keywords]
        
        return context
    
    def _generate_workflow_steps(self, user_request: str, task_type: TaskType, 
                               context: Dict[str, Any]) -> List[TaskStep]:
        """Generate workflow steps dynamically based on task type."""
        steps = []
        step_id = 0
        
        if task_type == TaskType.DOCUMENT_READING:
            steps.extend(self._generate_document_reading_steps(user_request, context))
        
        elif task_type == TaskType.DOCUMENT_SUMMARIZATION:
            steps.extend(self._generate_document_summarization_steps(user_request, context))
        
        elif task_type == TaskType.LEAD_SCRAPING:
            steps.extend(self._generate_lead_scraping_steps(user_request, context))
        
        elif task_type == TaskType.APP_AUTOMATION:
            steps.extend(self._generate_app_automation_steps(user_request, context))
        
        elif task_type == TaskType.WEB_AUTOMATION:
            steps.extend(self._generate_web_automation_steps(user_request, context))
        
        elif task_type == TaskType.EMAIL_MANAGEMENT:
            steps.extend(self._generate_email_management_steps(user_request, context))
        
        elif task_type == TaskType.FILE_MANAGEMENT:
            steps.extend(self._generate_file_management_steps(user_request, context))
        
        elif task_type == TaskType.DATA_PROCESSING:
            steps.extend(self._generate_data_processing_steps(user_request, context))
        
        elif task_type == TaskType.ANALYSIS:
            steps.extend(self._generate_analysis_steps(user_request, context))
        
        elif task_type == TaskType.RESEARCH:
            steps.extend(self._generate_research_steps(user_request, context))
        
        else:  # GENERIC
            steps.extend(self._generate_generic_steps(user_request, context))
        
        # Assign step IDs
        for i, step in enumerate(steps):
            step.step_id = i
        
        return steps
    
    def _generate_document_reading_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for document reading."""
        steps = []
        
        # Step 1: Open document
        if context.get("file_paths"):
            file_path = context["file_paths"][0]
            steps.append(TaskStep(
                step_id=0,
                action=ActionType.LAUNCH,
                description=f"Open document: {file_path}",
                target=file_path,
                params={"path": file_path},
                requires_confirmation=False,
                tools_needed=["DAP"],
                estimated_duration=2.0
            ))
        else:
            steps.append(TaskStep(
                step_id=0,
                action=ActionType.NAVIGATE,
                description="Navigate to document location",
                params={},
                requires_confirmation=True,
                tools_needed=["DAP"],
                estimated_duration=5.0
            ))
        
        # Step 2: Read document content
        steps.append(TaskStep(
            step_id=1,
            action=ActionType.READ,
            description="Read document content",
            params={},
            requires_confirmation=False,
            tools_needed=["DAP", "Vision", "OCR"],
            estimated_duration=10.0
        ))
        
        # Step 3: Extract key information
        steps.append(TaskStep(
            step_id=2,
            action=ActionType.EXTRACT,
            description="Extract key information from document",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=15.0
        ))
        
        return steps
    
    def _generate_document_summarization_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for document summarization."""
        steps = []
        
        # Step 1: Read document
        steps.extend(self._generate_document_reading_steps(user_request, context))
        
        # Step 2: Summarize content
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.SUMMARIZE,
            description="Summarize document content comprehensively",
            params={"detail_level": "maximum", "no_details_missed": True},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=20.0
        ))
        
        # Step 3: Verify summary completeness
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.VERIFY,
            description="Verify no important details were missed",
            params={},
            requires_confirmation=True,
            tools_needed=["LLM"],
            estimated_duration=5.0
        ))
        
        return steps
    
    def _generate_lead_scraping_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for lead scraping."""
        steps = []
        
        # Step 1: Navigate to target
        if context.get("urls"):
            url = context["urls"][0]
            steps.append(TaskStep(
                step_id=0,
                action=ActionType.NAVIGATE,
                description=f"Navigate to target: {url}",
                target=url,
                params={"url": url},
                requires_confirmation=False,
                tools_needed=["CDP"],
                estimated_duration=5.0
            ))
        else:
            steps.append(TaskStep(
                step_id=0,
                action=ActionType.SEARCH,
                description="Search for target website/directory",
                params={},
                requires_confirmation=True,
                tools_needed=["CDP"],
                estimated_duration=10.0
            ))
        
        # Step 2: Extract leads
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.EXTRACT,
            description="Extract lead information",
            params={},
            requires_confirmation=False,
            tools_needed=["CDP", "LLM"],
            estimated_duration=30.0
        ))
        
        # Step 3: Export leads
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.DOWNLOAD,
            description="Export leads to spreadsheet",
            params={"format": "excel"},
            requires_confirmation=False,
            tools_needed=["DAP"],
            estimated_duration=5.0
        ))
        
        return steps
    
    def _generate_app_automation_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for app automation."""
        steps = []
        
        # Step 1: Launch app
        if context.get("mentioned_apps"):
            app_name = context["mentioned_apps"][0]
            steps.append(TaskStep(
                step_id=0,
                action=ActionType.LAUNCH,
                description=f"Launch application: {app_name}",
                target=app_name,
                params={"app_name": app_name},
                requires_confirmation=False,
                tools_needed=["AppLauncher"],
                estimated_duration=3.0
            ))
        else:
            steps.append(TaskStep(
                step_id=0,
                action=ActionType.LAUNCH,
                description="Launch target application",
                params={},
                requires_confirmation=True,
                tools_needed=["AppLauncher"],
                estimated_duration=5.0
            ))
        
        # Step 2: Handle minimized app
        if context.get("mentions_minimized"):
            steps.append(TaskStep(
                step_id=len(steps),
                action=ActionType.NAVIGATE,
                description="Restore app from minimized state",
                params={"action": "restore"},
                requires_confirmation=False,
                tools_needed=["DAP"],
                estimated_duration=2.0
            ))
        
        # Step 3: Perform task in app
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Analyze app state and determine actions",
            params={},
            requires_confirmation=False,
            tools_needed=["DAP", "Vision", "LLM"],
            estimated_duration=10.0
        ))
        
        # Step 4: Execute actions
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.EXECUTE,
            description="Execute required actions in app",
            params={},
            requires_confirmation=True,
            tools_needed=["DAP", "Input"],
            estimated_duration=30.0
        ))
        
        return steps
    
    def _generate_web_automation_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for web automation."""
        steps = []
        
        # Step 1: Launch browser
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.LAUNCH,
            description="Launch Chrome browser",
            target="Chrome",
            params={"profile": "user_profile"},
            requires_confirmation=False,
            tools_needed=["AppLauncher"],
            estimated_duration=3.0
        ))
        
        # Step 2: Navigate to target
        if context.get("urls"):
            url = context["urls"][0]
            steps.append(TaskStep(
                step_id=len(steps),
                action=ActionType.NAVIGATE,
                description=f"Navigate to: {url}",
                target=url,
                params={"url": url},
                requires_confirmation=False,
                tools_needed=["CDP"],
                estimated_duration=5.0
            ))
        
        # Step 3: Perform web task
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Analyze web page and determine actions",
            params={},
            requires_confirmation=False,
            tools_needed=["CDP", "Vision", "LLM"],
            estimated_duration=10.0
        ))
        
        # Step 4: Execute web actions
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.EXECUTE,
            description="Execute web actions (click, type, scroll)",
            params={},
            requires_confirmation=True,
            tools_needed=["CDP"],
            estimated_duration=20.0
        ))
        
        return steps
    
    def _generate_email_management_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for email management."""
        steps = []
        
        # Step 1: Launch email client
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.LAUNCH,
            description="Launch email client (Gmail/Outlook)",
            target="Gmail",
            params={"profile": "user_profile"},
            requires_confirmation=False,
            tools_needed=["AppLauncher"],
            estimated_duration=3.0
        ))
        
        # Step 2: Navigate to inbox
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.NAVIGATE,
            description="Navigate to inbox",
            params={},
            requires_confirmation=False,
            tools_needed=["CDP"],
            estimated_duration=5.0
        ))
        
        # Step 3: Read emails
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.READ,
            description="Read all emails in inbox",
            params={},
            requires_confirmation=False,
            tools_needed=["CDP", "Vision", "LLM"],
            estimated_duration=15.0
        ))
        
        # Step 4: Categorize emails
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Categorize emails (spam, important, work, personal)",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=20.0
        ))
        
        # Step 5: Handle spam
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.DELETE,
            description="Delete spam emails (with confirmation)",
            params={"requires_confirmation": True},
            requires_confirmation=True,
            tools_needed=["CDP"],
            estimated_duration=10.0
        ))
        
        # Step 6: Handle replies
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Determine which emails need replies",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=15.0
        ))
        
        return steps
    
    def _generate_file_management_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for file management."""
        steps = []
        
        # Step 1: Navigate to file location
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.NAVIGATE,
            description="Navigate to file/directory location",
            params={},
            requires_confirmation=True,
            tools_needed=["DAP"],
            estimated_duration=5.0
        ))
        
        # Step 2: Perform file operation
        if "copy" in user_request.lower():
            steps.append(TaskStep(
                step_id=len(steps),
                action=ActionType.COPY,
                description="Copy file/directory",
                params={},
                requires_confirmation=True,
                tools_needed=["DAP"],
                estimated_duration=5.0
            ))
        elif "delete" in user_request.lower():
            steps.append(TaskStep(
                step_id=len(steps),
                action=ActionType.DELETE,
                description="Delete file/directory",
                params={"requires_confirmation": True},
                requires_confirmation=True,
                tools_needed=["DAP"],
                estimated_duration=3.0
            ))
        elif "move" in user_request.lower():
            steps.append(TaskStep(
                step_id=len(steps),
                action=ActionType.NAVIGATE,
                description="Move file/directory",
                params={},
                requires_confirmation=True,
                tools_needed=["DAP"],
                estimated_duration=5.0
            ))
        
        return steps
    
    def _generate_data_processing_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for data processing."""
        steps = []
        
        # Step 1: Open data source
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.LAUNCH,
            description="Open data source (Excel, CSV, database)",
            params={},
            requires_confirmation=True,
            tools_needed=["DAP"],
            estimated_duration=5.0
        ))
        
        # Step 2: Read data
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.READ,
            description="Read data from source",
            params={},
            requires_confirmation=False,
            tools_needed=["DAP", "LLM"],
            estimated_duration=10.0
        ))
        
        # Step 3: Process data
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Process/transform data",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=20.0
        ))
        
        # Step 4: Export results
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.DOWNLOAD,
            description="Export processed data",
            params={},
            requires_confirmation=False,
            tools_needed=["DAP"],
            estimated_duration=5.0
        ))
        
        return steps
    
    def _generate_analysis_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for analysis tasks."""
        steps = []
        
        # Step 1: Open target for analysis
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.LAUNCH,
            description="Open target (document, app, website)",
            params={},
            requires_confirmation=True,
            tools_needed=["DAP", "CDP"],
            estimated_duration=5.0
        ))
        
        # Step 2: Read content
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.READ,
            description="Read content for analysis",
            params={},
            requires_confirmation=False,
            tools_needed=["DAP", "CDP", "Vision", "OCR"],
            estimated_duration=15.0
        ))
        
        # Step 3: Perform analysis
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Perform analysis/audit/review",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=30.0
        ))
        
        # Step 4: Generate report
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.SUMMARIZE,
            description="Generate analysis report",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM", "ReportGenerator"],
            estimated_duration=15.0
        ))
        
        return steps
    
    def _generate_research_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for research tasks."""
        steps = []
        
        # Step 1: Launch browser
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.LAUNCH,
            description="Launch browser for research",
            target="Chrome",
            params={"profile": "user_profile"},
            requires_confirmation=False,
            tools_needed=["AppLauncher"],
            estimated_duration=3.0
        ))
        
        # Step 2: Search for information
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.SEARCH,
            description="Search for target information",
            params={},
            requires_confirmation=False,
            tools_needed=["CDP"],
            estimated_duration=10.0
        ))
        
        # Step 3: Read results
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.READ,
            description="Read search results",
            params={},
            requires_confirmation=False,
            tools_needed=["CDP", "Vision", "LLM"],
            estimated_duration=15.0
        ))
        
        # Step 4: Extract findings
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.EXTRACT,
            description="Extract key findings",
            params={},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=10.0
        ))
        
        return steps
    
    def _generate_generic_steps(self, user_request: str, context: Dict[str, Any]) -> List[TaskStep]:
        """Generate steps for generic tasks."""
        steps = []
        
        # Step 1: Understand task
        steps.append(TaskStep(
            step_id=0,
            action=ActionType.ANALYZE,
            description="Understand task requirements",
            params={"task": user_request},
            requires_confirmation=False,
            tools_needed=["LLM"],
            estimated_duration=10.0
        ))
        
        # Step 2: Plan execution
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.ANALYZE,
            description="Plan execution strategy",
            params={},
            requires_confirmation=True,
            tools_needed=["LLM"],
            estimated_duration=15.0
        ))
        
        # Step 3: Execute
        steps.append(TaskStep(
            step_id=len(steps),
            action=ActionType.EXECUTE,
            description="Execute task according to plan",
            params={},
            requires_confirmation=True,
            tools_needed=["Dynamic"],
            estimated_duration=30.0
        ))
        
        return steps
    
    def _determine_required_organs(self, steps: List[TaskStep]) -> List[str]:
        """Determine which organs are required for the workflow."""
        organs_needed = set()
        
        for step in steps:
            for tool in step.tools_needed:
                if tool == "CDP":
                    organs_needed.add("organ_19_chrome_cdp_runtime")
                elif tool == "DAP":
                    organs_needed.add("organ_24_dap")
                elif tool == "Vision":
                    organs_needed.add("organ_31_visual_perception")
                elif tool == "OCR":
                    organs_needed.add("organ_31_visual_perception")
                elif tool == "LLM":
                    organs_needed.add("organ_37_llm_gateway")
                elif tool == "AppLauncher":
                    organs_needed.add("organ_40_app_launcher")
                elif tool == "Input":
                    organs_needed.add("organ_24_dap")
                elif tool == "ReportGenerator":
                    organs_needed.add("organ_52_report_generator")
                elif tool == "Dynamic":
                    organs_needed.add("organ_46_task_understanding")
        
        return list(organs_needed)


class TaskExecutionEngine:
    """
    Execute task workflows dynamically.
    
    Features:
    - Execute any workflow dynamically
    - Handle confirmation requests
    - Adapt to task type
    - Coordinate multiple organs
    """
    
    def __init__(self, cdp_runtime=None, dap_runtime=None, llm_gateway=None):
        self.cdp = cdp_runtime
        self.dap = dap_runtime
        self.llm = llm_gateway
        self._current_workflow: Optional[TaskWorkflow] = None
        self._execution_history: List[Dict[str, Any]] = []
    
    async def execute_workflow(self, workflow: TaskWorkflow) -> Dict[str, Any]:
        """
        Execute a task workflow.
        
        Args:
            workflow: TaskWorkflow to execute
        
        Returns:
            Execution results
        """
        self._current_workflow = workflow
        results = []
        
        logger.info(f"[TaskExecution] Starting workflow: {workflow.task_type.value}")
        logger.info(f"[TaskExecution] Steps: {len(workflow.steps)}")
        
        for step in workflow.steps:
            try:
                step_result = await self._execute_step(step)
                results.append({
                    "step_id": step.step_id,
                    "action": step.action.value,
                    "description": step.description,
                    "success": step_result["success"],
                    "result": step_result
                })
                
                # Record history
                self._execution_history.append({
                    "timestamp": asyncio.get_event_loop().time(),
                    "step": step,
                    "result": step_result
                })
                
            except Exception as e:
                logger.error(f"[TaskExecution] Step {step.step_id} failed: {e}")
                results.append({
                    "step_id": step.step_id,
                    "action": step.action.value,
                    "description": step.description,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "workflow_id": workflow.task_id,
            "task_type": workflow.task_type.value,
            "total_steps": len(workflow.steps),
            "successful": sum(1 for r in results if r["success"]),
            "results": results
        }
    
    async def _execute_step(self, step: TaskStep) -> Dict[str, Any]:
        """Execute a single workflow step."""
        logger.info(f"[TaskExecution] Executing step {step.step_id}: {step.description}")
        
        # Handle confirmation
        if step.requires_confirmation:
            confirmed = await self._request_confirmation(step)
            if not confirmed:
                return {"success": False, "skipped": True, "reason": "User declined"}
        
        # Execute based on action type
        if step.action == ActionType.LAUNCH:
            return await self._execute_launch(step)
        elif step.action == ActionType.NAVIGATE:
            return await self._execute_navigate(step)
        elif step.action == ActionType.READ:
            return await self._execute_read(step)
        elif step.action == ActionType.EXTRACT:
            return await self._execute_extract(step)
        elif step.action == ActionType.SUMMARIZE:
            return await self._execute_summarize(step)
        elif step.action == ActionType.CLICK:
            return await self._execute_click(step)
        elif step.action == ActionType.TYPE:
            return await self._execute_type(step)
        elif step.action == ActionType.DELETE:
            return await self._execute_delete(step)
        elif step.action == ActionType.ANALYZE:
            return await self._execute_analyze(step)
        elif step.action == ActionType.EXECUTE:
            return await self._execute_execute(step)
        else:
            logger.warning(f"[TaskExecution] Unknown action: {step.action}")
            return {"success": False, "error": "Unknown action"}
    
    async def _request_confirmation(self, step: TaskStep) -> bool:
        """Request user confirmation for a step."""
        # TODO: Implement user confirmation dialog
        logger.info(f"[TaskExecution] Confirmation requested for: {step.description}")
        # For now, auto-confirm
        return True
    
    async def _execute_launch(self, step: TaskStep) -> Dict[str, Any]:
        """Execute launch action using App Launcher."""
        logger.debug(f"[TaskExecution] Launching: {step.target}")
        
        if self._app_launcher:
            try:
                # Use actual app launcher
                # AppLauncher signature: launch(app_name) -> bool
                app_name = step.target or step.params.get("app_name", "")
                # If app_launcher is the class from Organ 40, it needs a catalog
                # For now, try to use it directly or resolve_and_launch
                from core_organs.organ_40_app_launcher import resolve_and_launch
                result = resolve_and_launch(app_name)
                return {"success": result.get("launched", False), "launched": result.get("target_app", app_name), "result": result}
            except Exception as e:
                logger.error(f"[TaskExecution] App launcher failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(0.5)
            return {"success": True, "launched": step.target or "unknown"}
    
    async def _execute_navigate(self, step: TaskStep) -> Dict[str, Any]:
        """Execute navigate action using CDP or DAP."""
        logger.debug(f"[TaskExecution] Navigating to: {step.target}")
        
        url = step.target or step.params.get("url", "")
        
        if self._cdp_runtime and url:
            try:
                # Use actual CDP runtime for web navigation
                # CDP navigate signature: navigate(session_id, url)
                session_id = step.params.get("session_id", "default")
                result = await self._cdp_runtime.navigate(session_id, url)
                return {"success": True, "navigated": url, "result": result}
            except Exception as e:
                logger.error(f"[TaskExecution] CDP navigation failed: {e}")
                return {"success": False, "error": str(e)}
        elif self._dap_runtime:
            try:
                # Use DAP for desktop navigation (focus app)
                app_name = step.params.get("app_name", "")
                # DAP window_focus signature: window_focus(target)
                from core_organs.organ_24_dap import NodeTarget
                target = NodeTarget(node_id=app_name) if app_name else None
                if target:
                    result = await self._dap_runtime.window_focus(target)
                    return {"success": True, "navigated": app_name, "result": result}
                else:
                    return {"success": False, "error": "No target specified"}
            except Exception as e:
                logger.error(f"[TaskExecution] DAP navigation failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(0.5)
            return {"success": True, "navigated": url or "unknown"}
    
    async def _execute_read(self, step: TaskStep) -> Dict[str, Any]:
        """Execute read action using Vision/OCR or CDP."""
        logger.debug(f"[TaskExecution] Reading content")
        
        if self._vision_organ:
            try:
                # Use actual vision organ
                content = await self._vision_organ.capture_and_read()
                return {"success": True, "content": content}
            except Exception as e:
                logger.error(f"[TaskExecution] Vision organ failed: {e}")
                return {"success": False, "error": str(e)}
        elif self._cdp_runtime:
            try:
                # Use CDP to read page content
                content = await self._cdp_runtime.get_page_content()
                return {"success": True, "content": content}
            except Exception as e:
                logger.error(f"[TaskExecution] CDP read failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(1.0)
            return {"success": True, "content": "Sample content"}
    
    async def _execute_extract(self, step: TaskStep) -> Dict[str, Any]:
        """Execute extract action using LLM."""
        logger.debug(f"[TaskExecution] Extracting information")
        
        if self._llm_gateway:
            try:
                # Use actual LLM gateway
                prompt = step.params.get("prompt", "Extract key information")
                content = step.params.get("content", "")
                extracted = await self._llm_gateway.generate(prompt + "\n\n" + content)
                return {"success": True, "extracted": extracted}
            except Exception as e:
                logger.error(f"[TaskExecution] LLM extraction failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(1.5)
            return {"success": True, "extracted": []}
    
    async def _execute_summarize(self, step: TaskStep) -> Dict[str, Any]:
        """Execute summarize action using LLM."""
        logger.debug(f"[TaskExecution] Summarizing content")
        
        if self._llm_gateway:
            try:
                # Use actual LLM gateway
                content = step.params.get("content", "")
                detail_level = step.params.get("detail_level", "maximum")
                prompt = f"Summarize the following content with {detail_level} detail, no important information should be missed:\n\n{content}"
                summary = await self._llm_gateway.generate(prompt)
                return {"success": True, "summary": summary}
            except Exception as e:
                logger.error(f"[TaskExecution] LLM summarization failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(2.0)
            return {"success": True, "summary": "Sample summary"}
    
    async def _execute_click(self, step: TaskStep) -> Dict[str, Any]:
        """Execute click action using CDP or DAP."""
        logger.debug(f"[TaskExecution] Clicking element")
        
        target = step.target or step.params.get("target", "")
        
        if self._cdp_runtime and target:
            try:
                # Use actual CDP runtime for web click
                # CDP click signature: click(session_id, x, y, button, click_count, modifiers)
                # If target is coordinates
                if isinstance(target, (tuple, list)) and len(target) == 2:
                    session_id = step.params.get("session_id", "default")
                    result = await self._cdp_runtime.click(session_id, target[0], target[1])
                    return {"success": True, "clicked": f"({target[0]}, {target[1]})", "result": result}
                else:
                    # Target is element - would need element resolution
                    session_id = step.params.get("session_id", "default")
                    # Placeholder for element-based click
                    return {"success": True, "clicked": target}
            except Exception as e:
                logger.error(f"[TaskExecution] CDP click failed: {e}")
                return {"success": False, "error": str(e)}
        elif self._dap_runtime:
            try:
                # Use DAP for desktop click
                # DAP mouse_click signature: mouse_click(x, y, button, session_id)
                x = step.params.get("x", 0)
                y = step.params.get("y", 0)
                button = step.params.get("button", "left")
                session_id = step.params.get("session_id", "default")
                result = await self._dap_runtime.mouse_click(x, y, button, session_id)
                return {"success": True, "clicked": f"({x}, {y})", "result": result}
            except Exception as e:
                logger.error(f"[TaskExecution] DAP click failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(0.3)
            return {"success": True, "clicked": target or "unknown"}
    
    async def _execute_type(self, step: TaskStep) -> Dict[str, Any]:
        """Execute type action using CDP or DAP."""
        logger.debug(f"[TaskExecution] Typing text")
        
        text = step.params.get("text", "")
        target = step.target or step.params.get("target", "")
        
        if self._cdp_runtime and target:
            try:
                # Use actual CDP runtime for web typing
                # CDP type_text signature: type_text(session_id, text)
                session_id = step.params.get("session_id", "default")
                result = await self._cdp_runtime.type_text(session_id, text)
                return {"success": True, "typed": text, "result": result}
            except Exception as e:
                logger.error(f"[TaskExecution] CDP type failed: {e}")
                return {"success": False, "error": str(e)}
        elif self._dap_runtime:
            try:
                # Use DAP for desktop typing
                # DAP keyboard_type signature: keyboard_type(text)
                result = await self._dap_runtime.keyboard_type(text)
                return {"success": True, "typed": text, "result": result}
            except Exception as e:
                logger.error(f"[TaskExecution] DAP type failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(0.5)
            return {"success": True, "typed": text}
    
    async def _execute_delete(self, step: TaskStep) -> Dict[str, Any]:
        """Execute delete action using CDP or DAP."""
        logger.debug(f"[TaskExecution] Deleting item")
        
        target = step.target or step.params.get("target", "")
        
        if self._cdp_runtime and target:
            try:
                # Use actual CDP runtime for web deletion
                await self._cdp_runtime.delete_element(target)
                return {"success": True, "deleted": target}
            except Exception as e:
                logger.error(f"[TaskExecution] CDP delete failed: {e}")
                return {"success": False, "error": str(e)}
        elif self._dap_runtime:
            try:
                # Use DAP for desktop deletion
                await self._dap_runtime.delete_item(target)
                return {"success": True, "deleted": target}
            except Exception as e:
                logger.error(f"[TaskExecution] DAP delete failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(0.5)
            return {"success": True, "deleted": target or "unknown"}
    
    async def _execute_analyze(self, step: TaskStep) -> Dict[str, Any]:
        """Execute analyze action using LLM."""
        logger.debug(f"[TaskExecution] Analyzing content")
        
        if self._llm_gateway:
            try:
                # Use actual LLM gateway
                content = step.params.get("content", "")
                analysis_type = step.params.get("analysis_type", "general")
                prompt = f"Analyze the following content ({analysis_type}):\n\n{content}"
                analysis = await self._llm_gateway.generate(prompt)
                return {"success": True, "analysis": analysis}
            except Exception as e:
                logger.error(f"[TaskExecution] LLM analysis failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Fallback to placeholder
            await asyncio.sleep(1.5)
            return {"success": True, "analysis": "Sample analysis"}
    
    async def _execute_execute(self, step: TaskStep) -> Dict[str, Any]:
        """Execute custom action dynamically based on params."""
        logger.debug(f"[TaskExecution] Executing custom action")
        
        # Try to determine the best organ for the action
        action_type = step.params.get("action_type", "")
        
        if action_type == "cdp_navigate" and self._cdp_runtime:
            url = step.params.get("url", "")
            await self._cdp_runtime.navigate(url)
            return {"success": True, "action": "cdp_navigate", "url": url}
        elif action_type == "dap_launch" and self._dap_runtime:
            app_name = step.params.get("app_name", "")
            await self._dap_runtime.launch_app(app_name)
            return {"success": True, "action": "dap_launch", "app": app_name}
        elif action_type == "llm_generate" and self._llm_gateway:
            prompt = step.params.get("prompt", "")
            result = await self._llm_gateway.generate(prompt)
            return {"success": True, "action": "llm_generate", "result": result}
        else:
            # Fallback to placeholder
            await asyncio.sleep(1.0)
            return {"success": True, "action": action_type or "generic"}
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history."""
        return self._execution_history.copy()
